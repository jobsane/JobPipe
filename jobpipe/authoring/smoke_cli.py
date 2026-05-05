"""Smoke CLI: build one AuthoringCaseContext from canonical run artifacts.

Reads the canonical JobPipe stage JSON files for a single job in a single run,
assembles the four context inputs, calls build_authoring_case_context, and
writes the result to stdout (or --out path).

No agent call. No generation. No pipeline edit. See
docs/execplans/T002-slice-4.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jobpipe.authoring.builder import build_authoring_case_context
from jobpipe.authoring.case_context import AuthoringCaseContext
from jobpipe.core.candidate_data import (
    default_candidate_id,
    load_candidate_profile_pack,
)
from jobpipe.model.schema import (
    JobContext,
    JobParse,
    ModeratorOut,
    PivotOut,
    ProfileMatchOut,
    RunMeta,
    TriageOut,
)
# ---------------------------------------------------------------------------
# Stubs for helpers removed in the profile_layer refactor.
# The real pipeline now uses build_authoring_context(profile_layer_bundle).
# These stubs keep the smoke CLI importable and the monkeypatch points alive
# for existing tests.  Replace with profile_layer wiring when adapting.
# ---------------------------------------------------------------------------


def _load_resume_context() -> dict:
    """Stub: replaced by profile_layer in the pipeline (kept for smoke-CLI compat)."""
    return {}


def _build_application_pack_contexts(job_ctx, resume_ctx):  # type: ignore[no-untyped-def]
    """Stub: replaced by build_authoring_context(profile_layer_bundle).

    Raises NotImplementedError when called without monkeypatching so callers
    know they must migrate to the profile_layer approach.
    """
    raise NotImplementedError(
        "_build_application_pack_contexts was removed in the profile_layer refactor. "
        "Use build_authoring_context(load_or_build_profile_layer_for_paths(paths)) "
        "from jobpipe.core.profile_layer instead."
    )


# ---------------------------------------------------------------------------
# Artifact loading
# ---------------------------------------------------------------------------


def _load_stage(job_dir: Path, *candidates: str) -> dict[str, Any]:
    """Load the first candidate stage file that exists; raise if none."""
    tried: list[str] = []
    for name in candidates:
        path = job_dir / name
        tried.append(str(path))
        if path.is_file():
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
    raise FileNotFoundError(
        f"No stage artifact found for job_dir={job_dir}. Tried: {tried}"
    )


def _resolve_job_dir(artifacts_root: Path, run_id: str | None, job_id: str) -> Path:
    """Resolve <artifacts_root>/<run_id>/<job_id>. If run_id is None, pick latest."""
    if run_id is not None:
        candidate = artifacts_root / run_id / job_id
        if not candidate.is_dir():
            raise FileNotFoundError(
                f"job_dir does not exist: {candidate}"
            )
        return candidate
    # Pick the most recent run_id directory that contains this job_id.
    if not artifacts_root.is_dir():
        raise FileNotFoundError(f"artifacts_root does not exist: {artifacts_root}")
    matches = [
        d for d in artifacts_root.iterdir()
        if d.is_dir() and (d / job_id).is_dir()
    ]
    if not matches:
        raise FileNotFoundError(
            f"No run under {artifacts_root} contains job_id={job_id}"
        )
    # Sort by mtime descending; the caller can still override with --run.
    matches.sort(key=lambda d: d.stat().st_mtime, reverse=True)
    return matches[0] / job_id


# ---------------------------------------------------------------------------
# Context assembly
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")


def _try_validate(cls: Any, data: dict[str, Any] | None):
    """Validate with a pydantic model; return None if data is empty/falsy."""
    if not data:
        return None
    return cls.model_validate(data)


def _optional_stage(job_dir: Path, *candidates: str) -> dict[str, Any]:
    """Like _load_stage, but returns {} instead of raising on missing."""
    for name in candidates:
        path = job_dir / name
        if path.is_file():
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
    return {}


def build_context_for_job(
    *,
    artifacts_root: Path,
    run_id: str | None,
    job_id: str,
    candidate_id: str | None = None,
) -> AuthoringCaseContext:
    """Assemble AuthoringCaseContext from canonical run artifacts.

    Reuses the production assembly helper `_build_application_pack_contexts`
    from `jobpipe.stages.application_pack` so the smoke CLI produces the
    same three derived contexts (decision / evidence / narrative) that the
    real application_pack stage produces. This avoids drift between the
    smoke path and the production path.
    """
    job_dir = _resolve_job_dir(artifacts_root, run_id, job_id)
    effective_run_id = run_id or job_dir.parent.name
    effective_candidate_id = candidate_id or default_candidate_id()

    # --- Load raw stage JSON --------------------------------------------------
    # Required:
    input_data = _load_stage(job_dir, "00_input.json")
    parsed_data = _load_stage(job_dir, "02_parsed.json", "03_parsed.json")
    moderator_data = _load_stage(job_dir, "05_moderator.json", "06_moderator.json")
    # Optional (the job_view helper tolerates None for these):
    triage_data = _optional_stage(job_dir, "01_triage.json")
    pm_data = _optional_stage(job_dir, "03_profile_match.json", "04_profile_match.json")
    pivot_data = _optional_stage(job_dir, "04_pivot.json", "05_pivot.json")

    if not moderator_data:
        raise ValueError(
            f"[job_id={job_id}] moderator stage JSON is empty; cannot build authoring context"
        )
    if not parsed_data:
        raise ValueError(
            f"[job_id={job_id}] parse stage JSON is empty; cannot build authoring context"
        )

    # --- Candidate static inputs ---------------------------------------------
    profile_pack_text = load_candidate_profile_pack(candidate_id=effective_candidate_id)
    resume_ctx = _load_resume_context()  # canonical compacted shape

    # --- Assemble JobContext --------------------------------------------------
    # Builder guards: job_ctx.moderator and job_ctx.parsed MUST be present.
    # Triage / profile_match / pivot stay validated when present because
    # _application_pack_job_view reads their attributes with `if ctx.X`.
    job_ctx = JobContext.model_construct(
        meta=RunMeta(
            run_id=effective_run_id,
            pipeline_name="smoke_cli",
            created_at=_now_iso(),
        ),
        job_id=job_id,
        job=input_data,
        profile_pack=profile_pack_text,
        triage=_try_validate(TriageOut, triage_data),
        reverse_triage=None,
        parsed=JobParse.model_validate(parsed_data),
        profile_match=_try_validate(ProfileMatchOut, pm_data),
        pivot=_try_validate(PivotOut, pivot_data),
        moderator=ModeratorOut.model_validate(moderator_data),
        notes={},
    )

    # --- Build the three derived contexts via the PRODUCTION helper ---------
    # _build_application_pack_contexts(ctx, resume_ctx) -> (decision, evidence, narrative)
    # using the correct Mapping[str, Any] / profile_pack str / evidence-unit-list
    # call shape. This is the same function application_pack_stage uses in prod.
    decision_ctx, evidence_ctx, narrative_ctx = _build_application_pack_contexts(
        job_ctx, resume_ctx
    )

    # --- Call the pure constructor -------------------------------------------
    evaluation_id = f"{effective_run_id}:{job_id}"
    return build_authoring_case_context(
        job_ctx,
        decision_ctx,
        evidence_ctx,
        narrative_ctx,
        candidate_id=effective_candidate_id,
        evaluation_id=evaluation_id,
    )


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def _to_jsonable(obj: Any) -> Any:
    """Convert AuthoringCaseContext (frozen dataclass) to a JSON-ready dict."""
    if is_dataclass(obj):
        return {k: _to_jsonable(v) for k, v in asdict(obj).items()}
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    return obj


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------


def add_subparser(subparsers: argparse._SubParsersAction) -> None:
    """Register 'build-authoring-context' with the main jobpipe CLI."""
    p = subparsers.add_parser(
        "build-authoring-context",
        help="Build one AuthoringCaseContext from canonical run artifacts (smoke).",
    )
    _add_arguments(p)
    p.set_defaults(func=_run)


def _add_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("--job", required=True, help="job_id to build context for")
    p.add_argument("--run", default=None, help="run_id (defaults to latest run containing --job)")
    p.add_argument(
        "--artifacts-root",
        default="artifacts",
        help="Root artifacts directory (default: ./artifacts)",
    )
    p.add_argument("--candidate", default=None, help="candidate_id (default: default_candidate_id())")
    p.add_argument("--out", default=None, help="Write JSON to this path instead of stdout")
    p.add_argument(
        "--validate",
        action="store_true",
        default=False,
        help="Run deterministic validation rules on the built context and report.",
    )


def _run(args: argparse.Namespace) -> int:
    ctx = build_context_for_job(
        artifacts_root=Path(args.artifacts_root),
        run_id=args.run,
        job_id=args.job,
        candidate_id=args.candidate,
    )
    if args.validate:
        from jobpipe.authoring.validation import validate_authoring_context

        result = validate_authoring_context(ctx)
        _print_validation_result(result)
        if not result.passed:
            return 2

    payload = _to_jsonable(ctx)
    text = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        sys.stdout.write(text)
        sys.stdout.write("\n")
    return 0


def _print_validation_result(result) -> None:
    summary = (
        f"[validate] passed={result.passed}"
        f"  score={result.score:.2f}"
        f"  failures={len(result.failures)}"
        f"  warnings={len(result.warnings)}"
    )
    print(summary, file=sys.stderr)
    for failure in result.failures:
        print(f"  FAIL: {failure}", file=sys.stderr)
    for warning in result.warnings:
        print(f"  WARN: {warning}", file=sys.stderr)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="jobpipe build-authoring-context",
        description="Build one AuthoringCaseContext from canonical run artifacts (smoke).",
    )
    _add_arguments(parser)
    args = parser.parse_args(argv)
    raise SystemExit(_run(args))


if __name__ == "__main__":
    main()
