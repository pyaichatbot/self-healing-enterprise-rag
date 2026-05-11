from fastapi.testclient import TestClient

from shrag.api import routes
from shrag.app import app
from shrag.eval.pipeline_eval import EvalResult
from shrag.observe.models import GenerationResult, ReflectionOutcome, RequestContext
from shrag.retrieve.pipeline import RetrieveResult
from shrag.grade.pipeline import GradeResult
from shrag.security.policy import SecurityDecision
from shrag.security.guardrails import GuardrailResult
from shrag.eval.scale_gate import ScaleGateDecision


class _CaptureObserver:
    def __init__(self) -> None:
        self.events: list[tuple[str | None, str, str]] = []

    def on_stage_event(self, context: RequestContext, event) -> None:
        self.events.append((context.trace_id, event.stage, event.status))


class _AllowScale:
    def allow(self, context: RequestContext) -> ScaleGateDecision:
        _ = context
        return ScaleGateDecision(allowed=True, reason="ok")


class _AllowQueryPolicy:
    def check_query(self, context: RequestContext) -> SecurityDecision:
        _ = context
        return SecurityDecision(allowed=True)


class _AllowChunkPolicy:
    def check_chunks(self, context: RequestContext, chunks):
        _ = (context, chunks)
        return SecurityDecision(allowed=True)


class _RetrieveNone:
    def retrieve(self, context: RequestContext, top_k: int = 5) -> RetrieveResult:
        _ = (context, top_k)
        return RetrieveResult(chunks=())


class _GradeNone:
    def grade(self, context: RequestContext, chunks) -> GradeResult:
        _ = (context, chunks)
        return GradeResult(selected_chunks=(), chunk_scores=())


class _GenerateFixed:
    def generate(self, context: RequestContext, chunks) -> GenerationResult:
        _ = (context, chunks)
        return GenerationResult(response_text="answer")


class _EvalFixed:
    def evaluate(self, context: RequestContext, generation: GenerationResult) -> EvalResult:
        _ = (context, generation)
        return EvalResult()


class _ReflectNoHeal:
    def reflect(self, context: RequestContext, generation: GenerationResult, signals=()):
        _ = (context, generation, signals)
        return ReflectionOutcome(should_heal=False)


class _NoopGuardrail:
    def enforce(self, context: RequestContext, generation: GenerationResult) -> GuardrailResult:
        _ = context
        return GuardrailResult(generation=generation)


def test_query_emits_trace_events_with_request_trace_id(monkeypatch):
    observer = _CaptureObserver()
    monkeypatch.setattr(routes, "_observer", observer)
    monkeypatch.setattr(routes, "_scale_gate", _AllowScale())
    monkeypatch.setattr(routes, "_query_policy", _AllowQueryPolicy())
    monkeypatch.setattr(routes, "_chunk_policy", _AllowChunkPolicy())
    monkeypatch.setattr(routes, "_retrieval_stage", _RetrieveNone())
    monkeypatch.setattr(routes, "_grade_stage", _GradeNone())
    monkeypatch.setattr(routes, "_generate_stage", _GenerateFixed())
    monkeypatch.setattr(routes, "_eval_hook", _EvalFixed())
    monkeypatch.setattr(routes, "_reflect_stage", _ReflectNoHeal())
    monkeypatch.setattr(routes, "_output_guardrail", _NoopGuardrail())
    monkeypatch.setattr(routes.settings, "eval_oracle_context_enabled", True)
    monkeypatch.setattr(routes.settings, "eval_oracle_context_mode", "both")

    client = TestClient(app)
    headers = {
        "X-API-Version": "2026-05-01",
        "X-User-Id": "reader-1",
        "X-Tenant-Id": "tenant-a",
        "X-Roles": "reader",
        "X-Trace-Id": "trace-from-header",
    }
    response = client.post("/query", json={"query": "test", "top_k": 3}, headers=headers)

    assert response.status_code == 200
    assert observer.events
    assert all(trace_id == "trace-from-header" for trace_id, _, _ in observer.events)
    stage_names = {(stage, status) for _, stage, status in observer.events}
    assert ("retrieve", "started") in stage_names
    assert ("generate", "completed") in stage_names
