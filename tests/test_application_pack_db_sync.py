"""Tests for the current application_pack stage helpers.

The DB-sync and old context-builder tests were removed when the profile_layer
refactor (try/v3-triage) eliminated _sync_generated_documents,
_build_application_pack_contexts, and the primary-DB dependency.  This file
covers the helpers that survived the refactor.
"""

from __future__ import annotations

from pathlib import Path

from jobpipe.stages import application_pack as app_pack


def test_generate_cv_docx_creates_document(tmp_path: Path) -> None:
    """_generate_cv_docx writes a DOCX file and returns None."""
    pack_data = {
        "positioning_headline": "Operations-focused product leader",
        "cover_letter_angle": "Strong fit for local-first execution-heavy roles.",
        "cv_highlights": ["Led roadmap execution", "Improved delivery flow"],
        "cv_experience_refs": ["Example Co", "Example Co"],
        "interview_prep": ["How would you sequence platform cleanup work?"],
    }
    job_input = {"title": "Senior Product Owner", "employer_name": "Example Co"}

    result = app_pack._generate_cv_docx(pack_data, job_input, tmp_path)

    assert result is None
    out_path = tmp_path / "07_cv_highlights.docx"
    assert out_path.exists()
    assert out_path.stat().st_size > 0


def test_generate_cv_docx_skips_when_no_highlights(tmp_path: Path) -> None:
    """_generate_cv_docx returns early (None) when cv_highlights is empty."""
    result = app_pack._generate_cv_docx({}, {"title": "Test"}, tmp_path)
    assert result is None
    assert not (tmp_path / "07_cv_highlights.docx").exists()
