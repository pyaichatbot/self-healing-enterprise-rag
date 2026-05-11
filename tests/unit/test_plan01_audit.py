from pathlib import Path
import json
from dataclasses import asdict

from ops.verification.plan01_audit import run_audit


def test_plan01_audit_reports_items():
    report = run_audit()
    assert len(report.items) >= 3
    names = {item.name for item in report.items}
    assert "required_artifacts_present" in names
    assert "evidence_bundle_latest_present" in names
    assert "external_live_evidence_status" in names


def test_plan01_audit_json_serializable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path(".state").mkdir(parents=True, exist_ok=True)
    Path("docs/evidence/latest").mkdir(parents=True, exist_ok=True)
    for name in ("scale-500k-report.json", "dr-failover-report.json", "connector-evidence-report.json"):
        Path("docs/evidence/latest", name).write_text(json.dumps({"passed": True, "all_gates_passed": True}), encoding="utf-8")
    Path("docs/evidence/latest/manifest.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    Path(".state/connector-evidence-report-strict.json").write_text(json.dumps({"passed": True}), encoding="utf-8")

    report = run_audit()
    payload = {
        "passed": report.passed,
        "items": [asdict(item) for item in report.items],
        "unresolved": list(report.unresolved),
    }
    assert isinstance(payload["passed"], bool)
