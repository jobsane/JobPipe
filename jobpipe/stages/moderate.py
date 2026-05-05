from __future__ import annotations

from typing import Any, Dict

from jobpipe.core.profile_pack import parse_profile_pack
from jobpipe.core.schema import HardGates
from jobpipe.core.triage_v3 import aggregate_triage_decision
from jobpipe.decision import derive_selection_assessment
from jobpipe.model.schema import JobContext, ModeratorOut
from jobpipe.stages.triage_decision_v3 import persist_triage_decision_v3
from jobpipe.stages.triage_features import build_triage_features, persist_triage_features


_SCOPE_CAUTION_TERMS = ("early", "junior", "coordinator", "associate", "specialist", "operations")
_PRODUCT_FAMILY_TERMS = ("product", "produkt")


def _clamp01(x) -> float:
    try:
        x = float(x)
    except Exception:
        return 0.0
    return max(0.0, min(1.0, x))


def _v3_adjust_decision(
    initial: str,
    ctx: JobContext,
    *,
    v3_review_priority_boost: int,
    v3_discard_demote: bool,
) -> tuple[str, str]:
    """
    Refine initial moderation decision using v3 triage context.

    Rules (calibrated against April-24 run — 99.6% SKIP, 46 KEEPs):
    - v3 discard + REVIEW_LOW  → SKIP  (v3 confirms borderline is not worth Lars's time)
    - v3 discard + REVIEW_HIGH → REVIEW_LOW  (soften — fit is decent but v3 sees red flags)
    - v3 shortlist + REVIEW_LOW → REVIEW_HIGH  (v3 sees structural advantage, promote)
    - review_priority >= boost + REVIEW_LOW → REVIEW_HIGH  (high-priority review case)

    None of these override SKIP, APPLY, or APPLY_STRONGLY — the hard gates and strong
    signals stay intact.
    """
    # Resolve v3 label: prefer ambiguity-corrected label
    decision = ctx.triage_decision_v3
    ambiguity = ctx.triage_ambiguity_v3
    advantage = ctx.advantage_assessment_v3

    v3_label = None
    if ambiguity:
        v3_label = ambiguity.resolved_label
    elif decision:
        v3_label = decision.label

    review_priority = advantage.review_priority if advantage else None

    if v3_label is None:
        return initial, ""

    note_parts: list[str] = []
    result = initial

    if v3_discard_demote and v3_label == "discard":
        if initial == "REVIEW_LOW":
            result = "SKIP"
            note_parts.append("v3_discard_demote_review_low")
        elif initial == "REVIEW_HIGH":
            result = "REVIEW_LOW"
            note_parts.append("v3_discard_soften_review_high")
    elif v3_label == "shortlist" and initial == "REVIEW_LOW":
        result = "REVIEW_HIGH"
        note_parts.append("v3_shortlist_upgrade")
    elif (
        review_priority is not None
        and review_priority >= v3_review_priority_boost
        and initial == "REVIEW_LOW"
    ):
        result = "REVIEW_HIGH"
        note_parts.append(f"v3_review_priority={review_priority}")

    return result, ", ".join(note_parts)


