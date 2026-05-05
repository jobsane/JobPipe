from __future__ import annotations

from jobpipe.core.schema import JobContext, NarrativeStrategyV3
from jobpipe.core.stage_cache import stable_payload_hash


def build_narrative_strategy(ctx: JobContext) -> NarrativeStrategyV3:
    job = ctx.job or {}
    parsed = ctx.parsed
    match = ctx.profile_match
    pivot = ctx.pivot
    advantage = ctx.advantage_assessment_v3
    moderator = ctx.moderator

    title = str(job.get("title") or "").strip() or "rollen"
    employer = str(job.get("employer_name") or "").strip() or "virksomheten"
    role_summary = parsed.role_summary if parsed and parsed.role_summary else title

    advantage_signals = list(advantage.advantage_signals) if advantage else []
    objection_signals = list(advantage.objection_signals) if advantage else []
    overlaps = list(match.overlaps) if match else []
    pivot_why = list(pivot.why_it_matters) if pivot else []

    if advantage and advantage.advantage_type == "strong_fit":
        positioning_angle = f"Direkte relevant erfaring som kan levere raskt i {title} hos {employer}."
        brand_frame = "Trygg leverandør av digitalt eierskap"
    elif advantage and advantage.advantage_type == "advantageous_mismatch":
        positioning_angle = f"Overførbar erfaring som gir en uvant, men sterk inngang til {title} hos {employer}."
        brand_frame = "Brobygger mellom produkt, drift og endring"
    elif advantage and advantage.advantage_type == "stretch_review":
        positioning_angle = f"Realistisk stretch-case der relevant eierskapserfaring kan oversettes til {title} hos {employer}."
        brand_frame = "Tydelig utviklingscase med relevant tyngde"
    else:
        positioning_angle = f"Krev en nøktern og presis sak for hvorfor erfaringen passer til {title} hos {employer}."
        brand_frame = "Må underbygge relevansen konkret"

    top_value_props = []
    for value in overlaps[:2]:
        top_value_props.append(value)
    for value in advantage_signals[:4]:
        if value not in top_value_props:
            top_value_props.append(value)
        if len(top_value_props) >= 4:
            break
    while len(top_value_props) < 2:
        fallback = role_summary if len(top_value_props) == 0 else "tydelig gjennomføring"
        if fallback not in top_value_props:
            top_value_props.append(fallback)

    cv_focus_order = []
    if moderator and moderator.cv_focus:
        cv_focus_order.extend(moderator.cv_focus[:3])
    for item in top_value_props:
        if item not in cv_focus_order:
            cv_focus_order.append(item)
        if len(cv_focus_order) >= 6:
            break
    if pivot_why:
        for item in pivot_why[:2]:
            if item not in cv_focus_order:
                cv_focus_order.append(item)
    cv_focus_order = cv_focus_order[:6]
    while len(cv_focus_order) < 2:
        cv_focus_order.append("relevant leveranse")

    objections_to_handle = objection_signals[:4]
    why_me_now_parts = []
    if overlaps:
        why_me_now_parts.append(f"Har allerede erfaring som matcher {overlaps[0]}.")
    if pivot_why:
        why_me_now_parts.append(f"Kan oversette tidligere leveranser gjennom {pivot_why[0]}.")
    if not why_me_now_parts:
        why_me_now_parts.append(f"Har relevant erfaring som kan kobles direkte til {role_summary}.")
    why_me_now = " ".join(why_me_now_parts)[:240]

    cover_letter_strategy = (
        f"Åpne med {positioning_angle.lower()} "
        f"og underbygg med {', '.join(top_value_props[:2])}."
    )[:240]

    confidence_parts = []
    if advantage:
        confidence_parts.append(advantage.confidence)
    if ctx.triage_decision_v3:
        confidence_parts.append(ctx.triage_decision_v3.confidence)
    if ctx.triage_ambiguity_v3:
        confidence_parts.append(ctx.triage_ambiguity_v3.confidence)
    confidence = round(sum(confidence_parts) / len(confidence_parts)) if confidence_parts else 65

    summary = f"Narrative strategy for {title} with {len(top_value_props)} prioritized value props."

    return NarrativeStrategyV3(
        positioning_angle=positioning_angle,
        brand_frame=brand_frame,
        why_me_now=why_me_now,
        top_value_props=top_value_props[:4],
        objections_to_handle=objections_to_handle,
        cv_focus_order=cv_focus_order,
        cover_letter_strategy=cover_letter_strategy,
        confidence=confidence,
        summary=summary,
    )


def narrative_strategy_v3_cache_key(ctx: JobContext) -> str:
    job = ctx.job or {}
    payload = {
        "version": "narrative_strategy_v3.v1",
        "job": {
            "title": job.get("title"),
            "employer_name": job.get("employer_name"),
        },
        "parsed": ctx.parsed.model_dump() if ctx.parsed else None,
        "profile_match": ctx.profile_match.model_dump() if ctx.profile_match else None,
        "pivot": ctx.pivot.model_dump() if ctx.pivot else None,
        "advantage_assessment_v3": ctx.advantage_assessment_v3.model_dump() if ctx.advantage_assessment_v3 else None,
        "moderator": ctx.moderator.model_dump() if ctx.moderator else None,
    }
    return stable_payload_hash(payload)


def narrative_strategy_v3_stage_factory():
    def should_run(ctx: JobContext) -> bool:
        return bool(ctx.advantage_assessment_v3 and (ctx.profile_match or ctx.parsed))

    def run(ctx: JobContext, job_dir: str) -> JobContext:  # noqa: ARG001
        ctx.narrative_strategy_v3 = build_narrative_strategy(ctx)
        return ctx

    return should_run, run
