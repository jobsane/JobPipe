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
    """

    candidate_id: str
    job_id: str
    evaluation_id: str | None
    job_summary: dict
    decision_brief: dict
    selected_evidence: list[dict]
    narrative_brief: dict | None
    artifact_plan: dict | None
