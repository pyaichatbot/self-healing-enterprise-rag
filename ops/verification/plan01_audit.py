from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(slots=True)
class AuditItem:
    name: str
    status: str  # pass|fail
    details: str


@dataclass(slots=True)
class AuditReport:
    passed: bool
    items: tuple[AuditItem, ...]
    unresolved: tuple[str, ...]


def _exists(path: str) -> bool:
    return Path(path).exists()


def run_audit(*, strict_external: bool = True) -> AuditReport:
    items: list[AuditItem] = []

    required_paths = (
        "src/shrag/api/routes.py",
        "src/shrag/api/rate_limit.py",
        "src/shrag/api/backpressure.py",
        "src/shrag/heal/retry.py",
        "src/shrag/heal/circuit.py",
        "src/shrag/ingest/connectors/base.py",
        "src/shrag/ingest/connectors/confluence.py",
        "src/shrag/ingest/connectors/jira.py",
        "src/shrag/ingest/connectors/sharepoint.py",
        "src/shrag/ingest/connectors/google_drive.py",
        "src/shrag/ingest/connectors/notion.py",
        "src/shrag/ingest/connectors/github.py",
        "src/shrag/ingest/connectors/gitlab.py",
        "src/shrag/ingest/connectors/webdav_s3.py",
        "src/shrag/eval/scale_gate.py",
        "tests/scale/run_500k_validation.py",
        "ops/drills/failover_drill.py",
        "ops/verification/run_connector_evidence.py",
        "ops/verification/release_gate.py",
        "ops/verification/publish_evidence_bundle.py",
        ".github/workflows/ci.yml",
    )
    missing = [path for path in required_paths if not _exists(path)]
    items.append(
        AuditItem(
            name="required_artifacts_present",
            status="pass" if not missing else "fail",
            details="all required files present" if not missing else f"missing:{','.join(missing)}",
        )
    )

    evidence_files = (
        "docs/evidence/latest/scale-500k-report.json",
        "docs/evidence/latest/dr-failover-report.json",
        "docs/evidence/latest/connector-evidence-report.json",
        "docs/evidence/latest/manifest.json",
    )
    missing_evidence = [path for path in evidence_files if not _exists(path)]
    items.append(
        AuditItem(
            name="evidence_bundle_latest_present",
            status="pass" if not missing_evidence else "fail",
            details="evidence bundle present" if not missing_evidence else f"missing:{','.join(missing_evidence)}",
        )
    )

    unresolved: list[str] = []
    strict_connector = Path(".state/connector-evidence-report-strict.json")
    if strict_connector.exists():
        strict_payload = json.loads(strict_connector.read_text(encoding="utf-8"))
        if not bool(strict_payload.get("passed") is True):
            unresolved.append("strict_connector_evidence_not_passed")
    else:
        unresolved.append("strict_connector_evidence_missing")

    benchmark_report = Path("docs/evidence/latest/scale-500k-report.json")
    if benchmark_report.exists():
        payload = json.loads(benchmark_report.read_text(encoding="utf-8"))
        if not bool(payload.get("all_gates_passed") is True):
            unresolved.append("scale_500k_gates_not_passed")
    else:
        unresolved.append("scale_500k_report_missing")

    external_status = "pass" if not unresolved else ("fail" if strict_external else "pass")
    items.append(
        AuditItem(
            name="external_live_evidence_status",
            status=external_status,
            details="all strict evidence satisfied" if not unresolved else ",".join(unresolved),
        )
    )

    passed = all(item.status == "pass" for item in items)
    return AuditReport(passed=passed, items=tuple(items), unresolved=tuple(unresolved))


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit plan-01 completion against repository artifacts.")
    parser.add_argument("--output", required=True, help="Output JSON report path")
    parser.add_argument("--strict-external", action="store_true", default=False)
    args = parser.parse_args()

    report = run_audit(strict_external=args.strict_external)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(asdict(report), indent=2, sort_keys=True), encoding="utf-8")
    print(output)
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
