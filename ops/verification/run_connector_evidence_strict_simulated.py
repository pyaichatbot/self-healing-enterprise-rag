from __future__ import annotations

import argparse
import json
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


class _SimulatedConnector:
    def authenticate(self, config):
        scopes = str(config.get("scopes", ""))
        return "repo" in scopes

    def discover(self, cursor=None):
        _ = cursor
        return ["mock-org/mock-rag:docs/architecture.md@main"], None


def _resolver(source, config):
    _ = source, config
    return _SimulatedConnector()


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate strict connector evidence report in simulated mode.")
    parser.add_argument("--output", required=True, help="Path to strict evidence JSON output")
    args = parser.parse_args()

    checks = (
        ConnectorCheckInput(
            source="github",
            base_url="simulated://github",
            token="simulated-token",
            scopes="repo",
            enabled=True,
        ),
    )
    report = run_connector_evidence(checks, require_no_skips=True, min_passed=1, resolver=_resolver)
    payload = report_to_dict(report)
    payload["evidence_mode"] = "simulated"
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(out)
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
