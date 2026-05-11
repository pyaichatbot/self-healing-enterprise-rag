from fastapi.testclient import TestClient

from shrag.app import app


client = TestClient(app)


def test_metrics_exposes_stage_bulkhead_counters():
    headers = {
        "X-API-Version": "2026-05-01",
        "X-User-Id": "reader-1",
        "X-Tenant-Id": "tenant-a",
        "X-Roles": "reader",
    }

    response = client.get("/metrics", headers=headers)
    assert response.status_code == 200
    counters = response.json()["counters"]
    assert "inflight" in counters
    assert "retrieve_inflight" in counters
    assert "grade_inflight" in counters
    assert "generate_inflight" in counters
    assert "reflect_inflight" in counters
    assert "heal_inflight" in counters
    assert "ingest_inflight" in counters
