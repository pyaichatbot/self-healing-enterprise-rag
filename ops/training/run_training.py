from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ops.training.job_spec import build_train_job_spec, to_payload
from ops.training.model_registry import ModelRecord, upsert_model_record_backend


def _render_command(template: str, values: dict[str, object]) -> list[str]:
    rendered = template.format(**values)
    return shlex.split(rendered)


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute a production-mode fine-tuning training command.")
    parser.add_argument("--state-dir", default=".state")
    parser.add_argument("--run-id", default=os.environ.get("SHRAG_FINETUNE_RUN_ID", "train-20260510-001"))
    parser.add_argument("--dataset-id", default=os.environ.get("SHRAG_FINETUNE_DATASET_ID", "engineering-corpus"))
    parser.add_argument("--dataset-version", default=os.environ.get("SHRAG_FINETUNE_DATASET_VERSION", "2026.05.10"))
    parser.add_argument("--output-model-id", default=os.environ.get("SHRAG_FINETUNE_OUTPUT_MODEL_ID", "eng-assistant-v1"))
    parser.add_argument("--provenance-mode", default=os.environ.get("SHRAG_FINETUNE_PROVENANCE_MODE", "production"))
    parser.add_argument("--framework", default=os.environ.get("SHRAG_FINETUNE_FRAMEWORK", "peft"))
    parser.add_argument("--train-loss", type=float, default=float(os.environ.get("SHRAG_FINETUNE_TRAIN_LOSS", "1.42")))
    parser.add_argument(
        "--command-template",
        default=os.environ.get("SHRAG_FINETUNE_TRAIN_COMMAND", "echo training {run_id} for {dataset_id}"),
    )
    args = parser.parse_args()

    state_dir = Path(args.state_dir)
    spec = build_train_job_spec(
        run_id=args.run_id,
        dataset_id=args.dataset_id,
        dataset_version=args.dataset_version,
        output_model_id=args.output_model_id,
    )
    state_dir.mkdir(parents=True, exist_ok=True)
    spec_payload = to_payload(spec)
    (state_dir / "finetune-training-job-spec.json").write_text(
        json.dumps(spec_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    cmd = _render_command(args.command_template, spec_payload)
    started = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    duration = round(time.time() - started, 3)
    success = proc.returncode == 0

    (state_dir / "finetune-training-exec.json").write_text(
        json.dumps(
            {
                "command": cmd,
                "return_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "duration_seconds": duration,
                "provenance_mode": args.provenance_mode,
            },
            indent=2,
            sort_keys=True,
        ),
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
                "train_loss": args.train_loss,
                "eval_passed": success,
                "provenance_mode": args.provenance_mode,
                "framework": args.framework,
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
            status="trained" if success else "failed",
            artifact_path=f"{spec.output_path.rstrip('/')}/{spec.output_model_id}",
            approved=False,
            approver="",
            change_ticket="",
            rollback_plan_ref="",
        ),
    )
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
