from fastapi.testclient import TestClient

from shrag.app import app


client = TestClient(app)


def test_docs_endpoint_is_idempotent_when_idempotency_key_is_reused():
    payload = {
        "documents": [
            {"document_id": "doc-a", "text": "alpha"},
            {"document_id": "doc-b", "text": "beta"},
        ]
    }
    headers = {
        "X-API-Version": "2026-05-01",
        "X-User-Id": "writer-1",
        "X-Tenant-Id": "tenant-a",
        "X-Roles": "writer",
        "Idempotency-Key": "docs-batch-001",
    }

    first = client.post("/docs", json=payload, headers=headers)
    second = client.post("/docs", json=payload, headers=headers)

    assert first.status_code == 202
    assert second.status_code == 202
    first_job = first.json().get("job_id")
    second_job = second.json().get("job_id")
    assert first_job
    assert second_job
    assert first_job == second_job
