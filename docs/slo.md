# Service Level Objectives (SLO)

## Availability
- API availability objective: **99.9% monthly**.
- Critical retrieval path objective: **99.5% monthly**.

## Latency
- `/health` p95 < 200ms.
- Retrieval endpoint p95 < 1200ms, p99 < 2500ms.

## Quality
- Golden eval pass rate >= 95% on pinned dataset.
- Hallucination guardrail violations < 1% of sampled responses.

## Error Budget
- 99.9% monthly allows ~43m 49s downtime.
- Burn alerts:
  - Fast burn: >10% budget in 1h.
  - Slow burn: >25% budget in 24h.

## Review Cadence
- Weekly SLO review.
- Monthly objective reset with incident-driven adjustments.
