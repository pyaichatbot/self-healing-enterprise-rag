SHELL := /bin/bash

.PHONY: help lint type test test-unit test-integration test-eval test-load test-scale test-coverage scale-report benchmark-500k dr-drill connector-evidence connector-evidence-strict connector-evidence-strict-mock finetune-dataset finetune-dataset-simulated finetune-train finetune-train-simulated finetune-render-job finetune-promote-simulated finetune-readiness finetune-readiness-production-check finetune-readiness-simulated enterprise-readiness-audit enterprise-readiness-audit-strict erb-bench-ingest erb-bench-eval erb-bench-report erb-bench release-gate release-gate-strict publish-evidence plan01-audit plan01-audit-strict ci local-ci-gate up down

help:
	@echo "Targets: lint type test test-coverage local-ci-gate scale-report benchmark-500k dr-drill connector-evidence connector-evidence-strict connector-evidence-strict-mock finetune-dataset finetune-dataset-simulated finetune-train finetune-train-simulated finetune-render-job finetune-promote-simulated finetune-readiness finetune-readiness-production-check finetune-readiness-simulated enterprise-readiness-audit enterprise-readiness-audit-strict erb-bench-ingest erb-bench-eval erb-bench-report erb-bench release-gate release-gate-strict publish-evidence plan01-audit plan01-audit-strict ci up down"

ERB_DIR ?= ../EnterpriseRAG-Bench
SHRAG_BASE_URL ?= http://localhost:8000

lint:
	ruff check src tests

type:
	python -m mypy src

test: test-unit test-integration test-eval test-load test-scale

test-unit:
	pytest -q tests/unit

test-integration:
	pytest -q tests/integration

test-eval:
	pytest -q tests/eval

test-load:
	pytest -q tests/load

test-scale:
	pytest -q tests/scale

test-coverage:
	@if [ -z "$$SHRAG_COVERAGE_MIN" ]; then \
		COVERAGE_MIN=85; \
	else \
		COVERAGE_MIN=$$SHRAG_COVERAGE_MIN; \
	fi; \
	if [ -z "$$SHRAG_COVERAGE_TARGETS" ]; then \
		COVERAGE_TARGETS="shrag.api.backpressure shrag.api.rate_limit shrag.api.routes shrag.retrieve.pipeline shrag.retrieve.rerank shrag.retrieve.router shrag.retrieve.web_fallback shrag.eval.enterprise_gates shrag.eval.metrics_runner shrag.eval.scale_gate shrag.eval.stage_metrics shrag.security.policy shrag.security.guardrails shrag.security.injection shrag.observe.hooks shrag.ingest.pipeline"; \
	else \
		COVERAGE_TARGETS="$$SHRAG_COVERAGE_TARGETS"; \
	fi; \
	if [ $$COVERAGE_MIN -lt 85 ] || [ $$COVERAGE_MIN -gt 90 ]; then \
		echo "SHRAG_COVERAGE_MIN must be between 85 and 90 inclusive (got $$COVERAGE_MIN)"; \
		exit 2; \
	fi; \
	COV_ARGS=""; \
	for target in $$COVERAGE_TARGETS; do \
		COV_ARGS="$$COV_ARGS --cov=$$target"; \
	done; \
	pytest -q tests $$COV_ARGS --cov-report=term-missing:skip-covered --cov-fail-under=$$COVERAGE_MIN

scale-report:
	python tests/scale/run_500k_validation.py --output .state/scale-500k-report.json

benchmark-500k:
	python tests/scale/run_500k_benchmark.py --output .state/benchmark-500k-report.json

dr-drill:
	python ops/drills/failover_drill.py --output .state/dr-failover-report.json --rollback-verified --readyz-healthy-after-cutover

connector-evidence:
	python ops/verification/run_connector_evidence.py --output .state/connector-evidence-report.json

connector-evidence-strict:
	python ops/verification/run_connector_evidence.py --output .state/connector-evidence-report-strict.json --require-no-skips --min-passed 1

connector-evidence-strict-mock:
	python ops/verification/run_connector_evidence_strict_simulated.py --output .state/connector-evidence-report-strict.json

finetune-dataset:
	python ops/training/run_dataset_prep.py --state-dir .state

finetune-dataset-simulated:
	python ops/training/run_dataset_prep_simulated.py --state-dir .state

finetune-train:
	python ops/training/run_training.py --state-dir .state

finetune-train-simulated:
	python ops/training/run_training_simulated.py --state-dir .state

finetune-render-job:
	python ops/training/emit_k8s_training_job.py --state-dir .state --input finetune-training-job-spec.json --output finetune-training-job.yaml

finetune-promote-simulated:
	python ops/training/run_promotion.py --state-dir .state --model-id eng-assistant-v1 --approver ml-governance-board --change-ticket CHG-2026-0510 --rollback-plan-ref docs/runbooks/model-rollback.md#v1

finetune-readiness:
	python ops/verification/run_finetune_readiness.py --state-dir .state --output .state/finetune-readiness-report.json

finetune-readiness-production-check:
	python ops/verification/run_finetune_readiness.py --state-dir .state --output .state/finetune-readiness-report.json --require-non-simulated

finetune-readiness-simulated: finetune-dataset-simulated finetune-train-simulated finetune-render-job finetune-promote-simulated finetune-readiness

release-gate:
	python ops/verification/release_gate.py

release-gate-strict:
	python ops/verification/release_gate.py --strict

publish-evidence:
	python ops/verification/publish_evidence_bundle.py --state-dir .state --out-dir docs/evidence

plan01-audit:
	python ops/verification/plan01_audit.py --output .state/plan01-audit.json

plan01-audit-strict:
	python ops/verification/plan01_audit.py --output .state/plan01-audit-strict.json --strict-external

enterprise-readiness-audit:
	python ops/verification/run_enterprise_readiness_audit.py --output .state/enterprise-readiness-audit.json

enterprise-readiness-audit-strict:
	python ops/verification/run_enterprise_readiness_audit.py --output .state/enterprise-readiness-audit-strict.json --strict-external

erb-bench-ingest:
	PYTHONPATH=$(CURDIR) python -m tests.bench.ingest_erb \
	  --erb-dir $(ERB_DIR) \
	  --base-url $(SHRAG_BASE_URL) \
	  --output .state/erb-ingest-manifest.json

erb-bench-eval:
	PYTHONPATH=$(CURDIR) python -m tests.bench.run_erb_queries \
	  --erb-dir $(ERB_DIR) \
	  --base-url $(SHRAG_BASE_URL) \
	  --output .state/erb-answers.jsonl
	cd $(ERB_DIR) && python -m src.scripts.answer_evaluation.metrics_based_eval \
	  --answers-file $(CURDIR)/.state/erb-answers.jsonl \
	  --results-file $(CURDIR)/.state/erb-results/evaluator_output.jsonl || \
	(cd $(ERB_DIR) && python -m src.scripts.answer_evaluation.metrics_based_eval \
	  --answers-file $(CURDIR)/.state/erb-answers.jsonl \
	  --output-dir $(CURDIR)/.state/erb-results/)

erb-bench-report:
	PYTHONPATH=$(CURDIR) python -m tests.bench.erb_report \
	  --results-dir .state/erb-results/ \
	  --answers-file .state/erb-answers.jsonl \
	  --output .state/erb-bench-report.json

erb-bench: erb-bench-ingest erb-bench-eval erb-bench-report

ci: lint type test

local-ci-gate: lint test-coverage

up:
	docker compose up -d

down:
	docker compose down
