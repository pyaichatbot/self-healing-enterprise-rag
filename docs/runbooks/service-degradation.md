# Runbook: Service Degradation

## Trigger
- Elevated p95/p99 latency
- Increased 5xx rate
- SLO burn alerts firing

## Triage
1. Validate alert scope (global vs. single dependency).
2. Check recent deploys and config changes.
3. Inspect retrieval store, model provider, and queue saturation.

## Mitigation
1. Enable degraded mode (smaller context / cheaper model fallback).
2. Apply traffic shaping and rate limiting.
3. Roll back latest risky deploy if correlated.

## Exit Criteria
- Error rate and latency return within SLO thresholds.
- No active fast-burn alerts for 30 minutes.
