from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def _load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"missing_report:{path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def _is_pass(payload: dict[str, object]) -> bool:
    return bool(payload.get("passed") is True or payload.get("all_gates_passed") is True)


def run_gate(*, strict: bool) -> tuple[bool, list[str]]:
    failures: list[str] = []
    scale: dict[str, object] = {}
    benchmark: dict[str, object] = {}
    dr: dict[str, object] = {}
    connector_relaxed: dict[str, object] = {}
    finetune: dict[str, object] = {}
    # Env-driven override for deployment lanes that require fine-tuning evidence.
    require_finetune = os.environ.get("SHRAG_RELEASE_REQUIRE_FINETUNE_REPORT", "false").lower() == "true" or strict
    try:
        scale = _load_json(Path(".state/scale-500k-report.json"))
    except FileNotFoundError as exc:
        failures.append(str(exc))
    try:
        benchmark = _load_json(Path(".state/benchmark-500k-report.json"))
    except FileNotFoundError as exc:
        failures.append(str(exc))
    try:
        dr = _load_json(Path(".state/dr-failover-report.json"))
    except FileNotFoundError as exc:
        failures.append(str(exc))
    try:
        connector_relaxed = _load_json(Path(".state/connector-evidence-report.json"))
    except FileNotFoundError as exc:
        failures.append(str(exc))

    if scale and not _is_pass(scale):
        failures.append("scale_report_failed")
    if benchmark and not _is_pass(benchmark):
        failures.append("benchmark_report_failed")
    if dr and not _is_pass(dr):
        failures.append("dr_report_failed")
    if connector_relaxed and not _is_pass(connector_relaxed):
        failures.append("connector_report_failed")
    if require_finetune:
        try:
            finetune = _load_json(Path(".state/finetune-readiness-report.json"))
        except FileNotFoundError as exc:
            failures.append(str(exc))
        if finetune and not _is_pass(finetune):
            failures.append("finetune_readiness_failed")
        if strict and finetune:
            details = finetune.get("details")
            require_non_simulated = False
            if isinstance(details, dict):
                require_non_simulated = bool(details.get("require_non_simulated") is True)
            if not require_non_simulated:
                failures.append("finetune_non_simulated_check_not_enforced")
        if strict:
            if not Path(".state/finetune-training-job.yaml").exists():
                failures.append("missing_report:finetune-training-job.yaml")
            if not Path(".state/finetune-training-exec.json").exists():
                failures.append("missing_report:finetune-training-exec.json")

    if strict:
        connector_strict: dict[str, object] = {}
        require_live_connector = os.environ.get("SHRAG_RELEASE_REQUIRE_LIVE_CONNECTOR_EVIDENCE", "true").lower() == "true"
        try:
            connector_strict = _load_json(Path(".state/connector-evidence-report-strict.json"))
        except FileNotFoundError as exc:
            failures.append(str(exc))
        if connector_strict and not _is_pass(connector_strict):
            failures.append("connector_strict_failed")
        if require_live_connector and connector_strict:
            if str(connector_strict.get("evidence_mode", "unknown")).lower() != "live":
                failures.append("connector_strict_not_live")

    return len(failures) == 0, failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate release evidence reports.")
    parser.add_argument("--strict", action="store_true", default=False, help="Require strict connector evidence report")
    args = parser.parse_args()
    ok, failures = run_gate(strict=args.strict)
    payload = {"passed": ok, "strict": args.strict, "failures": failures}
    print(json.dumps(payload, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
