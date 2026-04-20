# JobPipe

AI-assisted job hunting pipeline for Lars Værland. It ingests listings from NAV and FINN-related sources, runs a staged filter and scoring pipeline, writes per-job JSON artifacts, syncs the latest state into SQLite, and exports a dashboard for daily decision-making.

Core thesis:

- the product value is the job-ad data pipeline
- the system should remove cognitive noise before the user starts spending effort
- the user should spend time on review, tailoring, applying, and follow-up, not on feed scanning and repetitive context gathering

```powershell
.\go.ps1
```

## What Is Running Today

```text
NAV pam-stilling-feed
    ↓ Apps Script / Sheet bridge
Google Sheet
    ↓ pull_sheets_csv.py
NAV connector output

Gmail recommendation emails
    ↓ scan_gmail --scan-suggestions
suggested_jobs.jsonl
    ↓ sync_mailbox_leads / pull_suggested
suggested-lead connector output

NAV connector output + suggested-lead connector output
    ↓ shared intake merge + dedupe
<data-root>/jobs_delta.jsonl
    ↓ run_feed.py
    [NAV] Geo filter
    [NAV] Hard-no title regex
    [NAV] Semantic pre-filter
    [SUGGESTED] Hard-no title regex only
    [NANO] Triage
    [MINI] Parse
    [MINI] Profile match
    [MINI] Pivot
    [FREE] Moderate
    [MINI] Application pack
    ↓
<data-root>/out_runs/<run_id>/<job_id>/
    ↓ sync_ledger.py
<data-root>/reports/ledger.sqlite
    ↓ export_dashboard.py
<data-root>/exports/dashboard.html
```

The core rule is unchanged throughout the repo: cheap filters run before any LLM call.

Connector policy:
- `NAV` is the broad canonical feed and goes through the normal deterministic gate stack
- mailbox/platform-suggested leads are separate connectors until the shared intake merge point
- dedupe happens before the rest of the pipeline sees the merged jobs
- `NAV` is the pragmatic canonical source when duplicates collide unless the suggested-lead variant is the only record with materially missing fields filled in
- mailbox/platform-suggested leads bypass `geo` and semantic pre-filter elimination, but hard-no title blocking still applies

## Local Data Root

Private user data now lives outside the git worktree by default.

- Windows: `~/JobpipeData`
- macOS: `~/Library/Application Support/JobPipe`
- Linux: `$XDG_DATA_HOME/jobpipe` or `~/.local/share/jobpipe`
- Override anywhere with `JOBPIPE_DATA_ROOT`

This data root holds local state such as `.env`, `profile_pack.md`, `resume.json`, Gmail credentials/tokens, `jobs_state.json`, `jobs_delta.jsonl`, `out_runs/`, `reports/ledger.sqlite`, and the exported dashboard. The repo keeps code, templates, configs, and docs.

## Quick Start

Requirements:
- Python 3.11+
- `.venv` with project dependencies installed
- `OPENAI_API_KEY` in the data-root `.env`
- Google Sheet CSV access for the NAV feed

Run the standard flows:

```powershell
.\go.ps1
.\go.ps1 -DryRun
.\go.ps1 -NoOpen
```

Useful direct commands:

```powershell
.venv\Scripts\python.exe compile_check.py
.venv\Scripts\python.exe -m pytest tests -q
.venv\Scripts\python.exe -m jobpipe.cli.check_companion_revisions --strict
.venv\Scripts\python.exe -m jobpipe.cli.sync_mailbox_leads --dry-run
.venv\Scripts\python.exe -m jobpipe.cli.sync_ledger
.venv\Scripts\python.exe -m jobpipe.cli.export_dashboard
start $HOME\JobpipeData\exports\dashboard.html
```

## Dashboard Modes

Two supported dashboard modes exist, but they now share one payload contract and the same tracked template:

1. `<data-root>/exports/dashboard.html`
   Static self-contained export from SQLite. Read-only.
