from __future__ import annotations
import json
import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Type

from jobpipe.core.io import ensure_dir, write_json, append_jsonl
from jobpipe.core.schema import JobContext
from jobpipe.core.stage_cache import read_artifact_cache_key, write_artifact_cache_key

try:
    from jobpipe.core.decision_sink import get_profile_version, upsert_decision
    from jobpipe.core.paths import get_jobpipe_paths
    _DECISION_SINK_AVAILABLE = True
except ImportError:
    _DECISION_SINK_AVAILABLE = False


def _debug_dump_enabled() -> bool:
    """Per-case JSON artifact + index.jsonl writes.

    After the canonical-state migration these are debug-only IF Supabase is
    available — the upsert via decision_sink is the durable record. When
    Supabase is NOT configured (tests, local fallback), the file artifacts
    ARE the durable record, so writes must stay on.

    Order of precedence:
      1. JOBPIPE_DEBUG_DUMP=1 forces writes on (debug parity with Supabase).
      2. JOBPIPE_DEBUG_DUMP=0 forces writes off.
      3. Otherwise: writes off when JOBPIPE_SUPABASE_URL/KEY are set
         (Supabase is the durable record); writes on otherwise.
    """
    explicit = os.environ.get("JOBPIPE_DEBUG_DUMP")
    if explicit == "1":
        return True
    if explicit == "0":
        return False
    supabase_configured = bool(
        os.environ.get("JOBPIPE_SUPABASE_URL") and os.environ.get("JOBPIPE_SUPABASE_KEY")
    )
    return not supabase_configured

StageFn = Callable[[JobContext, str], JobContext]


@dataclass
class Stage:
    name: str
    run: Any
    should_run: Callable = lambda ctx: True  # default: always run
    ctx_model: Optional[Type] = None  # Pydantic model used to reload cached artifact into ctx
    cache_key_fn: Optional[Callable[[JobContext], str]] = None

    def __post_init__(self):
        # Allow factories to return (should_run, run)
        if isinstance(self.run, tuple) and len(self.run) == 2 and callable(self.run[0]) and callable(self.run[1]):
            self.should_run, self.run = self.run


class PipelineRunner:
    def __init__(self, stages: List[Stage]):
        self.stages = stages

    def run_job(self, ctx: JobContext, job_dir: str, overwrite: bool = False) -> JobContext:
        debug_dump = _debug_dump_enabled()
        ensure_dir(job_dir)
        # save raw input once (debug-only after canonical migration)
        input_path = os.path.join(job_dir, "00_input.json")
        if debug_dump and (overwrite or (not os.path.exists(input_path))):
            write_json(input_path, ctx.job)

        for idx, stage in enumerate(self.stages, start=1):
            if stage.should_run and not stage.should_run(ctx):
                continue

            artifact_path = os.path.join(job_dir, f"{idx:02d}_{stage.name}.json")
            cache_key = stage.cache_key_fn(ctx) if stage.cache_key_fn is not None else None
            if (not overwrite) and os.path.exists(artifact_path):
                if cache_key is not None:
                    cached_key = read_artifact_cache_key(artifact_path)
                    if cached_key != cache_key:
                        pass
                    else:
                        # Reload cached artifact into ctx so downstream stages can read from it.
                        # Without this, a partial run (some stages cached, some not) would see None
                        # for the skipped stage's output, causing downstream should_run() checks to fail.
                        if stage.ctx_model is not None and hasattr(ctx, stage.name):
                            try:
                                with open(artifact_path, encoding="utf-8") as f:
                                    data = json.load(f)
                                setattr(ctx, stage.name, stage.ctx_model(**data))
                            except Exception:
                                pass  # best-effort; if reload fails downstream sees None (same as before)
                        continue

                # Reload cached artifact into ctx so downstream stages can read from it.
                # Without this, a partial run (some stages cached, some not) would see None
                # for the skipped stage's output, causing downstream should_run() checks to fail.
                if cache_key is None:
                    if stage.ctx_model is not None and hasattr(ctx, stage.name):
                        try:
                            with open(artifact_path, encoding="utf-8") as f:
                                data = json.load(f)
                            setattr(ctx, stage.name, stage.ctx_model(**data))
                        except Exception:
                            pass  # best-effort; if reload fails downstream sees None (same as before)
                    continue

            ctx = stage.run(ctx, job_dir)

            # stage writes its own output into ctx; store a stage snapshot too for debugging
            out_obj: Dict[str, Any] = {}
            if hasattr(ctx, stage.name):
                out_val = getattr(ctx, stage.name)
                out_obj = out_val.model_dump() if out_val is not None else {}
            else:
                # some stages (e.g. moderate) may write ctx.moderator but stage.name is "moderate"
                out_obj = ctx.snapshot_summary()

            if debug_dump:
                write_json(artifact_path, out_obj)
                if cache_key is not None:
                    write_artifact_cache_key(artifact_path, cache_key)

        return ctx

    def append_index(self, run_dir: str, ctx: JobContext) -> None:
        summary = ctx.snapshot_summary()
        # Canonical: Supabase. The file index.jsonl is now debug-only.
        if _debug_dump_enabled():
            append_jsonl(os.path.join(run_dir, "index.jsonl"), summary)
        if _DECISION_SINK_AVAILABLE:
            try:
                paths = get_jobpipe_paths()
                upsert_decision(summary, profile_version=get_profile_version(paths.profile_pack_path))
            except Exception:
                pass  # never let a sink failure break the runner
