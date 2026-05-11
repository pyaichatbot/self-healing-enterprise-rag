from __future__ import annotations


def partition_key(tenant_id: str, namespace: str) -> str:
    return f"{tenant_id}:{namespace}"
