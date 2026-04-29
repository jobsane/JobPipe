# Public Loop Test How-To

Last updated: 2026-04-20

Purpose:
- give one honest manual validation path for the current public JobPipe loop
- define what success looks like at each step
- define what is not successful so failures do not get hand-waved away

This how-to matches the current `Jobpipe` repo shape:
- canonical CLI: `jobpipe` or `python -m jobpipe.cli.main`
- primary state: the primary DB
- dashboard validation: static export
- no `dashboard_server` dependency

## What this test proves

Canonical bounded smoke command for this repo:

```powershell
.venv\Scripts\python.exe -m jobpipe.cli.main run --dry-run --no-open
```

This command is the single best local smoke entrypoint because it exercises the
canonical CLI run loop while keeping the path bounded and browser-free.

This test is for the current public local-first loop:

1. the CLI starts
2. the dry-run workflow completes
3. the primary DB and export paths are usable
4. the dashboard export can be rebuilt and opened
5. the repo is behaving like the current docs describe, not like a different worktree

This test does not prove:
- full Gmail setup
- live mailbox ingestion
- live persona-audit matrix completion
- any browser-served dashboard app flow

## Preconditions

Before you start:

1. Make sure you are in the real repo.
   Success:
   - current working directory is `C:\Users\larsv\Jobpipe`
   Not successful:
   - you are in another worktree and the commands/docs do not match the code

2. Check repo state.
   Commands:

   ```powershell
   git status --short
   git branch --show-current
   ```

   Success:
   - you understand whether the tree is clean or dirty
   - you know which branch you are testing
   Not successful:
   - you cannot tell whether you are testing active sprint work or unrelated drift

3. Confirm baseline setup exists.
   Success:
   - `.venv` exists
   - `.env` exists or required environment variables are otherwise available
   - the package imports from the current repo
   Not successful:
   - Python cannot import `jobpipe`
   - required local setup is obviously missing

## Recommended command form

For reproducible local testing from the repo root, use:

```powershell
.venv\Scripts\python.exe -m jobpipe.cli.main ...
```

The `jobpipe ...` console script is the canonical interface, but the module form is the safest way to verify the local checkout specifically.

## Step-by-step test

### Step 1. Confirm the CLI surface exists

Run:

```powershell
.venv\Scripts\python.exe -m jobpipe.cli.main --help
```

Success:
- help text prints
- top-level commands include `run`, `export-dashboard`, `inspect-db`, `sync-evaluations`

Not successful:
- Python cannot import `jobpipe.cli.main`
- the CLI surface is missing or crashes before help output

### Step 2. Confirm the repo parses cleanly

Run:

```powershell
.venv\Scripts\python.exe compile_check.py
```

Success:
- compile check completes without parse errors

Not successful:
- syntax or import-level parsing errors appear

### Step 3. Run the canonical dry-run smoke path

Run:

```powershell
.venv\Scripts\python.exe -m jobpipe.cli.main run --dry-run --no-open
```

Success:
- the command completes without crashing
- the workflow reaches the normal sync/export path
- in current JobPipe, `--dry-run` is a bounded local smoke path:
  - it skips live sheet intake
  - it processes at most two already-queued jobs if a local delta exists
- `--no-open` keeps the smoke path browser-free and scriptable
- zero jobs processed is acceptable if the local queue is empty

Not successful:
- the command aborts with an exception
- required paths or configuration are missing in a way the docs do not explain
- the run cannot reach the export step

### Step 4. Rebuild the dashboard export directly

Run:

```powershell
.venv\Scripts\python.exe -m jobpipe.cli.main export-dashboard --candidate-id default
```

Success:
- the command prints an output path
- the dashboard export file is written successfully
- the command can read the current primary DB state

Not successful:
- export crashes
- export cannot find the DB or artifacts it expects
- export writes an obviously wrong or empty output without explanation

### Step 5. Inspect the primary DB summary

Run:

```powershell
.venv\Scripts\python.exe -m jobpipe.cli.main inspect-db --show summary --show applications
```

Success:
- summary output prints
- the DB can be read without schema/runtime errors
- application summary output is coherent with the current local state

Not successful:
- DB inspection crashes
- schema mismatch errors appear
- the DB cannot be opened from the documented runtime path

### Step 6. Open the exported dashboard manually

Open the file printed by Step 4.

Expected default path in a normal local setup:
- `C:\Users\larsv\JobpipeData\exports\dashboard.html`

Success:
- the file opens in a browser
- the main dashboard shell renders
- actionable counts and queue rows display instead of a broken blank page

Not successful:
- the file does not exist after export said it succeeded
- the browser shows a broken page or unusable script errors
- the dashboard clearly contradicts the exported local state

### Step 7. Verify the test matched the current repo shape

Check the result against current docs:
- `run --dry-run --no-open` is the canonical bounded smoke command
- static export is the dashboard validation path
- the primary DB is the system of record
- `jobpipe.cli.main` is the canonical CLI surface

Success:
- the commands you just used match `TESTING.md`, `docs/cli.md`, `docs/dashboard.md`, and `docs/configuration.md`

Not successful:
- you had to switch to undocumented commands from another repo
- you had to use `jobpipe.cli.dashboard_server` or other non-existent surfaces to complete the test

## Optional deeper checks

Use these only if they are relevant to the current slice.

### Persona-audit freeze check

Run:

```powershell
.venv\Scripts\python.exe -m jobpipe.cli.persona_audit --freeze-only
```

Success:
- a frozen local audit baseline is created without mutating the normal candidate state unexpectedly

Not successful:
- the command mutates the normal runtime state in undocumented ways
- persona-audit setup fails before it can freeze the baseline

### Thin companion projection check

Run:

```powershell
.venv\Scripts\python.exe -m jobpipe.cli.main export-jobsync --candidate-id default
.venv\Scripts\python.exe -m jobpipe.cli.main export-reactive-resume-plan JOB_ID
```

Success:
- thin projection commands run as documented
- projection output is generated without pretending those sibling tools are the source of truth

Not successful:
- the commands are missing
- they require undocumented repo coupling to work at all

## Stop conditions

Stop and record the blocker if:
- repo state is too unclear to classify
- the CLI help command fails
- compile check fails
- the dry-run smoke path crashes
- export fails
- the only way to continue is to use commands from another worktree or outdated docs

That result is still useful. It means the current branch needs alignment or a bounded fix before broader work continues.
