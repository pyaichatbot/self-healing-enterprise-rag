from shrag.ingest import keyword_extractor as kw


def test_extract_keywords_uses_layered_fallbacks(monkeypatch):
    monkeypatch.setenv("SHRAG_KEYWORD_MAX", "4")
    monkeypatch.setattr(kw, "_extract_llm", lambda text, max_keywords: [])
    monkeypatch.setattr(kw, "_extract_yake", lambda text, max_keywords: [])
    out = kw.extract_keywords("alpha beta beta gamma delta beta")
    assert out
    assert "beta" in out


def test_extract_keywords_uses_cache(monkeypatch):
    monkeypatch.setattr(kw, "_extract_llm", lambda text, max_keywords: ["alpha", "beta"])
    key = kw._cache_key("abc", 2)
    kw._cache.pop(key, None)
    first = kw.extract_keywords("abc", max_keywords=2, use_cache=True)
    second = kw.extract_keywords("abc", max_keywords=2, use_cache=True)
    assert first == second == ["alpha", "beta"]


def test_extract_batch(monkeypatch):
    monkeypatch.setattr(kw, "extract_keywords", lambda t, max_keywords=None, use_cache=True: [t[:3]])
    out = kw.extract_batch(["hello", "world"])
    assert out == [["hel"], ["wor"]]

