from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import random

import httpx

from tests.bench.erb_adapter import ErbDocument, load_erb_dataset

_RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
_DEFAULT_API_VERSION = "2026-05-01"
_DEFAULT_ROLES = "writer"
_DEFAULT_USER_ID = "erb-bench-runner"


@dataclass(slots=True)
class IngestFailure:
    document_id: str
    source: str
    reason: str


@dataclass(slots=True)
class IngestResult:
    attempted: int
    succeeded: int
    failed: int
    by_source: dict[str, int]
    failures: list[IngestFailure]


def _build_headers(
    tenant_id: str,
    document: ErbDocument,
    *,
    api_version: str = _DEFAULT_API_VERSION,
    roles: str = _DEFAULT_ROLES,
    user_id: str = _DEFAULT_USER_ID,
) -> dict[str, str]:
    digest = sha256(f"{tenant_id}:{document.document_id}:{document.text}".encode("utf-8")).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-API-Version": api_version,
        "X-Roles": roles,
        "X-User-Id": user_id,
        "X-Tenant-Id": tenant_id,
        "Idempotency-Key": f"erb-doc-{digest}",
    }


def _is_retryable(exc: Exception | None, response: httpx.Response | None) -> bool:
    if exc is not None:
        return isinstance(exc, (httpx.TimeoutException, httpx.TransportError))
    return bool(response and response.status_code in _RETRYABLE_STATUS_CODES)


async def _post_with_retry(
    client: httpx.AsyncClient,
    base_url: str,
    tenant_id: str,
    document: ErbDocument,
    timeout: float,
    *,
    api_version: str = _DEFAULT_API_VERSION,
    roles: str = _DEFAULT_ROLES,
    user_id: str = _DEFAULT_USER_ID,
    max_attempts: int = 4,
) -> tuple[bool, str | None]:
    payload = {"documents": [{"document_id": document.document_id, "text": document.text}]}
    headers = _build_headers(
        tenant_id,
        document,
        api_version=api_version,
        roles=roles,
        user_id=user_id,
    )
    last_reason: str | None = None

    for attempt in range(1, max_attempts + 1):
        response: httpx.Response | None = None
        error: Exception | None = None
        try:
            response = await client.post(f"{base_url.rstrip('/')}/docs", json=payload, headers=headers, timeout=timeout)
            if 200 <= response.status_code < 300:
                return True, None
            last_reason = f"http_{response.status_code}"
        except Exception as exc:  # pragma: no cover - exercised by tests via mocks
            error = exc
            last_reason = exc.__class__.__name__

        if attempt == max_attempts or not _is_retryable(error, response):
            return False, last_reason

        backoff = min(2.0, 0.2 * (2 ** (attempt - 1))) + random.uniform(0.0, 0.1)
        await asyncio.sleep(backoff)

    return False, last_reason


async def ingest_documents(
    documents: list[ErbDocument],
    base_url: str,
    tenant_id: str,
    concurrency: int,
    timeout: float,
    *,
    api_version: str = _DEFAULT_API_VERSION,
    roles: str = _DEFAULT_ROLES,
    user_id: str = _DEFAULT_USER_ID,
) -> IngestResult:
    sem = asyncio.Semaphore(max(1, concurrency))
    by_source: dict[str, int] = {}
    failures: list[IngestFailure] = []
    succeeded = 0

    async with httpx.AsyncClient() as client:
        async def _run(document: ErbDocument) -> None:
            nonlocal succeeded
            async with sem:
                ok, reason = await _post_with_retry(
                    client,
                    base_url,
                    tenant_id,
                    document,
                    timeout,
                    api_version=api_version,
                    roles=roles,
                    user_id=user_id,
                )
                if ok:
                    succeeded += 1
                    by_source[document.source] = by_source.get(document.source, 0) + 1
                else:
                    failures.append(
                        IngestFailure(
                            document_id=document.document_id,
                            source=document.source,
                            reason=reason or "unknown_error",
                        )
                    )

        await asyncio.gather(*(_run(doc) for doc in documents))

    return IngestResult(
        attempted=len(documents),
        succeeded=succeeded,
        failed=len(failures),
        by_source=by_source,
        failures=failures,
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest ERB docs into /docs")
    parser.add_argument("--erb-dir", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--tenant-id", default=os.environ.get("SHRAG_ERB_TENANT_ID", "erb-bench"))
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--api-version", default=os.environ.get("SHRAG_ERB_API_VERSION", _DEFAULT_API_VERSION))
    parser.add_argument("--roles", default=os.environ.get("SHRAG_ERB_ROLES", _DEFAULT_ROLES))
    parser.add_argument("--user-id", default=os.environ.get("SHRAG_ERB_USER_ID", _DEFAULT_USER_ID))
    parser.add_argument("--sources", nargs="*", default=None)
    return parser.parse_args(argv)


def _write_manifest(path: Path, result: IngestResult, erb_dir: str, base_url: str, tenant_id: str) -> None:
    payload = {
        "created_at": datetime.now(UTC).isoformat(),
        "erb_dir": erb_dir,
        "base_url": base_url,
        "tenant_id": tenant_id,
        "attempted": result.attempted,
        "succeeded": result.succeeded,
        "failed": result.failed,
        "by_source": result.by_source,
        "failures": [asdict(item) for item in result.failures],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    sources = tuple(args.sources) if args.sources else None
    dataset = load_erb_dataset(args.erb_dir, sources=sources)
    result = asyncio.run(
        ingest_documents(
            documents=dataset.documents,
            base_url=args.base_url,
            tenant_id=args.tenant_id,
            concurrency=args.concurrency,
            timeout=args.timeout,
            api_version=args.api_version,
            roles=args.roles,
            user_id=args.user_id,
        )
    )
    _write_manifest(Path(args.output), result, args.erb_dir, args.base_url, args.tenant_id)
    return 0 if result.failed == 0 else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
