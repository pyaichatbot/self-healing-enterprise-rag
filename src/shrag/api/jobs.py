from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from uuid import NAMESPACE_URL, uuid5


@dataclass(slots=True)
class Job:
    id: str
    kind: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    status: str = "accepted"
    idempotency_key: str | None = None


class JobRegistry:
    """SQLite-backed job registry with deterministic IDs for idempotent writes."""

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
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    idempotency_key TEXT
                )
                """
            )
            conn.commit()

    def create_deterministic(self, kind: str, idempotency_key: str) -> tuple[Job, bool]:
        stable_id = str(uuid5(NAMESPACE_URL, f"{kind}:{idempotency_key}"))
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT id, kind, created_at, status, idempotency_key FROM jobs WHERE id = ?",
                (stable_id,),
            ).fetchone()
            if row is not None:
                return self._to_job(row), False
            created_at = datetime.now(UTC).isoformat()
            conn.execute(
                "INSERT INTO jobs(id, kind, created_at, status, idempotency_key) VALUES (?, ?, ?, ?, ?)",
                (stable_id, kind, created_at, "accepted", idempotency_key),
            )
            conn.commit()
            return Job(id=stable_id, kind=kind, created_at=datetime.fromisoformat(created_at), status="accepted", idempotency_key=idempotency_key), True

    def get(self, job_id: str) -> Job | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT id, kind, created_at, status, idempotency_key FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            return self._to_job(row) if row is not None else None

    def update_status(self, job_id: str, status: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))
            conn.commit()

    @staticmethod
    def _to_job(row: tuple[str, str, str, str, str | None]) -> Job:
        return Job(
            id=row[0],
            kind=row[1],
            created_at=datetime.fromisoformat(row[2]),
            status=row[3],
            idempotency_key=row[4],
        )
