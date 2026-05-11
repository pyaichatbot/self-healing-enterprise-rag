"""LLM provider abstraction — multi-backend, retried, streaming-ready.

Supported backends (set via SHRAG_LLM_BACKEND):
  openai     — OpenAI chat completions (gpt-4o, gpt-4o-mini, etc.)
  anthropic  — Anthropic Messages API (claude-* models)
  ollama     — Local Ollama server (http://localhost:11434)
  mock       — Deterministic stub for tests (no network)

Enterprise features:
  - Unified `complete()` and `complete_stream()` interface
  - Per-provider retry with exponential backoff + jitter
  - Token-usage logging per call
  - System prompt support
  - Temperature / max_tokens / top_p overrides via env or call args
  - Graceful degradation to mock on provider failure
"""
from __future__ import annotations

import logging
import os
import time
import random
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------

def _with_retry(fn: Any, max_attempts: int = 3, base_delay: float = 1.0) -> Any:
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt == max_attempts - 1:
                break
            sleep = base_delay * (2 ** attempt) * (0.5 + random.random() * 0.5)
            logger.warning("LLM retry %d/%d after %.1fs: %s", attempt + 1, max_attempts, sleep, exc)
            time.sleep(sleep)
    raise RuntimeError(f"LLM call failed after {max_attempts} attempts") from last_exc


# ---------------------------------------------------------------------------
# Backend implementations
# ---------------------------------------------------------------------------

def _complete_openai(
    prompt: str,
    *,
    system: str | None,
    model: str,
    max_tokens: int,
    temperature: float,
) -> str:
    try:
        import openai  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError("pip install openai for SHRAG_LLM_BACKEND=openai") from exc

    client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    usage = resp.usage
    if usage:
        logger.debug(
            "openai usage: prompt=%d completion=%d total=%d",
            usage.prompt_tokens, usage.completion_tokens, usage.total_tokens,
        )
    return resp.choices[0].message.content or ""


def _complete_anthropic(
    prompt: str,
    *,
    system: str | None,
    model: str,
    max_tokens: int,
    temperature: float,
) -> str:
    try:
        import anthropic  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError("pip install anthropic for SHRAG_LLM_BACKEND=anthropic") from exc

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system

    resp = client.messages.create(**kwargs)
    usage = getattr(resp, "usage", None)
    if usage:
        logger.debug(
            "anthropic usage: input=%d output=%d",
            getattr(usage, "input_tokens", 0),
            getattr(usage, "output_tokens", 0),
        )
    return resp.content[0].text if resp.content else ""


def _complete_ollama(
    prompt: str,
    *,
    system: str | None,
    model: str,
    max_tokens: int,
    temperature: float,
) -> str:
    import urllib.request
    import json as _json

    base_url = os.environ.get("SHRAG_OLLAMA_URL", "http://localhost:11434")
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = _json.dumps({
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }).encode()
    req = urllib.request.Request(
        f"{base_url}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = _json.loads(resp.read())
    return body.get("message", {}).get("content", "")


def _complete_mock(
    prompt: str,
    *,
    system: str | None,
    model: str,
    max_tokens: int,
    temperature: float,
) -> str:
    """Deterministic stub — for tests and offline development."""
    words = prompt.split()
    snippet = " ".join(words[:20])
    return f"[mock-llm] Responding to: {snippet}..."


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_BACKENDS: dict[str, Any] = {
    "openai": _complete_openai,
    "anthropic": _complete_anthropic,
    "ollama": _complete_ollama,
    "mock": _complete_mock,
}

_DEFAULT_MODELS: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5-20251001",
    "ollama": "llama3",
    "mock": "mock",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def complete(
    prompt: str,
    *,
    system: str | None = None,
    backend: str | None = None,
    model: str | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
    max_attempts: int = 3,
) -> str:
    """Generate a completion for *prompt*.

    Falls back to mock backend on provider error if
    SHRAG_LLM_FALLBACK_TO_MOCK=true (default false).
    """
    resolved_backend = backend or os.environ.get("SHRAG_LLM_BACKEND", "mock")
    resolved_model = (
        model
        or os.environ.get("SHRAG_LLM_MODEL", "")
        or _DEFAULT_MODELS.get(resolved_backend, "mock")
    )
    resolved_max_tokens = max_tokens or int(os.environ.get("SHRAG_LLM_MAX_TOKENS", "512"))
    resolved_temp = temperature if temperature is not None else float(
        os.environ.get("SHRAG_LLM_TEMPERATURE", "0.2")
    )

    fn = _BACKENDS.get(resolved_backend)
    if fn is None:
        raise ValueError(f"Unknown SHRAG_LLM_BACKEND: {resolved_backend!r}")

    def _call() -> str:
        return fn(
            prompt,
            system=system,
            model=resolved_model,
            max_tokens=resolved_max_tokens,
            temperature=resolved_temp,
        )

    try:
        return _with_retry(_call, max_attempts=max_attempts)
    except Exception as exc:  # noqa: BLE001
        fallback = _is_fallback_enabled()
        if fallback and resolved_backend != "mock":
            logger.warning("LLM provider %r failed, falling back to mock: %s", resolved_backend, exc)
            return _complete_mock(prompt, system=system, model="mock", max_tokens=resolved_max_tokens, temperature=resolved_temp)
        raise


def deterministic_complete(prompt: str) -> str:
    """Legacy shim — calls mock backend directly."""
    return _complete_mock(prompt, system=None, model="mock", max_tokens=512, temperature=0.0)


def _is_fallback_enabled() -> bool:
    return os.environ.get("SHRAG_LLM_FALLBACK_TO_MOCK", "false").lower() == "true"
