from pathlib import Path
import json

from ops.verification.release_gate import run_gate


def _write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_release_gate_passes_with_required_reports(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write(tmp_path / ".state/scale-500k-report.json", {"all_gates_passed": True})
    _write(tmp_path / ".state/benchmark-500k-report.json", {"passed": True})
    _write(tmp_path / ".state/dr-failover-report.json", {"passed": True})
    _write(tmp_path / ".state/connector-evidence-report.json", {"passed": True})
    ok, failures = run_gate(strict=False)
    assert ok is True
    assert failures == []


def test_release_gate_strict_fails_without_strict_connector_report(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write(tmp_path / ".state/scale-500k-report.json", {"all_gates_passed": True})
    _write(tmp_path / ".state/benchmark-500k-report.json", {"passed": True})
    _write(tmp_path / ".state/dr-failover-report.json", {"passed": True})
    _write(tmp_path / ".state/connector-evidence-report.json", {"passed": True})
    ok, failures = run_gate(strict=True)
    assert ok is False
    assert "connector_strict_failed" in failures or any("missing_report" in f for f in failures)


def test_release_gate_strict_passes_with_finetune_report(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write(tmp_path / ".state/scale-500k-report.json", {"all_gates_passed": True})
    _write(tmp_path / ".state/benchmark-500k-report.json", {"passed": True})
    _write(tmp_path / ".state/dr-failover-report.json", {"passed": True})
    _write(tmp_path / ".state/connector-evidence-report.json", {"passed": True})
    _write(tmp_path / ".state/connector-evidence-report-strict.json", {"passed": True, "evidence_mode": "live"})
    _write(tmp_path / ".state/finetune-training-job.yaml", {"kind": "Job"})
    _write(tmp_path / ".state/finetune-training-exec.json", {"return_code": 0})
    _write(
        tmp_path / ".state/finetune-readiness-report.json",
        {"passed": True, "details": {"require_non_simulated": True}},
    )
    ok, failures = run_gate(strict=True)
    assert ok is True
    assert failures == []


def test_release_gate_strict_fails_without_non_simulated_flag(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write(tmp_path / ".state/scale-500k-report.json", {"all_gates_passed": True})
    _write(tmp_path / ".state/benchmark-500k-report.json", {"passed": True})
    _write(tmp_path / ".state/dr-failover-report.json", {"passed": True})
    _write(tmp_path / ".state/connector-evidence-report.json", {"passed": True})
    _write(tmp_path / ".state/connector-evidence-report-strict.json", {"passed": True, "evidence_mode": "live"})
    _write(tmp_path / ".state/finetune-training-job.yaml", {"kind": "Job"})
    _write(tmp_path / ".state/finetune-readiness-report.json", {"passed": True, "details": {"require_non_simulated": False}})
    ok, failures = run_gate(strict=True)
    assert ok is False
    assert "finetune_non_simulated_check_not_enforced" in failures


def test_release_gate_strict_fails_without_training_job_manifest(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write(tmp_path / ".state/scale-500k-report.json", {"all_gates_passed": True})
    _write(tmp_path / ".state/benchmark-500k-report.json", {"passed": True})
    _write(tmp_path / ".state/dr-failover-report.json", {"passed": True})
    _write(tmp_path / ".state/connector-evidence-report.json", {"passed": True})
    _write(tmp_path / ".state/connector-evidence-report-strict.json", {"passed": True, "evidence_mode": "live"})
    _write(tmp_path / ".state/finetune-readiness-report.json", {"passed": True, "details": {"require_non_simulated": True}})
    ok, failures = run_gate(strict=True)
    assert ok is False
    assert "missing_report:finetune-training-job.yaml" in failures


def test_release_gate_strict_fails_for_simulated_connector_evidence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write(tmp_path / ".state/scale-500k-report.json", {"all_gates_passed": True})
    _write(tmp_path / ".state/benchmark-500k-report.json", {"passed": True})
    _write(tmp_path / ".state/dr-failover-report.json", {"passed": True})
    _write(tmp_path / ".state/connector-evidence-report.json", {"passed": True})
    _write(tmp_path / ".state/connector-evidence-report-strict.json", {"passed": True, "evidence_mode": "simulated"})
    _write(tmp_path / ".state/finetune-training-job.yaml", {"kind": "Job"})
    _write(tmp_path / ".state/finetune-training-exec.json", {"return_code": 0})
    _write(tmp_path / ".state/finetune-readiness-report.json", {"passed": True, "details": {"require_non_simulated": True}})
    ok, failures = run_gate(strict=True)
    assert ok is False
    assert "connector_strict_not_live" in failures