def moderate_stage_factory(thresholds: Dict[str, Any]):
    """
    Deterministisk moderatorlogikk.

    Grunnregler:
    - fit < review_min_fit  → SKIP (uansett pivot og v3)
    - fit < review_high_min_fit → REVIEW_LOW (startpunkt, kan justeres av v3)
    - svake REVIEW_LOW-kandidater kan demoteres ved kandidatrisiko (off-anchor-profil)
    - v3 triage-kontekst kan løfte REVIEW_LOW → REVIEW_HIGH eller senke REVIEW_HIGH → REVIEW_LOW
    """

    thr = thresholds or {}

    apply_strong_fit = int(thr.get("apply_strong_fit", 78))
    apply_fit = int(thr.get("apply_fit", 66))
    pivot_boost_apply = int(thr.get("pivot_boost_apply", 72))
    review_min_fit = int(thr.get("review_min_fit", 25))
    review_high_min_fit = int(thr.get("review_high_min_fit", 52))

    # v3 integration thresholds
    # review_priority >= this → upgrade REVIEW_LOW to REVIEW_HIGH
    v3_review_priority_boost = int(thr.get("v3_review_priority_boost", 60))
    # v3 discard label demotes borderline REVIEW_LOW → SKIP and REVIEW_HIGH → REVIEW_LOW
    v3_discard_demote = str(thr.get("v3_discard_demote", "true")).lower() not in ("false", "0", "no")

    def _profile_text(candidate_profile: dict[str, Any]) -> str:
        snapshot = candidate_profile.get("snapshot") or {}
        return " ".join(
            str(part).strip()
            for part in (
                snapshot.get("level"),
                snapshot.get("positioning"),
                candidate_profile.get("strategic_direction"),
            )
            if str(part).strip()
        ).lower()

    def _profile_list(candidate_profile: dict[str, Any], *path: str) -> list[str]:
        current: Any = candidate_profile
        for key in path:
            if not isinstance(current, dict):
                return []
            current = current.get(key)
        if not isinstance(current, list):
            return []
        return [str(value).strip() for value in current if str(value).strip()]

    def _supports_broad_product_scope(candidate_profile: dict[str, Any]) -> bool:
        targets = [
            *_profile_list(candidate_profile, "target_roles", "primary"),
            *_profile_list(candidate_profile, "target_roles", "secondary"),
        ]
        for target in targets:
            normalized = target.lower()
            if not any(term in normalized for term in _PRODUCT_FAMILY_TERMS):
                continue
            if any(term in normalized for term in _SCOPE_CAUTION_TERMS):
                continue
            return True
        return False

    def _candidate_risk_demotes_review(ctx: JobContext, fit: int, pivot: int) -> bool:
        profile_pack = str(ctx.profile_pack or "").strip()
        if not profile_pack:
            return False

        candidate_profile = parse_profile_pack(profile_pack)
        if not candidate_profile:
            return False

        title = str(ctx.job.get("normalized_title") or ctx.job.get("title") or "").strip()
        if not title:
            return False

        assessment = derive_selection_assessment(
            {
                "title": title,
                "sector": str(ctx.job.get("sector") or "").strip(),
                "fit_score": fit,
                "pivot_score": pivot,
                "triage_signals": list(getattr(ctx.triage, "signals", []) or []),
                "detail": {
                    "hard_blockers": list(getattr(ctx.profile_match, "hard_blockers", []) or []),
                },
            },
            candidate_profile=candidate_profile,
        )

        candidate_flags = assessment.assessment_json.get("candidate_profile_flags", {})
        profile_text = _profile_text(candidate_profile)
        return (
            bool(candidate_flags.get("product_leadership_off_anchor"))
            and any(term in profile_text for term in _SCOPE_CAUTION_TERMS)
            and not _supports_broad_product_scope(candidate_profile)
            and assessment.selection_risk_level == "very_high"
        )

    def should_run(ctx: JobContext) -> bool:
        return True

    def run(ctx: JobContext, job_dir: str) -> JobContext:
        fit = int((ctx.profile_match.fit_score if ctx.profile_match else 0) or 0)
        pivot = int((ctx.pivot.pivot_score if ctx.pivot else 0) or 0)

        # 1) hard gate — v3 cannot override this
        if fit < review_min_fit:
            final = "SKIP"
        # 2) borderline zone — start REVIEW_LOW, v3 may adjust
        elif fit < review_high_min_fit:
            final = "REVIEW_LOW"
        else:
            # 3) normal path
            if fit >= apply_strong_fit:
                final = "APPLY_STRONGLY"
            elif fit >= apply_fit:
                final = "APPLY"
            else:
                final = "REVIEW_HIGH" if pivot >= pivot_boost_apply else "REVIEW_LOW"

        # Existing candidate-risk demotion (runs before v3 to preserve its semantics)
        candidate_risk_demoted = False
        if final == "REVIEW_LOW" and _candidate_risk_demotes_review(ctx, fit, pivot):
            final = "SKIP"
            candidate_risk_demoted = True

        # --- v3 fallback builder ---
        # If the dedicated v3 stages didn't run (e.g. pipeline config omits them),
        # build triage_features and triage_decision_v3 here so ModeratorOut always
        # carries a v3 snapshot and the v3 adjustment below has something to work with.
        if ctx.triage_features is None:
            ctx.triage_features = build_triage_features(ctx)
            persist_triage_features(job_dir, ctx.triage_features)

        hard_gates = ctx.triage.hard_gates if ctx.triage and ctx.triage.hard_gates else HardGates()
        if ctx.triage_decision_v3 is None:
            ctx.triage_decision_v3 = aggregate_triage_decision(ctx.triage_features, hard_gates)
            persist_triage_decision_v3(job_dir, ctx.triage_decision_v3)

        # v3 adjustment (only when we're still in a REVIEW zone — not SKIP/APPLY)
        v3_note = ""
        if final in ("REVIEW_LOW", "REVIEW_HIGH"):
            final, v3_note = _v3_adjust_decision(
                final,
                ctx,
                v3_review_priority_boost=v3_review_priority_boost,
                v3_discard_demote=v3_discard_demote,
            )

        conf = 0.40 + 0.45 * _clamp01(fit / 100.0) + 0.15 * _clamp01(pivot / 100.0)
        conf = round(float(_clamp01(conf)), 2)

        reason_parts = [f"fit={fit}, pivot={pivot}"]
        if candidate_risk_demoted:
            reason_parts.append("candidate_risk=off_anchor_product_leadership_scope")
        if v3_note:
            reason_parts.append(v3_note)
        reason = ", ".join(reason_parts)

        # Resolved v3 decision: prefer ambiguity-corrected when available
        effective_v3 = (
            ctx.triage_ambiguity_v3.final_decision
            if ctx.triage_ambiguity_v3
            else ctx.triage_decision_v3
        )

        ctx.moderator = ModeratorOut(
            final_decision=final,
            confidence=conf,
            recommendation_reason=reason,
            cv_focus=[],
            feedback_flags=[],
            triage_decision_v3=effective_v3,
        )
        return ctx

    return should_run, run
