from __future__ import annotations

import json
from pathlib import Path
from urllib import request

from tests.bench import run_erb_queries


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_dedupe_document_ids_keeps_order_and_unique():
    citations = [
        {"document_id": "d1"},
        {"document_id": "d2"},
        {"document_id": "d1"},
        "d3",
        "d2",
    ]
    assert run_erb_queries._dedupe_document_ids(citations) == ["d1", "d2", "d3"]


def test_run_queries_writes_answers_jsonl(tmp_path: Path, monkeypatch):
    erb_dir = tmp_path / "erb"
    _write_json(erb_dir / "documents" / "github" / "docs.json", {"documents": [{"dataset_doc_uuid": "d1", "text": "A"}]})
    (erb_dir / "questions.jsonl").write_text(
        json.dumps({"question_id": "q1", "question": "What?", "expected_doc_ids": ["d1"]}),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        run_erb_queries,
        "query_once",
        lambda **kwargs: {"answer": "ans", "citations": [{"document_id": "d1"}], "document_ids": ["d1"]},
    )
    output = tmp_path / "answers.jsonl"
    run_erb_queries.run_queries(
        erb_dir=erb_dir,
        base_url="http://localhost:8000",
        output=output,
        tenant_id="erb-bench",
        api_version="2026-05-01",
        roles="reader",
        user_id="erb-bench-runner",
        sources=["github"],
    )
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["question_id"] == "q1"
    assert rows[0]["document_ids"] == ["d1"]
    assert rows[0]["type"] == "unknown"
    assert rows[0]["expected_doc_ids"] == ["d1"]


def test_query_once_sends_roles_and_user_id_headers(monkeypatch):
    seen: dict[str, str] = {}

    class _Resp:
        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, exc_type, exc, tb):  # type: ignore[no-untyped-def]
            return False

        def read(self) -> bytes:
            return b'{"answer":"ok","citations":[]}'

    def _fake_urlopen(req: request.Request):  # type: ignore[no-untyped-def]
        headers = {k.lower(): v for k, v in req.header_items()}
        seen["X-Roles"] = headers.get("x-roles", "")
        seen["X-User-Id"] = headers.get("x-user-id", "")
        return _Resp()

    monkeypatch.setattr(run_erb_queries.request, "urlopen", _fake_urlopen)

    out = run_erb_queries.query_once(
        base_url="http://localhost:8000",
        tenant_id="erb-bench",
        api_version="2026-05-01",
        roles="reader,writer",
        user_id="bench-user",
        question="What is this?",
    )

    assert out["answer"] == "ok"
    assert seen["X-Roles"] == "reader,writer"
    assert seen["X-User-Id"] == "bench-user"


def test_run_queries_continue_on_error_writes_error_row(tmp_path: Path, monkeypatch):
    erb_dir = tmp_path / "erb"
    _write_json(erb_dir / "documents" / "github" / "docs.json", {"documents": [{"dataset_doc_uuid": "d1", "text": "A"}]})
    (erb_dir / "questions.jsonl").write_text(
        json.dumps({"question_id": "q1", "question": "What?", "expected_doc_ids": ["d1"]}),
        encoding="utf-8",
    )

    def _raise_http_error(**kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("Query failed for question 'What?': HTTP 403 blocked_chunk")

    monkeypatch.setattr(run_erb_queries, "query_once", _raise_http_error)

    output = tmp_path / "answers.jsonl"
    run_erb_queries.run_queries(
        erb_dir=erb_dir,
        base_url="http://localhost:8000",
        output=output,
        tenant_id="erb-bench",
        api_version="2026-05-01",
        roles="reader",
        user_id="erb-bench-runner",
        sources=["github"],
    )
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["question_id"] == "q1"
    assert rows[0]["answer"] == ""
    assert rows[0]["citations"] == []
    assert rows[0]["document_ids"] == []
    assert "HTTP 403" in rows[0]["error"]


def test_run_queries_fail_fast_raises_on_error(tmp_path: Path, monkeypatch):
    erb_dir = tmp_path / "erb"
    _write_json(erb_dir / "documents" / "github" / "docs.json", {"documents": [{"dataset_doc_uuid": "d1", "text": "A"}]})
    (erb_dir / "questions.jsonl").write_text(
        json.dumps({"question_id": "q1", "question": "What?", "expected_doc_ids": ["d1"]}),
        encoding="utf-8",
    )

    def _raise_http_error(**kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("Query failed for question 'What?': HTTP 403 blocked_chunk")

    monkeypatch.setattr(run_erb_queries, "query_once", _raise_http_error)

    try:
        run_erb_queries.run_queries(
            erb_dir=erb_dir,
            base_url="http://localhost:8000",
            output=tmp_path / "answers.jsonl",
            tenant_id="erb-bench",
            api_version="2026-05-01",
            roles="reader",
            user_id="erb-bench-runner",
            sources=["github"],
            fail_fast=True,
        )
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "HTTP 403" in str(exc)
