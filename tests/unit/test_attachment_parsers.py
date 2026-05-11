from shrag.ingest.loaders import parsers
from shrag.ingest.loaders.parsers import parse_attachment
import io
import zipfile


def test_parse_html_attachment_strips_tags():
    parsed = parse_attachment("note.html", b"<h1>Title</h1><p>Hello <b>world</b></p>", "text/html")
    assert "Title" in parsed.text
    assert "world" in parsed.text


def test_parse_text_attachment():
    parsed = parse_attachment("notes.txt", b"alpha beta gamma")
    assert parsed.text == "alpha beta gamma"


def test_parse_pdf_uses_pdf_parser(monkeypatch):
    monkeypatch.setattr(parsers, "_parse_pdf", lambda blob: "pdf text extracted")
    parsed = parse_attachment("report.pdf", b"%PDF-1.4 fake", "application/pdf")
    assert parsed.text == "pdf text extracted"


def test_parse_image_uses_ocr_parser(monkeypatch):
    monkeypatch.setattr(parsers, "_parse_image_with_ocr", lambda blob: "image ocr text")
    parsed = parse_attachment("screenshot.png", b"\x89PNG", "image/png")
    assert parsed.text == "image ocr text"


def test_parse_docx_pptx_xlsx_dispatch(monkeypatch):
    monkeypatch.setattr(parsers, "_parse_docx", lambda blob: "docx content")
    monkeypatch.setattr(parsers, "_parse_pptx", lambda blob: "pptx content")
    monkeypatch.setattr(parsers, "_parse_xlsx", lambda blob: "xlsx content")

    assert parse_attachment("a.docx", b"blob").text == "docx content"
    assert parse_attachment("b.pptx", b"blob").text == "pptx content"
    assert parse_attachment("c.xlsx", b"blob").text == "xlsx content"


def test_decode_bytes_fallback_path():
    # latin-1 path is exercised when utf-8 decoding fails.
    assert parsers._decode_bytes(b"\xff") == "ÿ"


def test_strip_html_removes_script_and_style():
    html = "<style>.x{}</style><script>alert(1)</script><p>Hello&nbsp;World</p>"
    assert parsers._strip_html(html) == "Hello World"


def test_parse_unknown_extension_falls_back_to_decode():
    parsed = parse_attachment("blob.bin", b"abc")
    assert parsed.text == "abc"
    assert parsed.content_type == "application/octet-stream"


def test_parse_docx_and_pptx_and_xlsx_minimal_archives():
    docx = io.BytesIO()
    with zipfile.ZipFile(docx, "w") as zf:
        zf.writestr("word/document.xml", "<w:p>Hello</w:p><w:p>Docx</w:p>")
    assert "Hello" in parsers._parse_docx(docx.getvalue())

    pptx = io.BytesIO()
    with zipfile.ZipFile(pptx, "w") as zf:
        zf.writestr("ppt/slides/slide1.xml", "<a:t>Slide One</a:t>")
    assert "Slide One" in parsers._parse_pptx(pptx.getvalue())

    xlsx = io.BytesIO()
    with zipfile.ZipFile(xlsx, "w") as zf:
        zf.writestr("xl/sharedStrings.xml", "<sst><si><t>Shared</t></si></sst>")
        zf.writestr("xl/worksheets/sheet1.xml", '<sheet><c t="s"><v>0</v></c><is><t>Inline</t></is></sheet>')
    parsed = parsers._parse_xlsx(xlsx.getvalue())
    assert "Shared" in parsed and "Inline" in parsed
