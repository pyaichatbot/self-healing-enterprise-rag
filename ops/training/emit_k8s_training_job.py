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

from ops.training.job_spec import TrainJobSpec
from ops.training.k8s_job import render_training_job_yaml


def main() -> int:
    parser = argparse.ArgumentParser(description="Render Kubernetes training job from fine-tuning job spec.")
    parser.add_argument("--state-dir", default=".state")
    parser.add_argument("--input", default="finetune-training-job-spec.json")
    parser.add_argument("--output", default="finetune-training-job.yaml")
    args = parser.parse_args()

    state_dir = Path(args.state_dir)
    payload = json.loads((state_dir / args.input).read_text(encoding="utf-8"))
    spec = TrainJobSpec(**payload)
    (state_dir / args.output).write_text(render_training_job_yaml(spec), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
