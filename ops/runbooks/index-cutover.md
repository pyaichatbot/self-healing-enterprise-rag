# Index Cutover Runbook

## Preconditions
- New index fully built and validated.
- Golden eval and regression checks passed.
- Rollback pointer to previous index ready.

## Cutover Steps
1. Enable shadow reads from new index.
2. Compare retrieval quality and latency for canary traffic.
3. Promote to full read traffic when thresholds pass.
4. Keep rollback window open for at least 24h.
