from __future__ import annotations

import json
import sqlite3

from jobpipe.cli import record_reactive_resume_document
from jobpipe.model import ReactiveResumeRenderedDocumentRef
from jobpipe.runtime import record_reactive_resume_document_ref


def test_record_reactive_resume_document_ref_writes_generated_documents(tmp_path) -> None:
    db_path = tmp_path / "jobpipe.sqlite"

    record_reactive_resume_document_ref(
        db_path,
        ReactiveResumeRenderedDocumentRef(
            document_id="doc-rr-1",
            candidate_id="candidate-a",
            job_id="job-123",
            evaluation_id="run-123",
            kind="tailored_cv_docx",
            storage_path="C:/tmp/tailored_cv.docx",
            status="ready",
            producer="reactive_resume",
            updated_at="2026-04-20T12:00:00Z",
            preview_text="Tailored CV",
            document_json={"template": "ats-safe"},
        ),
    )

    con = sqlite3.connect(str(db_path))
    row = con.execute(
        """
        SELECT kind, producer, status, storage_path, preview_text
        FROM generated_documents
        WHERE candidate_id = ? AND job_id = ?
        """,
        ["candidate-a", "job-123"],
    ).fetchone()
    con.close()

    assert row == ("tailored_cv_docx", "reactive_resume", "ready", "C:/tmp/tailored_cv.docx", "Tailored CV")


def test_record_reactive_resume_document_cli_runtime_profile_uses_live_local_db(tmp_path, monkeypatch, capsys) -> None:
    data_root = tmp_path / "JobpipeData"
    monkeypatch.setenv("JOBPIPE_DATA_DIR", str(data_root))

    record_reactive_resume_document.main(
        [
            "job-rr-2",
            "tailored_cv_docx",
            "C:/tmp/cv.docx",
            "--candidate-id",
            "candidate-b",
            "--runtime-profile",
            "live_local",
            "--document-json",
            '{"template": "default"}',
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert output["job_id"] == "job-rr-2"

    con = sqlite3.connect(str(data_root / "db" / "jobpipe.sqlite"))
    row = con.execute(
        """
        SELECT kind, storage_path
        FROM generated_documents
        WHERE candidate_id = ? AND job_id = ?
        """,
        ["candidate-b", "job-rr-2"],
    ).fetchone()
    con.close()

    assert row == ("tailored_cv_docx", "C:/tmp/cv.docx")
