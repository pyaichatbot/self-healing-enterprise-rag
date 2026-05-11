# API Versioning

## Current Contract
- Header: `X-API-Version`
- Supported value: `2026-05-01`
- Missing header: HTTP 400
- Unsupported version: HTTP 426

## Policy
- Date-based versions with additive-first changes.
- Deprecation window: minimum 90 days for non-critical endpoints.
- Breaking changes require migration notes and dual-read period.

## Rollout
1. Introduce new version in allowlist.
2. Add compatibility tests for old/new versions.
3. Announce migration and monitor adoption metrics.
