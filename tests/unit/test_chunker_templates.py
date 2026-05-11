from shrag.ingest.chunker import chunk_document


def test_chunker_markdown_template_keeps_heading_metadata():
    text = "# Title\nAlpha paragraph.\n## Section\nBeta paragraph with more context."
    chunks = chunk_document(text, source_id="doc-md", template="markdown", chunk_size=20)
    assert chunks
    assert any(c.template == "markdown" for c in chunks)
    assert any("heading" in c.metadata for c in chunks)


def test_chunker_qa_template_extracts_pairs():
    text = "Q: What is RAG?\nA: Retrieval augmented generation.\nQ: Why?\nA: Better grounding."
    chunks = chunk_document(text, source_id="doc-qa", template="qa")
    assert len(chunks) >= 2
    assert all(c.template == "qa" for c in chunks)
    assert chunks[0].text.startswith("Q:")


def test_chunker_laws_template_splits_sections():
    text = "Article 1. Scope and purpose.\nArticle 2. Enforcement and penalties."
    chunks = chunk_document(text, source_id="doc-law", template="laws")
    assert len(chunks) >= 2
    assert all(c.template == "laws" for c in chunks)


def test_chunker_code_template_detects_function_blocks():
    text = "def alpha():\n    return 1\n\nclass Beta:\n    pass\n"
    chunks = chunk_document(text, source_id="doc-code", template="code", chunk_size=100)
    assert chunks
    assert all(c.template == "code" for c in chunks)
