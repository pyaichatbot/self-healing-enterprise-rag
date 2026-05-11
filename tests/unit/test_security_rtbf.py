from __future__ import annotations

import sqlite3
from pathlib import Path

from shrag.security.rtbf import rtbf_certificate


def _seed_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id TEXT PRIMARY KEY,
                source_id TEXT,
                subject_id TEXT,
                text TEXT
            )
            """
        )
        conn.execute("CREATE TABLE IF NOT EXISTS requests (id INTEGER PRIMARY KEY, user_id TEXT)")
        conn.execute("INSERT INTO chunks(chunk_id, source_id, subject_id, text) VALUES ('c1', 's1', 'user-1', 'hello')")
        conn.execute("INSERT INTO requests(user_id) VALUES ('user-1')")
        conn.commit()


def test_rtbf_dry_run_keeps_data(monkeypatch, tmp_path):
    db_path = tmp_path / "state.db"
    _seed_db(db_path)

    monkeypatch.setenv("SHRAG_VECTOR_BACKEND", "sqlite")
    monkeypatch.setenv("SHRAG_STATE_DB_PATH", str(db_path))

    result = rtbf_certificate("user-1", dry_run=True)

    assert result["status"] == "dry_run"
    assert result["deleted_chunks"] == 1
    assert result["deleted_requests"] == 1

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM chunks WHERE subject_id='user-1'").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM requests WHERE user_id='user-1'").fetchone()[0] == 1


def test_rtbf_purge_deletes_and_writes_audit(monkeypatch, tmp_path):
    db_path = tmp_path / "state.db"
    _seed_db(db_path)

    monkeypatch.setenv("SHRAG_VECTOR_BACKEND", "sqlite")
    monkeypatch.setenv("SHRAG_STATE_DB_PATH", str(db_path))

    result = rtbf_certificate("user-1", dry_run=False)

    assert result["status"] == "purged"
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM chunks WHERE subject_id='user-1'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM requests WHERE user_id='user-1'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM rtbf_audit WHERE subject_id='user-1'").fetchone()[0] == 1


def test_rtbf_unknown_backend_is_safe_noop(monkeypatch):
    monkeypatch.setenv("SHRAG_VECTOR_BACKEND", "unknown")
    out = rtbf_certificate("user-404", dry_run=True)
    assert out["status"] == "dry_run"
    assert out["deleted_chunks"] == 0
