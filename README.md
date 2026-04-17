# JobPipe

AI-assisted job hunting pipeline for Lars Værland. It ingests listings from NAV and FINN-related sources, runs a staged filter and scoring pipeline, writes per-job JSON artifacts, syncs the latest state into SQLite, and exports a dashboard for daily decision-making.

```powershell
.\go.ps1
```

## What Is Running Today

```text
NAV pam-stilling-feed + FINN leads
    ↓ Apps Script / pull scripts
Google Sheet / JSONL delta
    ↓ pull_sheets_csv.py
<data-root>/jobs_delta.jsonl
    ↓ run_feed.py
    [FREE] Geo filter
    [FREE] Hard-no title regex
    [FREE] Semantic pre-filter
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
.venv\Scripts\python.exe -m jobpipe.cli.sync_ledger
.venv\Scripts\python.exe -m jobpipe.cli.export_dashboard
start $HOME\JobpipeData\exports\dashboard.html
```

## Dashboard Modes

Two supported dashboard modes exist, but they now share one payload contract and the same tracked template:

1. `<data-root>/exports/dashboard.html`
   Static self-contained export from SQLite. Read-only.
2. `python -m jobpipe.cli.dashboard_server`
   Local interactive mode for direct status updates, notes, CV-builder draft persistence, and application-workspace flows.

Both modes now render from the canonical `build_payload()` output in `jobpipe/cli/export_dashboard.py`.

## Smoke Test

Use this after dashboard/export/server changes:

```powershell
.venv\Scripts\python.exe compile_check.py
.venv\Scripts\python.exe -m pytest tests -q
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
- [AGENT_STATUS.md](./AGENT_STATUS.md)
- [AUDIT.md](./AUDIT.md)
- [docs/architecture-plan.md](./docs/architecture-plan.md)
- [docs/mvp-task-plan.md](./docs/mvp-task-plan.md)
- [DASHBOARD_SPEC.md](./DASHBOARD_SPEC.md)

## Documentation Discipline

This repo should stay on a small canonical doc set. Do not create ad hoc dated audits, loose research dumps, duplicate agent guides, or extra "next steps" files when the information belongs in an existing source of truth.

Use these files instead:

- `README.md`: repo entrypoint and operator quickstart
- `CLAUDE.md`: operating rules and workflow guardrails
- `AGENT_STATUS.md`: current state, handoffs, cross-agent requests
- `AUDIT.md`: bugs, quality issues, and audit history
- `PRODUCT_VISION.md`: product goals and roadmap
- `docs/architecture-plan.md`: architecture and red-line contract
- `docs/mvp-task-plan.md`: one ordered execution plan
- `DASHBOARD_SPEC.md`: dashboard and payload contract

Specialized docs are allowed only when they map to a concrete subsystem with durable operational value, for example `APPS_SCRIPT_CHANGES.md` or `docs/gmail_filter_spec.md`.

## Current Focus

The current project direction is:
- preserve the red line from source data to decision to dashboard
- keep the dashboard contract hardened and truthful under live updates
- keep the local-first data boundary consistent across runtime, docs, and versioning
- keep the OSS track portable and valuable without hosted infrastructure
- clean the repo surface before commit so only intentional first-class assets remain

## Historical Note

Earlier Supabase-first and backend-heavy planning docs are not the active architecture anymore. The current repo is the file-based `jobpipe/` pipeline described above. Historical notes are kept only for reference.
