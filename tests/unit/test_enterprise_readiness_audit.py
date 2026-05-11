from __future__ import annotations

import json
from pathlib import Path

from ops.verification.enterprise_readiness_audit import report_to_dict, run_enterprise_audit


def _write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_enterprise_readiness_audit_detects_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    report = run_enterprise_audit(strict_external=True)
    assert report.passed is False
    assert report.unresolved
    payload = report_to_dict(report)
    assert "items" in payload


def test_enterprise_readiness_audit_passes_with_required_artifacts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("src/shrag/api").mkdir(parents=True, exist_ok=True)
    Path("src/shrag/security").mkdir(parents=True, exist_ok=True)
    Path("src/shrag/retrieve").mkdir(parents=True, exist_ok=True)
    Path("src/shrag/ingest/connectors").mkdir(parents=True, exist_ok=True)
    Path("src/shrag/ingest").mkdir(parents=True, exist_ok=True)
    Path("ops/verification").mkdir(parents=True, exist_ok=True)
    Path("ops/training").mkdir(parents=True, exist_ok=True)
    Path("ops/helm/templates").mkdir(parents=True, exist_ok=True)
    for p in (
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
    ):
        Path(p).write_text("# stub\n", encoding="utf-8")

    _write(Path(".state/scale-500k-report.json"), {"all_gates_passed": True})
    _write(Path(".state/dr-failover-report.json"), {"passed": True})
    _write(Path(".state/connector-evidence-report.json"), {"passed": True, "evidence_mode": "live"})
    _write(Path(".state/connector-evidence-report-strict.json"), {"passed": True, "evidence_mode": "live"})
    _write(Path(".state/finetune-dataset-report.json"), {"ok": True})
    _write(Path(".state/finetune-training-report.json"), {"ok": True})
    _write(Path(".state/finetune-training-exec.json"), {"return_code": 0, "provenance_mode": "production"})
    Path(".state/finetune-training-job.yaml").write_text("kind: Job\n", encoding="utf-8")
    _write(Path(".state/finetune-promotion-report.json"), {"ok": True})
    _write(
        Path(".state/finetune-readiness-report.json"),
        {
            "passed": True,
            "details": {
                "require_non_simulated": True,
                "training_exec_return_code": 0,
                "training_exec_mode": "production",
            },
        },
    )
    Path("docs/evidence/latest").mkdir(parents=True, exist_ok=True)
    _write(Path("docs/evidence/latest/manifest.json"), {"ok": True})
    _write(Path("docs/evidence/latest/scale-500k-report.json"), {"all_gates_passed": True})
    _write(Path("docs/evidence/latest/dr-failover-report.json"), {"passed": True})
    _write(Path("docs/evidence/latest/connector-evidence-report.json"), {"passed": True})

    report = run_enterprise_audit(strict_external=True)
    assert report.passed is True
    assert report.unresolved == ()
