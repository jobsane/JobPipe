from __future__ import annotations

from typing import Any, Dict, Callable, Tuple

from jobpipe.core.schema import JobContext, ModeratorOut


def _clamp01(x) -> float:
    try:
        x = float(x)
    except Exception:
        return 0.0
    return max(0.0, min(1.0, x))


def moderate_stage_factory(thresholds: Dict[str, Any]):
    """
    Deterministisk moderatorlogikk.

    Regler (som du ba om):
    - hvis fit < review_min_fit  -> SKIP (uansett pivot)
    - hvis fit < review_high_min_fit -> REVIEW_LOW (selv om pivot er høy)
    """

    thr = thresholds or {}

    # eksisterende terskler (fallbacks)
    apply_strong_fit = int(thr.get("apply_strong_fit", 78))
    apply_fit = int(thr.get("apply_fit", 66))
    pivot_boost_apply = int(thr.get("pivot_boost_apply", 72))

    # NYE "gate"-terskler
    review_min_fit = int(thr.get("review_min_fit", 25))              # <- løsere gate (justér i yaml)
    review_high_min_fit = int(thr.get("review_high_min_fit", 52))    # <- under denne blir det alltid REVIEW_LOW

    def should_run(ctx: JobContext) -> bool:
        return True

    def run(ctx: JobContext, job_dir: str) -> JobContext:
        fit = int((ctx.profile_match.fit_score if ctx.profile_match else 0) or 0)
        pivot = int((ctx.pivot.pivot_score if ctx.pivot else 0) or 0)

        # 1) hard gate
        if fit < review_min_fit:
            final = "SKIP"
        # 2) mid gate: alltid REVIEW_LOW
        elif fit < review_high_min_fit:
            final = "REVIEW_LOW"
        else:
            # 3) normal logikk videre
            if fit >= apply_strong_fit:
                final = "APPLY_STRONGLY"
            elif fit >= apply_fit:
                final = "APPLY"
            else:
                final = "REVIEW_HIGH" if pivot >= pivot_boost_apply else "REVIEW_LOW"

        # enkel, stabil confidence
        conf = 0.40 + 0.45 * _clamp01(fit / 100.0) + 0.15 * _clamp01(pivot / 100.0)
        conf = round(float(_clamp01(conf)), 2)

        ctx.moderator = ModeratorOut(
            final_decision=final,
            confidence=conf,
            recommendation_reason=f"fit={fit}, pivot={pivot}",
            cv_focus=[],
            feedback_flags=[],
        )
        return ctx

    return should_run, run
