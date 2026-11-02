"""Pull plain text out of an uploaded study file.

Supports the formats people actually keep exam notes in: PDF, Word (.docx),
Excel (.xlsx), and plain text/markdown/CSV. Everything is done in memory from
the uploaded bytes — nothing is written to disk — and only the extracted text is
kept, matching how the voice upload path already works.

Deliberately NOT handled: scanned-image PDFs and photos. Those need OCR
(Tesseract) or a vision model, which is a much heavier dependency; a scanned PDF
simply yields little or no text and the caller reports that cleanly.
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)


class ExtractError(Exception):
    """Raised with a user-facing message when a file cannot be read."""


@dataclass
class Extracted:
    text: str
    kind: str  # pdf | docx | xlsx | text — how it was read, for the UI


# Map a filename extension to how we read it. content_type from the browser is
# unreliable, so the extension is the primary signal.
_PDF_EXT = {".pdf"}
_DOCX_EXT = {".docx"}
_XLSX_EXT = {".xlsx", ".xlsm"}
_TEXT_EXT = {".txt", ".md", ".markdown", ".csv", ".tsv", ".text", ".rtf"}


def _ext(filename: str) -> str:
    dot = filename.rfind(".")
    return filename[dot:].lower() if dot != -1 else ""


def _from_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        raise ExtractError("That PDF could not be opened. It may be corrupt or password-protected.") from exc

    if reader.is_encrypted:
        # An empty password unlocks many "protected" PDFs; try it before giving up.
        try:
            reader.decrypt("")
        except Exception:  # noqa: BLE001
            raise ExtractError("That PDF is password-protected. Remove the password and re-upload.")

    parts: list[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001
            continue  # one bad page should not sink the whole file
    return "\n\n".join(p.strip() for p in parts if p.strip())


def _from_docx(data: bytes) -> str:
    import docx  # python-docx

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        raise ExtractError("That Word file could not be opened. Save it as .docx and try again.") from exc

    parts = [p.text for p in document.paragraphs if p.text.strip()]
    # Tables hold a lot of revision material; flatten them row by row.
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts)


def _from_xlsx(data: bytes) -> str:
    from openpyxl import load_workbook

    try:
        # read_only + data_only: fast, and reads computed values not formulas.
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001
        raise ExtractError("That spreadsheet could not be opened. Save it as .xlsx and try again.") from exc

    parts: list[str] = []
    for sheet in workbook.worksheets:
        parts.append(f"# Sheet: {sheet.title}")
        for row in sheet.iter_rows(values_only=True):
            cells = [str(c).strip() for c in row if c is not None and str(c).strip()]
            if cells:
                parts.append(" | ".join(cells))
    workbook.close()
    return "\n".join(parts)


def _from_text(data: bytes) -> str:
    # Try UTF-8, then common fallbacks, before giving up.
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ExtractError("That text file is in an encoding I could not read.")


def extract(filename: str, data: bytes, *, max_chars: int) -> Extracted:
    """Return the text of an uploaded study file, capped at `max_chars`.

    Raises ExtractError with a message safe to show the user when the file type
    is unsupported or the file holds no usable text (e.g. a scanned PDF).
    """
    if not data:
        raise ExtractError("The file was empty.")

    ext = _ext(filename or "")
    if ext in _PDF_EXT:
        text, kind = _from_pdf(data), "pdf"
    elif ext in _DOCX_EXT:
        text, kind = _from_docx(data), "docx"
    elif ext in _XLSX_EXT:
        text, kind = _from_xlsx(data), "xlsx"
    elif ext in _TEXT_EXT or ext == "":
        text, kind = _from_text(data), "text"
    elif ext in {".doc", ".ppt", ".pptx", ".pages"}:
        raise ExtractError(
            f"{ext} files are not supported yet. Export to PDF or .docx and re-upload."
        )
    else:
        raise ExtractError(
            f"I can't read {ext or 'that'} files. Upload a PDF, Word (.docx), Excel (.xlsx) or text file."
        )

    text = (text or "").strip()
    if len(text) < 20:
        raise ExtractError(
            "I couldn't find readable text in that file. If it's a scanned PDF or a "
            "photo, OCR isn't supported yet — upload a text-based version."
        )

    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars]
    return Extracted(text=text, kind=kind)
