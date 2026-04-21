from __future__ import annotations

import argparse
import json
import shutil
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from jobpipe.authoring.case_context import AuthoringCaseContext
from jobpipe.authoring.smoke_cli import (
    _load_stage,
    _resolve_job_dir,
    _run,
    build_context_for_job,
)
from jobpipe.model.schema import JobContext


@pytest.fixture
def work_tmp() -> Path:
    root = Path("tmp-authoring-smoke")
    root.mkdir(exist_ok=True)
    path = root / uuid.uuid4().hex
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _minimal_parsed_dict() -> dict:
    return {
        "role_summary": "Own product discovery and delivery.",
        "responsibilities": ["Own roadmap"],
        "requirements_must": ["Product leadership"],
        "requirements_nice": ["Public sector"],
    }


def _minimal_moderator_dict() -> dict:
    return {
        "final_decision": "APPLY",
        "confidence": 0.82,
        "recommendation_reason": "Strong product leadership overlap.",
        "cv_focus": ["roadmap"],
        "feedback_flags": [],
    }


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_canonical_run(root: Path, run_id: str, job_id: str) -> Path:
    job_dir = root / run_id / job_id
    job_dir.mkdir(parents=True)
    _write_json(job_dir / "00_input.json", {"title": "Test Role", "employer_name": "Example AS"})
    _write_json(
        job_dir / "01_triage.json",
        {
            "triage_decision": "APPLY_CANDIDATE",
            "confidence": 0.7,
            "explanation": "Relevant role.",
            "signals": ["product"],
        },
    )
    _write_json(job_dir / "02_parsed.json", _minimal_parsed_dict())
    _write_json(
        job_dir / "03_profile_match.json",
        {
            "fit_score": 70,
            "match_level": "medium",
            "overlaps": ["roadmap"],
            "gaps": [],
            "hard_blockers": [],
            "notes": "Plausible fit.",
        },
    )
    _write_json(
        job_dir / "04_pivot.json",
        {
            "pivot_score": 64,
            "pivot_type": "adjacent",
            "potential_risk": "low",
            "why_it_matters": ["credible move"],
        },
    )
    _write_json(job_dir / "05_moderator.json", _minimal_moderator_dict())
    return job_dir


def _sentinel_context() -> AuthoringCaseContext:
    return AuthoringCaseContext(
        candidate_id="cand-1",
        job_id="job-1",
        evaluation_id="run-1:job-1",
        job_summary={
            "title": "Test Role",
            "employer_name": "Example AS",
            "sector": "Technology",
            "application_due": "2026-05-01",
            "source_url": "https://example.test/job-1",
            "role_summary": "Own product discovery and delivery.",
        },
        decision_brief={
            "final_decision": "APPLY",
            "recommendation_reason": "Strong fit.",
            "cv_focus": ["roadmap"],
            "act_now": "pursue_now",
            "can_do_score": 84,
            "can_get_score": 76,
            "should_want_score": 81,
            "can_explain_score": 88,
        },
        selected_evidence=[
            {"evidence_unit_id": "evidence-1", "canonical_text": "Led roadmap work."}
        ],
        narrative_brief={
            "core_identity": ["Product leader"],
            "future_direction": ["AI services"],
            "motivation_themes": [],
            "pivot_thesis": ["Credible move"],
            "direction_fit_score": 82,
            "motivation_fit_score": 79,
            "story_strength_score": 88,
            "motivation_brief": "The role fits.",
        },
        artifact_plan=None,
    )


def test_load_stage_canonical_layout(work_tmp: Path) -> None:
    _write_json(work_tmp / "00_input.json", {"kind": "input"})
    _write_json(work_tmp / "02_parsed.json", {"kind": "parsed"})
    _write_json(work_tmp / "05_moderator.json", {"kind": "moderator"})

    assert _load_stage(work_tmp, "00_input.json") == {"kind": "input"}
    assert _load_stage(work_tmp, "02_parsed.json", "03_parsed.json") == {"kind": "parsed"}
    assert _load_stage(work_tmp, "05_moderator.json", "06_moderator.json") == {"kind": "moderator"}


def test_load_stage_legacy_layout(work_tmp: Path) -> None:
    _write_json(work_tmp / "03_parsed.json", {"kind": "legacy-parsed"})
    _write_json(work_tmp / "06_moderator.json", {"kind": "legacy-moderator"})

    assert _load_stage(work_tmp, "02_parsed.json", "03_parsed.json") == {"kind": "legacy-parsed"}
    assert _load_stage(work_tmp, "05_moderator.json", "06_moderator.json") == {"kind": "legacy-moderator"}


def test_load_stage_missing_raises(work_tmp: Path) -> None:
    with pytest.raises(FileNotFoundError) as exc_info:
        _load_stage(work_tmp, "02_parsed.json", "03_parsed.json")

    message = str(exc_info.value)
    assert "02_parsed.json" in message
    assert "03_parsed.json" in message


def test_resolve_job_dir_explicit_run(work_tmp: Path) -> None:
    job_dir = work_tmp / "run-1" / "job-1"
    job_dir.mkdir(parents=True)

    assert _resolve_job_dir(work_tmp, "run-1", "job-1") == job_dir


