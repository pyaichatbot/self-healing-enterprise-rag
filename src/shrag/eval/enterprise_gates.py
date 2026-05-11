from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Mapping

from shrag.settings import Settings


def _runtime_settings() -> Settings:
    return Settings()


def _parse_csv(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _parse_int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_class_thresholds(value: str) -> dict[str, int]:
    thresholds: dict[str, int] = {}
    for token in _parse_csv(value):
        if ":" not in token:
            continue
        name, raw_threshold = token.split(":", 1)
        name = name.strip()
        if not name:
            continue
        thresholds[name] = _parse_int(raw_threshold.strip(), 0)
    return thresholds


@dataclass(frozen=True, slots=True)
class GateDecision:
    allowed: bool
    reason: str


@dataclass(frozen=True, slots=True)
class BucketContract:
    required_tags: frozenset[str]

    @classmethod
    def from_env(cls) -> BucketContract:
        runtime_settings = _runtime_settings()
        return cls(required_tags=frozenset(_parse_csv(runtime_settings.eval_required_bucket_tags)))

    def validate(self, tags: Mapping[str, str]) -> GateDecision:
        missing = sorted(tag for tag in self.required_tags if tag not in tags)
        if missing:
            return GateDecision(allowed=False, reason=f"missing_bucket_tags:{','.join(missing)}")
        return GateDecision(allowed=True, reason="bucket_contract_satisfied")


@dataclass(frozen=True, slots=True)
class CriticalErrorPolicy:
    class_thresholds: Mapping[str, int]
    strict_risk_tiers: frozenset[str]
    protected_threshold: int

    @classmethod
    def from_env(cls) -> CriticalErrorPolicy:
        runtime_settings = _runtime_settings()
        class_thresholds = _parse_class_thresholds(runtime_settings.eval_critical_error_thresholds)
        strict_tiers = frozenset(_parse_csv(runtime_settings.eval_strict_risk_tiers))
        protected_threshold = int(runtime_settings.eval_protected_bucket_threshold)
        return cls(
            class_thresholds=class_thresholds,
            strict_risk_tiers=strict_tiers,
            protected_threshold=protected_threshold,
        )

    def evaluate(self, error_counts: Mapping[str, int], bucket_tags: Mapping[str, str]) -> GateDecision:
        risk_tier = bucket_tags.get("risk_tier", "")
        protected = risk_tier in self.strict_risk_tiers
        for error_class, count in error_counts.items():
            threshold = self.class_thresholds.get(error_class, 0)
            if protected:
                threshold = min(threshold, self.protected_threshold)
            if count > threshold:
                return GateDecision(allowed=False, reason=f"critical_error:{error_class}:{count}>{threshold}")
        return GateDecision(allowed=True, reason="critical_error_policy_pass")


@dataclass(frozen=True, slots=True)
class CanaryPolicy:
    min_sample_size: int
    required_healthy_windows: int
    rollback_error_rate_threshold: float

    @classmethod
    def from_env(cls) -> CanaryPolicy:
        runtime_settings = _runtime_settings()
        return cls(
            min_sample_size=int(runtime_settings.eval_canary_min_sample_size),
            required_healthy_windows=int(runtime_settings.eval_canary_required_healthy_windows),
            rollback_error_rate_threshold=float(runtime_settings.eval_canary_rollback_error_rate),
        )

    def can_promote(self, sample_size: int, healthy_windows: int) -> GateDecision:
        if sample_size < self.min_sample_size:
            return GateDecision(allowed=False, reason="insufficient_canary_sample")
        if healthy_windows < self.required_healthy_windows:
            return GateDecision(allowed=False, reason="insufficient_healthy_windows")
        return GateDecision(allowed=True, reason="canary_promotion_ready")

    def should_rollback(self, error_rate: float, critical_error_count: int) -> GateDecision:
        if critical_error_count > 0:
            return GateDecision(allowed=False, reason="rollback_critical_error")
        if error_rate > self.rollback_error_rate_threshold:
            return GateDecision(allowed=False, reason="rollback_error_rate")
        return GateDecision(allowed=True, reason="canary_healthy")


@dataclass(frozen=True, slots=True)
class JudgeSamplingPolicy:
    min_judge_samples: int
    calibration_window_days: int
    min_agreement: float
    max_stability_delta: float

    @classmethod
    def from_env(cls) -> JudgeSamplingPolicy:
        runtime_settings = _runtime_settings()
        return cls(
            min_judge_samples=int(runtime_settings.eval_judge_min_samples),
            calibration_window_days=int(runtime_settings.eval_judge_calibration_window_days),
            min_agreement=float(runtime_settings.eval_judge_min_agreement),
            max_stability_delta=float(runtime_settings.eval_judge_max_stability_delta),
        )

    def evaluate_calibration(self, sample_count: int, agreement: float, stability_delta: float) -> GateDecision:
        if sample_count < self.min_judge_samples:
            return GateDecision(allowed=False, reason="judge_sample_too_small")
        if agreement < self.min_agreement:
            return GateDecision(allowed=False, reason="judge_agreement_below_threshold")
        if stability_delta > self.max_stability_delta:
            return GateDecision(allowed=False, reason="judge_stability_delta_exceeded")
        return GateDecision(allowed=True, reason="judge_calibration_healthy")


@dataclass(frozen=True, slots=True)
class FlakeControlPolicy:
    deterministic_runs: int
    stochastic_runs: int
    max_relative_stddev: float
    min_quality_median: float

    @classmethod
    def from_env(cls) -> FlakeControlPolicy:
        runtime_settings = _runtime_settings()
        return cls(
            deterministic_runs=int(runtime_settings.eval_flake_deterministic_runs),
            stochastic_runs=int(runtime_settings.eval_flake_stochastic_runs),
            max_relative_stddev=float(runtime_settings.eval_flake_max_rel_stddev),
            min_quality_median=float(runtime_settings.eval_flake_min_quality_median),
        )

    def evaluate(self, scores: list[float]) -> GateDecision:
        if not scores:
            return GateDecision(allowed=False, reason="no_scores")
        med = median(scores)
        mean = sum(scores) / len(scores)
        variance = sum((score - mean) ** 2 for score in scores) / len(scores)
        stddev = variance**0.5
        rel_stddev = stddev / mean if mean > 0 else float("inf")

        if med < self.min_quality_median:
            return GateDecision(allowed=False, reason="median_quality_below_threshold")
        if rel_stddev > self.max_relative_stddev:
            return GateDecision(allowed=False, reason="relative_stddev_exceeded")
        return GateDecision(allowed=True, reason="flake_control_pass")
