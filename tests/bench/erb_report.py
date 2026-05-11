from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shrag.eval.regression import RegressionGate
from shrag.eval.retrieval_metrics import RetrievalMetricResult, compute_retrieval_metrics

RECALL_FLOOR = 0.75


@dataclass(slots=True)
class _EvalRow:
    question_id: str
    question_type: str
    correctness: float
    completeness: float
    doc_recall: float
    invalid_extra_docs: float
    expected_doc_ids: list[str]
    document_ids: list[str]


def _to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _extract_rows_from_json_payload(payload: object) -> list[dict[str, Any]]:
    if isinstance(payload, list) and all(isinstance(v, dict) for v in payload):
        return payload
    if isinstance(payload, dict):
        questions = payload.get("questions")
        if isinstance(questions, list) and all(isinstance(v, dict) for v in questions):
            return questions
    return []


def _read_rows_with_fallback(path: Path) -> list[dict[str, Any]]:
    try:
        rows = _read_jsonl(path)
        if len(rows) == 1:
            expanded = _extract_rows_from_json_payload(rows[0])
            if expanded:
                return expanded
        return rows
    except json.JSONDecodeError:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = _extract_rows_from_json_payload(payload)
        if rows:
            return rows
        raise


def _find_eval_rows(results_dir: Path) -> list[dict[str, Any]]:
    candidates = (
        results_dir / "erb_eval.jsonl",
        results_dir / "erb-eval.jsonl",
        results_dir / "evaluator_output.jsonl",
        results_dir / "eval.jsonl",
    )
    for path in candidates:
        if path.exists():
            return _read_rows_with_fallback(path)
    matches = sorted(results_dir.glob("*eval*.jsonl"))
    if matches:
        return _read_rows_with_fallback(matches[0])
    matches_json = sorted(results_dir.glob("*.json"))
    for path in matches_json:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = _extract_rows_from_json_payload(payload)
        if rows:
            return rows
    raise FileNotFoundError(f"No ERB evaluator output found in {results_dir}")


