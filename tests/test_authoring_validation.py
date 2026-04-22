from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from jobpipe.authoring.case_context import AuthoringCaseContext
from jobpipe.authoring.validation import validate_authoring_context


def _good_ctx(**overrides) -> AuthoringCaseContext:
    values = dict(
        candidate_id="cand-1",
        job_id="job-001",
        evaluation_id="run-abc:job-001",
        job_summary={
            "title": "Product Manager",
            "employer_name": "Acme AS",
            "sector": "Technology",
            "application_due": "2026-05-01",
            "source_url": "https://example.test/job-001",
            "role_summary": "Lead product discovery.",
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
    values.update(overrides)
    return AuthoringCaseContext(**values)


def _empty_narrative() -> dict:
    return {
        "core_identity": [],
        "future_direction": [],
        "motivation_themes": [],
        "pivot_thesis": [],
        "direction_fit_score": 0,
        "motivation_fit_score": 0,
        "story_strength_score": 0,
        "motivation_brief": "",
    }


def test_validate_well_formed_context_passes() -> None:
    result = validate_authoring_context(_good_ctx())

    assert result.passed is True
    assert result.failures == []
    assert result.warnings == []
    assert result.score == 1.0


def test_required_field_absent_blank_candidate_id() -> None:
    result = validate_authoring_context(_good_ctx(candidate_id=""))

    assert result.passed is False
    assert any("required_field_absent" in failure for failure in result.failures)
    assert any("candidate_id" in failure for failure in result.failures)


def test_required_field_absent_empty_job_summary() -> None:
    result = validate_authoring_context(_good_ctx(job_summary={}))

    assert result.passed is False
    assert any("job_summary" in failure for failure in result.failures)


def test_missing_decision_context_missing_key() -> None:
    brief = _good_ctx().decision_brief.copy()
    del brief["final_decision"]
    del brief["act_now"]

    result = validate_authoring_context(_good_ctx(decision_brief=brief))
    findings = [
        failure for failure in result.failures if "missing_decision_context" in failure
    ]

    assert result.passed is False
    assert len(findings) == 2
    assert any("final_decision" in failure for failure in findings)
    assert any("act_now" in failure for failure in findings)


def test_missing_decision_context_all_keys_present() -> None:
    result = validate_authoring_context(_good_ctx())

    assert not any("missing_decision_context" in failure for failure in result.failures)


def test_empty_evidence_units_fails() -> None:
    result = validate_authoring_context(_good_ctx(selected_evidence=[]))

    assert result.passed is False
    assert any("empty_evidence_units" in failure for failure in result.failures)


def test_narrative_empty_produces_warning_not_error() -> None:
    result = validate_authoring_context(_good_ctx(narrative_brief=_empty_narrative()))

    assert result.passed is True
    assert result.failures == []
    assert any("narrative_empty" in warning for warning in result.warnings)


def test_narrative_empty_none_is_valid() -> None:
    result = validate_authoring_context(_good_ctx(narrative_brief=None))

    assert not any("narrative_empty" in warning for warning in result.warnings)


def test_resume_job_mismatch_narrative_without_evidence() -> None:
    result = validate_authoring_context(
        _good_ctx(
            selected_evidence=[],
            narrative_brief={
                **_good_ctx().narrative_brief,
                "story_strength_score": 88,
            },
        )
    )

    assert result.passed is False
    assert any("resume_job_mismatch" in failure for failure in result.failures)


def test_score_one_error_one_warning() -> None:
    result = validate_authoring_context(
        _good_ctx(candidate_id="", narrative_brief=_empty_narrative())
    )

    assert abs(result.score - 0.75) < 0.001


def test_score_clamped_at_zero() -> None:
    decision_brief = {"unexpected_key": True}
    result = validate_authoring_context(
        _good_ctx(
            candidate_id="",
            job_id="",
            job_summary={},
            decision_brief=decision_brief,
            selected_evidence=[],
        )
    )

    assert result.score == 0.0


def test_passed_false_on_failures_true_on_warnings_only() -> None:
    assert validate_authoring_context(_good_ctx(candidate_id="")).passed is False

    result = validate_authoring_context(_good_ctx(narrative_brief=_empty_narrative()))

    assert result.passed is True
    assert len(result.warnings) > 0


def test_no_crewai_import() -> None:
    env = None
    grep_exe = shutil.which("grep")
    for candidate in (
        Path("C:/Program Files/Git/usr/bin/grep.exe"),
        Path("C:/Program Files/Git/bin/grep.exe"),
        Path("C:/msys64/usr/bin/grep.exe"),
    ):
        if grep_exe is None and candidate.exists():
            grep_exe = str(candidate)
            break

    if grep_exe is not None:
        git_grep_dir = Path(grep_exe).parent
        env = dict(os.environ)
        env["PATH"] = f"{git_grep_dir}{os.pathsep}{env.get('PATH', '')}"

    result = subprocess.run(
        [
            grep_exe or "grep",
            "-rE",
            "^from crewai|^import crewai",
            "jobpipe/",
            "--include=*.py",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert result.returncode == 1, f"Unexpected crewai reference found:\n{result.stdout}"
    assert result.stdout == ""


def test_result_model_dump_roundtrip() -> None:
    dumped = validate_authoring_context(_good_ctx()).model_dump()

    assert set(dumped.keys()) == {"passed", "score", "failures", "warnings"}
    assert isinstance(dumped["passed"], bool)
    assert isinstance(dumped["score"], float)
