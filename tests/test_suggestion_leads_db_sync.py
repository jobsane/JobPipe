from __future__ import annotations

import json

from jobpipe.cli.pull_suggested import _load_merged_queue
from jobpipe.core.primary_db import (
    connect_primary_db,
    ensure_candidate,
    list_suggestion_leads,
    mark_suggestion_lead_status,
    upsert_suggestion_lead,
)


def test_suggestion_leads_round_trip_and_status_updates(tmp_path):
    db_path = tmp_path / "jobpipe.sqlite"

    conn = connect_primary_db(db_path)
    ensure_candidate(conn, candidate_id="candidate-a")
    upsert_suggestion_lead(
        conn,
        {
            "suggestion_id": "suggestion_1",
            "candidate_id": "candidate-a",
            "platform": "finn",
            "external_id": "123456789",
            "job_url": "https://www.finn.no/job/fulltime/ad.html?finnkode=123456789",
            "job_id_hint": "finn_123456789",
            "suggested_at": "2026-04-16",
            "email_subject": "Ledige stillinger",
            "source": "gmail_suggestions",
            "status": "queued",
            "fetched_at": "",
            "last_error": "",
            "payload_json": {"platform": "finn", "finnkode": "123456789"},
            "created_at": "2026-04-16T10:00:00Z",
            "updated_at": "2026-04-16T10:00:00Z",
        },
    )
    conn.commit()

    rows = list_suggestion_leads(conn, "candidate-a", statuses=["queued"])
    assert len(rows) == 1
    assert rows[0]["external_id"] == "123456789"
    assert rows[0]["payload_json"]["finnkode"] == "123456789"

    mark_suggestion_lead_status(
        conn,
        "suggestion_1",
        status="fetched",
        fetched_at="2026-04-16T11:00:00Z",
        last_error="",
        updated_at="2026-04-16T11:00:00Z",
    )
    conn.commit()

    fetched_rows = list_suggestion_leads(conn, "candidate-a", statuses=["fetched"])
    assert len(fetched_rows) == 1
    assert fetched_rows[0]["fetched_at"] == "2026-04-16T11:00:00Z"
    conn.close()


def test_load_merged_queue_prefers_db_and_falls_back_to_file(tmp_path):
    db_path = tmp_path / "jobpipe.sqlite"
    suggested_path = tmp_path / "suggested_jobs.jsonl"

    conn = connect_primary_db(db_path)
    ensure_candidate(conn, candidate_id="candidate-a")
    upsert_suggestion_lead(
        conn,
        {
            "suggestion_id": "suggestion_1",
            "candidate_id": "candidate-a",
            "platform": "finn",
            "external_id": "123456789",
            "job_url": "https://db.example/finn",
            "job_id_hint": "finn_123456789",
            "suggested_at": "2026-04-16",
            "email_subject": "From DB",
            "source": "gmail_suggestions",
            "status": "queued",
            "fetched_at": "",
            "last_error": "",
            "payload_json": {"platform": "finn", "finnkode": "123456789", "job_url": "https://db.example/finn"},
            "created_at": "2026-04-16T10:00:00Z",
            "updated_at": "2026-04-16T10:00:00Z",
        },
    )
    conn.commit()
    conn.close()

    suggested_path.write_text(
        "\n".join(
            [
                json.dumps({"platform": "finn", "finnkode": "123456789", "job_url": "https://file.example/duplicate"}, ensure_ascii=False),
                json.dumps({"platform": "linkedin", "linkedin_job_id": "999", "job_url": "https://file.example/linkedin"}, ensure_ascii=False),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    queue = _load_merged_queue(suggested_path, db_path, "candidate-a")
    keyed = {
        (row.get("platform"), row.get("finnkode") or row.get("linkedin_job_id")): row
        for row in queue
    }

    assert len(queue) == 2
    assert keyed[("finn", "123456789")]["job_url"] == "https://db.example/finn"
    assert keyed[("linkedin", "999")]["job_url"] == "https://file.example/linkedin"
