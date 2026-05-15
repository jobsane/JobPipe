"""Typed ApplicationWorkspaceHub read contracts.

These models are storage-agnostic. They define the safe payload surface that a
future API/MCP wrapper can expose to JobDesk.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


_PATH_MARKERS = (
    "storage_path",
    "out_runs",
    ".jobpipe_tmp",
    ".env",
    "secrets",
    "profile_pack",
)
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")


class WorkspaceContractError(ValueError):
    """Raised when a hub contract value violates the safe payload boundary."""


class WorkMode(StrEnum):
    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"
    FLEXIBLE = "flexible"
    UNKNOWN = "unknown"


class TailoringEffort(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Recommendation(StrEnum):
    STRONG_APPLY = "strong_apply"
    APPLY = "apply"
    MAYBE = "maybe"
    SKIP = "skip"


class ApplicationStatus(StrEnum):
    """Narrowed to match JobDesk's canonical 9-value set (audit D-C, 2026-05-13).

    The hub used to expose a 10-value set including ``ready_to_apply``,
    ``waiting``, ``follow_up_needed``, ``interview``, ``offer``, ``closed``.
    Those values were lossy-translated by ``http-jobdesk-api.ts`` and the
    extras were unused. ``case_state.json`` (Slice C) already validates
    against this narrower set, so the hub is the only consumer that needed
    catching up.
    """

    DRAFTING = "drafting"
    READY = "ready"
    APPLIED = "applied"
    INTERVIEWING = "interviewing"
    OFFERED = "offered"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    GHOSTED = "ghosted"


class DecisionSignalKey(StrEnum):
    CAN_DO = "can_do"
    CAN_GET = "can_get"
    SHOULD_WANT = "should_want"
    CAN_EXPLAIN = "can_explain"


def _asdict(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, list):
        return [_asdict(item) for item in value]
    if isinstance(value, dict):
        return {key: _asdict(item) for key, item in value.items()}
    if hasattr(value, "__dataclass_fields__"):
        return {key: _asdict(item) for key, item in asdict(value).items()}
    return value


def _validate_safe_identifier(field_name: str, value: str) -> None:
    text = str(value or "").strip()
    if not text:
        raise WorkspaceContractError(f"{field_name} is required")
    lowered = text.lower().replace("\\", "/")
    if _WINDOWS_DRIVE_RE.search(text) or "\\" in text:
        raise WorkspaceContractError(f"{field_name} must not be a raw filesystem path")
    if any(marker in lowered for marker in _PATH_MARKERS):
        raise WorkspaceContractError(f"{field_name} must not expose private path markers")


@dataclass(frozen=True)
class ProvenanceRef:
    """Safe source reference for a projected workspace value."""

    source_system: str
    source_id: str
    source_label: str = ""
    observed_at: str = ""
    confidence: str = "unknown"

    def __post_init__(self) -> None:
        _validate_safe_identifier("source_system", self.source_system)
        _validate_safe_identifier("source_id", self.source_id)

    def to_dict(self) -> dict[str, Any]:
        return _asdict(self)


@dataclass(frozen=True)
class EvidenceRef:
    """Workspace-safe evidence excerpt or reference."""

    id: str
    label: str
    source: str
    quote: str = ""
    confidence: str = "unknown"
    provenance: list[ProvenanceRef] = field(default_factory=list)

    def __post_init__(self) -> None:
        _validate_safe_identifier("id", self.id)
        _validate_safe_identifier("source", self.source)

    def to_dict(self) -> dict[str, Any]:
        return _asdict(self)


@dataclass(frozen=True)
class ArtifactRef:
    """Safe generated artifact reference without raw storage paths."""

    id: str
    kind: str
    status: str
    label: str = ""
    preview: str = ""
    updated_at: str = ""
    provenance: list[ProvenanceRef] = field(default_factory=list)

    def __post_init__(self) -> None:
        _validate_safe_identifier("id", self.id)
        _validate_safe_identifier("kind", self.kind)

    def to_dict(self) -> dict[str, Any]:
        return _asdict(self)


@dataclass(frozen=True)
class DecisionSignal:
    """Projected JobPipe decision signal for JobDesk review."""

    key: DecisionSignalKey
    label: str
    score: int
    band: str
    rationale: str = ""
    confidence: str = "unknown"
    evidence_ids: list[str] = field(default_factory=list)
    supporting_points: list[str] = field(default_factory=list)
    risk_points: list[str] = field(default_factory=list)
    provenance: list[ProvenanceRef] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.score < 0 or self.score > 100:
            raise WorkspaceContractError("decision signal score must be between 0 and 100")
        for evidence_id in self.evidence_ids:
            _validate_safe_identifier("evidence_id", evidence_id)

    def to_dict(self) -> dict[str, Any]:
        return _asdict(self)


@dataclass(frozen=True)
class CaseListItem:
    """Compact case queue item for cases.list()."""

    id: str
    company: str
    role: str
    location: str
    work_mode: WorkMode
    deadline: str = ""
    score: int = 0
    recommendation: Recommendation = Recommendation.MAYBE
    application_status: ApplicationStatus = ApplicationStatus.DRAFTING
    main_strength: str = ""
    main_gap: str = ""
    tailoring_effort: TailoringEffort = TailoringEffort.MEDIUM
    next_action: str = "Open review"
    # ISO 8601 timestamp from triage_decisions.decided_at — when this case
    # entered the user's actionable shortlist. Used as the "freshness" signal
    # in the UI ("Today", "2d ago", etc.).
    decided_at: str = ""
    # ISO 8601 timestamp from jobs.updated_at — when the employer-side ad
    # was last touched on NAV (post / edit / status change). Distinct from
    # decided_at (= when JobPipe surfaced this case to the user).
    job_updated_at: str = ""
    # ISO 8601 timestamp from jobs.published_at — when the employer first
    # posted the ad on NAV. Used as the "posted" date in the UI.
    job_posted_at: str = ""
    provenance: list[ProvenanceRef] = field(default_factory=list)

    def __post_init__(self) -> None:
        _validate_safe_identifier("id", self.id)
        if self.score < 0 or self.score > 100:
            raise WorkspaceContractError("case score must be between 0 and 100")

    def to_dict(self) -> dict[str, Any]:
        return _asdict(self)


class ClaimStatus(StrEnum):
    """Validation status of a claim made in the tailored materials."""

    VERIFIED = "verified"
    WEAK = "weak"
    UNSUPPORTED = "unsupported"


class TailoringPlanSource(StrEnum):
    """Where a TailoringPlanReadModel originated.

    ``pipeline`` — projected from JobPipe's ``ApplicationPackOut`` on disk.
    ``jobsane``  — written back by a JobSane ``/tailor`` run.
    ``merged``   — pipeline-seeded then refined by JobSane (write-back path).
    """

    PIPELINE = "pipeline"
    JOBSANE = "jobsane"
    MERGED = "merged"


@dataclass(frozen=True)
class BulletChange:
    """Single CV bullet swap: which section, what was there, what JobSane proposes."""

    id: str
    section: str  # e.g. "summary", "headline", "work:Acme:Engineer", "skills"
    original: str
    proposed: str
    rationale: str
    confidence: str = "unknown"
    provenance: list[ProvenanceRef] = field(default_factory=list)

    def __post_init__(self) -> None:
        _validate_safe_identifier("id", self.id)
        _validate_safe_identifier("section", self.section)

    def to_dict(self) -> dict[str, Any]:
        return _asdict(self)


@dataclass(frozen=True)
class KeywordCoverage:
    """Whether a job-posting keyword is present in the candidate's materials."""

    keyword: str
    present: bool
    suggested_placement: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _asdict(self)


