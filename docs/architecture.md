# Architecture

## Overview

JobPipe is a local-first, candidate-scoped pipeline.

The current system has four main layers:

1. source intake
2. staged evaluation
3. primary state storage
4. derived exports and documents

## Runtime flow

```text
source feeds / suggestion intake
    -> pull_sheets_csv / pull_finn_* / scan_gmail / pull_suggested
    -> run_feed
    -> out_runs/<run_id>/<job_id>/*.json
    -> sync_evaluations
    -> primary DB (jobpipe.sqlite)
    -> export_dashboard
    -> reports/dashboard.html + dashboard_data.json + evaluations_latest.csv
```

## Primary state model

The primary DB is the canonical state layer.

It holds:

- candidates
- candidate profiles
- application events and summaries
- generated document metadata
- suggestion leads
- latest job evaluations
- per-run job events

Legacy `ledger.sqlite` is removed from the runtime architecture.

## Filesystem artifacts

Artifacts still matter because JobPipe is intentionally traceable.

The main artifact families are:

- `out_runs/<run_id>/<job_id>/...` for pipeline stage outputs
- exported dashboard files under `reports/`
- generated application documents under the documents root

The DB stores structured state and document metadata. The filesystem stores heavier and more inspectable outputs.

## Runtime roots

JobPipe now supports a clean external data root via `JOBPIPE_DATA_DIR`.

If that variable is set, runtime data can live outside the repo:

- DB
- candidate profile files
- resume JSON
- Gmail credentials and token
- suggestion queue bridge
- embedding cache
- generated documents

Code stays in the repo. Candidate data and runtime history do not have to.

## Main components

| Area | Purpose |
|---|---|
| `go.ps1` | One-shot runner for the normal workflow |
| `jobpipe/cli/` | Operational entry points |
| `jobpipe/stages/` | Evaluation stages |
| `jobpipe/core/` | shared IO, paths, schema, runner, DB helpers |
| `configs/pipeline.v1.yaml` | model choices, thresholds, regex rules |
| `reports/` | exported dashboard and reporting outputs |
| `apps_script/` | upstream NAV feed ingestion support |
| `specs/` | design and migration specs |

## Architectural rules

1. Cheap filters before expensive models.
2. Candidate-specific state belongs in the primary DB or external data root.
3. Artifacts are retained for debugging and trust.
4. Derived exports are not the source of truth.
5. New architecture work should reinforce the current local-first model instead of bypassing it.
