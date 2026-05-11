from shrag.ingest import index_lifecycle, partition, reindex, worker
from shrag.ingest.worker import IngestJob, IngestWorker


def test_small_ingest_helpers():
    assert index_lifecycle.cutover("v1", "") == "v1"
    assert index_lifecycle.cutover("v1", "v2") == "v2"
    assert partition.partition_key("t", "n") == "t:n"
    assert reindex.should_reindex(0.3, threshold=0.2) is True


def test_worker_local_enqueue_and_status(monkeypatch):
    monkeypatch.setattr(worker, "_get_redis", lambda: None)
    job_id = worker.enqueue_ingest_job("s1", "hello world")
    status = worker.get_job_status(job_id)
    assert status is not None
    assert status["source_id"] == "s1"


def test_worker_process_one_success(monkeypatch):
    monkeypatch.setattr(worker, "_process_job", lambda job: None)
    w = IngestWorker(concurrency=1, max_retries=1)
    job = IngestJob(job_id="j1", source_id="s", content="x")
    w._process_one(job, None)
    assert worker.get_job_status("j1")["status"] == "completed"


def test_worker_process_one_failure_retries(monkeypatch):
    def fail(_job):
        raise RuntimeError("boom")

    monkeypatch.setattr(worker, "_process_job", fail)
    monkeypatch.setattr(worker, "_enqueue_local", lambda job: None)
    w = IngestWorker(concurrency=1, max_retries=2)
    job = IngestJob(job_id="j2", source_id="s", content="x")
    w._process_one(job, None)
    assert worker.get_job_status("j2")["status"] == "pending"
    assert worker.get_job_status("j2")["retries"] == 1
