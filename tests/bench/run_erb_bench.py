from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

DEFAULT_PHASES = ("ingest", "query", "erb-eval", "report")


def _run(cmd: list[str], *, cwd: Path | None = None) -> None:
    result = subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(cmd)}")


def _parse_phases(raw: str) -> list[str]:
    phases = [p.strip() for p in raw.split(",") if p.strip()]
    unknown = [p for p in phases if p not in DEFAULT_PHASES]
    if unknown:
        raise ValueError(f"Unknown phases: {', '.join(unknown)}")
    return phases


def _run_erb_eval(
    *,
    erb_dir: Path,
    answers_file: Path,
    results_dir: Path,
    parallelism: int,
) -> None:
    results_file = results_dir / "evaluator_output.jsonl"
    cmd_results_file = [
        sys.executable,
        "-m",
        "src.scripts.answer_evaluation.metrics_based_eval",
        "--answers-file",
        str(answers_file.resolve()),
        "--results-file",
        str(results_file.resolve()),
        "--parallelism",
        str(parallelism),
    ]
    try:
        _run(cmd_results_file, cwd=erb_dir)
    except RuntimeError:
        # Backward compatibility with older ERB evaluator versions.
        cmd_output_dir = [
            sys.executable,
            "-m",
            "src.scripts.answer_evaluation.metrics_based_eval",
            "--answers-file",
            str(answers_file.resolve()),
            "--output-dir",
            str(results_dir.resolve()),
            "--parallelism",
            str(parallelism),
        ]
        _run(cmd_output_dir, cwd=erb_dir)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ERB benchmark phases end-to-end.")
    parser.add_argument("--erb-dir", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--state-dir", default=".state")
    parser.add_argument("--tenant-id", default="erb-bench")
    parser.add_argument("--api-version", default="2026-05-01")
    parser.add_argument("--phases", default=",".join(DEFAULT_PHASES))
    parser.add_argument("--sources", help="Optional comma-separated source filter list")
    parser.add_argument("--erb-eval-parallelism", type=int, default=4)
    args = parser.parse_args()

    erb_dir = Path(args.erb_dir)
    if not erb_dir.exists():
        raise FileNotFoundError(f"ERB directory does not exist: {erb_dir}")
    state_dir = Path(args.state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    phases = _parse_phases(args.phases)

    ingest_manifest = state_dir / "erb-ingest-manifest.json"
    answers_file = state_dir / "erb-answers.jsonl"
    results_dir = state_dir / "erb-results"
    report_file = state_dir / "erb-bench-report.json"

    if "ingest" in phases:
        cmd = [
            sys.executable,
            str(Path(__file__).with_name("ingest_erb.py")),
            "--erb-dir",
            str(erb_dir),
            "--base-url",
            args.base_url,
            "--output",
            str(ingest_manifest),
            "--tenant-id",
            args.tenant_id,
        ]
        if args.sources:
            cmd.extend(["--sources", *[s.strip() for s in args.sources.split(",") if s.strip()]])
        _run(cmd)

    if "query" in phases:
        cmd = [
            sys.executable,
            str(Path(__file__).with_name("run_erb_queries.py")),
            "--erb-dir",
            str(erb_dir),
            "--base-url",
            args.base_url,
            "--output",
            str(answers_file),
            "--tenant-id",
            args.tenant_id,
            "--api-version",
            args.api_version,
        ]
        if args.sources:
            cmd.extend(["--sources", args.sources])
        _run(cmd)

    if "erb-eval" in phases:
        results_dir.mkdir(parents=True, exist_ok=True)
        _run_erb_eval(
            erb_dir=erb_dir,
            answers_file=answers_file,
            results_dir=results_dir,
            parallelism=args.erb_eval_parallelism,
        )

    if "report" in phases:
        cmd = [
            sys.executable,
            str(Path(__file__).with_name("erb_report.py")),
            "--results-dir",
            str(results_dir),
            "--answers-file",
            str(answers_file),
            "--output",
            str(report_file),
        ]
        _run(cmd)

    print(report_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
