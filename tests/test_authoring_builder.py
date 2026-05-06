from __future__ import annotations

import ast
from pathlib import Path

import pytest

from jobpipe.authoring.builder import build_authoring_case_context
from jobpipe.decision.models import (
    CandidateEvidenceContext,
    CandidateEvidenceSelection,
    CandidateNarrativeContext,
    CandidateNarrativeProfile,
    JobDecisionDimension,
    JobDecisionTable,
    JobNarrativeAssessment,
    JobSelectionAssessment,
    DecisionContext,
)
from jobpipe.model.schema import JobContext, JobParse, ModeratorOut, RunMeta


def _job_ctx(*, moderator: ModeratorOut | None | object = ..., parsed: JobParse | None | object = ...) -> JobContext:
    if moderator is ...:
        moderator = ModeratorOut(
            final_decision="APPLY",
            confidence=0.82,
            recommendation_reason="Strong product leadership overlap.",
            cv_focus=["roadmap", "stakeholder alignment"],
        )
    if parsed is ...:
        parsed = JobParse(
            role_summary="Lead product discovery and delivery.",
            responsibilities=["Own roadmap"],
            requirements_must=["Product leadership"],
            requirements_nice=["Public sector experience"],
        )
    return JobContext(
        meta=RunMeta(run_id="run-abc", pipeline_name="test", created_at="2026-04-21T10:00:00Z"),
        job_id="job-001",
        job={
            "title": "Product Manager",
            "employer_name": "Example AS",
            "sector": "Technology",
            "applicationDue": "2026-05-01",
            "sourceurl": "https://example.test/job-001",
        },
        profile_pack="Candidate profile",
        parsed=parsed,
        moderator=moderator,
    )


def _decision_ctx() -> DecisionContext:
    def dim(key: str, score: int) -> JobDecisionDimension:
        return JobDecisionDimension(
            dimension_key=key,
            level="strong",
            score=score,
            reason=f"{key} reason",
        )

    return DecisionContext(
        selection_assessment=JobSelectionAssessment(
            structural_pass=True,
            screenability_score=77,
            title_continuity_score=80,
            domain_continuity_score=70,
            ambiguity_risk_score=20,
            evidence_burden_score=30,
            selection_risk_level="medium",
            assessment_reason="Plausible role.",
        ),
        decision_table=JobDecisionTable(
            can_do=dim("can_do", 84),
            can_get=dim("can_get", 76),
            should_want=dim("should_want", 81),
            can_explain=dim("can_explain", 88),
            act_now="pursue_now",
            confidence_score=0.86,
            table_reason="Apply with focused evidence.",
        ),
    )


def _evidence_ctx() -> CandidateEvidenceContext:
    return CandidateEvidenceContext(
        selected_evidence_units=[
            CandidateEvidenceSelection(
                evidence_unit_id="evidence-1",
                source_type="work_highlight",
                source_ref="resume:work:1",
                canonical_text="Led cross-functional roadmap work.",
                rewrite_policy="light_rewrite_only",
                relevance_score=91,
                matched_role_family_tags=["product"],
                matched_domain_tags=["technology"],
                matched_capability_tags=["roadmap"],
                targeted_terms=["roadmap"],
                selection_reason="Direct match with role focus.",
            )
        ]
    )


def _narrative_ctx() -> CandidateNarrativeContext:
    return CandidateNarrativeContext(
        narrative_profile=CandidateNarrativeProfile(
            narrative_version_id="narrative-1",
            candidate_id="cand-1",
            source_kind="manual",
            core_identity=["Product leader"],
            future_direction=["AI-enabled services"],
            motivation_themes=[],
            pivot_thesis=["Credible adjacent move"],
            narrative_summary="Product leader moving toward AI-enabled services.",
        ),
        job_narrative_assessment=JobNarrativeAssessment(
            direction_fit_score=82,
            motivation_fit_score=79,
            pivot_credibility_score=75,
            story_strength_score=88,
            assessment_reason="Narrative fits the role.",
            motivation_brief="The role fits the candidate's current direction.",
        ),
    )


def _build(**overrides: object):
    values = {
        "job_ctx": _job_ctx(),
        "decision_ctx": _decision_ctx(),
        "evidence_ctx": _evidence_ctx(),
        "narrative_ctx": _narrative_ctx(),
        "candidate_id": "cand-1",
        "evaluation_id": "run-abc:job-001",
    }
    values.update(overrides)
    return build_authoring_case_context(**values)


def test_happy_path_with_narrative() -> None:
    result = _build()

    assert result.candidate_id == "cand-1"
    assert result.job_id == "job-001"
    assert result.evaluation_id == "run-abc:job-001"
    assert result.job_summary == {
        "title": "Product Manager",
        "employer_name": "Example AS",
        "sector": "Technology",
        "application_due": "2026-05-01",
        "source_url": "https://example.test/job-001",
        "role_summary": "Lead product discovery and delivery.",
    }
    assert result.decision_brief == {
        "final_decision": "APPLY",
        "recommendation_reason": "Strong product leadership overlap.",
        "cv_focus": ["roadmap", "stakeholder alignment"],
        "act_now": "pursue_now",
        "can_do_score": 84,
        "can_get_score": 76,
        "should_want_score": 81,
        "can_explain_score": 88,
    }
    assert result.selected_evidence[0]["evidence_unit_id"] == "evidence-1"
    assert result.narrative_brief == {
        "core_identity": ["Product leader"],
        "future_direction": ["AI-enabled services"],
        "motivation_themes": [],
        "pivot_thesis": ["Credible adjacent move"],
        "direction_fit_score": 82,
        "motivation_fit_score": 79,
        "story_strength_score": 88,
        "motivation_brief": "The role fits the candidate's current direction.",
    }
    assert result.artifact_plan is None


