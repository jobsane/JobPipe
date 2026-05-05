from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

TriageDecision = Literal["SKIP", "REVIEW", "APPLY_CANDIDATE"]
ReverseDecision = Literal["SKIP_CONFIRMED", "REVIVE_REVIEW", "REVIVE_APPLY"]
FinalDecision = Literal["APPLY_STRONGLY", "APPLY", "REVIEW_HIGH", "REVIEW_LOW", "SKIP"]
TriageDecisionLabel = Literal["discard", "review", "shortlist"]


class EvidenceSpan(BaseModel):
    text: str = Field(min_length=1, max_length=280)
    source: Literal["title", "body", "metadata", "connector"]
    note: Optional[str] = Field(default=None, max_length=160)


class FeatureScore(BaseModel):
    score: int = Field(ge=0, le=100)
    confidence: int = Field(ge=0, le=100)
    reason: str = Field(min_length=1, max_length=240)
    evidence_spans: List[EvidenceSpan] = Field(default_factory=list, max_length=4)


class HardGates(BaseModel):
    title_gate: bool = True
    language_gate: bool = True
    sector_gate: bool = True
    geo_gate: bool = True
    remote_gate: bool = True
    must_have_tech_gate: bool = True
    duplicate_gate: bool = True
    blocker_reasons: List[str] = Field(default_factory=list)

    def passed(self) -> bool:
        return (
            self.title_gate
            and self.language_gate
            and self.sector_gate
            and self.geo_gate
            and self.remote_gate
            and self.must_have_tech_gate
            and self.duplicate_gate
        )


class TriageFeatures(BaseModel):
    core_tech_alignment: FeatureScore
    legacy_burden: FeatureScore
    role_specificity: FeatureScore
    requirement_density: FeatureScore
    geospatial_friction: FeatureScore
    remote_veracity: FeatureScore
    autonomy_level: FeatureScore
    stakeholder_complexity: FeatureScore
    operating_fit: FeatureScore


class TriageDecisionV3(BaseModel):
    label: TriageDecisionLabel
    weighted_score: float = Field(ge=0, le=100)
    confidence: int = Field(ge=0, le=100)
    needs_ambiguity_pass: bool = False
    blockers: List[str] = Field(default_factory=list)
    boosts: List[str] = Field(default_factory=list)
    summary: str = Field(min_length=1, max_length=240)


class TriageAmbiguityV3(BaseModel):
    initial_label: TriageDecisionLabel
    resolved_label: TriageDecisionLabel
    confidence: int = Field(ge=0, le=100)
    resolution_reason: str = Field(min_length=1, max_length=240)
    blockers: List[str] = Field(default_factory=list)
    boosts: List[str] = Field(default_factory=list)
    final_decision: TriageDecisionV3


class AdvantageAssessmentV3(BaseModel):
    advantage_type: Literal["strong_fit", "advantageous_mismatch", "stretch_review", "weak_case"]
    advantage_signals: List[str] = Field(default_factory=list, max_length=6)
    objection_signals: List[str] = Field(default_factory=list, max_length=6)
    neutralizing_evidence: List[str] = Field(default_factory=list, max_length=6)
    differentiation_signals: List[str] = Field(default_factory=list, max_length=6)
    advantageous_match_score: int = Field(default=0, ge=0, le=100)
    applicant_pool_hypothesis: str = Field(default="", max_length=240)
    recruiter_hook: str = Field(default="", max_length=240)
    stretch_level: Literal["low", "medium", "high"]
    review_priority: int = Field(ge=0, le=100)
    confidence: int = Field(ge=0, le=100)
    summary: str = Field(min_length=1, max_length=240)


