from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class HAStatus:
    ready: bool
    serving_region: str
    role: str
    reason: str


def evaluate_ha_readiness(
    *,
    region: str,
    mode: str,
    primary_region: str,
    primary_region_healthy: bool,
    replication_lag_seconds: int,
    max_replication_lag_seconds: int,
) -> HAStatus:
    if mode == "single":
        return HAStatus(ready=True, serving_region=region, role="single", reason="single_mode")

    role = "primary" if region == primary_region else "secondary"
    if role == "primary":
        return HAStatus(
            ready=primary_region_healthy,
            serving_region=region,
            role=role,
            reason="primary_healthy" if primary_region_healthy else "primary_unhealthy",
        )

    if not primary_region_healthy and replication_lag_seconds <= max_replication_lag_seconds:
        return HAStatus(ready=True, serving_region=region, role=role, reason="failover_serving")
    if replication_lag_seconds > max_replication_lag_seconds:
        return HAStatus(ready=False, serving_region=region, role=role, reason="replication_lag_exceeded")
    return HAStatus(ready=False, serving_region=region, role=role, reason="standby_only")
