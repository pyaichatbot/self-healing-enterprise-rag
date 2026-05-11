from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ChaosRecoveryMetrics:
    recovered: bool
    observed_recovery_seconds: int
    rollback_invoked: bool
    data_loss_events: int


def failure_chaos_gate(
    metrics: ChaosRecoveryMetrics,
    max_recovery_seconds: int = 1800,
) -> tuple[bool, str]:
    if not metrics.recovered:
        return False, "not_recovered"
    if metrics.observed_recovery_seconds > max_recovery_seconds:
        return False, "recovery_slo_breach"
    if not metrics.rollback_invoked:
        return False, "rollback_not_invoked"
    if metrics.data_loss_events > 0:
        return False, "data_loss_detected"
    return True, "pass"
