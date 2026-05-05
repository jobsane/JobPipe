from __future__ import annotations

from jobpipe.core.schema import (
    AdvantageAssessmentV3,
    JobContext,
    ModeratorOut,
    NarrativeStrategyV3,
    PivotOut,
    ProfileMatchOut,
    RunMeta,
    TriageAmbiguityV3,
    TriageDecisionV3,
    TriageOut,
)


def _ctx() -> JobContext:
    ctx = JobContext(
        meta=RunMeta(run_id="run", pipeline_name="pipe", created_at="2026-04-19T00:00:00Z"),
        job_id="job-1",
        job={"title": "Produkteier", "employer_name": "Avinor"},
        profile_pack="",
    )
    ctx.triage = TriageOut(triage_decision="REVIEW", confidence=0.8, explanation="ok", signals=["target_title_match"])
    ctx.profile_match = ProfileMatchOut(
        fit_score=71,
        match_level="medium",
        overlaps=["produktledelse"],
        gaps=["public sector"],
        hard_blockers=[],
        notes="",
    )
    ctx.pivot = PivotOut(pivot_score=79, pivot_type="adjacent", potential_risk="low", why_it_matters=["Relevant scope"])
    ctx.triage_decision_v3 = TriageDecisionV3(
        label="review",
        weighted_score=63.0,
        confidence=74,
        needs_ambiguity_pass=True,
        blockers=[],
        boosts=["specific_role_signal"],
        summary="review from weighted feature aggregation.",
    )
    ctx.triage_ambiguity_v3 = TriageAmbiguityV3(
        initial_label="review",
        resolved_label="shortlist",
        confidence=76,
        resolution_reason="Borderline review upgraded.",
        blockers=[],
        boosts=["ambiguity_upgrade_review"],
        final_decision=TriageDecisionV3(
            label="shortlist",
            weighted_score=63.0,
            confidence=76,
            needs_ambiguity_pass=False,
            blockers=[],
            boosts=["ambiguity_upgrade_review"],
            summary="Borderline review upgraded.",
        ),
    )
    ctx.advantage_assessment_v3 = AdvantageAssessmentV3(
        advantage_type="strong_fit",
        advantage_signals=["produktledelse"],
        objection_signals=["public sector"],
        neutralizing_evidence=["Relevant scope"],
        stretch_level="low",
        review_priority=84,
        confidence=78,
        summary="strong fit",
    )
    ctx.narrative_strategy_v3 = NarrativeStrategyV3(
        positioning_angle="Direkte relevant erfaring som kan levere raskt.",
        brand_frame="Brobygger mellom produkt og drift",
        why_me_now="Har allerede erfaring som matcher kjernen i rollen.",
        top_value_props=["Produktledelse", "Tverrfaglig samhandling"],
        objections_to_handle=["public sector"],
        cv_focus_order=["ownership", "delivery"],
        cover_letter_strategy="Åpne med relevant eierskap.",
        confidence=80,
        summary="Narrative strategy for Produkteier.",
    )
    ctx.moderator = ModeratorOut(
        final_decision="APPLY",
        confidence=0.84,
        recommendation_reason="fit=71, pivot=79",
        cv_focus=["ownership"],
        feedback_flags=[],
        triage_decision_v3=ctx.triage_ambiguity_v3.final_decision,
    )
    return ctx


def test_snapshot_summary_carries_topic19_v3_summary_fields() -> None:
    summary = _ctx().snapshot_summary()

    assert summary["triage_v3_label"] == "shortlist"
    assert summary["triage_v3_weighted_score"] == 63.0
    assert summary["triage_v3_confidence"] == 76
    assert summary["triage_v3_needs_ambiguity"] is False
    assert summary["triage_ambiguity_label"] == "shortlist"
    assert summary["advantage_type"] == "strong_fit"
    assert summary["advantage_review_priority"] == 84
    assert summary["narrative_positioning_angle"] == "Direkte relevant erfaring som kan levere raskt."
    assert summary["narrative_brand_frame"] == "Brobygger mellom produkt og drift"