class NarrativeStrategyV3(BaseModel):
    positioning_angle: str = Field(min_length=1, max_length=240)
    brand_frame: str = Field(min_length=1, max_length=180)
    why_me_now: str = Field(min_length=1, max_length=240)
    top_value_props: List[str] = Field(default_factory=list, min_length=2, max_length=4)
    objections_to_handle: List[str] = Field(default_factory=list, max_length=4)
    cv_focus_order: List[str] = Field(default_factory=list, min_length=2, max_length=6)
    cover_letter_strategy: str = Field(min_length=1, max_length=240)
    confidence: int = Field(ge=0, le=100)
    summary: str = Field(min_length=1, max_length=240)
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


class TriageOut(BaseModel):
    triage_decision: TriageDecision
    confidence: float = Field(ge=0, le=1)
    explanation: str
    signals: List[str] = Field(default_factory=list)
    forced_safety: bool = False
    noise_level: Optional[float] = Field(default=None, ge=0, le=1)
    # Snapshot of the deterministic gates that ran before the LLM triage.
    # Keeps hard skips auditable. None means not produced (older artifacts).
    hard_gates: Optional[HardGates] = None

    @field_validator("confidence")
    @classmethod
    def no_zero_confidence(cls, v: float) -> float:
        if v < 0.10:
            return 0.80
        return v


class ReverseTriageOut(BaseModel):
    reverse_decision: ReverseDecision
    confidence: float = Field(ge=0, le=1)
    rationale: str
    reasoning_flags: List[str] = Field(default_factory=list)


class JobParse(BaseModel):
    role_summary: str
    responsibilities: List[str]
    requirements_must: List[str]
    requirements_nice: List[str]
    seniority: Optional[str] = None
    domain_tags: List[str] = Field(default_factory=list)
    tools_tech: List[str] = Field(default_factory=list)
    org_context: Optional[str] = None
    red_flags: List[str] = Field(default_factory=list)


class ProfileMatchDimensions(BaseModel):
    """Dimension-level scoring for profile match. Each 0-100."""

    role_fit: int = Field(
        ge=0,
        le=100,
        description="Does the role TYPE match (PO, service owner, PM, digital project lead)?",
    )
    domain_fit: int = Field(
        ge=0,
        le=100,
        description="Does the domain/sector match candidate experience?",
    )
    seniority_fit: int = Field(
        ge=0,
        le=100,
        description="Does the seniority/autonomy level match candidate trajectory?",
    )
    skills_fit: int = Field(
        ge=0,
        le=100,
        description="Do the explicit skills/tools/methods required match candidate toolkit?",
    )


class ProfileMatchOut(BaseModel):
    dimensions: Optional[ProfileMatchDimensions] = None
    fit_score: int = Field(ge=0, le=100)
    match_level: Literal["strong", "medium", "weak"]
    overlaps: List[str]
    gaps: List[str]
    hard_blockers: List[str] = Field(default_factory=list)
    notes: str = ""


class PivotOut(BaseModel):
    pivot_score: int = Field(ge=0, le=100)
    pivot_type: str
    potential_risk: Literal["low", "medium", "high"]
    why_it_matters: List[str]


class ModeratorOut(BaseModel):
    final_decision: FinalDecision
    confidence: float = Field(ge=0, le=1)
    recommendation_reason: str
    cv_focus: List[str] = Field(default_factory=list)
    feedback_flags: List[str] = Field(default_factory=list)
    triage_decision_v3: Optional[TriageDecisionV3] = None


class ApplicationPackOut(BaseModel):
    positioning_headline: str
    top_value_props: List[str]
    evidence_map: List[str]
    gap_mitigations: List[str]
    cover_letter_angle: str
    interview_prep: List[str]
    cv_highlights: List[str] = Field(default_factory=list)
    cv_experience_refs: List[str] = Field(default_factory=list)


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


class RunMeta(BaseModel):
    run_id: str
    pipeline_name: str
    created_at: str


