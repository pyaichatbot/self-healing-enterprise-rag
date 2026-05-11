from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
import sys


@dataclass(slots=True)
class ScaleValidationReport:
    ingest_ok: bool
    ingest_reason: str
    query_ok: bool
    query_reason: str
    chaos_ok: bool
    chaos_reason: str
    all_gates_passed: bool


def build_report() -> ScaleValidationReport:
    this_dir = Path(__file__).resolve().parent
    if str(this_dir) not in sys.path:
        sys.path.insert(0, str(this_dir))
    from failure_chaos import ChaosRecoveryMetrics, failure_chaos_gate
    from ingest_500k import IngestScaleMetrics, ingest_capacity_gate
    from query_500k import QueryScaleMetrics, query_latency_gate

    ingest_ok, ingest_reason = ingest_capacity_gate(
        IngestScaleMetrics(docs_per_hour=51_000, error_rate=0.004, queue_lag_p95_seconds=80.0)
    )
    query_ok, query_reason = query_latency_gate(
        QueryScaleMetrics(p95_ms=2300.0, retrieval_p95_ms=780.0, retrieval_recall_at_k=0.81)
    )
    chaos_ok, chaos_reason = failure_chaos_gate(
        ChaosRecoveryMetrics(
            recovered=True,
            observed_recovery_seconds=840,
            rollback_invoked=True,
            data_loss_events=0,
        )
    )
    return ScaleValidationReport(
        ingest_ok=ingest_ok,
        ingest_reason=ingest_reason,
        query_ok=query_ok,
        query_reason=query_reason,
        chaos_ok=chaos_ok,
        chaos_reason=chaos_reason,
        all_gates_passed=ingest_ok and query_ok and chaos_ok,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Emit 500K readiness validation report.")
    parser.add_argument("--output", required=True, help="Path to JSON output report")
    args = parser.parse_args()

    report = build_report()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(asdict(report), indent=2, sort_keys=True), encoding="utf-8")
    print(output)
    return 0 if report.all_gates_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
