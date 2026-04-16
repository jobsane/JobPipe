from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from jobpipe.cli.mark_status import add_stage


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_add_stage_dual_writes_state_and_db(tmp_path):
    state_path = tmp_path / "application_state.json"
    db_path = tmp_path / "jobpipe.sqlite"

    add_stage(
        job_id="job-123",
        token="shortlisted",
        state_path=state_path,
        notes="Looks strong",
        source="manual",
        db_path=db_path,
        candidate_id="candidate-a",
    )

    state = _load_json(state_path)
    entry = state["applications"]["job-123"]
    assert entry["stages"] == ["shortlisted"]
    assert entry["status"] == "shortlisted"
    assert entry["notes"] == "Looks strong"

    con = sqlite3.connect(str(db_path))
    summary = con.execute(
        "SELECT current_stage, current_outcome, effective_status, notes_latest FROM application_summary "
        "WHERE candidate_id = ? AND job_id = ?",
        ["candidate-a", "job-123"],
    ).fetchone()
    assert summary == ("shortlisted", "", "shortlisted", "Looks strong")

    events = con.execute(
        "SELECT event_type, source, notes FROM application_events WHERE candidate_id = ? AND job_id = ?",
        ["candidate-a", "job-123"],
    ).fetchall()
    con.close()

    assert len(events) == 1
    assert events[0] == ("shortlisted", "manual", "Looks strong")


def test_clear_removes_state_and_db_tracking(tmp_path):
    state_path = tmp_path / "application_state.json"
    db_path = tmp_path / "jobpipe.sqlite"

    add_stage(
        job_id="job-123",
        token="applied",
        state_path=state_path,
        notes="Submitted",
        source="manual",
        db_path=db_path,
        candidate_id="candidate-a",
    )
    add_stage(
        job_id="job-123",
        token="clear",
        state_path=state_path,
        source="manual",
        db_path=db_path,
        candidate_id="candidate-a",
    )

    state = _load_json(state_path)
    assert "job-123" not in state["applications"]

    con = sqlite3.connect(str(db_path))
    summary_count = con.execute(
        "SELECT COUNT(*) FROM application_summary WHERE candidate_id = ? AND job_id = ?",
        ["candidate-a", "job-123"],
    ).fetchone()[0]
    event_count = con.execute(
        "SELECT COUNT(*) FROM application_events WHERE candidate_id = ? AND job_id = ?",
        ["candidate-a", "job-123"],
    ).fetchone()[0]
    con.close()

    assert summary_count == 0
    assert event_count == 0
