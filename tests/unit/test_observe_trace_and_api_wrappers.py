from shrag.api import routes, routes_feedback, routes_health, routes_ingest, routes_query
from shrag.observe.models import RequestContext
from shrag.observe.trace import trace_fields


def test_trace_fields_defaults_and_metadata_tenant():
    ctx = RequestContext(request_id="req-1", query="hello", metadata={"tenant_id": "tenant-a"})
    fields = trace_fields(ctx)

    assert fields["trace_id"] == "req-1"
    assert fields["tenant_id"] == "tenant-a"
    assert fields["user_id"] == "anonymous"


def test_route_wrapper_exports_bind_to_main_routes():
    assert routes_feedback.feedback is routes.feedback
    assert routes_health.healthz is routes.healthz
    assert routes_health.readyz is routes.readyz
    assert routes_health.metrics is routes.metrics
    assert routes_ingest.docs is routes.docs
    assert routes_ingest.docs_status is routes.docs_status
    assert routes_query.query is routes.query
