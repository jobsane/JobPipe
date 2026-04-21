# CLI Reference

The canonical operator interface is `jobpipe`.

If the console script is not available in your shell, use:

```text
python -m jobpipe.cli.main ...
```

`go.ps1` remains a Windows convenience wrapper for the one-shot workflow. It is not the canonical product interface.

## Notes on scope

The CLI is the control-plane surface for JobPipe's local-first workflow system.

It operates the candidate-first data-and-reasoning layer. It is not a public platform API and it should not be treated as the product's main source of business differentiation.

## Main workflow

Normal run:

```text
jobpipe run
```

Useful variants:

```text
jobpipe run --dry-run
jobpipe run --no-open
jobpipe run --with-suggestions
```

`jobpipe run --dry-run` is the bounded local smoke path:

- it skips live sheet intake
- it processes at most two already-queued jobs from the local delta if present
- it still runs sync/export so the canonical CLI path and dashboard projection path are exercised

Use plain `jobpipe run` when you want the live intake + drain loop.

`jobpipe run --with-suggestions` currently does this before the normal drain/sync/export loop:

- Gmail status scan
- Gmail suggestion scan
- suggested-job intake processing
- FINN search intake processing

Windows wrapper:

```powershell
.\go.ps1
.\go.ps1 -DryRun
.\go.ps1 -WithSuggestions
```

## Source intake and batch processing

Pull from the published sheet export:

```text
jobpipe pull-sheets --csv-url "<published-csv-url>"
```

Drain the queue and run the pipeline in batches:

```text
jobpipe drain-queue --csv-url "<published-csv-url>" --candidate-id default
```

FINN helpers:

```text
jobpipe pull-finn-search
jobpipe pull-finn-ext --finn-jobs "/path/to/jobs.jsonl"
jobpipe pull-suggested --dry-run
```

## Evaluation sync and dashboard export

Mirror latest evaluations into the primary DB and export a reporting CSV:

```text
jobpipe sync-evaluations --candidate-id default
```

`jobpipe sync-evaluations` also preserves rerunnable job input snapshots from run artifacts in the primary DB so evaluated jobs remain auditable after the live catalog changes.

Rebuild the dashboard export:

```text
jobpipe export-dashboard --candidate-id default
```

Export thin companion workflow projections for `jobsync`:

```text
jobpipe export-jobsync --candidate-id default
jobpipe export-jobsync --job-id JOB_ID
```

Export one thin `reactive-resume` tailoring plan:

```text
jobpipe export-reactive-resume-plan JOB_ID
```

## Candidate state and inspection

Bootstrap current candidate files into the primary DB:

```text
jobpipe bootstrap-state-db
jobpipe import-reactive-resume /path/to/reactive_resume.json
```

Archive generated runtime state and create a fresh post-refactor baseline root:

```text
jobpipe reset-runtime
jobpipe reset-runtime --tag post_refactor_baseline
```

`jobpipe reset-runtime`:

- requires `JOBPIPE_DATA_DIR`
- archives generated runtime state under `<JOBPIPE_DATA_DIR>/_archives/<tag>/`
- recreates fresh `db/`, `artifacts/`, `exports/`, and `cache/` roots
- restores the active `application_state.json` by default so tracked application history can be re-bootstrapped into the fresh DB
- leaves candidate inputs, secrets, and audit outputs in place

The intended rebuild sequence is:

```text
jobpipe reset-runtime
jobpipe bootstrap-state-db
jobpipe run --no-open
```

That sequence is for a bounded fresh baseline plus the normal loop.

If you explicitly want a new full first-pass pull from the sheet/NAV queue, use the lower-level queue command later:

```text
jobpipe drain-queue --reset-state
```

That path is intentionally slower and should be treated as a deliberate operator action, not as the normal smoke or sprint-closure validation surface.

Generate a capability-gap report from current evaluation evidence:

```text
jobpipe gap-analysis --candidate-id default
```

Record explicit manual feedback for later calibration:

```text
jobpipe record-feedback JOB_ID good_recommendation
jobpipe record-feedback JOB_ID bad_recommendation --notes "Prestigious role, but unrealistic ask"
jobpipe record-feedback JOB_ID promote --notes "Non-obvious role family, but strong real match"
jobpipe record-feedback JOB_ID demote
jobpipe record-feedback JOB_ID good_fit
jobpipe record-feedback JOB_ID bad_fit --json
```

Inspect DB state:

```text
jobpipe inspect-db --show summary --show applications --show suggestions
jobpipe inspect-db --show events --limit 20 --json
jobpipe inspect-db --show feedback --show gaps --show gap_assessments --limit 20
jobpipe inspect-db --show job_claims --show job_selection_signals --show job_selection_assessments --job-id JOB_ID
```

Persona audit utilities:

```text
python -m jobpipe.cli.persona_audit --freeze-only
python -m jobpipe.cli.persona_audit --jobs-per-bucket 2
```

The persona audit CLI:

- freezes one local live-corpus baseline
- freezes one small stratified audit slice for the first runnable matrix
- runs each synthetic persona into its own isolated DB, artifacts root, and dashboard export
- keeps persona dashboard application state isolated from the normal local sidecar state
- does not mutate the normal `JOBPIPE_DATA_DIR` state used by day-to-day operation

## Application tracking

Manual status updates:

```text
jobpipe mark-status JOB_ID shortlisted
jobpipe mark-status JOB_ID applied
jobpipe mark-status JOB_ID interview
jobpipe mark-status JOB_ID rejected --notes "Form letter"
jobpipe mark-status JOB_ID dismissed
jobpipe mark-status --list
```

Thin `jobsync` write-back event:

```text
jobpipe record-jobsync-event JOB_ID applied
jobpipe record-jobsync-event JOB_ID interview --notes "Booked in jobsync"
```

Thin `reactive-resume` rendered-document write-back:

```text
jobpipe record-reactive-resume-document JOB_ID tailored_cv_docx "C:/path/to/tailored_cv.docx"
```

## Gmail integration

One-time setup:

```text
jobpipe scan-gmail --setup
```

Status scan:

```text
jobpipe scan-gmail
jobpipe scan-gmail --dry-run --verbose
```

Suggestion scan:

```text
jobpipe scan-gmail --scan-suggestions
jobpipe scan-gmail --scan-suggestions --dry-run
```

## Runtime notes

- The primary DB is the canonical runtime state layer.
- `JOBPIPE_CANDIDATE_ID` defaults to `default` if not set.
- `JOBPIPE_DATA_DIR` is the recommended boundary for persistent user data.
- The canonical top-level `jobpipe run` flags are `--artifacts` and `--exports`; low-level module CLIs may still expose legacy `--out`, `--out-runs`, or `--reports` flags during transition.
- Use the low-level module CLIs when debugging a specific slice.
- Use `jobpipe run` for normal operation.
