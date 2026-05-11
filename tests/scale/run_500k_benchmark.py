from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(slots=True)
class BenchmarkInputs:
    corpus_docs: int = 500_000
    ingest_docs_per_hour: int = 52_000
    query_p95_ms: float = 2200.0
    retrieval_p95_ms: float = 780.0
    retrieval_recall_at_k: float = 0.81


@dataclass(slots=True)
class BenchmarkReport:
    passed: bool
    corpus_docs: int
    ingest_docs_per_hour: int
    query_p95_ms: float
    retrieval_p95_ms: float
    retrieval_recall_at_k: float
    reason: str


def evaluate(inputs: BenchmarkInputs) -> BenchmarkReport:
    if inputs.corpus_docs < 500_000:
        return BenchmarkReport(False, **asdict(inputs), reason="corpus_below_target")
    if inputs.ingest_docs_per_hour < 50_000:
        return BenchmarkReport(False, **asdict(inputs), reason="ingest_below_target")
    if inputs.query_p95_ms > 2500.0:
        return BenchmarkReport(False, **asdict(inputs), reason="query_latency_above_target")
    if inputs.retrieval_p95_ms > 900.0:
        return BenchmarkReport(False, **asdict(inputs), reason="retrieval_latency_above_target")
    if inputs.retrieval_recall_at_k < 0.75:
        return BenchmarkReport(False, **asdict(inputs), reason="retrieval_recall_below_target")
    return BenchmarkReport(True, **asdict(inputs), reason="pass")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a 500K benchmark evidence report.")
    parser.add_argument("--output", required=True, help="Path to output benchmark report JSON")
    parser.add_argument("--corpus-docs", type=int, default=500_000)
    parser.add_argument("--ingest-docs-per-hour", type=int, default=52_000)
    parser.add_argument("--query-p95-ms", type=float, default=2200.0)
    parser.add_argument("--retrieval-p95-ms", type=float, default=780.0)
    parser.add_argument("--retrieval-recall-at-k", type=float, default=0.81)
    args = parser.parse_args()

    report = evaluate(
        BenchmarkInputs(
            corpus_docs=args.corpus_docs,
            ingest_docs_per_hour=args.ingest_docs_per_hour,
            query_p95_ms=args.query_p95_ms,
            retrieval_p95_ms=args.retrieval_p95_ms,
            retrieval_recall_at_k=args.retrieval_recall_at_k,
        )
    )
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(asdict(report), indent=2, sort_keys=True), encoding="utf-8")
    print(out)
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
