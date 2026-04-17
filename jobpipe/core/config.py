from __future__ import annotations
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Dict, Any, Iterable
import yaml

@dataclass
class PipelineConfig:
    pipeline_name: str
    models: Dict[str, str]
    stages: list[str]
    thresholds: Dict[str, Any]
    safety_rules: Dict[str, Any]


def _load_yaml_dict(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Config file must contain a top-level mapping: {path}")
    return raw


def _merge_dicts(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _merge_dicts(current, value)
        else:
            merged[key] = value
    return merged


def resolve_config_overlays(overlays: Iterable[str] | None = None) -> list[Path]:
    resolved: list[Path] = []

    env_raw = os.environ.get("JOBPIPE_CONFIG_OVERLAY", "").strip()
    if env_raw:
        for item in env_raw.split(os.pathsep):
            item = item.strip()
            if item:
                resolved.append(Path(item))

    for item in overlays or []:
        text = str(item).strip()
        if text:
            resolved.append(Path(text))

    return resolved


def load_raw_config(path: str | Path, overlays: Iterable[str] | None = None) -> Dict[str, Any]:
    config_path = Path(path)
    raw = _load_yaml_dict(config_path)

    for overlay_path in resolve_config_overlays(overlays):
        if not overlay_path.exists():
            raise FileNotFoundError(f"Config overlay not found: {overlay_path}")
        overlay_raw = _load_yaml_dict(overlay_path)
        raw = _merge_dicts(raw, overlay_raw)

    return raw


def load_config(path: str | Path, overlays: Iterable[str] | None = None) -> PipelineConfig:
    raw = load_raw_config(path, overlays=overlays)
    return PipelineConfig(
        pipeline_name=raw.get("pipeline_name", "jobpipe"),
        models=raw.get("models", {}),
        stages=raw.get("stages", []),
        thresholds=raw.get("thresholds", {}),
        safety_rules=raw.get("safety_rules", {}),
    )
