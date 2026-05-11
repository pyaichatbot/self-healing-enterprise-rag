import base64

from fastapi.testclient import TestClient

from shrag.app import app


client = TestClient(app)


def test_docs_ingest_supports_attachment_lineage():
    attachment_text = b"attachment content about rollback procedures and incident response"
    payload = {
        "documents": [
            {
                "document_id": "doc-attach-1",
                "text": "parent document text for enterprise policy",
                "attachments": [
                    {
                        "name": "runbook.txt",
                        "content_type": "text/plain",
                        "content_b64": base64.b64encode(attachment_text).decode("utf-8"),
                    }
                ],
            }
        ]
    }
    headers = {
        "X-API-Version": "2026-05-01",
        "X-User-Id": "writer-1",
        "X-Tenant-Id": "tenant-a",
        "X-Roles": "writer",
    }
    response = client.post("/v1/docs", json=payload, headers=headers)
    assert response.status_code == 202
