from __future__ import annotations

from jobpipe.core.schema import (
    AdvantageAssessmentV3,
    FeatureScore,
    JobContext,
    JobParse,
    ProfileMatchOut,
    RunMeta,
)
from jobpipe.stages.narrative_strategy_v3 import (
    build_narrative_strategy,
    narrative_strategy_v3_stage_factory,
)


def _feature(score: int, confidence: int = 80) -> FeatureScore:
    return FeatureScore(score=score, confidence=confidence, reason="test", evidence_spans=[])


def _ctx() -> JobContext:
    ctx = JobContext(
        meta=RunMeta(run_id="test", pipeline_name="test", created_at="2026-01-01T00:00:00Z"),
        job_id="job-1",
        job={"title": "Produkteier", "employer_name": "Avinor"},
        profile_pack="",
    )
    ctx.parsed = JobParse(
        role_summary="Produkteier for digital plattform",
        responsibilities=["roadmap", "stakeholder management"],
        requirements_must=["produktledelse", "prioritering"],
        requirements_nice=["offentlig sektor"],
    )
    ctx.profile_match = ProfileMatchOut(
        fit_score=82,
        match_level="strong",
        overlaps=["product ownership", "platform delivery", "cross-functional leadership"],
        gaps=["public-sector context"],
        notes="strong overlap",
    )
    ctx.advantage_assessment_v3 = AdvantageAssessmentV3(
        advantage_type="strong_fit",
        advantage_signals=["strong_core_tech_alignment", "strong_role_specificity"],
        objection_signals=["public-sector context"],
        neutralizing_evidence=["product ownership", "platform delivery"],
        stretch_level="low",
        review_priority=82,
        confidence=79,
        summary="strong fit with manageable objection",
    )
    return ctx


def test_build_narrative_strategy_returns_expected_shape() -> None:
    strategy = build_narrative_strategy(_ctx())
    assert strategy.positioning_angle
    assert strategy.brand_frame
    assert len(strategy.top_value_props) >= 2
    assert len(strategy.cv_focus_order) >= 2
    assert "public-sector context" in strategy.objections_to_handle


def test_narrative_stage_sets_ctx() -> None:
    should_run, run = narrative_strategy_v3_stage_factory()
    ctx = _ctx()
    assert should_run(ctx) is True
    result = run(ctx, "/tmp")
    assert result.narrative_strategy_v3 is not None
    assert result.narrative_strategy_v3.cover_letter_strategy
