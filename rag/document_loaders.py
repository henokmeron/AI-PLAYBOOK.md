"""Bounded text extraction for small business-document prototypes.

TXT, Markdown, CSV, HTML and DOCX use the Python standard library. PDF text
extraction uses a separately installed, pinned pypdf dependency.
PDFs containing only scanned images require OCR and are intentionally rejected.
XLSX remains unsupported.
"""
from __future__ import annotations

import csv
from html.parser import HTMLParser
import io
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

TEXT_EXTENSIONS = {".txt", ".md"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | {".csv", ".html", ".htm", ".docx", ".pdf"}
MAX_INPUT_BYTES = 10 * 1024 * 1024
MAX_DOCX_XML_BYTES = 20 * 1024 * 1024
MAX_PDF_PAGES = 300
MAX_EXTRACTED_TEXT_CHARS = 5_000_000
WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class DocumentLoadError(ValueError):
    """Raised when a source file cannot safely be read as supported text."""


class _VisibleHTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._hidden_depth = 0
        self._hidden_tags = {"script", "style", "noscript", "svg"}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() in self._hidden_tags:
            self._hidden_depth += 1
        elif tag.casefold() in {"p", "div", "li", "tr", "h1", "h2", "h3", "br"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in self._hidden_tags and self._hidden_depth:
            self._hidden_depth -= 1
        elif tag.casefold() in {"p", "div", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._hidden_depth == 0:
            cleaned = " ".join(data.split())
            if cleaned:
                self.parts.append(cleaned + " ")

    def get_text(self) -> str:
        return "\n".join(line.strip() for line in "".join(self.parts).splitlines() if line.strip()).strip()


def _read_utf8(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise DocumentLoadError(f"cannot read {path}: {exc}") from exc
    if len(raw) > MAX_INPUT_BYTES:
        raise DocumentLoadError(f"{path} exceeds the {MAX_INPUT_BYTES}-byte input limit")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DocumentLoadError(f"{path} is not valid UTF-8 text") from exc


def _read_csv(path: Path) -> str:
    raw = _read_utf8(path)
    rows: list[str] = []
    try:
        reader = csv.reader(io.StringIO(raw, newline=""))
        for row_number, row in enumerate(reader, start=1):
            # Empty rows add no searchable information.
            cells = [cell.strip() for cell in row]
            if any(cells):
                rows.append(f"Row {row_number}: " + " | ".join(cells))
    except csv.Error as exc:
        raise DocumentLoadError(f"invalid CSV file {path}: {exc}") from exc
    return "\n".join(rows)


def _read_html(path: Path) -> str:
    raw = _read_utf8(path)
    parser = _VisibleHTMLText()
    try:
        parser.feed(raw)
        parser.close()
    except Exception as exc:
        raise DocumentLoadError(f"could not parse HTML file {path}: {exc}") from exc
    return parser.get_text()


def _read_docx(path: Path) -> str:
    try:
        with zipfile.ZipFile(path, "r") as archive:
            try:
                info = archive.getinfo("word/document.xml")
            except KeyError as exc:
                raise DocumentLoadError(f"{path} is not a Word DOCX document (missing word/document.xml)") from exc
            if info.file_size > MAX_DOCX_XML_BYTES:
                raise DocumentLoadError(f"uncompressed Word XML in {path} exceeds the safety limit")
            with archive.open(info, "r") as stream:
                xml_bytes = stream.read(MAX_DOCX_XML_BYTES + 1)
            if len(xml_bytes) > MAX_DOCX_XML_BYTES:
                raise DocumentLoadError(f"Word XML in {path} exceeds the safety limit")
    except DocumentLoadError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError, KeyError) as exc:
        raise DocumentLoadError(f"invalid or unreadable DOCX file {path}: {exc}") from exc

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise DocumentLoadError(f"invalid Word XML in {path}: {exc}") from exc

    paragraphs: list[str] = []
    for paragraph in root.iter(f"{WORD_NS}p"):
        pieces: list[str] = []
        for node in paragraph.iter():
            if node.tag == f"{WORD_NS}t" and node.text:
                pieces.append(node.text)
            elif node.tag == f"{WORD_NS}tab":
                pieces.append("\t")
            elif node.tag in {f"{WORD_NS}br", f"{WORD_NS}cr"}:
                pieces.append("\n")
        text = "".join(pieces).strip()
        if text:
            paragraphs.append(text)
    return "\n".join(paragraphs)


def _read_pdf(path: Path) -> str:
    # Import lazily so TXT/CSV/HTML/DOCX still work if the optional PDF dependency
    # is not installed. The gateway startup script sets PYTHONPATH=/tmp/rag-deps.
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise DocumentLoadError(
            "PDF support requires the pinned pypdf dependency; run rag/setup_pdf_support.sh first"
        ) from exc

    try:
        reader = PdfReader(str(path), strict=False)
        if reader.is_encrypted:
            try:
                unlocked = reader.decrypt("")
            except Exception as exc:
                raise DocumentLoadError(f"encrypted PDF is not supported: {path.name}") from exc
            if not unlocked:
                raise DocumentLoadError(f"password-protected PDF is not supported: {path.name}")
        page_count = len(reader.pages)
        if page_count > MAX_PDF_PAGES:
            raise DocumentLoadError(
                f"{path.name} has {page_count} pages; the limit is {MAX_PDF_PAGES}"
            )
        pages: list[str] = []
        total_chars = 0
        for page_number, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception as exc:
                raise DocumentLoadError(
                    f"could not extract text from page {page_number} of {path.name}"
                ) from exc
            text = text.strip()
            if text:
                page_text = f"[Page {page_number}]\\n{text}"
                total_chars += len(page_text)
                if total_chars > MAX_EXTRACTED_TEXT_CHARS:
                    raise DocumentLoadError(
                        f"extracted text from {path.name} exceeds the safety limit"
                    )
                pages.append(page_text)
    except DocumentLoadError:
        raise
    except Exception as exc:
        raise DocumentLoadError(f"invalid or unreadable PDF file {path.name}: {exc}") from exc

    if not pages:
        raise DocumentLoadError(
            f"{path.name} contains no extractable text; scanned/image-only PDFs require OCR, which is not enabled"
        )
    return "\\n\\n".join(pages)


def read_document(path: Path) -> str:
    """Read a supported document into plain text without executing its content."""
    suffix = path.suffix.casefold()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise DocumentLoadError(f"unsupported document type: {path.suffix or '(no extension)'}")
    if not path.is_file():
        raise DocumentLoadError(f"not a regular file: {path}")
    try:
        input_size = path.stat().st_size
    except OSError as exc:
        raise DocumentLoadError(f"cannot inspect {path}: {exc}") from exc
    if input_size > MAX_INPUT_BYTES:
        raise DocumentLoadError(f"{path} exceeds the {MAX_INPUT_BYTES}-byte input limit")
    if suffix in TEXT_EXTENSIONS:
        return _read_utf8(path)
    if suffix == ".csv":
        return _read_csv(path)
    if suffix in {".html", ".htm"}:
        return _read_html(path)
    if suffix == ".docx":
        return _read_docx(path)
    if suffix == ".pdf":
        return _read_pdf(path)
    raise DocumentLoadError(f"unsupported document type: {suffix}")
