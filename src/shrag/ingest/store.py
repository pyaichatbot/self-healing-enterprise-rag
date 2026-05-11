from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Protocol

from shrag.observe.models import RetrievedChunk
from shrag.settings import settings


class ChunkStore(Protocol):
    def upsert(self, chunk: RetrievedChunk) -> None: ...
    def delete_by_source(self, source_id: str) -> None: ...
    def all(self) -> tuple[RetrievedChunk, ...]: ...


class VectorStoreBackend(Protocol):
    name: str
    supports_vector_search: bool
    supports_filtering: bool
    operational: bool


class SQLiteChunkStore:
    name = "sqlite"
    supports_vector_search = False
    supports_filtering = True
    operational = True

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._lock = Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, check_same_thread=False)

    def _init_db(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    score REAL NOT NULL,
                    rank INTEGER NOT NULL,
                    metadata_json TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def upsert(self, chunk: RetrievedChunk) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO chunks(chunk_id, source_id, text, score, rank, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(chunk_id) DO UPDATE SET
                    source_id=excluded.source_id,
                    text=excluded.text,
                    score=excluded.score,
                    rank=excluded.rank,
                    metadata_json=excluded.metadata_json
                """,
                (
                    chunk.chunk_id,
                    chunk.source_id,
                    chunk.text,
                    float(chunk.score),
                    int(chunk.rank),
                    json.dumps(dict(chunk.metadata)),
                ),
            )
            conn.commit()

    def delete_by_source(self, source_id: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM chunks WHERE source_id = ?", (source_id,))
            conn.commit()

    def all(self) -> tuple[RetrievedChunk, ...]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT chunk_id, source_id, text, score, rank, metadata_json FROM chunks"
            ).fetchall()
        return tuple(
            RetrievedChunk(
                chunk_id=row[0],
                source_id=row[1],
                text=row[2],
                score=float(row[3]),
                rank=int(row[4]),
                metadata=json.loads(row[5]) if row[5] else {},
            )
            for row in rows
        )


class QdrantChunkStore:
    name = "qdrant"
    supports_vector_search = True
    supports_filtering = True

    def __init__(self, url: str, collection: str) -> None:
        self._url = url
        self._collection = collection
        self._client = self._init_client(url)
        self._ready = self._client is not None
        self.operational = self._ready
        if self._ready:
            self._ensure_collection()

    def _init_client(self, url: str) -> Any | None:
        try:
            from qdrant_client import QdrantClient
        except Exception:
            return None
        try:
            return QdrantClient(url=url)
        except Exception:
            return None

    def _ensure_collection(self) -> None:
        if self._client is None:
            return
        try:
            self._client.get_collection(self._collection)
        except Exception:
            try:
                from qdrant_client.models import Distance, VectorParams

                self._client.recreate_collection(
                    collection_name=self._collection,
                    vectors_config=VectorParams(size=8, distance=Distance.COSINE),
                )
            except Exception:
                self._ready = False
                self.operational = False

    def upsert(self, chunk: RetrievedChunk) -> None:
        if not self._ready or self._client is None:
            return
        try:
            from qdrant_client.models import PointStruct

            vector = [float((ord(ch) % 31) / 31.0) for ch in chunk.text[:8]]
            vector += [0.0] * (8 - len(vector))
            self._client.upsert(
                collection_name=self._collection,
                points=[
                    PointStruct(
                        id=str(uuid.uuid5(uuid.NAMESPACE_URL, chunk.chunk_id)),
                        vector=vector[:8],
                        payload={
                            "chunk_id": chunk.chunk_id,
                            "source_id": chunk.source_id,
                            "text": chunk.text,
                            "score": chunk.score,
                            "rank": chunk.rank,
                            "metadata": dict(chunk.metadata),
                        },
                    )
                ],
            )
        except Exception:
            self._ready = False
            self.operational = False

    def delete_by_source(self, source_id: str) -> None:
        if not self._ready or self._client is None:
            return
        try:
            from qdrant_client.models import FieldCondition, Filter, MatchValue

            self._client.delete(
                collection_name=self._collection,
                points_selector=Filter(
                    must=[FieldCondition(key="source_id", match=MatchValue(value=source_id))]
                ),
            )
        except Exception:
            self._ready = False
            self.operational = False

    def all(self) -> tuple[RetrievedChunk, ...]:
        if not self._ready or self._client is None:
            return ()
        try:
            points, _ = self._client.scroll(collection_name=self._collection, limit=10_000, with_payload=True)
            chunks: list[RetrievedChunk] = []
            for point in points:
                payload = point.payload or {}
                chunks.append(
                    RetrievedChunk(
                        chunk_id=str(payload.get("chunk_id", "")),
                        source_id=str(payload.get("source_id", "")),
                        text=str(payload.get("text", "")),
                        score=float(payload.get("score", 0.0)),
                        rank=int(payload.get("rank", 0)),
                        metadata=payload.get("metadata") or {},
                    )
                )
            return tuple(chunks)
        except Exception:
            self._ready = False
            self.operational = False
            return ()


StoreBuilder = Callable[[], ChunkStore]


def _build_sqlite_store(sqlite_db_path: str) -> ChunkStore:
    return SQLiteChunkStore(sqlite_db_path)


def _build_qdrant_store(qdrant_url: str | None, qdrant_collection: str) -> ChunkStore | None:
    if not qdrant_url:
        return None
    qdrant = QdrantChunkStore(qdrant_url, qdrant_collection)
    return qdrant if qdrant._ready else None


def build_store(
    *,
    vector_backend: str | None = None,
    qdrant_url: str | None = None,
    qdrant_collection: str | None = None,
    sqlite_db_path: str | None = None,
) -> ChunkStore:
    backend = vector_backend or settings.vector_backend
    q_url = qdrant_url if qdrant_url is not None else settings.qdrant_url
    q_collection = qdrant_collection or settings.qdrant_collection
    db_path = sqlite_db_path or settings.state_db_path
    registry: dict[str, StoreBuilder] = {
        "sqlite": lambda: _build_sqlite_store(db_path),
        "qdrant": lambda: _build_qdrant_store(q_url, q_collection) or _build_sqlite_store(db_path),
    }
    if backend not in registry:
        raise ValueError(f"Unsupported vector backend '{backend}'. Supported: {', '.join(sorted(registry))}")
    return registry[backend]()


_store_lock = Lock()
_store_instance: ChunkStore | None = None


def get_store() -> ChunkStore:
    global _store_instance
    if _store_instance is None:
        with _store_lock:
            if _store_instance is None:
                _store_instance = build_store()
    return _store_instance


def reset_store_for_testing() -> None:
    global _store_instance
    with _store_lock:
        _store_instance = None


def set_store_for_testing(store: ChunkStore) -> None:
    global _store_instance
    with _store_lock:
        _store_instance = store