2. `python -m jobpipe.cli.dashboard_server`
   Local interactive mode for direct status updates, notes, CV-builder draft persistence, a sidebar app shell, automation actions, and application-workspace flows.

Both modes now render from the canonical `build_payload()` output in `jobpipe/cli/export_dashboard.py`.

## Companion Projects

The current target stack is:

- `JobPipe` as control plane for setup, profile source data, ingestion, triage review, and sync health
- `JobSync` as the long-term operator workspace for active applications, notes, tasks, and day-to-day status work
- `Reactive Resume` as the structured resume system and tailored CV authoring/export surface, linked back to jobs rather than merged into the JobPipe UI
- a separate `NAV Google Apps Script` project as the feed bridge between NAV/Google Sheets and JobPipe

Source-of-truth split:
- `JobPipe` owns intake, scoring, packet generation, artifacts, and calibration history
- `JobSync` owns active application-case workflow after promotion
- `Reactive Resume` owns resume structure and CV variant/export truth

The current JobPipe local shell is therefore a control-plane surface, not the intended final day-to-day operator shell.

This split is documented in:

- `docs/architecture-plan.md`
- `docs/mvp-task-plan.md`
- `DASHBOARD_SPEC.md`

### Maintenance Strategy

Do **not** vendor `JobSync`, `Reactive Resume`, or the NAV Google Apps Script into this repo.

For easiest maintenance:

1. keep `agentic_jobpilot` as its own git repo
2. keep `jobsync` as its own git repo or deployment directory
3. keep `reactive-resume` as its own deployment directory, and only clone the source repo if you intend to modify it
4. keep the NAV Apps Script in its own git repo so Sheet/API code does not leak into the JobPipe repo
5. record sibling-repo revisions in `COMPANION_REVISIONS.json` when a JobPipe checkpoint depends on local integration state

This is the normal developer setup for multi-project local stacks: separate repos or stack directories under one parent folder, not one repo containing all upstream codebases.

Recommended local layout:

```text
<workspace-root>\
  agentic_jobpilot\
  jobsync\
  reactive-resume\
  nav-jobpipe-sheet-sync\
  stacks\
    jobsync-local\
    reactive-resume-local\
```

This is the standard polyrepo pattern:

- one parent workspace folder
- one repo per codebase you may modify
- optional stack folders for Compose files, env files, and persistent volumes

That keeps upstream updates and local fixes attributable to the correct project.

### Boundary Rules During Development

Use these rules so the projects do not pollute each other:

1. `agentic_jobpilot`
   - Python pipeline, dashboard/control-plane UI, local data-root contract, integration docs
   - no checked-in Next.js app code from JobSync
   - no checked-in Docker stack from Reactive Resume
   - no checked-in Apps Script source except interface docs or sample payload specs
2. `jobsync`
   - operator workspace UI and its own backend/runtime
   - no copies of JobPipe pipeline code
   - no copies of NAV Apps Script logic
3. `reactive-resume`
   - CV builder/runtime only
   - no job-ingestion or pipeline code
4. `nav-jobpipe-sheet-sync`
   - Apps Script, NAV fetch logic, Sheet write logic, install/setup notes for that bridge
   - no JobPipe private data, no JobSync code

The integration seam between repos should be files, payload contracts, and HTTP endpoints, not copied modules.

When local sibling changes are needed, checkpoint them in the sibling repo first, then update `COMPANION_REVISIONS.json` in JobPipe to record the aligned SHAs. That keeps the stack auditable without turning JobPipe into a vendor repo.

### Recommended Local Install Order

Install and validate the stack one project at a time:

1. `JobPipe`
   - keep this repo under your normal workspace root, for example `<workspace-root>\agentic_jobpilot`
   - validate the current local runtime first:
     - `.\go.ps1`
     - `python -m jobpipe.cli.dashboard_server`
   - confirm:
     - `http://127.0.0.1:5100/`
     - `<data-root>/exports/dashboard.html`
