from __future__ import annotations

import sys
import types

from shrag.ingest.store import SQLiteChunkStore, build_store, reset_store_for_testing, set_store_for_testing
from shrag.observe.models import RetrievedChunk


def _chunk(chunk_id: str, source_id: str, text: str) -> RetrievedChunk:
    return RetrievedChunk(chunk_id=chunk_id, source_id=source_id, text=text, score=0.2, rank=1, metadata={"k": "v"})


def test_sqlite_store_upsert_all_and_delete(tmp_path):
    db_path = tmp_path / "state.db"
    store = SQLiteChunkStore(str(db_path))
    store.upsert(_chunk("c1", "s1", "text1"))
    store.upsert(_chunk("c2", "s2", "text2"))
    store.upsert(_chunk("c1", "s1", "text1-updated"))
    all_chunks = store.all()
    assert len(all_chunks) == 2
    assert any(c.text == "text1-updated" for c in all_chunks)
    store.delete_by_source("s1")
    assert {c.source_id for c in store.all()} == {"s2"}


def test_build_store_qdrant_falls_back_to_sqlite_without_url(tmp_path):
    store = build_store(vector_backend="qdrant", qdrant_url=None, sqlite_db_path=str(tmp_path / "state.db"))
    assert isinstance(store, SQLiteChunkStore)


def test_set_store_for_testing_replaces_singleton(tmp_path):
    reset_store_for_testing()
    store = SQLiteChunkStore(str(tmp_path / "state.db"))
    set_store_for_testing(store)
    from shrag.ingest.store import get_store

    assert get_store() is store


def test_qdrant_store_happy_paths(monkeypatch):
    deleted = {}

    class _Client:
        def __init__(self, url=""):  # type: ignore[no-untyped-def]
            self.url = url
            self.points = []

        def get_collection(self, name):  # type: ignore[no-untyped-def]
            return {"name": name}

        def upsert(self, **kwargs):  # type: ignore[no-untyped-def]
            self.points = kwargs["points"]

        def delete(self, **kwargs):  # type: ignore[no-untyped-def]
            deleted["ok"] = True

        def scroll(self, **kwargs):  # type: ignore[no-untyped-def]
            payload = {"chunk_id": "c1", "source_id": "s1", "text": "t1", "score": 0.1, "rank": 1, "metadata": {}}
            return ([types.SimpleNamespace(payload=payload)], None)

    models = types.SimpleNamespace(
        Distance=types.SimpleNamespace(COSINE="cosine"),
        VectorParams=lambda size, distance: {"size": size, "distance": distance},
        PointStruct=lambda **kwargs: types.SimpleNamespace(**kwargs),
        FieldCondition=lambda **kwargs: types.SimpleNamespace(**kwargs),
        Filter=lambda **kwargs: types.SimpleNamespace(**kwargs),
        MatchValue=lambda **kwargs: types.SimpleNamespace(**kwargs),
    )
    qmod = types.SimpleNamespace(QdrantClient=_Client, models=models)
    monkeypatch.setitem(sys.modules, "qdrant_client", qmod)
    monkeypatch.setitem(sys.modules, "qdrant_client.models", models)

    store = build_store(vector_backend="qdrant", qdrant_url="http://qdrant:6333", qdrant_collection="x", sqlite_db_path=":memory:")
    store.upsert(_chunk("c1", "s1", "hello"))
    assert store.all()[0].chunk_id == "c1"
    store.delete_by_source("s1")
    assert deleted["ok"] is True
