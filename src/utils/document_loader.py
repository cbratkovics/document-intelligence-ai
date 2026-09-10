"""Upload validation, text extraction, and upload storage.

Supported formats are plain text (.txt), Markdown (.md), reStructuredText
(.rst, treated as plain text: directives are never executed) and PDF (.pdf,
text layer only via pypdf; scanned PDFs without a text layer are rejected).

Extraction produces a *normalized* text (``\\r\\n`` -> ``\\n``, NUL bytes
removed) plus page spans so that chunk offsets can be mapped back to pages.
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from ..core.types import IngestionError

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".txt", ".md", ".rst", ".pdf"}
_TEXT_EXTENSIONS = {".txt", ".md", ".rst"}
_PDF_MAGIC = b"%PDF-"


@dataclass(frozen=True)
class PageSpan:
    page_number: int
    char_start: int
    char_end: int


@dataclass
class ExtractedDocument:
    text: str
    extension: str
    pages: List[PageSpan] = field(default_factory=list)
    page_count: Optional[int] = None
    warnings: List[str] = field(default_factory=list)


def content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def normalize_display_filename(filename: Optional[str], max_length: int) -> str:
    """Return a safe display name (never used as a storage path)."""
    name = (filename or "").strip()
    name = name.replace("\\", "/").split("/")[-1]
    name = unicodedata.normalize("NFC", name)
    name = "".join(ch for ch in name if ch.isprintable() and ch not in "\x00")
    if not name or name in {".", ".."}:
        raise IngestionError("A filename is required", code="missing_filename")
    if len(name) > max_length:
        raise IngestionError(
            f"Filename longer than {max_length} characters", code="filename_too_long"
        )
    return name


def detect_extension(display_filename: str) -> str:
    ext = Path(display_filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise IngestionError(
            f"Unsupported file type '{ext or '(none)'}'. Supported: "
            + ", ".join(sorted(SUPPORTED_EXTENSIONS)),
            code="unsupported_type",
        )
    return ext


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    return text


def _decode_text(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16"):
        try:
            text = content.decode(encoding)
        except UnicodeDecodeError:
            continue
        # utf-16 will happily decode ASCII garbage; require a BOM for it.
        if encoding == "utf-16" and not content.startswith((b"\xff\xfe", b"\xfe\xff")):
            continue
        return text
    raise IngestionError(
        "Text files must be UTF-8 (or UTF-16 with a byte-order mark)",
        code="invalid_encoding",
    )


def _extract_pdf(content: bytes, max_pages: int) -> ExtractedDocument:
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError as exc:  # pragma: no cover - dependency is in base reqs
        raise IngestionError("PDF support is not installed", status=500) from exc

    if not content.startswith(_PDF_MAGIC):
        raise IngestionError("File does not look like a PDF", code="invalid_pdf")
    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            # pypdf can open some encrypted PDFs with an empty password.
            try:
                if reader.decrypt("") == 0:
                    raise IngestionError("Encrypted PDFs are not supported", code="encrypted_pdf")
            except IngestionError:
                raise
            except Exception as exc:
                raise IngestionError(
                    "Encrypted PDFs are not supported", code="encrypted_pdf"
                ) from exc
        page_count = len(reader.pages)
    except IngestionError:
        raise
    except (PdfReadError, ValueError, TypeError, KeyError, IndexError) as exc:
        raise IngestionError(f"Malformed PDF: {exc}", code="invalid_pdf") from exc
    except Exception as exc:  # pypdf raises a wide variety of exceptions
        raise IngestionError(f"Malformed PDF: {exc}", code="invalid_pdf") from exc

    if page_count > max_pages:
        raise IngestionError(
            f"PDF has {page_count} pages; the limit is {max_pages}",
            code="too_many_pages",
        )

    parts: List[str] = []
    spans: List[PageSpan] = []
    warnings: List[str] = []
    cursor = 0
    for index, page in enumerate(reader.pages):
        try:
            page_text = page.extract_text() or ""
        except Exception as exc:  # pragma: no cover - depends on PDF internals
            warnings.append(f"page {index + 1}: extraction failed ({exc})")
            page_text = ""
        page_text = _normalize_text(page_text).strip()
        if not page_text:
            warnings.append(f"page {index + 1}: no text layer")
            continue
        if parts:
            cursor += 2  # separator "\n\n"
        start = cursor
        parts.append(page_text)
        cursor += len(page_text)
        spans.append(PageSpan(page_number=index + 1, char_start=start, char_end=cursor))

    text = "\n\n".join(parts)
    return ExtractedDocument(
        text=text, extension=".pdf", pages=spans, page_count=page_count, warnings=warnings
    )


def extract_document(
    display_filename: str,
    content: bytes,
    *,
    max_extracted_chars: int,
    max_pdf_pages: int,
) -> ExtractedDocument:
    """Validate ``content`` and extract normalized text.

    Raises ``IngestionError`` for unsupported, malformed, encrypted, empty, or
    oversized inputs. Never executes embedded scripts or fetches resources.
    """
    extension = detect_extension(display_filename)
    if not content:
        raise IngestionError("Uploaded file is empty", code="empty_file")

    if extension == ".pdf":
        extracted = _extract_pdf(content, max_pages=max_pdf_pages)
    else:
        if content.startswith(_PDF_MAGIC):
            raise IngestionError(
                "File content looks like a PDF but the extension is not .pdf",
                code="extension_mismatch",
            )
        text = _normalize_text(_decode_text(content))
        extracted = ExtractedDocument(text=text, extension=extension)

    if len(extracted.text) > max_extracted_chars:
        raise IngestionError(
            f"Extracted text exceeds {max_extracted_chars} characters",
            code="too_much_text",
        )
    if not extracted.text.strip():
        raise IngestionError(
            "No extractable text found (scanned or empty document)",
            code="no_text",
        )
    return extracted


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$", re.MULTILINE)


def markdown_headings(text: str) -> List[Dict[str, object]]:
    """Return ``[{"start": offset, "title": str}]`` for Markdown headings."""
    return [
        {"start": m.start(), "title": m.group(2).strip()[:200]} for m in _HEADING_RE.finditer(text)
    ]


class UploadStorage:
    """Stores uploaded bytes under server-generated names inside ``root``."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, storage_name: str) -> Path:
        path = (self.root / storage_name).resolve()
        if path.parent != self.root:
            raise IngestionError("Invalid storage name", status=500)
        return path

    def save(self, doc_id: str, version: int, extension: str, content: bytes) -> str:
        self.ensure()
        storage_name = f"{doc_id}.v{version}{extension}"
        path = self._path_for(storage_name)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return storage_name

    def delete(self, storage_name: Optional[str]) -> bool:
        if not storage_name:
            return False
        path = self._path_for(storage_name)
        if path.is_file():
            path.unlink()
            return True
        return False

    def exists(self, storage_name: Optional[str]) -> bool:
        if not storage_name:
            return False
        return self._path_for(storage_name).is_file()
