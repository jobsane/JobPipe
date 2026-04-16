# JobPipe Canonical Data Model

## Purpose

This document defines the clean data foundation JobPipe should grow toward.

The goal is to:

- keep the repository lean
- keep the workflow local-first and practical
- support one user well today
- make future multi-user/server work possible without rewriting the product model
- avoid premature architecture drift toward tools the app does not actually need yet

This is a repo-grounded spec. It reflects how JobPipe works today:

- staged pipeline in `jobpipe/stages/`
- per-job run artifacts in `out_runs/`
- latest-state evaluation data in `jobpipe.sqlite`
- follow-up state in `application_state.json`
- candidate truth currently split across `profile_pack.md`, `resume.json`, `.env`, and sidecar files

---

## Current State

Today JobPipe stores meaningfully different kinds of data in different formats:

| Concern | Current shape | Current location |
|---|---|---|
| Candidate targeting | Markdown truth source | `profile_pack.md` |
| Candidate CV data | JSON Resume file | `resume.json` |
| Application lifecycle | Sidecar JSON | `application_state.json` |
| Suggested jobs | JSONL queue | `suggested_jobs.jsonl` |
| Semantic cache | NPY file | `profile_embedding.npy` |
| Raw pipeline artifacts | JSON per stage per job | `out_runs/<run_id>/<job_id>/` |
| Latest evaluation state | SQLite + CSV | `jobpipe.sqlite` (`job_evaluations`, `job_run_events`), `reports/evaluations_latest.csv` |
| Dashboard export | Static HTML/JSON | `reports/dashboard.*` |
| Secrets and credentials | `.env` + Gmail JSON | local files |

This works for a solo local tool, but it creates four real problems:

1. Candidate truth is fragmented across Markdown, JSON, env vars, and generated files.
2. Mutable runtime data still tends to leak into the repo layout.
3. The same business concept is often represented multiple ways.
4. There is no clean boundary between source-of-truth data and derived exports.

---

## Design Principles

The next architecture should follow these rules:

1. One canonical model for business data.
2. Relational data first, artifacts second, embeddings third.
3. Code stays in the repo. Personal data and runtime data live under `JOBPIPE_DATA_DIR`.
4. Structured records are the source of truth. Markdown, JSON exports, HTML, and DOCX are derived views.
5. Append-only history where it matters: runs, evaluations, application events, generated documents.
6. Keep artifact traceability. JobPipe should stay debuggable.
7. Do not introduce a dedicated vector database until the relational model is stable and the actual retrieval workload justifies it.

---

## Recommended Storage Strategy

### Short-term target

Use one local data root plus one primary relational database.

Recommended layout:

```text
JOBPIPE_DATA_DIR/
  db/
    jobpipe.sqlite
  candidate/
    profile_pack.md
    resume.json
  artifacts/
    runs/<run_id>/<job_id>/*.json
  documents/
    <candidate_id>/<job_id>/*
  exports/
    dashboard.html
    dashboard_data.json
    evaluations_latest.csv
  cache/
    profile_embedding.npy
  secrets/
    gmail_credentials.json
    gmail_token.json
```

### Source of truth by type

- Database: candidates, jobs, evaluations, application events, notes, document metadata, settings
- Filesystem: raw stage artifacts, generated DOCX/PDF/HTML, large exports
- `.env` or secret store: API keys and credentials only

### Long-term target

Keep the same logical model and move it to Postgres later if JobPipe becomes server-backed.

That means:

- SQLite now is the most natural consolidation layer
- Postgres or Supabase later is the most natural server layer
- pgvector later is the most natural embedding extension

This is intentionally not a “vector DB first” design. Most of JobPipe is workflow, state, traceability, filtering, deadlines, notes, and document history. That is relational work.

---

## Canonical Domain Objects

JobPipe should center around six business objects:

1. candidate
2. candidate profile
3. canonical job
4. job evaluation
5. application activity
6. generated document

Everything else is supporting metadata, cache, or export.

---

## 1. Candidate

Represents one job hunter.

This should exist even in a single-user install, because it is the cleanest path to future multi-user support.

### Required fields

