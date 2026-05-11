# Connector Failure Runbook

## Detection
- Connector sync lag alert
- Elevated parse or auth failure rate

## Mitigation
1. Identify failing connector scope and tenant impact.
2. Re-authenticate credentials / rotate tokens.
3. Replay failed jobs from checkpoint.
4. Verify recovery with successful sync samples.

## Escalation
- Escalate to connector owner if unresolved after 30 minutes.
