from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from jobpipe.core.intake_pipe import CONNECTOR_NAV, POLICY_FULL_FEED, prepare_connector_record


def test_drain_queue_merge_only_writes_delta_without_run_feed(tmp_path: Path) -> None:
    nav_path = tmp_path / "nav_connector.jsonl"
    leads_path = tmp_path / "leads_connector.jsonl"
    delta_path = tmp_path / "jobs_delta.jsonl"

    nav_record = prepare_connector_record(
        {
            "job_id": "nav-smoke-1",
            "title": "Product Manager",
            "employer_name": "Example AS",
            "description_html": "Build useful internal tools.",
            "applicationUrl": "https://example.test/apply",
            "work_city": "Oslo",
        },
        connector_name=CONNECTOR_NAV,
        connector_source="nav",
        intake_channel="supabase",
        pretriage_policy=POLICY_FULL_FEED,
    )
    nav_path.write_text(json.dumps(nav_record, ensure_ascii=False) + "\n", encoding="utf-8")
    leads_path.write_text("", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "jobpipe.cli.drain_queue",
            "--data-root",
            str(tmp_path / "data-root"),
            "--merge-only",
            "--nav-connector",
            str(nav_path),
            "--leads-connector",
            str(leads_path),
            "--delta",
            str(delta_path),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "merge-only" in result.stdout
    assert "nav=1 leads=0 merged=1" in result.stdout
    assert "run_feed skipped" in result.stdout
    assert "jobpipe.cli.run_feed" not in result.stdout

    rows = [json.loads(line) for line in delta_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["job_id"] == "nav-smoke-1"
    assert rows[0]["intake_connector_names"] == ["nav_feed"]


def test_drain_queue_help_exposes_merge_only_flags() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "jobpipe.cli.drain_queue", "--help"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--merge-only" in result.stdout
    assert "--nav-connector" in result.stdout
    assert "--leads-connector" in result.stdout
