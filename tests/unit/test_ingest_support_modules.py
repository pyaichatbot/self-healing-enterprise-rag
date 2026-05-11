from __future__ import annotations

from dataclasses import dataclass
import importlib.util
from pathlib import Path
import sys


def _load_module(name: str, relative_path: str):
    root = Path(__file__).resolve().parents[2]
    target = root / relative_path
    spec = importlib.util.spec_from_file_location(name, target)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


keyword_extractor = _load_module("keyword_extractor", "src/shrag/ingest/keyword_extractor.py")
toc_generator = _load_module("toc_generator", "src/shrag/ingest/toc_generator.py")
index_lifecycle = _load_module("index_lifecycle", "src/shrag/ingest/index_lifecycle.py")
partition = _load_module("partition", "src/shrag/ingest/partition.py")
reindex = _load_module("reindex", "src/shrag/ingest/reindex.py")


@dataclass
class _Chunk:
    text: str
    token_estimate: int = 0


def test_keyword_extractor_uses_l1_cache(monkeypatch):
    monkeypatch.setattr(keyword_extractor, "_cache", {})
    monkeypatch.setattr(keyword_extractor, "_extract_llm", lambda text, n: ["alpha", "beta"])  # type: ignore[arg-type]
    monkeypatch.setattr(keyword_extractor, "_extract_yake", lambda text, n: [])  # type: ignore[arg-type]
    monkeypatch.setattr(keyword_extractor, "_extract_tfidf_heuristic", lambda text, n: ["fallback"])  # type: ignore[arg-type]

    first = keyword_extractor.extract_keywords("alpha beta gamma", max_keywords=2)
    second = keyword_extractor.extract_keywords("alpha beta gamma", max_keywords=2)

    assert first == ["alpha", "beta"]
    assert second == ["alpha", "beta"]


def test_keyword_extractor_fallback_chain_and_no_cache(monkeypatch):
    monkeypatch.setattr(keyword_extractor, "_extract_llm", lambda text, n: [])  # type: ignore[arg-type]
    monkeypatch.setattr(keyword_extractor, "_extract_yake", lambda text, n: [])  # type: ignore[arg-type]
    monkeypatch.setattr(keyword_extractor, "_extract_tfidf_heuristic", lambda text, n: ["signal", "latency"])  # type: ignore[arg-type]

    out = keyword_extractor.extract_keywords("signal latency reliability", max_keywords=2, use_cache=False)

    assert out == ["signal", "latency"]


def test_keyword_extractor_honors_stopwords_env(monkeypatch):
    monkeypatch.setenv("SHRAG_KEYWORD_STOPWORDS", "customstop")
    stops = keyword_extractor._stopwords()
    assert "customstop" in stops
    assert "the" in stops


def test_keyword_extractor_extract_batch(monkeypatch):
    monkeypatch.setattr(keyword_extractor, "extract_keywords", lambda text, max_keywords=None: [text.split()[0]])
    out = keyword_extractor.extract_batch(["alpha one", "beta two"], max_keywords=1)
    assert out == [["alpha"], ["beta"]]


def test_toc_heading_extract_and_markdown_serialization():
    chunks = [
        _Chunk("# Intro\nWelcome", token_estimate=12),
        _Chunk("## Details\nDeep dive", token_estimate=15),
        _Chunk("No heading here", token_estimate=8),
    ]
    toc = toc_generator.generate_toc(chunks, mode="heading_extract")

    assert toc.total_chunks == 3
    assert len(toc.entries) == 2
    assert toc.entries[0].title == "Intro"
    assert toc.entries[0].chunk_end == 0
    rendered = toc.to_markdown()
    assert "Intro" in rendered
    assert "Details" in rendered
    as_dict = toc.to_dict()
    assert as_dict["mode"] == "heading_extract"


def test_toc_llm_summarize_mode(monkeypatch):
    monkeypatch.setattr(toc_generator, "_summarise_chunk", lambda text: "summary")
    chunks = [_Chunk("a", 1), _Chunk("b", 2), _Chunk("c", 3)]
    toc = toc_generator.generate_toc(chunks, mode="llm_summarize", stride=2)

    assert len(toc.entries) == 2
    assert toc.entries[0].summary == "summary"
    assert toc.entries[0].chunk_end == 1


def test_toc_hybrid_falls_back_to_llm_when_no_headings(monkeypatch):
    monkeypatch.setattr(toc_generator, "_summarise_chunk", lambda text: "fallback-summary")
    chunks = [_Chunk("plain paragraph one", 4), _Chunk("plain paragraph two", 5)]

    toc = toc_generator.generate_toc(chunks, mode="hybrid", stride=1)

    assert len(toc.entries) == 2
    assert all(entry.summary == "fallback-summary" for entry in toc.entries)


def test_toc_mode_from_env_and_empty_input(monkeypatch):
    monkeypatch.setenv("SHRAG_TOC_MODE", "heading_extract")
    toc = toc_generator.generate_toc([])
    assert toc.mode == "heading_extract"
    assert toc.entries == []


def test_index_lifecycle_cutover_behavior():
    assert index_lifecycle.cutover("v1", "v2") == "v2"
    assert index_lifecycle.cutover("v1", "") == "v1"


def test_partition_key_and_reindex_threshold_edges():
    assert partition.partition_key("tenant-a", "kb") == "tenant-a:kb"
    assert reindex.should_reindex(0.2, threshold=0.2) is True
    assert reindex.should_reindex(0.19, threshold=0.2) is False
