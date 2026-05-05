from __future__ import annotations
import json
import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Type

from jobpipe.core.io import ensure_dir, write_json, append_jsonl
from jobpipe.core.stage_cache import read_artifact_cache_key, write_artifact_cache_key
from jobpipe.model.schema import JobContext

StageFn = Callable[[JobContext, str], JobContext]


@dataclass
class Stage:
    name: str
    run: Any
    should_run: Callable = lambda ctx: True  # default: always run
    ctx_model: Optional[Type] = None  # Pydantic model used to reload cached artifact into ctx
    cache_key_fn: Optional[Callable[[JobContext], str]] = None  # optional content-hash skip

    def __post_init__(self):
        # Allow factories to return (should_run, run)
        if isinstance(self.run, tuple) and len(self.run) == 2 and callable(self.run[0]) and callable(self.run[1]):
            self.should_run, self.run = self.run


class PipelineRunner:
    def __init__(self, stages: List[Stage]):
        self.stages = stages

    def run_job(self, ctx: JobContext, job_dir: str, overwrite: bool = False) -> JobContext:
        ensure_dir(job_dir)
        # save raw input once
        input_path = os.path.join(job_dir, "00_input.json")
        if overwrite or (not os.path.exists(input_path)):
            write_json(input_path, ctx.job)

        for idx, stage in enumerate(self.stages, start=1):
            if stage.should_run and not stage.should_run(ctx):
                continue

            artifact_path = os.path.join(job_dir, f"{idx:02d}_{stage.name}.json")
            cache_key = stage.cache_key_fn(ctx) if stage.cache_key_fn is not None else None

            if (not overwrite) and os.path.exists(artifact_path):
                # When a cache_key_fn is provided, only skip if the stored key still matches.
                if cache_key is not None:
                    cached_key = read_artifact_cache_key(artifact_path)
                    if cached_key != cache_key:
                        # Inputs changed — fall through to re-run below.
                        pass
                    else:
                        # Cache hit: reload stored artifact into ctx so downstream
                        # should_run() checks don't see None for this stage.
                        _reload_artifact(ctx, stage, artifact_path)
                        continue
                else:
                    # No cache_key_fn: reload and skip unconditionally (old behaviour).
                    _reload_artifact(ctx, stage, artifact_path)
                    continue

            ctx = stage.run(ctx, job_dir)

            # Persist a stage snapshot for debugging and future cache reloads.
            out_obj: Dict[str, Any] = {}
            if hasattr(ctx, stage.name):
                out_val = getattr(ctx, stage.name)
                out_obj = out_val.model_dump() if out_val is not None else {}
            else:
                # some stages (e.g. moderate) write ctx.moderator but stage.name is "moderate"
                out_obj = ctx.snapshot_summary()

            write_json(artifact_path, out_obj)
            if cache_key is not None:
                write_artifact_cache_key(artifact_path, cache_key)

        return ctx

    def append_index(self, run_dir: str, ctx: JobContext) -> None:
        append_jsonl(os.path.join(run_dir, "index.jsonl"), ctx.snapshot_summary())


def _reload_artifact(ctx: JobContext, stage: Stage, artifact_path: str) -> None:
    """Best-effort: load a stored artifact JSON back into ctx.<stage.name>."""
    if stage.ctx_model is not None and hasattr(ctx, stage.name):
        try:
            with open(artifact_path, encoding="utf-8") as f:
                data = json.load(f)
            setattr(ctx, stage.name, stage.ctx_model(**data))
        except Exception:
            pass  # if reload fails downstream sees None — same as before
