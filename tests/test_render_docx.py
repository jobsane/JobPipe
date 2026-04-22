from pathlib import Path


def test_render_returns_bytes(tmp_path):
    from jobpipe.authoring.render_docx import render_cover_letter_docx

    output = tmp_path / "cover_letter.docx"
    result = render_cover_letter_docx(
        data={
            "recipientName": "Hiring Manager",
            "senderName": "Jane Doe",
            "date": "2026-04-22",
            "body": ["Dear Hiring Manager,", "I am writing to apply.", "Sincerely,"],
        },
        output_path=output,
    )
    assert isinstance(result, bytes)
    assert len(result) > 0


def test_render_valid_docx_magic(tmp_path):
    """A .docx is a ZIP - first 4 bytes must be the PK magic number."""
    from jobpipe.authoring.render_docx import render_cover_letter_docx

    output = tmp_path / "cover_letter.docx"
    result = render_cover_letter_docx(
        data={
            "recipientName": "Test Co",
            "senderName": "Candidate",
            "date": "2026-04-22",
            "body": ["Paragraph one.", "Paragraph two."],
        },
        output_path=output,
    )
    assert result[:4] == b"PK\x03\x04", f"Not a valid ZIP/DOCX file (got {result[:4]!r})"


def test_no_crewai_import():
    """render_docx.py must not import crewai."""
    src = (
        Path(__file__).resolve().parent.parent
        / "jobpipe"
        / "authoring"
        / "render_docx.py"
    ).read_text(encoding="utf-8")
    assert "import crewai" not in src
    assert "from crewai" not in src
