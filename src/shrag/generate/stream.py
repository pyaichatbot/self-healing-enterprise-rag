from __future__ import annotations

from collections.abc import Iterator


def stream_text(text: str, token_size: int = 24) -> Iterator[str]:
    for index in range(0, len(text), token_size):
        yield text[index : index + token_size]
