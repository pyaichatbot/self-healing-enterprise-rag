import jwt
from fastapi.testclient import TestClient

from shrag.app import app


client = TestClient(app)


def _jwt_headers():
    token = jwt.encode(
        {"sub": "alice", "tenant_id": "tenant-jwt", "roles": ["writer", "reader"]},
        "dev-secret-change-me",
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}", "X-API-Version": "2026-05-01"}


def test_v1_health_endpoint_available():
    response = client.get("/v1/healthz")
    assert response.status_code == 200


def test_v1_docs_endpoint_with_jwt_auth():
    payload = {"documents": [{"document_id": "jwt-doc-1", "text": "enterprise runbook content for jwt tenant"}]}
    response = client.post("/v1/docs", json=payload, headers=_jwt_headers())
    assert response.status_code == 202
    body = response.json()
    assert body["tenant_id"] == "tenant-jwt"
    status = client.get(f"/v1/docs/{body['job_id']}", headers=_jwt_headers())
    assert status.status_code == 200
    assert status.json()["tenant_id"] == "tenant-jwt"
