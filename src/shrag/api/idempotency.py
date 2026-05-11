from __future__ import annotations

import sqlite3
from pathlib import Path
from threading import Lock


class IdempotencyStore:
    """SQLite-backed idempotency key store."""

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
                CREATE TABLE IF NOT EXISTS idempotency_keys (
                    key TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def seen(self, key: str) -> bool:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT 1 FROM idempotency_keys WHERE key = ?", (key,)).fetchone()
            return row is not None

    def mark(self, key: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO idempotency_keys(key, created_at) VALUES (?, datetime('now'))",
                (key,),
            )
            conn.commit()
