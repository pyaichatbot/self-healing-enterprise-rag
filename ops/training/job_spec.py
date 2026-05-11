from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass


@dataclass(slots=True)
class TrainJobSpec:
    run_id: str
    dataset_id: str
    dataset_version: str
    base_model: str
    method: str
    gpu_type: str
    gpu_count: int
    output_model_id: str
    output_path: str


def build_train_job_spec(
    *,
    run_id: str,
    dataset_id: str,
    dataset_version: str,
    output_model_id: str,
    base_model: str | None = None,
    method: str | None = None,
    gpu_type: str | None = None,
    gpu_count: int | None = None,
    output_path: str | None = None,
) -> TrainJobSpec:
    resolved_base_model = base_model or os.environ.get("SHRAG_FINETUNE_BASE_MODEL", "llama3.1-70b-instruct")
    resolved_method = method or os.environ.get("SHRAG_FINETUNE_METHOD", "qlora")
    resolved_gpu_type = gpu_type or os.environ.get("SHRAG_FINETUNE_GPU_TYPE", "H100")
    resolved_gpu_count = gpu_count or int(os.environ.get("SHRAG_FINETUNE_GPU_COUNT", "4"))
    resolved_output_path = output_path or os.environ.get("SHRAG_FINETUNE_OUTPUT_PATH", ".state/models")
    return TrainJobSpec(
        run_id=run_id,
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        base_model=resolved_base_model,
        method=resolved_method,
        gpu_type=resolved_gpu_type,
        gpu_count=resolved_gpu_count,
        output_model_id=output_model_id,
        output_path=resolved_output_path,
    )


def to_payload(spec: TrainJobSpec) -> dict[str, object]:
    return asdict(spec)


def to_json(spec: TrainJobSpec) -> str:
    return json.dumps(to_payload(spec), indent=2, sort_keys=True)
