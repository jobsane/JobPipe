from __future__ import annotations

from jobpipe.core.evaluation_state import load_job_catalog, load_processed_job_ids
from jobpipe.core.primary_db import (
    connect_primary_db,
    ensure_candidate,
    upsert_job,
    upsert_job_evaluation,
)


def test_load_job_catalog_reads_primary_db(tmp_path):
    db_path = tmp_path / "jobpipe.sqlite"

    conn = connect_primary_db(db_path)
    ensure_candidate(conn, candidate_id="candidate-a")
    upsert_job_evaluation(
        conn,
        {
            "candidate_id": "candidate-a",
            "job_id": "job-db",
            "run_id": "run-1",
            "run_mtime": 1713260000.0,
            "run_seen_at": "2026-04-17T10:00:00Z",
            "title": "Primary DB Job",
            "employer": "Example AS",
            "sector": "",
            "work_city": "Oslo",
            "work_county": "",
            "work_postalCode": "",
            "applicationDue": "",
            "source_url": "",
            "application_url": "",
            "triage_decision": "APPLY",
            "triage_confidence": 0.9,
            "triage_explanation": "",
            "triage_signals": "",
            "reverse_decision": "",
            "reverse_confidence": None,
            "reverse_rationale": "",
            "fit_score": 80,
            "pivot_score": 30,
            "final_decision": "APPLY",
            "final_confidence": 0.88,
            "recommendation_reason": "",
            "cv_focus": "",
            "feedback_flags": "",
            "description_snip": "",
            "skip_reason": "passed",
            "raw_index_json": "{}",
            "raw_match_json": "{}",
            "raw_pivot_json": "{}",
            "raw_moderator_json": "{}",
            "closed_at": "",
            "updated_at": "2026-04-17T10:05:00Z",
        },
    )
    conn.commit()
    conn.close()

    rows = load_job_catalog(
        primary_db_path=db_path,
        candidate_id="candidate-a",
    )

    assert [row["job_id"] for row in rows] == ["job-db"]
    assert rows[0]["title"] == "Primary DB Job"
    assert load_processed_job_ids(
        primary_db_path=db_path,
        candidate_id="candidate-a",
    ) == {"job-db"}


def test_load_job_catalog_returns_empty_when_db_missing(tmp_path):
    rows = load_job_catalog(
        primary_db_path=tmp_path / "missing.sqlite",
        candidate_id="candidate-a",
    )

    assert rows == []
    assert load_processed_job_ids(
        primary_db_path=tmp_path / "missing.sqlite",
        candidate_id="candidate-a",
    ) == set()


def test_load_processed_job_ids_excludes_catalog_only_jobs(tmp_path):
    """load_processed_job_ids must return only job_ids with an evaluation,
    NOT every catalog row. Pre-fix, the function returned the broader
    catalog and drain_queue's skip-processed filter blocked unevaluated jobs.
    """
    db_path = tmp_path / "jobpipe.sqlite"

    conn = connect_primary_db(db_path)
    ensure_candidate(conn, candidate_id="candidate-a")

    # Job in catalog only — never evaluated, must NOT be returned.
    upsert_job(
        conn,
        {
            "job_id": "job-unevaluated",
            "title": "Unevaluated Catalog Job",
            "employer": "X",
            "sector": "",
            "work_city": "Oslo",
            "work_county": "",
            "work_postalCode": "",
            "applicationDue": "",
            "source_url": "",
            "application_url": "",
            "closed_at": "",
            "first_seen_at": "2026-04-25T00:00:00Z",
            "updated_at": "2026-04-25T00:00:00Z",
            "job_metadata_json": "{}",
        },
    )

    upsert_job_evaluation(
        conn,
        {
            "candidate_id": "candidate-a",
            "job_id": "job-evaluated",
            "run_id": "run-1",
            "run_mtime": 1713260000.0,
            "run_seen_at": "2026-04-25T10:00:00Z",
            "title": "Evaluated Job",
            "employer": "Y",
            "sector": "",
            "work_city": "Oslo",
            "work_county": "",
            "work_postalCode": "",
            "applicationDue": "",
            "source_url": "",
            "application_url": "",
            "triage_decision": "APPLY",
            "triage_confidence": 0.9,
            "triage_explanation": "",
            "triage_signals": "",
            "reverse_decision": "",
            "reverse_confidence": None,
            "reverse_rationale": "",
            "fit_score": 80,
            "pivot_score": 30,
            "final_decision": "APPLY",
            "final_confidence": 0.88,
            "recommendation_reason": "",
            "cv_focus": "",
            "feedback_flags": "",
            "description_snip": "",
            "skip_reason": "passed",
            "raw_index_json": "{}",
            "raw_match_json": "{}",
            "raw_pivot_json": "{}",
            "raw_moderator_json": "{}",
            "closed_at": "",
            "updated_at": "2026-04-25T10:05:00Z",
        },
    )
    conn.commit()
    conn.close()

    assert load_processed_job_ids(
        primary_db_path=db_path,
        candidate_id="candidate-a",
    ) == {"job-evaluated"}