def _index_answers(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None or not path.exists():
        return {}
    rows = _read_jsonl(path)
    out: dict[str, dict[str, Any]] = {}
    for i, row in enumerate(rows):
        qid = str(row.get("question_id") or row.get("id") or f"q{i+1}")
        out[qid] = row
    return out


def _normalize_row(row: dict[str, Any], answers: dict[str, dict[str, Any]], idx: int) -> _EvalRow:
    qid = str(row.get("question_id") or row.get("id") or f"q{idx+1}")
    qtype = str(row.get("type") or row.get("question_type") or "unknown")
    correctness = _to_float(
        row.get("correctness"),
        _to_float(row.get("correctness_score"), _to_float(row.get("score"), 0.0)),
    )
    completeness = _to_float(row.get("completeness"), _to_float(row.get("completeness_score"), correctness))
    doc_recall = _to_float(row.get("doc_recall"), _to_float(row.get("retrieval_recall"), 0.0))
    invalid_extra_docs = _to_float(row.get("invalid_extra_docs"), _to_float(row.get("extra_docs_invalid_rate"), 0.0))
    ans = answers.get(qid, {})
    expected_doc_ids = [
        str(v)
        for v in (
            row.get("expected_doc_ids")
            or row.get("expected_document_ids")
            or row.get("relevant_document_ids")
            or ans.get("expected_doc_ids")
            or ans.get("expected_document_ids")
            or ans.get("relevant_document_ids")
            or []
        )
        if str(v).strip()
    ]
    document_ids = [
        str(v)
        for v in (
            ans.get("document_ids")
            or ans.get("retrieved_document_ids")
            or row.get("document_ids")
            or row.get("retrieved_document_ids")
            or []
        )
        if str(v).strip()
    ]
    return _EvalRow(
        question_id=qid,
        question_type=qtype,
        correctness=correctness,
        completeness=completeness,
        doc_recall=doc_recall,
        invalid_extra_docs=invalid_extra_docs,
        expected_doc_ids=expected_doc_ids,
        document_ids=document_ids,
    )


def _avg(metrics: list[float]) -> float:
    if not metrics:
        return 0.0
    return sum(metrics) / len(metrics)


def _retrieval_metric_for_row(row: _EvalRow) -> RetrievalMetricResult:
    return compute_retrieval_metrics(
        retrieved_ids=row.document_ids,
        relevant_ids=row.expected_doc_ids,
        k=max(1, len(row.document_ids)),
    )


def build_report(results_dir: Path, answers_file: Path | None) -> dict[str, Any]:
    eval_rows_raw = _find_eval_rows(results_dir)
    if not eval_rows_raw:
        raise ValueError("ERB evaluator output is empty")
    answers = _index_answers(answers_file)
    rows = [_normalize_row(r, answers, i) for i, r in enumerate(eval_rows_raw)]

    by_type: dict[str, dict[str, float]] = {}
    retrieval: list[RetrievalMetricResult] = []
    correctness_vals: list[float] = []
    completeness_vals: list[float] = []
    doc_recall_vals: list[float] = []
    invalid_extra_vals: list[float] = []

    for row in rows:
        correctness_vals.append(row.correctness)
        completeness_vals.append(row.completeness)
        doc_recall_vals.append(row.doc_recall)
        invalid_extra_vals.append(row.invalid_extra_docs)
        retrieval.append(_retrieval_metric_for_row(row))

        bucket = by_type.setdefault(
            row.question_type,
            {"correctness": 0.0, "completeness": 0.0, "doc_recall": 0.0, "invalid_extra_docs": 0.0, "_count": 0.0},
        )
        bucket["correctness"] += row.correctness
        bucket["completeness"] += row.completeness
        bucket["doc_recall"] += row.doc_recall
        bucket["invalid_extra_docs"] += row.invalid_extra_docs
        bucket["_count"] += 1.0

    for key, bucket in list(by_type.items()):
        count = max(1.0, bucket.pop("_count"))
        by_type[key] = {
            "correctness": bucket["correctness"] / count,
            "completeness": bucket["completeness"] / count,
            "doc_recall": bucket["doc_recall"] / count,
            "invalid_extra_docs": bucket["invalid_extra_docs"] / count,
        }

    retrieval_recall_at_k = _avg([m.recall_at_k for m in retrieval])
    retrieval_mrr = _avg([m.mrr for m in retrieval])
    retrieval_ndcg_at_k = _avg([m.ndcg_at_k for m in retrieval])
    correctness_pct = _avg(correctness_vals)
    completeness_pct = _avg(completeness_vals)
    doc_recall_pct = _avg(doc_recall_vals)

    gate = RegressionGate()
    regression_passed, regression_reason = gate.check(
        quality=(correctness_pct + completeness_pct) / 2.0,
        error_rate_value=max(0.0, 1.0 - doc_recall_pct),
    )
    recall_above_floor = retrieval_recall_at_k >= RECALL_FLOOR
    passed = regression_passed and recall_above_floor

    return {
        "passed": passed,
        "question_count": len(rows),
        "by_type": by_type,
        "aggregate": {
            "correctness_pct": correctness_pct,
            "completeness_pct": completeness_pct,
            "doc_recall_pct": doc_recall_pct,
            "retrieval_recall_at_k": retrieval_recall_at_k,
            "mrr": retrieval_mrr,
            "ndcg_at_k": retrieval_ndcg_at_k,
        },
        "gates": {
            "regression_passed": regression_passed,
            "regression_reason": regression_reason,
            "recall_above_floor": recall_above_floor,
            "recall_floor": RECALL_FLOOR,
        },
        "erb_results_dir": str(results_dir),
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate ERB benchmark report from evaluator output.")
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--answers-file")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    report = build_report(
        results_dir=Path(args.results_dir),
        answers_file=Path(args.answers_file) if args.answers_file else None,
    )
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(out)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