2. `JobSync`
   - install separately
   - validate its own login and local DB before thinking about integration
   - confirm:
     - `http://localhost:3737`
3. `Reactive Resume`
   - install separately
   - validate resume create/import/export before linking it to jobs
   - confirm:
     - `http://localhost:3000`
4. `NAV Apps Script`
   - keep as a separate repo after the local apps are stable
   - validate the script against its target Sheet and NAV endpoint independently of JobPipe

Do not start by wiring all four together. Get each one running on its own first.

### JobSync Installation

The official JobSync repo README and bundled compose file support a simple Docker deployment:

- clone the repo
- run `docker compose up`
- open `http://localhost:3737`

Relevant upstream references:

- `https://github.com/Gsync/jobsync`

Grounded details from the upstream README and bundled compose:

- port: `3737`
- runtime: Docker image `ghcr.io/gsync/jobsync:latest`
- local DB path in the container: `file:/data/dev.db`
- persistent volume in the sample compose: `./jobsyncdb/data:/data`
- important env knobs:
  - `NEXTAUTH_URL`
  - `AUTH_SECRET`
  - `ENCRYPTION_KEY`
  - `TZ`
  - optional AI keys such as `OPENAI_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `OPENROUTER_API_KEY`, `RAPIDAPI_KEY`

For this project, treat JobSync as a **separate codebase**:

- if you plan to customize JobSync UI or add JobPipe integration endpoints, clone it as a sibling repo
- if you only want to run stock JobSync, keep its compose/env/data in a separate deployment folder under `stacks/`

The official upstream quickstart is clone + compose. The maintainable local pattern is still separate from this repo.

### Reactive Resume Installation

Reactive Resume officially supports:

- cloud use
- self-hosting with Docker
- JSON import/export

Relevant upstream references:

- `https://github.com/AmruthPillai/Reactive-Resume`
- `https://docs.rxresume.org/self-hosting/docker`
- `https://docs.rxresume.org/guides/json-resume-schema`

Grounded details from the official self-hosting docs:

- default app URL example: `http://localhost:3000`
- required services in the documented Compose setup:
  - Reactive Resume app
  - PostgreSQL
  - printer service for PDF/screenshots
- required env vars:
  - `APP_URL`
  - `DATABASE_URL`
  - `PRINTER_ENDPOINT`
  - `AUTH_SECRET`
- optional but documented:
  - Google/GitHub OAuth
  - SMTP
  - S3-compatible storage

For easiest maintenance, prefer a **standalone deployment folder** for Reactive Resume unless you need to patch the code:

1. create a folder with `compose.yml`, `.env`, and a persistent data directory
2. run Docker Compose there
3. keep JobPipe linked to Reactive Resume by resume IDs/URLs or imported JSON, not by copying its source into this repo

Reactive Resume is currently best treated as a CV tool, not as part of the main JobPipe runtime.

### Repository Choice Rules

Use these rules to decide whether the companion projects belong as repos or just runtime folders on your machine:

1. `JobSync`
   - clone the repo if you will add custom endpoints, status sync, or UI changes
   - otherwise a deployment folder is enough
2. `Reactive Resume`
   - use a deployment folder by default
   - clone the repo only if you intend to patch its source or build deeper automation against its internals
3. `NAV Google Apps Script`
   - keep it as a separate repo by default
   - it is integration code, not JobPipe runtime code

For your current direction, the cleanest setup is:

- `agentic_jobpilot` as a repo
- `jobsync` as a sibling repo
- `reactive-resume-local` as a deployment folder, not necessarily a source repo
- `nav-jobpipe-sheet-sync` as a sibling repo for Apps Script and Sheet setup

That is how developers usually keep maintenance simple in a small multi-app local stack.

### Future Container Note

