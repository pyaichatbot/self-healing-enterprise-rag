from __future__ import annotations

from shrag.observe.models import RequestContext


def trace_fields(context: RequestContext) -> dict[str, str]:
    tenant_id = str(context.metadata.get("tenant_id", "unknown"))
    return {
        "trace_id": context.trace_id or context.request_id,
        "request_id": context.request_id,
        "tenant_id": tenant_id,
        "user_id": context.user_id or "anonymous",
        "query": context.query,
    }
