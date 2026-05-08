from __future__ import annotations

import json
from pathlib import Path

from jobpipe.workspace import (
    ApplicationWorkspaceHub,
    ArtifactCasesCapability,
    DecisionSignalKey,
    Recommendation,
    build_artifact_workspace_hub,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_fixture_run(root: Path) -> Path:
    run_dir = root / "run-1"
    job_dir = run_dir / "job-1"
    job_dir.mkdir(parents=True)
    (run_dir / "index.jsonl").write_text(
        json.dumps(
            {
                "job_id": "job-1",
                "title": "Product Manager",
                "employer": "Example AS",
                "triage_v3_weighted_score": 82,
                "final_decision": "APPLY",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_json(
        job_dir / "00_input.json",
        {
            "job_id": "job-1",
            "uuid": "job-1",
            "title": "Product Manager",
            "normalized_title": "Product Manager",
            "employer_name": "Example AS",
            "description_html": "Hybrid role with APIs, discovery, and stakeholder work.",
            "applicationUrl": "https://example.test/apply",
            "sourceurl": "https://example.test/job",
            "applicationDue": "2026-06-01",
            "work_city": "Oslo",
            "work_county": "Oslo",
            "sector": "Technology",
            "occ_level1": "Product",
        },
    )
    _write_json(
        job_dir / "01_triage.json",
        {
            "triage_decision": "REVIEW_HIGH",
            "confidence": 0.84,
            "explanation": "Good fit for product ownership.",
            "signals": ["Clear product ownership", "Relevant stakeholder work"],
        },
    )
    _write_json(
        job_dir / "bridge_triage_features.json",
        {
            "core_tech_alignment": {
                "score": 88,
                "confidence": 80,
                "reason": "API and platform work match the profile.",
                "evidence_spans": ["API platform ownership"],
            },
            "role_specificity": {
                "score": 78,
                "confidence": 80,
                "reason": "The role is explicitly product-oriented.",
                "evidence_spans": ["Product Manager"],
            },
            "operating_fit": {
                "score": 74,
                "confidence": 70,
                "reason": "Cross-functional work fits the operating model.",
                "evidence_spans": ["stakeholder work"],
            },
            "requirement_density": {"score": 64, "reason": "Requirements are manageable."},
            "stakeholder_complexity": {"score": 69, "reason": "Stakeholder complexity is useful."},
            "autonomy_level": {"score": 72, "reason": "Autonomy is visible."},
            "geospatial_friction": {"score": 52, "reason": "Oslo/hybrid is workable."},
            "remote_veracity": {"score": 60, "reason": "Hybrid is stated."},
            "legacy_burden": {"score": 35, "reason": "Some legacy burden may exist."},
        },
    )
    _write_json(
        job_dir / "bridge_triage_decision_v3.json",
        {
            "label": "shortlist",
            "weighted_score": 82,
            "confidence": 78,
            "needs_ambiguity_pass": False,
            "blockers": ["Legacy burden needs framing"],
            "boosts": ["Strong platform/product overlap"],
            "summary": "Worth review effort.",
        },
    )
    _write_json(
        job_dir / "10_moderator.json",
        {
            "final_decision": "APPLY",
            "confidence": 0.8,
            "recommendation_reason": "Apply with tailored product framing.",
            "cv_focus": ["Platform ownership"],
            "feedback_flags": [],
        },
    )
    return run_dir


def test_artifact_cases_capability_lists_and_gets_cases(tmp_path: Path) -> None:
    run_dir = _write_fixture_run(tmp_path)
    cases = ArtifactCasesCapability(run_dir)

    listed = cases.list()
    case = cases.get("job-1")

    assert len(listed) == 1
    assert listed[0].id == "job-1"
    assert listed[0].company == "Example AS"
    assert listed[0].score == 82
    assert listed[0].recommendation == Recommendation.APPLY
    assert case is not None
    assert case.role == "Product Manager"
    assert case.work_mode == "hybrid"
    assert [signal.key for signal in case.decision_signals] == [
        DecisionSignalKey.CAN_DO,
        DecisionSignalKey.CAN_GET,
        DecisionSignalKey.SHOULD_WANT,
        DecisionSignalKey.CAN_EXPLAIN,
    ]
    assert case.artifacts
    assert case.evidence
    assert cases.get("missing") is None


def test_artifact_adapter_omits_error_jobs_and_handles_partials(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-1"
    good_dir = run_dir / "good-job"
    error_dir = run_dir / "bad-job"
    _write_json(good_dir / "00_input.json", {"job_id": "good-job", "title": "Analyst"})
    _write_json(error_dir / "00_input.json", {"job_id": "bad-job", "title": "Broken"})
    _write_json(error_dir / "pipeline_error.json", {"error": "failed"})

    cases = ArtifactCasesCapability(run_dir)
    listed = cases.list()
    case = cases.get("good-job")

    assert [item.id for item in listed] == ["good-job"]
    assert case is not None
    assert case.company == ""
    assert case.score == 0
    assert case.decision_signals


def test_artifact_adapter_does_not_emit_raw_paths(tmp_path: Path) -> None:
    run_dir = _write_fixture_run(tmp_path)
    payload = ArtifactCasesCapability(run_dir).get("job-1")

    assert payload is not None
    serialized = json.dumps(payload.to_dict(), ensure_ascii=False)
    assert str(run_dir) not in serialized
    assert "out_runs" not in serialized
    assert "storage_path" not in serialized
    assert "C:\\\\" not in serialized
    assert all("\\" not in artifact.id for artifact in payload.artifacts)


def test_artifact_workspace_hub_exposes_cases(tmp_path: Path) -> None:
    run_dir = _write_fixture_run(tmp_path)
    hub: ApplicationWorkspaceHub = build_artifact_workspace_hub(run_dir)

    assert hub.cases.list()[0].id == "job-1"
    assert hub.cases.get("job-1") is not None
