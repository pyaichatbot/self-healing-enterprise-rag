from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Mapping, Protocol, Sequence

from shrag.ingest.chunker import chunk_document
from shrag.ingest.embed import embed_text
from shrag.ingest.loaders import parse_attachment
from shrag.ingest.store import get_store
from shrag.observe.models import RequestContext
from shrag.observe.models import RetrievedChunk
from shrag.settings import settings


@dataclass(slots=True)
class Attachment:
    name: str
    content: bytes
    content_type: str | None = None


@dataclass(slots=True)
class IngestDocument:
    document_id: str
    text: str
    metadata: Mapping[str, object] = field(default_factory=dict)
    attachments: tuple[Attachment, ...] = ()


@dataclass(slots=True)
class IngestResult:
    indexed_ids: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class IngestStage(Protocol):
    def ingest(self, context: RequestContext, documents: Sequence[IngestDocument]) -> IngestResult: ...


class BaselineIngestStage:
    """Deterministic baseline ingest stage with simple dedupe and warnings."""

    def ingest(self, context: RequestContext, documents: Sequence[IngestDocument]) -> IngestResult:
        store = get_store()
        tenant_id = str(context.metadata.get("tenant_id", "public"))
        attachment_template_map = _attachment_template_map()
        seen: set[str] = set()
        indexed: list[str] = []
        warnings: list[str] = []
        for doc in documents:
            if doc.document_id in seen:
                warnings.append(f"duplicate:{doc.document_id}")
                continue
            seen.add(doc.document_id)
            if len(doc.text.strip()) < 20:
                warnings.append(f"too_short:{doc.document_id}")
                continue
            store.delete_by_source(doc.document_id)
            chunks = chunk_document(
                doc.text,
                source_id=doc.document_id,
                template=settings.chunk_template,
                chunk_size=settings.chunk_size_words,
                chunk_overlap=settings.chunk_overlap_words,
                metadata={"tenant_id": tenant_id, **dict(doc.metadata)},
            )
            for idx, chunk in enumerate(chunks, start=1):
                embedding = embed_text(chunk.text)
                store.upsert(
                    RetrievedChunk(
                        chunk_id=f"{doc.document_id}:{idx}:{chunk.template}",
                        source_id=doc.document_id,
                        text=chunk.text,
                        score=0.0,
                        rank=idx,
                        metadata={
                            "tenant_id": tenant_id,
                            "lineage_parent": doc.document_id,
                            "lineage_kind": "document",
                            "chunk_template": chunk.template,
                            "token_estimate": chunk.token_estimate,
                            "char_start": chunk.char_start,
                            "char_end": chunk.char_end,
                            "_embedding": list(embedding),
                            **dict(doc.metadata),
                        },
                    )
                )
            for att_idx, attachment in enumerate(doc.attachments, start=1):
                parsed = parse_attachment(attachment.name, attachment.content, attachment.content_type)
                if len(parsed.text.strip()) < 20:
                    warnings.append(f"attachment_too_short:{doc.document_id}:{attachment.name}")
                    continue
                ext = Path(parsed.name).suffix.lower().lstrip(".")
                att_template = attachment_template_map.get(ext, settings.chunk_template)
                att_chunks = chunk_document(
                    parsed.text,
                    source_id=f"{doc.document_id}:att:{att_idx}",
                    template=att_template,
                    chunk_size=settings.chunk_size_words,
                    chunk_overlap=settings.chunk_overlap_words,
                    metadata={"tenant_id": tenant_id, **dict(doc.metadata)},
                )
                for piece_idx, chunk in enumerate(att_chunks, start=1):
                    embedding = embed_text(chunk.text)
                    store.upsert(
                        RetrievedChunk(
                            chunk_id=f"{doc.document_id}:att:{att_idx}:{piece_idx}:{chunk.template}",
                            source_id=doc.document_id,
                            text=chunk.text,
                            score=0.0,
                            rank=piece_idx,
                            metadata={
                                "tenant_id": tenant_id,
                                "lineage_parent": doc.document_id,
                                "lineage_kind": "attachment",
                                "chunk_template": chunk.template,
                                "token_estimate": chunk.token_estimate,
                                "char_start": chunk.char_start,
                                "char_end": chunk.char_end,
                                "attachment_name": parsed.name,
                                "attachment_content_type": parsed.content_type,
                                "_embedding": list(embedding),
                                **dict(doc.metadata),
                            },
                        )
                    )
            indexed.append(doc.document_id)
        return IngestResult(indexed_ids=tuple(indexed), warnings=tuple(warnings))


NoOpIngestStage = BaselineIngestStage


def _attachment_template_map() -> dict[str, str]:
    try:
        raw = json.loads(settings.chunk_attachment_template_map_json)
        return {str(k).lower(): str(v).lower() for k, v in raw.items()}
    except Exception:
        return {}
