from __future__ import annotations

from pathlib import Path


def test_makefile_has_erb_targets():
    content = Path("Makefile").read_text(encoding="utf-8")
    assert "ERB_DIR ?= ../EnterpriseRAG-Bench" in content
    assert "SHRAG_BASE_URL ?= http://localhost:8000" in content
    assert "erb-bench-ingest:" in content
    assert "erb-bench-eval:" in content
    assert "erb-bench-report:" in content
    assert "PYTHONPATH=$(CURDIR) python -m tests.bench.ingest_erb" in content
    assert "PYTHONPATH=$(CURDIR) python -m tests.bench.run_erb_queries" in content
    assert "PYTHONPATH=$(CURDIR) python -m tests.bench.erb_report" in content
    assert "--results-file $(CURDIR)/.state/erb-results/evaluator_output.jsonl || \\" in content
    assert "--output-dir $(CURDIR)/.state/erb-results/" in content
    assert "erb-bench: erb-bench-ingest erb-bench-eval erb-bench-report" in content
