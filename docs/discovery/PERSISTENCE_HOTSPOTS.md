# Persistence Hotspots

This report maps where JobPipe currently reads or writes durable state before
repository seams, source-event ingestion, or Supabase/Postgres adapters are
introduced.

It is discovery work for
[Jobpipe#167](https://github.com/larsvaerland/Jobpipe/issues/167).

## Discovery Sources

Verified through codebase analysis:

- Indexed repository: `Jobpipe`
- Remote: `https://github.com/larsvaerland/Jobpipe`
- Indexed at: `2026-04-30T17:11:17.371Z`
- Indexed commit: `ed30bf48adde42a9616b431a2fd88f6563f2f417`
- Indexed shape: 238 files, 4903 symbols, 8201 edges, 256 processes

Symbol context was checked for:

- `jobpipe/core/primary_db.py:connect_primary_db`
- `jobpipe/authoring/persist.py:persist_generated_package`
- `jobpipe/cli/scan_gmail.py:_persist_gmail_status`
- `jobpipe/runtime/jobsync.py:record_jobsync_application_status_event`
- `jobpipe/core/primary_db.py:upsert_job_source_record`
- `jobpipe/core/primary_db.py:upsert_job_evaluation`

Direct file inspection was used for the hotspot map below. This matters because
the graph impact result for `connect_primary_db` under-reported the practical
blast radius. Treat `jobpipe/core/primary_db.py` as high-risk even when a graph
walk reports low impact.

## Architecture Rule

JobPipe owns meaning. The database owns storage. Adapters own translation.

The immediate goal is not to replace SQLite or migrate to Supabase. The goal is
to identify durable state boundaries so the current local-first pipe can be
cleaned up without coupling JobSane, JobSync, or Apply Workbench directly to raw
tables and file paths.

## Hotspot Summary

| Domain | Main files | Storage shape | Blast radius | Seam candidate |
|---|---|---|---|---|
| Core DB and schema | `jobpipe/core/primary_db.py` | SQLite schema and helper functions | High | Repository protocols plus SQLite adapter |
| Job intake and source records | `jobpipe/runtime/catalog.py`, `jobpipe/cli/pull_sheets_csv.py`, `jobpipe/cli/pull_finn_search.py`, `jobpipe/cli/pull_finn_ext.py`, `jobpipe/cli/pull_suggested.py` | SQLite, JSONL, source state files | High | `JobRepository`, `SourceRecordRepository`, `SuggestionLeadRepository` |
| Evaluation and decision state | `jobpipe/cli/sync_evaluations.py`, `jobpipe/core/evaluation_state.py`, `jobpipe/decision/persistence.py` | SQLite plus artifact-derived state | High | `EvaluationRepository`, `DecisionRepository`, `ChangeEventRepository` |
| Application events and status | `jobpipe/runtime/jobsync.py`, `jobpipe/cli/record_jobsync_event.py`, `jobpipe/cli/mark_status.py`, `jobpipe/cli/scan_gmail.py` | SQLite plus legacy application state JSON | High | `ApplicationRepository`, `ApplicationEventRepository` |
| Artifacts and generated documents | `jobpipe/stages/application_pack.py`, `jobpipe/authoring/persist.py`, `jobpipe/runtime/reactive_resume.py` | Artifact files plus SQLite metadata | Medium | `ArtifactRepository`, `GeneratedDocumentRepository` |
| JobSync projections | `jobpipe/projections/jobsync.py`, `jobpipe/projections/dashboard.py`, `jobpipe/cli/export_jobsync.py`, `jobpipe/cli/export_dashboard.py` | Read models, exports, SQLite reads | Medium | Projection/read-model service |
| Reactive Resume and candidate profile | `jobpipe/cli/import_reactive_resume.py`, `jobpipe/runtime/reactive_resume.py`, `jobpipe/core/candidate_data.py` | SQLite candidate/profile rows, JSON inputs | Medium | `CandidateProfileRepository`, document reference service |
| Email and external signals | `jobpipe/cli/scan_gmail.py` | SQLite events/leads plus local cache/state | High | `SourceEventRepository`, `ApplicationEventRepository` |
| Runtime paths and local-first files | `jobpipe/runtime/paths.py`, `jobpipe/runtime/data_sources.py` | `JOBPIPE_DATA_DIR`, JSON, JSONL, artifacts, exports | High | Runtime profile and storage-root contract |

## Core DB And Schema

`jobpipe/core/primary_db.py` is the central persistence hotspot.

It currently owns:

- schema bootstrap in `connect_primary_db`
- candidate and candidate profile rows
- application events and application summaries
- generated document metadata
- capability gaps and gap assessments
- suggestion leads
- canonical jobs and source records
- replay inputs
- pipeline runs
- job evaluations and run events
- job claims, selection signals, assessments, and decision tables
- candidate evidence, narrative, watchlists, and change events

This file is already a repository-like module, but it mixes schema creation,
SQLite-specific details, and domain-level write helpers. It should not be
rewritten as one slice.

Recommended treatment:

- document helper groups first
- define repository protocols outside this module
- add a SQLite adapter that can initially delegate to existing helpers
- migrate one low-risk caller at a time

Avoid:

- broad `primary_db.py` rewrite
- schema migration as part of the seam definition
- direct Supabase table writes from JobSane or JobSync

## Job Intake And Source Records

Important files:

- `jobpipe/runtime/catalog.py`
- `jobpipe/cli/pull_sheets_csv.py`
- `jobpipe/cli/pull_finn_search.py`
- `jobpipe/cli/pull_finn_ext.py`
- `jobpipe/cli/pull_suggested.py`
- `jobpipe/cli/drain_queue.py`

Current storage surfaces:

- `jobs` table
- `job_source_records` table
- `suggestion_leads` table
- `jobs_state.json`
- `jobs_delta.jsonl`
- `jobs_expired.jsonl`
- `suggested_jobs.jsonl`
- per-run artifacts

This area blocks the desired NAV/Finn.no-to-canonical-DB path. It is also the
first boundary JobSane will rely on when it adds employer, recruiter, Finn.no,
LinkedIn, or company-page enrichment.

Recommended seams:

- `JobRepository` for canonical job identity and normalized job fields
- `SourceRecordRepository` for source-specific records, active/inactive state,
  and dedupe keys
- `SuggestionLeadRepository` for external leads that are not yet canonical jobs

First safe slice:

- define source-event and source-record contracts before changing callers
- keep JSONL files as transitional local-first intake artifacts
- migrate only one intake caller after the contracts exist

## Evaluation, Triage, And Decision State

Important files:

- `jobpipe/cli/sync_evaluations.py`
- `jobpipe/core/evaluation_state.py`
- `jobpipe/decision/persistence.py`
- `jobpipe/stages/pipeline.py`
- `jobpipe/stages/application_pack.py`

Current storage surfaces:

- `job_evaluations`
- `pipeline_runs`
- `job_run_events`
- `job_claims`
- `job_selection_signals`
- `job_selection_assessments`
- `job_decision_tables`
- `change_events`
- per-stage artifact JSON files

This domain has high blast radius because it decides what becomes curated,
skipped, applied, or authored. It also feeds JobSync and Apply Workbench.

Recommended seams:

- `EvaluationRepository`
- `DecisionRepository`
- `ChangeEventRepository`

First safe slice:

- document how `sync_evaluations` converts run artifacts into canonical DB rows
- keep the stage pipeline unchanged
- avoid changing `build_stages` or stage factories while defining persistence
  seams

## Application Events And Status

Important files:

- `jobpipe/runtime/jobsync.py`
- `jobpipe/cli/record_jobsync_event.py`
- `jobpipe/cli/mark_status.py`
- `jobpipe/cli/scan_gmail.py`
- `jobpipe/projections/dashboard.py`
- `jobpipe/projections/jobsync.py`

Current storage surfaces:

- `application_events`
- `application_summary`
- `application_state.json`
- dashboard and JobSync exports

This is the key boundary for JobSane. Email, portal observations, JobSync
actions, and Apply Workbench events should become traceable events or
suggestions before they affect canonical status.

Recommended seams:

- `ApplicationEventRepository`
- `ApplicationRepository`
- `StatusReconciliationService`

First safe slice:

- define source/application event contract
- define status reconciliation policy
- wrap `record_jobsync_application_status_event` behind a small service boundary
  before moving larger mail/status flows

Avoid:

- letting JobSane write `application_summary` directly
- silently overriding human status choices
- hiding status policy inside CLI modules

## Artifacts And Generated Documents

Important files:

- `jobpipe/stages/application_pack.py`
- `jobpipe/authoring/persist.py`
- `jobpipe/authoring/author_cli.py`
- `jobpipe/runtime/reactive_resume.py`
- `jobpipe/cli/record_reactive_resume_document.py`
- `jobpipe/cli/export_reactive_resume_plan.py`

Current storage surfaces:

- per-run artifact files
- application pack JSON
- generated CV/cover-letter references
- `generated_documents`
- exports under runtime export roots

This area is central to Apply Workbench. The artifact contract should preserve
traceability across draft, generated, manually edited, and final exported
states.

Recommended seams:

- `ArtifactRepository`
- `GeneratedDocumentRepository`
- `ApplicationPackRepository`

First safe slice:

- keep generated document metadata writes as-is
- define the application pack/artifact contract
- migrate document-reference recording before migrating full pack generation

## JobSync Projections

Important files:

- `jobpipe/projections/jobsync.py`
- `jobpipe/projections/dashboard.py`
- `jobpipe/cli/export_jobsync.py`
- `jobpipe/cli/export_dashboard.py`

Current storage surfaces:

- SQLite reads
- derived JSON exports
- dashboard HTML/data exports

Projection code should remain a read/export surface over canonical state. It
should not become an alternate source of truth for status, decisions, or
application artifacts.

Recommended seam:

- projection/read-model service that consumes repositories or stable query
  APIs

First safe slice:

- do not refactor projections until application events, lifecycle, and artifact
  contracts are explicit

## Reactive Resume And Candidate Data

Important files:

- `jobpipe/cli/import_reactive_resume.py`
- `jobpipe/runtime/reactive_resume.py`
- `jobpipe/core/candidate_data.py`
- `jobpipe/projections/reactive_resume.py`

Current storage surfaces:

- candidate rows
- candidate profile rows
- imported Reactive Resume JSON
- generated document references

Reactive Resume should remain the editable profile/CV surface while JobPipe
stores the canonical candidate/profile data needed for matching and tailoring.

Recommended seams:

- `CandidateProfileRepository`
- Reactive Resume import/export adapter
- generated document reference service

First safe slice:

- define the minimum profile fields and round-trip constraints before changing
  import/export behavior

## Email And External Signals

Important file:

- `jobpipe/cli/scan_gmail.py`

Current storage surfaces:

- local Gmail scan state/cache
- `application_events`
- `application_summary`
- `suggestion_leads`
- source reference matching against jobs/source records

This module is a bridge between external observations and canonical JobPipe
state. It is useful but risky because it mixes signal detection, matching,
state/cache writes, and DB writes.

Recommended seams:

- `SourceEventRepository`
- `ApplicationEventRepository`
- signal matching service

First safe slice:

- define source events before refactoring Gmail writes
- treat low-confidence email matches as review items, not status truth
- keep dry-run behavior intact

## Runtime Paths And Local-First Files

Important files:

- `jobpipe/runtime/paths.py`
- `jobpipe/runtime/data_sources.py`
- `jobpipe/cli/refresh_runtime_state.py`
- `jobpipe/cli/bootstrap_state_db.py`
- `jobpipe/cli/reset_runtime.py`

Current storage roots include:

- primary DB path
- artifacts root
- exports root
- documents root
- application state path
- suggested jobs path
- jobs state/delta/expired paths
- runtime data root

This is the current local-first storage boundary. It should remain the default
while repository seams are introduced.

Recommended seam:

- runtime profile/storage-root contract
- adapter factory that can select local SQLite now and Supabase/Postgres later

Avoid:

- changing default runtime roots during persistence cleanup
- making Supabase the only supported runtime path

## First Refactor Slices

Do these after this report and after the source-event/status-policy docs exist.

1. Define repository protocols only.
   - Add type contracts without migrating callers.
   - No behavior change.

2. Wrap generated document persistence.
   - Candidate files: `jobpipe/authoring/persist.py`,
     `jobpipe/runtime/reactive_resume.py`, `jobpipe/stages/application_pack.py`.
   - Lower risk than intake/status because it is mostly append/upsert metadata.

3. Wrap JobSync status event recording.
   - Candidate files: `jobpipe/runtime/jobsync.py`,
     `jobpipe/cli/record_jobsync_event.py`.
   - Useful seam for JobSane and Apply Workbench.

4. Wrap suggestion leads/source records.
   - Candidate files: `jobpipe/cli/pull_suggested.py`,
     `jobpipe/runtime/catalog.py`.
   - Do this after source-event contract is explicit.

5. Wrap evaluation sync.
   - Candidate files: `jobpipe/cli/sync_evaluations.py`,
     `jobpipe/decision/persistence.py`.
   - Higher risk. Do only after smaller seams prove the pattern.

## Tests For Future Slices

Run targeted tests based on changed domain:

- JobSync/status:
  - `tests/test_record_jobsync_event_cli.py`
  - `tests/test_jobsync_runtime.py`
  - `tests/test_mark_status_db_sync.py`
  - `tests/test_scan_gmail_db_sync.py`
- Artifacts/generated documents:
  - `tests/test_application_pack_db_sync.py`
  - `tests/test_author_persist.py`
  - `tests/test_reactive_resume_runtime.py`
- Intake/source records/suggestions:
  - `tests/test_job_catalog_db.py`
  - `tests/test_suggestion_leads_db_sync.py`
- Evaluation/decision sync:
  - `tests/test_sync_evaluations_primary_db.py`
  - decision persistence tests if touched
- Runtime paths:
  - `tests/test_paths.py`
  - `tests/test_reset_runtime_cli.py`

For broad persistence changes, run the full test suite after targeted tests.

## Open Questions

- Which application lifecycle states are canonical versus projection-only?
- Should source events and application events share one envelope or remain
  separate but compatible contracts?
- Which event types may auto-update state, and which must become
  `needs_review`?
- Should generated document metadata reference files, external editor URLs, or
  both?
- Where should repository protocols live: `jobpipe/runtime`, `jobpipe/model`, or
  a new adapter-focused module?
- What is the minimum adapter interface needed to support SQLite now and
  Supabase/Postgres later without weakening local-first behavior?

## Recommended Next Project Items

1. [Jobpipe#165](https://github.com/larsvaerland/Jobpipe/issues/165):
   define source event contract.
2. [Jobpipe#166](https://github.com/larsvaerland/Jobpipe/issues/166):
   define status reconciliation policy.
3. [Jobpipe#159](https://github.com/larsvaerland/Jobpipe/issues/159):
   align lifecycle and artifact contract.
4. [Jobpipe#163](https://github.com/larsvaerland/Jobpipe/issues/163):
   define repository/data seam contracts.

