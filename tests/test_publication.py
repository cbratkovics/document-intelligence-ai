from pathlib import Path

from scripts.check_publication import scan_paths


def _scan(tmp_path: Path, name: str, text: str) -> list[tuple[str, int, str]]:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return scan_paths([path], tmp_path)


def test_personal_preparation_heading_is_rejected(tmp_path):
    findings = _scan(
        tmp_path,
        "notes.md",
        "## Interview preparation\n",  # publication-check: allow=coaching-heading
    )
    assert findings == [("notes.md", 1, "coaching-heading")]


def test_role_targeting_advice_is_rejected(tmp_path):
    findings = _scan(
        tmp_path,
        "notes.md",
        "Tailor these bullets to the role.\n",  # publication-check: allow=role-targeting
    )
    assert findings == [("notes.md", 1, "role-targeting")]


def test_technical_and_sample_document_language_is_allowed(tmp_path):
    text = (
        "# Retrieval architecture\n"
        "A hiring manager submits an equipment request.\n"
        "The parser must resume processing after a recoverable error.\n"
        "Users may ingest arbitrary interview transcripts.\n"
    )
    assert _scan(tmp_path, "sample-document.md", text) == []


def test_suspicious_preparation_filename_is_rejected(tmp_path):
    findings = _scan(tmp_path, "interview-prep.md", "Technical notes only.\n")
    assert findings == [("interview-prep.md", 1, "suspicious-filename")]