@dataclass(frozen=True)
class ClaimValidation:
    """A claim from the cover letter / value prop, validated against evidence."""

    id: str
    claim: str
    status: ClaimStatus
    evidence_ids: list[str] = field(default_factory=list)
    note: str = ""

    def __post_init__(self) -> None:
        _validate_safe_identifier("id", self.id)
        for evidence_id in self.evidence_ids:
            _validate_safe_identifier("evidence_id", evidence_id)

    def to_dict(self) -> dict[str, Any]:
        return _asdict(self)


@dataclass(frozen=True)
class ValuePropositionReadModel:
    """Projected value proposition — message pillars, proof, gaps.

    Fed by JobPipe's ``ApplicationPackOut`` (positioning_headline,
    top_value_props, evidence_map, gap_mitigations, cover_letter_angle) and
    optionally refined by JobSane on write-back.
    """

    positioning_angle: str
    employer_problem: str = ""
    applicant_advantage: str = ""
    message_pillars: list[str] = field(default_factory=list)
    proof_points: list[str] = field(default_factory=list)
    gap_mitigations: list[str] = field(default_factory=list)
    provenance: list[ProvenanceRef] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _asdict(self)


@dataclass(frozen=True)
class CoverLetterDraftReadModel:
    """Editable cover letter draft + the language the pipeline produced it in.

    Tiptap in JobDesk seeds from this. ``text`` carries the actual prose;
    JobDesk renders it as a paragraph-structured rich-text doc.
    """

    text: str
    language: str = ""  # e.g. "nb" (Norwegian bokmål), "en" — pipeline-authoritative
    angle: str = ""  # the strategic angle / recruiter hook
    word_count: int = 0
    provenance: list[ProvenanceRef] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.word_count < 0:
            raise WorkspaceContractError("word_count must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return _asdict(self)


@dataclass(frozen=True)
class TailoringPlanReadModel:
    """Full tailoring plan for one case — resume + value prop + cover letter.

    This is the single payload returned by ``GET /cases/:id/tailoring_plan``
    and accepted by ``POST /cases/:id/tailoring_plan``. It deliberately
    aggregates three concerns (resume bullets, value pillars, cover letter
    draft) because JobDesk's review screens treat them as one tailoring unit
    and JobSane writes them back as one atomic record.
    """

    case_id: str
    source: TailoringPlanSource
    positioning_angle: str
    section_strategy: list[str] = field(default_factory=list)
    bullet_changes: list[BulletChange] = field(default_factory=list)
    keyword_coverage: list[KeywordCoverage] = field(default_factory=list)
    claim_warnings: list[ClaimValidation] = field(default_factory=list)
    value_proposition: ValuePropositionReadModel | None = None
    cover_letter: CoverLetterDraftReadModel | None = None
    reactive_resume_url: str = ""
    updated_at: str = ""
    provenance: list[ProvenanceRef] = field(default_factory=list)

    def __post_init__(self) -> None:
        _validate_safe_identifier("case_id", self.case_id)

    def to_dict(self) -> dict[str, Any]:
        return _asdict(self)


@dataclass(frozen=True)
class ApplicationCaseReadModel:
    """Full read-only case model for cases.get(case_id)."""

    id: str
    company: str
    role: str
    location: str
    work_mode: WorkMode
    deadline: str = ""
    # Canonical URL where a human reads the ad in its original location.
    # For NAV-sourced jobs that's the arbeidsplassen.nav.no listing; for
    # finn.no / LinkedIn / employer-page sources it's the original posting.
    # Distinct from `application_url` (where the user submits).
    source_url: str = ""
    application_url: str = ""
    summary: str = ""
    ats_keywords: list[str] = field(default_factory=list)
    score: int = 0
    recommendation: Recommendation = Recommendation.MAYBE
    application_status: ApplicationStatus = ApplicationStatus.DRAFTING
    tailoring_effort: TailoringEffort = TailoringEffort.MEDIUM
    decision_signals: list[DecisionSignal] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    evidence: list[EvidenceRef] = field(default_factory=list)
    artifacts: list[ArtifactRef] = field(default_factory=list)
    next_action: str = "Open review"
    # ISO 8601 timestamp — when JobPipe wrote this decision (= when the case
    # became visible in the user's shortlist). Used as the freshness signal.
    decided_at: str = ""
    # ISO 8601 timestamp from jobs.updated_at — when the employer-side ad
    # was last touched on NAV. Distinct from `decided_at`.
    job_updated_at: str = ""
    # ISO 8601 timestamp from jobs.published_at — when the employer first
    # posted the ad on NAV.
    job_posted_at: str = ""
    provenance: list[ProvenanceRef] = field(default_factory=list)

    def __post_init__(self) -> None:
        _validate_safe_identifier("id", self.id)
        if self.score < 0 or self.score > 100:
            raise WorkspaceContractError("case score must be between 0 and 100")

    def to_list_item(self) -> CaseListItem:
        return CaseListItem(
            id=self.id,
            company=self.company,
            role=self.role,
            location=self.location,
            work_mode=self.work_mode,
            deadline=self.deadline,
            score=self.score,
            recommendation=self.recommendation,
            application_status=self.application_status,
            main_strength=self.strengths[0] if self.strengths else "",
            main_gap=self.gaps[0] if self.gaps else "",
            tailoring_effort=self.tailoring_effort,
            next_action=self.next_action,
            decided_at=self.decided_at,
            job_updated_at=self.job_updated_at,
            job_posted_at=self.job_posted_at,
            provenance=self.provenance,
        )

    def to_dict(self) -> dict[str, Any]:
        return _asdict(self)


__all__ = [
    "ApplicationCaseReadModel",
    "ApplicationStatus",
    "ArtifactRef",
    "BulletChange",
    "CaseListItem",
    "ClaimStatus",
    "ClaimValidation",
    "CoverLetterDraftReadModel",
    "DecisionSignal",
    "DecisionSignalKey",
    "EvidenceRef",
    "KeywordCoverage",
    "ProvenanceRef",
    "Recommendation",
    "TailoringEffort",
    "TailoringPlanReadModel",
    "TailoringPlanSource",
    "ValuePropositionReadModel",
    "WorkMode",
    "WorkspaceContractError",
]

