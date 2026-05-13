"""Compatibility re-export surface.

jobpipe.core.schema is the canonical schema module (consolidated in the
v3-triage refactor).  This file re-exports all core types from there, and
defines the ReactiveResume models that are not in core.schema.

The JobSync* models lived here through the JobSync integration era; they
were removed 2026-05-13 when JobDesk + workspace_server took over the
human-review surface. Older specs and docs may still reference them.
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
ReactiveResumeRenderTarget = Literal["reactive_resume_json", "docx", "pdf"]


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


# ── Authoring session models ──────────────────────────────────────────────────

class SuggestedPatch(BaseModel):
    patch_id: str
    kind: Literal["cover_letter", "summary", "headline", "section_bullet"]
    section_ref: str = ""
    original_text: str = ""
    suggested_text: str
    rationale: str = ""
    status: Literal["pending", "accepted", "rejected"] = "pending"
    created_at: str = ""


class AcceptedPatch(BaseModel):
    patch_id: str
    kind: str
    section_ref: str = ""
    accepted_text: str
    accepted_at: str


class AuthoringSession(BaseModel):
    session_id: str
    job_id: str
    candidate_id: str
    created_at: str
    updated_at: str
    chat_history: List[Dict[str, Any]] = Field(default_factory=list)
    suggested_patches: List[SuggestedPatch] = Field(default_factory=list)
    accepted_patches: List[AcceptedPatch] = Field(default_factory=list)


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
    "ReactiveResumeRenderTarget",
    "ReactiveResumeImportProjection",
    "ReactiveResumeTailoredCVPlan",
    "ReactiveResumeTailoredCVProjection",
    "ReactiveResumeRenderedDocumentRef",
    "SuggestedPatch",
    "AcceptedPatch",
    "AuthoringSession",
]
