from __future__ import annotations

import json
from pathlib import Path

from jobpipe.cli.export_dashboard import _load_app_state_merged
from jobpipe.core.primary_db import (
    connect_primary_db,
    ensure_candidate,
    insert_application_event,
    upsert_application_summary,
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
