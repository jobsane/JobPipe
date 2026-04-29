from __future__ import annotations

from typing import List

from jobpipe.core.config import PipelineConfig
from jobpipe.core.runner import Stage
from jobpipe.model.schema import (
    ApplicationPackOut,
    JobParse,
    ModeratorOut,
    PivotOut,
    ProfileMatchOut,
    ReverseTriageOut,
    TriageOut,
)
from jobpipe.stages.application_pack import application_pack_stage_factory
from jobpipe.stages.moderate import moderate_stage_factory
from jobpipe.stages.parse import parse_stage_factory
from jobpipe.stages.pivot import pivot_stage_factory
from jobpipe.stages.profile_match import profile_match_stage_factory
from jobpipe.stages.reverse_triage import reverse_triage_stage_factory
from jobpipe.stages.triage import triage_stage_factory

SUPPORTED_STAGE_ALIASES = {"parse": "parsed", "moderate": "moderator"}

# reverse_triage remains a supported optional stage even when config omits it.
# Keep it in the supported order so validation and callers can reason about the
# full runtime shape without treating the stage as dead code.
SUPPORTED_DEFAULT_STAGE_ORDER = [
    "triage",
    "reverse_triage",
    "parsed",
    "profile_match",
    "pivot",
    "moderator",
    "application_pack",
]


def build_stages(cfg: PipelineConfig, profile_pack: str = "") -> List[Stage]:
    """
    Stage.name must match JobContext attribute names for artifact dumps.
    Accept YAML-friendly aliases:
      - parse     -> parsed
      - moderate  -> moderator
    """
    max_chars = int(cfg.thresholds.get("max_ad_text_chars", 2200))
    triage_max_chars = int(cfg.thresholds.get("triage_max_ad_text_chars", max_chars))
    rt_max_chars = int(cfg.thresholds.get("reverse_triage_max_ad_text_chars", max_chars))
    rt_min_conf = float(cfg.thresholds.get("reverse_triage_min_conf", 0.70))
    rt_skip_above = float(cfg.thresholds.get("reverse_triage_skip_above", 1.0))

    order_raw = cfg.stages or SUPPORTED_DEFAULT_STAGE_ORDER
    order = [SUPPORTED_STAGE_ALIASES.get(s, s) for s in order_raw]

    allowed = set(SUPPORTED_DEFAULT_STAGE_ORDER)
    stages: List[Stage] = []

    for s in order:
        if s not in allowed:
            raise ValueError(
                f"Unknown stage '{s}'. Allowed: {sorted(allowed)} "
                "(aliases: parse->parsed, moderate->moderator)"
            )

        if s == "triage":
            should_tr, run_tr = triage_stage_factory(
                model=cfg.models.get("triage", "gpt-4.1-nano"),
                max_ad_text_chars=triage_max_chars,
                safety_rules=cfg.safety_rules,
                profile_pack=profile_pack,
                semantic_threshold=float(cfg.thresholds.get("semantic_filter_threshold", 0.0)),
                semantic_model=str(cfg.thresholds.get("semantic_filter_model", "BAAI/bge-small-en-v1.5")),
            )
            stages.append(Stage(name="triage", run=run_tr, should_run=should_tr, ctx_model=TriageOut))

        elif s == "reverse_triage":
            should_rt, run_rt = reverse_triage_stage_factory(
                model=cfg.models.get("reverse_triage", "gpt-4.1-mini"),
                max_ad_text_chars=rt_max_chars,
                min_conf=rt_min_conf,
                skip_above=rt_skip_above,
            )
            stages.append(Stage(name="reverse_triage", run=run_rt, should_run=should_rt, ctx_model=ReverseTriageOut))

        elif s == "parsed":
            should_parse, run_parse = parse_stage_factory(
                model=cfg.models.get("parse", "gpt-4.1-mini"),
                max_ad_text_chars=max_chars,
            )
            stages.append(Stage(name="parsed", run=run_parse, should_run=should_parse, ctx_model=JobParse))

        elif s == "profile_match":
            should_pm, run_pm = profile_match_stage_factory(
                model=cfg.models.get("profile_match", "gpt-4.1-mini"),
            )
            stages.append(Stage(name="profile_match", run=run_pm, should_run=should_pm, ctx_model=ProfileMatchOut))

        elif s == "pivot":
            should_pv, run_pv = pivot_stage_factory(
                model=cfg.models.get("pivot", "gpt-4.1-mini"),
            )
            stages.append(Stage(name="pivot", run=run_pv, should_run=should_pv, ctx_model=PivotOut))

        elif s == "moderator":
            should_mod, run_mod = moderate_stage_factory(cfg.thresholds)
            stages.append(Stage(name="moderator", run=run_mod, should_run=should_mod, ctx_model=ModeratorOut))

        elif s == "application_pack":
            should_pack, run_pack = application_pack_stage_factory(
                model=cfg.models.get("application_pack", "gpt-4.1"),
            )
            stages.append(Stage(name="application_pack", run=run_pack, should_run=should_pack, ctx_model=ApplicationPackOut))

    return stages
