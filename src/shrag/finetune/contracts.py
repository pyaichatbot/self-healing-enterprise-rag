from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class DatasetArtifact:
    dataset_id: str
    dataset_version: str
    source_systems: tuple[str, ...]
    pii_scrubbed: bool
    license_policy_passed: bool
    record_count: int
    provenance_mode: str = "unknown"

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "DatasetArtifact":
        systems = payload.get("source_systems") or ()
        if isinstance(systems, list):
            source_systems = tuple(str(v) for v in systems)
        elif isinstance(systems, tuple):
            source_systems = tuple(str(v) for v in systems)
        else:
            source_systems = ()
        return cls(
            dataset_id=str(payload.get("dataset_id", "")),
            dataset_version=str(payload.get("dataset_version", "")),
            source_systems=source_systems,
            pii_scrubbed=bool(payload.get("pii_scrubbed") is True),
            license_policy_passed=bool(payload.get("license_policy_passed") is True),
            record_count=int(payload.get("record_count", 0) or 0),
            provenance_mode=str(payload.get("provenance_mode", "unknown")),
        )


@dataclass(slots=True)
class TrainingRunArtifact:
    run_id: str
    base_model: str
    method: str
    gpu_type: str
    gpu_count: int
    train_loss: float
    eval_passed: bool
    provenance_mode: str = "unknown"
    framework: str = "unknown"

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "TrainingRunArtifact":
        return cls(
            run_id=str(payload.get("run_id", "")),
            base_model=str(payload.get("base_model", "")),
            method=str(payload.get("method", "")),
            gpu_type=str(payload.get("gpu_type", "")),
            gpu_count=int(payload.get("gpu_count", 0) or 0),
            train_loss=float(payload.get("train_loss", 0.0) or 0.0),
            eval_passed=bool(payload.get("eval_passed") is True),
            provenance_mode=str(payload.get("provenance_mode", "unknown")),
            framework=str(payload.get("framework", "unknown")),
        )


@dataclass(slots=True)
class PromotionDecision:
    candidate_model_id: str
    approved: bool
    approver: str
    change_ticket: str
    rollback_plan_ref: str
    provenance_mode: str = "unknown"

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "PromotionDecision":
        return cls(
            candidate_model_id=str(payload.get("candidate_model_id", "")),
            approved=bool(payload.get("approved") is True),
            approver=str(payload.get("approver", "")),
            change_ticket=str(payload.get("change_ticket", "")),
            rollback_plan_ref=str(payload.get("rollback_plan_ref", "")),
            provenance_mode=str(payload.get("provenance_mode", "unknown")),
        )


def validate_artifact_bundle(
    dataset: DatasetArtifact,
    training: TrainingRunArtifact,
    promotion: PromotionDecision,
    *,
    require_h100: bool = True,
    require_non_simulated: bool = False,
) -> tuple[bool, list[str]]:
    failures: list[str] = []

    if not dataset.dataset_id or not dataset.dataset_version:
        failures.append("dataset_identity_missing")
    if dataset.record_count <= 0:
        failures.append("dataset_empty")
    if not dataset.pii_scrubbed:
        failures.append("dataset_pii_scrub_not_verified")
    if not dataset.license_policy_passed:
        failures.append("dataset_license_policy_failed")
    if not dataset.source_systems:
        failures.append("dataset_source_systems_missing")
    if require_non_simulated and dataset.provenance_mode.lower() == "simulated":
        failures.append("dataset_simulated_not_allowed")

    if not training.run_id or not training.base_model:
        failures.append("training_identity_missing")
    if training.gpu_count <= 0:
        failures.append("training_gpu_count_invalid")
    if require_h100 and training.gpu_type.upper() != "H100":
        failures.append("training_gpu_type_not_h100")
    if training.method.lower() not in {"lora", "qlora", "sft"}:
        failures.append("training_method_unsupported")
    if not training.eval_passed:
        failures.append("training_eval_not_passed")
    if training.framework.lower() not in {"peft", "trl", "deepspeed", "accelerate"}:
        failures.append("training_framework_unsupported")
    if require_non_simulated and training.provenance_mode.lower() == "simulated":
        failures.append("training_simulated_not_allowed")

    if not promotion.candidate_model_id:
        failures.append("promotion_candidate_missing")
    if not promotion.approved:
        failures.append("promotion_not_approved")
    if not promotion.approver:
        failures.append("promotion_approver_missing")
    if not promotion.change_ticket:
        failures.append("promotion_change_ticket_missing")
    if not promotion.rollback_plan_ref:
        failures.append("promotion_rollback_plan_missing")
    if require_non_simulated and promotion.provenance_mode.lower() == "simulated":
        failures.append("promotion_simulated_not_allowed")

    return len(failures) == 0, failures
