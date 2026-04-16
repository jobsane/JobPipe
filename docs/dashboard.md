# Dashboard

## Purpose

The dashboard is the candidate-facing decision surface.

It is not meant to be a generic analytics console. It should answer three operational questions quickly:

1. Which jobs need action now?
2. Why were those jobs prioritized?
3. What already happened for each job?

## Data sources

The dashboard export reads from the primary DB:

- `job_evaluations` for latest per-job evaluation state
- `job_run_events` for run history
- `application_summary` and `application_events` for follow-up state
- `generated_documents` for document metadata

It also emits:

- `reports/dashboard.html`
- `reports/dashboard_data.json`

## Core views

### Action list

The default view should surface jobs with:

- `APPLY_STRONGLY`
- `APPLY`
- `REVIEW_HIGH`

The most important fields are:

- title
- employer
- final decision
- fit score
- pivot score
- deadline
- application URL
- recommendation reason
- current application status

### Decision detail

For a selected job, the dashboard should show:

- triage explanation and signals
- score breakdown
- recommendation reason
- generated documents
- application timeline

### Pipeline health

The dashboard should still make it easy to inspect:

- distribution of final decisions
- recent run volume
- skip-reason patterns
- expiring-soon jobs

## Design rules

1. Actionability first.
2. Show why, not just what.
3. Prefer a short explanation over raw metric volume.
4. Keep historical data available without making the default view noisy.
5. Reflect the primary DB as the system of record.

## Current implementation notes

- export is static HTML, not a live web app
- the dashboard is rebuilt by `jobpipe.cli.export_dashboard`
- application state is merged from the primary DB
- generated document metadata is included in the export payload

## Future direction

The next useful dashboard improvements are:

- better source-quality visibility
- clearer advantageous-match signals
- better handling of expiring jobs
- tighter presentation of application-state milestones
