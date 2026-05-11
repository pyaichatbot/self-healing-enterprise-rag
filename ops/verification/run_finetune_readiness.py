from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ops.verification.finetune_readiness import run_finetune_gate


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate fine-tuning readiness evidence reports.")
    parser.add_argument("--state-dir", default=".state")
    parser.add_argument("--output", default=".state/finetune-readiness-report.json")
    parser.add_argument("--allow-non-h100", action="store_true", default=False)
    parser.add_argument("--require-non-simulated", action="store_true", default=False)
    args = parser.parse_args()

    ok, failures, details = run_finetune_gate(
        state_dir=Path(args.state_dir),
        require_h100=not args.allow_non_h100,
        require_non_simulated=args.require_non_simulated,
    )
    payload = {
        "passed": ok,
        "failures": failures,
        "details": details,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
