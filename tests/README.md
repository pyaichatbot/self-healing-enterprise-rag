# Test Suite Skeleton

## Categories
- `unit/`: fast deterministic tests (health contract smoke included)
- `integration/`: app + dependency behavior
- `eval/`: golden dataset quality checks
- `load/`: throughput and latency envelope checks
- `scale/`: horizontal scaling and resilience checks

## Local Run
- `make test`
- `make test-coverage` (enforces `SHRAG_COVERAGE_MIN`, default `85`, allowed range `85..90`)
- `make local-ci-gate` (lint + mypy + coverage-gated tests)
- `make test-unit`
- `make scale-report` (writes `.state/scale-500k-report.json`)
- `make benchmark-500k` (writes `.state/benchmark-500k-report.json`)
- `make dr-drill` (writes `.state/dr-failover-report.json`)
- `make connector-evidence` (writes `.state/connector-evidence-report.json`)
- `make connector-evidence-strict` (fails on skips; requires live pass evidence)
- `make connector-evidence-strict-mock` (runs strict evidence against local mock provider)
- `make publish-evidence` (copies reports into `docs/evidence/latest` + timestamp snapshot)
- `make plan01-audit` (non-strict checklist snapshot) / `make plan01-audit-strict` (fails on unresolved live evidence)
- `make enterprise-readiness-audit` (consolidated RAG + fine-tune readiness snapshot)
- `make enterprise-readiness-audit-strict` (fails when strict external/live evidence requirements are unmet)
- `make erb-bench-ingest ERB_DIR=<path>` (ingests ERB documents into `/docs`, writes `.state/erb-ingest-manifest.json`)
- `make erb-bench-eval ERB_DIR=<path>` (runs `/query` for ERB questions, writes `.state/erb-answers.jsonl`, executes ERB evaluator into `.state/erb-results/`)
- `make erb-bench-report` (builds `.state/erb-bench-report.json`)
- `make erb-bench ERB_DIR=<path>` (full ingest + eval + report chain)
