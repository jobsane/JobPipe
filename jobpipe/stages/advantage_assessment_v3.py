from __future__ import annotations

from jobpipe.core.schema import AdvantageAssessmentV3, JobContext
from jobpipe.core.stage_cache import stable_payload_hash


def build_advantage_assessment(ctx: JobContext) -> AdvantageAssessmentV3:
    features = ctx.triage_features
    decision = ctx.triage_ambiguity_v3.final_decision if ctx.triage_ambiguity_v3 else ctx.triage_decision_v3
    profile_match = ctx.profile_match
    pivot = ctx.pivot

    advantage_signals: list[str] = []
    objection_signals: list[str] = []
    neutralizing_evidence: list[str] = []
    differentiation_signals: list[str] = []

    if profile_match:
        advantage_signals.extend(profile_match.overlaps[:3])
        objection_signals.extend(profile_match.gaps[:3])
        neutralizing_evidence.extend(profile_match.overlaps[:2])
        differentiation_signals.extend(profile_match.overlaps[:2])

    if features:
        if features.core_tech_alignment.score >= 75:
            advantage_signals.append("strong_core_tech_alignment")
            differentiation_signals.append("core stack + ownership range")
        if features.role_specificity.score >= 70:
            advantage_signals.append("strong_role_specificity")
            differentiation_signals.append("role language maps cleanly to prior ownership")
        if features.remote_veracity.score >= 80:
            advantage_signals.append("credible_remote_flexibility")
        if features.legacy_burden.score < 40:
            objection_signals.append("legacy_heavy_context")
        if features.operating_fit.score < 45:
            objection_signals.append("operating_fit_risk")
        if features.stakeholder_complexity.score >= 65 and features.autonomy_level.score >= 65:
            differentiation_signals.append("cross-functional operating range")
        if features.operating_fit.score >= 65 and features.legacy_burden.score >= 55:
            differentiation_signals.append("can own live operations without sounding like a caretaker")

    if pivot and pivot.pivot_score >= 70:
        advantage_signals.append("high_transferable_pivot")
        neutralizing_evidence.extend(pivot.why_it_matters[:2])
        differentiation_signals.append("transferable scope beyond literal title match")
    elif pivot and pivot.potential_risk == "high":
        objection_signals.append("high_pivot_risk")

    if decision:
        if decision.label == "shortlist":
            advantage_type = "strong_fit"
        elif decision.label == "review" and pivot and pivot.pivot_score >= 70:
            advantage_type = "advantageous_mismatch"
        elif decision.label == "review":
            advantage_type = "stretch_review"
        else:
            advantage_type = "weak_case"
    else:
        advantage_type = "stretch_review"

    objection_count = len(set(objection_signals))
    if objection_count <= 1:
        stretch_level = "low"
    elif objection_count <= 3:
        stretch_level = "medium"
    else:
        stretch_level = "high"

    advantageous_match_score = 10
    if decision:
        advantageous_match_score += {"discard": 0, "review": 12, "shortlist": 24}[decision.label]
    if features:
        advantageous_match_score += round(features.core_tech_alignment.score * 0.22)
        advantageous_match_score += round(features.role_specificity.score * 0.18)
        advantageous_match_score += round(features.stakeholder_complexity.score * 0.08)
        advantageous_match_score += round(features.autonomy_level.score * 0.08)
        advantageous_match_score += round(features.operating_fit.score * 0.08)
        advantageous_match_score -= round(max(0, 50 - features.legacy_burden.score) * 0.18)
    if pivot:
        advantageous_match_score += round(pivot.pivot_score * 0.08)
    advantageous_match_score -= len(set(objection_signals)) * 4
    advantageous_match_score = max(0, min(100, advantageous_match_score))

    if advantage_type == "advantageous_mismatch":
        applicant_pool_hypothesis = (
            "Likely screened against candidates with more literal domain history; "
            "transferable ownership and delivery evidence must land early."
        )
    elif advantage_type == "strong_fit" and features and features.stakeholder_complexity.score >= 65:
        applicant_pool_hypothesis = (
            "Likely compared against generic product or service-owner candidates; "
            "operating range and stakeholder handling can differentiate."
        )
    elif advantage_type == "stretch_review":
        applicant_pool_hypothesis = (
            "Needs a sharper first-impression story than a standard fit case because "
            "recruiters may default to closer title or domain matches."
        )
    else:
        applicant_pool_hypothesis = (
            "Competing case is not yet self-evident; the value story needs clear proof, "
            "not only general fit language."
        )

    primary_overlap = ""
    if profile_match and profile_match.overlaps:
        primary_overlap = str(profile_match.overlaps[0])
    elif differentiation_signals:
        primary_overlap = str(differentiation_signals[0])
    else:
        primary_overlap = "end-to-end ownership"

    if pivot and pivot.pivot_score >= 70 and pivot.why_it_matters:
        recruiter_hook = (
            f"Lead with {primary_overlap} and frame {pivot.why_it_matters[0]} "
            "as proof that the move is less risky than it first appears."
        )
    elif features and features.stakeholder_complexity.score >= 65:
        recruiter_hook = (
            f"Lead with {primary_overlap} and stress cross-functional delivery ownership "
            "instead of generic product language."
        )
    else:
        recruiter_hook = (
            f"Lead with {primary_overlap} and make the immediate business value explicit "
            "in the first lines."
        )

    base_priority = 30
    if decision:
        base_priority += {"discard": 0, "review": 18, "shortlist": 35}[decision.label]
    if features:
        base_priority += round(features.core_tech_alignment.score * 0.15)
        base_priority += round(features.role_specificity.score * 0.10)
        base_priority -= round(max(0, 50 - features.legacy_burden.score) * 0.20)
    if pivot:
        base_priority += round(pivot.pivot_score * 0.08)
    review_priority = max(0, min(100, base_priority))

    confidence_parts: list[int] = []
    if features:
        confidence_parts.extend(
            [
                features.core_tech_alignment.confidence,
                features.role_specificity.confidence,
                features.operating_fit.confidence,
            ]
        )
    if decision:
        confidence_parts.append(decision.confidence)
    confidence = round(sum(confidence_parts) / len(confidence_parts)) if confidence_parts else 60

    summary = (
        f"{advantage_type} with advantageous-match score {advantageous_match_score}, "
        f"{len(set(advantage_signals))} advantage signals and {len(set(objection_signals))} objections."
    )

    return AdvantageAssessmentV3(
        advantage_type=advantage_type,
        advantage_signals=list(dict.fromkeys(advantage_signals))[:6],
        objection_signals=list(dict.fromkeys(objection_signals))[:6],
        neutralizing_evidence=list(dict.fromkeys(neutralizing_evidence))[:6],
        differentiation_signals=list(dict.fromkeys(differentiation_signals))[:6],
        advantageous_match_score=advantageous_match_score,
        applicant_pool_hypothesis=applicant_pool_hypothesis,
        recruiter_hook=recruiter_hook,
        stretch_level=stretch_level,
        review_priority=review_priority,
        confidence=confidence,
        summary=summary,
    )


def advantage_assessment_v3_cache_key(ctx: JobContext) -> str:
    decision = ctx.triage_ambiguity_v3.final_decision if ctx.triage_ambiguity_v3 else ctx.triage_decision_v3
    payload = {
        "version": "advantage_assessment_v3.v1",
        "triage_features": ctx.triage_features.model_dump() if ctx.triage_features else None,
        "decision": decision.model_dump() if decision else None,
        "profile_match": ctx.profile_match.model_dump() if ctx.profile_match else None,
        "pivot": ctx.pivot.model_dump() if ctx.pivot else None,
    }
    return stable_payload_hash(payload)


def advantage_assessment_v3_stage_factory():
    def should_run(ctx: JobContext) -> bool:
        return bool(ctx.triage_features and (ctx.triage_decision_v3 or ctx.triage_ambiguity_v3))

    def run(ctx: JobContext, job_dir: str) -> JobContext:  # noqa: ARG001
        ctx.advantage_assessment_v3 = build_advantage_assessment(ctx)
        return ctx

    return should_run, run
