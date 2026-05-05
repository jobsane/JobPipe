from __future__ import annotations

import json
from pathlib import Path

from jobpipe.core.runner import PipelineRunner, Stage
from jobpipe.core.schema import (
    FeatureScore,
    HardGates,
    JobContext,
    JobParse,
    ProfileMatchDimensions,
    ProfileMatchOut,
    RunMeta,
    TriageFeatures,
    TriageOut,
)
from jobpipe.core.stage_cache import artifact_meta_path
from jobpipe.stages.triage_decision_v3 import triage_decision_v3_cache_key, triage_decision_v3_stage_factory
from jobpipe.stages.triage_features import triage_features_cache_key


def _feature(score: int, confidence: int = 80) -> FeatureScore:
    return FeatureScore(score=score, confidence=confidence, reason="test", evidence_spans=[])


def _ctx() -> JobContext:
    ctx = JobContext(
        meta=RunMeta(run_id="test", pipeline_name="test", created_at="2026-01-01T00:00:00Z"),
        job_id="job-1",
        job={
            "title": "Produkteier",
            "description_html": "Hybrid rolle med produktutvikling og stakeholder-ansvar.",
            "work_arrangement": "Hybrid",
        },
        profile_pack="",
    )
    ctx.triage = TriageOut(
        triage_decision="REVIEW",
        confidence=0.8,
        explanation="ok",
        signals=[],
        hard_gates=HardGates(),
    )
    ctx.parsed = JobParse(
        role_summary="Produkteier med leveranseansvar",
        responsibilities=["lede backlog", "samhandle med interessenter"],
        requirements_must=["produktledelse"],
        requirements_nice=["plattform"],
    )
    ctx.profile_match = ProfileMatchOut(
        dimensions=ProfileMatchDimensions(role_fit=62, domain_fit=58, seniority_fit=55, skills_fit=61),
        fit_score=61,
        match_level="medium",
        overlaps=["produktledelse"],
        gaps=["public sector"],
    )
    ctx.triage_features = TriageFeatures(
        core_tech_alignment=_feature(58),
        legacy_burden=_feature(56),
        role_specificity=_feature(54),
        requirement_density=_feature(50),
        geospatial_friction=_feature(24),
        remote_veracity=_feature(82),
        autonomy_level=_feature(48),
        stakeholder_complexity=_feature(46),
        operating_fit=_feature(50),
    )
    return ctx


def test_runner_reuses_cached_stage_when_cache_key_matches(tmp_path: Path) -> None:
    calls: list[str] = []

    def run(ctx: JobContext, job_dir: str) -> JobContext:  # noqa: ARG001
        calls.append("run")
        ctx.notes["counter"] = ctx.notes.get("counter", 0) + 1
        return ctx

    runner = PipelineRunner(
        [
            Stage(
                name="cache_probe",
                run=run,
                should_run=lambda ctx: True,
                cache_key_fn=lambda ctx: "same-key",
            )
        ]
    )
    ctx = _ctx()
    runner.run_job(ctx, str(tmp_path))
    runner.run_job(_ctx(), str(tmp_path))

    assert calls == ["run"]
    meta_path = Path(artifact_meta_path(str(tmp_path / "01_cache_probe.json")))
    assert meta_path.exists() is True
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["cache_key"] == "same-key"


def test_runner_invalidates_cached_stage_when_cache_key_changes(tmp_path: Path) -> None:
    decision_should, decision_run = triage_decision_v3_stage_factory()
    runner = PipelineRunner(
        [
            Stage(
                name="triage_decision_v3",
                run=decision_run,
                should_run=decision_should,
                ctx_model=None,
                cache_key_fn=triage_decision_v3_cache_key,
            )
        ]
    )

    ctx = _ctx()
    runner.run_job(ctx, str(tmp_path))
    first = json.loads((tmp_path / "01_triage_decision_v3.json").read_text(encoding="utf-8"))

    mutated = _ctx()
    mutated.triage_features.core_tech_alignment.score = 92
    runner.run_job(mutated, str(tmp_path))
    second = json.loads((tmp_path / "01_triage_decision_v3.json").read_text(encoding="utf-8"))

    assert first["weighted_score"] != second["weighted_score"]
    assert second["weighted_score"] > first["weighted_score"]


def test_triage_features_cache_key_changes_when_inputs_change() -> None:
    base = _ctx()
    changed = _ctx()
    changed.profile_match.dimensions.skills_fit = 88
    changed.profile_match.fit_score = 88

    assert triage_features_cache_key(base) != triage_features_cache_key(changed)
