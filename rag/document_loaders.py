"""Bounded text extraction for small business-document prototypes.

TXT, Markdown, CSV, HTML and DOCX use the Python standard library. PDF text
extraction uses a separately installed, pinned pypdf dependency. XLSX reading
uses pinned openpyxl + defusedxml dependencies installed separately from vLLM.
PDFs containing only scanned images require OCR and are intentionally rejected.
"""
from __future__ import annotations

import csv
from decimal import Decimal, ROUND_HALF_UP
from html.parser import HTMLParser
import io
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

TEXT_EXTENSIONS = {".txt", ".md"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | {".csv", ".html", ".htm", ".docx", ".pdf", ".xlsx"}
MAX_INPUT_BYTES = 10 * 1024 * 1024
MAX_DOCX_XML_BYTES = 20 * 1024 * 1024
MAX_PDF_PAGES = 300
MAX_EXTRACTED_TEXT_CHARS = 5_000_000
MAX_XLSX_TOTAL_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_XLSX_MEMBER_BYTES = 40 * 1024 * 1024
MAX_XLSX_SHEETS = 50
MAX_XLSX_ROWS_PER_SHEET = 100_000
MAX_XLSX_COLUMNS_PER_SHEET = 512
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


def sanitize_excel_float(value: float) -> Decimal:
    """Convert an IEEE float from Excel into a Decimal without binary tails.

    Excel stores many cells as binary floats (for example 99.498 becoming
    99.49800000000002). This keeps the stored magnitude; it does not invent a
    different business amount or apply currency rounding.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("sanitize_excel_float expects a non-bool int or float")
    if isinstance(value, int):
        return Decimal(value)
    text = format(Decimal(str(float(value))), "f")
    if "000000" in text or "999999" in text:
        cleaned = Decimal(str(float(value))).quantize(Decimal("1e-10"))
    else:
        cleaned = Decimal(str(float(value)))
    normalized = cleaned.normalize()
    # Avoid scientific notation for ordinary spreadsheet magnitudes.
    rendered = format(normalized, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return Decimal(rendered or "0")


def format_money_gbp(amount: Decimal | float | int | str) -> str:
    """Format a monetary amount for display as pounds to two decimal places."""
    value = amount if isinstance(amount, Decimal) else Decimal(str(amount))
    quantized = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"£{quantized}"


def weekly_from_daily(daily: Decimal | float | int | str, days: int = 7) -> Decimal:
    """Derive a weekly amount as daily × days using decimal arithmetic."""
    if days <= 0:
        raise ValueError("days must be a positive integer")
    if isinstance(daily, Decimal):
        rate = daily
    elif isinstance(daily, float):
        rate = sanitize_excel_float(daily)
    elif isinstance(daily, bool):
        raise TypeError("boolean values are not daily rates")
    else:
        rate = Decimal(str(daily))
    return rate * Decimal(days)


def _is_numeric_xlsx_value(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _currency_display(value: Decimal, number_format: str | None) -> str | None:
    if not number_format:
        return None
    fmt = number_format.casefold()
    if "£" in number_format or "[$£" in fmt or "gbp" in fmt:
        return format_money_gbp(value)
    if "€" in number_format or "[$€" in fmt:
        quantized = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return f"€{quantized}"
    if "$" in number_format and "red" not in fmt.replace("£", ""):
        # Conservative: only treat clear currency formats as display money.
        if '"$"$' in number_format or number_format.startswith("$#") or '"$"#' in number_format:
            quantized = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            return f"${quantized}"
    return None


def render_xlsx_cell_value(value: object, number_format: str | None = None) -> str:
    """Render one workbook cell for retrieval without inventing missing values."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if hasattr(value, "isoformat") and callable(value.isoformat):
        return value.isoformat()
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        stored = sanitize_excel_float(value)
        rendered = format(stored, "f")
        if "." in rendered:
            rendered = rendered.rstrip("0").rstrip(".")
        display = _currency_display(stored, number_format)
        if display and display.lstrip("£€$") != rendered:
            return f"{rendered} (workbook displays {display})"
        return rendered or "0"
    text = str(value).strip()
    return text


def _combine_column_headers(header_rows: list[list[str | None]], column_count: int) -> list[str | None]:
    """Stack label rows above the first numeric data row into one header per column."""
    combined: list[str | None] = []
    for column_index in range(column_count):
        parts: list[str] = []
        seen: set[str] = set()
        for row in header_rows:
            if column_index >= len(row):
                continue
            part = row[column_index]
            if not part:
                continue
            key = part.casefold()
            if key in seen:
                continue
            seen.add(key)
            parts.append(part)
        combined.append(" / ".join(parts) if parts else None)
    return combined


def _xlsx_cell_coordinate(cell: object, row_index: int, column_index: int) -> str:
    """Resolve A1-style coordinates, including openpyxl EmptyCell placeholders."""
    coordinate = getattr(cell, "coordinate", None)
    if isinstance(coordinate, str) and coordinate:
        return coordinate
    try:
        from openpyxl.utils import get_column_letter
    except ImportError:
        return f"C{column_index}R{row_index}"
    row_number = getattr(cell, "row", None) or row_index
    column_number = getattr(cell, "column", None) or column_index
    return f"{get_column_letter(int(column_number))}{int(row_number)}"


def _read_xlsx(path: Path) -> str:
    # Optional packages are kept in /tmp/rag-deps, separate from vLLM/PyTorch.
    try:
        import openpyxl
    except ImportError as exc:
        raise DocumentLoadError(
            "XLSX support requires the pinned openpyxl and defusedxml dependencies; "
            "run rag/setup_xlsx_support.sh first"
        ) from exc

    # Validate ZIP entry sizes before giving the workbook to a reader. XLSX files
    # are ZIP containers and must be treated as untrusted input.
    try:
        with zipfile.ZipFile(path, "r") as archive:
            infos = archive.infolist()
            names = {info.filename for info in infos}
            if "[Content_Types].xml" not in names or "xl/workbook.xml" not in names:
                raise DocumentLoadError(f"{path.name} is not a valid XLSX workbook")
            total_size = 0
            for info in infos:
                member = Path(info.filename)
                if member.is_absolute() or ".." in member.parts:
                    raise DocumentLoadError(f"unsafe ZIP entry in {path.name}")
                if info.file_size > MAX_XLSX_MEMBER_BYTES:
                    raise DocumentLoadError(
                        f"uncompressed component in {path.name} exceeds the size limit"
                    )
                total_size += info.file_size
                if total_size > MAX_XLSX_TOTAL_UNCOMPRESSED_BYTES:
                    raise DocumentLoadError(
                        f"uncompressed workbook in {path.name} exceeds the total size limit"
                    )
    except DocumentLoadError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise DocumentLoadError(f"invalid or unreadable XLSX file {path.name}: {exc}") from exc

    workbook = None
    try:
        workbook = openpyxl.load_workbook(
            filename=path,
            read_only=True,
            data_only=True,
            keep_links=False,
        )
        sheets = workbook.worksheets
        if len(sheets) > MAX_XLSX_SHEETS:
            raise DocumentLoadError(
                f"{path.name} has more than {MAX_XLSX_SHEETS} worksheets"
            )
        output: list[str] = []
        total_chars = 0
        for sheet in sheets:
            if sheet.max_row is not None and sheet.max_row > MAX_XLSX_ROWS_PER_SHEET:
                raise DocumentLoadError(
                    f"worksheet {sheet.title!r} in {path.name} exceeds the row limit"
                )
            if sheet.max_column is not None and sheet.max_column > MAX_XLSX_COLUMNS_PER_SHEET:
                raise DocumentLoadError(
                    f"worksheet {sheet.title!r} in {path.name} exceeds the column limit"
                )
            sheet_label = f"Sheet: {sheet.title} (state: {sheet.sheet_state})"
            output.append(sheet_label)
            # Buffer rows so multi-line headers (title / age bands / units) can be
            # stacked before the first numeric data row instead of freezing on row 1.
            buffered_rows: list[tuple[int, list[tuple[str, object, str | None]]]] = []
            for row_index, row in enumerate(sheet.iter_rows(values_only=False), start=1):
                if row_index > MAX_XLSX_ROWS_PER_SHEET:
                    raise DocumentLoadError(
                        f"worksheet {sheet.title!r} in {path.name} exceeds the row limit"
                    )
                cells: list[tuple[str, object, str | None]] = []
                for column_index, cell in enumerate(row, start=1):
                    coordinate = _xlsx_cell_coordinate(cell, row_index, column_index)
                    value = getattr(cell, "value", None)
                    if value is None or (isinstance(value, str) and not value.strip()):
                        cells.append((coordinate, None, None))
                        continue
                    number_format = getattr(cell, "number_format", None)
                    cells.append((coordinate, value, number_format))
                if any(value is not None for _, value, _ in cells):
                    buffered_rows.append((row_index, cells))

            header_label_rows: list[list[str | None]] = []
            headers: list[str | None] = []
            headers_frozen = False
            for row_index, cells in buffered_rows:
                column_count = max(len(cells), len(headers), 1)
                label_row: list[str | None] = [None] * column_count
                has_numeric = False
                values: list[str] = []
                for column_index, (coordinate, value, number_format) in enumerate(cells):
                    if value is None:
                        continue
                    if _is_numeric_xlsx_value(value):
                        has_numeric = True
                    rendered = render_xlsx_cell_value(value, number_format)
                    if not rendered:
                        continue
                    label_row[column_index] = rendered
                    if headers_frozen:
                        header = headers[column_index] if column_index < len(headers) else None
                        if header:
                            values.append(f"{coordinate}/{header}={rendered}")
                        else:
                            values.append(f"{coordinate}={rendered}")

                if not headers_frozen:
                    if has_numeric:
                        headers = _combine_column_headers(header_label_rows, column_count)
                        headers_frozen = True
                        values = []
                        for column_index, (coordinate, value, number_format) in enumerate(cells):
                            if value is None:
                                continue
                            rendered = render_xlsx_cell_value(value, number_format)
                            if not rendered:
                                continue
                            header = headers[column_index] if column_index < len(headers) else None
                            if header:
                                values.append(f"{coordinate}/{header}={rendered}")
                            else:
                                values.append(f"{coordinate}={rendered}")
                    else:
                        header_label_rows.append(label_row)
                        # Still emit label rows so sheet structure remains searchable.
                        label_values: list[str] = []
                        for column_index, (coordinate, value, number_format) in enumerate(cells):
                            if value is None:
                                continue
                            rendered = render_xlsx_cell_value(value, number_format)
                            if rendered:
                                label_values.append(f"{coordinate}={rendered}")
                        if label_values:
                            values = label_values

                if values:
                    line = f"Sheet: {sheet.title} | Row {row_index}: " + " | ".join(values)
                    total_chars += len(line) + 1
                    if total_chars > MAX_EXTRACTED_TEXT_CHARS:
                        raise DocumentLoadError(
                            f"extracted worksheet text from {path.name} exceeds the text limit"
                        )
                    output.append(line)
        text = "\n".join(output).strip()
        if not text or not any(line.startswith("Sheet:") and "| Row " in line for line in output):
            raise DocumentLoadError(f"{path.name} contains no searchable worksheet cell values")
        return text
    except DocumentLoadError:
        raise
    except Exception as exc:
        raise DocumentLoadError(f"invalid or unreadable XLSX file {path.name}: {exc}") from exc
    finally:
        if workbook is not None:
            try:
                workbook.close()
            except Exception:
                pass


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
    if suffix == ".xlsx":
        return _read_xlsx(path)
    raise DocumentLoadError(f"unsupported document type: {suffix}")
