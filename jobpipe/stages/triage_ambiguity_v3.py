from __future__ import annotations

from pathlib import Path

from jobpipe.core.io import write_json
from jobpipe.core.schema import JobContext, TriageAmbiguityV3
from jobpipe.core.stage_cache import stable_payload_hash
from jobpipe.core.triage_v3 import resolve_triage_ambiguity


def triage_ambiguity_v3_artifact_path(job_dir: str) -> Path:
    return Path(job_dir) / "bridge_triage_ambiguity_v3.json"


def persist_triage_ambiguity_v3(job_dir: str, ambiguity: TriageAmbiguityV3) -> None:
    path = triage_ambiguity_v3_artifact_path(job_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(str(path), ambiguity.model_dump())


def triage_ambiguity_v3_cache_key(ctx: JobContext) -> str:
    payload = {
        "version": "triage_ambiguity_v3.v1",
        "triage_features": ctx.triage_features.model_dump() if ctx.triage_features else None,
        "triage_decision_v3": ctx.triage_decision_v3.model_dump() if ctx.triage_decision_v3 else None,
    }
    return stable_payload_hash(payload)


def triage_ambiguity_v3_stage_factory():
    def should_run(ctx: JobContext) -> bool:
        return bool(
            ctx.triage_decision_v3
            and ctx.triage_decision_v3.needs_ambiguity_pass
            and ctx.triage_features
        )

    def run(ctx: JobContext, job_dir: str) -> JobContext:
        ambiguity = resolve_triage_ambiguity(ctx.triage_features, ctx.triage_decision_v3)
        ctx.triage_ambiguity_v3 = ambiguity
        return ctx

    return should_run, run
