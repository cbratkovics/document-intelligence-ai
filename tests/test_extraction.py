import pytest

from src.core.types import IngestionError
from src.utils.document_loader import (
    UploadStorage,
    detect_extension,
    extract_document,
    normalize_display_filename,
)
from tests.conftest import build_pdf

LIMITS = dict(max_extracted_chars=100_000, max_pdf_pages=10)


def test_filename_normalization_strips_paths_and_bounds_length():
    assert normalize_display_filename("../../etc/passwd.txt", 255) == "passwd.txt"
    assert normalize_display_filename("C:\\docs\\notes.md", 255) == "notes.md"
    with pytest.raises(IngestionError):
        normalize_display_filename("", 255)
    with pytest.raises(IngestionError):
        normalize_display_filename("a" * 300 + ".txt", 255)


def test_unsupported_and_missing_extensions_rejected():
    for name in ("run.exe", "archive.zip", "noext", "page.html", "report.docx"):
        with pytest.raises(IngestionError) as info:
            detect_extension(name)
        assert info.value.code == "unsupported_type"


def test_empty_and_whitespace_only_text_rejected():
    with pytest.raises(IngestionError) as info:
        extract_document("empty.txt", b"", **LIMITS)
    assert info.value.code == "empty_file"
    with pytest.raises(IngestionError) as info:
        extract_document("blank.txt", b"  \n\t \n", **LIMITS)
    assert info.value.code == "no_text"


def test_invalid_encoding_rejected_not_silently_decoded():
    with pytest.raises(IngestionError) as info:
        extract_document("latin.txt", "café".encode("latin-1") + b"\xff\xfe\xfa", **LIMITS)
    assert info.value.code == "invalid_encoding"


def test_utf8_bom_and_crlf_normalized():
    doc = extract_document("notes.txt", "\ufeffline one\r\nline two".encode("utf-8"), **LIMITS)
    assert doc.text == "line one\nline two"


def test_pdf_bytes_with_text_extension_rejected():
    with pytest.raises(IngestionError) as info:
        extract_document("sneaky.txt", build_pdf(["hello"]), **LIMITS)
    assert info.value.code == "extension_mismatch"


def test_malformed_pdf_rejected():
    with pytest.raises(IngestionError) as info:
        extract_document("broken.pdf", b"%PDF-1.4\ngarbage", **LIMITS)
    assert info.value.code in {"invalid_pdf", "no_text"}
    with pytest.raises(IngestionError) as info:
        extract_document("nota.pdf", b"not a pdf at all", **LIMITS)
    assert info.value.code == "invalid_pdf"


def test_pdf_page_spans_and_blank_pages():
    pdf = build_pdf(["First page text", "", "Third page text"])
    doc = extract_document("doc.pdf", pdf, **LIMITS)
    assert doc.page_count == 3
    assert [p.page_number for p in doc.pages] == [1, 3]
    for span in doc.pages:
        assert doc.text[span.char_start : span.char_end].strip()
    assert any("page 2" in w for w in doc.warnings)


def test_scanned_pdf_without_text_layer_rejected():
    with pytest.raises(IngestionError) as info:
        extract_document("scan.pdf", build_pdf(["", ""]), **LIMITS)
    assert info.value.code == "no_text"


def test_encrypted_pdf_rejected():
    from io import BytesIO

    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    writer.append(PdfReader(BytesIO(build_pdf(["secret"]))))
    writer.encrypt("owner-password")
    buffer = BytesIO()
    writer.write(buffer)
    with pytest.raises(IngestionError) as info:
        extract_document("locked.pdf", buffer.getvalue(), **LIMITS)
    assert info.value.code == "encrypted_pdf"


def test_page_and_text_limits_enforced():
    with pytest.raises(IngestionError) as info:
        extract_document(
            "many.pdf", build_pdf(["p"] * 3), max_extracted_chars=100_000, max_pdf_pages=2
        )
    assert info.value.code == "too_many_pages"
    with pytest.raises(IngestionError) as info:
        extract_document("big.txt", b"x" * 1001, max_extracted_chars=1000, max_pdf_pages=2)
    assert info.value.code == "too_much_text"


def test_rst_is_plain_text_without_directive_processing():
    text = ".. raw:: html\n\n   <script>alert(1)</script>\n\nBody text here."
    doc = extract_document("doc.rst", text.encode(), **LIMITS)
    assert doc.text == text


def test_upload_storage_uses_server_names_and_refuses_escape(tmp_path):
    storage = UploadStorage(tmp_path / "uploads")
    name = storage.save("abc123", 1, ".txt", b"data")
    assert name == "abc123.v1.txt"
    assert (tmp_path / "uploads" / name).read_bytes() == b"data"
    with pytest.raises(FileExistsError):
        storage.save("abc123", 1, ".txt", b"again")
    with pytest.raises(IngestionError):
        storage.delete("../escape.txt")
    assert storage.delete(name) is True
    assert storage.delete(name) is False
