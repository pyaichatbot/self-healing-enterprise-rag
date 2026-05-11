from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable

from shrag.ingest.connectors import ConnectorConfig, resolve_connector


@dataclass(slots=True)
class ConnectorCheckInput:
    source: str
    base_url: str | None
    token: str | None
    scopes: str | None
    enabled: bool


@dataclass(slots=True)
class ConnectorCheckResult:
    source: str
    status: str  # pass|fail|skip
    reason: str


@dataclass(slots=True)
class ConnectorEvidenceReport:
    passed: bool
    passed_count: int
    failed_count: int
    skipped_count: int
    strict_required: bool
    results: tuple[ConnectorCheckResult, ...]


Resolver = Callable[[str, ConnectorConfig], object]


def run_connector_evidence(
    checks: tuple[ConnectorCheckInput, ...],
    *,
    require_no_skips: bool = False,
    min_passed: int = 0,
    resolver: Resolver = resolve_connector,
) -> ConnectorEvidenceReport:
    results: list[ConnectorCheckResult] = []
    failed = False
    passed_count = 0
    failed_count = 0
    skipped_count = 0
    for check in checks:
        if not check.enabled:
            results.append(ConnectorCheckResult(source=check.source, status="skip", reason="not_enabled"))
            skipped_count += 1
            continue
        if not check.base_url or not check.token:
            results.append(ConnectorCheckResult(source=check.source, status="skip", reason="missing_base_url_or_token"))
            skipped_count += 1
            continue
        try:
            connector = resolver(
                check.source,
                ConnectorConfig(
                    base_url=check.base_url,
                    token=check.token,
                    dry_run=False,
                ),
            )
            auth_ok = connector.authenticate({"token": check.token, "scopes": check.scopes or ""})  # type: ignore[attr-defined]
            if not auth_ok:
                failed = True
                failed_count += 1
                results.append(ConnectorCheckResult(source=check.source, status="fail", reason="auth_scope_failed"))
                continue
            refs, _ = connector.discover(None)  # type: ignore[attr-defined]
            if not isinstance(refs, list):
                failed = True
                failed_count += 1
                results.append(ConnectorCheckResult(source=check.source, status="fail", reason="discover_contract_failed"))
                continue
            passed_count += 1
            results.append(ConnectorCheckResult(source=check.source, status="pass", reason="contract_verified"))
        except Exception as exc:  # pragma: no cover - defensive
            failed = True
            failed_count += 1
            results.append(ConnectorCheckResult(source=check.source, status="fail", reason=f"exception:{type(exc).__name__}"))
    if passed_count < min_passed:
        failed = True
    if require_no_skips and skipped_count > 0:
        failed = True
    return ConnectorEvidenceReport(
        passed=not failed,
        passed_count=passed_count,
        failed_count=failed_count,
        skipped_count=skipped_count,
        strict_required=require_no_skips or min_passed > 0,
        results=tuple(results),
    )


def report_to_dict(report: ConnectorEvidenceReport) -> dict[str, object]:
    return {
        "passed": report.passed,
        "passed_count": report.passed_count,
        "failed_count": report.failed_count,
        "skipped_count": report.skipped_count,
        "strict_required": report.strict_required,
        "results": [asdict(item) for item in report.results],
    }
