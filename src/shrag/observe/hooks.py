from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import logging
from typing import Any, Mapping, Protocol

from shrag.observe.models import RequestContext, TraceRecord
from shrag.settings import settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class StageEvent:
    stage: str
    status: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    payload: Mapping[str, Any] = field(default_factory=dict)


class Observer(Protocol):
    def on_stage_event(self, context: RequestContext, event: StageEvent) -> None: ...


class TraceValidationError(ValueError):
    pass


def parse_required_fields(csv_fields: str) -> tuple[str, ...]:
    fields = tuple(item.strip() for item in csv_fields.split(",") if item.strip())
    return fields or ("trace_id", "request_id", "tenant_id", "user_id", "stage", "status", "timestamp")


def validate_trace_record(record: TraceRecord, required_fields: tuple[str, ...]) -> tuple[str, ...]:
    missing: list[str] = []
    for field_name in required_fields:
        value = getattr(record, field_name, None)
        if value is None:
            missing.append(field_name)
            continue
        if isinstance(value, str) and not value.strip():
            missing.append(field_name)
    return tuple(missing)


class DefaultObserver:
    def __init__(
        self,
        validation_mode: str | None = None,
        required_fields: tuple[str, ...] | None = None,
    ) -> None:
        self.validation_mode = validation_mode or settings.trace_validation_mode
        self.required_fields = required_fields or parse_required_fields(settings.trace_required_fields_csv)

    def _trace_record_from(self, context: RequestContext, event: StageEvent) -> TraceRecord:
        tenant_id = str(context.metadata.get("tenant_id", "unknown"))
        trace_id = context.trace_id or context.request_id
        user_id = context.user_id or "anonymous"
        return TraceRecord(
            trace_id=trace_id,
            request_id=context.request_id,
            tenant_id=tenant_id,
            user_id=user_id,
            stage=event.stage,
            status=event.status,
            timestamp=event.timestamp,
            payload=event.payload,
        )

    def on_stage_event(self, context: RequestContext, event: StageEvent) -> None:
        record = self._trace_record_from(context, event)
        missing = validate_trace_record(record, self.required_fields)
        if missing:
            message = f"trace contract violation: missing required fields {missing}"
            if self.validation_mode == "block":
                raise TraceValidationError(message)
            logger.warning(message)
        return None


NoOpObserver = DefaultObserver
