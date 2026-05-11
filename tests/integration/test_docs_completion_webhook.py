from fastapi.testclient import TestClient
from uuid import uuid4

from shrag.app import app
import shrag.api.routes as routes_module


client = TestClient(app)


def test_docs_completion_webhook_is_invoked(monkeypatch):
    calls: list[tuple[str | None, dict[str, object]]] = []

    def fake_send(callback_url, body):
        calls.append((callback_url, body))

    monkeypatch.setattr(routes_module, "_send_completion_webhook", fake_send)
    payload = {
        "documents": [{"document_id": "doc-webhook", "text": "hello webhook"}],
        "callback_url": "https://example.com/webhook",
    }
    headers = {
        "X-API-Version": "2026-05-01",
        "X-User-Id": "writer-1",
        "X-Tenant-Id": "tenant-a",
        "X-Roles": "writer",
        "Idempotency-Key": f"docs-webhook-{uuid4()}",
    }

    response = client.post("/docs", json=payload, headers=headers)

    assert response.status_code == 202
    assert len(calls) == 1
    callback_url, body = calls[0]
    assert callback_url == "https://example.com/webhook"
    assert body["tenant_id"] == "tenant-a"
    assert body["status"] == "completed"
