# Architecture

This file describes the current runtime shape and the target boundary model at a high level.

Canonical planning source:

- [MASTER_PLAN.md](../MASTER_PLAN.md)
- [OSS_SCOPE.md](../OSS_SCOPE.md)
- [../specs/architecture-boundaries.md](../specs/architecture-boundaries.md)

This is not the place to redefine product scope.

The current public repo should also be read as the OSS-first foundation for the project.

Any later private/commercial implementation should build on this foundation rather than redefine the canonical public model here.

Current sibling-integration seam references:

- [../specs/jobsync-integration-seam.md](../specs/jobsync-integration-seam.md)
- [../specs/reactive-resume-integration-seam.md](../specs/reactive-resume-integration-seam.md)

## Overview

JobPipe is a local-first, candidate-first, hiring-aware data-and-reasoning layer.

The runtime currently has four major layers:

1. source intake
2. staged evaluation
3. canonical state storage
4. derived projections and documents

The architectural rule is simple:

**business value should accumulate in the canonical data model, not in one connector or one UI surface.**

## Runtime flow

```text
source feeds / suggestion intake
    -> pull_sheets_csv / pull_finn_* / scan_gmail / pull_suggested
    -> run_feed
    -> per-job stage artifacts
    -> sync_evaluations
    -> primary DB (jobpipe.sqlite)
    -> jobpipe.projections.dashboard
    -> derived exports and candidate-facing surfaces
```

## Canonical state

The primary DB is the canonical runtime state layer.

It is the shared substrate for:

- candidate state
- canonical jobs and source records
- reproducible replay inputs for evaluated jobs
- evaluation history
- application events and summaries
- generated document metadata
- feedback and calibration
- first-class claims, selection, decision-table, evidence, narrative, and monitoring layers

Legacy `ledger.sqlite` is not part of the intended runtime architecture.

## Runtime roots

The intended runtime boundary is `JOBPIPE_DATA_DIR`.

Code stays in the repo.

User data and runtime data should live outside it:

- DB
- candidate files
- artifacts
- exports
- documents
- credentials
- caches

This keeps JobPipe stable across:

- code changes
- provider changes
- UI changes
- later deployment changes

## Artifacts and projections

JobPipe is intentionally traceable.

Canonical naming is moving toward:

- `artifacts/` for run outputs
- `exports/` for derived reporting/dashboard outputs
- `documents/` for generated candidate-facing files

The repo still contains legacy `out_runs/` and `reports/` naming in places during transition. Those should be treated as transitional runtime/output names, not long-term architectural truth.

## Current main components

| Area | Purpose |
|---|---|
| `jobpipe/cli/main.py` | canonical cross-platform CLI |
| `go.ps1` | Windows wrapper over the canonical CLI |
| `jobpipe/cli/` | operational entry points |
| `jobpipe/runtime/` | canonical runtime roots, path helpers, storage-boundary logic, and canonical intake/dedup services |
| `jobpipe/model/` | canonical public schema and domain-model boundary |
| `jobpipe/decision/` | canonical public decision objects, deterministic claim/selection/decision/evidence/narrative/monitoring derivation, calibration helpers, and persistence adapters for promoted decision-state rows |
| `jobpipe/projections/` | canonical export/projection logic built on canonical state |
| `jobpipe/connectors/mail/` | extracted Gmail provider/session, parsing, suggestion, and status-helper logic |
| `jobpipe/stages/` | evaluation stages, current stage-builder wiring, and interpretation pipeline |
| `jobpipe/core/` | transitional shared IO, compat shims, runner, and DB helpers |
| `configs/pipeline.v1.yaml` | thresholds, stage order, model choices, rules |
| `docs/` | runtime/operator documentation |
| `specs/` | active and future design targets |
| `apps_script/` | transitional NAV ingestion support |

## Target public boundary model

The public repo should converge toward these package slices:

