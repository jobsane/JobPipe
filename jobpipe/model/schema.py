"""Compatibility re-export surface.

jobpipe.core.schema is the canonical schema module (consolidated in the
v3-triage refactor).  This file re-exports all core types from there, and
defines the JobSync / ReactiveResume models that are not in core.schema.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

# ── Core schema re-exports ───────────────────────────────────────────────────
from jobpipe.core.schema import (  # noqa: F401
    AdvantageAssessmentV3,
    ApplicationCaseProjection,
    ApplicationPackOut,
    ArtifactPlan,
    AuthoringBrief,
    DecisionBrief,
    EvidenceSpan,
    FeatureScore,
    FinalDecision,
    HardGates,
    JobContext,
    JobParse,
    ModeratorOut,
    NarrativeStrategyV3,
    OutcomeFeedback,
    PivotOut,
    ProfileMatchDimensions,
    ProfileMatchOut,
    ReverseDecision,
    ReverseTriageOut,
    RunMeta,
    TriageAmbiguityV3,
    TriageDecision,
    TriageDecisionLabel,
    TriageDecisionV3,
    TriageFeatures,
    TriageOut,
)

# ── Additional type aliases ───────────────────────────────────────────────────
JobSyncStatusEventType = Literal[
    "shortlisted",
    "called",
    "applied",
    "interview",
    "second_interview",
    "accepted",
    "rejected",
    "dismissed",
]
ReactiveResumeRenderTarget = Literal["reactive_resume_json", "docx", "pdf"]


# ── JobSync models ────────────────────────────────────────────────────────────

class JobSyncJobSummary(BaseModel):
    job_id: str
    title: str
    employer: str = ""
    location: str = ""
    application_due: str = ""
    source_url: str = ""
    application_url: str = ""
    updated_at: str = ""


class JobSyncDecisionBrief(BaseModel):
    final_decision: str
    recommendation_reason: str = ""
    decision_table_summary: str = ""
    selection_risk_level: str = ""
    top_claims: List[str] = Field(default_factory=list)
    top_selection_signals: List[str] = Field(default_factory=list)
    top_mitigation_moves: List[str] = Field(default_factory=list)
    top_evidence_units: List[str] = Field(default_factory=list)
    narrative_motivation_brief: str = ""


class JobSyncDocumentRef(BaseModel):
    document_id: str = ""
    kind: str
    status: str = ""
    storage_path: str = ""
    updated_at: str = ""


class JobSyncApplicationCaseProjection(BaseModel):
    job_summary: JobSyncJobSummary
    decision_brief: JobSyncDecisionBrief
    document_refs: List[JobSyncDocumentRef] = Field(default_factory=list)
    current_application_status: str = ""
    last_application_event_at: str = ""
    next_action_hint: str = ""


class JobSyncApplicationStatusEvent(BaseModel):
    job_id: str
    candidate_id: str
    event_type: JobSyncStatusEventType
    event_at: str
    source: str = "jobsync"
    notes: str = ""
    metadata_json: Dict[str, Any] = Field(default_factory=dict)


class JobSyncNoteEvent(BaseModel):
    job_id: str
    candidate_id: str
    note_text: str
    created_at: str
    source: str = "jobsync"


class JobSyncDocumentRefEvent(BaseModel):
    job_id: str
    candidate_id: str
    document_kind: str
    storage_path: str
    status: str = ""
    created_at: str
    source: str = "jobsync"


# ── ReactiveResume models ─────────────────────────────────────────────────────

class ReactiveResumeImportProjection(BaseModel):
    candidate_id: str
    resume_source_id: str
    schema_version: str = "v1"
    basics: Dict[str, Any] = Field(default_factory=dict)
    work: List[Dict[str, Any]] = Field(default_factory=list)
    projects: List[Dict[str, Any]] = Field(default_factory=list)
    education: List[Dict[str, Any]] = Field(default_factory=list)
    skills: List[Dict[str, Any]] = Field(default_factory=list)
    languages: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ReactiveResumeTailoredCVPlan(BaseModel):
    candidate_id: str
    job_id: str
    evaluation_id: str = ""
    variant_strategy: Literal["conservative", "balanced", "aggressive"] = "balanced"
    selected_evidence_unit_ids: List[str] = Field(default_factory=list)
    selected_section_order: List[str] = Field(default_factory=list)
    suppressed_items: List[str] = Field(default_factory=list)
    summary_brief: str = ""
    rewrite_constraints: List[str] = Field(default_factory=list)
    claim_targets: List[str] = Field(default_factory=list)
    selection_mitigation_targets: List[str] = Field(default_factory=list)


class ReactiveResumeTailoredCVProjection(BaseModel):
    headline: str = ""
    summary_text: str = ""
    section_plan: List[Dict[str, Any]] = Field(default_factory=list)
    selected_bullets: List[str] = Field(default_factory=list)
    provenance: Dict[str, Any] = Field(default_factory=dict)
    render_target: ReactiveResumeRenderTarget = "reactive_resume_json"


class ReactiveResumeRenderedDocumentRef(BaseModel):
    document_id: str
    candidate_id: str
    job_id: str
    evaluation_id: str = ""
    kind: str
    storage_path: str
    status: str = "draft"
    producer: str = "reactive_resume"
    updated_at: str
    preview_text: str = ""
    document_json: Dict[str, Any] = Field(default_factory=dict)


__all__ = [
    # core re-exports
    "AdvantageAssessmentV3",
    "ApplicationCaseProjection",
    "ApplicationPackOut",
    "ArtifactPlan",
    "AuthoringBrief",
    "DecisionBrief",
    "EvidenceSpan",
    "FeatureScore",
    "FinalDecision",
    "HardGates",
    "JobContext",
    "JobParse",
    "ModeratorOut",
    "NarrativeStrategyV3",
    "OutcomeFeedback",
    "PivotOut",
    "ProfileMatchDimensions",
    "ProfileMatchOut",
    "ReverseDecision",
    "ReverseTriageOut",
    "RunMeta",
    "TriageAmbiguityV3",
    "TriageDecision",
    "TriageDecisionLabel",
    "TriageDecisionV3",
    "TriageFeatures",
    "TriageOut",
    # local models
    "JobSyncStatusEventType",
    "JobSyncJobSummary",
    "JobSyncDecisionBrief",
    "JobSyncDocumentRef",
    "JobSyncApplicationCaseProjection",
    "JobSyncApplicationStatusEvent",
    "JobSyncNoteEvent",
    "JobSyncDocumentRefEvent",
    "ReactiveResumeRenderTarget",
    "ReactiveResumeImportProjection",
    "ReactiveResumeTailoredCVPlan",
    "ReactiveResumeTailoredCVProjection",
    "ReactiveResumeRenderedDocumentRef",
]
