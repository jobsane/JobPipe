from __future__ import annotations

import json

from jobpipe.core.job_catalog import canonical_job_row, ingest_catalog_job, job_source_record_row
from jobpipe.core.primary_db import (
    connect_primary_db,
    ensure_candidate,
    mark_pipeline_run_finished,
    mark_source_records_inactive,
    upsert_job,
    upsert_job_source_record,
    upsert_pipeline_run,
)


def test_canonical_job_helpers_build_expected_rows():
    job = {
        "uuid": "nav-123",
        "title": "Senior Product Manager",
        "normalized_title": "Product Manager",
        "employer_name": "Example AS",
        "description_html": "<p>Lead product work.</p>",
        "sourceurl": "https://example.test/job/nav-123",
        "applicationUrl": "https://example.test/apply/nav-123",
        "applicationDue": "2026-05-01",
        "work_city": "Oslo",
        "work_county": "Oslo",
        "work_postalCode": "0001",
        "sector": "Private",
        "status": "ACTIVE",
        "cat_name": "Product",
    }

    canonical = canonical_job_row(job, "2026-04-17T10:00:00Z")
    source_record = job_source_record_row(job, "nav_sheet", "2026-04-17T10:00:00Z")

    assert canonical["job_id"] == "nav-123"
    assert canonical["title"] == "Product Manager"
    assert canonical["employer"] == "Example AS"
    assert canonical["description_text"] == "Lead product work."
    assert canonical["job_metadata_json"]["cat_name"] == "Product"

    assert source_record["job_id"] == "nav-123"
    assert source_record["source_name"] == "nav_sheet"
    assert source_record["source_job_key"] == "nav-123"
    assert source_record["is_active"] == 1
    assert canonical["dedupe_key"] == "product manager|example as|oslo|0001|2026-05-01"


def test_job_catalog_tables_and_pipeline_runs_roundtrip(tmp_path):
    db_path = tmp_path / "jobpipe.sqlite"
    conn = connect_primary_db(db_path)
    try:
        ensure_candidate(conn, candidate_id="default")
        upsert_job(
            conn,
            {
                "job_id": "nav-123",
                "dedupe_key": "product manager|example as|oslo|2026-05-01|https://example.test/job/nav-123",
                "title": "Product Manager",
                "employer": "Example AS",
                "work_city": "Oslo",
                "work_county": "Oslo",
                "work_postalCode": "0001",
                "applicationDue": "2026-05-01",
                "source_url": "https://example.test/job/nav-123",
                "application_url": "https://example.test/apply/nav-123",
                "description_text": "Lead product work.",
                "description_html": "<p>Lead product work.</p>",
                "sector": "Private",
                "job_metadata_json": {"cat_name": "Product"},
                "content_hash": "hash-1",
                "first_seen_at": "2026-04-17T10:00:00Z",
                "last_seen_at": "2026-04-17T10:00:00Z",
                "closed_at": "",
                "updated_at": "2026-04-17T10:00:00Z",
            },
        )
        upsert_job_source_record(
            conn,
            {
                "source_record_id": "src-1",
                "source_name": "nav_sheet",
                "source_job_key": "nav-123",
                "job_id": "nav-123",
                "seen_at": "2026-04-17T10:00:00Z",
                "last_seen_at": "2026-04-17T10:00:00Z",
                "is_active": 1,
                "source_url": "https://example.test/job/nav-123",
                "work_city": "Oslo",
                "work_county": "Oslo",
                "work_postalCode": "0001",
                "applicationDue": "2026-05-01",
                "content_hash": "hash-1",
                "raw_payload_json": {"uuid": "nav-123"},
                "updated_at": "2026-04-17T10:00:00Z",
            },
        )
        upsert_pipeline_run(
            conn,
            {
                "run_id": "run-1",
                "candidate_id": "default",
                "profile_version_id": "",
                "config_version": "jobpipe_v1",
                "jobs_path": "jobs.jsonl",
                "max_jobs": 50,
                "status": "running",
                "started_at": "2026-04-17T10:00:00Z",
                "finished_at": "",
                "jobs_seen": 0,
                "jobs_failed": 0,
                "source_batch_json": {"jobs_path": "jobs.jsonl"},
                "updated_at": "2026-04-17T10:00:00Z",
            },
        )
        mark_pipeline_run_finished(
            conn,
            run_id="run-1",
            status="completed",
            finished_at="2026-04-17T10:05:00Z",
            jobs_seen=2,
            jobs_failed=0,
        )
        mark_source_records_inactive(
            conn,
            "nav_sheet",
            ["nav-123"],
            seen_at="2026-04-18T08:00:00Z",
        )
        conn.commit()

        job_row = conn.execute(
            "SELECT closed_at, last_seen_at FROM jobs WHERE job_id = ?",
            ["nav-123"],
        ).fetchone()
        source_row = conn.execute(
            "SELECT is_active, last_seen_at FROM job_source_records WHERE source_record_id = ?",
            ["src-1"],
        ).fetchone()
        run_row = conn.execute(
            "SELECT status, finished_at, jobs_seen, jobs_failed FROM pipeline_runs WHERE run_id = ?",
            ["run-1"],
        ).fetchone()
    finally:
        conn.close()

    assert job_row is not None
    assert job_row[0] == "2026-04-18T08:00:00Z"
    assert source_row is not None
    assert source_row[0] == 0
    assert source_row[1] == "2026-04-18T08:00:00Z"
    assert run_row is not None
    assert run_row[0] == "completed"
    assert run_row[1] == "2026-04-17T10:05:00Z"
    assert run_row[2] == 2
    assert run_row[3] == 0


