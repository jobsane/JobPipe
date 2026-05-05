from __future__ import annotations

from typing import List

from jobpipe.core.config import PipelineConfig
from jobpipe.core.runner import Stage
from jobpipe.model.schema import (
    AdvantageAssessmentV3,
    ApplicationPackOut,
    JobParse,
    ModeratorOut,
    NarrativeStrategyV3,
    PivotOut,
    ProfileMatchOut,
    ReverseTriageOut,
    TriageAmbiguityV3,
    TriageDecisionV3,
    TriageFeatures,
    TriageOut,
)
from jobpipe.stages.advantage_assessment_v3 import advantage_assessment_v3_stage_factory
from jobpipe.stages.application_pack import application_pack_stage_factory
from jobpipe.stages.moderate import moderate_stage_factory
from jobpipe.stages.narrative_strategy_v3 import narrative_strategy_v3_stage_factory
from jobpipe.stages.parse import parse_stage_factory
from jobpipe.stages.pivot import pivot_stage_factory
from jobpipe.stages.profile_match import profile_match_stage_factory
from jobpipe.stages.reverse_triage import reverse_triage_stage_factory
from jobpipe.stages.triage import triage_stage_factory
from jobpipe.stages.triage_ambiguity_v3 import triage_ambiguity_v3_stage_factory
from jobpipe.stages.triage_decision_v3 import triage_decision_v3_stage_factory
from jobpipe.stages.triage_features import triage_features_stage_factory

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
    "triage_features",
    "triage_decision_v3",
    "triage_ambiguity_v3",
    "advantage_assessment_v3",
    "narrative_strategy_v3",
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

        elif s == "triage_features":
            should_tf, run_tf = triage_features_stage_factory()
            stages.append(Stage(name="triage_features", run=run_tf, should_run=should_tf, ctx_model=TriageFeatures))

        elif s == "triage_decision_v3":
            should_td, run_td = triage_decision_v3_stage_factory()
            stages.append(Stage(name="triage_decision_v3", run=run_td, should_run=should_td, ctx_model=TriageDecisionV3))

        elif s == "triage_ambiguity_v3":
            should_ta, run_ta = triage_ambiguity_v3_stage_factory()
            stages.append(Stage(name="triage_ambiguity_v3", run=run_ta, should_run=should_ta, ctx_model=TriageAmbiguityV3))

        elif s == "advantage_assessment_v3":
            should_aa, run_aa = advantage_assessment_v3_stage_factory()
            stages.append(Stage(name="advantage_assessment_v3", run=run_aa, should_run=should_aa, ctx_model=AdvantageAssessmentV3))

        elif s == "narrative_strategy_v3":
            should_ns, run_ns = narrative_strategy_v3_stage_factory()
            stages.append(Stage(name="narrative_strategy_v3", run=run_ns, should_run=should_ns, ctx_model=NarrativeStrategyV3))

        elif s == "moderator":
            should_mod, run_mod = moderate_stage_factory(cfg.thresholds)
            stages.append(Stage(name="moderator", run=run_mod, should_run=should_mod, ctx_model=ModeratorOut))

        elif s == "application_pack":
            should_pack, run_pack = application_pack_stage_factory(
                model=cfg.models.get("application_pack", "gpt-4.1"),
            )
            stages.append(
                Stage(name="application_pack", run=run_pack, should_run=should_pack, ctx_model=ApplicationPackOut)
            )

    return stages
