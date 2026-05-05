from __future__ import annotations

from jobpipe.core.schema import (
    FeatureScore,
    JobContext,
    PivotOut,
    ProfileMatchOut,
    RunMeta,
    TriageDecisionV3,
    TriageFeatures,
)
from jobpipe.stages.advantage_assessment_v3 import (
    advantage_assessment_v3_stage_factory,
    build_advantage_assessment,
)


def _feature(score: int, confidence: int = 80) -> FeatureScore:
    return FeatureScore(score=score, confidence=confidence, reason="test", evidence_spans=[])


def _ctx() -> JobContext:
    ctx = JobContext(
        meta=RunMeta(run_id="test", pipeline_name="test", created_at="2026-01-01T00:00:00Z"),
        job_id="job-1",
        job={"title": "Produkteier"},
        profile_pack="",
    )
    ctx.triage_features = TriageFeatures(
        core_tech_alignment=_feature(84),
        legacy_burden=_feature(68),
        role_specificity=_feature(79),
        requirement_density=_feature(64),
        geospatial_friction=_feature(76),
        remote_veracity=_feature(82),
        autonomy_level=_feature(72),
        stakeholder_complexity=_feature(70),
        operating_fit=_feature(66),
    )
    ctx.triage_decision_v3 = TriageDecisionV3(
        label="shortlist",
        weighted_score=76.0,
        confidence=78,
        needs_ambiguity_pass=False,
        blockers=[],
        boosts=["strong_core_tech_match"],
        summary="shortlist from weighted feature aggregation.",
    )
    ctx.profile_match = ProfileMatchOut(
        fit_score=82,
        match_level="strong",
        overlaps=["product ownership", "platform delivery", "cross-functional leadership"],
        gaps=["public-sector context"],
        notes="strong overlap",
    )
    ctx.pivot = PivotOut(
        pivot_score=74,
        pivot_type="adjacent",
        potential_risk="low",
        why_it_matters=["transferable ownership scope", "stakeholder orchestration"],
    )
    return ctx


def test_build_advantage_assessment_returns_expected_shape() -> None:
    assessment = build_advantage_assessment(_ctx())
    assert assessment.advantage_type in {"strong_fit", "advantageous_mismatch"}
    assert "strong_core_tech_alignment" in assessment.advantage_signals
    assert assessment.advantageous_match_score >= 60
    assert assessment.differentiation_signals
    assert assessment.applicant_pool_hypothesis
    assert assessment.recruiter_hook
    assert assessment.review_priority >= 60
    assert assessment.stretch_level in {"low", "medium", "high"}


def test_advantage_stage_sets_ctx() -> None:
    should_run, run = advantage_assessment_v3_stage_factory()
    ctx = _ctx()
    assert should_run(ctx) is True
    result = run(ctx, "/tmp")
    assert result.advantage_assessment_v3 is not None
    assert result.advantage_assessment_v3.summary
