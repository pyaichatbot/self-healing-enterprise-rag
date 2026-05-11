from __future__ import annotations


def normalize_document(raw: dict[str, object]) -> dict[str, object]:
    return {
        "document_id": raw.get("id") or raw.get("document_id") or "unknown",
        "text": str(raw.get("text") or raw.get("content") or ""),
        "metadata": raw.get("metadata") or {},
    }