def test_happy_path_narrative_none() -> None:
    result = _build(narrative_ctx=None, evaluation_id=None)

    assert result.narrative_brief is None
    assert result.evaluation_id is None


def test_job_summary_key_set() -> None:
    result = _build()

    assert set(result.job_summary.keys()) == {
        "title",
        "employer_name",
        "sector",
        "application_due",
        "source_url",
        "role_summary",
    }


def test_decision_brief_key_set() -> None:
    result = _build()

    assert set(result.decision_brief.keys()) == {
        "final_decision",
        "recommendation_reason",
        "cv_focus",
        "act_now",
        "can_do_score",
        "can_get_score",
        "should_want_score",
        "can_explain_score",
    }


def test_decision_brief_act_now_is_string() -> None:
    result = _build()

    assert isinstance(result.decision_brief["act_now"], str)


def test_missing_moderator_raises_value_error() -> None:
    job_ctx = _job_ctx(moderator=None)

    with pytest.raises(ValueError) as exc_info:
        _build(job_ctx=job_ctx)

    assert job_ctx.job_id in str(exc_info.value)


def test_missing_parsed_raises_value_error() -> None:
    job_ctx = _job_ctx(parsed=None)

    with pytest.raises(ValueError) as exc_info:
        _build(job_ctx=job_ctx)

    assert job_ctx.job_id in str(exc_info.value)


def test_evaluation_id_default_is_none() -> None:
    result = build_authoring_case_context(
        _job_ctx(),
        _decision_ctx(),
        _evidence_ctx(),
        _narrative_ctx(),
        candidate_id="cand-1",
    )

    assert result.evaluation_id is None


def test_candidate_id_required() -> None:
    with pytest.raises(TypeError):
        build_authoring_case_context(
            _job_ctx(),
            _decision_ctx(),
            _evidence_ctx(),
            _narrative_ctx(),
        )


def test_determinism() -> None:
    inputs = {
        "job_ctx": _job_ctx(),
        "decision_ctx": _decision_ctx(),
        "evidence_ctx": _evidence_ctx(),
        "narrative_ctx": _narrative_ctx(),
        "candidate_id": "cand-1",
        "evaluation_id": "run-abc:job-001",
    }

    assert build_authoring_case_context(**inputs) == build_authoring_case_context(**inputs)


def test_v3_advantage_fields_wired_from_job_ctx() -> None:
    from jobpipe.core.schema import AdvantageAssessmentV3

    adv = AdvantageAssessmentV3(
        advantage_type="strong_fit",
        differentiation_signals=["deep product leadership", "public sector exposure"],
        neutralizing_evidence=["5 years product management"],
        recruiter_hook="Product leader with public sector credibility.",
        stretch_level="low",
        review_priority=80,
        confidence=85,
        summary="Strong fit.",
    )
    job_ctx = _job_ctx().model_copy(update={"advantage_assessment_v3": adv})

    result = _build(job_ctx=job_ctx)

    assert result.advantage_type == "strong_fit"
    assert result.differentiation_signals == ["deep product leadership", "public sector exposure"]
    assert result.neutralizing_evidence == ["5 years product management"]
    assert result.recruiter_hook == "Product leader with public sector credibility."


def test_v3_narrative_fields_wired_from_job_ctx() -> None:
    from jobpipe.core.schema import NarrativeStrategyV3

    ns = NarrativeStrategyV3(
        positioning_angle="Product leader with public sector credibility.",
        brand_frame="Strategic product leader.",
        why_me_now="Rare combination of product and public sector.",
        top_value_props=["Product leadership", "Public sector"],
        cv_focus_order=["roadmap", "stakeholder alignment"],
        cover_letter_strategy="Lead with public sector angle.",
        confidence=82,
        summary="Strong narrative.",
    )
    job_ctx = _job_ctx().model_copy(update={"narrative_strategy_v3": ns})

    result = _build(job_ctx=job_ctx)

    assert result.narrative_positioning_angle == "Product leader with public sector credibility."
    assert result.narrative_brand_frame == "Strategic product leader."
    assert result.narrative_why_me_now == "Rare combination of product and public sector."
    assert result.cover_letter_strategy == "Lead with public sector angle."


def test_v3_fields_are_absent_when_job_ctx_has_no_v3() -> None:
    result = _build()  # default _job_ctx() has no v3 fields

    assert result.advantage_type is None
    assert result.differentiation_signals == []
    assert result.neutralizing_evidence == []
    assert result.recruiter_hook is None
    assert result.narrative_positioning_angle is None
    assert result.narrative_brand_frame is None
    assert result.narrative_why_me_now is None
    assert result.cover_letter_strategy is None


def test_no_crewai_import() -> None:
    jobpipe_dir = Path("jobpipe")
    hits: list[tuple[Path, str]] = []
    for path in jobpipe_dir.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "crewai" or alias.name.startswith("crewai."):
                        hits.append((path, alias.name))
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module == "crewai" or node.module.startswith("crewai."):
                    hits.append((path, node.module))

    assert not hits, f"Unexpected crewai reference found: {hits}"
