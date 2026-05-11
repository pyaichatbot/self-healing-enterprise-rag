from __future__ import annotations

import json
from pathlib import Path

from shrag.finetune.contracts import (
    DatasetArtifact,
    PromotionDecision,
    TrainingRunArtifact,
    validate_artifact_bundle,
)


def _load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"missing_report:{path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def run_finetune_gate(
    *,
    state_dir: Path,
    require_h100: bool = True,
    require_non_simulated: bool = False,
) -> tuple[bool, list[str], dict[str, object]]:
    failures: list[str] = []

    dataset_payload: dict[str, object] = {}
    training_payload: dict[str, object] = {}
    promotion_payload: dict[str, object] = {}

    try:
        dataset_payload = _load_json(state_dir / "finetune-dataset-report.json")
    except FileNotFoundError as exc:
        failures.append(str(exc))
    try:
        training_payload = _load_json(state_dir / "finetune-training-report.json")
    except FileNotFoundError as exc:
        failures.append(str(exc))
    try:
        promotion_payload = _load_json(state_dir / "finetune-promotion-report.json")
    except FileNotFoundError as exc:
        failures.append(str(exc))

    details: dict[str, object] = {
        "require_h100": require_h100,
        "state_dir": str(state_dir),
    }

    if not failures:
        dataset = DatasetArtifact.from_dict(dataset_payload)
        training = TrainingRunArtifact.from_dict(training_payload)
        promotion = PromotionDecision.from_dict(promotion_payload)
        ok, artifact_failures = validate_artifact_bundle(
            dataset,
            training,
            promotion,
            require_h100=require_h100,
            require_non_simulated=require_non_simulated,
        )
        failures.extend(artifact_failures)
        details["dataset_id"] = dataset.dataset_id
        details["dataset_version"] = dataset.dataset_version
        details["run_id"] = training.run_id
        details["candidate_model_id"] = promotion.candidate_model_id
        details["validation_passed"] = ok
        details["require_non_simulated"] = require_non_simulated
        if require_non_simulated:
            try:
                exec_payload = _load_json(state_dir / "finetune-training-exec.json")
            except FileNotFoundError as exc:
                failures.append(str(exc))
                exec_payload = {}
            if exec_payload:
                raw_return_code = exec_payload.get("return_code", 1)
                try:
                    return_code = int(raw_return_code)  # type: ignore[arg-type]
                except Exception:
                    return_code = 1
                mode = str(exec_payload.get("provenance_mode", "unknown"))
                if return_code != 0:
                    failures.append("training_exec_failed")
                if mode.lower() == "simulated":
                    failures.append("training_exec_simulated_not_allowed")
                details["training_exec_return_code"] = return_code
                details["training_exec_mode"] = mode

    return len(failures) == 0, failures, details