| Field | Notes |
|---|---|
| `candidate_id` | Stable internal ID |
| `display_name` | Human-readable name |
| `email` | Optional for future notifications/login |
| `locale` | Example: `nb-NO` |
| `timezone` | Example: `Europe/Oslo` |
| `base_location` | Free-text current base |
| `seniority_label` | Example: `mid-senior` |
| `positioning_summary` | Compact professional positioning |
| `strategic_direction` | Current search direction |
| `is_active` | Active candidate flag |
| `created_at`, `updated_at` | Audit timestamps |

### Why this matters

Today “the user” is implicit. Making it explicit is the smallest change that keeps future growth sane.

---

## 2. Candidate Profile

This is the structured truth currently spread across `profile_pack.md`, `resume.json`, and some manual assumptions.

The profile should be versioned.

### Recommended shape

Use one active profile version per candidate, backed by structured JSON in the database and renderable back to `profile_pack.md`.

### Core fields

| Field | Notes |
|---|---|
| `profile_version_id` | Stable ID for one profile snapshot |
| `candidate_id` | Owner |
| `source_kind` | `manual_form`, `profile_pack_import`, `resume_import`, `agent_generated` |
| `profile_json` | Canonical structured content |
| `rendered_profile_pack_md` | Derived Markdown view for current pipeline compatibility |
| `resume_json_snapshot` | Optional embedded snapshot reference |
| `is_active` | Which version drives new scoring |
| `created_at`, `updated_at` | Audit timestamps |

### `profile_json` sections

The JSON document should contain:

- snapshot
- strategic_direction
- target_roles
- constraints
- geo_rules
- compensation_preferences
- positive_signals
- negative_signals
- evidence_bullets
- experience
- projects
- education
- language_profile
- application_style
- prompt_preferences

### Important rule

`profile_pack.md` should eventually become an export and import format, not the only truth source.

That preserves the current workflow while removing Markdown as the only system of record.

---

## 3. Canonical Job

Represents one deduplicated job opportunity regardless of where it was seen.

This should be separate from source-specific sightings.

### Recommended split

Use two layers:

1. `job_source_records`
2. `jobs`

### `job_source_records`

Append-only inbound sightings from NAV, FINN, LinkedIn, Gmail, and future sources.

| Field | Notes |
|---|---|
| `source_record_id` | Stable ID for the sighting |
| `source_name` | `nav`, `finn`, `linkedin_alert`, `gmail_suggestion`, etc. |
| `source_job_key` | Native source ID if present |
| `job_id` | Canonical job reference if deduplicated |
| `raw_payload_json` | Normalized raw intake payload |
| `seen_at` | When JobPipe ingested it |
| `is_active` | Source-level active flag |

### `jobs`

Latest normalized canonical job record.

| Field | Notes |
|---|---|
| `job_id` | Stable canonical ID |
| `dedupe_key` | Derived normalization key |
| `title` | Canonical title |
| `employer` | Canonical employer |
| `work_city`, `work_county`, `work_postal_code` | Normalized location |
| `source_url` | Best public listing URL |
| `application_url` | Best apply URL |
| `application_due` | Normalized date |
| `description_text` | Cleaned text form |
| `description_html` | Optional original HTML |
| `job_metadata_json` | Sector, employment type, extent, etc. |
| `first_seen_at`, `last_seen_at` | Lifecycle tracking |
| `closed_at` | Expired or removed |
| `content_hash` | Detect meaningful text changes |

### Important rule

All candidate-specific scoring must live outside `jobs`.

The same job may be evaluated differently for different candidates later.

---

## 4. Job Evaluation

Represents how one candidate was evaluated against one job in one pipeline run.

This is the heart of JobPipe.

### Recommended split

Use:

1. `pipeline_runs`
2. `job_evaluations`
3. optional `stage_artifacts`

### `pipeline_runs`

| Field | Notes |
|---|---|
| `run_id` | Stable run ID |
| `candidate_id` | Candidate evaluated in this run |
| `profile_version_id` | Which candidate profile was used |
| `config_version` | Pipeline config identity |
| `started_at`, `finished_at` | Runtime tracking |
| `source_batch_json` | Inputs, filters, or scheduler metadata |
| `status` | `running`, `completed`, `failed` |

### `job_evaluations`

One row per candidate x job x run.

