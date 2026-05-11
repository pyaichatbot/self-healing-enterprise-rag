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

from ops.training.job_spec import build_train_job_spec, to_payload
from ops.training.model_registry import ModelRecord, upsert_model_record_backend


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulate an env-driven fine-tuning training job.")
    parser.add_argument("--state-dir", default=".state")
    parser.add_argument("--run-id", default=os.environ.get("SHRAG_FINETUNE_RUN_ID", "train-20260510-001"))
    parser.add_argument("--dataset-id", default=os.environ.get("SHRAG_FINETUNE_DATASET_ID", "engineering-corpus"))
    parser.add_argument("--dataset-version", default=os.environ.get("SHRAG_FINETUNE_DATASET_VERSION", "2026.05.10"))
    parser.add_argument("--output-model-id", default=os.environ.get("SHRAG_FINETUNE_OUTPUT_MODEL_ID", "eng-assistant-v1"))
    args = parser.parse_args()

    state_dir = Path(args.state_dir)
    spec = build_train_job_spec(
        run_id=args.run_id,
        dataset_id=args.dataset_id,
        dataset_version=args.dataset_version,
        output_model_id=args.output_model_id,
    )

    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "finetune-training-job-spec.json").write_text(
        json.dumps(to_payload(spec), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (state_dir / "finetune-training-report.json").write_text(
        json.dumps(
            {
                "run_id": spec.run_id,
                "base_model": spec.base_model,
                "method": spec.method,
                "gpu_type": spec.gpu_type,
                "gpu_count": spec.gpu_count,
                "train_loss": 1.42,
                "eval_passed": True,
                "provenance_mode": os.environ.get("SHRAG_FINETUNE_PROVENANCE_MODE", "simulated"),
                "framework": os.environ.get("SHRAG_FINETUNE_FRAMEWORK", "peft"),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    upsert_model_record_backend(
        state_dir / "model-registry.json",
        ModelRecord(
            model_id=spec.output_model_id,
            run_id=spec.run_id,
            base_model=spec.base_model,
            method=spec.method,
            dataset_id=spec.dataset_id,
            dataset_version=spec.dataset_version,
            status="trained",
            artifact_path=f"{spec.output_path.rstrip('/')}/{spec.output_model_id}",
            approved=False,
            approver="",
            change_ticket="",
            rollback_plan_ref="",
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
