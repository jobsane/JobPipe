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
    DRAFTING = "drafting"
    READY_TO_APPLY = "ready_to_apply"
    APPLIED = "applied"
    WAITING = "waiting"
    FOLLOW_UP_NEEDED = "follow_up_needed"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    CLOSED = "closed"


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
    provenance: list[ProvenanceRef] = field(default_factory=list)

    def __post_init__(self) -> None:
        _validate_safe_identifier("id", self.id)
        if self.score < 0 or self.score > 100:
            raise WorkspaceContractError("case score must be between 0 and 100")

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
            provenance=self.provenance,
        )

    def to_dict(self) -> dict[str, Any]:
        return _asdict(self)


__all__ = [
    "ApplicationCaseReadModel",
    "ApplicationStatus",
    "ArtifactRef",
    "CaseListItem",
    "DecisionSignal",
    "DecisionSignalKey",
    "EvidenceRef",
    "ProvenanceRef",
    "Recommendation",
    "TailoringEffort",
    "WorkMode",
    "WorkspaceContractError",
]

