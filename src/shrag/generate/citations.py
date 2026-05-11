from __future__ import annotations

import re
from collections.abc import Sequence

from shrag.observe.models import RetrievedChunk


_SOURCE_RE = re.compile(r"\[([^\]]+)\]")


def extract_citations(answer: str, chunks: Sequence[RetrievedChunk]) -> tuple[str, ...]:
    cited = set(_SOURCE_RE.findall(answer))
    allowed = {chunk.source_id for chunk in chunks}
    valid = tuple(sorted(cited.intersection(allowed)))
    if valid:
        return valid
    return tuple(chunk.source_id for chunk in chunks[:2])
