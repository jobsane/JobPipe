from __future__ import annotations

import sqlite3
from pathlib import Path

from jobpipe.model.schema import (
    ModeratorOut,
    PivotOut,
    ProfileMatchDimensions,
    ProfileMatchOut,
    TriageOut,
)
from jobpipe.model.schema import JobContext, RunMeta
from jobpipe.stages import application_pack as app_pack


def _make_ctx() -> JobContext:
    return JobContext(
        meta=RunMeta(run_id="run_123", pipeline_name="jobpipe_v1", created_at="2026-04-16T00:00:00Z"),
        job_id="job-123",
        job={"title": "Senior Product Owner", "employer_name": "Example Co", "sector": "SaaS"},
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


def test_generated_document_rows_builds_json_and_docx_rows(tmp_path):
    job_dir = tmp_path / "job-123"
    job_dir.mkdir()
    draft_path = job_dir / "application_pack_draft.json"
    draft_path.write_text('{"ok": true}', encoding="utf-8")
    docx_path = job_dir / "07_cv_highlights.docx"
    docx_path.write_bytes(b"fake-docx")

    rows = app_pack._generated_document_rows(
        _make_ctx(),
        {
            "positioning_headline": "Product owner with delivery depth",
            "cover_letter_angle": "Strong fit for platform ownership",
            "cv_highlights": ["Led roadmap", "Improved operations"],
            "cv_experience_refs": ["Example Co", "Another Co"],
        },
        draft_path,
        docx_path,
        candidate_id="candidate-a",
        generated_at="2026-04-29T00:00:00Z",
    )

    assert [row["kind"] for row in rows] == ["application_pack_json", "cv_highlights_docx"]
    assert all(row["candidate_id"] == "candidate-a" for row in rows)
    assert rows[0]["document_json"]["cv_highlights"] == ["Led roadmap", "Improved operations"]
    assert rows[1]["document_json"]["cv_experience_refs"] == ["Example Co", "Another Co"]


def test_generate_cv_docx_creates_document(tmp_path):
    out_path = app_pack._generate_cv_docx(
        {
            "positioning_headline": "Operations-focused product leader",
            "cover_letter_angle": "Strong fit for local-first execution-heavy roles.",
            "cv_highlights": ["Led roadmap execution", "Improved delivery flow"],
            "cv_experience_refs": ["Example Co", "Example Co"],
            "interview_prep": ["How would you sequence platform cleanup work?"],
        },
        {"title": "Senior Product Owner", "employer_name": "Example Co"},
        tmp_path,
    )

    assert out_path is not None
    assert out_path.exists()
    assert out_path.name == "07_cv_highlights.docx"


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


def test_build_application_pack_payload_includes_evidence_context(monkeypatch):
    monkeypatch.setattr(
        app_pack,
        "_DEFAULT_CANDIDATE_ID",
        "candidate-a",
    )
    ctx = _make_ctx()
    ctx.triage = TriageOut(
        triage_decision="APPLY_CANDIDATE",
        confidence=0.91,
        explanation="Strong product and platform overlap.",
        signals=["semantic_match"],
    )
    ctx.profile_match = ProfileMatchOut(
        fit_score=82,
        match_level="strong",
        dimensions=ProfileMatchDimensions(
            role_fit=88,
            domain_fit=75,
            seniority_fit=85,
            skills_fit=84,
            language_fit=70,
            location_fit=100,
        ),
        overlaps=["Product strategy", "Platform delivery"],
        gaps=["Marketplace exposure"],
        hard_blockers=[],
        notes="Strong core fit.",
    )
    ctx.pivot = PivotOut(
        pivot_score=70,
        pivot_type="adjacent",
        potential_risk="low",
        why_it_matters=["Adjacent role with strong overlap."],
    )
    ctx.moderator = ModeratorOut(
        final_decision="APPLY",
        confidence=0.88,
        recommendation_reason="Role aligns with current ownership and delivery scope.",
        cv_focus=["Platform leadership", "Stakeholder alignment"],
        feedback_flags=[],
    )

    payload = app_pack._build_application_pack_payload(
        ctx,
        {
            "resume_work": [
                {
                    "company": "Example SaaS",
                    "position": "Senior Product Manager",
                    "start": "2022-01-01",
                    "end": "present",
                    "summary": "Led product strategy and platform delivery.",
                    "highlights": [
                        "Led roadmap prioritization across platform teams and stakeholders.",
                        "Improved delivery predictability by 25% through workflow changes.",
                    ],
                }
            ],
            "resume_projects": [
                {
                    "name": "Platform migration",
                    "description": "Coordinated rollout and vendor alignment for a platform migration.",
                }
            ],
            "resume_education": [
                {
                    "institution": "BI",
                    "area": "Management",
                    "studyType": "Bachelor",
                }
            ],
        },
    )

    assert payload["decision_table"]["act_now"] in {"pursue_now", "review_then_pursue", "monitor", "skip"}
    assert len(payload["candidate_evidence_units"]) >= 3
    assert 1 <= len(payload["selected_evidence_units"]) <= 6
    assert any(unit["source_type"] == "work_highlight" for unit in payload["candidate_evidence_units"])
    assert payload["narrative_profile"]["core_identity"]
    assert payload["narrative_fragments"]
    assert payload["narrative_evidence_links"]
    assert payload["job_narrative_assessment"]["story_strength_score"] >= 0
    assert payload["motivation_brief"]


def test_sync_generated_documents_persists_evidence_and_narrative_state(monkeypatch, tmp_path):
    db_path = tmp_path / "jobpipe.sqlite"
    monkeypatch.setattr(app_pack, "_PRIMARY_DB_PATH", db_path)
    monkeypatch.setattr(app_pack, "_DEFAULT_CANDIDATE_ID", "candidate-a")

    ctx = _make_ctx()
    ctx.triage = TriageOut(
        triage_decision="APPLY_CANDIDATE",
        confidence=0.91,
        explanation="Strong product and platform overlap.",
        signals=["semantic_match"],
    )
    ctx.profile_match = ProfileMatchOut(
        fit_score=82,
        match_level="strong",
        dimensions=ProfileMatchDimensions(
            role_fit=88,
            domain_fit=75,
            seniority_fit=85,
            skills_fit=84,
            language_fit=70,
            location_fit=100,
        ),
        overlaps=["Product strategy", "Platform delivery"],
        gaps=["Marketplace exposure"],
        hard_blockers=[],
        notes="Strong core fit.",
    )
    ctx.pivot = PivotOut(
        pivot_score=70,
        pivot_type="adjacent",
        potential_risk="low",
        why_it_matters=["Adjacent role with strong overlap."],
    )
    ctx.moderator = ModeratorOut(
        final_decision="APPLY",
        confidence=0.88,
        recommendation_reason="Role aligns with current ownership and delivery scope.",
        cv_focus=["Platform leadership", "Stakeholder alignment"],
        feedback_flags=[],
    )

    resume_ctx = {
        "resume_work": [
            {
                "company": "Example SaaS",
                "position": "Senior Product Manager",
                "start": "2022-01-01",
                "end": "present",
                "summary": "Led product strategy and platform delivery.",
                "highlights": [
                    "Led roadmap prioritization across platform teams and stakeholders.",
                    "Improved delivery predictability by 25% through workflow changes.",
                ],
            }
        ],
        "resume_projects": [
            {
                "name": "Platform migration",
                "description": "Coordinated rollout and vendor alignment for a platform migration.",
            }
        ],
        "resume_education": [
            {
                "institution": "BI",
                "area": "Management",
                "studyType": "Bachelor",
            }
        ],
    }
    decision_context, evidence_context, narrative_context = app_pack._build_application_pack_contexts(ctx, resume_ctx)

    job_dir = tmp_path / "job-123"
    job_dir.mkdir()
    draft_path = job_dir / "application_pack_draft.json"
    draft_path.write_text('{"ok": true}', encoding="utf-8")

    app_pack._sync_generated_documents(
        ctx,
        {
            "positioning_headline": "Product owner with delivery depth",
            "cover_letter_angle": "Strong fit for platform ownership",
            "cv_highlights": ["Led roadmap", "Improved operations"],
            "cv_experience_refs": ["Example SaaS", "Example SaaS"],
        },
        draft_path=draft_path,
        docx_path=None,
        decision_context=decision_context,
        evidence_context=evidence_context,
        narrative_context=narrative_context,
    )

    con = sqlite3.connect(str(db_path))
    try:
        evidence_count = con.execute(
            "SELECT COUNT(*) FROM candidate_evidence_units WHERE candidate_id = ?",
            ["candidate-a"],
        ).fetchone()[0]
        narrative_profile = con.execute(
            """
            SELECT narrative_version_id, narrative_summary
            FROM candidate_narrative_profiles
            WHERE candidate_id = ? AND is_active = 1
            """,
            ["candidate-a"],
        ).fetchone()
        fragment_count = con.execute(
            "SELECT COUNT(*) FROM narrative_fragments WHERE candidate_id = ?",
            ["candidate-a"],
        ).fetchone()[0]
        link_count = con.execute(
            "SELECT COUNT(*) FROM narrative_evidence_links WHERE candidate_id = ?",
            ["candidate-a"],
        ).fetchone()[0]
        assessment = con.execute(
            """
            SELECT story_strength_score, motivation_brief
            FROM job_narrative_assessments
            WHERE candidate_id = ? AND job_id = ?
            """,
            ["candidate-a", "job-123"],
        ).fetchone()
    finally:
        con.close()

    assert evidence_count >= 3
    assert narrative_profile is not None
    assert narrative_profile[0]
    assert narrative_profile[1]
    assert fragment_count >= 3
    assert link_count >= 1
    assert assessment is not None
    assert assessment[0] >= 0
    assert assessment[1]
