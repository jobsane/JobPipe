from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any
import yaml

@dataclass
class PipelineConfig:
    pipeline_name: str
    models: Dict[str, str]
    stages: list[str]
    thresholds: Dict[str, Any]
    safety_rules: Dict[str, Any]

def load_config(path: str) -> PipelineConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return PipelineConfig(
        pipeline_name=raw.get("pipeline_name", "jobpipe"),
        models=raw.get("models", {}),
        stages=raw.get("stages", []),
        thresholds=raw.get("thresholds", {}),
        safety_rules=raw.get("safety_rules", {}),
    )
