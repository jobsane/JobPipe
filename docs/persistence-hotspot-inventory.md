# Persistence Hotspot Inventory

Maps every place in the Jobpipe codebase that directly reads/writes SQLite, JSON state files, artifact files, or status files — grouped by domain. Research only; no code changes.

Supports #163 (persistence seam contracts) and #164 (event ingestion seam).

---

## 1. Jobs

Intake, upsert, triage, and catalog reads.

| File | Line(s) | Access | Notes |
|------|---------|--------|-------|
| `jobpipe/cli/run_feed.py` | 173 | `connect_primary_db` | Main intake path — evaluation/triage write |
| `jobpipe/cli/drain_queue.py` | 40 | `sqlite3.connect` (direct) | Orchestrates run_feed artifact writes; jobs/triage write |
| `jobpipe/cli/pull_sheets_csv.py` | 367 | `connect_primary_db` | Job upsert from Google Sheets |
| `jobpipe/cli/pull_suggested.py` | 127, 591 | `connect_primary_db` | Suggestion lead read/write |
| `jobpipe/runtime/catalog.py` | 448 | `sqlite3.connect` (direct) | Job catalog read |

---

## 2. Evaluations

Scoring/decisioning writes and reads.

| File | Line(s) | Access | Notes |
|------|---------|--------|-------|
| `jobpipe/cli/run_feed.py` | 173 | `connect_primary_db` | Evaluation write (also in jobs domain — dual role) |
| `jobpipe/cli/sync_evaluations.py` | 522 | `connect_primary_db` | Evaluation sync write |
| `jobpipe/core/evaluation_state.py` | 13 | `sqlite3.connect` (direct) | Evaluation state read/write |

---

## 3. Applications

Application pack, status, and lifecycle.

| File | Line(s) | Access | Notes |
|------|---------|--------|-------|
| `jobpipe/stages/application_pack.py` | 330 | `connect_primary_db` | Generated document write |
| `jobpipe/cli/mark_status.py` | 187 | `connect_primary_db` | Status write; reads/writes application_state.json via primary_db |
| `jobpipe/authoring/author_cli.py` | 71 | `connect_primary_db` | Application pack write |

---

## 4. Artifacts

JSON/JSONL stage outputs per job written to `out_runs/`.

| File | Notes |
|------|-------|
| `jobpipe/cli/run_feed.py` | Writes stage JSON artifacts per job |
| `jobpipe/cli/sync_evaluations.py` | Writes evaluation artifacts |
| `jobpipe/cli/drain_queue.py` | Orchestrates run_feed artifact writes |
| `jobpipe/authoring/author_cli.py` | Writes application pack artifacts |
| `jobpipe/cli/export_jobsync.py` | Writes jobsync export file |
| `jobpipe/cli/export_reactive_resume_plan.py` | Writes Reactive Resume plan file |
| `jobpipe/core/io.py` | Shared write helpers (`write_jsonl_lines`, `write_text`) |

---

## 5. Profile / Candidate

Candidate profile, resume, and profile_pack.

| File | Line(s) | Access | Notes |
|------|---------|--------|-------|
| `jobpipe/core/candidate_data.py` | 36 | `sqlite3.connect` (direct) | Profile read |
| `jobpipe/cli/bootstrap_state_db.py` | 163 | `connect_primary_db` | Setup/migration |
| `jobpipe/cli/import_reactive_resume.py` | 80 | `connect_primary_db` | Profile/CV import |

---

## 6. Email / Source Events

Gmail scan, suggestion leads, and feedback.

| File | Line(s) | Access | Notes |
|------|---------|--------|-------|
| `jobpipe/cli/scan_gmail.py` | 491, 578, 705 | `connect_primary_db` | Email/suggestion write |
| `jobpipe/cli/pull_suggested.py` | 127, 591 | `connect_primary_db` | Suggestion lead read/write (also in jobs domain) |
| `jobpipe/cli/record_feedback.py` | 68 | `connect_primary_db` | Feedback write |

---

## 7. Projections / Exports

Dashboard, jobsync export, Reactive Resume plan, gap report.

| File | Line(s) | Access | Notes |
|------|---------|--------|-------|
| `jobpipe/projections/dashboard.py` | 189, 276, 322, 357, 391, 468, 865 | `sqlite3.connect` (direct ×7) | Read-only projections; writes dashboard.html |
| `jobpipe/runtime/jobsync.py` | 59 | `connect_primary_db` | Jobsync export read |
| `jobpipe/runtime/reactive_resume.py` | 19 | `connect_primary_db` | Reactive Resume document write |
| `jobpipe/cli/export_jobsync.py` | — | artifact write | Writes jobsync export file |
| `jobpipe/cli/export_reactive_resume_plan.py` | — | artifact write | Writes RR plan file |
| `jobpipe/cli/gap_analysis_report.py` | 61 | `connect_primary_db` | Gap analysis read; writes gap analysis report |

---

## 8. Audit / Tooling

Persona audit, db inspection, runtime reset.

| File | Line(s) | Access | Notes |
|------|---------|--------|-------|
| `jobpipe/cli/persona_audit.py` | 192 | `sqlite3.connect` (direct) | Audit read — bypasses `connect_primary_db` |
| `jobpipe/cli/persona_audit.py` | 284 | `connect_primary_db` | Audit db copy write |
| `jobpipe/cli/inspect_primary_db.py` | 52 | `connect_primary_db` | Inspection read |
| `jobpipe/cli/reset_runtime.py` | — | state files | Deletes/resets state files |
| `jobpipe/cli/refresh_runtime_state.py` | — | state files | Rebuilds runtime state |

---

## Critical Path Hotspots

These modules block the primary NAV → Finn.no → triage → JobSync → apply flow. Any persistence seam introduction must not break these callers.

| File | Role | Access type |
|------|------|-------------|
| `jobpipe/cli/run_feed.py` | Evaluation write — must work for intake to complete | `connect_primary_db` |
| `jobpipe/cli/sync_evaluations.py` | Evaluation sync — required before apply queue is populated | `connect_primary_db` |
| `jobpipe/cli/drain_queue.py` | Orchestrates intake — drives run_feed | `sqlite3.connect` (direct) |
| `jobpipe/stages/application_pack.py` | Application pack write — required before Apply Workbench | `connect_primary_db` |
| `jobpipe/cli/mark_status.py` | Status write — lifecycle tracking | `connect_primary_db` |
| `jobpipe/cli/export_jobsync.py` | JobSync export — candidate-facing apply queue | artifact write |

---

## Summary Counts

| Access type | Count |
|-------------|-------|
| `sqlite3.connect` direct | 9 call sites across 5 files |
| Via `connect_primary_db` | ~20 call sites across 16 files |
| Artifact file writes (JSON/JSONL) | 7 files |
| State file reads/writes/deletes | 3 files |
