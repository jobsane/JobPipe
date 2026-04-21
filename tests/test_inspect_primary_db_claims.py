from __future__ import annotations

import json
import sys

import pytest

from jobpipe.cli import inspect_primary_db
from jobpipe.core.primary_db import (
    connect_primary_db,
    ensure_candidate,
    replace_job_claims,
    replace_job_selection_signals,
    upsert_job,
    upsert_job_selection_assessment,
)


TS = "2026-04-21T10:00:00Z"


def _insert_job(db_path, job_id: str = "job-claims-1") -> None:
    conn = connect_primary_db(db_path)
    try:
        ensure_candidate(conn, "default")
        upsert_job(
            conn,
            {
                "job_id": job_id,
                "dedupe_key": f"{job_id}|example",
                "title": "Product Manager",
                "employer": "Example AS",
                "updated_at": TS,
            },
        )
        conn.commit()
    finally:
        conn.close()


def _insert_claim_layer_rows(db_path, job_id: str = "job-claims-1") -> None:
    conn = connect_primary_db(db_path)
    try:
        replace_job_claims(
            conn,
            job_id,
            [
                {
                    "job_id": job_id,
                    "claim_id": "claim-1",
                    "claim_type": "must_requirement",
                    "claim_strength": "explicit_must",
                    "claim_subject_type": "capability",
                    "claim_text": "Must have roadmap experience.",
                    "confidence_score": 0.95,
                    "importance_score": 0.9,
                    "claim_json": {"source": "requirements"},
                    "created_at": TS,
                    "updated_at": TS,
                },
                {
                    "job_id": job_id,
                    "claim_id": "claim-2",
                    "claim_type": "responsibility",
                    "claim_strength": "explicit_must",
                    "claim_subject_type": "capability",
                    "claim_text": "Lead product discovery.",
                    "confidence_score": 0.9,
                    "importance_score": 0.8,
                    "claim_json": {"source": "responsibilities"},
                    "created_at": TS,
                    "updated_at": TS,
                },
            ],
        )
        replace_job_selection_signals(
            conn,
            job_id,
            [
                {
                    "job_id": job_id,
                    "signal_id": "signal-1",
                    "signal_type": "screening_gate",
                    "signal_label": "Roadmap ownership",
                    "selection_stage": "first_pass",
                    "signal_strength": "strong",
                    "importance_score": 0.85,
                    "signal_json": {"claim_id": "claim-1"},
                    "created_at": TS,
                    "updated_at": TS,
                }
            ],
        )
        upsert_job_selection_assessment(
            conn,
            {
                "candidate_id": "default",
                "job_id": job_id,
                "evaluation_id": "eval-1",
                "structural_pass": 1,
                "screenability_score": 76,
                "title_continuity_score": 70,
                "domain_continuity_score": 65,
                "ambiguity_risk_score": 25,
                "evidence_burden_score": 40,
                "selection_risk_level": "medium",
                "likely_rejection_vectors_json": ["domain continuity"],
                "mitigation_moves_json": ["surface roadmap evidence"],
                "assessment_reason": "Plausible but needs explicit evidence.",
                "assessment_json": {"claim_id": "claim-1"},
                "updated_at": TS,
            },
        )
        conn.commit()
    finally:
        conn.close()


def _run_cli(monkeypatch, db_path, *args: str) -> None:
    monkeypatch.setattr(inspect_primary_db, "_configure_stdout", lambda: None)
    monkeypatch.setattr(
        sys,
        "argv",
        ["inspect_primary_db", "--db", str(db_path), *args],
    )
    inspect_primary_db.main()


def test_job_claims_view_outputs_claim_types_and_json_list(tmp_path, monkeypatch, capfd) -> None:
    db_path = tmp_path / "jobpipe.sqlite"
    _insert_job(db_path)
    _insert_claim_layer_rows(db_path)

    _run_cli(monkeypatch, db_path, "--show", "job_claims", "--job-id", "job-claims-1")
    text = capfd.readouterr().out
    assert "must_requirement" in text
    assert "responsibility" in text

    _run_cli(monkeypatch, db_path, "--show", "job_claims", "--job-id", "job-claims-1", "--json")
    data = json.loads(capfd.readouterr().out)
    rows = data["job_claims"]
    assert isinstance(rows, list)
    assert all(isinstance(row, dict) for row in rows)
    assert {row["claim_type"] for row in rows} == {"must_requirement", "responsibility"}


def test_job_claims_view_empty_valid_job_exits_zero_with_info_line(tmp_path, monkeypatch, capfd) -> None:
    db_path = tmp_path / "jobpipe.sqlite"
    _insert_job(db_path, "job-empty")

    _run_cli(monkeypatch, db_path, "--show", "job_claims", "--job-id", "job-empty")
    captured = capfd.readouterr()
    assert "[job_claims] no rows for job_id job-empty" in captured.out
    assert captured.err == ""


def test_claim_view_unknown_job_exits_nonzero_with_stderr(tmp_path, monkeypatch, capfd) -> None:
    db_path = tmp_path / "jobpipe.sqlite"
    _insert_job(db_path, "job-known")

    with pytest.raises(SystemExit) as exc:
        _run_cli(monkeypatch, db_path, "--show", "job_claims", "--job-id", "job-missing")

    captured = capfd.readouterr()
    assert exc.value.code == 1
    assert captured.out == ""
    assert "error: job_id job-missing not found in jobs" in captured.err


def test_claim_layer_views_share_show_and_job_id_plumbing(tmp_path, monkeypatch, capfd) -> None:
    db_path = tmp_path / "jobpipe.sqlite"
    _insert_job(db_path)
    _insert_job(db_path, "job-other")
    _insert_claim_layer_rows(db_path)

    for view_name, expected_text in (
        ("job_claims", "claim-1"),
        ("job_selection_signals", "signal-1"),
        ("job_selection_assessments", "eval-1"),
    ):
        _run_cli(monkeypatch, db_path, "--show", view_name, "--job-id", "job-claims-1")
        output = capfd.readouterr().out
        assert expected_text in output
        assert "job-other" not in output
