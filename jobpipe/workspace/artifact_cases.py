"""Artifact-backed ApplicationWorkspaceHub cases adapter.

This adapter reads existing JobPipe run artifacts and projects them into the
workspace contracts. It does not depend on dashboard payloads, SQLite, Supabase,
or any transport wrapper.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .contracts import (
    ApplicationCaseReadModel,
    ApplicationStatus,
    ArtifactRef,
    CaseListItem,
    DecisionSignal,
    DecisionSignalKey,
    EvidenceRef,
    ProvenanceRef,
    Recommendation,
    TailoringEffort,
    WorkMode,
)

_ARTIFACT_LABELS = {
    "00_input.json": "Input job record",
    "01_triage.json": "Initial triage",
    "bridge_triage_features.json": "Decision features",
    "bridge_triage_decision_v3.json": "Decision table",
    "10_moderator.json": "Moderated recommendation",
}

_FEATURE_GROUPS: dict[DecisionSignalKey, tuple[str, ...]] = {
    DecisionSignalKey.CAN_DO: (
        "core_tech_alignment",
        "role_specificity",
        "operating_fit",
    ),
    DecisionSignalKey.CAN_GET: (
        "requirement_density",
        "stakeholder_complexity",
        "autonomy_level",
    ),
    DecisionSignalKey.SHOULD_WANT: (
        "operating_fit",
        "geospatial_friction",
        "remote_veracity",
    ),
    DecisionSignalKey.CAN_EXPLAIN: (
        "role_specificity",
        "legacy_burden",
        "requirement_density",
    ),
}

_SIGNAL_LABELS = {
    DecisionSignalKey.CAN_DO: "Can do",
    DecisionSignalKey.CAN_GET: "Can get",
    DecisionSignalKey.SHOULD_WANT: "Should want",
    DecisionSignalKey.CAN_EXPLAIN: "Can explain",
}


@dataclass(frozen=True)
class ArtifactCasesCapability:
    """Read-only cases capability backed by one JobPipe run directory."""

    run_dir: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_dir", Path(self.run_dir))

    def list(self, candidate_id: str = "default") -> list[CaseListItem]:  # noqa: ARG002
        return [case.to_list_item() for case in self._read_cases()]

    def get(
        self,
        case_id: str,
        candidate_id: str = "default",  # noqa: ARG002
    ) -> ApplicationCaseReadModel | None:
        for case in self._read_cases():
            if case.id == case_id:
                return case
        return None

    def _read_cases(self) -> list[ApplicationCaseReadModel]:
        index_rows = _read_index(self.run_dir / "index.jsonl")
        index_by_id = {
            str(row.get("job_id") or "").strip(): row
            for row in index_rows
            if str(row.get("job_id") or "").strip()
        }

        cases: list[ApplicationCaseReadModel] = []
        if not self.run_dir.exists():
            return cases

        for job_dir in sorted(path for path in self.run_dir.iterdir() if path.is_dir()):
            if (job_dir / "pipeline_error.json").exists():
                continue
            input_artifact = _read_json(job_dir / "00_input.json")
            case_id = _case_id(job_dir.name, input_artifact, index_by_id)
            if not case_id:
                continue
            case = _map_job_artifacts(
                case_id=case_id,
                job_dir=job_dir,
                input_artifact=input_artifact,
                triage=_read_json(job_dir / "01_triage.json"),
                features=_read_json(job_dir / "bridge_triage_features.json"),
                decision=_read_json(job_dir / "bridge_triage_decision_v3.json"),
                moderator=_read_json(job_dir / "10_moderator.json"),
                index_row=index_by_id.get(case_id, {}),
            )
            cases.append(case)

        cases.sort(key=lambda item: (-item.score, item.company.lower(), item.role.lower()))
        return cases


@dataclass(frozen=True)
class ArtifactWorkspaceHub:
    """Minimal ApplicationWorkspaceHub implementation for artifact-backed cases."""

    run_dir: Path

    @property
    def cases(self) -> ArtifactCasesCapability:
        return ArtifactCasesCapability(self.run_dir)


def build_artifact_workspace_hub(run_dir: str | Path) -> ArtifactWorkspaceHub:
    """Create a read-only workspace hub over one JobPipe artifact run."""

    return ArtifactWorkspaceHub(Path(run_dir))


def _read_index(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return value if isinstance(value, dict) else {}


def _case_id(job_dir_name: str, input_artifact: dict[str, Any], index_by_id: dict[str, Any]) -> str:
    for key in ("job_id", "uuid"):
        value = str(input_artifact.get(key) or "").strip()
        if value:
            return value
    if job_dir_name in index_by_id:
        return job_dir_name
    return str(job_dir_name or "").strip()


def _map_job_artifacts(
    *,
    case_id: str,
    job_dir: Path,
    input_artifact: dict[str, Any],
    triage: dict[str, Any],
    features: dict[str, Any],
    decision: dict[str, Any],
    moderator: dict[str, Any],
    index_row: dict[str, Any],
) -> ApplicationCaseReadModel:
    provenance = [
        ProvenanceRef(
            source_system="jobpipe",
            source_id=f"run-artifact:{case_id}",
            source_label="JobPipe run artifacts",
            observed_at=_text(input_artifact.get("updated_at") or input_artifact.get("ad_updated")),
            confidence="medium",
        )
    ]
    evidence = _build_evidence(case_id, features, provenance)
    evidence_by_signal = _evidence_ids_by_signal(evidence)
    signals = _build_decision_signals(case_id, features, decision, moderator, evidence_by_signal, provenance)
    score = _score(decision.get("weighted_score"), index_row.get("triage_v3_weighted_score"))
    recommendation = _recommendation(moderator, decision, triage, index_row)
    strengths = _strengths(decision, moderator, triage)
    gaps = _gaps(decision, moderator)

    return ApplicationCaseReadModel(
        id=case_id,
        company=_text(input_artifact.get("employer_name") or index_row.get("employer")),
        role=_text(input_artifact.get("normalized_title") or input_artifact.get("title") or index_row.get("title")),
        location=_location(input_artifact),
        work_mode=_work_mode(input_artifact),
        deadline=_text(input_artifact.get("applicationDue") or input_artifact.get("expires_at")),
        source_url=_text(input_artifact.get("sourceurl")),
        application_url=_text(input_artifact.get("applicationUrl")),
        summary=_text(decision.get("summary") or moderator.get("recommendation_reason") or triage.get("explanation")),
        ats_keywords=_keywords(input_artifact, features),
        score=score,
        recommendation=recommendation,
        application_status=ApplicationStatus.DRAFTING,
        tailoring_effort=_tailoring_effort(score, gaps),
        decision_signals=signals,
        strengths=strengths,
        gaps=gaps,
        evidence=evidence,
        artifacts=_artifact_refs(case_id, job_dir, provenance),
        next_action="Open review",
        provenance=provenance,
    )


def _build_evidence(
    case_id: str,
    features: dict[str, Any],
    provenance: list[ProvenanceRef],
) -> list[EvidenceRef]:
    refs: list[EvidenceRef] = []
    for feature_key, payload in features.items():
        if not isinstance(payload, dict):
            continue
        spans = payload.get("evidence_spans")
        if not isinstance(spans, list):
            continue
        for index, span in enumerate(spans):
            quote = _text(span)
            if not quote:
                continue
            refs.append(
                EvidenceRef(
                    id=f"evidence:{case_id}:{feature_key}:{index}",
                    label=_humanize(feature_key),
                    source=f"triage-feature:{feature_key}",
                    quote=quote,
                    confidence=_confidence(payload.get("confidence")),
                    provenance=provenance,
                )
            )
    return refs


def _evidence_ids_by_signal(evidence: Iterable[EvidenceRef]) -> dict[DecisionSignalKey, list[str]]:
    grouped: dict[DecisionSignalKey, list[str]] = {key: [] for key in DecisionSignalKey}
    for ref in evidence:
        feature_key = ref.source.removeprefix("triage-feature:")
        for signal_key, features in _FEATURE_GROUPS.items():
            if feature_key in features:
                grouped[signal_key].append(ref.id)
    return grouped


def _build_decision_signals(
    case_id: str,
    features: dict[str, Any],
    decision: dict[str, Any],
    moderator: dict[str, Any],
    evidence_by_signal: dict[DecisionSignalKey, list[str]],
    provenance: list[ProvenanceRef],
) -> list[DecisionSignal]:
    signals: list[DecisionSignal] = []
    for key in DecisionSignalKey:
        feature_payloads = [
            features.get(feature_name)
            for feature_name in _FEATURE_GROUPS[key]
            if isinstance(features.get(feature_name), dict)
        ]
        score = _average_scores(feature_payloads)
        rationale_parts = [_text(item.get("reason")) for item in feature_payloads if isinstance(item, dict)]
        supporting_points = _points_from_features(feature_payloads, threshold=65)
        risk_points = _points_from_features(feature_payloads, threshold=35, below=True)
        if key == DecisionSignalKey.SHOULD_WANT:
            score = _score(decision.get("weighted_score"), score)
            supporting_points.extend(_string_list(decision.get("boosts")))
            risk_points.extend(_string_list(decision.get("blockers")))
            rationale_parts.insert(0, _text(decision.get("summary") or moderator.get("recommendation_reason")))

        signals.append(
            DecisionSignal(
                key=key,
                label=_SIGNAL_LABELS[key],
                score=score,
                band=_band(score),
                rationale=" ".join(part for part in rationale_parts if part).strip(),
                confidence=_confidence(decision.get("confidence") if key == DecisionSignalKey.SHOULD_WANT else None),
                evidence_ids=evidence_by_signal.get(key, []),
                supporting_points=_dedupe(supporting_points),
                risk_points=_dedupe(risk_points),
                provenance=provenance,
            )
        )
    return signals


def _artifact_refs(case_id: str, job_dir: Path, provenance: list[ProvenanceRef]) -> list[ArtifactRef]:
    refs: list[ArtifactRef] = []
    for path in sorted(job_dir.glob("*.json")):
        if path.name == "pipeline_error.json":
            continue
        refs.append(
            ArtifactRef(
                id=f"artifact:{case_id}:{path.stem}",
                kind=path.stem,
                status="available",
                label=_ARTIFACT_LABELS.get(path.name, _humanize(path.stem)),
                provenance=provenance,
            )
        )
    return refs


def _score(*values: Any) -> int:
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number <= 1:
            number *= 100
        return max(0, min(100, round(number)))
    return 0


def _average_scores(feature_payloads: list[Any]) -> int:
    scores = [_score(item.get("score")) for item in feature_payloads if isinstance(item, dict) and item.get("score") is not None]
    if not scores:
        return 0
    return round(sum(scores) / len(scores))


def _recommendation(
    moderator: dict[str, Any],
    decision: dict[str, Any],
    triage: dict[str, Any],
    index_row: dict[str, Any],
) -> Recommendation:
    raw = _text(
        moderator.get("final_decision")
        or index_row.get("final_decision")
        or decision.get("label")
        or triage.get("triage_decision")
    ).lower()
    if "skip" in raw or "discard" in raw or "reject" in raw:
        return Recommendation.SKIP
    if "strong" in raw and "apply" in raw:
        return Recommendation.STRONG_APPLY
    if "apply" in raw or "shortlist" in raw:
        return Recommendation.APPLY
    return Recommendation.MAYBE


def _tailoring_effort(score: int, gaps: list[str]) -> TailoringEffort:
    if gaps or score < 45:
        return TailoringEffort.HIGH
    if score < 70:
        return TailoringEffort.MEDIUM
    return TailoringEffort.LOW


def _location(input_artifact: dict[str, Any]) -> str:
    parts = [
        _text(input_artifact.get("work_city")),
        _text(input_artifact.get("work_county")),
        _text(input_artifact.get("work_postalCode")),
    ]
    return ", ".join(part for part in parts if part)


def _work_mode(input_artifact: dict[str, Any]) -> WorkMode:
    text = " ".join(
        _text(input_artifact.get(key))
        for key in ("title", "description_html", "work_city", "work_county")
    ).lower()
    if any(term in text for term in ("hybrid", "hybridarbeid", "hjemmekontor")):
        return WorkMode.HYBRID
    if any(term in text for term in ("remote", "fjernarbeid", "remote-first")):
        return WorkMode.REMOTE
    return WorkMode.UNKNOWN


def _keywords(input_artifact: dict[str, Any], features: dict[str, Any]) -> list[str]:
    values = [
        _text(input_artifact.get("sector")),
        _text(input_artifact.get("occ_level1")),
        _text(input_artifact.get("occ_level2")),
    ]
    values.extend(_humanize(key) for key, value in features.items() if isinstance(value, dict) and _score(value.get("score")) >= 65)
    return _dedupe([value for value in values if value])[:12]


def _strengths(decision: dict[str, Any], moderator: dict[str, Any], triage: dict[str, Any]) -> list[str]:
    points = [
        *_string_list(decision.get("boosts")),
        *_string_list(moderator.get("cv_focus")),
        *_string_list(triage.get("signals")),
    ]
    return _dedupe(points)[:6]


def _gaps(decision: dict[str, Any], moderator: dict[str, Any]) -> list[str]:
    points = [
        *_string_list(decision.get("blockers")),
        *_string_list(moderator.get("feedback_flags")),
    ]
    return _dedupe(points)[:6]


def _points_from_features(feature_payloads: list[Any], *, threshold: int, below: bool = False) -> list[str]:
    points: list[str] = []
    for item in feature_payloads:
        if not isinstance(item, dict):
            continue
        score = _score(item.get("score"))
        if (below and score <= threshold) or (not below and score >= threshold):
            reason = _text(item.get("reason"))
            if reason:
                points.append(reason)
    return points


def _confidence(value: Any) -> str:
    score = _score(value)
    if score >= 75:
        return "high"
    if score >= 40:
        return "medium"
    if score > 0:
        return "low"
    return "unknown"


def _band(score: int) -> str:
    if score >= 75:
        return "strong"
    if score >= 55:
        return "mixed"
    return "weak"


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _text(value)
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _humanize(value: str) -> str:
    return _text(value).replace("_", " ").replace("-", " ").strip().title()


def _text(value: Any) -> str:
    return str(value or "").strip()


__all__ = [
    "ArtifactCasesCapability",
    "ArtifactWorkspaceHub",
    "build_artifact_workspace_hub",
]
