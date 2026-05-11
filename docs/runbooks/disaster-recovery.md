# Runbook: Disaster Recovery

## Objectives
- RTO: 60 minutes
- RPO: 15 minutes

## Recovery Steps
1. Declare DR event and freeze non-essential changes.
2. Restore control plane and critical data stores from latest verified backup.
3. Re-deploy API + retrieval components using known-good release.
4. Run post-restore health/eval smoke checks.
5. Re-enable traffic gradually and monitor SLO burn.
