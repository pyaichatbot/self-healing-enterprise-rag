from __future__ import annotations

from collections.abc import Sequence

from shrag.observe.models import RequestContext


def replay_window(records: Sequence[RequestContext], limit: int = 100) -> tuple[RequestContext, ...]:
    return tuple(records[-limit:])
