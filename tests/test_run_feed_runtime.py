from __future__ import annotations

import json

from jobpipe.cli.run_feed import (
    _build_repaired_index_record,
    _repair_missing_index_entries,
)


def test_build_repaired_index_record_reads_known_artifacts(tmp_path) -> None:
    job_dir = tmp_path / "job-1"
    job_dir.mkdir()

    (job_dir / "00_input.json").write_text(
        json.dumps({"title": "PM", "employer_name": "Acme"}),
        encoding="utf-8",
    )
    (job_dir / "01_triage.json").write_text(
        json.dumps({"decision": "REVIEW", "confidence": 0.61, "signals": ["sim:0.41"]}),
        encoding="utf-8",
    )
    (job_dir / "05_moderator.json").write_text(
        json.dumps({"final_decision": "APPLY", "fit_score": 71, "pivot_score": 63}),
        encoding="utf-8",
    )

    record = _build_repaired_index_record(job_dir, "job-1")

    assert record == {
        "job_id": "job-1",
        "title": "PM",
        "employer": "Acme",
        "triage_decision": "REVIEW",
        "triage_confidence": 0.61,
        "triage_signals": ["sim:0.41"],
        "final_decision": "APPLY",
        "fit_score": 71,
        "pivot_score": 63,
        "repaired": True,
    }


def test_repair_missing_index_entries_appends_only_missing_jobs(tmp_path) -> None:
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()

    index_path = run_dir / "index.jsonl"
    index_path.write_text(
        json.dumps({"job_id": "job-existing", "title": "Existing"}) + "\n",
        encoding="utf-8",
    )

    existing_dir = run_dir / "job-existing"
    existing_dir.mkdir()
    (existing_dir / "00_input.json").write_text(json.dumps({"title": "Existing"}), encoding="utf-8")

    missing_dir = run_dir / "job-missing"
    missing_dir.mkdir()
    (missing_dir / "00_input.json").write_text(
        json.dumps({"title": "Missing", "employer_name": "Acme"}),
        encoding="utf-8",
    )
    (missing_dir / "01_triage.json").write_text(
        json.dumps({"decision": "SKIP", "confidence": 0.8, "signals": []}),
        encoding="utf-8",
    )
    (missing_dir / "05_moderator.json").write_text(
        json.dumps({"final_decision": "SKIP", "fit_score": 12, "pivot_score": 5}),
        encoding="utf-8",
    )

    repaired = _repair_missing_index_entries(str(run_dir))

    assert repaired == 1

    lines = index_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    repaired_record = json.loads(lines[1])
    assert repaired_record["job_id"] == "job-missing"
    assert repaired_record["repaired"] is True
