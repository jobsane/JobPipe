# Architecture Plan

Last updated: 2026-04-17

This is the canonical architecture note for the active system. Fold architecture updates into this file instead of creating dated architecture snapshots.

## Red Line

The product only works if the same job can be traced cleanly from source input to final dashboard action:

1. source data arrives intact
2. cheap filters remove noise first
3. every stage leaves evidence
4. the ledger becomes the durable system of record
5. the dashboard projects that record without guessing

If a field is useful for filtering, debugging, scoring, or acting, it should either be carried explicitly or be intentionally excluded with a documented reason.

## Actual Running Architecture

```text
NAV pam-stilling-feed
    ↓ Apps Script
Google Sheet (JobFeed)
    ↓ pull_sheets_csv.py
<data-root>/jobs_delta.jsonl
    ↓ run_feed.py
    00_input.json
    01_triage.json
    02_parsed.json
    03_profile_match.json
    04_pivot.json
    05_moderator.json
    06_application_pack.json   (APPLY/APPLY_STRONGLY only)
    07_cv_highlights.docx      (APPLY/APPLY_STRONGLY only)
    ↓ sync_ledger.py
<data-root>/reports/ledger.sqlite
    ↓ export_dashboard.py
<data-root>/exports/dashboard.html
```

Related local runtime:

```text
dashboard_server.py
    ↓ build_payload()
SQLite + <data-root>/out_runs + <data-root>/reports/application_state.json + <data-root>/reports/resume.json
    ↓
dashboard template + apply template served on localhost
```

## Data Contract By Layer

### 1. Input contract

`pull_sheets_csv.py` already preserves more data than the dashboard currently uses:

- identity: `job_id`, `uuid`
- job metadata: `title`, `employer_name`, `status`, `ad_updated`, `sistEndret`
- action data: `applicationUrl`, `applicationDue`, `sourceurl`, `link`
- location: `work_city`, `work_county`, `work_postalCode`, `workLocations_json`
- zero-cost taxonomy: `occ_level1`, `occ_level2`, `cat_type`, `cat_code`, `cat_name`, `cat_score`
- optional normalization: `normalized_title`

This is good. The main issue is not ingestion; it is carry-through.

### 2. Artifact contract

Each stage writes JSON per job. This gives strong traceability, but the dashboard is not consuming the full artifact graph:

- triage additive fields like `noise_level` and `forced_safety` are not carried into the ledger
- parsed output is not represented in the ledger
- application pack output is only partially represented in the ledger

### 3. Ledger contract

`sync_ledger.py` is the critical narrowing point. It now keeps:

- identity, URLs, location, due date
- triage summary
- reverse triage summary
- fit and pivot scores
- final decision
- selected raw blobs for match, pivot, moderator
- `skip_reason`
- source taxonomy and normalized titles
- application-pack summary fields
- closed state and source identity needed by the dashboard

### 4. Dashboard payload contract

`export_dashboard.py` builds a single payload for both static export and local server mode. It now exports:

- thresholds and config snapshot
- profile/resume summary for the Profile & CV page
- source/taxonomy fields for filtering and debugging
- pack readiness summary
- closed state
- payload budget metadata

### 5. UI contract

The dashboard currently mixes two interaction models:

1. Static report mode
2. Local app mode via `dashboard_server.py`

This is the main architectural reason the dashboard feels clunky. The product surface is split between:

- `dashboard.html`
- `dashboard_server.py`
- `apply_template.html`
- `resume.json`
- per-job files under `out_runs/`

## Verified Breakpoints

These remain the main pressure points after Topics 1-7:

1. Some actionable rows still have no fixed deadline because the source data itself does not provide one.
2. Queue dedupe/grouping still lives in dashboard JS rather than the payload contract.
3. The deep drafting route is still a separate surface from the main workspace page.
4. Documentation and local habits still need to stay aligned with the new external data-root contract.

## Target Architecture

The next stable shape should be:

```text
source jobs
    ↓
normalized artifacts
    ↓
ledger.sqlite   <- single durable record for dashboard-worthy fields
    ↓
build_payload() <- one canonical payload builder
    ↓
static export OR local server
    ↓
same UI contract
```

Principles for that target:

- `build_payload()` is the only source for dashboard data
- static export and server mode share the same payload
- no dashboard logic guesses skip reason, thresholds, or pack state
- profile/CV data is first-class, not hidden behind a per-job workspace
- filesystem reads remain a fallback, not a primary UI dependency

## Page Model For The Dashboard

The dashboard should evolve into a small local product with these pages:

1. Jobs
   Action list, filters, deadlines, statuses, pack state.
2. Pipeline
   Funnel, skip reasons, score distributions, calibration and source metrics.
3. Profile & CV
   `<data-root>/reports/resume.json`, `<data-root>/profile_pack.md`, strengths, target roles, reusable CV material.
4. Application Workspace
   Current `apply_template.html`, but integrated intentionally.
5. Debug / Data
   Field completeness, schema version, run health, payload validation.

## Validation Standard

A change is not done until these hold:

- field origin is documented
- field owner is clear
- field survives to ledger or is intentionally excluded
- dashboard reads explicit values instead of inferring from gaps
- tests cover the contract where code exists
