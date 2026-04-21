from __future__ import annotations

import os
import subprocess
import sys

from jobpipe.authoring.case_context import AuthoringCaseContext
from jobpipe.authoring.output_models import DocumentValidationResult
from jobpipe.authoring.validation import validate_authoring_context


def _good_ctx(**overrides) -> AuthoringCaseContext:
    """Well-formed context that should pass all rules."""
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
    ctx = _good_ctx()
    result = validate_authoring_context(ctx)

    assert result.passed is True
    assert result.failures == []
    assert result.warnings == []
    assert result.score == 1.0


def test_required_field_absent_blank_candidate_id() -> None:
    ctx = _good_ctx(candidate_id="")
    result = validate_authoring_context(ctx)

    assert result.passed is False
    assert any("required_field_absent" in f for f in result.failures)
    assert any("candidate_id" in f for f in result.failures)


def test_required_field_absent_empty_job_summary() -> None:
    ctx = _good_ctx(job_summary={})
    result = validate_authoring_context(ctx)

    assert result.passed is False
    assert any("job_summary" in f for f in result.failures)


def test_missing_decision_context_missing_key() -> None:
    brief = _good_ctx().decision_brief.copy()
    del brief["final_decision"]
    ctx = _good_ctx(decision_brief=brief)
    result = validate_authoring_context(ctx)

    assert result.passed is False
    assert any("missing_decision_context" in f for f in result.failures)
    assert any("final_decision" in f for f in result.failures)


def test_missing_decision_context_all_keys_present() -> None:
    ctx = _good_ctx()
    result = validate_authoring_context(ctx)

    assert not any("missing_decision_context" in f for f in result.failures)


def test_empty_evidence_units_fails() -> None:
    ctx = _good_ctx(selected_evidence=[])
    result = validate_authoring_context(ctx)

    assert result.passed is False
    assert any("empty_evidence_units" in f for f in result.failures)


def test_narrative_empty_produces_warning_not_error() -> None:
    ctx = _good_ctx(narrative_brief=_empty_narrative())
    result = validate_authoring_context(ctx)

    assert result.passed is True
    assert result.failures == []
    assert any("narrative_empty" in w for w in result.warnings)


def test_narrative_empty_none_is_valid() -> None:
    ctx = _good_ctx(narrative_brief=None)
    result = validate_authoring_context(ctx)

    assert not any("narrative_empty" in w for w in result.warnings)


def test_resume_job_mismatch_narrative_without_evidence() -> None:
    ctx = _good_ctx(
        selected_evidence=[],
        narrative_brief={
            **_good_ctx().narrative_brief,
            "story_strength_score": 88,
        },
    )
    result = validate_authoring_context(ctx)

    assert result.passed is False
    assert any("resume_job_mismatch" in f for f in result.failures)


def test_score_one_error_one_warning() -> None:
    ctx = _good_ctx(
        job_id="",
        narrative_brief=_empty_narrative(),
    )
    result = validate_authoring_context(ctx)

    assert abs(result.score - 0.75) < 0.001


def test_score_clamped_at_zero() -> None:
    ctx = _good_ctx(
        candidate_id="",
        job_id="",
        job_summary={},
        decision_brief={},
        selected_evidence=[],
    )
    result = validate_authoring_context(ctx)

    assert result.score == 0.0


def test_passed_flag_matches_failure_presence() -> None:
    ctx = _good_ctx(candidate_id="")

    assert validate_authoring_context(ctx).passed is False
    warnings_only = _good_ctx(narrative_brief=_empty_narrative())
    result = validate_authoring_context(warnings_only)

    assert result.passed is True
    assert len(result.warnings) > 0


def test_no_crewai_import() -> None:
    script = (
        "from pathlib import Path\n"
        "matches=[]\n"
        "for path in Path('jobpipe').rglob('*.py'):\n"
        "    text = path.read_text(encoding='utf-8')\n"
        "    if 'crewai' in text:\n"
        "        matches.append(str(path))\n"
        "print('\\n'.join(matches), end='')\n"
        "raise SystemExit(0 if matches else 1)\n"
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        env=dict(os.environ),
    )

    assert result.returncode == 1, f"Unexpected crewai reference found:\n{result.stdout}"
    assert result.stdout == ""


def test_result_model_dump_roundtrip() -> None:
    ctx = _good_ctx()
    result = validate_authoring_context(ctx)
    dumped = result.model_dump()

    assert isinstance(result, DocumentValidationResult)
    assert set(dumped.keys()) == {"passed", "score", "failures", "warnings"}
    assert isinstance(dumped["passed"], bool)
    assert isinstance(dumped["score"], float)