def test_resolve_job_dir_latest_run(work_tmp: Path) -> None:
    (work_tmp / "run-1").mkdir()
    job_dir = work_tmp / "run-2" / "job-1"
    job_dir.mkdir(parents=True)

    assert _resolve_job_dir(work_tmp, None, "job-1") == job_dir


def test_build_context_for_job_happy_path(monkeypatch: pytest.MonkeyPatch, work_tmp: Path) -> None:
    root = work_tmp / "artifacts"
    _write_canonical_run(root, "run-1", "job-1")
    decision_ctx = MagicMock(name="decision_ctx")
    evidence_ctx = MagicMock(name="evidence_ctx")
    narrative_ctx = MagicMock(name="narrative_ctx")
    sentinel = _sentinel_context()

    monkeypatch.setattr(
        "jobpipe.authoring.smoke_cli.load_candidate_profile_pack",
        lambda *, candidate_id: f"profile for {candidate_id}",
    )
    monkeypatch.setattr(
        "jobpipe.authoring.smoke_cli._load_resume_context",
        lambda: {"resume_work": [], "resume_projects": [], "resume_education": []},
    )
    monkeypatch.setattr(
        "jobpipe.authoring.smoke_cli._build_application_pack_contexts",
        lambda ctx, resume_ctx: (decision_ctx, evidence_ctx, narrative_ctx),
    )

    def fake_build(job_ctx, got_decision, got_evidence, got_narrative, *, candidate_id, evaluation_id):
        assert isinstance(job_ctx, JobContext)
        assert job_ctx.moderator is not None
        assert job_ctx.parsed is not None
        assert got_decision is decision_ctx
        assert got_evidence is evidence_ctx
        assert got_narrative is narrative_ctx
        assert candidate_id == "cand-1"
        assert evaluation_id == "run-1:job-1"
        return sentinel

    monkeypatch.setattr("jobpipe.authoring.smoke_cli.build_authoring_case_context", fake_build)

    assert build_context_for_job(
        artifacts_root=root,
        run_id="run-1",
        job_id="job-1",
        candidate_id="cand-1",
    ) is sentinel


def test_cli_run_writes_stdout(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], work_tmp: Path) -> None:
    sentinel = _sentinel_context()
    monkeypatch.setattr("jobpipe.authoring.smoke_cli.build_context_for_job", lambda **kwargs: sentinel)
    args = argparse.Namespace(
        artifacts_root=str(work_tmp / "artifacts"),
        run="run-1",
        job="job-1",
        candidate="cand-1",
        out=None,
        validate=False,
    )

    assert _run(args) == 0
    stdout_text = capsys.readouterr().out
    data = json.loads(stdout_text)
    assert set(data.keys()) == {
        "candidate_id",
        "job_id",
        "evaluation_id",
        "job_summary",
        "decision_brief",
        "selected_evidence",
        "narrative_brief",
        "artifact_plan",
    }

    out_path = work_tmp / "context.json"
    args.out = str(out_path)
    assert _run(args) == 0
    expected = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True)
    assert out_path.read_text(encoding="utf-8") == expected


def test_validate_flag_passes_on_good_context(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    work_tmp: Path,
) -> None:
    monkeypatch.setattr("jobpipe.authoring.smoke_cli.build_context_for_job", lambda **kwargs: _sentinel_context())
    args = argparse.Namespace(
        artifacts_root=str(work_tmp / "artifacts"),
        run="run-1",
        job="job-1",
        candidate="cand-1",
        out=None,
        validate=True,
    )

    assert _run(args) == 0
    captured = capsys.readouterr()
    assert "passed=True" in captured.err
    assert "FAIL:" not in captured.err


def test_validate_flag_fails_on_bad_context(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    work_tmp: Path,
) -> None:
    good = _sentinel_context()
    bad = AuthoringCaseContext(
        candidate_id="",
        job_id=good.job_id,
        evaluation_id=good.evaluation_id,
        job_summary=good.job_summary,
        decision_brief=good.decision_brief,
        selected_evidence=good.selected_evidence,
        narrative_brief=good.narrative_brief,
        artifact_plan=good.artifact_plan,
    )
    monkeypatch.setattr("jobpipe.authoring.smoke_cli.build_context_for_job", lambda **kwargs: bad)
    args = argparse.Namespace(
        artifacts_root=str(work_tmp / "artifacts"),
        run="run-1",
        job="job-1",
        candidate="cand-1",
        out=None,
        validate=True,
    )

    assert _run(args) == 2
    captured = capsys.readouterr()
    assert "passed=False" in captured.err
    assert "FAIL:" in captured.err


def test_validate_flag_absent_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
    work_tmp: Path,
) -> None:
    monkeypatch.setattr("jobpipe.authoring.smoke_cli.build_context_for_job", lambda **kwargs: _sentinel_context())
    args = argparse.Namespace(
        artifacts_root=str(work_tmp / "artifacts"),
        run="run-1",
        job="job-1",
        candidate="cand-1",
        out=None,
        validate=False,
    )

    assert _run(args) == 0


def test_no_crewai_import() -> None:
    text = Path("jobpipe/authoring/smoke_cli.py").read_text(encoding="utf-8")

    assert "crewai" not in text
    assert "autogen" not in text
    assert "langchain" not in text
