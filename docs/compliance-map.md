# Compliance Control Map

| Domain | Control Objective | Status | Evidence Placeholder |
|---|---|---|---|
| Access Control | Least privilege and MFA enforcement | Partial | `src/shrag/security/authz.py`, IdP/IAM evidence external |
| Data Protection | Encryption in transit/at rest | Partial | TLS/KMS evidence external, `docs/security-policy.md` |
| Logging/Audit | Immutable audit trails for admin actions | Partial | `src/shrag/security/rtbf.py`, SIEM retention evidence external |
| Change Mgmt | Reviewed and traceable deployments | Implemented in-repo gate | `ops/verification/release_gate.py`, `docs/evidence/latest/manifest.json` |
| Incident Response | Defined response and escalation paths | Implemented | `ops/runbooks/connector-failure.md`, `ops/runbooks/disaster-recovery.md` |
| Vendor Risk | Third-party model/provider assessment | Partial | provider risk register maintained outside repo |
| Fine-tuning Governance | Dataset/training/promotion evidence with rollback | Implemented in-repo gate | `ops/verification/run_finetune_readiness.py`, `.state/finetune-readiness-report.json` |

## Framework Alignment (Initial)
- SOC 2: CC6, CC7, CC8, CC9
- ISO 27001: A.5, A.8, A.12, A.16
- GDPR: Art. 5, 25, 32

## Required Enterprise External Evidence
- IAM policy exports and access-review attestations.
- KMS key policy and storage encryption attestations.
- SIEM immutability/retention evidence.
- Change-ticket and CAB approvals for production promotion.
