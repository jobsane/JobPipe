from __future__ import annotations

from pathlib import Path

from jobpipe.core.runner import PipelineRunner, Stage
from jobpipe.core.schema import JobContext, JobParse, ProfileMatchDimensions, ProfileMatchOut, RunMeta, TriageFeatures
from jobpipe.stages.triage_features import (
    build_triage_features,
    persist_triage_features,
    triage_features_artifact_path,
    triage_features_stage_factory,
)


def _ctx() -> JobContext:
    ctx = JobContext(
        meta=RunMeta(run_id="test", pipeline_name="test", created_at="2026-01-01T00:00:00Z"),
        job_id="job-1",
        job={
            "title": "Produkteier plattform",
            "description_html": "Greenfield plattformprodukt med hybrid arbeidsform og tydelig roadmap-ansvar.",
            "work_type": "Hybrid",
        },
        profile_pack="",
    )
    ctx.parsed = JobParse(
        role_summary="Produkteier for intern plattform",
        responsibilities=["roadmap", "stakeholder management", "prioritering"],
        requirements_must=["plattform", "produktledelse", "tverrfaglig samarbeid"],
        requirements_nice=["offentlig sektor"],
    )
    ctx.profile_match = ProfileMatchOut(
        fit_score=78,
        match_level="strong",
        overlaps=["plattformeierskap"],
        gaps=["offentlig sektor"],
        notes="test",
        dimensions=ProfileMatchDimensions(
            role_fit=82,
            domain_fit=64,
            seniority_fit=76,
            skills_fit=80,
        ),
    )
    return ctx


def test_build_triage_features_returns_expected_shape() -> None:
    features = build_triage_features(_ctx())
    assert features.core_tech_alignment.score == 80
    assert features.role_specificity.score == 82
    assert features.remote_veracity.score >= 60
    assert features.requirement_density.score > 35


def test_persist_triage_features_writes_suffix_artifact(tmp_path: Path) -> None:
    features = build_triage_features(_ctx())
    persist_triage_features(str(tmp_path), features)
    path = triage_features_artifact_path(str(tmp_path))
    assert path.exists()
    assert path.name.endswith("_triage_features.json")


def test_triage_features_stage_factory_sets_ctx(tmp_path: Path) -> None:
    should_run, run = triage_features_stage_factory()
    ctx = _ctx()
    assert should_run(ctx) is True
    result = run(ctx, str(tmp_path))
    assert result.triage_features is not None


def test_pipeline_runner_writes_numbered_triage_features_artifact(tmp_path: Path) -> None:
    should_run, run = triage_features_stage_factory()
    runner = PipelineRunner(
        [Stage(name="triage_features", run=run, should_run=should_run, ctx_model=TriageFeatures)]
    )
    runner.run_job(_ctx(), str(tmp_path))

    matches = sorted(tmp_path.glob("*_triage_features.json"))
    assert [path.name for path in matches] == ["01_triage_features.json"]
