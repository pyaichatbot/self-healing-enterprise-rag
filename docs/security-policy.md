# Security Policy

## Data Classification
- Public
- Internal
- Confidential
- Restricted (regulated or customer-sensitive data)

## Core Requirements
- Encrypt in transit (TLS 1.2+).
- Encrypt at rest for persistent data stores.
- Use least-privilege IAM for runtime and CI identities.
- Centralized secrets management; no plaintext secrets in git.

## LLM/RAG-Specific Controls
- Prompt injection detection and response filtering.
- Source allowlist and provenance tracking for retrieval.
- Output moderation and PII redaction for sensitive contexts.

## Vulnerability Management
- Critical: remediate within 24h.
- High: remediate within 7 days.
- Medium/Low: triage in sprint planning.

## Incident Handling
- Follow `docs/runbooks/security-incident.md`.
- Preserve logs and forensic evidence before remediation.
