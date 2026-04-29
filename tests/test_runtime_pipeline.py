from __future__ import annotations

import pytest

from jobpipe.core.config import PipelineConfig
from jobpipe.core.runner import Stage
from jobpipe.runtime.pipeline import build_stages


def _stub_stage_factory(*args, **kwargs):
    def _should_run(ctx):
        return True

    def _run(ctx, job_dir):
        return ctx

    return _should_run, _run


def _cfg(stages: list[str]) -> PipelineConfig:
    return PipelineConfig(
        pipeline_name="test",
        models={},
        stages=stages,
        thresholds={
            "max_ad_text_chars": 3200,
            "triage_max_ad_text_chars": 1500,
            "reverse_triage_max_ad_text_chars": 1800,
            "reverse_triage_min_conf": 0.60,
            "reverse_triage_skip_above": 0.82,
            "semantic_filter_threshold": 0.27,
            "semantic_filter_model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        },
        safety_rules={},
    )


def _patch_stage_factories(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("jobpipe.runtime.pipeline.triage_stage_factory", _stub_stage_factory)
    monkeypatch.setattr("jobpipe.runtime.pipeline.reverse_triage_stage_factory", _stub_stage_factory)
    monkeypatch.setattr("jobpipe.runtime.pipeline.parse_stage_factory", _stub_stage_factory)
    monkeypatch.setattr("jobpipe.runtime.pipeline.profile_match_stage_factory", _stub_stage_factory)
    monkeypatch.setattr("jobpipe.runtime.pipeline.pivot_stage_factory", _stub_stage_factory)
    monkeypatch.setattr("jobpipe.runtime.pipeline.moderate_stage_factory", _stub_stage_factory)
    monkeypatch.setattr("jobpipe.runtime.pipeline.application_pack_stage_factory", _stub_stage_factory)


def test_build_stages_translates_yaml_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_stage_factories(monkeypatch)

    stages = build_stages(
        _cfg(["triage", "parse", "profile_match", "pivot", "moderate", "application_pack"]),
        profile_pack="profile",
    )

    assert [stage.name for stage in stages] == [
        "triage",
        "parsed",
        "profile_match",
        "pivot",
        "moderator",
        "application_pack",
    ]
    assert all(isinstance(stage, Stage) for stage in stages)


def test_build_stages_uses_default_order_when_config_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_stage_factories(monkeypatch)

    stages = build_stages(_cfg([]), profile_pack="profile")

    assert [stage.name for stage in stages] == [
        "triage",
        "reverse_triage",
        "parsed",
        "profile_match",
        "pivot",
        "moderator",
        "application_pack",
    ]


def test_build_stages_respects_configured_disable_of_reverse_triage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_stage_factories(monkeypatch)

    stages = build_stages(
        _cfg(["triage", "parse", "profile_match", "pivot", "moderate", "application_pack"]),
        profile_pack="profile",
    )

    assert [stage.name for stage in stages] == [
        "triage",
        "parsed",
        "profile_match",
        "pivot",
        "moderator",
        "application_pack",
    ]
    assert all(stage.name != "reverse_triage" for stage in stages)


def test_build_stages_rejects_unknown_stage(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_stage_factories(monkeypatch)

    with pytest.raises(ValueError, match="Unknown stage 'writer'"):
        build_stages(_cfg(["triage", "writer"]), profile_pack="profile")
