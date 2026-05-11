from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from ops.verification.connector_evidence import (
    ConnectorCheckInput,
    report_to_dict,
    run_connector_evidence,
)


def _enabled(name: str) -> bool:
    return os.getenv(f"SHRAG_CONNECTOR_{name.upper()}_ENABLED", "false").lower() in {"1", "true", "yes"}


def _input(name: str) -> ConnectorCheckInput:
    key = name.upper()
    return ConnectorCheckInput(
        source=name,
        base_url=os.getenv(f"SHRAG_CONNECTOR_{key}_BASE_URL"),
        token=os.getenv(f"SHRAG_CONNECTOR_{key}_TOKEN"),
        scopes=os.getenv(f"SHRAG_CONNECTOR_{key}_SCOPES"),
        enabled=_enabled(name),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run live connector evidence checks and emit JSON.")
    parser.add_argument("--output", required=True, help="Path to output JSON report")
    parser.add_argument("--require-no-skips", action="store_true", default=False)
    parser.add_argument("--min-passed", type=int, default=0)
    args = parser.parse_args()

    checks = tuple(
        _input(name)
        for name in (
            "confluence",
            "jira",
            "sharepoint",
            "google_drive",
            "notion",
            "github",
            "gitlab",
            "webdav_s3",
        )
    )
    report = run_connector_evidence(
        checks,
        require_no_skips=args.require_no_skips,
        min_passed=args.min_passed,
    )
    payload = report_to_dict(report)
    payload["evidence_mode"] = "live"

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(output)
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
