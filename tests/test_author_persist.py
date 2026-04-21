from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from jobpipe.authoring.output_models import GeneratedApplicationPackage
from jobpipe.authoring.persist import persist_generated_package


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE generated_documents (
            document_id TEXT PRIMARY KEY,
            candidate_id TEXT NOT NULL,
            job_id TEXT NOT NULL,
            evaluation_id TEXT NOT NULL DEFAULT '',
            kind TEXT NOT NULL,
            producer TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            storage_path TEXT NOT NULL DEFAULT '',
            preview_text TEXT NOT NULL DEFAULT '',
            document_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    return conn


def _package() -> GeneratedApplicationPackage:
    return GeneratedApplicationPackage(
        job_id="job-001",
        cover_letter_draft="Dette er et kort søknadsutkast.",
        tailored_cv_projection={"highlights": ["Ledet roadmap"], "experience_refs": ["evidence-1"]},
        evidence_refs=[{"evidence_unit_id": "evidence-1"}],
        gap_notes=["Ingen kritiske gap."],
    )


def test_persist_returns_document_id() -> None:
    conn = _conn()

    doc_id = persist_generated_package(conn, _package(), candidate_id="cand-1")

    assert doc_id.startswith("apkg_")


def test_persist_inserts_row() -> None:
    conn = _conn()

    persist_generated_package(conn, _package(), candidate_id="cand-1")
    row = conn.execute("SELECT COUNT(*) FROM generated_documents WHERE job_id = ?", ["job-001"]).fetchone()

    assert row[0] == 1


def test_persist_kind_is_author_package_json() -> None:
    conn = _conn()

    persist_generated_package(conn, _package(), candidate_id="cand-1")
    row = conn.execute("SELECT kind FROM generated_documents WHERE job_id = ?", ["job-001"]).fetchone()

    assert row[0] == "author_package_json"


def test_persist_document_json_roundtrip() -> None:
    conn = _conn()
    package = _package()

    persist_generated_package(conn, package, candidate_id="cand-1")
    row = conn.execute("SELECT document_json FROM generated_documents WHERE job_id = ?", ["job-001"]).fetchone()
    data = json.loads(row[0])

    assert data["cover_letter_draft"] == package.cover_letter_draft


def test_persist_no_crewai() -> None:
    text = Path("jobpipe/authoring/persist.py").read_text(encoding="utf-8")

    assert "crewai" not in text
    assert "autogen" not in text
    assert "langchain" not in text
