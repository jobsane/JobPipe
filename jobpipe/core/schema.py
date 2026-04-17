from __future__ import annotations
from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field, field_validator

TriageDecision = Literal["SKIP", "REVIEW", "APPLY_CANDIDATE"]
ReverseDecision = Literal["SKIP_CONFIRMED", "REVIVE_REVIEW", "REVIVE_APPLY"]
FinalDecision = Literal["APPLY_STRONGLY", "APPLY", "REVIEW_HIGH", "REVIEW_LOW", "SKIP"]

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

class ApplicationPackOut(BaseModel):
    positioning_headline: str
    top_value_props: List[str]
    evidence_map: List[str]  # "Job need -> your proof"
    gap_mitigations: List[str]
    cover_letter_angle: str
    interview_prep: List[str]
    # --- Tailored CV highlights (additive) ---
    # AI-selected experience bullets from JSON Resume most relevant to this job.
    # Each entry is a standalone bullet ready to paste into a CV/cover letter.
    cv_highlights: List[str] = Field(default_factory=list)
    # Source references for traceability: e.g. "Brownells Europe (2015-2022)"
    cv_experience_refs: List[str] = Field(default_factory=list)

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
    reverse_triage: Optional[ReverseTriageOut] = None
    parsed: Optional[JobParse] = None
    profile_match: Optional[ProfileMatchOut] = None
    pivot: Optional[PivotOut] = None
    moderator: Optional[ModeratorOut] = None
    application_pack: Optional[ApplicationPackOut] = None

    # internal helpers
    notes: Dict[str, Any] = Field(default_factory=dict)

    def snapshot_summary(self) -> Dict[str, Any]:
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
        }
