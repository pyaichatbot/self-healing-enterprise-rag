from __future__ import annotations

import json
from pathlib import Path

from tests.bench.erb_report import build_report


def test_build_report_schema_and_gates(tmp_path: Path):
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "erb_eval.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"question_id": "q1", "type": "basic", "correctness": 0.9, "completeness": 0.8, "doc_recall": 1.0}),
                json.dumps({"question_id": "q2", "type": "semantic", "correctness": 0.3, "completeness": 0.2, "doc_recall": 0.0}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    answers = tmp_path / "answers.jsonl"
    answers.write_text(
        "\n".join(
            [
                json.dumps({"question_id": "q1", "expected_doc_ids": ["d1"], "document_ids": ["d1"]}),
                json.dumps({"question_id": "q2", "expected_doc_ids": ["d2"], "document_ids": ["x"]}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = build_report(results_dir=results_dir, answers_file=answers)
    assert "aggregate" in report
    assert "by_type" in report
    assert "gates" in report
    assert report["question_count"] == 2
    assert report["gates"]["recall_above_floor"] is False


def test_build_report_errors_when_eval_output_missing(tmp_path: Path):
    try:
        build_report(results_dir=tmp_path, answers_file=None)
        raise AssertionError("expected FileNotFoundError")
    except FileNotFoundError:
        pass


def test_build_report_supports_metrics_eval_results_questions_schema(tmp_path: Path):
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "metrics_eval_results.json").write_text(
        json.dumps(
            {
                "questions": [
                    {
                        "question_id": "q1",
                        "question_type": "basic",
                        "correctness_score": 1.0,
                        "completeness_score": 0.9,
                        "retrieval_recall": 1.0,
                        "expected_document_ids": ["d1"],
                        "retrieved_document_ids": ["d1", "d9"],
                    },
                    {
                        "question_id": "q2",
                        "question_type": "semantic",
                        "correctness_score": 0.6,
                        "completeness_score": 0.5,
                        "retrieval_recall": 0.0,
                        "expected_document_ids": ["d2"],
                        "retrieved_document_ids": ["dx"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    report = build_report(results_dir=results_dir, answers_file=None)
    assert report["question_count"] == 2
    assert "aggregate" in report
    assert "by_type" in report
    assert "gates" in report
    assert report["by_type"]["basic"]["correctness"] == 1.0
    assert report["aggregate"]["retrieval_recall_at_k"] == 0.5


def test_build_report_supports_eval_jsonl_with_single_object_payload(tmp_path: Path):
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "custom_eval_output.jsonl").write_text(
        json.dumps(
            {
                "questions": [
                    {
                        "question_id": "q1",
                        "question_type": "basic",
                        "correctness_score": 0.8,
                        "completeness_score": 0.7,
                        "retrieval_recall": 1.0,
                        "expected_document_ids": ["d1"],
                        "retrieved_document_ids": ["d1"],
                    },
                    {
                        "question_id": "q2",
                        "question_type": "semantic",
                        "correctness_score": 0.4,
                        "completeness_score": 0.3,
                        "retrieval_recall": 0.0,
                        "expected_document_ids": ["d2"],
                        "retrieved_document_ids": ["x"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    report = build_report(results_dir=results_dir, answers_file=None)
    assert report["question_count"] == 2
    assert report["by_type"]["basic"]["correctness"] == 0.8
    assert report["aggregate"]["retrieval_recall_at_k"] == 0.5
