from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any


class RateLimiter:
    """Configurable fixed-window limiter: sqlite by default, redis when configured."""

    def __init__(self, limit_per_minute: int, db_path: str, *, backend: str = "sqlite", redis_url: str | None = None) -> None:
        self._limit = limit_per_minute
        self._db_path = db_path
        self._backend = backend
        self._redis_url = redis_url
        self._lock = Lock()
        self._redis = None
        if backend == "redis" and redis_url:
            self._redis = self._init_redis(redis_url)
        self._init_sqlite()

    def _init_redis(self, redis_url: str) -> Any | None:
        try:
            import redis
        except Exception:
            return None
        try:
            client = redis.from_url(redis_url, decode_responses=True)  # type: ignore[no-untyped-call]
            client.ping()
            return client
        except Exception:
            return None

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, check_same_thread=False)

    def _init_sqlite(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rate_limits (
                    key TEXT NOT NULL,
                    window_start INTEGER NOT NULL,
                    count INTEGER NOT NULL,
                    PRIMARY KEY (key, window_start)
                )
                """
            )
            conn.commit()

    def allow(self, key: str) -> bool:
        now = datetime.now(UTC)
        window_start = int(now.timestamp() // 60)
        if self._redis is not None:
            redis_key = f"rl:{key}:{window_start}"
            value = int(self._redis.incr(redis_key))
            if value == 1:
                self._redis.expire(redis_key, 65)
            return value <= self._limit

        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT count FROM rate_limits WHERE key = ? AND window_start = ?",
                (key, window_start),
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO rate_limits(key, window_start, count) VALUES (?, ?, ?)",
                    (key, window_start, 1),
                )
                conn.commit()
                return True
            current = int(row[0])
            if current >= self._limit:
                return False
            conn.execute(
                "UPDATE rate_limits SET count = ? WHERE key = ? AND window_start = ?",
                (current + 1, key, window_start),
            )
            conn.commit()
            return True
