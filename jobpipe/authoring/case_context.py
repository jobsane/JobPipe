from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AuthoringCaseContext:
    """
    Immutable authoring contract for one candidate and one job.

    Constructed from existing JobPipe state before any document generation.
    The payload stays plain dict/list data so it can be logged, inspected, and
    rehydrated without reaching back through runtime artifacts.

    Fields
    ------
    candidate_id:
        Candidate identifier, from JobContext.meta["candidate_id"].
    job_id:
        Job identifier, from JobContext.job_id.
    evaluation_id:
        Optional evaluation run identifier, from JobContext.meta.get("evaluation_id").
        None is valid for the MVP.
    job_summary:
        Flat job summary from JobContext.job plus JobParse role_summary.
    decision_brief:
        Decision summary from ModeratorOut plus JobDecisionTable signals.
    selected_evidence:
        Serialized CandidateEvidenceSelection dicts selected for this job.
    narrative_brief:
        Optional narrative summary from CandidateNarrativeProfile plus
        JobNarrativeAssessment. None is valid when narrative context is absent.
    artifact_plan:
        Reserved artifact plan. None in the MVP.

    v3 Signals (from advantage_assessment_v3 and narrative_strategy_v3 stages)
    ----------
    advantage_type:
        Advantage classification from advantage_assessment_v3 (e.g. "strong_match").
        None when the v3 stage has not been run.
    differentiation_signals:
        List of differentiating skills/experience strings from advantage_assessment_v3.
        Empty list when the v3 stage has not been run.
    neutralizing_evidence:
        List of gap-neutralizing evidence strings from advantage_assessment_v3.
        Empty list when the v3 stage has not been run.
    recruiter_hook:
        Single-sentence recruiter attention hook from advantage_assessment_v3.
        None when the v3 stage has not been run.
    narrative_positioning_angle:
        Positioning angle string from narrative_strategy_v3.positioning_angle.
        None when the v3 stage has not been run.
    narrative_brand_frame:
        Brand frame string from narrative_strategy_v3.brand_frame.
        None when the v3 stage has not been run.
    narrative_why_me_now:
        Why-me-now rationale from narrative_strategy_v3.why_me_now.
        None when the v3 stage has not been run.
    cover_letter_strategy:
        Cover letter strategy string from narrative_strategy_v3.cover_letter_strategy.
        None when the v3 stage has not been run.
    """

    candidate_id: str
    job_id: str
    evaluation_id: str | None
    job_summary: dict
    decision_brief: dict
    selected_evidence: list[dict]
    narrative_brief: dict | None
    artifact_plan: dict | None

    # v3 signals — all optional to preserve backward compatibility
    advantage_type: str | None = None
    differentiation_signals: list[str] | None = None
    neutralizing_evidence: list[str] | None = None
    recruiter_hook: str | None = None
    narrative_positioning_angle: str | None = None
    narrative_brand_frame: str | None = None
    narrative_why_me_now: str | None = None
    cover_letter_strategy: str | None = None

    # Supplementary profile files — loaded at runtime when present alongside profile_pack
    voice_guide: str | None = None        # content of cover_letter_voice.md
    motivation_context: str | None = None  # content of motivation.md
