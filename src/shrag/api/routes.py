from __future__ import annotations

from datetime import UTC, datetime
import base64
from contextlib import contextmanager
from hashlib import sha256
import hmac
import hashlib
import json
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
import httpx
from pydantic import BaseModel, Field

from shrag.api.backpressure import InflightGuard, StageBulkhead
from shrag.api.idempotency import IdempotencyStore
from shrag.api.jobs import JobRegistry
from shrag.api.rate_limit import RateLimiter
from shrag.api.versioning import require_api_version
from shrag.eval.pipeline_eval import BaselineEvalHook, EvalResult, merge_eval_results
from shrag.eval.scale_gate import ScaleGate
from shrag.generate.pipeline import BaselineGenerateStage
from shrag.generate.stream import stream_text
from shrag.grade.pipeline import BaselineGradeStage
from shrag.heal.pipeline import BaselineHealStage
from shrag.ingest.pipeline import Attachment, BaselineIngestStage, IngestDocument
from shrag.observe.hooks import DefaultObserver, StageEvent
from shrag.observe.ha import evaluate_ha_readiness
from shrag.observe.models import RequestContext, RetrievedChunk, ScoreArtifact
from shrag.reflect.pipeline import BaselineReflectStage
from shrag.retrieve.pipeline import BaselineRetrievalStage
from shrag.security.guardrails import DefaultOutputGuardrail
from shrag.security.authn import parse_bearer_token
from shrag.security.acl_filter import filter_chunks_by_acl
from shrag.security.policy import DefaultChunkPolicy, DefaultQueryPolicy
from shrag.settings import settings

router = APIRouter()
_rate_limiter = RateLimiter(
    settings.rate_limit_per_minute,
    settings.state_db_path,
    backend=settings.rate_limit_backend,
    redis_url=settings.redis_url,
)
_inflight_guard = InflightGuard(settings.max_inflight_requests)
_retrieve_bulkhead = StageBulkhead("retrieve", settings.max_retrieve_inflight)
_grade_bulkhead = StageBulkhead("grade", settings.max_grade_inflight)
_generate_bulkhead = StageBulkhead("generate", settings.max_generate_inflight)
_reflect_bulkhead = StageBulkhead("reflect", settings.max_reflect_inflight)
_heal_bulkhead = StageBulkhead("heal", settings.max_heal_inflight)
_ingest_bulkhead = StageBulkhead("ingest", settings.max_ingest_inflight)
_job_registry = JobRegistry(settings.state_db_path)
_idempotency = IdempotencyStore(settings.state_db_path)

_observer = DefaultObserver()
_ingest_stage = BaselineIngestStage()
_retrieval_stage = BaselineRetrievalStage()
_grade_stage = BaselineGradeStage()
_generate_stage = BaselineGenerateStage()
_reflect_stage = BaselineReflectStage()
_heal_stage = BaselineHealStage()
_eval_hook = BaselineEvalHook()
_query_policy = DefaultQueryPolicy()
_chunk_policy = DefaultChunkPolicy()
_output_guardrail = DefaultOutputGuardrail()
_scale_gate = ScaleGate()


class AuthContext(BaseModel):
    user_id: str
    tenant_id: str
    roles: tuple[str, ...]


class BaseEnvelope(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class HealthResponse(BaseEnvelope):
    status: str


class ReadyResponse(BaseEnvelope):
    status: str
    checks: dict[str, str]


class QueryRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)


class Claim(BaseModel):
    text: str
    supported: bool


class QueryResponse(BaseEnvelope):
    answer: str
    confidence: float = Field(ge=0.0, le=1.0)
    abstained: bool
    claims: list[Claim]
    citations: list[str]


class DocsItem(BaseModel):
    document_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    attachments: list[dict[str, str]] = Field(default_factory=list)


class DocsRequest(BaseModel):
    documents: list[str | DocsItem] = Field(min_length=1)
    callback_url: str | None = None


class DocsResponse(BaseEnvelope):
    job_id: str
    accepted: bool
    status: str


class DocsStatusResponse(BaseEnvelope):
    job_id: str
    status: str
    kind: str


class FeedbackRequest(BaseModel):
    query_id: str = Field(min_length=1)
    rating: int = Field(ge=1, le=5)
    notes: str | None = None


class FeedbackResponse(BaseEnvelope):
    accepted: bool


class MetricsResponse(BaseEnvelope):
    counters: dict[str, int]