| Field | Notes |
|---|---|
| `evaluation_id` | Stable ID |
| `run_id` | Run reference |
| `candidate_id` | Candidate evaluated |
| `job_id` | Canonical job |
| `triage_decision`, `triage_confidence`, `triage_explanation` | Triage output |
| `triage_signals_json` | Structured signals, not comma text |
| `reverse_decision`, `reverse_confidence`, `reverse_rationale` | Reverse triage output |
| `fit_score` | Profile match |
| `fit_dimensions_json` | Role/domain/seniority/skills breakdown |
| `pivot_score`, `pivot_type`, `pivot_risk` | Pivot output |
| `final_decision`, `final_confidence` | Moderator result |
| `recommendation_reason` | Human-facing explanation |
| `cv_focus_json` | Structured list |
| `feedback_flags_json` | Structured list |
| `skip_reason` | `geo`, `hard_no`, `semantic`, `triage_llm`, `fit_floor`, `moderate`, `passed` |
| `is_latest_for_candidate_job` | Convenient latest marker |
| `created_at` | Evaluation time |

### `stage_artifacts`

Metadata table pointing to raw files under `artifacts/runs/...`.

| Field | Notes |
|---|---|
| `artifact_id` | Stable ID |
| `run_id`, `job_id`, `candidate_id` | Ownership |
| `stage_name` | `input`, `triage`, `profile_match`, `pivot`, `moderator`, `application_pack` |
| `path` | Filesystem path |
| `content_hash` | Integrity/debugging |
| `created_at` | Timestamp |

### Why this matters

This keeps the current artifact-trace philosophy while giving the app a real queryable history model instead of relying on ad hoc file reads alone.

---

## 5. Application Activity

Represents everything that happens after a job becomes actionable.

The current `application_state.json` is useful, but it collapses timeline data into one mutable record.

The cleaner model is append-only events plus a derived summary.

### Recommended split

Use:

1. `application_events`
2. `application_summary`
3. optional `candidate_job_notes`

### `application_events`

| Field | Notes |
|---|---|
| `application_event_id` | Stable ID |
| `candidate_id` | Candidate |
| `job_id` | Job |
| `event_type` | `shortlisted`, `called`, `applied`, `interview`, `second_interview`, `accepted`, `rejected`, `dismissed`, `note_added` |
| `event_at` | When it happened |
| `source` | `manual`, `gmail_scan`, `dashboard`, `agent` |
| `notes` | Optional event note |
| `metadata_json` | Email subject, message IDs, external refs |
| `created_at` | Insert timestamp |

### `application_summary`

Derived latest status for fast UI use.

| Field | Notes |
|---|---|
| `candidate_id`, `job_id` | Composite key |
| `current_stage` | Latest non-terminal stage |
| `current_outcome` | Terminal outcome if any |
| `effective_status` | Backward-compatible simple status |
| `last_event_at` | Last change |
| `notes_latest` | Optional latest note preview |

### `candidate_job_notes`

Optional freeform notes separate from stage changes.

This is useful when the user wants working notes without mutating the official application timeline.

---

## 6. Generated Document

Represents any generated application material tied to a job and candidate.

This includes both JobPipe-generated materials and externally refined outputs.

### `generated_documents`

| Field | Notes |
|---|---|
| `document_id` | Stable ID |
| `candidate_id` | Owner |
| `job_id` | Job reference |
| `evaluation_id` | Optional evaluation that produced it |
| `kind` | `application_pack_json`, `cv_highlights_docx`, `cover_letter_md`, `cover_letter_docx`, `cv_pdf`, `external_final_upload` |
| `producer` | `jobpipe_pipeline`, `chatgpt`, `claude`, `manual`, `dashboard_server` |
| `status` | `draft`, `reviewed`, `final`, `archived` |
| `storage_path` | Filesystem path under `documents/` |
| `preview_text` | Small searchable excerpt |
| `document_json` | Optional structured payload for JSON artifacts |
| `created_at`, `updated_at` | Audit timestamps |

### Important rule

The database should store metadata and structured payloads.

Large binaries like DOCX and PDF should stay on disk.

---

## Optional Capability: Embeddings

Embeddings should be treated as a support layer, not the core architecture.

### Why

JobPipe’s hard problems are:

