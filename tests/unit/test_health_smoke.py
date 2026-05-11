"""Smoke tests for health endpoint contract."""

from fastapi.testclient import TestClient

from shrag.app import app


def test_health_smoke_contract():
    client = TestClient(app)
    response = client.get("/healthz", headers={"X-User-Id": "smoke-user", "X-Tenant-Id": "tenant-smoke"})
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("status") == "ok"
