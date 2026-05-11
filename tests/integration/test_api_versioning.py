from fastapi.testclient import TestClient

from shrag.app import app


client = TestClient(app)


def test_missing_version_header_rejected():
    response = client.get("/metrics", headers={"X-User-Id": "u1", "X-Roles": "reader"})
    assert response.status_code == 400


def test_unsupported_version_rejected():
    response = client.get(
        "/metrics",
        headers={"X-API-Version": "1999-01-01", "X-User-Id": "u1", "X-Roles": "reader"},
    )
    assert response.status_code == 426


def test_deprecated_version_rejected():
    response = client.get(
        "/metrics",
        headers={"X-API-Version": "2026-04-01", "X-User-Id": "u1", "X-Roles": "reader"},
    )
    assert response.status_code == 410
