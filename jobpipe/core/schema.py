from __future__ import annotations
from typing import Any, Dict, List, Optional, Literal
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

    @field_validator("recruiter_hook", "applicant_pool_hypothesis", "summary", mode="before")
    @classmethod
    def _truncate_str(cls, v: Any) -> Any:
        """Truncate LLM-generated strings that exceed the display limit rather than hard-failing."""
        if isinstance(v, str) and len(v) > 240:
            return v[:237] + "..."
        return v


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

    @field_validator(
        "positioning_angle",
        "why_me_now",
        "cover_letter_strategy",
        "summary",
        mode="before",
    )
    @classmethod
    def _truncate_240(cls, v: Any) -> Any:
        """Truncate LLM or template strings that exceed the 240-char display cap.

        Without this, a long employer + title combo in the
        ``narrative_strategy_v3.build_narrative_strategy`` f-strings can
        overflow and Pydantic refuses to parse — silently losing the entire
        case from the shortlist (see 2026-05-16 c968ed47 incident).
        """
        if isinstance(v, str) and len(v) > 240:
            return v[:237] + "..."
        return v

    @field_validator("brand_frame", mode="before")
    @classmethod
    def _truncate_180(cls, v: Any) -> Any:
        if isinstance(v, str) and len(v) > 180:
            return v[:177] + "..."
        return v

class TriageOut(BaseModel):
    triage_decision: TriageDecision
    confidence: float = Field(ge=0, le=1)
    explanation: str
    signals: List[str] = Field(default_factory=list)
    forced_safety: bool = False
    # Additive field: HR-noise detector. 0.0 = clean/substantive, 1.0 = pure fluff/buzzwords.
    # High noise_level (>0.7) combined with low confidence is a strong SKIP signal.
    # None means the field was not produced (older artifacts, geo/hard-no skips).
    noise_level: Optional[float] = Field(default=None, ge=0, le=1)
    # Topic 19 additive field: snapshot of the deterministic gates that already
    # ran before the broader triage LLM. Keeps hard skips auditable.
    hard_gates: Optional[HardGates] = None

    @field_validator("confidence")
    @classmethod
    def no_zero_confidence(cls, v: float) -> float:
        """
        The nano model sometimes returns 0.0 as a non-answer rather than
        a calibrated score. A SKIP with genuine uncertainty should be ≥0.50
        (and would trigger reverse_triage). A SKIP with certainty should be
        ≥0.85. 0.0 is never a valid calibrated confidence — clamp it to 0.80
        so it doesn't falsely trigger reverse_triage on obvious rejects.
        """
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
    role_fit: int = Field(ge=0, le=100,
        description="Does the role TYPE match (PO, service owner, PM, digital project lead)?")
    domain_fit: int = Field(ge=0, le=100,
        description="Does the domain/sector match candidate experience?")
    seniority_fit: int = Field(ge=0, le=100,
        description="Does the seniority/autonomy level match candidate trajectory?")
    skills_fit: int = Field(ge=0, le=100,
        description="Do the explicit skills/tools/methods required match candidate toolkit?")

class ProfileMatchOut(BaseModel):
    # --- new: dimension breakdown (additive, does not break existing consumers) ---
    dimensions: Optional[ProfileMatchDimensions] = None

    # --- existing fields (unchanged) ---
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
    evidence_map: List[str]  # "Job need -> your proof"
    gap_mitigations: List[str]
    cover_letter_angle: str        # Strategic angle / approach (internal, used as basis for the letter)
    cover_letter_text: str = ""    # Complete, ready-to-send søknadsbrev (230-260 words, Norwegian)
    interview_prep: List[str]
    # --- Tailored CV highlights (additive) ---
    # AI-selected experience bullets from JSON Resume most relevant to this job.
    # Each entry is a standalone bullet ready to paste into a CV/cover letter.
    # Must mirror job posting terminology. Must NOT invent experience.
    cv_highlights: List[str] = Field(default_factory=list)
    # Source references for traceability: e.g. "Brownells Europe (2015-2022)"
    cv_experience_refs: List[str] = Field(default_factory=list)


class DecisionBrief(BaseModel):
    schema_version: str
    final_decision: str = ""
    triage_v3_label: str = ""
    fit_score: Optional[int] = None
    pivot_score: Optional[int] = None
    advantage_type: str = ""
    advantageous_match_score: Optional[int] = None
    review_priority: Optional[int] = None
    positioning_angle: str = ""
    brand_frame: str = ""
    applicant_pool_hypothesis: str = ""
    recruiter_hook: str = ""
    rationale: str = ""
    overlaps: List[str] = Field(default_factory=list)
    gaps: List[str] = Field(default_factory=list)
    differentiation_signals: List[str] = Field(default_factory=list)
    top_value_props: List[str] = Field(default_factory=list)
    cv_focus: List[str] = Field(default_factory=list)
    cover_letter_angle: str = ""


class AuthoringBrief(BaseModel):
    schema_version: str
    artifact_kind: Literal["resume", "cover_letter", "screening_answers"]
    objective: str = ""
    handoff_brief: str = ""
    launch_url: str = ""
    seed_text: str = ""
    inputs: Dict[str, Any] = Field(default_factory=dict)


class ArtifactPlan(BaseModel):
    schema_version: str
    artifact_root: str = ""
    input_snapshot_path: str = ""
    save_targets: Dict[str, Any] = Field(default_factory=dict)
    generated_artifacts: List[Dict[str, Any]] = Field(default_factory=list)


