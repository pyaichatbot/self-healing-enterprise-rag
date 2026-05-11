from __future__ import annotations

import html
import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ParsedAttachment:
    name: str
    text: str
    content_type: str


def _decode_bytes(blob: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return blob.decode(encoding)
        except Exception:
            continue
    return blob.decode("utf-8", errors="ignore")


def _strip_html(text: str) -> str:
    text = re.sub(r"<script.*?>.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style.*?>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(html.unescape(text).split())


def _parse_docx(blob: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
        text = re.sub(r"</w:p>", "\n", xml)
        text = re.sub(r"<[^>]+>", " ", text)
        return " ".join(text.split())
    except Exception:
        return ""


def _parse_pptx(blob: bytes) -> str:
    texts: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            slide_files = [name for name in zf.namelist() if name.startswith("ppt/slides/slide")]
            for slide in sorted(slide_files):
                xml = zf.read(slide).decode("utf-8", errors="ignore")
                cleaned = re.sub(r"<[^>]+>", " ", xml)
                cleaned = " ".join(cleaned.split())
                if cleaned:
                    texts.append(cleaned)
    except Exception:
        return ""
    return "\n".join(texts)


def _parse_xlsx(blob: bytes) -> str:
    out: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            strings: list[str] = []
            if "xl/sharedStrings.xml" in zf.namelist():
                shared = zf.read("xl/sharedStrings.xml").decode("utf-8", errors="ignore")
                strings = [html.unescape(s) for s in re.findall(r"<t[^>]*>(.*?)</t>", shared, flags=re.S)]

            worksheet_files = [name for name in zf.namelist() if name.startswith("xl/worksheets/sheet")]
            for sheet in worksheet_files:
                xml = zf.read(sheet).decode("utf-8", errors="ignore")
                # Inline strings
                inline = [html.unescape(s) for s in re.findall(r"<is>.*?<t[^>]*>(.*?)</t>.*?</is>", xml, flags=re.S)]
                out.extend(inline)
                # Shared string references
                for idx_raw in re.findall(r'<c[^>]*t="s"[^>]*>.*?<v>(\d+)</v>.*?</c>', xml, flags=re.S):
                    idx = int(idx_raw)
                    if 0 <= idx < len(strings):
                        out.append(strings[idx])
    except Exception:
        return ""
    return " ".join(" ".join(out).split())


def _parse_image_with_ocr(blob: bytes) -> str:
    try:
        from PIL import Image  # type: ignore[import-untyped]
        import pytesseract  # type: ignore[import-untyped]
        image = Image.open(io.BytesIO(blob))
        return " ".join(pytesseract.image_to_string(image).split())
    except Exception:
        return ""


def _parse_pdf(blob: bytes) -> str:
    pages: list[str] = []
    # Primary path: pypdf for reliable textual extraction.
    try:
        from PyPDF2 import PdfReader  # type: ignore[import-untyped]
        reader = PdfReader(io.BytesIO(blob))
        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                pages.append(" ".join(text.split()))
    except Exception:
        pass
    # Secondary path: pdfplumber for table/layout-friendly extraction.
    if not pages:
        try:
            import pdfplumber  # type: ignore[import-untyped]
            with pdfplumber.open(io.BytesIO(blob)) as pdf:
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    if text.strip():
                        pages.append(" ".join(text.split()))
                    for table in page.extract_tables() or []:
                        rows = [" | ".join(cell or "" for cell in row) for row in table if row]
                        if rows:
                            pages.append(" ; ".join(" ".join(r.split()) for r in rows))
        except Exception:
            pass
    # OCR fallback for scanned PDFs converted to images is intentionally omitted here.
    return "\n".join(pages)


def parse_attachment(name: str, blob: bytes, content_type: str | None = None) -> ParsedAttachment:
    ext = Path(name).suffix.lower()
    ctype = (content_type or "").lower()

    text = ""
    if ext in {".txt", ".md", ".markdown", ".rst", ".adoc", ".csv", ".json", ".yaml", ".yml", ".xml", ".sql"}:
        text = _decode_bytes(blob)
    elif ext in {".html", ".htm"} or "html" in ctype:
        text = _strip_html(_decode_bytes(blob))
    elif ext == ".docx":
        text = _parse_docx(blob)
    elif ext == ".pptx":
        text = _parse_pptx(blob)
    elif ext == ".xlsx":
        text = _parse_xlsx(blob)
    elif ext == ".pdf" or "pdf" in ctype:
        text = _parse_pdf(blob)
    elif ext in {".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".gif"} or ctype.startswith("image/"):
        text = _parse_image_with_ocr(blob)
    else:
        text = _decode_bytes(blob)

    return ParsedAttachment(name=name, text=text.strip(), content_type=content_type or "application/octet-stream")
