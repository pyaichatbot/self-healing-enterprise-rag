from __future__ import annotations

import json
from pathlib import Path


def test_run_training_success(tmp_path):
    from ops.training.run_training import main as train_main
    import sys

    argv_orig = list(sys.argv)
    try:
        sys.argv = [
            "run_training.py",
            "--state-dir",
            str(tmp_path),
            "--command-template",
            "echo ok",
            "--provenance-mode",
            "production",
        ]
        rc = train_main()
    finally:
        sys.argv = argv_orig
    assert rc == 0
    report = json.loads((tmp_path / "finetune-training-report.json").read_text(encoding="utf-8"))
    exec_payload = json.loads((tmp_path / "finetune-training-exec.json").read_text(encoding="utf-8"))
    assert report["eval_passed"] is True
    assert report["provenance_mode"] == "production"
    assert report["framework"] == "peft"
    assert exec_payload["return_code"] == 0


def test_run_training_failure(tmp_path):
    from ops.training.run_training import main as train_main
    import sys

    argv_orig = list(sys.argv)
    try:
        sys.argv = [
            "run_training.py",
            "--state-dir",
            str(tmp_path),
            "--command-template",
            "false",
            "--provenance-mode",
            "production",
        ]
        rc = train_main()
    finally:
        sys.argv = argv_orig
    assert rc == 1
    report = json.loads((tmp_path / "finetune-training-report.json").read_text(encoding="utf-8"))
    assert report["eval_passed"] is False


def test_release_gate_requires_training_exec_and_job_manifest(tmp_path, monkeypatch):
    from ops.verification.release_gate import run_gate

    def _write(path: Path, payload: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    _write(tmp_path / ".state/scale-500k-report.json", {"all_gates_passed": True})
    _write(tmp_path / ".state/benchmark-500k-report.json", {"passed": True})
    _write(tmp_path / ".state/dr-failover-report.json", {"passed": True})
    _write(tmp_path / ".state/connector-evidence-report.json", {"passed": True})
    _write(tmp_path / ".state/connector-evidence-report-strict.json", {"passed": True, "evidence_mode": "live"})
    _write(
        tmp_path / ".state/finetune-readiness-report.json",
        {"passed": True, "details": {"require_non_simulated": True}},
    )
    (tmp_path / ".state/finetune-training-job.yaml").write_text("kind: Job\n", encoding="utf-8")
    (tmp_path / ".state/finetune-training-exec.json").write_text('{"return_code":0}', encoding="utf-8")
    ok, failures = run_gate(strict=True)
    assert ok is True
    assert failures == []
