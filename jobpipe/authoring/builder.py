from __future__ import annotations

from jobpipe.authoring.case_context import AuthoringCaseContext
from jobpipe.decision.models import (
    CandidateEvidenceContext,
    CandidateNarrativeContext,
    DecisionContext,
)
from jobpipe.model.schema import JobContext


def _enum_val(v: object) -> str:
    """Return v.value if v is an enum member, else str(v)."""
    return v.value if hasattr(v, "value") else str(v)


def build_authoring_case_context(
    job_ctx: JobContext,
    decision_ctx: DecisionContext,
    evidence_ctx: CandidateEvidenceContext,
    narrative_ctx: CandidateNarrativeContext | None,
    *,
    candidate_id: str,
    evaluation_id: str | None = None,
) -> AuthoringCaseContext:
    """
    Deterministic constructor for AuthoringCaseContext.

    Maps already-computed pipeline outputs into the immutable authoring
    contract. No side effects, no agent calls. Call after all required
    pipeline stages (parse, moderate, evidence, decision) have produced
    their outputs.

    Parameters
    ----------
    job_ctx:
        Full pipeline context for the job being authored.
    decision_ctx:
        Decision context produced by build_decision_context().
    evidence_ctx:
        Evidence context produced by build_candidate_evidence_context().
    narrative_ctx:
        Narrative context produced by build_candidate_narrative_context(),
        or None if the narrative stage was skipped.
    candidate_id:
        Caller-supplied candidate identifier. In the pipeline this is
        default_candidate_id() from jobpipe.core.candidate_data. The
        builder does not resolve it to keep the function pure.
    evaluation_id:
        Caller-supplied evaluation identifier, or None. Pipeline convention
        is f"{ctx.meta.run_id}:{ctx.job_id}" but the builder accepts whatever
        the caller provides, including None for MVP or test use.

    Raises
    ------
    ValueError
        If job_ctx.moderator is None (moderation stage absent) or
        job_ctx.parsed is None (parse stage absent).
    """
    if job_ctx.moderator is None:
        raise ValueError(
            f"[job_id={job_ctx.job_id}] moderator output is required to build "
            "AuthoringCaseContext but is absent. Ensure the moderation stage "
            "has completed before calling this constructor."
        )
    if job_ctx.parsed is None:
        raise ValueError(
            f"[job_id={job_ctx.job_id}] parsed job output is required to build "
            "AuthoringCaseContext but is absent. Ensure the parse stage "
            "has completed before calling this constructor."
        )

    job_summary = {
        "title": job_ctx.job.get("title", ""),
        "employer_name": job_ctx.job.get("employer_name", ""),
        "sector": job_ctx.job.get("sector", ""),
        "application_due": job_ctx.job.get("applicationDue"),
        "source_url": job_ctx.job.get("sourceurl", ""),
        "role_summary": job_ctx.parsed.role_summary,
    }

    dt = decision_ctx.decision_table
    decision_brief = {
        "final_decision": _enum_val(job_ctx.moderator.final_decision),
        "recommendation_reason": job_ctx.moderator.recommendation_reason,
        "cv_focus": job_ctx.moderator.cv_focus,
        "act_now": _enum_val(dt.act_now),
        "can_do_score": dt.can_do.score,
        "can_get_score": dt.can_get.score,
        "should_want_score": dt.should_want.score,
        "can_explain_score": dt.can_explain.score,
    }

    selected_evidence = [eu.model_dump() for eu in evidence_ctx.selected_evidence_units]

    narrative_brief: dict | None = None
    if narrative_ctx is not None:
        np_ = narrative_ctx.narrative_profile
        na = narrative_ctx.job_narrative_assessment
        narrative_brief = {
            "core_identity": np_.core_identity,
            "future_direction": np_.future_direction,
            "motivation_themes": np_.motivation_themes,
            "pivot_thesis": np_.pivot_thesis,
            "direction_fit_score": na.direction_fit_score,
            "motivation_fit_score": na.motivation_fit_score,
            "story_strength_score": na.story_strength_score,
            "motivation_brief": na.motivation_brief,
        }

    return AuthoringCaseContext(
        candidate_id=candidate_id,
        job_id=job_ctx.job_id,
        evaluation_id=evaluation_id,
        job_summary=job_summary,
        decision_brief=decision_brief,
        selected_evidence=selected_evidence,
        narrative_brief=narrative_brief,
        artifact_plan=None,
    )
