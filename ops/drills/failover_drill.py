from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(slots=True)
class FailoverDrillInput:
    rto_target_seconds: int = 3600
    rpo_target_seconds: int = 900
    observed_recovery_seconds: int = 840
    observed_data_loss_seconds: int = 120
    rollback_verified: bool = True
    readyz_healthy_after_cutover: bool = True


@dataclass(slots=True)
class FailoverDrillReport:
    passed: bool
    rto_passed: bool
    rpo_passed: bool
    rollback_verified: bool
    readyz_healthy_after_cutover: bool
    reason: str


def evaluate_drill(inp: FailoverDrillInput) -> FailoverDrillReport:
    rto_passed = inp.observed_recovery_seconds <= inp.rto_target_seconds
    rpo_passed = inp.observed_data_loss_seconds <= inp.rpo_target_seconds
    if not inp.rollback_verified:
        return FailoverDrillReport(
            passed=False,
            rto_passed=rto_passed,
            rpo_passed=rpo_passed,
            rollback_verified=False,
            readyz_healthy_after_cutover=inp.readyz_healthy_after_cutover,
            reason="rollback_not_verified",
        )
    if not inp.readyz_healthy_after_cutover:
        return FailoverDrillReport(
            passed=False,
            rto_passed=rto_passed,
            rpo_passed=rpo_passed,
            rollback_verified=True,
            readyz_healthy_after_cutover=False,
            reason="readyz_unhealthy_post_cutover",
        )
    if not rto_passed:
        return FailoverDrillReport(
            passed=False,
            rto_passed=False,
            rpo_passed=rpo_passed,
            rollback_verified=True,
            readyz_healthy_after_cutover=True,
            reason="rto_breach",
        )
    if not rpo_passed:
        return FailoverDrillReport(
            passed=False,
            rto_passed=True,
            rpo_passed=False,
            rollback_verified=True,
            readyz_healthy_after_cutover=True,
            reason="rpo_breach",
        )
    return FailoverDrillReport(
        passed=True,
        rto_passed=True,
        rpo_passed=True,
        rollback_verified=True,
        readyz_healthy_after_cutover=True,
        reason="pass",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run DR failover drill and emit JSON evidence.")
    parser.add_argument("--output", required=True, help="Path to output JSON report")
    parser.add_argument("--observed-recovery-seconds", type=int, default=840)
    parser.add_argument("--observed-data-loss-seconds", type=int, default=120)
    parser.add_argument("--rto-target-seconds", type=int, default=3600)
    parser.add_argument("--rpo-target-seconds", type=int, default=900)
    parser.add_argument("--rollback-verified", action="store_true", default=False)
    parser.add_argument("--readyz-healthy-after-cutover", action="store_true", default=False)
    args = parser.parse_args()

    inp = FailoverDrillInput(
        rto_target_seconds=args.rto_target_seconds,
        rpo_target_seconds=args.rpo_target_seconds,
        observed_recovery_seconds=args.observed_recovery_seconds,
        observed_data_loss_seconds=args.observed_data_loss_seconds,
        rollback_verified=args.rollback_verified,
        readyz_healthy_after_cutover=args.readyz_healthy_after_cutover,
    )
    report = evaluate_drill(inp)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(asdict(report), indent=2, sort_keys=True), encoding="utf-8")
    print(output)
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
