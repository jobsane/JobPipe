from __future__ import annotations

import json

import pytest

from jobpipe.workspace import (
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
from jobpipe.workspace.contracts import WorkspaceContractError
from jobpipe.workspace.hub import ApplicationWorkspaceHub


def _case_model() -> ApplicationCaseReadModel:
    provenance = [
        ProvenanceRef(
            source_system="jobpipe",
            source_id="job-decision-table:job-1",
            source_label="JobPipe decision table",
            observed_at="2026-05-08T10:00:00Z",
            confidence="high",
        )
    ]
    evidence = [
        EvidenceRef(
            id="job-claim:claim-1",
            label="Service design",
            source="job_ad",
            quote="service design role requiring stakeholder facilitation",
            confidence="high",
            provenance=provenance,
        )
    ]
    return ApplicationCaseReadModel(
        id="job-1",
        company="Example Kommune",
        role="Service Designer",
        location="Oslo / hybrid",
        work_mode=WorkMode.HYBRID,
        deadline="2026-06-01",
        source_url="https://example.test/job/1",
        application_url="https://example.test/apply/1",
        summary="Public-sector service improvement role.",
        ats_keywords=["Service design", "Stakeholder facilitation"],
        score=83,
        recommendation=Recommendation.APPLY,
        application_status=ApplicationStatus.APPLIED,
        tailoring_effort=TailoringEffort.HIGH,
        decision_signals=[
            DecisionSignal(
                key=DecisionSignalKey.CAN_DO,
                label="Can do",
                score=80,
                band="good",
                rationale="Relevant delivery evidence.",
                confidence="high",
                evidence_ids=["job-claim:claim-1"],
                supporting_points=["Led cross-functional service improvement."],
                risk_points=[],
                provenance=provenance,
            ),
            DecisionSignal(
                key=DecisionSignalKey.CAN_GET,
                label="Can get",
                score=66,
                band="mixed",
                rationale="Credible but competitive.",
                confidence="medium",
                evidence_ids=["job-claim:claim-1"],
                supporting_points=["Public-sector adjacency helps."],
                risk_points=["Title continuity may be questioned."],
                provenance=provenance,
            ),
            DecisionSignal(
                key=DecisionSignalKey.SHOULD_WANT,
                label="Should want",
                score=83,
                band="good",
                rationale="Worth prioritising.",
                confidence="high",
                evidence_ids=["job-claim:claim-1"],
                supporting_points=["Strong strategic fit."],
                risk_points=[],
                provenance=provenance,
            ),
            DecisionSignal(
                key=DecisionSignalKey.CAN_EXPLAIN,
                label="Can explain",
                score=45,
                band="weak",
                rationale="Needs concise transition framing.",
                confidence="medium",
                evidence_ids=["job-claim:claim-1"],
                supporting_points=["Change-management narrative can bridge the move."],
                risk_points=["Story may read indirect without tailoring."],
                provenance=provenance,
            ),
        ],
        strengths=["Strong strategic fit."],
        gaps=["Story may read indirect without tailoring."],
        evidence=evidence,
        artifacts=[
            ArtifactRef(
                id="generated-document:doc-1",
                kind="value_proposition",
                status="draft",
                label="Value proposition draft",
                preview="I can help Example Kommune improve public services.",
                updated_at="2026-05-08T10:30:00Z",
                provenance=provenance,
            )
        ],
        next_action="Open review",
        provenance=provenance,
    )


def test_application_case_contract_serializes_safe_jobdesk_shape() -> None:
    case = _case_model()

    payload = case.to_dict()

    assert payload["id"] == "job-1"
    assert payload["work_mode"] == "hybrid"
    assert payload["recommendation"] == "apply"
    assert payload["application_status"] == "applied"
    assert payload["tailoring_effort"] == "high"
    assert [signal["key"] for signal in payload["decision_signals"]] == [
        "can_do",
        "can_get",
        "should_want",
        "can_explain",
    ]
    assert payload["artifacts"][0]["id"] == "generated-document:doc-1"

    serialized = json.dumps(payload)
    assert "storage_path" not in serialized
    assert "out_runs" not in serialized
    assert "C:\\\\" not in serialized
    assert ".env" not in serialized


def test_application_case_can_project_to_list_item() -> None:
    item = _case_model().to_list_item()

    assert isinstance(item, CaseListItem)
    assert item.id == "job-1"
    assert item.main_strength == "Strong strategic fit."
    assert item.main_gap == "Story may read indirect without tailoring."
    assert item.to_dict()["tailoring_effort"] == "high"


def test_artifact_and_provenance_refs_reject_raw_paths() -> None:
    with pytest.raises(WorkspaceContractError):
        ArtifactRef(
            id="C:\\Users\\larsv\\private\\artifact.pdf",
            kind="value_proposition",
            status="draft",
        )

    with pytest.raises(WorkspaceContractError):
        ProvenanceRef(
            source_system="jobpipe",
            source_id="out_runs/run-1/job-1/08_application_pack.json",
        )


def test_hub_protocol_shape_accepts_cases_capability() -> None:
    class InMemoryCases:
        def __init__(self, case: ApplicationCaseReadModel) -> None:
            self._case = case

        def list(self, candidate_id: str = "default") -> list[CaseListItem]:
            return [self._case.to_list_item()]

        def get(self, case_id: str, candidate_id: str = "default") -> ApplicationCaseReadModel | None:
            return self._case if case_id == self._case.id else None

    class InMemoryHub:
        def __init__(self, case: ApplicationCaseReadModel) -> None:
            self._cases = InMemoryCases(case)

        @property
        def cases(self) -> InMemoryCases:
            return self._cases

    hub: ApplicationWorkspaceHub = InMemoryHub(_case_model())

    assert hub.cases.list()[0].id == "job-1"
    assert hub.cases.get("job-1").score == 83
    assert hub.cases.get("missing") is None

