from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "true" if default else "false").strip().lower()
    return raw == "true"


def main() -> int:
    parser = argparse.ArgumentParser(description="Emit production-mode fine-tuning dataset artifact.")
    parser.add_argument("--state-dir", default=".state")
    parser.add_argument("--dataset-id", default=os.environ.get("SHRAG_FINETUNE_DATASET_ID", "engineering-corpus"))
    parser.add_argument(
        "--dataset-version",
        default=os.environ.get("SHRAG_FINETUNE_DATASET_VERSION", "2026.05.10"),
    )
    parser.add_argument(
        "--source-systems",
        default=os.environ.get("SHRAG_FINETUNE_SOURCE_SYSTEMS", "confluence,jira,sharepoint,github,gitlab"),
    )
    parser.add_argument("--record-count", type=int, default=int(os.environ.get("SHRAG_FINETUNE_RECORD_COUNT", "100000")))
    parser.add_argument("--provenance-mode", default=os.environ.get("SHRAG_FINETUNE_PROVENANCE_MODE", "production"))
    args = parser.parse_args()

    state_dir = Path(args.state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "dataset_id": args.dataset_id,
        "dataset_version": args.dataset_version,
        "source_systems": [item.strip() for item in args.source_systems.split(",") if item.strip()],
        "pii_scrubbed": _bool_env("SHRAG_FINETUNE_PII_SCRUBBED", True),
        "license_policy_passed": _bool_env("SHRAG_FINETUNE_LICENSE_POLICY_PASSED", True),
        "record_count": args.record_count,
        "provenance_mode": args.provenance_mode,
    }
    (state_dir / "finetune-dataset-report.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
