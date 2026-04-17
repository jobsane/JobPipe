from __future__ import annotations

import os
from pathlib import Path
from textwrap import dedent

import pytest

from jobpipe.core.config import load_config, load_raw_config


def _write_yaml(path: Path, text: str) -> None:
    path.write_text(dedent(text).strip() + "\n", encoding="utf-8")


def test_load_raw_config_merges_nested_overlays(tmp_path: Path) -> None:
    base = tmp_path / "base.yaml"
    overlay = tmp_path / "overlay.yaml"

    _write_yaml(
        base,
        """
        pipeline_name: jobpipe_v1
        models:
          triage: gpt-4.1-nano
          application_pack: gpt-4.1-mini
        thresholds:
          apply_fit: 67
          semantic_filter_threshold: 0.30
        safety_rules:
          geo_enabled: true
          geo_county_regex: old
        stages:
          - triage
          - moderate
        """,
    )
    _write_yaml(
        overlay,
        """
        pipeline_name: jobpipe_workbench
        models:
          application_pack: gpt-4.1
        thresholds:
          semantic_filter_threshold: 0.42
        safety_rules:
          geo_county_regex: new
        stages:
          - triage
          - parse
          - moderate
        """,
    )

    raw = load_raw_config(base, overlays=[str(overlay)])

    assert raw["pipeline_name"] == "jobpipe_workbench"
    assert raw["models"]["triage"] == "gpt-4.1-nano"
    assert raw["models"]["application_pack"] == "gpt-4.1"
    assert raw["thresholds"]["apply_fit"] == 67
    assert raw["thresholds"]["semantic_filter_threshold"] == 0.42
    assert raw["safety_rules"]["geo_enabled"] is True
    assert raw["safety_rules"]["geo_county_regex"] == "new"
    assert raw["stages"] == ["triage", "parse", "moderate"]


def test_load_config_uses_jobpipe_config_overlay_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = tmp_path / "base.yaml"
    overlay = tmp_path / "overlay.yaml"

    _write_yaml(
        base,
        """
        pipeline_name: jobpipe_v1
        models:
          triage: gpt-4.1-nano
        thresholds:
          apply_fit: 67
        safety_rules: {}
        stages:
          - triage
        """,
    )
    _write_yaml(
        overlay,
        """
        thresholds:
          apply_fit: 75
        """,
    )

    monkeypatch.setenv("JOBPIPE_CONFIG_OVERLAY", str(overlay))
    cfg = load_config(base)

    assert cfg.pipeline_name == "jobpipe_v1"
    assert cfg.thresholds["apply_fit"] == 75


def test_explicit_overlay_is_applied_after_env_overlay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = tmp_path / "base.yaml"
    env_overlay = tmp_path / "env.yaml"
    explicit_overlay = tmp_path / "explicit.yaml"

    _write_yaml(
        base,
        """
        pipeline_name: jobpipe_v1
        models: {}
        thresholds:
          apply_fit: 67
        safety_rules: {}
        stages:
          - triage
        """,
    )
    _write_yaml(
        env_overlay,
        """
        thresholds:
          apply_fit: 70
        """,
    )
    _write_yaml(
        explicit_overlay,
        """
        thresholds:
          apply_fit: 73
        """,
    )

    monkeypatch.setenv("JOBPIPE_CONFIG_OVERLAY", os.pathsep.join([str(env_overlay)]))
    cfg = load_config(base, overlays=[str(explicit_overlay)])

    assert cfg.thresholds["apply_fit"] == 73


def test_load_config_accepts_empty_yaml_with_defaults(tmp_path: Path) -> None:
    base = tmp_path / "empty.yaml"
    base.write_text("", encoding="utf-8")

    cfg = load_config(base)

    assert cfg.pipeline_name == "jobpipe"
    assert cfg.models == {}
    assert cfg.stages == []
    assert cfg.thresholds == {}
    assert cfg.safety_rules == {}


def test_load_raw_config_rejects_non_mapping_root(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("- triage\n- parse\n", encoding="utf-8")

    with pytest.raises(ValueError, match="top-level mapping"):
        load_raw_config(bad)
