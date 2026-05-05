from __future__ import annotations

from typing import Dict, Optional

from jobpipe.core.schema import HardGates, TriageAmbiguityV3, TriageDecisionV3, TriageFeatures

TRIAGE_FEATURE_WEIGHTS: Dict[str, float] = {
    "core_tech_alignment": 0.24,
    "legacy_burden": 0.14,
    "role_specificity": 0.12,
    "requirement_density": 0.08,
    "geospatial_friction": 0.14,
    "remote_veracity": 0.10,
    "autonomy_level": 0.06,
    "stakeholder_complexity": 0.06,
    "operating_fit": 0.06,
}

REVIEW_THRESHOLD = 48.0
SHORTLIST_THRESHOLD = 67.0


def aggregate_triage_decision(
    features: TriageFeatures,
    hard_gates: HardGates,
    *,
    feature_weights: Optional[Dict[str, float]] = None,
    review_threshold: float = REVIEW_THRESHOLD,
    shortlist_threshold: float = SHORTLIST_THRESHOLD,
) -> TriageDecisionV3:
    weights = feature_weights or TRIAGE_FEATURE_WEIGHTS
    if not hard_gates.passed():
        blockers = list(dict.fromkeys(hard_gates.blocker_reasons or ["hard_gates_failed"]))
        return TriageDecisionV3(
            label="discard",
            weighted_score=0.0,
            confidence=100,
            needs_ambiguity_pass=False,
            blockers=blockers,
            boosts=[],
            summary="Discarded by deterministic hard gates.",
        )

    weighted_score = round(
        sum(getattr(features, name).score * weight for name, weight in weights.items()),
        1,
    )
    confidence = round(
        sum(getattr(features, name).confidence for name in weights) / len(weights)
    )

    blockers: list[str] = []
    boosts: list[str] = []

    if features.core_tech_alignment.score < 35:
        blockers.append("core_tech_alignment_too_low")
    if features.geospatial_friction.score < 20 and features.remote_veracity.score < 60:
        blockers.append("commute_not_offset_by_remote")
    if features.legacy_burden.score < 25:
        blockers.append("legacy_burden_too_high")

    if features.core_tech_alignment.score >= 80:
        boosts.append("strong_core_tech_match")
    if features.role_specificity.score >= 70:
        boosts.append("specific_role_signal")
    if features.remote_veracity.score >= 80:
        boosts.append("credible_remote_flexibility")

    if blockers:
        label = "discard"
    elif weighted_score >= shortlist_threshold:
        label = "shortlist"
    elif weighted_score >= review_threshold:
        label = "review"
    else:
        label = "discard"

    needs_ambiguity_pass = bool(
        review_threshold - 5 <= weighted_score <= shortlist_threshold + 5
        or confidence < 60
        or abs(features.geospatial_friction.score - features.remote_veracity.score) > 55
    )

    return TriageDecisionV3(
        label=label,
        weighted_score=weighted_score,
        confidence=confidence,
        needs_ambiguity_pass=needs_ambiguity_pass,
        blockers=blockers,
        boosts=boosts,
        summary=f"{label} from weighted feature aggregation.",
    )


def resolve_triage_ambiguity(
    features: TriageFeatures,
    decision: TriageDecisionV3,
) -> TriageAmbiguityV3:
    if not decision.needs_ambiguity_pass:
        resolved = decision.model_copy(update={"needs_ambiguity_pass": False})
        return TriageAmbiguityV3(
            initial_label=decision.label,
            resolved_label=resolved.label,
            confidence=resolved.confidence,
            resolution_reason="No ambiguity pass needed.",
            blockers=list(resolved.blockers),
            boosts=list(resolved.boosts),
            final_decision=resolved,
        )

    resolved_label = decision.label
    resolution_reason = "Kept first-pass decision after ambiguity review."
    blockers = list(decision.blockers)
    boosts = list(decision.boosts)

    geo_remote_gap = abs(features.geospatial_friction.score - features.remote_veracity.score)
    strong_competitive_core = (
        features.core_tech_alignment.score >= 70
        and features.role_specificity.score >= 65
        and features.legacy_burden.score >= 50
    )
    weak_operating_case = (
        features.operating_fit.score < 45
        or features.legacy_burden.score < 35
    )

    if decision.label == "discard" and strong_competitive_core:
        resolved_label = "review"
        resolution_reason = "Borderline discard upgraded after ambiguity review."
        boosts = list(dict.fromkeys(boosts + ["ambiguity_upgrade_review"]))
    elif decision.label == "shortlist" and weak_operating_case:
        resolved_label = "review"
        resolution_reason = "Shortlist softened to review after operating-risk ambiguity review."
        blockers = list(dict.fromkeys(blockers + ["ambiguity_downgrade_review"]))
    elif decision.label == "review" and geo_remote_gap > 55 and features.remote_veracity.score >= 80:
        resolved_label = "review"
        resolution_reason = "Kept review because remote flexibility offsets geo ambiguity."
        boosts = list(dict.fromkeys(boosts + ["remote_offsets_geo_ambiguity"]))
    elif decision.label == "review" and features.core_tech_alignment.score < 40:
        resolved_label = "discard"
        resolution_reason = "Borderline review downgraded after ambiguity review."
        blockers = list(dict.fromkeys(blockers + ["ambiguity_downgrade_discard"]))

    final_decision = decision.model_copy(
        update={
            "label": resolved_label,
            "needs_ambiguity_pass": False,
            "blockers": blockers,
            "boosts": boosts,
            "summary": resolution_reason,
        }
    )

    return TriageAmbiguityV3(
        initial_label=decision.label,
        resolved_label=resolved_label,
        confidence=final_decision.confidence,
        resolution_reason=resolution_reason,
        blockers=blockers,
        boosts=boosts,
        final_decision=final_decision,
    )
