from types import SimpleNamespace

from shrag.ingest import toc_generator
from shrag.ingest.toc_generator import TableOfContents, TocEntry, generate_toc


def _chunk(text: str, token_estimate: int = 10):
    return SimpleNamespace(text=text, token_estimate=token_estimate)


def test_generate_toc_heading_extract():
    chunks = [_chunk("# Intro\nhello"), _chunk("## Deep\nworld"), _chunk("tail")]
    toc = generate_toc(chunks, mode="heading_extract")
    assert toc.entries
    assert toc.entries[0].title == "Intro"
    assert toc.entries[0].chunk_start == 0


def test_generate_toc_llm_mode(monkeypatch):
    monkeypatch.setattr("shrag.ingest.toc_generator._summarise_chunk", lambda text: "summary")
    chunks = [_chunk("text one"), _chunk("text two"), _chunk("text three")]
    toc = generate_toc(chunks, mode="llm_summarize", stride=2)
    assert toc.entries
    assert toc.entries[0].summary == "summary"


def test_generate_toc_hybrid_falls_back_to_llm(monkeypatch):
    monkeypatch.setattr("shrag.ingest.toc_generator._extract_headings", lambda chunks: [])
    monkeypatch.setattr("shrag.ingest.toc_generator._llm_toc", lambda chunks, stride=5: [])
    toc = generate_toc([_chunk("no headings")], mode="hybrid")
    assert toc.entries == []


def test_generate_toc_empty_input():
    toc = generate_toc([], mode="heading_extract")
    assert toc.total_chunks == 0
    assert toc.entries == []


def test_toc_markdown_and_dict_serialization():
    toc = TableOfContents(
        entries=[TocEntry(title="Intro", level=1, chunk_start=0, chunk_end=1, summary="sum")],
        mode="manual",
        total_chunks=2,
    )
    md = toc.to_markdown()
    data = toc.to_dict()
    assert "Intro" in md
    assert data["entries"][0]["title"] == "Intro"


def test_summarise_chunk_fallback_when_llm_fails(monkeypatch):
    monkeypatch.setattr("shrag.generate.llm.complete", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    summary = toc_generator._summarise_chunk("one two three four five six seven")
    assert summary.startswith("one two")


def test_extract_headings_updates_same_chunk_entry():
    chunks = [_chunk("# A\n## B\n### C", token_estimate=11), _chunk("tail", token_estimate=2)]
    entries = toc_generator._extract_headings(chunks)
    assert entries[-1].title == "C"
    assert entries[-1].chunk_end == 1
