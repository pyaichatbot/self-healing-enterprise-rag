from __future__ import annotations

from types import SimpleNamespace

from shrag.ingest import worker


class _FakeRedis:
    def __init__(self, payload=None):
        self.payload = payload
        self.acked: list[str] = []
        self.dlq: list[str] = []
        self.enqueued: list[str] = []

    def brpoplpush(self, src, dst, timeout=0):
        _ = (src, dst, timeout)
        return self.payload


class _DoneFuture:
    def done(self) -> bool:
        return True


class _SyncExecutor:
    def __init__(self):
        self.calls = 0

    def submit(self, fn, *args, **kwargs):
        self.calls += 1
        fn(*args, **kwargs)
        return _DoneFuture()

    def shutdown(self, wait=True):
        _ = wait


def test_enqueue_local_and_status_tracking():
    worker._local_queue.clear()
    worker._status_store.clear()

    job_id = worker.enqueue_ingest_job("source-a", "plain text content", template="naive")

    assert job_id
    status = worker.get_job_status(job_id)
    assert status is not None
    assert status["status"] == "pending"
    assert worker._local_queue


def test_dequeue_redis_bad_payload_returns_none():
    r = _FakeRedis(payload="{bad-json")
    assert worker._dequeue_redis(r, timeout=1) is None


def test_worker_process_one_marks_completed(monkeypatch):
    worker._status_store.clear()
    w = worker.IngestWorker(max_retries=2)
    job = worker.IngestJob(job_id="j1", source_id="s1", content="content")

    monkeypatch.setattr(worker, "_process_job", lambda _job: None)

    w._process_one(job, r=None)

    assert worker.get_job_status("j1")["status"] == "completed"


def test_complete_job_calls_ack_when_redis_present(monkeypatch):
    worker._status_store.clear()
    w = worker.IngestWorker(max_retries=2)
    job = worker.IngestJob(job_id="j-ack", source_id="s", content="x")
    called = {"ack": 0}

    monkeypatch.setattr(worker, "_ack_redis", lambda r, j: called.__setitem__("ack", called["ack"] + 1))
    w._complete_job(job, r=_FakeRedis())

    assert worker.get_job_status("j-ack")["status"] == "completed"
    assert called["ack"] == 1


def test_worker_process_one_requeues_on_retryable_failure(monkeypatch):
    worker._status_store.clear()
    worker._local_queue.clear()
    w = worker.IngestWorker(max_retries=2)
    job = worker.IngestJob(job_id="j2", source_id="s2", content="content")

    def _boom(_job):
        raise RuntimeError("transient")

    monkeypatch.setattr(worker, "_process_job", _boom)

    w._process_one(job, r=None)

    status = worker.get_job_status("j2")
    assert status is not None
    assert status["status"] == "pending"
    assert status["retries"] == 1
    assert worker._local_queue and worker._local_queue[0].job_id == "j2"


def test_failure_with_redis_reenqueue_before_max_retries(monkeypatch):
    worker._status_store.clear()
    w = worker.IngestWorker(max_retries=3)
    job = worker.IngestJob(job_id="j-redis-retry", source_id="s", content="x")
    called = {"enqueue": 0}

    monkeypatch.setattr(worker, "_enqueue_redis", lambda r, j: called.__setitem__("enqueue", called["enqueue"] + 1))
    w._handle_job_failure(job, r=_FakeRedis(), exc=RuntimeError("retry"))

    status = worker.get_job_status("j-redis-retry")
    assert status is not None
    assert status["status"] == "pending"
    assert status["retries"] == 1
    assert called["enqueue"] == 1


def test_failure_with_redis_dlq_on_max_retries(monkeypatch):
    worker._status_store.clear()
    w = worker.IngestWorker(max_retries=1)
    job = worker.IngestJob(job_id="j-dlq", source_id="s", content="x")
    called = {"dlq": 0}

    monkeypatch.setattr(worker, "_dlq_redis", lambda r, j: called.__setitem__("dlq", called["dlq"] + 1))
    w._handle_job_failure(job, r=_FakeRedis(), exc=RuntimeError("fatal"))

    status = worker.get_job_status("j-dlq")
    assert status is not None
    assert status["status"] == "failed"
    assert status["retries"] == 1
    assert called["dlq"] == 1


def test_worker_process_one_marks_failed_after_max_retries(monkeypatch):
    worker._status_store.clear()
    worker._local_queue.clear()
    w = worker.IngestWorker(max_retries=1)
    job = worker.IngestJob(job_id="j3", source_id="s3", content="content")

    monkeypatch.setattr(worker, "_process_job", lambda _job: (_ for _ in ()).throw(RuntimeError("fatal")))

    w._process_one(job, r=None)

    status = worker.get_job_status("j3")
    assert status is not None
    assert status["status"] == "failed"
    assert status["retries"] == 1


def test_run_processes_one_job_and_prunes_future(monkeypatch):
    worker._status_store.clear()
    worker._local_queue.clear()
    w = worker.IngestWorker(max_retries=1)
    w._executor = _SyncExecutor()
    job = worker.IngestJob(job_id="run-1", source_id="s", content="x")
    worker._enqueue_local(job)

    monkeypatch.setattr(worker, "_get_redis", lambda: None)
    monkeypatch.setattr(worker, "_process_job", lambda _job: None)

    state = {"calls": 0}

    original_dequeue_local = worker._dequeue_local

    def _deq():
        state["calls"] += 1
        if state["calls"] == 1:
            return original_dequeue_local()
        w._stop_event.set()
        return None

    monkeypatch.setattr(worker, "_dequeue_local", _deq)

    w.run()

    assert worker.get_job_status("run-1")["status"] == "completed"
    assert w._futures == []


def test_process_job_url_fetch_flow(monkeypatch):
    calls = {"fetch": 0, "upsert": 0}

    monkeypatch.setattr(worker, "_fetch_url", lambda url: calls.__setitem__("fetch", calls["fetch"] + 1) or "Fetched body")

    fake_chunk = SimpleNamespace(
        chunk_id="c1",
        text="Fetched body",
        template="naive",
        token_estimate=2,
        metadata={},
    )
    monkeypatch.setattr("shrag.ingest.chunker.chunk_document", lambda *args, **kwargs: [fake_chunk])
    monkeypatch.setattr("shrag.ingest.embed.embed_batch", lambda texts: [(0.1, 0.2)])
    monkeypatch.setattr(worker, "_upsert_sqlite", lambda chunks, vectors, job: calls.__setitem__("upsert", calls["upsert"] + 1))

    job = worker.IngestJob(job_id="url-1", source_id="s", content="https://example.com/doc")
    worker._process_job(job)

    assert calls["fetch"] == 1
    assert calls["upsert"] == 1
