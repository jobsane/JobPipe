from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from jobpipe.cli.scan_gmail import _match_jobs, _match_jobs_by_source_refs, _persist_gmail_status


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_persist_gmail_status_dual_writes_state_and_db(tmp_path):
    state_path = tmp_path / "application_state.json"
    db_path = tmp_path / "jobpipe.sqlite"
    apps: dict = {}

    _persist_gmail_status(
        apps=apps,
        job_id="job-123",
        status="interview",
        parsed={"subject": "Invitasjon til intervju", "date": "2026-04-16"},
        existing={"notes": "Keep this"},
        state_path=state_path,
        db_path=db_path,
        candidate_id="candidate-a",
        dry_run=False,
    )

    assert apps["job-123"]["status"] == "interview"
    assert apps["job-123"]["source"] == "gmail"

    state = _load_json(state_path)
    entry = state["applications"]["job-123"]
    assert entry["status"] == "interview"
    assert entry["notes"] == "Keep this"
    assert entry["source"] == "gmail"

    con = sqlite3.connect(str(db_path))
    summary = con.execute(
        "SELECT current_stage, current_outcome, effective_status, notes_latest FROM application_summary "
        "WHERE candidate_id = ? AND job_id = ?",
        ["candidate-a", "job-123"],
    ).fetchone()
    events = con.execute(
        "SELECT event_type, source, notes FROM application_events WHERE candidate_id = ? AND job_id = ?",
        ["candidate-a", "job-123"],
    ).fetchall()
    con.close()

    assert summary == ("interview", "", "interview", "Keep this")
    assert len(events) == 1
    assert events[0] == ("interview", "gmail", "Keep this")


def test_persist_gmail_status_dry_run_only_updates_cache(tmp_path):
    state_path = tmp_path / "application_state.json"
    db_path = tmp_path / "jobpipe.sqlite"
    apps: dict = {}

    _persist_gmail_status(
        apps=apps,
        job_id="job-123",
        status="rejected",
        parsed={"subject": "Dessverre", "date": "2026-04-16"},
        existing={},
        state_path=state_path,
        db_path=db_path,
        candidate_id="candidate-a",
        dry_run=True,
    )

    assert apps["job-123"]["status"] == "rejected"
    assert not state_path.exists()
    assert not db_path.exists()


def test_match_jobs_requires_unique_high_confidence_match():
    catalog = [
        {"job_id": "job-1", "employer": "Example AS", "title": "Senior Product Manager", "fit_score": 90},
        {"job_id": "job-2", "employer": "Example Consulting", "title": "Designer", "fit_score": 70},
    ]
    matched = _match_jobs("Example AS", "Senior Product Manager", catalog)
    assert [row["job_id"] for row in matched] == ["job-1"]


def test_match_jobs_by_source_refs_prefers_exact_identifier_match():
    catalog = [
        {"job_id": "job-1", "employer": "Example AS", "title": "Senior Product Manager", "fit_score": 90},
        {"job_id": "job-2", "employer": "Example AS", "title": "Senior Product Manager", "fit_score": 70},
    ]
    source_index = {
        ("finn", "123"): {"job_id": "job-2"},
    }
    matched = _match_jobs_by_source_refs([("finn", "123")], source_index, catalog)
    assert [row["job_id"] for row in matched] == ["job-2"]
