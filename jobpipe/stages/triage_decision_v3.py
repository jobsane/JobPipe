from __future__ import annotations

from pathlib import Path

from jobpipe.core.io import write_json
from jobpipe.core.schema import HardGates, JobContext, TriageDecisionV3
from jobpipe.core.stage_cache import stable_payload_hash
from jobpipe.core.triage_v3 import aggregate_triage_decision


def triage_decision_v3_artifact_path(job_dir: str) -> Path:
    return Path(job_dir) / "bridge_triage_decision_v3.json"


def persist_triage_decision_v3(job_dir: str, decision: TriageDecisionV3) -> None:
    path = triage_decision_v3_artifact_path(job_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(str(path), decision.model_dump())


def triage_decision_v3_cache_key(ctx: JobContext) -> str:
    hard_gates = ctx.triage.hard_gates if ctx.triage and ctx.triage.hard_gates else HardGates()
    payload = {
        "version": "triage_decision_v3.v1",
        "hard_gates": hard_gates.model_dump(),
        "triage_features": ctx.triage_features.model_dump() if ctx.triage_features else None,
    }
    return stable_payload_hash(payload)


def triage_decision_v3_stage_factory():
    def should_run(ctx: JobContext) -> bool:
        return ctx.triage_features is not None

    def run(ctx: JobContext, job_dir: str) -> JobContext:
        hard_gates = ctx.triage.hard_gates if ctx.triage and ctx.triage.hard_gates else HardGates()
        decision = aggregate_triage_decision(ctx.triage_features, hard_gates)
        ctx.triage_decision_v3 = decision
        return ctx

    return should_run, run
