from pathlib import Path
import json

from ops.verification.finetune_readiness import run_finetune_gate
from shrag.finetune.contracts import (
    DatasetArtifact,
    PromotionDecision,
    TrainingRunArtifact,
    validate_artifact_bundle,
)


def _write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_validate_artifact_bundle_passes_for_h100():
    ok, failures = validate_artifact_bundle(
        DatasetArtifact(
            dataset_id="d1",
            dataset_version="v1",
            source_systems=("confluence", "jira"),
            pii_scrubbed=True,
            license_policy_passed=True,
            record_count=10,
            provenance_mode="production",
        ),
        TrainingRunArtifact(
            run_id="r1",
            base_model="llama",
            method="qlora",
            gpu_type="H100",
            gpu_count=2,
            train_loss=1.2,
            eval_passed=True,
            provenance_mode="production",
            framework="peft",
        ),
        PromotionDecision(
            candidate_model_id="m1",
            approved=True,
            approver="board",
            change_ticket="CHG-1",
            rollback_plan_ref="rb-1",
            provenance_mode="production",
        ),
    )
    assert ok is True
    assert failures == []


def test_validate_artifact_bundle_fails_for_non_h100_when_required():
    ok, failures = validate_artifact_bundle(
        DatasetArtifact("d1", "v1", ("github",), True, True, 1, "production"),
        TrainingRunArtifact("r1", "llama", "lora", "A100", 1, 1.0, True, "production", "peft"),
        PromotionDecision("m1", True, "board", "CHG-2", "rb-2", "production"),
        require_h100=True,
    )
    assert ok is False
    assert "training_gpu_type_not_h100" in failures


def test_run_finetune_gate_requires_reports(tmp_path):
    ok, failures, details = run_finetune_gate(state_dir=tmp_path)
    assert ok is False
    assert any("missing_report" in item for item in failures)
    assert details["state_dir"] == str(tmp_path)


def test_run_finetune_gate_passes_with_valid_reports(tmp_path):
    _write(
        tmp_path / "finetune-dataset-report.json",
        {
            "dataset_id": "d1",
            "dataset_version": "v1",
            "source_systems": ["confluence"],
            "pii_scrubbed": True,
            "license_policy_passed": True,
            "record_count": 100,
            "provenance_mode": "production",
        },
    )
    _write(
        tmp_path / "finetune-training-report.json",
        {
            "run_id": "r1",
            "base_model": "llama",
            "method": "qlora",
            "gpu_type": "H100",
            "gpu_count": 4,
            "train_loss": 1.2,
            "eval_passed": True,
            "provenance_mode": "production",
            "framework": "peft",
        },
    )
    _write(
        tmp_path / "finetune-promotion-report.json",
        {
            "candidate_model_id": "m1",
            "approved": True,
            "approver": "board",
            "change_ticket": "CHG-3",
            "rollback_plan_ref": "rb-3",
            "provenance_mode": "production",
        },
    )
    (tmp_path / "finetune-training-exec.json").write_text(
        json.dumps({"return_code": 0, "provenance_mode": "production"}),
        encoding="utf-8",
    )
    ok, failures, details = run_finetune_gate(state_dir=tmp_path, require_non_simulated=True)
    assert ok is True
    assert failures == []
    assert details["validation_passed"] is True


def test_run_finetune_gate_fails_when_simulated_not_allowed(tmp_path):
    _write(
        tmp_path / "finetune-dataset-report.json",
        {
            "dataset_id": "d1",
            "dataset_version": "v1",
            "source_systems": ["confluence"],
            "pii_scrubbed": True,
            "license_policy_passed": True,
            "record_count": 100,
            "provenance_mode": "simulated",
        },
    )
    _write(
        tmp_path / "finetune-training-report.json",
        {
            "run_id": "r1",
            "base_model": "llama",
            "method": "qlora",
            "gpu_type": "H100",
            "gpu_count": 4,
            "train_loss": 1.2,
            "eval_passed": True,
            "provenance_mode": "simulated",
            "framework": "peft",
        },
    )
    _write(
        tmp_path / "finetune-promotion-report.json",
        {
            "candidate_model_id": "m1",
            "approved": True,
            "approver": "board",
            "change_ticket": "CHG-3",
            "rollback_plan_ref": "rb-3",
            "provenance_mode": "simulated",
        },
    )
    ok, failures, details = run_finetune_gate(state_dir=tmp_path, require_non_simulated=True)
    assert ok is False
    assert "dataset_simulated_not_allowed" in failures
    assert details["require_non_simulated"] is True


def test_run_finetune_gate_fails_when_exec_failed(tmp_path):
    _write(
        tmp_path / "finetune-dataset-report.json",
        {
            "dataset_id": "d1",
            "dataset_version": "v1",
            "source_systems": ["confluence"],
            "pii_scrubbed": True,
            "license_policy_passed": True,
            "record_count": 100,
            "provenance_mode": "production",
        },
    )
    _write(
        tmp_path / "finetune-training-report.json",
        {
            "run_id": "r1",
            "base_model": "llama",
            "method": "qlora",
            "gpu_type": "H100",
            "gpu_count": 4,
            "train_loss": 1.2,
            "eval_passed": True,
            "provenance_mode": "production",
            "framework": "peft",
        },
    )
    _write(
        tmp_path / "finetune-promotion-report.json",
        {
            "candidate_model_id": "m1",
            "approved": True,
            "approver": "board",
            "change_ticket": "CHG-3",
            "rollback_plan_ref": "rb-3",
            "provenance_mode": "production",
        },
    )
    _write(tmp_path / "finetune-training-exec.json", {"return_code": 1, "provenance_mode": "production"})
    ok, failures, _ = run_finetune_gate(state_dir=tmp_path, require_non_simulated=True)
    assert ok is False
    assert "training_exec_failed" in failures
