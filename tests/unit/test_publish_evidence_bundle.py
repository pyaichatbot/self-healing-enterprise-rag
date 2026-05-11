from pathlib import Path
import json

from ops.verification.publish_evidence_bundle import publish_bundle


def _write_report(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_publish_bundle_copies_required_reports(tmp_path):
    state = tmp_path / ".state"
    out = tmp_path / "docs" / "evidence"
    _write_report(state / "scale-500k-report.json", {"all_gates_passed": True})
    _write_report(state / "benchmark-500k-report.json", {"passed": True})
    _write_report(state / "dr-failover-report.json", {"passed": True})
    _write_report(state / "connector-evidence-report.json", {"passed": True})

    latest = publish_bundle(state_dir=state, out_dir=out)
    assert latest == out / "latest"
    assert (latest / "manifest.json").exists()
    assert (latest / "scale-500k-report.json").exists()
    assert (latest / "benchmark-500k-report.json").exists()
    assert (latest / "dr-failover-report.json").exists()
    assert (latest / "connector-evidence-report.json").exists()


def test_publish_bundle_fails_if_reports_missing(tmp_path):
    state = tmp_path / ".state"
    out = tmp_path / "docs" / "evidence"
    state.mkdir(parents=True, exist_ok=True)
    try:
        publish_bundle(state_dir=state, out_dir=out)
    except FileNotFoundError as exc:
        assert "missing_reports" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected FileNotFoundError for missing reports")
