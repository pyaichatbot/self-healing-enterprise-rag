from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml  # type: ignore[import-untyped]


@dataclass(slots=True)
class CircuitDecision:
    open: bool
    reason: str
    threshold: float | None = None


def load_circuit_policy(path: str | None = None) -> dict[str, float]:
    policy_path = path or str(Path(__file__).with_name("circuit_policy.yaml"))
    with open(policy_path, "r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    return {
        "error_rate_threshold": float(raw.get("error_rate_threshold", 0.25)),
        "half_open_after_seconds": float(raw.get("half_open_after_seconds", 30.0)),
    }


def circuit_breaker(error_rate: float, threshold: float = 0.25) -> CircuitDecision:
    if error_rate >= threshold:
        return CircuitDecision(open=True, reason="error_rate_high", threshold=threshold)
    return CircuitDecision(open=False, reason="healthy", threshold=threshold)


def circuit_breaker_from_policy(error_rate: float, policy_path: str | None = None) -> CircuitDecision:
    policy = load_circuit_policy(policy_path)
    return circuit_breaker(error_rate, threshold=float(policy["error_rate_threshold"]))
