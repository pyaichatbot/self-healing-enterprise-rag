from __future__ import annotations

import argparse
import json
from pathlib import Path


def _write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate simulated fine-tuning readiness evidence.")
    parser.add_argument("--state-dir", default=".state")
    parser.add_argument("--gpu-type", default="H100")
    parser.add_argument("--method", default="qlora")
    parser.add_argument("--record-count", type=int, default=100000)
    args = parser.parse_args()

    state_dir = Path(args.state_dir)
    _write(
        state_dir / "finetune-dataset-report.json",
        {
            "dataset_id": "engineering-corpus",
            "dataset_version": "2026.05.10",
            "source_systems": ["confluence", "jira", "sharepoint", "github", "gitlab"],
            "pii_scrubbed": True,
            "license_policy_passed": True,
            "record_count": args.record_count,
        },
    )
    _write(
        state_dir / "finetune-training-report.json",
        {
            "run_id": "train-20260510-001",
            "base_model": "llama3.1-70b-instruct",
            "method": args.method,
            "gpu_type": args.gpu_type,
            "gpu_count": 4,
            "train_loss": 1.42,
            "eval_passed": True,
        },
    )
    _write(
        state_dir / "finetune-promotion-report.json",
        {
            "candidate_model_id": "eng-assistant-v1",
            "approved": True,
            "approver": "ml-governance-board",
            "change_ticket": "CHG-2026-0510",
            "rollback_plan_ref": "docs/runbooks/model-rollback.md#v1",
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
