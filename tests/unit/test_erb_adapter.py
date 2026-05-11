from __future__ import annotations

import json
from pathlib import Path

from tests.bench.erb_adapter import load_erb_dataset


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_load_erb_dataset_maps_document_id_to_dataset_uuid_and_builds_query_cases(tmp_path: Path):
    _write_json(
        tmp_path / "documents" / "github" / "docs.json",
        {
            "documents": [
                {"dataset_doc_uuid": "doc-1", "text": "first"},
                {"dataset_doc_uuid": "doc-2", "content": "second"},
            ]
        },
    )
    (tmp_path / "questions.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"question_id": "q1", "question": "What is first?", "expected_doc_ids": ["doc-1"], "type": "basic"}),
                json.dumps({"question_id": "q2", "query": "What is missing?", "expected_doc_ids": ["doc-x"], "type": "semantic"}),
            ]
        ),
        encoding="utf-8",
    )

    dataset = load_erb_dataset(tmp_path, sources=("github",))

    assert len(dataset.documents) == 2
    assert {d.document_id for d in dataset.documents} == {"doc-1", "doc-2"}
    assert {d.dataset_doc_uuid for d in dataset.documents} == {"doc-1", "doc-2"}
    assert len(dataset.questions) == 2
    assert len(dataset.query_cases) == 2
    assert dataset.query_cases[0].question_id == "q1"
    assert dataset.query_cases[0].expected_doc_ids == ["doc-1"]


def test_load_erb_dataset_supports_jsonl_docs_and_segment_fallback(tmp_path: Path):
    source_dir = tmp_path / "documents" / "slack"
    source_dir.mkdir(parents=True)
    (source_dir / "part.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"id": "doc-9", "segments": ["alpha", "beta"]}),
                json.dumps({"id": "doc-10", "text": "ten"}),
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "questions.jsonl").write_text(
        json.dumps({"id": "q-9", "prompt": "Find alpha", "doc_id": "doc-9", "type": "basic"}),
        encoding="utf-8",
    )

    dataset = load_erb_dataset(tmp_path, sources=("slack",))

    assert len(dataset.documents) == 2
    by_id = {d.document_id: d for d in dataset.documents}
    assert by_id["doc-9"].text == "alpha\n\nbeta"
    assert len(dataset.query_cases) == 1
    assert dataset.query_cases[0].expected_doc_ids == ["doc-9"]


def test_load_erb_dataset_raises_on_invalid_questions_jsonl(tmp_path: Path):
    (tmp_path / "questions.jsonl").write_text("{not-json}\n", encoding="utf-8")

    try:
        load_erb_dataset(tmp_path, sources=("arxiv",))
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "Invalid JSONL" in str(exc)


def test_load_erb_dataset_supports_generated_data_sources_layout(tmp_path: Path):
    _write_json(
        tmp_path / "generated_data" / "sources" / "github" / "docs.json",
        {"documents": [{"dataset_doc_uuid": "doc-gd-1", "text": "generated layout doc"}]},
    )
    (tmp_path / "questions.jsonl").write_text(
        json.dumps({"question_id": "q-gd", "question": "Where is generated doc?", "expected_doc_ids": ["doc-gd-1"]}),
        encoding="utf-8",
    )

    dataset = load_erb_dataset(tmp_path, sources=("github",))

    assert len(dataset.documents) == 1
    assert dataset.documents[0].document_id == "doc-gd-1"
    assert dataset.documents[0].source == "github"
    assert len(dataset.query_cases) == 1
    assert dataset.query_cases[0].expected_doc_ids == ["doc-gd-1"]


def test_load_erb_dataset_merges_documents_and_generated_data_layouts(tmp_path: Path):
    _write_json(
        tmp_path / "documents" / "github" / "docs.json",
        {"documents": [{"dataset_doc_uuid": "doc-a", "text": "documents layout"}]},
    )
    _write_json(
        tmp_path / "generated_data" / "sources" / "github" / "docs.json",
        {"documents": [{"dataset_doc_uuid": "doc-b", "text": "generated layout"}]},
    )
    (tmp_path / "questions.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"question_id": "q-a", "question": "A?", "expected_doc_ids": ["doc-a"]}),
                json.dumps({"question_id": "q-b", "question": "B?", "expected_doc_ids": ["doc-b"]}),
            ]
        ),
        encoding="utf-8",
    )

    dataset = load_erb_dataset(tmp_path, sources=("github",))

    assert {doc.document_id for doc in dataset.documents} == {"doc-a", "doc-b"}
