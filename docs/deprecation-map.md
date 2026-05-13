# Deprecation Map

> **Historical (2026-05-13).** This document predates the removal of the JobSync integration.
> JobSync was an upstream/companion review surface that JobDesk + workspace_server have now replaced.
> Sections referencing jobsync modules, CLIs, or schemas reflect the older architecture and are
> kept for context only.


This file is the first-pass cleanup inventory for transitional and likely-stale paths.

It is not a delete list.

Use it to track:

- why a file still exists
- whether it still has live callers
- what the intended replacement is
- what evidence is needed before removal

Status meanings:

- `keep`: canonical or still clearly needed
- `review-first`: likely transitional; verify callers and validation before changing
- `compat`: keep thin; do not enlarge
- `candidate-delete`: likely removable once callers/usage are proven absent

## Initial inventory

| Path | Current role | Status | Likely replacement / owner | Evidence needed before delete |
|---|---|---|---|---|
| `jobpipe/core/schema.py` | Compatibility import surface retained while `jobpipe/model/schema.py` becomes canonical | compat | `jobpipe/model/schema.py` | Keep until import-compat contract is explicitly retired; compat test exists |
| `jobpipe/core/job_catalog.py` | Compatibility import surface for runtime catalog ownership migration | compat | `jobpipe/runtime/catalog.py` | Keep until import-compat contract is explicitly retired; compat test exists |
| `jobpipe/core/paths.py` | Compatibility import surface for runtime path ownership migration | compat | `jobpipe/runtime/paths.py` | Keep until import-compat contract is explicitly retired; path compat tests exist |
| `jobpipe/core/runner.py` | Live orchestration dependency still imported by `jobpipe/cli/run_feed.py` | review-first | thin CLI orchestration + owned runtime helpers | Caller audit confirms live use; any extraction must preserve `run_feed` behavior |
| `jobpipe/cli/run_feed.py` | Main feed entrypoint and live pipeline invocation/orchestration concentration point | review-first | thinner CLI wrapper over a clearer pipeline/runtime boundary | DB run bookkeeping, per-job execution, and repair logic are still concentrated here; extraction should be a dedicated slice |
| `jobpipe/stages/reverse_triage.py` | Still-live optional stage referenced by `jobpipe/cli/run_feed.py`, `sync_evaluations.py`, and model schema | review-first | none yet; requires explicit stage-removal decision | Config check + caller audit + schema impact review before any removal |
| `jobpipe/cli/export_dashboard.py` | Thin wrapper over projection/export path | keep | `jobpipe.projections.dashboard` as owner | none; wrapper is intentional while CLI stays canonical |
| `jobpipe/cli/export_jobsync.py` | Thin wrapper over projection/export path | keep | `jobpipe.projections.jobsync` | none; wrapper is intentional |
| `jobpipe/cli/export_reactive_resume_plan.py` | Thin wrapper over projection/export path | keep | `jobpipe.projections.reactive_resume` | none; wrapper is intentional |
| `jobpipe/compat/__init__.py` | Reserved compat namespace, currently minimal | compat | explicit compatibility shims only | confirm future compat use before adding code |

## Highest-value review targets

Start cleanup review in this order:

1. `jobpipe/cli/run_feed.py`
2. `jobpipe/core/runner.py`
3. `jobpipe/stages/reverse_triage.py`
4. `jobpipe/core/schema.py`
5. `jobpipe/core/job_catalog.py`
6. `jobpipe/core/paths.py`

Why this order:

- `run_feed.py`, `core/runner.py`, `stages/pipeline.py`, and `reverse_triage.py` form a live orchestration seam that looks more removable than it is
- `core/schema.py`, `core/job_catalog.py`, and `core/paths.py` have explicit compatibility value and test coverage
- several replacements are already named in [docs/architecture.md](architecture.md), but removal still requires caller and contract review

## Evidence from first review pass

Confirmed current evidence:

- `jobpipe/core/schema.py` is covered by [tests/test_model_schema_compat.py](../tests/test_model_schema_compat.py)
- `jobpipe/core/job_catalog.py` is covered by [tests/test_runtime_catalog_compat.py](../tests/test_runtime_catalog_compat.py)
- `jobpipe/core/paths.py` is still imported directly by [tests/test_paths.py](../tests/test_paths.py)
- `jobpipe/cli/run_feed.py` still invokes the stage builder and owns DB run bookkeeping, per-job execution, and post-run index repair
- `jobpipe/stages/pipeline.py` owns current stage-builder wiring
- `jobpipe/core/runner.py` is still imported by [jobpipe/cli/run_feed.py](../jobpipe/cli/run_feed.py)
- `jobpipe/stages/reverse_triage.py` is still referenced by:
  - [jobpipe/cli/run_feed.py](../jobpipe/cli/run_feed.py)
  - [jobpipe/cli/sync_evaluations.py](../jobpipe/cli/sync_evaluations.py)
  - [jobpipe/model/schema.py](../jobpipe/model/schema.py)

## Review procedure for each file

Before reclassifying or deleting a file:

1. Check imports and CLI reachability.
2. Check whether tests still reference it directly.
3. Check whether docs/specs still name it as an active path.
4. Run targeted validation after any narrow removal or extraction.
5. Only then move from `review-first` to `candidate-delete` or remove it.

## Explicit non-goal

Do not use this file to justify broad cleanup by intuition.

The purpose is to make cleanup:

- explicit
- reviewable
- reversible
- evidence-backed
