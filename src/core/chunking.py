"""Offset-preserving character chunker.

Limits are in *characters* of the normalized extracted text. Every chunk
records its ``[char_start, char_end)`` span, the page range it covers (PDF
only), and the nearest preceding Markdown heading (Markdown only). The
algorithm always makes progress, so it terminates for any input, and it never
emits whitespace-only chunks.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import List, Optional, Sequence

from ..utils.document_loader import PageSpan, markdown_headings
from .types import IngestionError, SourceLocation

_BOUNDARIES: Sequence[str] = ("\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " ")


@dataclass(frozen=True)
class Chunk:
    ordinal: int
    text: str
    location: SourceLocation

    @property
    def text_hash(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()[:16]


def _find_boundary(text: str, lo: int, hi: int) -> Optional[int]:
    """Best split point in ``(lo, hi]`` preferring stronger separators."""
    for sep in _BOUNDARIES:
        idx = text.rfind(sep, lo, hi)
        if idx != -1 and idx + len(sep) > lo:
            return idx + len(sep)
    return None


def _page_for(offset: int, pages: Sequence[PageSpan]) -> Optional[int]:
    for span in pages:
        if span.char_start <= offset < span.char_end:
            return span.page_number
    # Offsets that land in a separator between pages belong to the next page.
    for span in pages:
        if offset < span.char_start:
            return span.page_number
    return pages[-1].page_number if pages else None


def _section_for(offset: int, headings: Sequence[dict]) -> Optional[str]:
    current = None
    for heading in headings:
        if int(heading["start"]) <= offset:
            current = str(heading["title"])
        else:
            break
    return current


def chunk_text(
    text: str,
    *,
    chunk_size: int,
    chunk_overlap: int,
    max_chunks: int,
    pages: Sequence[PageSpan] = (),
    extension: str = ".txt",
) -> List[Chunk]:
    """Split ``text`` into overlapping chunks with provenance."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be >= 0 and < chunk_size")
    if max_chunks <= 0:
        raise ValueError("max_chunks must be positive")

    headings = markdown_headings(text) if extension == ".md" else []
    length = len(text)
    chunks: List[Chunk] = []
    start = 0
    min_step = max(1, chunk_size - chunk_overlap)

    while start < length:
        # Skip leading whitespace without losing offset accuracy.
        while start < length and text[start].isspace():
            start += 1
        if start >= length:
            break

        end = min(start + chunk_size, length)
        if end < length:
            boundary = _find_boundary(text, start + chunk_size // 2, end)
            if boundary is not None and boundary > start:
                end = boundary

        piece = text[start:end]
        stripped = piece.rstrip()
        real_end = start + len(stripped)
        if stripped.strip():
            if len(chunks) >= max_chunks:
                raise IngestionError(
                    f"Document produces more than {max_chunks} chunks",
                    code="too_many_chunks",
                )
            location = SourceLocation(
                char_start=start,
                char_end=real_end,
                page=_page_for(start, pages) if pages else None,
                page_end=_page_for(max(real_end - 1, start), pages) if pages else None,
                section=_section_for(start, headings) if headings else None,
            )
            chunks.append(Chunk(ordinal=len(chunks), text=stripped, location=location))

        if end >= length:
            break
        next_start = end - chunk_overlap
        # Move the overlap start forward to a whitespace boundary if one exists
        # inside the overlap region, so chunks do not start mid-word.
        probe = text.find(" ", next_start, end)
        if probe != -1 and probe + 1 < end:
            next_start = probe + 1
        if next_start <= start:
            next_start = start + min_step
        start = next_start

    return chunks