class JobContext(BaseModel):
    meta: RunMeta
    job_id: str
    job: Dict[str, Any]
    profile_pack: str

    triage: Optional[TriageOut] = None
    triage_features: Optional[TriageFeatures] = None
    triage_decision_v3: Optional[TriageDecisionV3] = None
    triage_ambiguity_v3: Optional[TriageAmbiguityV3] = None
    advantage_assessment_v3: Optional[AdvantageAssessmentV3] = None
    narrative_strategy_v3: Optional[NarrativeStrategyV3] = None
    reverse_triage: Optional[ReverseTriageOut] = None
    parsed: Optional[JobParse] = None
    profile_match: Optional[ProfileMatchOut] = None
    pivot: Optional[PivotOut] = None
    moderator: Optional[ModeratorOut] = None
    application_pack: Optional[ApplicationPackOut] = None
    notes: Dict[str, Any] = Field(default_factory=dict)

    def snapshot_summary(self) -> Dict[str, Any]:
        # Resolved v3 decision: prefer ambiguity-corrected final_decision when available
        effective_v3 = (
            self.triage_ambiguity_v3.final_decision
            if self.triage_ambiguity_v3
            else self.triage_decision_v3
        )
        return {
            "job_id": self.job_id,
            "title": (self.job.get("title") or "").strip(),
            "employer": (self.job.get("employer_name") or "").strip(),
            "triage_decision": self.triage.triage_decision if self.triage else None,
            "triage_confidence": self.triage.confidence if self.triage else None,
            "triage_signals": self.triage.signals if self.triage else [],
            "final_decision": self.moderator.final_decision if self.moderator else None,
            "fit_score": self.profile_match.fit_score if self.profile_match else None,
            "pivot_score": self.pivot.pivot_score if self.pivot else None,
            "confidence": self.moderator.confidence if self.moderator else None,
            # v3 scoring — from the effective (ambiguity-resolved) decision
            "triage_v3_label": effective_v3.label if effective_v3 else None,
            "triage_v3_weighted_score": effective_v3.weighted_score if effective_v3 else None,
            "triage_v3_confidence": effective_v3.confidence if effective_v3 else None,
            "triage_v3_needs_ambiguity": effective_v3.needs_ambiguity_pass if effective_v3 else None,
            # ambiguity stage resolved label (None when the stage didn't run)
            "triage_ambiguity_label": self.triage_ambiguity_v3.resolved_label if self.triage_ambiguity_v3 else None,
            # advantage assessment
            "advantage_type": self.advantage_assessment_v3.advantage_type if self.advantage_assessment_v3 else None,
            "advantage_match_score": self.advantage_assessment_v3.advantageous_match_score if self.advantage_assessment_v3 else None,
            "advantage_review_priority": self.advantage_assessment_v3.review_priority if self.advantage_assessment_v3 else None,
            # narrative strategy
            "narrative_positioning_angle": self.narrative_strategy_v3.positioning_angle if self.narrative_strategy_v3 else None,
            "narrative_brand_frame": self.narrative_strategy_v3.brand_frame if self.narrative_strategy_v3 else None,
        }


__all__ = [
    "AdvantageAssessmentV3",
    "ApplicationPackOut",
    "EvidenceSpan",
    "FeatureScore",
    "FinalDecision",
    "HardGates",
    "JobContext",
    "JobParse",
    "NarrativeStrategyV3",
    "TriageAmbiguityV3",
    "TriageDecisionLabel",
    "TriageDecisionV3",
    "TriageFeatures",
    "JobSyncApplicationCaseProjection",
    "JobSyncApplicationStatusEvent",
    "JobSyncDecisionBrief",
    "JobSyncDocumentRef",
    "JobSyncDocumentRefEvent",
    "JobSyncJobSummary",
    "JobSyncNoteEvent",
    "JobSyncStatusEventType",
    "ModeratorOut",
    "PivotOut",
    "ProfileMatchDimensions",
    "ProfileMatchOut",
    "ReactiveResumeImportProjection",
    "ReactiveResumeRenderedDocumentRef",
    "ReactiveResumeRenderTarget",
    "ReactiveResumeTailoredCVPlan",
    "ReactiveResumeTailoredCVProjection",
    "ReverseDecision",
    "ReverseTriageOut",
    "RunMeta",
    "TriageDecision",
    "TriageOut",
]
