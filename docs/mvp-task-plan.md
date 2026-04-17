# Topic-By-Topic Task Plan

Last updated: 2026-04-18

This is the only active execution-order plan. Do not create separate "next steps" or parallel plan files; update this one.

Rule: finish one topic completely before starting the next. Each topic ends with validation and documentation updates.

## Topic 1. Documentation And Contracts

Status: done on 2026-04-17

Scope:
- reconcile repo docs with the actual `jobpipe/` pipeline
- audit dashboard/data-flow documentation
- write the current architecture and full audit down in one place

Exit criteria:
- README reflects the real system
- stale Supabase-first planning is removed from active docs
- dashboard/data contract is documented
- shared audit/status docs updated

## Topic 2. Data Carry-Through Contract

Status: done on 2026-04-17

Scope:
- define the exact field matrix from source input to artifacts to ledger to dashboard payload
- stop dropping useful fields without intent
- make `skip_reason` authoritative in the UI

Implementation targets:
- extend `sync_ledger.py` with explicit carry-through for source/taxonomy/application-pack summary fields
- export thresholds and config snapshot from `export_dashboard.py`
- add payload-level schema versioning
- remove guesswork from dashboard classification

Validation:
- automated assertions for field completeness on representative fixtures
- at least one test file covering `sync_ledger.py` and one covering `export_dashboard.py`

## Topic 3. Dashboard Runtime Unification

Status: done on 2026-04-17

Scope:
- stop treating the dashboard as half static report, half local app
- unify `dashboard.html`, `dashboard_server.py`, and payload building

Implementation targets:
- one canonical `build_payload()` contract for both modes
- fix stale artifact filename assumptions in server mode
- serve the dashboard through the local server without changing the UI contract
- keep static export as a supported read-only mode

Validation:
- manual smoke test in both modes
- server mode can read latest artifacts and application pack correctly

## Topic 4. Information Architecture And Pages

Status: done on 2026-04-17

Scope:
- make the dashboard answer "what do I do now?"
- add the missing profile/CV surface

Target pages:
1. Jobs
2. Pipeline
3. Profile & CV
4. Application Workspace
5. Debug / Data

Validation:
- top navigation matches page model
- profile/CV page renders from tracked source data, not hardcoded text
- no page depends on undocumented side files

## Topic 5. Interaction And Dynamic Data

Status: done on 2026-04-18

Scope:
- remove clunky workflows
- tighten queue behavior and make local editing/state less fragile

Implementation targets:
- dedupe or group duplicate-style postings in the queue
- persist local CV-builder/workspace state more intentionally than browser-local draft only
- keep pack/status/note changes reflected immediately in local app mode
- make deadlines, badges, and counters stay truthful after live updates

Validation:
- duplicate-style rows are meaningfully reduced or grouped
- local builder/workspace state survives refresh in a controlled way
- counters and charts match the active payload after updates

## Topic 6. Performance, Testing, And Hardening

Status: done on 2026-04-18

Scope:
- lock the contract down after the data/runtime redesign

Implementation targets:
- payload-size budget and pruning rules
- dashboard contract tests
- dashboard-server state tests for local notes/profile draft persistence
- end-to-end fixture run from input JSONL to payload
- documented smoke-test commands

Validation:
- `compile_check.py`
- `pytest`
- one fixture-based dashboard payload test
- one server-side local-state persistence test
- one manual rebuild + open pass

## Topic 7. Local-First Data Boundary And Portability

Status: done on 2026-04-18

Scope:
- separate versioned code from private user data cleanly
- make the OSS version portable, local-first, and platform agnostic
- define the boundary between single-user OSS mode and future hosted multi-user mode

Implementation targets:
- define one canonical user data root outside the git worktree
- move credentials, tokens, profile/CV files, ledgers, app state, caches, artifacts, and exports behind that path contract
- add path resolution rules for Windows, macOS, and Linux
- make repo checkouts and branch switches reuse the same private data without re-auth or re-entry
- document what belongs in OSS local storage vs. hosted private infrastructure