def _safe_hmac_signature(payload: bytes) -> str | None:
    secret = settings.jwt_secret.strip()
    if not secret:
        return None
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _send_completion_webhook(callback_url: str | None, body: dict[str, Any]) -> None:
    if not callback_url:
        return
    payload = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    signature = _safe_hmac_signature(payload)
    if signature:
        headers["X-SHRAG-Signature"] = signature
    try:
        with httpx.Client(timeout=settings.completion_webhook_timeout_seconds) as client:
            client.post(callback_url, json=body, headers=headers)
    except Exception:
        # Webhook is optional best-effort signal and must not fail ingest completion path.
        return


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _enforce_capacity(request: Request) -> None:
    if not _inflight_guard.try_enter():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Backpressure active")
    request.state.entered_inflight = True


def _finalize_capacity(request: Request) -> None:
    if getattr(request.state, "entered_inflight", False):
        _inflight_guard.exit()


def _enforce_rate_limit(request: Request) -> None:
    if not _rate_limiter.allow(_client_key(request)):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")


def _authorize(auth: AuthContext, required_roles: tuple[str, ...]) -> None:
    if not any(role in auth.roles for role in required_roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")


def _get_auth_context(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    x_roles: str | None = Header(default=None, alias="X-Roles"),
) -> AuthContext:
    token_identity = parse_bearer_token(
        authorization,
        secret=settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
        default_tenant_id=settings.default_tenant_id,
        jwks_url=settings.jwks_url,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
    )
    if token_identity is not None:
        return AuthContext(
            user_id=token_identity.user_id,
            tenant_id=token_identity.tenant_id,
            roles=token_identity.roles,
        )

    tenant = x_tenant_id or settings.default_tenant_id
    if settings.auth_required and not x_user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-User-Id")
    user = x_user_id or "anonymous"
    roles = tuple(sorted({r.strip() for r in (x_roles or "reader").split(",") if r.strip()}))
    return AuthContext(user_id=user, tenant_id=tenant, roles=roles)


def _build_context(payload: QueryRequest, auth: AuthContext, trace_id: str | None = None) -> RequestContext:
    return RequestContext(
        request_id=str(uuid4()),
        query=payload.query,
        user_id=auth.user_id,
        trace_id=trace_id or str(uuid4()),
        metadata={"tenant_id": auth.tenant_id, "roles": auth.roles},
    )


def _derive_claims(answer: str) -> list[Claim]:
    segments = [segment.strip() for segment in answer.split(".") if segment.strip()]
    claims = [Claim(text=segment[:180], supported=True) for segment in segments[:3]]
    return claims or ([Claim(text=answer[:140], supported=True)] if answer else [])


def _derive_confidence(signals: tuple[ScoreArtifact, ...], abstained: bool) -> float:
    if abstained:
        return 0.0
    if not signals:
        return 0.5
    values = [max(0.0, min(1.0, s.value)) for s in signals]
    return round(sum(values) / len(values), 3)


def _notify(context: RequestContext, stage: str, status_value: str, payload: dict[str, Any] | None = None) -> None:
    _observer.on_stage_event(context, StageEvent(stage=stage, status=status_value, payload=payload or {}))


def _oracle_context_text(chunks: tuple[RetrievedChunk, ...], max_chars: int) -> str:
    if not chunks:
        return "No evidence chunks were retrieved."
    parts: list[str] = []
    for chunk in chunks:
        snippet = " ".join(chunk.text.split())
        parts.append(f"[{chunk.chunk_id}] {snippet}")
        if sum(len(p) for p in parts) >= max_chars:
            break
    merged = " | ".join(parts)
    return merged[:max_chars]


def _lane_label_eval(result: EvalResult, lane: str) -> EvalResult:
    lane_scores = tuple(
        ScoreArtifact(
            name=f"{lane}:{score.name}",
            value=score.value,
            reason=score.reason,
            passed=score.passed,
            metadata={**dict(score.metadata), "eval_lane": lane},
        )
        for score in result.scores
    )
    lane_notes = tuple(f"{lane}:{note}" for note in result.notes)
    return EvalResult(scores=lane_scores, notes=lane_notes)


def _evaluate_with_oracle_context(
    context: RequestContext,
    generation: Any,
    selected_chunks: tuple[RetrievedChunk, ...],
) -> EvalResult:
    mode = settings.eval_oracle_context_mode if settings.eval_oracle_context_enabled else "off"
    results: list[EvalResult] = []
    if mode in ("off", "generation", "both"):
        results.append(_lane_label_eval(_eval_hook.evaluate(context, generation), "generation"))
    if mode in ("retrieval", "both"):
        oracle_generation = generation.__class__(
            response_text=_oracle_context_text(selected_chunks, settings.eval_oracle_context_max_chars),
            citations=tuple(chunk.source_id for chunk in selected_chunks[:5]),
            scores=(),
            metadata={"oracle_context": True},
        )
        results.append(_lane_label_eval(_eval_hook.evaluate(context, oracle_generation), "oracle_retrieval"))
    if not results:
        results.append(_lane_label_eval(_eval_hook.evaluate(context, generation), "generation"))
    return merge_eval_results(results)


@contextmanager
def _stage_or_503(stage: StageBulkhead) -> Iterator[None]:
    try:
        with stage.enter():
            yield
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(status="ok", tenant_id=settings.default_tenant_id)


@router.get("/readyz", response_model=ReadyResponse)
def readyz() -> ReadyResponse:
    ha = evaluate_ha_readiness(
        region=settings.region,
        mode=settings.ha_mode,
        primary_region=settings.primary_region,
        primary_region_healthy=settings.primary_region_healthy,
        replication_lag_seconds=settings.replication_lag_seconds,
        max_replication_lag_seconds=settings.max_replication_lag_seconds,
    )
    checks = {
        "api": "ok",
        "config": "ok",
        "ha_role": ha.role,
        "ha_reason": ha.reason,
        "ha_serving_region": ha.serving_region,
    }
    return ReadyResponse(
        status="ready" if ha.ready else "degraded",
        checks=checks,
        tenant_id=settings.default_tenant_id,
    )


@router.get("/metrics", response_model=MetricsResponse)
def metrics(auth: AuthContext = Depends(_get_auth_context), _: str = Depends(require_api_version)) -> MetricsResponse:
    _authorize(auth, ("reader", "writer", "admin"))
    return MetricsResponse(
        counters={
            "inflight": _inflight_guard.inflight,
            "retrieve_inflight": _retrieve_bulkhead.inflight,
            "grade_inflight": _grade_bulkhead.inflight,
            "generate_inflight": _generate_bulkhead.inflight,
            "reflect_inflight": _reflect_bulkhead.inflight,
            "heal_inflight": _heal_bulkhead.inflight,
            "ingest_inflight": _ingest_bulkhead.inflight,
        },
        tenant_id=auth.tenant_id,
    )


@router.post("/query", response_model=QueryResponse)
def query(
    payload: QueryRequest,
    request: Request,
    auth: AuthContext = Depends(_get_auth_context),
    _: str = Depends(require_api_version),
    x_trace_id: str | None = Header(default=None, alias="X-Trace-Id"),
) -> QueryResponse:
    _authorize(auth, ("reader", "writer", "admin"))
    _enforce_capacity(request)
    try:
        _enforce_rate_limit(request)
        context = _build_context(payload, auth, trace_id=x_trace_id)

        gate = _scale_gate.allow(context)
        if not gate.allowed:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Scale gate: {gate.reason}")

        query_decision = _query_policy.check_query(context)
        if not query_decision.allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=";".join(query_decision.reasons))

        _notify(context, "retrieve", "started")
        with _stage_or_503(_retrieve_bulkhead):
            retrieval = _retrieval_stage.retrieve(context, top_k=payload.top_k)
        acl_chunks = filter_chunks_by_acl(retrieval.chunks, {auth.tenant_id, "public"})
        _notify(context, "retrieve", "completed", {"chunks": len(acl_chunks)})

        chunk_decision = _chunk_policy.check_chunks(context, acl_chunks)
        if not chunk_decision.allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=";".join(chunk_decision.reasons))

        _notify(context, "grade", "started")
        with _stage_or_503(_grade_bulkhead):
            graded = _grade_stage.grade(context, acl_chunks)
        _notify(context, "grade", "completed", {"selected": len(graded.selected_chunks)})

        _notify(context, "generate", "started")
        with _stage_or_503(_generate_bulkhead):
            generation = _generate_stage.generate(context, graded.selected_chunks)
        _notify(context, "generate", "completed")

        merged_eval = _evaluate_with_oracle_context(context, generation, tuple(graded.selected_chunks))

        with _stage_or_503(_reflect_bulkhead):
            reflection = _reflect_stage.reflect(context, generation, signals=merged_eval.scores)
        if reflection.should_heal:
            with _stage_or_503(_heal_bulkhead):
                healed = _heal_stage.heal(context, generation, reflection)
            generation = healed.generation

        guardrail = _output_guardrail.enforce(context, generation)
        final_generation = guardrail.generation

        abstained = len(graded.selected_chunks) == 0 or "abstain" in reflection.suggested_actions
        confidence = _derive_confidence(tuple(merged_eval.scores) + tuple(generation.scores), abstained)
        claims = _derive_claims(final_generation.response_text)

        return QueryResponse(
            request_id=context.request_id,
            tenant_id=auth.tenant_id,
            answer=final_generation.response_text,
            confidence=confidence,
            abstained=abstained,
            claims=claims,
            citations=list(final_generation.citations),
        )
    finally:
        _finalize_capacity(request)