def test_ingest_catalog_job_prefers_nav_but_enriches_from_finn(tmp_path):
    db_path = tmp_path / "jobpipe.sqlite"
    conn = connect_primary_db(db_path)
    try:
        nav_job = {
            "uuid": "nav-123",
            "job_id": "nav-123",
            "title": "Senior Product Manager",
            "normalized_title": "Senior Product Manager",
            "employer_name": "Example AS",
            "description_html": "",
            "sourceurl": "https://nav.example/job/nav-123",
            "applicationUrl": "",
            "applicationDue": "2026-05-01",
            "work_city": "Oslo",
            "work_postalCode": "0001",
            "status": "ACTIVE",
        }
        finn_job = {
            "job_id": "finn_555",
            "finnkode": "555",
            "title": "Senior Product Manager",
            "normalized_title": "Senior Product Manager",
            "employer_name": "Example AS",
            "description_html": "<p>Lead product strategy across the full portfolio.</p>",
            "sourceurl": "https://www.finn.no/job/fulltime/ad.html?finnkode=555",
            "applicationUrl": "https://apply.example/finn-555",
            "applicationDue": "2026-05-01",
            "work_city": "Oslo",
            "work_postalCode": "0001",
            "status": "ACTIVE",
        }

        nav_result = ingest_catalog_job(conn, nav_job, source_name="nav_sheet", seen_at="2026-04-17T10:00:00Z")
        finn_result = ingest_catalog_job(conn, finn_job, source_name="finn", seen_at="2026-04-17T11:00:00Z")
        conn.commit()

        row = conn.execute(
            """
            SELECT job_id, source_url, application_url, description_text, job_metadata_json
            FROM jobs
            WHERE job_id = ?
            """,
            [nav_result["job_id"]],
        ).fetchone()
        source_rows = conn.execute(
            "SELECT source_name, source_job_key, job_id FROM job_source_records ORDER BY source_name",
        ).fetchall()
    finally:
        conn.close()

    assert nav_result["job_id"] == finn_result["job_id"]
    assert row is not None
    assert row[0] == "nav-123"
    assert row[1] == "https://nav.example/job/nav-123"
    assert row[2] == "https://apply.example/finn-555"
    assert "Lead product strategy" in row[3]
    metadata = json.loads(row[4])
    assert metadata["_canonical_source_name"] == "nav_sheet"
    assert {tuple(item[:2]) for item in source_rows} == {
        ("finn", "555"),
        ("nav_sheet", "nav-123"),
    }
