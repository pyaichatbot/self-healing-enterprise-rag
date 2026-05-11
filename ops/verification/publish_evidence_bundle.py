from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
import shutil


REQUIRED_REPORTS = (
    "scale-500k-report.json",
    "benchmark-500k-report.json",
    "dr-failover-report.json",
    "connector-evidence-report.json",
)
OPTIONAL_REPORTS = (
    "connector-evidence-report-strict.json",
    "finetune-readiness-report.json",
    "finetune-dataset-report.json",
    "finetune-training-report.json",
    "finetune-training-exec.json",
    "finetune-training-job.yaml",
    "finetune-promotion-report.json",
)


def publish_bundle(*, state_dir: Path, out_dir: Path) -> Path:
    missing = [name for name in REQUIRED_REPORTS if not (state_dir / name).exists()]
    if missing:
        raise FileNotFoundError(f"missing_reports:{','.join(missing)}")

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    latest = out_dir / "latest"
    snapshot = out_dir / timestamp

    latest.mkdir(parents=True, exist_ok=True)
    snapshot.mkdir(parents=True, exist_ok=True)

    for name in REQUIRED_REPORTS:
        shutil.copy2(state_dir / name, latest / name)
        shutil.copy2(state_dir / name, snapshot / name)
    copied_optional: list[str] = []
    for name in OPTIONAL_REPORTS:
        source = state_dir / name
        if source.exists():
            shutil.copy2(source, latest / name)
            shutil.copy2(source, snapshot / name)
            copied_optional.append(name)

    manifest = {
        "generated_at_utc": timestamp,
        "reports": list(REQUIRED_REPORTS),
        "source_state_dir": str(state_dir),
        "optional_reports": copied_optional,
    }
    (latest / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    (snapshot / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return latest


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish evidence reports into a versioned docs bundle.")
    parser.add_argument("--state-dir", default=".state", help="Directory containing generated report JSON files")
    parser.add_argument("--out-dir", default="docs/evidence", help="Output evidence directory")
    args = parser.parse_args()

    latest = publish_bundle(state_dir=Path(args.state_dir), out_dir=Path(args.out_dir))
    print(latest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
