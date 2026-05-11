from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class TraceStore:
    """In-memory trace store for local pipeline runs."""

    records: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def append(self, trace_id: str, event: dict[str, Any]) -> None:
        self.records.setdefault(trace_id, []).append(event)

    def get(self, trace_id: str) -> tuple[dict[str, Any], ...]:
        return tuple(self.records.get(trace_id, []))
