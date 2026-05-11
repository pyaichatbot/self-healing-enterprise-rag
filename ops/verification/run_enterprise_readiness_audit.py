from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from ops.verification.enterprise_readiness_audit import report_to_dict, run_enterprise_audit


def main() -> int:
    parser = argparse.ArgumentParser(description="Run enterprise readiness audit for RAG + fine-tuning lane.")
    parser.add_argument("--output", required=True, help="Output JSON report path")
    parser.add_argument("--strict-external", action="store_true", default=False)
    args = parser.parse_args()

    report = run_enterprise_audit(strict_external=args.strict_external)
    payload = report_to_dict(report)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(output)
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