class ApplicationCaseProjection(BaseModel):
    schema_version: str
    external_source: str
    external_id: str
    run_id: str = ""
    status: str = ""
    updated_at: str = ""
    job_summary: Dict[str, Any] = Field(default_factory=dict)
    decision_brief: DecisionBrief
    artifact_plan: ArtifactPlan


class OutcomeFeedback(BaseModel):
    schema_version: str
    external_source: str
    external_id: str
    run_id: str = ""
    final_decision: str = ""
    shared_status: str = ""
    outcome_label: str = ""
    outcome_source: str = ""
    app_notes: str = ""
    updated_at: str = ""
    artifact_refs_used: List[Dict[str, Any]] = Field(default_factory=list)
    decision_brief: DecisionBrief
    application_case_projection: ApplicationCaseProjection


class RunMeta(BaseModel):
    run_id: str
    pipeline_name: str
    created_at: str

class JobContext(BaseModel):
    meta: RunMeta
    job_id: str
    job: Dict[str, Any]
    profile_pack: str

    # stage outputs
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

    # internal helpers
    notes: Dict[str, Any] = Field(default_factory=dict)

    def snapshot_summary(self) -> Dict[str, Any]:
        effective_triage_v3 = self.triage_ambiguity_v3.final_decision if self.triage_ambiguity_v3 else self.triage_decision_v3
        return {
            "job_id": self.job_id,
            "title": (self.job.get("title") or "").strip(),
            "employer": (self.job.get("employer_name") or "").strip(),
            "triage_decision": self.triage.triage_decision if self.triage else None,
            "triage_confidence": self.triage.confidence if self.triage else None,
            "triage_signals": self.triage.signals if self.triage else [],
            "triage_v3_label": effective_triage_v3.label if effective_triage_v3 else None,
            "triage_v3_weighted_score": effective_triage_v3.weighted_score if effective_triage_v3 else None,
            "triage_v3_confidence": effective_triage_v3.confidence if effective_triage_v3 else None,
            "triage_v3_needs_ambiguity": effective_triage_v3.needs_ambiguity_pass if effective_triage_v3 else None,
            "triage_ambiguity_label": self.triage_ambiguity_v3.resolved_label if self.triage_ambiguity_v3 else None,
            "advantage_type": self.advantage_assessment_v3.advantage_type if self.advantage_assessment_v3 else None,
            "advantageous_match_score": (
                self.advantage_assessment_v3.advantageous_match_score if self.advantage_assessment_v3 else None
            ),
            "advantage_review_priority": (
                self.advantage_assessment_v3.review_priority if self.advantage_assessment_v3 else None
            ),
            "narrative_positioning_angle": (
                self.narrative_strategy_v3.positioning_angle if self.narrative_strategy_v3 else None
            ),
            "narrative_brand_frame": self.narrative_strategy_v3.brand_frame if self.narrative_strategy_v3 else None,
            "final_decision": self.moderator.final_decision if self.moderator else None,
            "fit_score": self.profile_match.fit_score if self.profile_match else None,
            "pivot_score": self.pivot.pivot_score if self.pivot else None,
            "confidence": self.moderator.confidence if self.moderator else None,
            # Rich list/prose fields from upstream deterministic stages. The
            # workspace read model uses these to render concrete strengths,
            # gaps, and per-dimension rationales instead of tag-translations.
            # All optional — drop into signals JSONB only when the stage ran.
            #
            # parse-stage projections drive the Job context summary and ATS
            # keywords list in JobDesk. parsed_role_summary replaces the
            # truncated raw ad description as the case summary. parsed_domain_tags
            # + parsed_tools_tech replace the occupation-taxonomy fallback for
            # ATS keywords with real ad-extracted terms.
            "parsed_role_summary": (
                self.parsed.role_summary if self.parsed else ""
            ),
            "parsed_domain_tags": (
                list(self.parsed.domain_tags) if self.parsed else []
            ),
            "parsed_tools_tech": (
                list(self.parsed.tools_tech) if self.parsed else []
            ),
            "profile_match_overlaps": (
                list(self.profile_match.overlaps) if self.profile_match else []
            ),
            "profile_match_gaps": (
                list(self.profile_match.gaps) if self.profile_match else []
            ),
            "profile_match_level": (
                self.profile_match.match_level if self.profile_match else None
            ),
            "pivot_why_it_matters": (
                list(self.pivot.why_it_matters) if self.pivot else []
            ),
            "pivot_potential_risk": (
                self.pivot.potential_risk if self.pivot else None
            ),
            "advantage_signals": (
                list(self.advantage_assessment_v3.advantage_signals) if self.advantage_assessment_v3 else []
            ),
            "objection_signals": (
                list(self.advantage_assessment_v3.objection_signals) if self.advantage_assessment_v3 else []
            ),
            "differentiation_signals": (
                list(self.advantage_assessment_v3.differentiation_signals) if self.advantage_assessment_v3 else []
            ),
            "neutralizing_evidence": (
                list(self.advantage_assessment_v3.neutralizing_evidence) if self.advantage_assessment_v3 else []
            ),
            "recruiter_hook": (
                self.advantage_assessment_v3.recruiter_hook if self.advantage_assessment_v3 else ""
            ),
            "applicant_pool_hypothesis": (
                self.advantage_assessment_v3.applicant_pool_hypothesis if self.advantage_assessment_v3 else ""
            ),
        }
