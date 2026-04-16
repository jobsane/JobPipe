from __future__ import annotations

import sqlite3
from pathlib import Path

from jobpipe.core.schema import JobContext, RunMeta
from jobpipe.stages import application_pack as app_pack


def _make_ctx() -> JobContext:
    return JobContext(
        meta=RunMeta(run_id="run_123", pipeline_name="jobpipe_v1", created_at="2026-04-16T00:00:00Z"),
        job_id="job-123",
        job={"title": "Senior Product Owner", "employer_name": "Example Co"},
        profile_pack="profile",
    )


def test_sync_generated_documents_registers_json_and_docx(monkeypatch, tmp_path):
    db_path = tmp_path / "jobpipe.sqlite"
    monkeypatch.setattr(app_pack, "_PRIMARY_DB_PATH", db_path)
    monkeypatch.setattr(app_pack, "_DEFAULT_CANDIDATE_ID", "candidate-a")

    job_dir = tmp_path / "job-123"
    job_dir.mkdir()
    draft_path = job_dir / "application_pack_draft.json"
    draft_path.write_text('{"ok": true}', encoding="utf-8")
    docx_path = job_dir / "07_cv_highlights.docx"
    docx_path.write_bytes(b"fake-docx")

    pack_data = {
        "positioning_headline": "Product owner with delivery depth",
        "cover_letter_angle": "Strong fit for platform ownership",
        "cv_highlights": ["Led roadmap", "Improved operations"],
        "cv_experience_refs": ["Example Co", "Another Co"],
    }

    app_pack._sync_generated_documents(_make_ctx(), pack_data, draft_path, docx_path)

    con = sqlite3.connect(str(db_path))
    rows = con.execute(
        "SELECT kind, producer, status, storage_path FROM generated_documents WHERE candidate_id = ? AND job_id = ? ORDER BY kind",
        ["candidate-a", "job-123"],
    ).fetchall()
    con.close()

    assert len(rows) == 2
    assert rows[0][0] == "application_pack_json"
    assert rows[1][0] == "cv_highlights_docx"
    assert all(row[1] == "jobpipe_pipeline" for row in rows)
    assert all(row[2] == "draft" for row in rows)
    assert str(draft_path.resolve()) in {rows[0][3], rows[1][3]}
    assert str(docx_path.resolve()) in {rows[0][3], rows[1][3]}


def test_sync_generated_documents_handles_missing_docx(monkeypatch, tmp_path):
    db_path = tmp_path / "jobpipe.sqlite"
    monkeypatch.setattr(app_pack, "_PRIMARY_DB_PATH", db_path)
    monkeypatch.setattr(app_pack, "_DEFAULT_CANDIDATE_ID", "candidate-a")

    job_dir = tmp_path / "job-123"
    job_dir.mkdir()
    draft_path = job_dir / "application_pack_draft.json"
    draft_path.write_text('{"ok": true}', encoding="utf-8")

    app_pack._sync_generated_documents(
        _make_ctx(),
        {
            "positioning_headline": "Headline",
            "cover_letter_angle": "Angle",
            "cv_highlights": [],
            "cv_experience_refs": [],
        },
        draft_path,
        None,
    )

    con = sqlite3.connect(str(db_path))
    count = con.execute(
        "SELECT COUNT(*) FROM generated_documents WHERE candidate_id = ? AND job_id = ?",
        ["candidate-a", "job-123"],
    ).fetchone()[0]
    con.close()

    assert count == 1
