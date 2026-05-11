# 500K Scale Blueprint

## Scope
This document defines what is required to credibly claim support for 500K+ documents in enterprise production.

## Capacity Targets
- Corpus: 500,000 mixed documents (text + attachments).
- Bulk ingest throughput: >= 50,000 docs/hour sustained.
- Shared-tenant ingest floor: >= 2,000 docs/hour per active tenant.
- Delta sync SLA: p95 <= 15 minutes from source update to searchable index.
- Query latency at 500K: retrieval p95 < 900ms, end-to-end p95 < 2.5s.

## Partitioning and Sharding
- Partition key: `tenant_id + corpus_namespace`.
- Vector storage:
  - Shared tier: payload-filtered shared collection + strict tenant filters.
  - Isolated tier: dedicated collection per tenant namespace.
- Metadata store indexes:
  - `tenant_id`, `source_id`, `version_id`, `updated_at`, `doc_id`.

## Concurrency and Throughput Model
- Ingestion workers are bounded by provider and embedding budgets.
- Per-tenant fairness enforced by queue and worker concurrency caps.
- Backpressure engages when queue lag or inflight thresholds exceed policy.

## Incremental Reindex and Versioning
- Blue/green index lifecycle:
  - `active_index_version`
  - `candidate_index_version`
- Bulk rebuilds target candidate index only.
- Delta upserts keyed by `source_id + version_id`.
- Cutover only after shadow-read parity and quality gates pass.
- Rollback path restores last healthy active index version.

## Connector Requirements for "Any Source"
- Connector contract must support auth, pagination, checkpoint/resume, delta sync, and normalize.
- ACL and identity metadata are mandatory for enterprise sources.
- Deletes/tombstones must propagate to retrieval index.

## Validation and Failure Testing
Required evidence:
- `tests/scale/ingest_500k.py`: throughput and queue-lag assertions.
- `tests/scale/query_500k.py`: retrieval latency and quality at corpus scale.
- `tests/scale/failure_chaos.py`: outage/recovery and cutover rollback drills.
- `src/shrag/eval/scale_gate.py`: promotion gate for latency/quality thresholds.

Release gates:
- No production promotion if scale gates fail.
- No production promotion if eval regression exceeds allowed budget.
