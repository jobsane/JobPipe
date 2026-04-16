from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from jobpipe.cli.scan_gmail import _persist_gmail_status


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