Validation:
- a fresh clone can attach to an existing local data root without Gmail re-setup
- repo deletion or branch switching does not destroy private state
- bootstrap and backup/restore steps are documented in one canonical place

Outcomes:
- canonical data-root path rules now exist for Windows, macOS, Linux, and `JOBPIPE_DATA_ROOT`
- active CLI/runtime commands bootstrap legacy repo-local private data into the external data root
- dashboard export now defaults to `<data-root>/exports/dashboard.html`
- direct validation passed for `sync_ledger`, `export_dashboard`, and `dashboard_server`

## Topic 8. Tree Cleanup, Version-Safe Repo Surface, And Commit Prep

Status: done on 2026-04-18

Scope:
- remove leftover repo noise from the dashboard/portability work
- make the canonical docs and plan files match the active runtime
- classify which local files are first-class project assets versus private/local-only material

Implementation targets:
- correct repo-local path drift in the canonical docs
- document the cleanup topic in the execution plan before commit
- keep personal calibration material out of accidental git churn
- confirm which untracked files are real product assets that should be promoted during commit prep

Validation:
- `compile_check.py`
- `pytest`
- manual review of `git status --short`
- manual review of the canonical doc set

Outcomes:
- the canonical docs now describe the external JobPipe data root consistently
- the cleanup/commit-prep topic is now part of the tracked execution plan
- private local calibration material is explicitly kept out of git noise
- the remaining untracked files are classified as first-class assets, not random leftovers

## Topic 9. Pipeline Behavior Audit And Tuning

Status: done on 2026-04-18

Scope:
- verify that the pipe behavior and dashboard truth match the current live data
- tune geo, semantic, triage, and queue behavior only after the data contract and cleanup work are stable

Implementation targets:
- verify geo-block counts and funnel truth against the live ledger/events
- inspect duplicate-looking rows and source-variant grouping for misleading action items
- review semantic-filter and triage distributions for over-uniform categories or drift
- tighten dashboard formatting issues that still interfere with acting on the queue

Validation:
- live-snapshot checks against the current ledger/export
- targeted tests where code contracts change
- rebuild/export/server smoke after any tuning change

Outcomes:
- live dashboard truth was rechecked against the current ledger: `7,686` jobs, `8,982` events, `87` actionable, `4,315` geo skips, `1,567` semantic skips, and `1,072` triage-LLM skips
- the earlier `2.8%` snapshot was confirmed to be stale; the current actionable rate is about `1.13%`
- geo blocks were confirmed to happen at the cheap pre-LLM stage, not after intake; the current geo-block rate is about `56.1%`
- queue duplication was narrowed to two real grouped source-variant cases in the actionable set, while the more serious uniformity issue came from sparse `favorites` source rows
- `merge_job_details()` and exporter enrichment now backfill employer, normalized title, location, and source more aggressively from `00_input.json`
- the Jobs view now has a source filter, grouped-source labels, data-gap disclosure, rolling-deadline normalization, and cleaner decision/status formatting
- broken inline action handlers in the exported dashboard were fixed and revalidated from a headless DOM dump

## Topic 10. Stable Baseline Commit And Dashboard Redesign Start

Status: next

Scope:
- commit the cleaned, validated baseline before the larger dashboard redesign
- then rebuild the dashboard shell and interaction model more intentionally around the new data contract

Implementation targets:
- review the remaining first-class untracked assets and promote the right ones into the repo
- make one clean baseline commit with docs, tests, and runtime paths aligned
- define the redesign entry point from the stable CareerTrack-style information architecture already chosen
- keep the next redesign topic separate from pipeline-truth fixes so regressions stay attributable

Validation:
- `compile_check.py`
- `pytest`
- `git status --short` reviewed for intentional contents only
- canonical docs and plan updated before commit
