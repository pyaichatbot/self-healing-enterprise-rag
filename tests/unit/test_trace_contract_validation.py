from datetime import datetime

import pytest

from shrag.observe.hooks import DefaultObserver, StageEvent, TraceValidationError, parse_required_fields
from shrag.observe.models import RequestContext


def _ctx() -> RequestContext:
    return RequestContext(
        request_id="req-1",
        query="q",
        user_id="user-1",
        trace_id="trace-1",
        metadata={"tenant_id": "tenant-1"},
    )


def test_parse_required_fields_csv():
    fields = parse_required_fields("trace_id, request_id, stage")
    assert fields == ("trace_id", "request_id", "stage")


def test_trace_validation_warn_mode_logs_and_continues(caplog):
    observer = DefaultObserver(validation_mode="warn", required_fields=("trace_id", "stage", "status"))
    event = StageEvent(stage="", status="completed", timestamp=datetime.utcnow())

    observer.on_stage_event(_ctx(), event)

    assert "trace contract violation" in caplog.text


def test_trace_validation_block_mode_raises():
    observer = DefaultObserver(validation_mode="block", required_fields=("trace_id", "stage", "status"))
    event = StageEvent(stage="", status="completed", timestamp=datetime.utcnow())

    with pytest.raises(TraceValidationError):
        observer.on_stage_event(_ctx(), event)
