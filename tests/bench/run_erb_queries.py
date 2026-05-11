from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
import os
from pathlib import Path
from urllib import error, request

from tests.bench.erb_adapter import load_erb_dataset


DEFAULT_TENANT_ID = "erb-bench"
DEFAULT_API_VERSION = "2026-05-01"
DEFAULT_ROLES = "reader"
DEFAULT_USER_ID = "erb-bench-runner"


def _dedupe_document_ids(citations: object) -> list[str]:
    if not isinstance(citations, Sequence) or isinstance(citations, (str, bytes)):
        return []
    ordered: list[str] = []
    seen: set[str] = set()
    for citation in citations:
        doc_id: str | None = None
        if isinstance(citation, dict):
            raw_doc_id = citation.get("document_id") or citation.get("doc_id") or citation.get("id")
            if raw_doc_id is not None:
                doc_id = str(raw_doc_id)
        elif citation is not None:
            doc_id = str(citation)
        if doc_id and doc_id not in seen:
            seen.add(doc_id)
            ordered.append(doc_id)
    return ordered


def query_once(
    *,
    base_url: str,
    tenant_id: str,
    api_version: str,
    roles: str,
    user_id: str,
    question: str,
) -> dict[str, object]:
    payload: dict[str, object] = {"query": question}

    req = request.Request(
        url=f"{base_url.rstrip('/')}/query",
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Tenant-Id": tenant_id,
            "X-API-Version": api_version,
            "X-Roles": roles,
            "X-User-Id": user_id,
        },
        data=json.dumps(payload).encode("utf-8"),
    )
    try:
        with request.urlopen(req) as resp:  # noqa: S310 - intentional configurable benchmark target
            body = json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Query failed for question {question!r}: HTTP {exc.code} {detail}") from exc

    answer = body.get("answer", "") if isinstance(body, dict) else ""
    citations = body.get("citations", []) if isinstance(body, dict) else []
    return {
        "answer": str(answer),
        "citations": citations,
        "document_ids": _dedupe_document_ids(citations),
    }


def run_queries(
    *,
    erb_dir: Path,
    base_url: str,
    output: Path,
    tenant_id: str,
    api_version: str,
    roles: str,
    user_id: str,
    sources: Sequence[str] | None,
    fail_fast: bool = False,
) -> Path:
    dataset = load_erb_dataset(erb_dir, sources=tuple(sources) if sources else None)
    doc_ids_for_sources = {doc.dataset_doc_uuid for doc in dataset.documents}
    questions = dataset.questions
    if sources:
        filtered = []
        for q in questions:
            expected_doc_ids = _expected_doc_ids(q)
            if not expected_doc_ids:
                continue
            if any(doc_id in doc_ids_for_sources for doc_id in expected_doc_ids):
                filtered.append(q)
        questions = filtered
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for q in questions:
            expected_doc_ids = _expected_doc_ids(q)
            error_message: str | None = None
            try:
                result = query_once(
                    base_url=base_url,
                    tenant_id=tenant_id,
                    api_version=api_version,
                    roles=roles,
                    user_id=user_id,
                    question=q.question,
                )
            except RuntimeError as exc:
                if fail_fast:
                    raise
                result = {"answer": "", "citations": [], "document_ids": []}
                error_message = str(exc)

            row = {
                "question_id": q.question_id,
                "question": q.question,
                "type": _question_type(q),
                "expected_doc_ids": expected_doc_ids,
                "gold_answer": q.metadata.get("gold_answer"),
                "answer_facts": q.metadata.get("answer_facts"),
                "answer": result["answer"],
                "citations": result["citations"],
                "document_ids": result["document_ids"],
                "error": error_message,
            }
            handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ERB questions against /query and write answers JSONL.")
    parser.add_argument("--erb-dir", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--tenant-id", default=os.environ.get("SHRAG_ERB_TENANT_ID", DEFAULT_TENANT_ID))
    parser.add_argument("--api-version", default=os.environ.get("SHRAG_ERB_API_VERSION", DEFAULT_API_VERSION))
    parser.add_argument("--roles", default=os.environ.get("SHRAG_ERB_ROLES", DEFAULT_ROLES))
    parser.add_argument("--user-id", default=os.environ.get("SHRAG_ERB_USER_ID", DEFAULT_USER_ID))
    parser.add_argument("--sources", help="Optional comma-separated source filter list")
    parser.add_argument("--fail-fast", action="store_true", help="Stop immediately on first query HTTP error.")
    args = parser.parse_args()

    sources = [s.strip() for s in args.sources.split(",") if s.strip()] if args.sources else None
    out = run_queries(
        erb_dir=Path(args.erb_dir),
        base_url=args.base_url,
        output=Path(args.output),
        tenant_id=args.tenant_id,
        api_version=args.api_version,
        roles=args.roles,
        user_id=args.user_id,
        sources=sources,
        fail_fast=args.fail_fast,
    )
    print(out)
    return 0


def _expected_doc_ids(question: object) -> list[str]:
    if hasattr(question, "expected_doc_ids"):
        raw = getattr(question, "expected_doc_ids")
        if isinstance(raw, list):
            return [str(v) for v in raw if str(v).strip()]
    if hasattr(question, "dataset_doc_uuid"):
        raw_uuid = getattr(question, "dataset_doc_uuid")
        if isinstance(raw_uuid, str) and raw_uuid.strip():
            return [raw_uuid.strip()]
    return []


def _question_type(question: object) -> str:
    value = getattr(question, "question_type", None)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
