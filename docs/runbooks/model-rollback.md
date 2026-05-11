# Model Rollback Runbook

## Purpose

Rollback a promoted fine-tuned model when post-deployment gates fail (quality, safety, latency, or compliance).

## Preconditions

- Active incident or change ticket is open.
- Last known-good model id is identified from `.state/model-registry.json` or production model registry.
- Release owner and approver are assigned.

## Procedure

1. Freeze further promotions.
2. Route traffic to last known-good model id.
3. Verify health and quality gates:
   - `make release-gate-strict`
4. Confirm operational SLO recovery and close incident.

## Evidence to Capture

- Incident/change ticket id.
- Model ids involved (failed candidate + restored model).
- Timestamp of cutover and verification checks.
- Gate output payloads from `.state/*` and `docs/evidence/latest/*`.
