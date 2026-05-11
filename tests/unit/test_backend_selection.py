from shrag.api.rate_limit import RateLimiter
import pytest

from shrag.ingest.store import SQLiteChunkStore, build_store, get_store, reset_store_for_testing


def test_rate_limiter_falls_back_when_redis_unavailable(tmp_path):
    db_path = str(tmp_path / "state.db")
    limiter = RateLimiter(2, db_path, backend="redis", redis_url="redis://127.0.0.1:6399/0")
    assert limiter.allow("k") is True
    assert limiter.allow("k") is True
    assert limiter.allow("k") is False


def test_store_defaults_to_sqlite_without_qdrant_url(tmp_path):
    store = build_store(vector_backend="qdrant", qdrant_url=None, sqlite_db_path=str(tmp_path / "state.db"))
    assert isinstance(store, SQLiteChunkStore)


def test_store_rejects_unknown_backend(tmp_path):
    with pytest.raises(ValueError, match="Unsupported vector backend"):
        build_store(vector_backend="unknown", sqlite_db_path=str(tmp_path / "state.db"))


def test_get_store_is_singleton_until_reset():
    reset_store_for_testing()
    first = get_store()
    second = get_store()
    assert first is second
