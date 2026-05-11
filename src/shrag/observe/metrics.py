"""Prometheus metrics — counters, histograms, gauges.

Metrics exposed:
  shrag_requests_total{stage, status}        — request counts per pipeline stage
  shrag_request_duration_seconds{stage}      — per-stage latency histogram
  shrag_repair_total{strategy, succeeded}    — repair loop outcomes
  shrag_retrieval_chunks{quantile}           — chunk count distribution
  shrag_token_cost_total{backend}            — LLM token usage (est. cost proxy)
  shrag_quality_score{metric}               — faithfulness/relevance gauge
  shrag_ingest_jobs_total{status}           — worker job outcomes
  shrag_embed_cache_hits_total              — embedding L1 cache hit rate

Enterprise features:
  - Registry-based (no global state collision in multi-tenant deploys)
  - Graceful degradation: all calls are no-ops when prometheus_client absent
  - /metrics endpoint compatible (ASGI middleware friendly)
  - Thread-safe counters and histograms
"""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Iterator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy prometheus_client import — degrade gracefully
# ---------------------------------------------------------------------------

_prom: Any = None
_registry: Any = None
_metrics: dict[str, Any] = {}


def _get_prom() -> Any:
    global _prom  # noqa: PLW0603
    if _prom is not None:
        return _prom
    try:
        import prometheus_client as _p
        _prom = _p
    except ImportError:
        _prom = False
    return _prom


def _get_registry() -> Any:
    global _registry  # noqa: PLW0603
    if _registry is not None:
        return _registry
    p = _get_prom()
    if not p:
        return None
    _registry = p.CollectorRegistry()
    return _registry


# ---------------------------------------------------------------------------
# Metric factories — idempotent (re-use existing metrics by name)
# ---------------------------------------------------------------------------

def _counter(name: str, documentation: str, labelnames: list[str] | None = None) -> Any:
    if name in _metrics:
        return _metrics[name]
    p = _get_prom()
    if not p:
        return None
    reg = _get_registry()
    c = p.Counter(name, documentation, labelnames=labelnames or [], registry=reg)
    _metrics[name] = c
    return c


def _histogram(name: str, documentation: str, labelnames: list[str] | None = None, buckets: tuple[float, ...] | None = None) -> Any:
    if name in _metrics:
        return _metrics[name]
    p = _get_prom()
    if not p:
        return None
    reg = _get_registry()
    kwargs: dict[str, Any] = {"registry": reg, "labelnames": labelnames or []}
    if buckets:
        kwargs["buckets"] = buckets
    h = p.Histogram(name, documentation, **kwargs)
    _metrics[name] = h
    return h


def _gauge(name: str, documentation: str, labelnames: list[str] | None = None) -> Any:
    if name in _metrics:
        return _metrics[name]
    p = _get_prom()
    if not p:
        return None
    reg = _get_registry()
    g = p.Gauge(name, documentation, labelnames=labelnames or [], registry=reg)
    _metrics[name] = g
    return g


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def inc_request(stage: str, status: str = "ok", amount: int = 1) -> None:
    """Increment request counter for a pipeline stage."""
    c = _counter("shrag_requests_total", "Total pipeline requests", ["stage", "status"])
    if c:
        try:
            c.labels(stage=stage, status=status).inc(amount)
        except Exception:  # noqa: BLE001
            pass


def observe_latency(stage: str, seconds: float) -> None:
    """Record latency observation for a pipeline stage."""
    h = _histogram(
        "shrag_request_duration_seconds",
        "Request duration per pipeline stage",
        ["stage"],
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    )
    if h:
        try:
            h.labels(stage=stage).observe(seconds)
        except Exception:  # noqa: BLE001
            pass


def inc_repair(strategy: str, succeeded: bool) -> None:
    """Increment repair counter."""
    c = _counter("shrag_repair_total", "Repair loop outcomes", ["strategy", "succeeded"])
    if c:
        try:
            c.labels(strategy=strategy, succeeded=str(succeeded).lower()).inc()
        except Exception:  # noqa: BLE001
            pass


def observe_chunk_count(count: int) -> None:
    """Record retrieved chunk count."""
    h = _histogram(
        "shrag_retrieval_chunks",
        "Retrieved chunk count distribution",
        buckets=(1, 3, 5, 10, 20, 50),
    )
    if h:
        try:
            h.observe(count)
        except Exception:  # noqa: BLE001
            pass


def inc_token_cost(backend: str, tokens: int) -> None:
    """Track token usage as cost proxy."""
    c = _counter("shrag_token_cost_total", "LLM token usage by backend", ["backend"])
    if c:
        try:
            c.labels(backend=backend).inc(tokens)
        except Exception:  # noqa: BLE001
            pass


def set_quality_score(metric: str, value: float) -> None:
    """Set a quality gauge (faithfulness, relevance, etc.)."""
    g = _gauge("shrag_quality_score", "Pipeline quality metric scores", ["metric"])
    if g:
        try:
            g.labels(metric=metric).set(value)
        except Exception:  # noqa: BLE001
            pass


def inc_ingest_job(status: str) -> None:
    """Track ingest worker job outcomes."""
    c = _counter("shrag_ingest_jobs_total", "Ingest worker job outcomes", ["status"])
    if c:
        try:
            c.labels(status=status).inc()
        except Exception:  # noqa: BLE001
            pass


def inc_embed_cache_hit(hit: bool = True) -> None:
    """Track embedding cache hit rate."""
    c = _counter("shrag_embed_cache_hits_total", "Embedding cache hits", ["result"])
    if c:
        try:
            c.labels(result="hit" if hit else "miss").inc()
        except Exception:  # noqa: BLE001
            pass


@contextmanager
def timed(stage: str) -> Iterator[None]:
    """Context manager: record stage latency + increment request counter."""
    start = time.perf_counter()
    status = "ok"
    try:
        yield
    except Exception:
        status = "error"
        raise
    finally:
        elapsed = time.perf_counter() - start
        observe_latency(stage, elapsed)
        inc_request(stage, status)


def generate_latest() -> bytes:
    """Return Prometheus text format for /metrics endpoint."""
    p = _get_prom()
    reg = _get_registry()
    if p and reg:
        try:
            return p.generate_latest(reg)
        except Exception:  # noqa: BLE001
            pass
    return b""


def metric_counter(name: str, value: int = 1) -> dict[str, int]:
    """Legacy shim — increments a named counter and returns it."""
    inc_request(name, "ok", value)
    return {name: value}
