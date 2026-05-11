from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate simulated dataset artifact evidence.")
    parser.add_argument("--state-dir", default=".state")
    args = parser.parse_args()
    state_dir = Path(args.state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "dataset_id": os.environ.get("SHRAG_FINETUNE_DATASET_ID", "engineering-corpus"),
        "dataset_version": os.environ.get("SHRAG_FINETUNE_DATASET_VERSION", "2026.05.10"),
        "source_systems": os.environ.get(
            "SHRAG_FINETUNE_SOURCE_SYSTEMS",
            "confluence,jira,sharepoint,github,gitlab",
        ).split(","),
        "pii_scrubbed": os.environ.get("SHRAG_FINETUNE_PII_SCRUBBED", "true").lower() == "true",
        "license_policy_passed": os.environ.get("SHRAG_FINETUNE_LICENSE_POLICY_PASSED", "true").lower() == "true",
        "record_count": int(os.environ.get("SHRAG_FINETUNE_RECORD_COUNT", "100000")),
        "provenance_mode": os.environ.get("SHRAG_FINETUNE_PROVENANCE_MODE", "simulated"),
    }
    (state_dir / "finetune-dataset-report.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
