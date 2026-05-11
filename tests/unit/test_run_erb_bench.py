from __future__ import annotations

from pathlib import Path

from tests.bench import run_erb_bench


def test_parse_phases_rejects_unknown():
    try:
        run_erb_bench._parse_phases("ingest,unknown")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_main_runs_selected_phases(tmp_path, monkeypatch):
    erb_dir = tmp_path / "erb"
    erb_dir.mkdir(parents=True)
    state_dir = tmp_path / ".state"
    calls: list[tuple[list[str], str | None]] = []

    def _fake_run(cmd, cwd=None):  # type: ignore[no-untyped-def]
        calls.append((list(cmd), str(cwd) if cwd else None))

    monkeypatch.setattr(run_erb_bench, "_run", _fake_run)

    import sys

    argv_orig = list(sys.argv)
    try:
        sys.argv = [
            "run_erb_bench.py",
            "--erb-dir",
            str(erb_dir),
            "--base-url",
            "http://localhost:8000",
            "--state-dir",
            str(state_dir),
            "--phases",
            "ingest,query",
        ]
        assert run_erb_bench.main() == 0
    finally:
        sys.argv = argv_orig

    assert len(calls) == 2
    assert "ingest_erb.py" in " ".join(calls[0][0])
    assert "run_erb_queries.py" in " ".join(calls[1][0])


def test_run_erb_eval_uses_results_file_then_falls_back_to_output_dir(tmp_path, monkeypatch):
    calls: list[list[str]] = []
    erb_dir = tmp_path / "erb"
    erb_dir.mkdir(parents=True)
    answers_file = tmp_path / "answers.jsonl"
    answers_file.write_text("", encoding="utf-8")
    results_dir = tmp_path / "results"
    results_dir.mkdir(parents=True)

    attempts = {"count": 0}

    def _fake_run(cmd, cwd=None):  # type: ignore[no-untyped-def]
        calls.append(list(cmd))
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("first evaluator invocation failed")

    monkeypatch.setattr(run_erb_bench, "_run", _fake_run)

    run_erb_bench._run_erb_eval(
        erb_dir=erb_dir,
        answers_file=answers_file,
        results_dir=results_dir,
        parallelism=2,
    )

    assert len(calls) == 2
    assert "--results-file" in calls[0]
    assert "--output-dir" in calls[1]
