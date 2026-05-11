from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import httpx

from tests.bench.erb_adapter import ErbDocument
from tests.bench import ingest_erb


class _FakeAsyncClient:
    def __init__(self, responses: list[int]):
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url: str, json: dict[str, object], headers: dict[str, str], timeout: float):  # noqa: A002
        self.calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        if not self.responses:
            return httpx.Response(202, json={"accepted": True})
        code = self.responses.pop(0)
        if code == -1:
            raise httpx.TimeoutException("timeout")
        return httpx.Response(code, json={"accepted": code < 300})


def test_build_headers_contains_deterministic_idempotency_key():
    doc = ErbDocument(dataset_doc_uuid="doc-1", document_id="doc-1", text="hello", source="arxiv", metadata={})

    headers = ingest_erb._build_headers("tenant-a", doc)

    digest = hashlib.sha256("tenant-a:doc-1:hello".encode("utf-8")).hexdigest()
    assert headers["Idempotency-Key"] == f"erb-doc-{digest}"
    assert headers["X-Tenant-Id"] == "tenant-a"
    assert headers["X-API-Version"] == "2026-05-01"
    assert headers["X-Roles"] == "writer"
    assert headers["X-User-Id"] == "erb-bench-runner"


def test_build_headers_allows_contract_header_overrides():
    doc = ErbDocument(dataset_doc_uuid="doc-1", document_id="doc-1", text="hello", source="arxiv", metadata={})

    headers = ingest_erb._build_headers(
        "tenant-a",
        doc,
        api_version="2026-07-01",
        roles="admin,writer",
        user_id="custom-user",
    )

    assert headers["X-API-Version"] == "2026-07-01"
    assert headers["X-Roles"] == "admin,writer"
    assert headers["X-User-Id"] == "custom-user"


def test_post_with_retry_retries_on_transient_and_then_succeeds(monkeypatch):
    fake = _FakeAsyncClient([503, 202])
    async def _noop(_: float) -> None:
        return None

    monkeypatch.setattr(ingest_erb.asyncio, "sleep", _noop)
    doc = ErbDocument(dataset_doc_uuid="doc-1", document_id="doc-1", text="hello", source="arxiv", metadata={})

    ok, reason = asyncio.run(ingest_erb._post_with_retry(fake, "http://example", "tenant", doc, timeout=5.0))

    assert ok is True
    assert reason is None
    assert len(fake.calls) == 2


def test_ingest_documents_collects_source_counts_and_failures(monkeypatch):
    fake = _FakeAsyncClient([202, 500, 400])

    class _Factory:
        def __init__(self, client):
            self.client = client

        def __call__(self):
            return self.client

    monkeypatch.setattr(ingest_erb.httpx, "AsyncClient", _Factory(fake))
    async def _noop(_: float) -> None:
        return None

    monkeypatch.setattr(ingest_erb.asyncio, "sleep", _noop)

    docs = [
        ErbDocument(dataset_doc_uuid="a", document_id="a", text="A", source="arxiv", metadata={}),
        ErbDocument(dataset_doc_uuid="b", document_id="b", text="B", source="pubmed", metadata={}),
    ]

    result = asyncio.run(
        ingest_erb.ingest_documents(
            documents=docs,
            base_url="http://example",
            tenant_id="tenant",
            concurrency=2,
            timeout=5.0,
        )
    )

    assert result.attempted == 2
    assert result.succeeded == 1
    assert result.failed == 1
    assert result.by_source == {"arxiv": 1}
    assert result.failures[0].document_id == "b"


def test_write_manifest(tmp_path: Path):
    result = ingest_erb.IngestResult(
        attempted=2,
        succeeded=1,
        failed=1,
        by_source={"arxiv": 1},
        failures=[ingest_erb.IngestFailure(document_id="b", source="pubmed", reason="http_400")],
    )
    out = tmp_path / "manifest.json"

    ingest_erb._write_manifest(out, result, "/tmp/erb", "http://example", "tenant")

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["attempted"] == 2
    assert payload["by_source"] == {"arxiv": 1}
    assert payload["failures"][0]["document_id"] == "b"


def test_parse_args_defaults_include_contract_headers(monkeypatch):
    monkeypatch.delenv("SHRAG_ERB_API_VERSION", raising=False)
    monkeypatch.delenv("SHRAG_ERB_ROLES", raising=False)
    monkeypatch.delenv("SHRAG_ERB_USER_ID", raising=False)

    args = ingest_erb._parse_args(
        [
            "--erb-dir",
            "/tmp/erb",
            "--base-url",
            "http://example",
            "--output",
            "/tmp/out.json",
        ]
    )

    assert args.api_version == "2026-05-01"
    assert args.roles == "writer"
    assert args.user_id == "erb-bench-runner"


def test_parse_args_allows_cli_and_env_header_overrides(monkeypatch):
    monkeypatch.setenv("SHRAG_ERB_API_VERSION", "2026-06-01")
    monkeypatch.setenv("SHRAG_ERB_ROLES", "editor")
    monkeypatch.setenv("SHRAG_ERB_USER_ID", "env-user")

    env_args = ingest_erb._parse_args(
        [
            "--erb-dir",
            "/tmp/erb",
            "--base-url",
            "http://example",
            "--output",
            "/tmp/out.json",
        ]
    )
    assert env_args.api_version == "2026-06-01"
    assert env_args.roles == "editor"
    assert env_args.user_id == "env-user"

    cli_args = ingest_erb._parse_args(
        [
            "--erb-dir",
            "/tmp/erb",
            "--base-url",
            "http://example",
            "--output",
            "/tmp/out.json",
            "--api-version",
            "2026-08-15",
            "--roles",
            "writer,admin",
            "--user-id",
            "cli-user",
        ]
    )
    assert cli_args.api_version == "2026-08-15"
    assert cli_args.roles == "writer,admin"
    assert cli_args.user_id == "cli-user"
