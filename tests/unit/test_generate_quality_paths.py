from __future__ import annotations

import pytest
import types

import shrag.generate.llm as llm_mod
from shrag.generate.citations import extract_citations
from shrag.generate.llm import complete, deterministic_complete
from shrag.generate.pipeline import BaselineGenerateStage
from shrag.generate.stream import stream_text
from shrag.observe.models import RequestContext, RetrievedChunk
from shrag.settings import settings


def test_extract_citations_uses_intersection_and_fallback_order():
    chunks = (
        RetrievedChunk(chunk_id="c1", source_id="doc:a", text="alpha"),
        RetrievedChunk(chunk_id="c2", source_id="doc:b", text="beta"),
        RetrievedChunk(chunk_id="c3", source_id="doc:c", text="gamma"),
    )
    cited = extract_citations("See [doc:b] and [doc:x] and [doc:a].", chunks)
    assert cited == ("doc:a", "doc:b")

    fallback = extract_citations("no explicit markers", chunks)
    assert fallback == ("doc:a", "doc:b")


def test_llm_complete_falls_back_to_mock_when_provider_fails(monkeypatch):
    monkeypatch.setenv("SHRAG_LLM_FALLBACK_TO_MOCK", "true")

    def _boom(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("provider_down")

    monkeypatch.setitem(__import__("shrag.generate.llm", fromlist=["_BACKENDS"])._BACKENDS, "openai", _boom)
    response = complete("Explain RAG briefly", backend="openai", max_attempts=1)
    assert response.startswith("[mock-llm] Responding to:")


def test_baseline_generate_stage_enforces_evidence_gate_and_prompt_path(monkeypatch):
    stage = BaselineGenerateStage()
    context = RequestContext(request_id="r1", query="what is rollback?")

    original = settings.generate_require_evidence
    settings.generate_require_evidence = True
    try:
        no_evidence = stage.generate(context, ())
        assert no_evidence.response_text == "Insufficient evidence."
        assert no_evidence.citations == ()
    finally:
        settings.generate_require_evidence = original

    settings.generate_require_evidence = False
    try:
        monkeypatch.setattr("shrag.generate.pipeline.complete", lambda prompt, system=None: "Answer with [doc:1]")
        with_evidence = stage.generate(
            context,
            (RetrievedChunk(chunk_id="c1", source_id="doc:1", text="rollback means reverting"),),
        )
        assert with_evidence.response_text == "Answer with [doc:1]"
        assert with_evidence.citations == ("doc:1",)
    finally:
        settings.generate_require_evidence = original


def test_stream_text_preserves_content_and_chunks():
    text = "abcdefghijklmnopqrstuvwxyz"
    parts = list(stream_text(text, token_size=5))
    assert parts == ["abcde", "fghij", "klmno", "pqrst", "uvwxy", "z"]
    assert "".join(parts) == text


def test_deterministic_complete_is_stable():
    first = deterministic_complete("repeatable prompt")
    second = deterministic_complete("repeatable prompt")
    assert first == second


def test_complete_rejects_unknown_backend():
    with pytest.raises(ValueError, match="Unknown SHRAG_LLM_BACKEND"):
        complete("hello", backend="nope")


def test_complete_uses_env_model_and_tokens(monkeypatch):
    captured = {}

    def _fake(prompt, *, system, model, max_tokens, temperature):  # type: ignore[no-untyped-def]
        captured["system"] = system
        captured["model"] = model
        captured["max_tokens"] = max_tokens
        captured["temperature"] = temperature
        return "ok"

    monkeypatch.setitem(llm_mod._BACKENDS, "mock", _fake)
    monkeypatch.setenv("SHRAG_LLM_MODEL", "env-model")
    monkeypatch.setenv("SHRAG_LLM_MAX_TOKENS", "77")
    monkeypatch.setenv("SHRAG_LLM_TEMPERATURE", "0.33")
    out = complete("x", backend="mock", system="sys")
    assert out == "ok"
    assert captured == {"system": "sys", "model": "env-model", "max_tokens": 77, "temperature": 0.33}


def test_complete_raises_when_fallback_disabled(monkeypatch):
    def _boom(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("provider_down")

    monkeypatch.setitem(llm_mod._BACKENDS, "openai", _boom)
    monkeypatch.setenv("SHRAG_LLM_FALLBACK_TO_MOCK", "false")
    with pytest.raises(RuntimeError, match="LLM call failed"):
        complete("hello", backend="openai", max_attempts=1)


def test_is_fallback_enabled_env(monkeypatch):
    monkeypatch.setenv("SHRAG_LLM_FALLBACK_TO_MOCK", "TrUe")
    assert llm_mod._is_fallback_enabled() is True


def test_complete_openai_backend_with_stub(monkeypatch):
    class _Msg:
        content = "openai-ok"

    class _Choice:
        message = _Msg()

    class _Usage:
        prompt_tokens = 1
        completion_tokens = 2
        total_tokens = 3

    class _Completions:
        @staticmethod
        def create(**kwargs):  # type: ignore[no-untyped-def]
            return type("Resp", (), {"choices": [_Choice()], "usage": _Usage()})()

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    fake = types.SimpleNamespace(OpenAI=lambda api_key="": _Client())
    monkeypatch.setitem(__import__("sys").modules, "openai", fake)
    assert llm_mod._complete_openai("prompt", system=None, model="m", max_tokens=20, temperature=0.2) == "openai-ok"


def test_complete_anthropic_backend_with_stub(monkeypatch):
    class _Content:
        text = "anthropic-ok"

    class _Usage:
        input_tokens = 2
        output_tokens = 1

    class _Messages:
        @staticmethod
        def create(**kwargs):  # type: ignore[no-untyped-def]
            return type("Resp", (), {"content": [_Content()], "usage": _Usage()})()

    class _Client:
        messages = _Messages()

    fake = types.SimpleNamespace(Anthropic=lambda api_key="": _Client())
    monkeypatch.setitem(__import__("sys").modules, "anthropic", fake)
    assert llm_mod._complete_anthropic("prompt", system=None, model="m", max_tokens=20, temperature=0.2) == "anthropic-ok"
