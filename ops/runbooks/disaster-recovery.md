# Disaster Recovery Runbook

## Scope
Recovery procedures for metadata/state and vector index after partial or regional failure.

## Targets
- RPO: 15 minutes
- RTO: 60 minutes

## Recovery Order
1. Restore control-plane dependencies (Postgres/Redis/state DB equivalent).
2. Restore vector index snapshot for impacted tenant namespaces.
3. Rebuild missing deltas via connector checkpoint replay.
4. Run scale/health smoke checks before traffic restore.

## Validation
- `GET /readyz` returns healthy checks.
- `tests/scale/failure_chaos.py` recovery scenario passes.
- Golden regression gate passes before full traffic cutback.
- `make dr-drill` produces `.state/dr-failover-report.json` with `passed=true`.
