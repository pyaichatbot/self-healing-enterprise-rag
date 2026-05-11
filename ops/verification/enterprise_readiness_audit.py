from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(slots=True)
class AuditItem:
    name: str
    status: str  # pass|fail
    details: str


@dataclass(slots=True)
class EnterpriseReadinessReport:
    passed: bool
    items: tuple[AuditItem, ...]
    unresolved: tuple[str, ...]


def _exists(path: str) -> bool:
    return Path(path).exists()


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_enterprise_audit(*, strict_external: bool = True) -> EnterpriseReadinessReport:
    items: list[AuditItem] = []
    unresolved: list[str] = []

    required_code_paths = (
        "src/shrag/api/routes.py",
        "src/shrag/security/authz.py",
        "src/shrag/security/prompt_guard.py",
        "src/shrag/security/rtbf.py",
        "src/shrag/retrieve/pipeline.py",
        "src/shrag/retrieve/graphrag.py",
        "src/shrag/ingest/connectors/base.py",
        "src/shrag/ingest/worker.py",
        "ops/verification/release_gate.py",
        "ops/verification/finetune_readiness.py",
        "ops/training/run_dataset_prep.py",
        "ops/training/run_training.py",
        "ops/training/emit_k8s_training_job.py",
        "ops/training/run_promotion.py",
        "ops/helm/templates/deployment.yaml",
    )
    missing_code = [path for path in required_code_paths if not _exists(path)]
    items.append(
        AuditItem(
            name="required_code_paths_present",
            status="pass" if not missing_code else "fail",
            details="all required code paths present" if not missing_code else f"missing:{','.join(missing_code)}",
        )
    )

    required_state_artifacts = (
        ".state/scale-500k-report.json",
        ".state/dr-failover-report.json",
        ".state/connector-evidence-report.json",
        ".state/connector-evidence-report-strict.json",
        ".state/finetune-dataset-report.json",
        ".state/finetune-training-report.json",
        ".state/finetune-training-exec.json",
        ".state/finetune-training-job.yaml",
        ".state/finetune-promotion-report.json",
        ".state/finetune-readiness-report.json",
    )
    missing_state = [path for path in required_state_artifacts if not _exists(path)]
    items.append(
        AuditItem(
            name="required_state_artifacts_present",
            status="pass" if not missing_state else "fail",
            details="all required state artifacts present" if not missing_state else f"missing:{','.join(missing_state)}",
        )
    )

    # Validate strict connector live evidence
    strict_connector = Path(".state/connector-evidence-report-strict.json")
    if strict_connector.exists():
        payload = _load_json(strict_connector)
        if not bool(payload.get("passed") is True):
            unresolved.append("strict_connector_evidence_not_passed")
        if str(payload.get("evidence_mode", "")).lower() != "live":
            unresolved.append("strict_connector_evidence_not_live")
    else:
        unresolved.append("strict_connector_evidence_missing")

    # Validate finetune readiness gate payload quality
    finetune = Path(".state/finetune-readiness-report.json")
    if finetune.exists():
        payload = _load_json(finetune)
        if not bool(payload.get("passed") is True):
            unresolved.append("finetune_readiness_not_passed")
        details = payload.get("details")
        if not isinstance(details, dict):
            unresolved.append("finetune_readiness_details_missing")
        else:
            if details.get("require_non_simulated") is not True:
                unresolved.append("finetune_non_simulated_check_not_enforced")
            raw_rc = details.get("training_exec_return_code", 1)
            try:
                training_exec_return_code = int(raw_rc)  # type: ignore[arg-type]
            except Exception:
                training_exec_return_code = 1
            if training_exec_return_code != 0:
                unresolved.append("finetune_training_exec_not_successful")
            if str(details.get("training_exec_mode", "")).lower() != "production":
                unresolved.append("finetune_training_exec_not_production")
    else:
        unresolved.append("finetune_readiness_report_missing")

    # Validate latest evidence bundle presence
    evidence_latest = (
        "docs/evidence/latest/manifest.json",
        "docs/evidence/latest/scale-500k-report.json",
        "docs/evidence/latest/dr-failover-report.json",
        "docs/evidence/latest/connector-evidence-report.json",
    )
    missing_latest = [path for path in evidence_latest if not _exists(path)]
    items.append(
        AuditItem(
            name="latest_evidence_bundle_present",
            status="pass" if not missing_latest else "fail",
            details="latest evidence bundle present" if not missing_latest else f"missing:{','.join(missing_latest)}",
        )
    )

    external_status = "pass" if not unresolved else ("fail" if strict_external else "pass")
    items.append(
        AuditItem(
            name="strict_external_evidence_status",
            status=external_status,
            details="all strict evidence checks passed" if not unresolved else ",".join(unresolved),
        )
    )

    passed = all(item.status == "pass" for item in items)
    return EnterpriseReadinessReport(passed=passed, items=tuple(items), unresolved=tuple(unresolved))


def report_to_dict(report: EnterpriseReadinessReport) -> dict[str, object]:
    return {
        "passed": report.passed,
        "items": [asdict(item) for item in report.items],
        "unresolved": list(report.unresolved),
    }