@router.post("/query/stream")
def query_stream(
    payload: QueryRequest,
    request: Request,
    auth: AuthContext = Depends(_get_auth_context),
    _: str = Depends(require_api_version),
    x_trace_id: str | None = Header(default=None, alias="X-Trace-Id"),
) -> StreamingResponse:
    response = query(payload=payload, request=request, auth=auth, _=_, x_trace_id=x_trace_id)

    def _sse_events() -> Iterator[str]:
        for chunk in stream_text(response.answer):
            yield f"event: token\ndata: {chunk}\n\n"
        yield (
            "event: final\n"
            f"data: {json.dumps({'request_id': response.request_id, 'confidence': response.confidence, 'abstained': response.abstained})}\n\n"
        )

    return StreamingResponse(_sse_events(), media_type="text/event-stream")


@router.post("/docs", response_model=DocsResponse, status_code=status.HTTP_202_ACCEPTED)
def docs(
    payload: DocsRequest,
    request: Request,
    auth: AuthContext = Depends(_get_auth_context),
    _: str = Depends(require_api_version),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_trace_id: str | None = Header(default=None, alias="X-Trace-Id"),
) -> DocsResponse:
    _authorize(auth, ("writer", "admin"))
    _enforce_capacity(request)
    try:
        _enforce_rate_limit(request)
        request_id = str(uuid4())
        context = RequestContext(
            request_id=request_id,
            query="ingest_docs",
            user_id=auth.user_id,
            trace_id=x_trace_id or str(uuid4()),
            metadata={"tenant_id": auth.tenant_id, "roles": auth.roles},
        )
        normalized_docs: list[DocsItem] = []
        for item in payload.documents:
            if isinstance(item, str):
                normalized_docs.append(DocsItem(document_id=item, text=item))
            else:
                normalized_docs.append(item)

        digest = sha256()
        digest.update(auth.tenant_id.encode("utf-8"))
        for doc in normalized_docs:
            digest.update(doc.document_id.encode("utf-8"))
            digest.update(doc.text.encode("utf-8"))
        deterministic_digest = digest.hexdigest()
        effective_key = idempotency_key or deterministic_digest
        composite_key = f"{auth.tenant_id}:{effective_key}"
        previously_seen = _idempotency.seen(composite_key)
        _idempotency.mark(composite_key)

        ingest_docs = tuple(IngestDocument(document_id=d.document_id, text=d.text) for d in normalized_docs)
        ingest_docs = tuple(
            IngestDocument(
                document_id=d.document_id,
                text=d.text,
                attachments=tuple(
                    Attachment(
                        name=item.get("name", f"{d.document_id}-attachment"),
                        content=base64.b64decode(item.get("content_b64", "").encode("utf-8")) if item.get("content_b64") else b"",
                        content_type=item.get("content_type"),
                    )
                    for item in d.attachments
                    if item.get("content_b64")
                ),
            )
            for d in normalized_docs
        )

        job, created = _job_registry.create_deterministic(
            kind="ingest_docs",
            idempotency_key=composite_key,
        )
        if created:
            _notify(context, "ingest", "started", {"job_id": job.id})
            with _stage_or_503(_ingest_bulkhead):
                _ingest_stage.ingest(context, ingest_docs)
            _job_registry.update_status(job.id, "completed")
            job = _job_registry.get(job.id) or job
            _notify(context, "ingest", "completed", {"job_id": job.id})
            _send_completion_webhook(
                payload.callback_url,
                {"tenant_id": auth.tenant_id, "job_id": job.id, "status": job.status, "kind": job.kind},
            )

        return DocsResponse(
            request_id=request_id,
            tenant_id=auth.tenant_id,
            job_id=job.id,
            accepted=True,
            status="duplicate" if previously_seen and not created else job.status,
        )
    finally:
        _finalize_capacity(request)


@router.get("/docs/{job_id}", response_model=DocsStatusResponse)
def docs_status(
    job_id: str,
    auth: AuthContext = Depends(_get_auth_context),
    _: str = Depends(require_api_version),
) -> DocsStatusResponse:
    _authorize(auth, ("reader", "writer", "admin"))
    job = _job_registry.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if not (job.idempotency_key or "").startswith(f"{auth.tenant_id}:"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Job is outside tenant scope")
    return DocsStatusResponse(tenant_id=auth.tenant_id, job_id=job.id, status=job.status, kind=job.kind)


@router.post("/feedback", response_model=FeedbackResponse, status_code=status.HTTP_202_ACCEPTED)
def feedback(
    payload: FeedbackRequest,
    request: Request,
    auth: AuthContext = Depends(_get_auth_context),
    _: str = Depends(require_api_version),
) -> FeedbackResponse:
    _authorize(auth, ("reader", "writer", "admin"))
    _enforce_capacity(request)
    try:
        _enforce_rate_limit(request)
        return FeedbackResponse(accepted=True, tenant_id=auth.tenant_id)
    finally:
        _finalize_capacity(request)
