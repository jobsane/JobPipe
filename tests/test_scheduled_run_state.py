from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from jobpipe.core.paths import JobPipePaths
from jobpipe.core.scheduled_run_state import (
    build_scheduled_run_payload,
    finish_scheduled_run,
    record_companion_check,
    start_scheduled_run,
)

# Fixed reference time: 2 hours after the test's "finished_at" timestamp so that
# freshness_status == "fresh" and overall_status == "ready" regardless of wall-clock date.
_FROZEN_NOW = datetime(2026, 4, 20, 10, 12, 0, tzinfo=timezone.utc)


def test_scheduled_run_payload_defaults_to_never_run(tmp_path) -> None:
    paths = JobPipePaths(repo_root=tmp_path, data_root=tmp_path)

    payload = build_scheduled_run_payload(paths)

    assert payload["schema_version"] == "jobpipe.scheduled-run-control.v1"
    assert payload["summary"]["status"] == "never_run"
    assert payload["summary"]["freshness_status"] == "never"
    assert payload["summary"]["companion_status"] == "unknown"


def test_scheduled_run_payload_tracks_last_success_and_companion_check(tmp_path) -> None:
    paths = JobPipePaths(repo_root=tmp_path, data_root=tmp_path)

    with patch("jobpipe.core.scheduled_run_state._utc_now", return_value=_FROZEN_NOW):
        start_scheduled_run(
            paths.scheduled_run_state_path,
            {
                "run_id": "scheduled_001",
                "flow_key": "scheduled_full_run",
                "label": "Scheduled operator flow",
                "status": "running",
                "started_at": "2026-04-20T08:00:00Z",
                "finished_at": "",
                "summary": "Scheduled flow started.",
                "log_excerpt": "",
                "max_jobs": 100,
                "with_suggestions": False,
                "allow_companion_drift": False,
                "companion_status": "",
                "steps": [],
            },
        )
        record_companion_check(
            paths.scheduled_run_state_path,
            {
                "status": "aligned",
                "companions": [
                    {
                        "id": "jobsync",
                        "status": "aligned",
                        "actual_branch": "main",
                        "actual_commit": "abc123",
                        "pinned_branch": "main",
                        "pinned_commit": "abc123",
                        "dirty": False,
                        "notes": [],
                    }
                ],
            },
        )
        finish_scheduled_run(
            paths.scheduled_run_state_path,
            "scheduled_001",
            {
                "run_id": "scheduled_001",
                "flow_key": "scheduled_full_run",
                "label": "Scheduled operator flow",
                "status": "succeeded",
                "started_at": "2026-04-20T08:00:00Z",
                "finished_at": "2026-04-20T08:12:00Z",
                "summary": "Scheduled flow completed successfully.",
                "log_excerpt": "Dashboard exported.",
                "max_jobs": 100,
                "with_suggestions": False,
                "allow_companion_drift": False,
                "companion_status": "aligned",
                "steps": [],
            },
        )

        payload = build_scheduled_run_payload(paths)

    assert payload["summary"]["status"] == "ready"
    assert payload["summary"]["last_success_at"] == "2026-04-20T08:12:00Z"
    assert payload["summary"]["companion_status"] == "aligned"
    assert payload["last_success"]["summary"] == "Scheduled flow completed successfully."
    assert payload["last_companion_check"]["status"] == "aligned"
