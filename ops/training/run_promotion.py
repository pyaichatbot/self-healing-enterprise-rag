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

from ops.training.model_registry import ModelRecord, get_model_record_backend, upsert_model_record_backend


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"missing_env:{name}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote trained model with governance metadata.")
    parser.add_argument("--state-dir", default=".state")
    parser.add_argument("--model-id", default=os.environ.get("SHRAG_FINETUNE_OUTPUT_MODEL_ID", "eng-assistant-v1"))
    parser.add_argument("--approver", default=os.environ.get("SHRAG_FINETUNE_APPROVER", ""))
    parser.add_argument("--change-ticket", default=os.environ.get("SHRAG_FINETUNE_CHANGE_TICKET", ""))
    parser.add_argument("--rollback-plan-ref", default=os.environ.get("SHRAG_FINETUNE_ROLLBACK_PLAN_REF", ""))
    args = parser.parse_args()

    state_dir = Path(args.state_dir)
    model_id = args.model_id
    approver = args.approver or _required_env("SHRAG_FINETUNE_APPROVER")
    change_ticket = args.change_ticket or _required_env("SHRAG_FINETUNE_CHANGE_TICKET")
    rollback_plan_ref = args.rollback_plan_ref or _required_env("SHRAG_FINETUNE_ROLLBACK_PLAN_REF")

    registry_path = state_dir / "model-registry.json"
    record = get_model_record_backend(registry_path, model_id)
    if record is None:
        raise FileNotFoundError(f"model_not_found:{model_id}")

    promoted = ModelRecord(
        model_id=record.model_id,
        run_id=record.run_id,
        base_model=record.base_model,
        method=record.method,
        dataset_id=record.dataset_id,
        dataset_version=record.dataset_version,
        status="promoted",
        artifact_path=record.artifact_path,
        approved=True,
        approver=approver,
        change_ticket=change_ticket,
        rollback_plan_ref=rollback_plan_ref,
    )
    upsert_model_record_backend(registry_path, promoted)
    (state_dir / "finetune-promotion-report.json").write_text(
        json.dumps(
            {
                "candidate_model_id": promoted.model_id,
                "approved": True,
                "approver": approver,
                "change_ticket": change_ticket,
                "rollback_plan_ref": rollback_plan_ref,
                "provenance_mode": "simulated" if os.environ.get("SHRAG_FINETUNE_PROVENANCE_MODE", "simulated") == "simulated" else "production",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
