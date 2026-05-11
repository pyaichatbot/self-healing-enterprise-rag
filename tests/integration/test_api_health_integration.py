from fastapi.testclient import TestClient

from shrag.app import app


client = TestClient(app)


def test_health_and_ready_contract():
    health = client.get("/healthz")
    ready = client.get("/readyz")

    assert health.status_code == 200
    assert ready.status_code == 200

    h = health.json()
    r = ready.json()
    assert h["status"] == "ok"
    assert r["status"] == "ready"
    assert "checks" in r
