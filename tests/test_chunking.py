import pytest

from src.core.chunking import chunk_text
from src.core.types import IngestionError
from src.utils.document_loader import PageSpan


def _check_offsets(text, chunks):
    for chunk in chunks:
        loc = chunk.location
        assert text[loc.char_start : loc.char_end] == chunk.text


def test_offsets_map_back_to_source_and_overlap_is_respected():
    text = " ".join(f"word{i}" for i in range(400))
    chunks = chunk_text(text, chunk_size=100, chunk_overlap=20, max_chunks=1000)
    assert len(chunks) > 3
    _check_offsets(text, chunks)
    assert all(len(c.text) <= 100 for c in chunks)
    for prev, nxt in zip(chunks, chunks[1:]):
        assert nxt.location.char_start < prev.location.char_end  # overlap
        assert nxt.location.char_start > prev.location.char_start  # progress
        assert prev.location.char_end - nxt.location.char_start <= 20
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))


def test_progress_on_text_without_separators():
    text = "x" * 1000
    chunks = chunk_text(text, chunk_size=100, chunk_overlap=30, max_chunks=1000)
    _check_offsets(text, chunks)
    assert chunks[-1].location.char_end == 1000
    assert all(len(c.text) <= 100 for c in chunks)


def test_unicode_and_whitespace_only():
    text = "Ünïcödé façade — naïve résumé. " * 30
    chunks = chunk_text(text, chunk_size=80, chunk_overlap=10, max_chunks=100)
    _check_offsets(text, chunks)
    assert chunk_text("   \n\n\t", chunk_size=50, chunk_overlap=0, max_chunks=10) == []


def test_markdown_sections_including_repeated_headings():
    text = "# Intro\n\nalpha text.\n\n# Details\n\nbeta text.\n\n# Details\n\ngamma text."
    chunks = chunk_text(text, chunk_size=30, chunk_overlap=0, max_chunks=100, extension=".md")
    _check_offsets(text, chunks)
    by_word = {}
    for chunk in chunks:
        for word in ("alpha", "beta", "gamma"):
            if word in chunk.text:
                by_word[word] = chunk.location.section
    assert by_word["alpha"] == "Intro"
    assert by_word["beta"] == "Details"
    assert by_word["gamma"] == "Details"
    plain = chunk_text(text, chunk_size=30, chunk_overlap=0, max_chunks=100, extension=".txt")
    assert all(c.location.section is None for c in plain)


def test_page_ranges_cross_page_boundaries_and_no_pages_for_text():
    page1 = "one one one"
    page2 = "two " * 60
    text = page1 + "\n\n" + page2.strip()
    pages = [PageSpan(1, 0, len(page1)), PageSpan(2, len(page1) + 2, len(text))]
    chunks = chunk_text(text, chunk_size=150, chunk_overlap=0, max_chunks=100, pages=pages)
    _check_offsets(text, chunks)
    assert chunks[0].location.page == 1
    assert chunks[-1].location.page_end == 2
    spanning = [c for c in chunks if c.location.page != c.location.page_end]
    assert spanning, "expected a chunk that spans both pages"
    no_pages = chunk_text(text, chunk_size=150, chunk_overlap=0, max_chunks=100)
    assert all(c.location.page is None for c in no_pages)


def test_limits_and_invalid_configuration():
    with pytest.raises(IngestionError) as info:
        chunk_text("a " * 500, chunk_size=20, chunk_overlap=0, max_chunks=3)
    assert info.value.code == "too_many_chunks"
    with pytest.raises(ValueError):
        chunk_text("abc", chunk_size=10, chunk_overlap=10, max_chunks=5)
    with pytest.raises(ValueError):
        chunk_text("abc", chunk_size=0, chunk_overlap=0, max_chunks=5)
