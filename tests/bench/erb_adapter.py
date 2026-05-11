from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

DEFAULT_SOURCE_DIRS: tuple[str, ...] = (
    "slack",
    "gmail",
    "linear",
    "google_drive",
    "github",
    "confluence",
    "hubspot",
    "jira",
    "fireflies",
)

_DOC_ID_KEYS: tuple[str, ...] = (
    "dataset_doc_uuid",
    "document_id",
    "doc_id",
    "doc_uuid",
    "uuid",
    "id",
)

_DOC_TEXT_KEYS: tuple[str, ...] = (
    "text",
    "content",
    "document",
    "body",
    "contents",
)

_QUESTION_TEXT_KEYS: tuple[str, ...] = (
    "question",
    "query",
    "question_text",
    "prompt",
)

_QUESTION_DOC_REF_KEYS: tuple[str, ...] = (
    "dataset_doc_uuid",
    "document_id",
    "doc_id",
    "doc_uuid",
    "answer_doc_uuid",
)


@dataclass(frozen=True, slots=True)
class ErbDocument:
    dataset_doc_uuid: str
    document_id: str
    text: str
    source: str
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ErbQuestion:
    question_id: str
    question: str
    question_type: str
    expected_doc_ids: list[str]
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ErbQueryCase:
    question_id: str
    question: str
    question_type: str
    expected_doc_ids: list[str]


@dataclass(frozen=True, slots=True)
class ErbDataset:
    documents: list[ErbDocument]
    questions: list[ErbQuestion]
    query_cases: list[ErbQueryCase]


def _first_non_empty(payload: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _document_text(payload: dict[str, Any]) -> str | None:
    text = _first_non_empty(payload, _DOC_TEXT_KEYS)
    if text:
        return text
    segments = payload.get("segments")
    if isinstance(segments, list):
        parts = [part.strip() for part in segments if isinstance(part, str) and part.strip()]
        if parts:
            return "\n\n".join(parts)
    return None


def _iter_json_objects(path: Path):
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return
    if path.suffix == ".jsonl":
        for i, line in enumerate(raw.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL in {path}:{i}") from exc
            if isinstance(payload, dict):
                yield payload
        return

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}") from exc

    if isinstance(payload, dict):
        if isinstance(payload.get("documents"), list):
            for item in payload["documents"]:
                if isinstance(item, dict):
                    yield item
            return
        yield payload
        return

    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                yield item


def _load_documents(erb_dir: Path, sources: tuple[str, ...]) -> list[ErbDocument]:
    docs: dict[str, ErbDocument] = {}
    roots: list[Path] = []
    documents_root = erb_dir / "documents"
    generated_sources_root = erb_dir / "generated_data" / "sources"
    if documents_root.exists():
        roots.append(documents_root)
    if generated_sources_root.exists():
        roots.append(generated_sources_root)
    if not roots:
        roots.append(erb_dir)

    for source in sources:
        for root in roots:
            source_dir = root / source
            if not source_dir.exists() or not source_dir.is_dir():
                continue
            for pattern in ("*.json", "*.jsonl"):
                for path in sorted(source_dir.rglob(pattern)):
                    for payload in _iter_json_objects(path):
                        dataset_doc_uuid = _first_non_empty(payload, _DOC_ID_KEYS)
                        text = _document_text(payload)
                        if not dataset_doc_uuid or not text:
                            continue

                        # Contract: document_id must map 1:1 to dataset_doc_uuid.
                        document_id = dataset_doc_uuid
                        docs[dataset_doc_uuid] = ErbDocument(
                            dataset_doc_uuid=dataset_doc_uuid,
                            document_id=document_id,
                            text=text,
                            source=source,
                            metadata={"path": str(path.relative_to(root)), "source_type": source},
                        )

    return list(docs.values())


def _load_questions(erb_dir: Path) -> list[ErbQuestion]:
    questions_path = erb_dir / "questions.jsonl"
    if not questions_path.exists():
        raise FileNotFoundError(f"questions.jsonl not found in {erb_dir}")

    questions: list[ErbQuestion] = []
    for idx, payload in enumerate(_iter_json_objects(questions_path), start=1):
        question = _first_non_empty(payload, _QUESTION_TEXT_KEYS)
        if not question:
            continue

        question_id = _first_non_empty(payload, ("question_id", "id")) or f"q-{idx}"
        question_type = str(payload.get("type") or payload.get("question_type") or "unknown")
        expected_raw = payload.get("expected_doc_ids") or payload.get("relevant_document_ids") or []
        expected_doc_ids = [str(v) for v in expected_raw if str(v).strip()]
        single_doc = _first_non_empty(payload, _QUESTION_DOC_REF_KEYS)
        if single_doc and single_doc not in expected_doc_ids:
            expected_doc_ids.append(single_doc)
        questions.append(
            ErbQuestion(
                question_id=question_id,
                question=question,
                question_type=question_type,
                expected_doc_ids=expected_doc_ids,
                metadata={"gold_answer": payload.get("gold_answer"), "answer_facts": payload.get("answer_facts")},
            )
        )
    return questions


def load_erb_dataset(erb_dir: str | Path, sources: tuple[str, ...] | None = None) -> ErbDataset:
    root = Path(erb_dir)
    selected_sources = sources or DEFAULT_SOURCE_DIRS
    documents = _load_documents(root, selected_sources)
    questions = _load_questions(root)

    query_cases: list[ErbQueryCase] = []
    for q in questions:
        query_cases.append(
            ErbQueryCase(
                question_id=q.question_id,
                question=q.question,
                question_type=q.question_type,
                expected_doc_ids=list(q.expected_doc_ids),
            )
        )

    return ErbDataset(documents=documents, questions=questions, query_cases=query_cases)