Later, once the JobPipe integration contracts are stable, it likely makes sense to containerize JobPipe too.

Not yet:

- JobPipe still has evolving module boundaries
- Gmail auth and local-first file handling are still operator-centric

Later target:

- one `jobpipe` container
- mounted external `JOBPIPE_DATA_ROOT`
- explicit env contract
- explicit port for the local server/API

Containerizing JobPipe should preserve the existing data-root boundary in `jobpipe/core/paths.py`, not move private state into the container filesystem.

## Smoke Test

Use this after dashboard/export/server changes:

```powershell
.venv\Scripts\python.exe compile_check.py
.venv\Scripts\python.exe -m pytest tests -q
.venv\Scripts\python.exe -m jobpipe.cli.check_companion_revisions --strict
.venv\Scripts\python.exe -m jobpipe.cli.export_dashboard
.venv\Scripts\python.exe -m jobpipe.cli.dashboard_server --no-open
```

Manual checks:
- open `http://127.0.0.1:5100/`
- confirm `/api/data` loads
- confirm a note save or CV-draft save survives refresh in local mode
- rebuild `<data-root>/exports/dashboard.html` and confirm the static export still opens cleanly

## Core Docs

- [CLAUDE.md](./CLAUDE.md)
- [PRODUCT_VISION.md](./PRODUCT_VISION.md)
- [docs/architecture-plan.md](./docs/architecture-plan.md)
- [docs/mvp-task-plan.md](./docs/mvp-task-plan.md)
- [DASHBOARD_SPEC.md](./DASHBOARD_SPEC.md)

Local operational docs, intentionally kept out of git for privacy:

- `AGENT_STATUS.md`
- `AUDIT.md`

## Documentation Discipline

This repo should stay on a small canonical doc set. Do not create ad hoc dated audits, loose research dumps, duplicate agent guides, or extra "next steps" files when the information belongs in an existing source of truth.

Use these files instead:

- `README.md`: repo entrypoint and operator quickstart
- `CLAUDE.md`: operating rules and workflow guardrails
- `PRODUCT_VISION.md`: product goals and roadmap
- `docs/architecture-plan.md`: architecture and red-line contract
- `docs/mvp-task-plan.md`: one ordered execution plan
- `DASHBOARD_SPEC.md`: dashboard and payload contract

Local-only operational docs:

- `AGENT_STATUS.md`: current state, handoffs, cross-agent requests
- `AUDIT.md`: bugs, quality issues, and audit history

Those two files are intentionally gitignored because they may contain private operational notes and local-environment details.

Specialized docs are allowed only when they map to a concrete subsystem with durable operational value, for example `APPS_SCRIPT_CHANGES.md` or `docs/gmail_filter_spec.md`.

### Planning structure

The project works best when the docs are treated as different layers instead of one blended planning blob:

- `PRODUCT_VISION.md`
  - product north star
  - design principles
  - long-term roadmap
- `docs/architecture-plan.md`
  - boundaries
  - ownership
  - integration rules
- `docs/mvp-task-plan.md`
  - ordered short-term execution topics
  - one active topic at a time
- `AUDIT.md`
  - local operational defect/debt log
- `AGENT_STATUS.md`
  - local operational state and handoffs

This split is the preferred product-management structure for the repo. It keeps strategy, execution, and defect tracking separate enough that work does not drift.

## Current Focus

The current project direction is:
- preserve the red line from source data to decision to dashboard
- keep the companion stack auditable through pinned sibling revisions plus a local drift check
- keep the local-first data boundary consistent across runtime, docs, and versioning
- keep the OSS track portable and valuable without hosted infrastructure
- define the next execution arc around daily run reliability, the profile/person-model spine, and the application-pack rewrite

## Historical Note

Earlier Supabase-first and backend-heavy planning docs are not the active architecture anymore. The current repo is the file-based `jobpipe/` pipeline described above. Historical notes are kept only for reference.
