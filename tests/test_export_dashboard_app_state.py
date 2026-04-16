from __future__ import annotations

import json

from jobpipe.cli.export_dashboard import _load_app_state_merged, build_payload
from jobpipe.core.primary_db import (
    connect_primary_db,
    ensure_candidate,
    insert_application_event,
    insert_generated_document,
    upsert_application_summary,
    upsert_job_evaluation,
    upsert_job_run_event,
)


def test_load_app_state_merged_prefers_db_and_falls_back_to_json(tmp_path):
    db_path = tmp_path / "jobpipe.sqlite"
    state_path = tmp_path / "application_state.json"

    conn = connect_primary_db(db_path)
    ensure_candidate(conn, candidate_id="candidate-a")
    insert_application_event(
        conn,
        {
            "application_event_id": "evt_1",
            "candidate_id": "candidate-a",
            "job_id": "job-db",
            "event_type": "interview",
            "event_at": "2026-04-16T10:00:00Z",
            "source": "gmail",
            "notes": "DB note",
            "metadata_json": {
                "stages": ["applied", "interview"],
                "outcome": "",
                "effective_status": "interview",
                "email_subject": "Interview invite",
                "email_date": "2026-04-16",
            },
            "created_at": "2026-04-16T10:00:01Z",
        },
    )
    upsert_application_summary(
        conn,
        {
            "candidate_id": "candidate-a",
            "job_id": "job-db",
            "current_stage": "interview",
            "current_outcome": "",
            "effective_status": "interview",
            "last_event_at": "2026-04-16T10:00:00Z",
            "notes_latest": "DB note",
            "updated_at": "2026-04-16T10:00:01Z",
        },
    )
    conn.commit()
    conn.close()

    state_path.write_text(
        json.dumps(
            {
                "applications": {
                    "job-db": {
                        "status": "applied",
                        "stages": ["applied"],
                        "outcome": "",
                        "updated_at": "2026-04-15T00:00:00Z",
                        "source": "manual",
                        "notes": "sidecar note should lose",
                    },
                    "job-json": {
                        "status": "shortlisted",
                        "stages": ["shortlisted"],
                        "outcome": "",
                        "updated_at": "2026-04-14T00:00:00Z",
                        "source": "manual",
                        "notes": "json fallback",
                    },
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    merged = _load_app_state_merged(state_path=state_path, db_path=db_path, candidate_id="candidate-a")

    assert merged["job-db"]["status"] == "interview"
    assert merged["job-db"]["source"] == "gmail"
    assert merged["job-db"]["stages"] == ["applied", "interview"]
    assert merged["job-db"]["notes"] == "DB note"

    assert merged["job-json"]["status"] == "shortlisted"
    assert merged["job-json"]["source"] == "manual"
    assert merged["job-json"]["notes"] == "json fallback"


def test_build_payload_includes_generated_documents_from_primary_db(tmp_path):
    out_runs = tmp_path / "out_runs"
    db_path = tmp_path / "jobpipe.sqlite"

    out_runs.mkdir()

    conn = connect_primary_db(db_path)
    ensure_candidate(conn, candidate_id="candidate-a")
    upsert_job_evaluation(
        conn,
        {
            "candidate_id": "candidate-a",
            "job_id": "job-doc",
            "run_id": "run-1",
            "run_mtime": 1713261600.0,
            "run_seen_at": "2026-04-16T10:00:00Z",
            "title": "Senior Product Manager",
            "employer": "Example AS",
            "sector": "",
            "work_city": "Oslo",
            "work_county": "Oslo",
            "work_postalCode": "0001",
            "applicationDue": "",
            "source_url": "https://example.test/job-doc",
            "application_url": "",
            "triage_decision": "APPLY",
            "triage_confidence": 0.92,
            "triage_explanation": "Looks strong.",
            "triage_signals": "safety:ok",
            "reverse_decision": "",
            "reverse_confidence": None,
            "reverse_rationale": "",
            "fit_score": 82,
            "pivot_score": 41,
            "final_decision": "APPLY",
            "final_confidence": 0.88,
            "recommendation_reason": "Strong fit.",
            "cv_focus": "Lead with SaaS and platform experience.",
            "feedback_flags": "",
            "description_snip": "",
            "skip_reason": "passed",
            "raw_index_json": json.dumps({"job_id": "job-doc"}, ensure_ascii=False),
            "raw_match_json": json.dumps({"overlaps": ["PM leadership"], "gaps": [], "hard_blockers": [], "notes": ""}, ensure_ascii=False),
            "raw_pivot_json": json.dumps({"pivot_type": "", "potential_risk": "", "why_it_matters": []}, ensure_ascii=False),
            "raw_moderator_json": json.dumps({"cv_focus": ["Platform"], "feedback_flags": []}, ensure_ascii=False),
            "closed_at": "",
            "updated_at": "2026-04-16T10:05:00Z",
        },
    )
    upsert_job_run_event(
        conn,
        {
            "candidate_id": "candidate-a",
            "run_id": "run-1",
            "job_id": "job-doc",
            "run_mtime": 1713261600.0,
            "seen_at": "2026-04-16T10:00:00Z",
            "final_decision": "APPLY",
            "final_confidence": 0.88,
            "triage_decision": "APPLY",
            "triage_confidence": 0.92,
            "fit_score": 82,
            "pivot_score": 41,
            "applicationDue": "",
            "title": "Senior Product Manager",
            "employer": "Example AS",
            "work_city": "Oslo",
            "work_county": "Oslo",
            "work_postalCode": "0001",
            "source_url": "https://example.test/job-doc",
            "application_url": "",
            "raw_index_json": json.dumps({"job_id": "job-doc"}, ensure_ascii=False),
            "updated_at": "2026-04-16T10:05:00Z",
        },
    )
    insert_generated_document(
        conn,
        {
            "document_id": "doc_1",
            "candidate_id": "candidate-a",
            "job_id": "job-doc",
            "evaluation_id": "run-1:job-doc",
            "kind": "cv_highlights_docx",
            "producer": "jobpipe_pipeline",
            "status": "draft",
            "storage_path": str(tmp_path / "07_cv_highlights.docx"),
            "preview_text": "Strong B2B SaaS and platform experience.",
            "document_json": {"cv_highlights": ["Leadership"]},
            "created_at": "2026-04-16T10:10:00Z",
            "updated_at": "2026-04-16T10:15:00Z",
        },
    )
    conn.commit()
    conn.close()

    payload = build_payload(
        out_runs,
        primary_db_path_=db_path,
        candidate_id="candidate-a",
    )

    job = next(j for j in payload["jobs"] if j["job_id"] == "job-doc")
    assert len(job["generated_documents"]) == 1
    assert job["generated_documents"][0]["kind"] == "cv_highlights_docx"
    assert job["generated_documents"][0]["status"] == "draft"
    assert job["generated_documents"][0]["preview_text"] == "Strong B2B SaaS and platform experience."


def test_build_payload_reads_jobs_and_events_from_primary_db(tmp_path):
    out_runs = tmp_path / "out_runs"
    db_path = tmp_path / "jobpipe.sqlite"

    out_runs.mkdir()

    conn = connect_primary_db(db_path)
    ensure_candidate(conn, candidate_id="candidate-a")
    upsert_job_evaluation(
        conn,
        {
            "candidate_id": "candidate-a",
            "job_id": "job-db",
            "run_id": "run-db",
            "run_mtime": 1713345600.0,
            "run_seen_at": "2026-04-17T08:00:00Z",
            "title": "Principal Product Lead",
            "employer": "DB Example AS",
            "sector": "",
            "work_city": "Oslo",
            "work_county": "Oslo",
            "work_postalCode": "0001",
            "applicationDue": "2026-04-30",
            "source_url": "https://example.test/job-db",
            "application_url": "",
            "triage_decision": "APPLY",
            "triage_confidence": 0.91,
            "triage_explanation": "Strong fit.",
            "triage_signals": "semantic_match",
            "reverse_decision": "",
            "reverse_confidence": None,
            "reverse_rationale": "",
            "fit_score": 84,
            "pivot_score": 33,
            "final_decision": "APPLY",
            "final_confidence": 0.88,
            "recommendation_reason": "Strong PM and platform overlap.",
            "cv_focus": "Platform leadership",
            "feedback_flags": "",
            "description_snip": "",
            "skip_reason": "passed",
            "raw_index_json": json.dumps({"job_id": "job-db"}, ensure_ascii=False),
            "raw_match_json": json.dumps({"overlaps": ["Leadership"], "gaps": [], "hard_blockers": [], "notes": ""}, ensure_ascii=False),
            "raw_pivot_json": json.dumps({"pivot_type": "", "potential_risk": "", "why_it_matters": []}, ensure_ascii=False),
            "raw_moderator_json": json.dumps({"cv_focus": ["Platform leadership"], "feedback_flags": []}, ensure_ascii=False),
            "closed_at": "",
            "updated_at": "2026-04-17T08:00:10Z",
        },
    )
    upsert_job_run_event(
        conn,
        {
            "candidate_id": "candidate-a",
            "run_id": "run-db",
            "job_id": "job-db",
            "run_mtime": 1713345600.0,
            "seen_at": "2026-04-17T08:00:00Z",
            "final_decision": "APPLY",
            "final_confidence": 0.88,
            "triage_decision": "APPLY",
            "triage_confidence": 0.91,
            "fit_score": 84,
            "pivot_score": 33,
            "applicationDue": "2026-04-30",
            "title": "Principal Product Lead",
            "employer": "DB Example AS",
            "work_city": "Oslo",
            "work_county": "Oslo",
            "work_postalCode": "0001",
            "source_url": "https://example.test/job-db",
            "application_url": "",
            "raw_index_json": json.dumps({"job_id": "job-db"}, ensure_ascii=False),
            "updated_at": "2026-04-17T08:00:10Z",
        },
    )
    conn.commit()
    conn.close()

    payload = build_payload(
        out_runs,
        primary_db_path_=db_path,
        candidate_id="candidate-a",
    )

    assert len(payload["jobs"]) == 1
    assert payload["jobs"][0]["job_id"] == "job-db"
    assert payload["jobs"][0]["title"] == "Principal Product Lead"
    assert payload["jobs"][0]["final_decision"] == "APPLY"
    assert len(payload["events"]) == 1
    assert payload["events"][0]["run_id"] == "run-db"
    assert payload["events"][0]["job_id"] == "job-db"