1. `jobpipe/cli`
2. `jobpipe/runtime`
3. `jobpipe/model`
4. `jobpipe/connectors`
5. `jobpipe/decision`
6. `jobpipe/projections`
7. `jobpipe/compat`

This target boundary model is defined in:

- [specs/architecture-boundaries.md](../specs/architecture-boundaries.md)

Important note:

- the current `core/` and `stages/` layout remains transitional
- `jobpipe/model/` now owns the canonical schema surface, while `jobpipe/core/schema.py` remains a compatibility shim during migration
- `jobpipe/runtime/paths.py` now owns the canonical runtime-root mapping, including `db/`, `artifacts/`, `exports/`, `documents/`, `cache/`, and `secrets/` under `JOBPIPE_DATA_DIR`
- `jobpipe/runtime/catalog.py` now owns canonical job/source-record intake and dedup behavior, while `jobpipe/core/job_catalog.py` remains a compatibility shim during migration
- `jobpipe/stages/pipeline.py` now owns current stage-builder wiring; `jobpipe/runtime/` must stay below stages and must not import stage modules
- `jobpipe/decision/` now owns the first public decision-substrate objects: deterministic `job_claims`, `selection_signals`, `selection_assessment`, a derived `decision_table`, deterministic candidate-evidence derivation/selection helpers, deterministic narrative derivation/assessment helpers, deterministic monitoring/change interpretation, and decision-state persistence adapters built on the primary DB
- `jobpipe/projections/dashboard.py` now owns the canonical dashboard projection logic, while `jobpipe/cli/export_dashboard.py` remains a thin CLI wrapper
- the mail/Gmail path is now substantially extracted into `jobpipe/connectors/mail/`
- `jobpipe/cli/scan_gmail.py` now mainly owns orchestration, matching, and persistence rather than provider/session/parsing helpers
- `jobpipe/cli/sync_evaluations.py` now promotes job-level decision state and monitoring state into first-class DB rows
- `jobpipe/cli/sync_evaluations.py` now also preserves rerunnable job input snapshots in the primary DB so evaluated jobs can be replayed even when the live catalog has moved on
- `jobpipe/stages/application_pack.py` now promotes candidate-evidence and narrative state into first-class DB rows when that seam already has the necessary context
- `jobpipe/authoring/` is the public authoring adapter contract and deterministic/local authoring surface
- `jobpipe_crewai/` is an optional CrewAI implementation outside `jobpipe/`; `jobpipe/` may load it dynamically through the author factory but must not statically import CrewAI
- the architecture pass does not require an immediate rewrite
- new work should increasingly land in the target slices instead of enlarging `core/` and `cli/` in the wrong directions

## Architectural rules

1. Cheap filters before expensive models.
2. Candidate-specific and evaluation state belongs in canonical storage, not in exports.
3. Connectors stay thin and stop at normalization.
4. Artifacts are retained for trust and debugging.
5. Exports are projections, not the source of truth.
6. New architecture work should reinforce the local-first control plane instead of bypassing it.
7. The public repo should expose stable public interfaces and baseline implementations; later premium logic should sit on top of them rather than fork the model.
8. Sibling repos may be integrated through thin versioned seams, but must not become alternate canonical state owners.

## Next architectural pressure points

The next architecture pass should inherit these already-settled truths:

- data is the product
- evidence-backed decision support is the core mechanism
- living monitoring is the repeat-usage mechanism
- candidate-first but hiring-aware logic belongs in the model
- connector cleanup and runtime-boundary cleanup come before platform expansion
- the public repo is the OSS-first foundation
- the later private/commercial layer should build on the public foundation rather than redefining it
- `jobpipe/decision/` now owns deterministic monitoring/change interpretation helpers built from canonical job state, run history, and application state
- `jobpipe/decision/` now also owns deterministic local calibration helpers built from local feedback, explicit settings, and outcome history
- calibration summaries and per-job calibration assessments still remain derived interpretations over local state rather than separately persisted learned-state tables
