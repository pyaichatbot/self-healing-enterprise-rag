from fastapi.testclient import TestClient

from shrag.app import app


client = TestClient(app)


def test_query_requires_api_version_header():
    response = client.post(
        "/query",
        json={"query": "what is rag", "top_k": 2},
        headers={"X-User-Id": "reader-1", "X-Roles": "reader", "X-Tenant-Id": "tenant-a"},
    )
    assert response.status_code == 400


def test_query_rejects_deprecated_api_version():
    response = client.post(
        "/query",
        json={"query": "what is rag", "top_k": 2},
        headers={
            "X-API-Version": "2026-04-01",
            "X-User-Id": "reader-1",
            "X-Roles": "reader",
            "X-Tenant-Id": "tenant-a",
        },
    )
    assert response.status_code == 410


def test_docs_forbidden_for_reader_role():
    response = client.post(
        "/docs",
        json={"documents": [{"document_id": "d1", "text": "hello world long enough for ingest"}]},
        headers={
            "X-API-Version": "2026-05-01",
            "X-User-Id": "reader-1",
            "X-Roles": "reader",
            "X-Tenant-Id": "tenant-a",
        },
    )
    assert response.status_code == 403


def test_docs_status_forbidden_cross_tenant():
    create = client.post(
        "/docs",
        json={"documents": [{"document_id": "d2", "text": "hello world long enough for ingest"}]},
        headers={
            "X-API-Version": "2026-05-01",
            "X-User-Id": "writer-1",
            "X-Roles": "writer",
            "X-Tenant-Id": "tenant-a",
            "Idempotency-Key": "cross-tenant-docs-1",
        },
    )
    assert create.status_code == 202
    job_id = create.json()["job_id"]

    check = client.get(
        f"/docs/{job_id}",
        headers={
            "X-API-Version": "2026-05-01",
            "X-User-Id": "reader-2",
            "X-Roles": "reader",
            "X-Tenant-Id": "tenant-b",
        },
    )
    assert check.status_code == 403