- job normalization
- candidate modeling
- evaluation history
- application status tracking
- generated document traceability

Those are not vector-database problems.

### Recommended model

Use one optional `embeddings` table later.

| Field | Notes |
|---|---|
| `embedding_id` | Stable ID |
| `owner_type` | `candidate_profile`, `job`, `document`, `profile_section` |
| `owner_id` | Entity reference |
| `chunk_key` | Optional section identifier |
| `model_name` | Embedding model |
| `text_hash` | Rebuild trigger |
| `vector` | SQLite blob now, pgvector later |
| `created_at` | Timestamp |

### Recommendation

- SQLite + file cache now is fine
- Postgres + pgvector later is the natural upgrade
- a separate vector database should be considered only if search scale or latency proves it necessary

---

## Recommended Physical Model for vNext

If we move from the current scattered files toward one cleaner store, the most practical next step is:

### One primary database

`JOBPIPE_DATA_DIR/db/jobpipe.sqlite`

### Files kept on disk

- run artifacts
- exported dashboard files
- generated CV and cover-letter documents
- Gmail credential files
- optional local caches

### Files that become derived compatibility views

- `profile_pack.md`
- `resume.json`
- `application_state.json`

These should remain usable during migration, but they should stop being the only truth source.

---

## Migration Roadmap

### Phase 1: Consolidate state without changing product behavior

Goal: one clean data root and one clearer system boundary.

Work:

- keep the existing pipeline and artifact model
- add database paths under `JOBPIPE_DATA_DIR/db/`
- define the canonical tables above in SQLite
- write import/sync code from:
  - `profile_pack.md`
  - `resume.json`
  - `application_state.json`
  - `jobpipe.sqlite`
- keep current CLI behavior intact

Success criteria:

- no repo-local personal data is required for normal use
- no business-critical state is stranded in one-off JSON files

### Phase 2: Make current sidecar files derived, not primary

Goal: stop duplicating truth by hand.

Work:

- store candidate profile as structured DB data
- render `profile_pack.md` from the active profile version
- store application events in DB
- generate `application_state.json` only for compatibility if needed
- store generated document metadata in DB

Success criteria:

- editing the candidate profile no longer requires manual synchronization across multiple files
- dashboard and status tools can rely on one canonical model

### Phase 3: Move runtime outputs fully under the data root

Goal: make the repo code-only.

Work:

- move `out_runs`, `reports`, and related exports under `JOBPIPE_DATA_DIR`
- keep repo-local defaults only as developer convenience
- add path helpers for runtime roots, not just personal data files

Success criteria:

- the repository can be recloned without carrying runtime history with it
- data backup is a matter of backing up one external folder

### Phase 4: Prepare the same model for server use

Goal: future-proof without overbuilding now.

Work:

- lift SQLite schema to Postgres when needed
- add auth-bound `candidate_id`
- add row-level isolation later if server-backed
- add pgvector only for the parts that truly need embeddings

Success criteria:

- the same domain model works for one user locally and multiple users later
- server migration is a storage migration, not a product rewrite

---

## What Not To Do Yet

1. Do not redesign JobPipe around a dedicated vector database.
2. Do not build a big settings UI before the profile model is stable.
3. Do not throw away artifact files; keep traceability.
4. Do not treat generated markdown, HTML, or DOCX as the source of truth.
5. Do not normalize everything to death. Keep the model clear, not academic.

---

## Immediate Next Steps

The most practical next implementation sequence is:

1. Add path helpers for a database root, document root, artifact root, and export root under `JOBPIPE_DATA_DIR`.
2. Define a first SQLite schema for:
   - `candidates`
   - `candidate_profiles`
   - `application_events`
   - `generated_documents`
3. Write a bootstrap/import CLI that imports current local files into that schema.
4. Keep `profile_pack.md` and `application_state.json` as compatibility exports during the transition.
5. Keep `reports/evaluations_latest.csv` only as a derived reporting export, not a second source of truth.

---

## Bottom Line

The most natural path for JobPipe is:

- one clean local data root
- one canonical relational model
- artifacts on disk
- generated documents on disk with metadata in the DB
- embeddings as an optional indexed capability, not the foundation

That keeps the app lean today and makes later Postgres or Supabase work straightforward without forcing a premature platform rewrite.
