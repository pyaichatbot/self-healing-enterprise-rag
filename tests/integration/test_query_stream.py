from fastapi.testclient import TestClient

from shrag.app import app


client = TestClient(app)


def test_query_stream_returns_sse_events():
    headers = {
        "X-API-Version": "2026-05-01",
        "X-User-Id": "reader-1",
        "X-Tenant-Id": "tenant-a",
        "X-Roles": "reader",
    }
    payload = {"query": "What is self healing rag?", "top_k": 3}
    response = client.post("/query/stream", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: token" in response.text
    assert "event: final" in response.text
