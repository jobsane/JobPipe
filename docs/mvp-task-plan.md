# Topic-By-Topic Task Plan

Last updated: 2026-04-20

This is the only active execution-order plan. Do not create separate "next steps" or parallel plan files; update this one.

Rule: finish one topic completely before starting the next. Each topic ends with validation and documentation updates.

## How this plan fits the rest of the project docs

This file is the short-term execution plan, not the full product-management system.

Use the canonical docs like this:

- `PRODUCT_VISION.md`
  - north star
  - product principles
  - long-term roadmap
  - Now / Next / Later priorities
- `docs/architecture-plan.md`
  - source-of-truth split
  - repo boundaries
  - integration seams
- `docs/mvp-task-plan.md`
  - ordered short-term execution topics
  - one active topic at a time
- `AUDIT.md`
  - local operational defect/debt log
- `AGENT_STATUS.md`
  - local operational state and handoffs

Privacy note:

- `AUDIT.md` and `AGENT_STATUS.md` are maintained locally for operator/agent continuity
- they are intentionally kept out of git because they may contain private operational notes and local-environment details

Backlog rule:

- if it is a strategic or long-term idea, put it in `PRODUCT_VISION.md`
- if it is a defect, risk, or debt item, put it in local `AUDIT.md`
- if it is immediate execution work, put it here as a topic or a task under the active topic
- if it is just current session state or a handoff, put it in local `AGENT_STATUS.md`

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

Status: done on 2026-04-18

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

Outcomes:
- the canonical docs now describe the companion-project split consistently across `README.md`, `docs/architecture-plan.md`, and `DASHBOARD_SPEC.md`
- the JobSync integration seam is now documented as a narrow contract instead of an implicit repo-sprawl plan
- canonical docs no longer depend on `.jobpipe_tmp` research paths
- baseline validation passed before commit prep: `compile_check.py`, `pytest`, and manual tree review

## Topic 11. Minimal JobSync Intake And Application-Packet Contract

Status: done on 2026-04-18

Scope:
- keep JobPipe stable while defining a narrow, durable integration seam with JobSync
- document and implement the real handoff object: promote a lead into an application case
- keep JobSync changes minimal and compatible with upstream by preserving its current tracked-job flow as much as possible

Implementation targets:
- define and document the application-packet schema emitted by JobPipe
- keep JobPipe as the owner of lead intake, scoring, gap analysis, and packet creation
- import shortlisted jobs into JobSync as `new` tracked jobs without rewriting JobSync's main workflow
- attach explicit external identity and provenance metadata only where needed for deterministic re-import
- keep status sync conservative and optional until the import flow is proven
- keep Reactive Resume and document-oriented cover-letter editing outside JobSync's core data model for now

Validation:
- one promoted JobPipe lead imports into JobSync as the intended tracked-job starting state
- repeated import is idempotent by stable external identity
- JobPipe remains the owner of scoring/explanation/artifact metadata
- JobSync's existing workflow remains usable without a broad status rewrite
- the documented contract is specific enough to support a later thin upstream-friendly API or sidecar importer

Outcomes:
- canonical docs now define the application-packet model and the minimal `JobSync` intake seam
- `jobpipe/core/jobsync.py` now carries a versioned connector contract plus application-packet version constant
- `jobpipe/cli/sync_jobsync_jobs.py` now emits promoted leads with:
  - `status = new`
  - explicit `jobpipeStatus`
  - a nested `applicationPacket` carrying local-first analysis, drafting, and artifact metadata
- focused connector tests now cover the versioned envelope, outbox writes, shared-status normalization, the richer import-record shape, and a stub HTTP receiver for the import contract
- the chosen boundary is now explicit: HTTP receiver first, outbox fallback when no receiver exists yet
- no sibling-repo changes were required to finish the JobPipe side of the topic

Boundary note:
- the actual JobSync receiver implementation remains an external dependency and should be handled in the sibling repo only if and when needed

### Detailed Execution Checklist

#### Task 1. Define the application packet

Files:
- `docs/architecture-plan.md`
- `PRODUCT_VISION.md`
- JobPipe packet / connector code as needed

Do:
- define the stable handoff object that turns a curated lead into an application case
- include:
  - external identity
  - job metadata
  - source/apply URLs
  - ad snapshot
  - JobPipe score + rationale
  - gap summary
  - cover-letter brief
  - CV-highlights / tailoring guidance
  - artifact-folder metadata where available

Done when:
- the canonical docs describe the same packet and ownership boundaries
- downstream connector work has a concrete contract to target

Risk / notes:
- do not let the packet depend on JobSync internals

#### Task 2. Keep JobPipe ownership explicit

Files:
- `jobpipe/cli/export_dashboard.py`
- JobPipe connector / outbox code as needed

Do:
- ensure the exported payload and connector/outbox surface carry the information that belongs to JobPipe:
  - scoring
  - rationale
  - ad snapshot
  - pack/drafting metadata
- keep JobPipe's richer internal state model intact even if the first external import does not consume all of it

Done when:
- JobPipe can emit enough context for JobSync and external authoring without losing provenance

Risk / notes:
- do not narrow the contract to "just create a job row"

#### Task 3. Define the minimal JobSync intake seam

Files:
- external JobSync repo and/or boundary notes
- connector/importer code as needed

Do:
- identify the smallest seam that can create a tracked job from an external curated lead
- prefer a thin import endpoint or sidecar importer over direct JobPipe writes to JobSync core tables
- preserve JobSync's `new`-first tracked workflow

Done when:
- one promoted lead can land in JobSync without changing how normal JobSync users work

Risk / notes:
- minimize required upstream divergence

#### Task 4. Add deterministic external identity

Files:
- connector/importer code
- JobSync-side schema only if strictly necessary

Do:
- upsert by explicit external identity rather than fuzzy matching
- keep provenance/source metadata lightweight

Done when:
- repeated import is idempotent
- imported jobs can be traced back to JobPipe cleanly

Risk / notes:
- do not overmodel JobPipe-specific concepts inside JobSync

#### Task 5. Keep the connector thin

Files:
- JobPipe connector code
- JobSync receiver/importer code if added

Do:
- keep JobPipe-specific mapping logic in the connector layer
- avoid depending on JobSync status row order, UI assumptions, or non-public semantics
- prefer label-based or packet-based input to raw table-shape coupling

Done when:
- upstream JobSync changes are buffered by the connector rather than breaking JobPipe directly

Risk / notes:
- this boundary discipline is the point of the topic

#### Task 6. Validate the minimal import path

Files:
- JobPipe tests and smoke flow
- JobSync-side smoke path where applicable

Do:
- verify the packet/outbox shape
- verify one idempotent import into JobSync
- verify provenance survives the handoff
- verify the import path does not require a broad JobSync workflow rewrite

Done when:
- one representative shortlisted lead can become one stable application case in JobSync

Risk / notes:
- validate the minimal path before adding status sync or apply orchestration

### Suggested Execution Order

1. Task 1
2. Task 2
3. Task 3
4. Task 4
5. Task 5
6. Task 6

### First Milestone

The first real proof point is:

- JobPipe emits a stable application packet
- JobSync can receive one promoted lead as one idempotent tracked job
- the contract is narrow enough that a later upstream-friendly endpoint or sidecar importer remains possible

## Topic 12. Apply Orchestration, External Authoring, And Artifact Saveback

Status: done on 2026-04-18

Scope:
- turn the promoted JobSync case into the launch point for actual application work
- keep final submission manual while automating preparation and context carry-through
- connect JobSync to external CV and cover-letter authoring without making JobSync the authoring engine

Implementation targets:
- define the `apply` action contract from JobSync:
  - open the job ad in a browser tab
  - open the application portal in a browser tab
  - launch the live JobPipe apply workspace when available
  - expose deterministic saveback targets for the downstream authoring tools
- persist apply-session context in JobPipe so external tools and the human operator can work from one stable packet
- keep final saveback local-first and manual-safe even before Reactive Resume and document automation are wired

Validation:
- one JobSync case can launch the intended external authoring workflow
- one JobSync case can launch the live JobPipe apply workspace plus source/apply links
- expected saveback targets are visible from both sides of the boundary
- manual edit/review remains part of the live flow before submission
- final artifact paths are visible from the active case

Outcomes:
- `jobpipe/cli/dashboard_server.py` now exposes a versioned local apply-session contract via `/api/apply_session/<job_id>`
- JobPipe persists the apply session per job as `apply_session.json` inside the job artifact folder
- the apply-session manifest records:
  - launch URLs for the job ad and application portal
  - deterministic saveback targets for CV PDF/JSON, cover-letter DOCX/TXT, and screening-answer DOCX
  - JobPipe analysis and drafting context for downstream authoring tools
- `reports/apply_template.html` now consumes that contract, exposes the saveback targets, and can open all launch URLs from one user click
- the sibling `JobSync` repo now has a minimal additive intake/launch seam:
  - `POST /api/integrations/jobpipe/jobs` with token auth
  - explicit `externalSource` / `externalId` / `externalData` on imported tracked jobs
  - `JobDetails` can launch the JobPipe workspace, fetch the live apply session, open source/apply URLs, and render saveback targets
- the environment seam is explicit:
  - `JOBSYNC_SYNC_TOKEN`
  - `JOBPIPE_BASE_URL` or `NEXT_PUBLIC_JOBPIPE_BASE_URL`
- validation passed across both repos:
  - JobPipe: `compile_check.py`, full `pytest`
  - JobSync: `npm run lint`, full `npm test`, `npm run build`

Deviation note:
- the local `JobSync` SQLite database on this machine required manual application of the generated migration SQL after Prisma schema-engine commands failed. The migration file is present in the sibling repo, but the local DB change was not completed through `prisma migrate dev`.

## Topic 13. Settings Surface And Integrations Control Plane

Status: done on 2026-04-18

Scope:
- add the first-class Settings / Integrations surface in JobPipe
- make JobPipe the place where profile-pack, targeting, secrets, and connector state are managed
- keep this topic narrowly about the control-plane surface, not mailbox ingestion or authoring automation yet

Implementation targets:
- add Settings / Integrations pages in JobPipe for:
  - profile pack
  - geo / domain / role targeting
  - credentials and secrets
  - Gmail lead/status connector state
  - external tool and sibling-app connection state

Validation:
- settings changes persist in the intended local-first boundary
- the control-plane surface exposes the currently active profile/targeting/connector truth without digging through files
- at least one settings-backed path is exercised end-to-end from UI to persisted local state

Outcomes:
- JobPipe now has a first-class `Settings / Integrations` page in the dashboard shell
- a new local settings state file lives under `<data-root>/reports/settings_state.json`
- the dashboard payload now exposes a versioned `settings` object with:
  - targeting state
  - integration state for JobSync, Reactive Resume, and Gmail
  - secret presence indicators only
  - local-first path disclosure for the active control-plane files
- local server mode now supports `POST /api/settings` for persisted control-plane updates
- focused tests now cover both settings persistence and the payload contract
- local smoke passed for:
  - `export_dashboard.py`
  - a fresh `dashboard_server.py` instance returning `settings.schema_version = jobpipe.settings.v1`

## Topic 14. Mailbox Intake And Recommended-Lead Flow

Status: done on 2026-04-18

Scope:
- make mailbox/Finn lead intake configurable from the JobPipe settings surface
- move recommended jobs into JobPipe as first-class leads before shortlist promotion

Implementation targets:
- add mailbox/Finn intake configuration under JobPipe settings
- define and implement the operator flow for:
  - Gmail-driven lead intake
  - mailbox-driven status detection
  - recommended-job ingestion into triage
- keep lead ingestion separate from JobSync tracked-job flow

Validation:
- at least one mailbox-driven lead can enter the triage flow through the documented path
- mailbox/status settings persist through the same local-first settings surface

Outcomes:
- mailbox recommendation intake is now a first-class settings-aware CLI flow via `jobpipe/cli/sync_mailbox_leads.py`
- Gmail lead intake is now explicitly separate from Gmail status detection:
  - lead intake scans recommendation emails and routes fetched FINN leads into the normal `jobs_delta.jsonl` connector before filters and triage
  - status detection continues to update `application_state.json`
- the shared lead connector is now versioned in `jobpipe/core/lead_intake.py`
- FINN mailbox recommendations, FINN direct search results, and FINN Chrome-extension captures now all write through the same lead-connector helper before entering the pipeline
- the Settings / Integrations payload now exposes Gmail lead/status target paths and flow labels so the control plane shows the split explicitly
- validation passed:
  - `compile_check.py`
  - focused pytest for mailbox intake + dashboard contract
  - full `pytest`
  - local CLI smoke: `sync_mailbox_leads --dry-run` correctly no-ops when Gmail lead intake is disabled in local settings

Deviation note:
- live Gmail recommendation ingestion was not executed against an enabled local mailbox configuration in this topic pass because the current local settings state did not enable mailbox lead intake. The implemented path is validated through focused tests and a live disabled-state CLI smoke.

## Topic 15. Intake Pipe Connector Normalization And Pre-Triage Dedupe

Status: done on 2026-04-18

Scope:
- make Topic 15 functionally about the intake pipe before any larger shell rewrite
- keep `NAV` feed intake and mailbox-derived suggested leads as separate connectors
- dedupe connector output before the rest of the pipeline sees the jobs
- preserve a pragmatic canonical preference for `NAV` rows when the same job appears from multiple sources

Implementation targets:
- define the explicit end-of-connector model for:
  - `NAV` feed intake
  - mailbox suggested-lead intake (`FINN` / later `LinkedIn`)
- add a shared intake-merge stage ahead of the main pipe instead of treating `jobs_delta.jsonl` as both raw connector sink and merged queue
- make dedupe happen at the shared intake boundary before the normal pipeline stages
- define canonical precedence rules:
  - prefer `NAV` as the pragmatic canonical record when both `NAV` and mailbox/scraped lead variants point to the same job
  - keep source provenance and alternates so the pipeline/debug surfaces still know where the job came from
- define connector-specific deterministic pre-triage policy:
  - `NAV` feed jobs go through the normal deterministic gate stack
  - mailbox/platform-suggested leads bypass `geo` block and semantic pre-filter
  - mailbox/platform-suggested leads must still be killed by `hard_no_title_regex`
  - surviving suggested leads go straight to triage review
- keep Gmail lead intake separate from Gmail/application status updates
- keep scrape/enrichment logic as part of the lead connector boundary:
  - today `FINN` suggestions enrich missing fields from the website before merge
  - later `LinkedIn` can join the same pattern when scraping is implemented

Validation:
- `NAV` and mailbox-suggested leads stage separately before merge
- dedupe happens before the rest of the pipeline sees the merged queue
- `NAV` is the pragmatic canonical source when duplicates collide, while alternate-source provenance is preserved
- suggested leads bypass `geo` and semantic pre-filters but still honor hard-no title blocking
- connectors can run independently, and `drain_queue.py` rebuilds the merged queue before processing the normal pipeline
- `compile_check.py` passes
- `pytest tests -q` passes

Current pass:
- `jobpipe/core/intake_pipe.py` now defines explicit connector staging, shared merge + dedupe, and `NAV` canonical precedence
- `pull_sheets_csv.py` now stages the broad NAV Sheet/API feed as the `NAV` connector instead of writing directly into the merged queue
- mailbox-received `FINN` suggested leads, direct `FINN` search results, and manual/browser captures now append into lead-style staging with explicit connector source and pre-triage policy metadata
- `drain_queue.py` now rebuilds `<data-root>/jobs_delta.jsonl` from connector staging before the main pipe runs, then prunes consumed staged rows
- `triage.py` now applies connector-aware deterministic policy: full-feed jobs keep the normal gate stack, while suggested leads bypass `geo` and semantic pre-filter elimination but still honor `hard_no_title_regex`

## Topic 16. JobPipe App Shell Replacement And Automation UX

Status: done

Scope:
- replace the legacy report-style JobPipe dashboard shell with a scalable app-style control plane
- reuse proven UI and workflow patterns from JobSync where they fit, without copying JobSync backend assumptions into JobPipe
- build the shell on top of the normalized intake-pipe/runtime contract from Topic 15 instead of redesigning the UI around unstable intake behavior

Implementation targets:
- define the new JobPipe app-shell/page model around the existing data contract
- separate control-plane pages from active application-workspace concerns
- evaluate JobSync automations as a UI/operations pattern for:
  - source refresh runs
  - mailbox intake runs
  - sync health
  - run history and logs
- keep JobPipe discovery and triage logic owned by JobPipe, not by JobSync automation internals

Validation:
- the replacement shell is documented as an intentional app architecture, not an incremental HTML sprawl
- at least one control-plane page or automation-facing flow proves the new structure is workable
- the docs state clearly what is reused from JobSync patterns and what is not
- the shell topic does not silently redefine intake/connector policy that belongs to Topic 15

Delivered:
- `reports/dashboard_template.html` now uses a sidebar app shell instead of the older top-pill report shell, while still staying on the shared static/server payload contract
- the local dashboard now has a first-class `Automations` page alongside Jobs, Pipeline, Profile & CV, Settings / Integrations, Application Workspace, and Debug / Data
- `jobpipe/core/automation_state.py` now persists local automation-run history at `<data-root>/reports/automation_runs.json`
- `export_dashboard.py` now emits a versioned `automations` payload object with connector counts, action definitions, and recent run history
- `dashboard_server.py` now exposes `POST /api/automation/run` so connector/control-plane actions can be triggered one by one from the local shell
- the first operator-grade actions are now wired as explicit local runs:
  - refresh NAV connector
  - mailbox lead intake dry run
  - rebuild merged queue
  - rebuild dashboard export

Boundary note:
- this closes Topic 16 as a real app-shell/control-plane slice inside the current local runtime
- it does **not** claim that JobPipe has already been rewritten into a separate frontend framework or that JobSync automation backends have been reused directly

## Topic 17. External Authoring Automation And Saveback

Status: done on 2026-04-19

Scope:
- lock the three-system architecture down before adding more automation coupling
- move from launch contracts to real external authoring automation where it is worth the coupling
- keep final submission manual while reducing repetitive CV/cover-letter setup work
- keep the end-state explicit:
  - `JobPipe` as engine/control plane
  - `JobSync` as operator shell
  - `Reactive Resume` as resume subsystem

Implementation targets:
- document the source-of-truth split and shared boundary objects across the canonical docs
- define what should be reused from JobSync underpinnings and what must remain JobPipe-owned
- define how Reactive Resume feeds the system:
  - canonical resume structure
  - resume variants
  - export references used by packets/cases
- add the first real external-authoring automation slice only after the boundary rules are explicit:
  - launch or handoff into Reactive Resume where appropriate
  - carry `ResumeVariantRef` / export references back into the active case
  - keep cover-letter and screening-answer authoring tool-agnostic until the right document workspace is chosen

Validation:
- the canonical docs all describe the same three-system model and source-of-truth split
- external authoring automation, if added, writes back to the expected per-job targets without changing final manual submission ownership
- Reactive Resume and document-workspace automation remain external-tool integrations rather than hidden JobPipe dashboard internals
- no new automation step assumes JobSync or Reactive Resume backend internals without documenting the boundary first

Current pass:
- Topic 17 starts with architecture alignment before implementation
- the canonical docs now treat Reactive Resume as a real third component in the companion stack, not just an optional export tool
- the shared common-ground objects are now explicit so implementation can target stable boundaries instead of ad hoc repo-to-repo coupling
- the first real JobPipe-side authoring/saveback slice is now implemented:
  - `POST /api/authoring/<job_id>`
  - per-job `authoring_state.json`
  - apply-session manifests now carry `authoringState` plus a saveback registration endpoint
  - the local apply workspace can register `ResumeVariantRef`-style resume variant metadata and external document refs without pretending full automation exists yet
- the next narrow slice is now in place too:
  - apply-session manifests can surface the configured Reactive Resume base URL
  - the local workspace can open Reactive Resume directly
  - the local workspace can copy a generated resume-authoring brief from the same packet context
- the document-authoring side of the boundary is now implemented in the same style:
  - settings can now expose a document-workspace base URL
  - apply-session manifests now carry launch URLs and handoff briefs for cover letter and screening answers
  - the local workspace can open the configured document workspace and copy those briefs directly
- the first automatic cross-repo saveback slice now exists too:
  - `dashboard_server.py` now best-effort syncs saved authoring refs into JobSync after local saveback registration succeeds
  - the sibling `jobsync` repo now exposes `POST /api/integrations/jobpipe/authoring`
  - JobSync merges those refs into `externalData` for the matching imported job instead of changing workflow/status tables
  - the JobSync job-details card can now show registered resume / cover-letter / screening-answer refs coming back from JobPipe
- the next narrow resume-side slice is now implemented too:
  - the apply workspace can now register the actual exported resume artifact used for the case, not just the selected Reactive Resume variant
  - `authoring_state.json` now preserves resume export ref, label, URL, format, and exported-at timestamp alongside the deterministic save targets
  - the mirrored JobSync `externalData` now carries that richer resume-export metadata so the operator case can show which export was actually used
- the same exported-artifact capture pattern now exists for document outputs too:
  - the apply workspace can now register the actual exported cover-letter and screening-answer artifacts used for the case, not just the live document refs
  - `authoring_state.json` now preserves export ref, label, URL, format, and exported-at timestamp for both document sections alongside the deterministic DOCX targets
  - the mirrored JobSync `externalData` now carries that richer document-export metadata so the operator case can show the final artifacts used, not only the source docs

Remaining tasks and dependencies:

### Task 17.1. Semantic cleanup of authoring truth

Depends on:
- current Topic 17 saveback/export-capture slices

Do:
- reframe generated cover-letter text and similar outputs as seeded working material instead of pretending they are final canonical authored artifacts
- make the final apply-time truth be:
  - structured decision context
  - exported artifact refs
  - operator workflow state

Done when:
- docs and runtime wording clearly distinguish seed text from exported artifact used

### Task 17.2. Reactive Resume integration research

Depends on:
- none; research topic

Do:
- audit what can be integrated safely from Reactive Resume without turning it into a hard backend dependency
- answer:
  - import/export surfaces available
  - share/link model
  - variant reference stability
  - whether any narrow automation is realistic without owning the upstream code

Done when:
- the repo has a documented answer for what is safe to automate versus what should stay launch-and-capture only

If blocked / uncertain:
- keep this as research-only backlog, not implementation

### Task 17.3. Document-workspace storage and artifact registration

Depends on:
- Task 17.1

Do:
- make sure the final exported CV, cover letter, and screening-answer artifacts all have one deterministic local registration/storage path in JobPipe
- tighten artifact registration so the active case can always tell:
  - source document/tool ref
  - exported artifact used
  - local save target
  - mirrored external ref

Done when:
- document storage/registration is deterministic and auditable for all three authored artifacts

### Task 17.4. AI-supported editing handoff quality

Depends on:
- Task 17.1
- ideally informed by Task 17.2

Do:
- improve the authoring briefs and seeded material handed to:
  - Reactive Resume-side CV work
  - document-workspace cover-letter editing
  - screening-answer editing
- keep this focused on better structured context, not browser automation first
- make the handoff quality good enough that manual editing becomes optional for strong cases, not assumed by default

Done when:
- the apply-time handoff gives AI-supported editing the strongest available structured context without shipping the whole raw dataset around

### Task 17.5. Optional deeper automation decision

Depends on:
- Task 17.2
- Task 17.3
- Task 17.4

Do:
- decide whether to stop Topic 17 at launch + handoff + export capture + document storage
- only proceed to deeper browser/tool automation if the research shows a stable narrow seam

Done when:
- Topic 17 has an explicit stop/go decision on deeper automation instead of open-ended drift

Suggested execution order:
1. Task 17.1
2. Task 17.2
3. Task 17.3
4. Task 17.4
5. Task 17.5

North-star checkpoint after Topic 17:
- the current external-authoring boundary is now useful and traceable
- the next topics must return upstream into the data model itself
- do not keep extending launch/saveback flows unless the next step clearly improves the quality of the data presented to AI and to Lars

## Topic 18. Resume Underlay And Derived Profile Objects

Status: done on 2026-04-19

Scope:
- stop letting multiple incompatible profile/resume shapes drive different parts of the system
- make Reactive Resume-compatible resume data and local targeting settings feed one derived profile layer inside JobPipe
- keep `JobSync` and external tools thin by moving the adaptation burden into JobPipe

Integration guardrail:
- build the person-model adapter layer inside `JobPipe`
- do not make Topic 18 depend on deep edits to `Reactive Resume` internals
- if external resume structure must be mirrored or imported, do it through a thin adapter contract owned by `JobPipe`

Implementation targets:
- define and implement the first derived profile object family in JobPipe:
  - `ProfileSnapshot`
  - `TargetingProfile`
  - `TriageProfile`
  - `AuthoringProfile`
- define the structured resume-tailoring object family:
  - `ResumeMaster`
  - `RoleRecord`
  - `RoleVariant`
  - `ProjectRecord`
  - `ProjectVariant`
  - `EvidenceAtom`
  - `SkillAtom`
  - `NarrativeProfile`
  - `TailoringPlan`
- map current runtime consumers away from direct dependence on:
  - raw `profile_pack.md` narrative text
  - ad hoc `resume.json` use
  - duplicated sibling-system assumptions
- keep `profile_pack.md` and resume exports as source/edit artifacts, not the only runtime truth
- define the minimum JobPipe-owned projection/storage set for the person model:
  - `resume_masters`
  - `role_records`
  - `role_variants`
  - `project_records`
  - `project_variants`
  - `evidence_atoms`
  - `skill_atoms`
  - `narrative_profiles`
  - `profile_snapshots`
  - `targeting_profiles`
  - `triage_profiles`
  - `authoring_profiles`

Validation:
- at least one deterministic filter path uses the new derived profile layer
- at least one triage/match path uses the new derived profile layer
- at least one authoring/apply-session path uses the new derived profile layer
- docs state clearly which old shapes are now source artifacts versus runtime objects

Tasks and dependencies:

### Task 18.1. Define the object family
Depends on:
- Topic 17 checkpoint

Do:
- define exact fields and ownership for:
  - `ProfileSnapshot`
  - `TargetingProfile`
  - `TriageProfile`
  - `AuthoringProfile`
  - `ResumeMaster`
  - `RoleRecord`
  - `RoleVariant`
  - `ProjectRecord`
  - `ProjectVariant`
  - `EvidenceAtom`
  - `SkillAtom`
  - `NarrativeProfile`
  - `TailoringPlan`
- define exact fields for the first derived runtime objects:
  - `ProfileSnapshot`
  - `TargetingProfile`
  - `TriageProfile`
  - `AuthoringProfile`

Done when:
- the canonical docs define exact object responsibilities
- it is clear which objects are canonical, which are derived, and which are source/edit artifacts

### Task 18.2. Map current consumers
Depends on:
- Task 18.1

Do:
- map which current code paths consume:
  - `profile_pack.md`
  - `resume.json`
  - apply-session authoring context
- decide which new object each consumer should read instead

Done when:
- every current consumer has a target object in the new model
- no critical consumer is left depending on "we will figure it out later"

### Task 18.3. Build the adapter layer
Depends on:
- Task 18.2

Do:
- implement the adapter layer inside JobPipe
- keep sibling repos untouched unless a minimal additive seam is required
- make sure the adapter can support:
  - multiple approved role variants for one real job
  - selective inclusion of older but relevant evidence
  - language-specific variants
  - skill ordering and section-order decisions
- define projection rebuild rules:
  - full rebuild
  - partial rebuild
  - source provenance
  - version bumps

Done when:
- JobPipe can derive the new object family from current local sources without requiring upstream sibling changes
- rebuild rules are explicit enough to support Topic 21 later

### Task 18.4. Switch one real consumer per layer
Depends on:
- Task 18.3

Do:
- move:
  - one deterministic filter consumer
  - one scoring consumer
  - one authoring consumer
  onto the new derived profile layer

Done when:
- at least one consumer in each of the three categories reads the new derived layer in runtime
- docs mark the old shapes as source artifacts where applicable

### Task 18.5. Define the storage/projection boundary
Depends on:
- Task 18.1
- Task 18.3

Do:
- define which Topic 18 objects are:
  - persisted projections
  - rebuildable caches
  - ephemeral derived objects
- define identity/version/provenance rules for the person-model projection layer
- keep this storage model JobPipe-owned and local-first

Done when:
- Topic 21 can build on Topic 18 without reopening basic person-model storage questions

Suggested execution order:
1. Task 18.1
2. Task 18.2
3. Task 18.3
4. Task 18.5
5. Task 18.4

Dependency note:
- Topic 18 is the upstream person-model prerequisite for Topic 19.
- Do not implement Triage v3 on top of raw `profile_pack.md` plus ad hoc `resume.json` reads.
- Do not treat Topic 18 as a reason to push resume-model ownership into sibling repos; import/adapt locally first.

Current runtime progress:
- `jobpipe/core/profile_layer.py` now provides the first JobPipe-owned person-model adapter and derived profile family.
- `semantic_filter.py` now builds its profile embedding input from `TriageProfile`-style derived context instead of extracting raw markdown directly.
- `export_dashboard.py` now builds the profile payload from the same derived layer, so the dashboard and scoring path no longer invent separate profile shapes for the same sources.
- `application_pack.py` now builds its authoring payload from the same derived layer instead of combining raw `profile_pack.md` with ad hoc `resume.json` slices directly.
- `profile_match.py` now builds its scoring payload from `profile_match_context` derived from the same layer instead of sending raw `profile_pack.md` into the match stage.
- `profile_layer.py` can now persist that derived layer as `<data-root>/reports/profile_layer_state.json`, making the first real local Topic 18 projection/storage seam explicit in code.
- `settings_state.py` now reads targeting/profile defaults from the persisted derived projection first, so the local Settings surface and the migrated scoring/authoring consumers now point at the same JobPipe-owned person-model truth.
- `run_feed.py` now builds triage-stage profile guidance and deterministic title-target patterns from the derived profile layer instead of relying only on raw `profile_pack.md`.
- `triage.py` now treats `TargetingProfile.target_title_patterns` as part of the deterministic target-title safety boundary, so hard-no exemptions and target-title safety no longer depend only on regex/config drift.
- `load_or_build_profile_layer_for_paths(...)` now gives Topic 18 a shared projection-aware hot path, and `semantic_filter.py`, `profile_match.py`, `application_pack.py`, and `run_feed.py` now all read the profile layer through that seam instead of rebuilding ad hoc every time.
- `pivot.py` and `reverse_triage.py` now consume derived profile contexts instead of forwarding raw `profile_pack` excerpts, which removes the last obvious stage-level profile-pack payload drift from the current pipeline chain.

Closeout note:
- Topic 18 is considered complete enough to hand off to Topic 19.
- Remaining direct `profile_pack.md` loads now serve source-artifact/bootstrap compatibility, not the main stage-level runtime truth for filtering, scoring, pivoting, reverse triage, authoring, dashboard profile payloads, or settings defaults.

## Topic 19. Triage Decomposition, Features, And Cached Scoring

Status: in progress

Scope:
- make triage faster, more reliable, and more debuggable by separating concerns
- prepare the runtime for calibration and experimentation without mixing that logic into one large stage

Integration guardrail:
- keep Triage v3 fully JobPipe-owned
- do not push scoring, calibration, or reranking logic into `JobSync`
- do not let Topic 19 create new sibling-system dependencies just because the feature pipeline becomes richer

Implementation targets:
- split triage into explicit layers:
  - deterministic hard gates
  - feature extraction
  - first-pass ranking / decision
  - ambiguity resolver
  - advantage assessment
  - narrative strategy
  - moderator / reranker
  - calibration hooks
- persist reusable match features instead of recomputing everything from narrative blobs
- keep connector policy explicit at the deterministic layer
- define Triage v3 as a feature pipeline rather than a single monolithic score prompt
  - keep the first-pass feature contract explicit:
    - `core_tech_alignment`
  - `legacy_burden`
  - `role_specificity`
  - `requirement_density`
  - `geospatial_friction`
  - `remote_veracity`
  - `autonomy_level`
  - `stakeholder_complexity`
  - `operating_fit`
    - `confidence`
    - `evidence_spans[]`

Runtime progress (2026-04-19 — Topic 19 first contracts slice):
- `jobpipe/core/schema.py` now defines the first live Topic 19 contracts:
  - `HardGates`
  - `EvidenceSpan`
  - `FeatureScore`
  - `TriageFeatures`
  - `TriageDecisionV3`
- `jobpipe/core/triage_v3.py` now provides the first deterministic weighted aggregator for the Topic 19 feature pipeline.
- `triage.py` now writes additive `hard_gates` snapshots into `TriageOut`, both for deterministic hard skips and for jobs that actually reach the LLM.
- `moderate.py` now attaches an additive `triage_decision_v3` snapshot to `ModeratorOut` using a provisional heuristic feature projection from current runtime truth (`profile_match`, `parsed`, job metadata, triage signals).
- This is an intentional bridge slice, not full Topic 19 completion:
  - `HardGates` are now live and auditable
  - the weighted `TriageDecision` contract is now live
  - true first-class `TriageFeatures` extraction is still incomplete and should replace the current heuristic projection in a later Topic 19 slice

Runtime progress (2026-04-19 — Topic 19 dedicated feature module):
- The provisional Topic 19 feature projection has now been moved out of `moderate.py` into a dedicated module: `jobpipe/stages/triage_features.py`.
- `JobContext` now carries additive `triage_features` runtime state.
- `moderate.py` now consumes that separate feature projection instead of defining the feature-building logic inline, and only persists a bridge artifact when the explicit feature stage is absent.
- A dedicated `*_triage_features.json` artifact now exists as its own runtime concern, but this slice still stopped short of making it a first-class default stage-order entry.
- This is still not the final Topic 19 shape:
  - `triage_features` is now a separate runtime object and artifact
  - it is not yet a first-class configured stage in the default pipeline order
  - ambiguity handling, advantage assessment, and narrative strategy still do not exist in runtime

Runtime progress (2026-04-19 — Topic 19 stage-order and suffix-lookup hardening):
- `triage_features` is now a first-class configured default stage-order entry in `run_feed.py`, placed between `pivot` and `moderator`.
- The bridge write path in `moderate.py` now only writes a fallback `*_triage_features.json` artifact when the explicit feature stage was skipped or omitted.
- `sync_ledger.py` now reads `profile_match`, `pivot`, `moderator`, and `application_pack` artifacts by suffix instead of fixed stage numbers, so Topic 19 no longer depends on `05_moderator.json` / `06_application_pack.json` staying stable.
- `export_dashboard.py` now discovers generated application-pack JSON and CV-highlights DOCX files by suffix as well, so dashboard payload generation follows the same numbering-agnostic contract.
- This removes the main compatibility blocker that kept Topic 19 feature extraction tied to moderation-time persistence.

Runtime progress (2026-04-19 — Topic 19 decision / ambiguity split):
- `triage_decision_v3` now exists as its own runtime stage and context object, separate from moderation.
- `triage_ambiguity_v3` now exists as a dedicated follow-on stage that only runs for borderline cases where `needs_ambiguity_pass` is true.
- `moderate.py` now consumes the upstream Topic 19 decision chain instead of pretending to own first-pass weighted triage itself; it only falls back to local bridge computation when those explicit stage outputs are absent.
- Topic 19 now has explicit runtime separation between:
  - hard gates
  - feature extraction
  - first-pass weighted decision
  - ambiguity handling
- Advantage assessment and narrative strategy still remain future Topic 19 work.

Runtime progress (2026-04-19 — Topic 19 advantage assessment slice):
- `advantage_assessment_v3` now exists as its own runtime stage after ambiguity handling.
- The new stage produces a compact explicit object for:
  - `advantage_type`
  - `advantage_signals`
  - `objection_signals`
  - `neutralizing_evidence`
  - `stretch_level`
  - `review_priority`
- `application_pack.py` now includes this upstream advantage object in its authoring payload, so later Topic 19/20 work can build narrative strategy and packet decomposition on explicit triage outputs instead of re-deriving them ad hoc.
- Topic 19 still lacks the final narrative-strategy stage, but the runtime chain now separates:
  - can this job pass?
  - is it ambiguous?
  - where can Lars plausibly win?

Runtime progress (2026-04-19 — Topic 19 narrative strategy slice):
- `narrative_strategy_v3` now exists as its own runtime stage after `advantage_assessment_v3`.
- The new stage produces an explicit object for:
  - `positioning_angle`
  - `brand_frame`
  - `why_me_now`
  - `top_value_props`
  - `objections_to_handle`
  - `cv_focus_order`
  - `cover_letter_strategy`
- `application_pack.py` now receives both `advantage_assessment` and `narrative_strategy` as upstream inputs, so the authoring layer can start consuming structured positioning truth instead of re-deriving it from raw fit/pivot overlap.
- Topic 19 still does not have cached feature/decision storage beyond artifacts, but the runtime chain now reaches all the way from:
  - hard gates
  - features
  - first-pass decision
  - ambiguity handling
  - advantage assessment
  - narrative strategy

Runtime progress (2026-04-19 — Topic 19 ledger/dashboard projection slice):
- `sync_ledger.py` now carries the first explicit ledger-facing projection of the new triage-v3 chain instead of leaving those objects trapped only in per-job artifacts.
- The ledger now records both scalar summary fields and raw JSON blobs for:
  - `triage_features`
  - `triage_decision_v3`
  - `triage_ambiguity_v3`
  - `advantage_assessment_v3`
  - `narrative_strategy_v3`
- `export_dashboard.py` now surfaces those Topic 19 objects in per-job detail payloads, so the dashboard can inspect:
  - first-pass weighted decision
  - ambiguity outcome
  - advantage signals / objections
  - narrative angle / CV focus / cover-letter strategy
- This is still not full Topic 19 cache/reuse completion:
  - the primary reusable store is still the artifact tree plus ledger projection
  - Topic 19.5 still needs more general cache/reuse rules beyond this first ledger/dashboard slice

Runtime progress (2026-04-19 — Topic 19 cache/reuse rules slice):
- `jobpipe/core/runner.py` now supports optional per-stage cache keys through sidecar `*.meta.json` files instead of blindly trusting artifact existence alone.
- The Topic 19 chain now uses explicit cache-key rules for:
  - `triage_features`
  - `triage_decision_v3`
  - `triage_ambiguity_v3`
  - `advantage_assessment_v3`
  - `narrative_strategy_v3`
- Those cache keys are built from the upstream objects each stage actually depends on, so repeated runs against the same job directory now:
  - reuse cached triage-v3 artifacts when upstream truth is unchanged
  - invalidate and recompute them when parsed/profile-match/decision/advantage inputs drift
- This is still only the first reusable-cache layer:
  - reuse is now precise at the stage-artifact boundary
  - Topic 21 still needs the broader JobPipe-owned projection store for faster cross-run, cross-consumer access beyond per-job artifact reuse

Runtime progress (2026-04-19 — Topic 19 runtime summary slice):
- `JobContext.snapshot_summary()` now carries additive Topic 19 summaries instead of exposing only old triage/moderator-era fields.
- The run index and self-heal path in `run_feed.py` now preserve compact v3-facing fields for:
  - effective `triage_v3_label`
  - weighted score / confidence
  - ambiguity resolution label
  - advantage type / review priority
  - narrative positioning angle / brand frame
- This makes the new triage-v3 chain visible in first-line runtime/debug outputs, not just:
  - deep artifact trees
  - ledger raw JSON blobs
  - dashboard detail panes
- Topic 19 therefore now has three operational visibility layers:
  - per-stage artifacts
  - run/index summaries
  - ledger/dashboard projections

Runtime progress (2026-04-19 — Topic 19 index-to-ledger fallback projection slice):
- `sync_ledger.py` can now synthesize minimal Topic 19 raw JSON projections from the compact index/run-summary fields when the underlying v3 stage artifacts are missing.
- That fallback currently covers:
  - `triage_decision_v3`
  - `triage_ambiguity_v3`
  - `advantage_assessment_v3`
  - `narrative_strategy_v3`
- This makes the current carry-through more robust for dashboard/detail inspection:
  - stage artifacts remain the preferred truth
  - ledger/detail payloads can still reconstruct a thin v3 object shape from summary fields when artifact files are absent
- This is still not Topic 20 packet decomposition or a generalized projection store:
  - the fallback is deliberately thin
  - richer downstream object contracts still belong to later topic work

Validation:
- stage outputs are still additive and debuggable
- repeated runs can reuse cached/derived features where input did not change
- calibration inputs are visible without re-parsing the whole artifact tree manually
- shortlist-only narrative work receives a smaller and better-shaped signal set than the broad feed

Tasks and dependencies:

### Task 19.1. Define the split
Depends on:
- Topic 18

Do:
- split triage into explicit sub-stages and contracts:
  - deterministic hard gates
  - feature extraction
  - first-pass ranking / decision
  - ambiguity resolver
  - advantage assessment
  - narrative strategy
  - moderator
  - calibration hooks
- define concrete runtime objects for:
  - `HardGates`
  - `TriageFeatures`
  - `TriageDecision`
  - `AdvantageAssessment`
  - `NarrativeStrategy`

### Task 19.2. Specify the first-pass feature family
Depends on:
- Task 19.1

Do:
- define the first-pass feature schema and scoring rules
- include:
  - score normalization
  - confidence requirements
  - evidence-span requirements
  - connector-policy handling
- document the first deterministic aggregator and hard overrides as a starting baseline, not permanent truth

Done when:
- the repo has a concrete Triage v3 spec that can be implemented without rediscovering the model in chat

### Task 19.3. Extract reusable features
Depends on:
- Task 19.2

Do:
- define and persist reusable match/triage features that do not require re-reading narrative inputs every time
- include features useful both for triage and later tailoring, so data can flow sideways instead of being recomputed in authoring
- make the feature layer useful both upward and downward in the stack:
  - upward to reranking/calibration
  - downward to narrative strategy and tailoring

### Task 19.4. Refactor runtime stage flow
Depends on:
- Task 19.3

Do:
- change runtime execution to use the decomposed stages without breaking additive artifacts or existing debugability
- keep expensive reasoning off the broad feed by running ambiguity resolution and narrative work only on smaller candidate sets

### Task 19.5. Add cache/reuse rules
Depends on:
- Task 19.4

Do:
- allow repeated runs to reuse derived features where inputs did not change
- ensure cached features can be reused later by Topic 20 boundary objects and Topic 22 experiments

Suggested execution order:
1. Task 19.1
2. Task 19.2
3. Task 19.3
4. Task 19.4
5. Task 19.5

Dependency note:
- Topic 19 is the bridge between the person-model work in Topic 18 and the packet/boundary-object work in Topic 20.
- Do not move on to broad packet decomposition until the feature and decision contracts are explicit.

## Topic 20. AI-Ready Boundary Objects And Packet Decomposition

Status: in progress

Scope:
- stop sending thick mixed-context datasets across boundaries
- reshape JobPipe outputs into smaller objects optimized for the next AI or human decision

Integration guardrail:
- Topic 20 is where the sibling boundaries should get thinner, not thicker
- every new boundary object must be justifiable as a minimal seam for `JobSync`, `Reactive Resume`, or document authoring
- do not use Topic 20 to smuggle raw JobPipe internals into sibling repos

Implementation targets:
- decompose the current broad `application_pack` shape into thinner handoff objects such as:
  - `CanonicalJob`
  - `TargetingDecision`
  - `MatchFeatures`
  - `TriageDecision`
  - `AdvantageAssessment`
  - `NarrativeStrategy`
  - `TailoringPlan`
  - `DecisionBrief`
  - `AuthoringBrief`
  - `ArtifactPlan`
  - `ApplicationCaseProjection`
- tighten JobSync-facing data to an operational projection
- tighten authoring-facing data to artifact-specific briefs

Validation:
- JobSync import no longer needs broad mixed packet context to remain useful
- apply-session / authoring flows can consume smaller purpose-built briefs
- the docs state clearly what stays thick inside JobPipe and what becomes a thin boundary object
- no step after Topic 20 should need to ship raw intake data, full profile text, and full application-pack blobs all at once

Runtime progress (2026-04-19 — Topic 20 first boundary-object slice):
- `jobpipe/core/schema.py` now defines the first explicit Topic 20 boundary-object family:
  - `DecisionBrief`
  - `AuthoringBrief`
  - `ArtifactPlan`
  - `ApplicationCaseProjection`
- `jobpipe/core/boundary_objects.py` now builds those objects centrally instead of letting each downstream seam improvise its own mixed payload shape.
- `sync_jobsync_jobs.py` now emits additive thin JobSync-facing objects:
  - `decisionBrief`
  - `artifactPlan`
  - `applicationCaseProjection`
- `_build_apply_session_manifest(...)` now emits additive authoring-facing objects:
  - `decisionBrief`
  - `authoringBriefs`
  - `artifactPlan`
  - `jobSummary`
- This is intentionally additive:
  - legacy `applicationPacket`
  - legacy apply-session `analysis` / `authoring` / `saveTargets`
  still remain for compatibility while Topic 20 continues
- The immediate gain is that both JobSync import and apply-session generation now have one thinner shared object family inside `JobPipe`, instead of drifting further apart.

Runtime progress (2026-04-19 — Topic 20 apply-workspace consumer slice):
- `reports/apply_template.html` now prefers the new Topic 20 boundary objects when rendering the live apply workspace:
  - `authoringBriefs.*.launch_url`
  - `authoringBriefs.*.handoff_brief`
  - `artifactPlan.save_targets`
- The apply workspace still falls back to the old manifest shape when those new objects are absent, so the slice is compatibility-safe.
- This is the first real downstream seam that treats the thin boundary objects as primary truth instead of just additive metadata.
- The old apply-session fields still remain:
  - `authoring`
  - `saveTargets`
  - `analysis`
  but they now act as fallback compatibility surfaces instead of the only consumer contract.

Runtime progress (2026-04-19 — Topic 20 surgical JobSync consumer slice):
- The sibling `jobsync` repo now has one real minimal consumer that prefers the new Topic 20 objects instead of reading only the old broad packet.
- `src/lib/external-jobs.ts` now carries additive support for:
  - `decisionBrief`
  - `artifactPlan`
  - `applicationCaseProjection`
- `src/lib/external-jobs.server.ts` now prefers `applicationCaseProjection.job_summary` over `applicationPacket.job` when deriving imported description snippets and due dates for stored jobs.
- `src/components/myjobs/JobDetails.tsx` now prefers `decisionBrief` / `applicationCaseProjection` when showing external decision context in the job details UI, while still falling back to the old external packet fields when the new objects are absent.
- This is the intended Topic 20 seam style:
  - one additive reader
  - no shared schema takeover
  - no workflow/status rewrite in the sibling repo

Runtime progress (2026-04-19 — Topic 20 dashboard/detail consumer slice):
- `jobpipe/cli/export_dashboard.py` now builds Topic 20 boundary objects directly into actionable dashboard detail payloads:
  - `detail.decision_brief`
  - `detail.application_case_projection`
- `reports/dashboard_template.html` now prefers `detail.decision_brief` when building:
  - recommendation narrative text
  - evidence/risk lists
  - agent-draft prompt context
- The older broad row fields still remain in the payload and template as compatibility fallback, but the dashboard/detail seam is no longer forced to reconstruct everything from legacy `recommendation_reason` / `triage_explanation` plus scattered detail fields alone.

Runtime progress (2026-04-19 — Topic 20 import demotion slice):
- The sibling `jobsync` import path now treats `applicationCaseProjection.job_summary` as the primary job-summary source when deriving imported description snippets and due dates.
- In this seam, `applicationPacket.job` is now only a legacy fallback/reference surface instead of the main read path.
- The same import path now also derives title/company/location/source inputs through projection-aware helpers, so the packet is no longer the default place to look when a thinner object is already present.
- This is the first slice where one downstream seam can honestly be described as:
  - projection-first
  - packet-second

Runtime progress (2026-04-19 — Topic 20 apply-session writer demotion slice):
- `jobpipe/cli/dashboard_server.py` now treats `decisionBrief`, `authoringBriefs`, `artifactPlan`, and `jobSummary` as the primary writer-truth inside `_build_apply_session_manifest(...)`.
- The legacy apply-session surfaces:
  - `job`
  - `analysis`
  - `authoring`
  - top-level `saveTargets`
  are now derived from those thinner boundary objects wherever a matching boundary field already exists.
- In practice, that means:
  - `job` now mirrors `jobSummary`
  - `analysis` now mirrors `decisionBrief` for shared decision fields
  - `authoring.*` now mirrors `authoringBriefs` plus `artifactPlan.save_targets`
  - top-level `saveTargets` now mirrors `artifactPlan.save_targets`
- This is the first JobPipe-side writer seam where the older broad apply-session shapes are still emitted, but no longer act as the primary source when an equivalent boundary object already exists.

Runtime progress (2026-04-19 — Topic 20 import-envelope writer demotion slice):
- `jobpipe/cli/sync_jobsync_jobs.py` now treats `applicationCaseProjection`, `decisionBrief`, and `artifactPlan` as the primary writer-truth when building the legacy `applicationPacket`.
- In practice, the packet now mirrors thinner boundary objects for overlapping fields:
  - `applicationPacket.job` mirrors `applicationCaseProjection.job_summary`
  - `applicationPacket.analysis.decision` / `fitScore` / `pivotScore` / `rationale` / `overlaps` / `gaps` mirror `decisionBrief`
  - `applicationPacket.artifactsPath` / `inputSnapshotPath` / `generatedArtifacts` mirror `artifactPlan`
- The packet still exists for compatibility, but it is no longer the canonical export shape inside the JobPipe-to-JobSync writer when an equivalent thin object already exists.

Closeout note (2026-04-19):
- Topic 20 is now complete enough to hand off to Topic 21.
- The key reader and writer seams now treat boundary objects as primary truth:
  - JobSync import/detail
  - apply-session generation
  - apply workspace
  - dashboard/detail payloads
  - JobPipe-to-JobSync export envelope
- The remaining legacy packet/manifest fields are now compatibility mirrors rather than the main source shape in those seams.
- Further cleanup belongs to later projection-store and compatibility-retirement work, not to keeping Topic 20 open indefinitely.

Tasks and dependencies:

### Task 20.1. Define thin boundary objects
Depends on:
- Topic 18
- informed by Topic 19

Do:
- define:
  - `DecisionBrief`
  - `AuthoringBrief`
  - `ArtifactPlan`
  - `ApplicationCaseProjection`
- define exactly which of these objects are consumed by:
  - JobSync
  - apply-session generation
  - Reactive Resume handoff
  - document-authoring handoff

### Task 20.2. Decompose application pack
Depends on:
- Task 20.1

Do:
- keep `application_pack` as a source-rich assembly artifact if useful
- stop making it the only downstream handoff object
- explicitly separate:
  - CV composition logic
  - cover-letter strategy
  - screening-answer strategy
  - operator/workflow projection
- keep generated text as working material, not the main cross-boundary truth

### Task 20.3. Tighten downstream seams
Depends on:
- Task 20.2

Do:
- make JobSync-facing and authoring-facing handoffs consume the thinner objects instead of thicker mixed packets
- keep exported artifact refs and workflow state visible without requiring the whole upstream source warehouse

### Task 20.4. Define end-to-end stack dependencies
Depends on:
- Task 20.3

Do:
- write the dependency chain from:
  - intake connector
  - canonical job
  - gates/features/decision
  - narrative strategy
  - tailoring plan
  - authoring brief
  - JobSync case projection
  - exported artifacts
  - status and outcome feedback
- make explicit what data each layer needs and what it must not receive

Suggested execution order:
1. Task 20.1
2. Task 20.2
3. Task 20.3
4. Task 20.4

## Topic 21. Derived Data Store And Low-Latency Projection Layer

Status: done on 2026-04-19

Scope:
- improve throughput, stability, and latency by giving JobPipe a stronger internal data model
- keep the store JobPipe-owned instead of trying to centralize sibling-system truth

Integration guardrail:
- the derived store belongs to `JobPipe`
- do not turn Topic 21 into a plan for a shared cross-repo database
- sibling repos may consume projections and refs, but not JobPipe's internal projection schema as their own runtime truth

Implementation targets:
- define the next internal data/storage model for derived objects and experiments, likely including:
  - `source_variants`
  - `canonical_jobs`
  - `job_requirements`
  - `profile_snapshots`
  - `resume_masters`
  - `evidence_atoms`
  - `triage_feature_sets`
  - `triage_decisions`
  - `advantage_assessments`
  - `narrative_strategies`
  - `tailoring_plans`
  - `authoring_briefs`
  - `application_case_projections`
  - `triage_runs`
  - `match_features`
  - `application_packets`
  - `apply_sessions`
  - `artifact_refs`
  - `status_events`
  - `outcome_feedback`
  - `experiment_runs`
- preserve the existing local-first/private-data boundary
- reduce repeated filesystem-heavy reads on the hot path where a derived projection is enough

Validation:
- at least one hot-path read shifts from ad hoc file assembly to a stable derived projection
- latency-sensitive UI or AI handoff paths become simpler or faster
- boundary docs still keep JobSync and Reactive Resume as separate systems

Runtime progress (2026-04-19 — Topic 21 first projection-store slice):
- `jobpipe/core/projection_store.py` now provides the first explicit JobPipe-owned derived projection store under `<data-root>/reports/projection_store.json`.
- The first persisted sections are:
  - `inputEnrichment`
  - `detailProjections`
- `export_dashboard.py` now loads and persists that store on each payload build.
- The first real hot-path shift is dashboard enrichment:
  - actionable rows now try the stable `inputEnrichment` projection first
  - only then fall back to per-job `00_input.json`
  - successful enrichment writes the normalized fields back into the projection store for later reads
- This is intentionally only the first Topic 21 slice:
  - the store is still local JSON, not a broader derived DB layer yet
  - the first consumer is dashboard/export, not the whole stack

Runtime progress (2026-04-19 — Topic 21 dashboard-server projection fallback slice):
- `dashboard_server.py` now treats stable stage artifacts and projection-store entries as valid evidence that a job run directory still exists, even when `00_input.json` is gone.
- `_load_workspace_context(...)` now falls back to `projection_store.json` when the raw input file is missing:
  - `inputEnrichment` provides normalized employer/link/location fields
  - `detailProjections.application_case_projection.job_summary` provides the compact job summary fallback
- This makes the apply-session / pack read path more resilient:
  - workspace context can still load from the derived store after input-file cleanup
  - the projection store is now serving both dashboard/export and dashboard-server read paths
- This is still a narrow Topic 21 slice:
  - the store remains local JSON
  - broader generalized projection reads still belong to later Topic 21 work

Runtime progress (2026-04-19 — Topic 21 derived workspace-context fallback slice):
- `dashboard_server.py` now reuses `detailProjections.decision_brief` in addition to `application_case_projection` when stage JSON files are missing.
- `_load_workspace_context(...)` now derives a minimal fallback context from the stored boundary objects:
  - `pack.positioning_headline`, `pack.top_value_props`, and `pack.cover_letter_angle`
  - `match.fit_score`, `match.overlaps`, and `match.gaps`
  - `pivot.pivot_score`
  - `moderator.final_decision`, `moderator.cv_focus`, and `moderator.recommendation_reason`
- This means dashboard/apply-session reads can now survive the loss of both:
  - `00_input.json`
  - key stage JSON files
- This is still intentionally bounded:
  - it is a minimal derived fallback, not a full replacement for stage artifacts
  - the projection store is becoming a shared read seam, but not yet the full Topic 21 data layer

Runtime progress (2026-04-19 — Topic 21 apply-session projection-first slice):
- `dashboard_server.py` now carries `detailProjections` through `_load_workspace_context(...)` even when raw files still exist.
- `_get_apply_session(...)` now treats persisted boundary objects as primary truth for the top-level apply-session envelope when they are available:
  - `decisionBrief` prefers `detailProjections.decision_brief`
  - `jobSummary` prefers `detailProjections.application_case_projection.job_summary`
- That means the first Topic 21 reader now uses the projection store as a primary source instead of only as an emergency fallback.
- This is still one bounded seam:
  - authoring inputs and deeper stage-derived fields still come from the current runtime context
  - broader projection-first adoption still belongs to later Topic 21 work

Runtime progress (2026-04-19 — Topic 21 pack-endpoint projection-first slice):
- `dashboard_server.py` now uses a dedicated `_build_pack_payload(...)` path for `/api/pack/<job_id>`.
- That payload now prefers persisted boundary objects when available:
  - `jobSummary` prefers `detailProjections.application_case_projection.job_summary`
  - `decisionBrief` prefers `detailProjections.decision_brief`
  - top-level `job`, `overlaps`, and `gaps` now derive from those stored objects before falling back to stage/runtime context
- This gives Topic 21 a second live projection-first reader seam alongside apply-session.
- Still intentionally bounded:
  - `pack` itself still comes from the current runtime context
  - deeper packet decomposition and broader projection-first rollout still belong to later Topic 21 work

Runtime progress (2026-04-19 — Topic 21 chat-context projection-aware slice):
- `_build_chat_system_prompt(...)` in `dashboard_server.py` no longer reads `00_input.json`, `profile_match`, and `application_pack` directly.
- It now goes through the shared projection-aware workspace path:
  - `_load_workspace_context(...)`
  - `_build_pack_payload(...)`
- That means the chat/system-prompt reader now inherits the same Topic 21 resilience:
  - persisted `jobSummary` and `decisionBrief` can drive the top-level prompt context
  - projection-backed fallback still works when raw input or stage files are missing
- This is still not a generalized projection service:
  - it is one more live reader seam on the same bounded shared context

Runtime progress (2026-04-19 — Topic 21 projection-helper cleanup slice):
- `dashboard_server.py` now centralizes the repeated projection-read logic into small helpers for:
  - loading the projection context for one job/run
  - extracting persisted `job_summary`
  - extracting persisted `decision_brief`
- This does not change the boundary model, but it reduces local drift:
  - `_load_workspace_context(...)`
  - `_build_pack_payload(...)`
  - `_get_apply_session(...)`
  now share the same projection extraction rules instead of each parsing `detailProjections` separately.
- This is a bounded hygiene slice:
  - no new store sections
  - no new reader seam
  - but it lowers the cost of the next Topic 21 consumer migration

Runtime progress (2026-04-19 — Topic 21 dashboard-export detail projection-first slice):
- `export_dashboard.py` now applies persisted `detailProjections` back onto actionable dashboard rows before persisting the refreshed store.
- For actionable jobs:
  - `detail.decision_brief` now prefers the stored `detailProjections.decision_brief`
  - `detail.application_case_projection` now prefers the stored `detailProjections.application_case_projection`
- This means dashboard/export is now both:
  - a writer of the bounded projection store
  - a reader that reuses persisted boundary objects when they already exist
- Still intentionally bounded:
  - only the boundary-object subtrees in `detail` are projection-first
  - the wider row shape and raw detail extraction still remain in place for now

Runtime progress (2026-04-19 — Topic 21 core projection-helper extraction slice):
- `jobpipe/core/projection_store.py` now owns the shared read/write semantics for the bounded projection-store surfaces instead of leaving them split across dashboard-only helpers.
- The core helper layer now provides:
  - one-job projection-context loading from `projection_store.json`
  - persisted `job_summary` extraction
  - persisted `decision_brief` extraction
  - bounded detail-projection apply/build helpers
- `dashboard_server.py` now reads Topic 21 boundary projections through those core helpers instead of maintaining local extraction helpers.
- `export_dashboard.py` now uses the same core helper layer when:
  - reapplying stored `detailProjections`
  - rebuilding the persisted detail-projection record
- This is still a bounded Topic 21 slice:
  - no new consumer seam was added
  - but dashboard-server and dashboard-export now share one real projection API instead of parallel local interpretations

Runtime progress (2026-04-19 — Topic 21 ledger projection-reader slice):
- `sync_ledger.py` now reads bounded Topic 21 projections during ledger rebuild instead of treating the projection store as a dashboard-only surface.
- When raw input or key stage artifacts are missing, `merge_job_details(...)` can now reuse:
  - `inputEnrichment` for employer/link/location/source defaults
  - `detailProjections.application_case_projection.job_summary` for compact job identity and description carry-through
  - `detailProjections.decision_brief` for fallback fit/pivot/final-decision context
- This means Topic 21 now has one shared read seam outside the dashboard path:
  - dashboard/export
  - dashboard-server readers
  - ledger rebuild / carry-through
- Still intentionally bounded:
  - this is fallback/recovery behavior for ledger merge, not a wholesale replacement of ledger artifact sourcing
  - the broader derived-data layer still belongs to later Topic 21 work

Runtime progress (2026-04-19 — Topic 21 projected-input helper generalization slice):
- `jobpipe/core/projection_store.py` now owns the shared helper layer for bounded projected job-input identity too, instead of leaving `inputEnrichment` build/apply rules and job-input synthesis split across dashboard/export, dashboard-server, and ledger code.
- The core projection API now centralizes:
  - building persisted `inputEnrichment` payloads
  - reapplying persisted `inputEnrichment` onto partial dashboard rows
  - synthesizing one bounded projected job-input object from `inputEnrichment` plus `detailProjections.application_case_projection.job_summary`
- `export_dashboard.py`, `dashboard_server.py`, and `sync_ledger.py` now all consume that same projected-input rule.
- This is still a bounded Topic 21 slice:
  - no new consumer seam was added
  - but one more cross-seam drift source is now gone inside the existing projection-store readers/writers

Runtime progress (2026-04-19 — Topic 21 projection-backed generation slice):
- `dashboard_server.py` no longer lets `_run_generation(...)` fail immediately just because `00_input.json` is gone.
- The application-pack regeneration path now reuses `_load_workspace_context(...)`, so it can recover:
  - projected job identity from `inputEnrichment` + `application_case_projection.job_summary`
  - projected `match`, `pivot`, and `moderator` fallback context from `decision_brief`
- Stage restoration inside `_run_generation(...)` is now per-stage instead of all-or-nothing, so one thin fallback object no longer blocks later context recovery.
- This is the first bounded Topic 21 slice that reaches an active writer/regenerator path instead of only dashboard/ledger readers.

Runtime progress (2026-04-19 — Topic 21 job-projection bundle slice):
- `jobpipe/core/projection_store.py` now defines an explicit job-level projection bundle boundary on top of the underlying store buckets.
- The new core API now supports:
  - building one `job_projection_bundle`
  - loading one bundle by `run_id` + `job_id`
  - extracting bounded `input_enrichment` and `detail_projection` from that bundle
  - persisting one bundle back into the store
- `export_dashboard.py`, `dashboard_server.py`, and `sync_ledger.py` now use that bundle boundary instead of each touching `inputEnrichment` and `detailProjections` directly.
- This is still a bounded Topic 21 slice:
  - the JSON store is still the same local store
  - but the internal derived-store API is now one step closer to an explicit projection family instead of raw section access

Tasks and dependencies:

### Task 21.1. Storage-model design
Depends on:
- Topics 18-20

Do:
- define the internal JobPipe-owned derived data model and migration approach
- prefer a cleaner section-by-section rewrite over continued patching of bloated mixed-purpose files
- make the store design explicit about which entities are:
  - connector/intake truth
  - person-model truth
  - decision-layer truth
  - workflow projections
  - experiment/eval truth

### Task 21.2. First hot-path projection
Depends on:
- Task 21.1

Do:
- move one latency-sensitive read path onto a stable projection

### Task 21.3. Broader projection rollout
Depends on:
- Task 21.2

Do:
- roll projections into the paths that benefit most:
  - UI
  - AI handoffs
  - sync/export seams

Suggested execution order:
1. Task 21.1
2. Task 21.2
3. Task 21.3

### Cross-topic dependency spine

The next stable implementation arc should now be read as:

1. Topic 18
   - define the structured person model and derived profile underlay
2. Topic 19
   - define Triage v3 as gates -> features -> decision -> ambiguity -> narrative
3. Topic 20
   - decompose broad packets into thin boundary objects
4. Topic 21
   - persist those derived objects in a faster JobPipe-owned projection layer
5. Topic 22
   - compare and calibrate features, rankers, and tailoring strategies safely
6. Topic 23
   - add advantageous-match and applicant-pool logic on top of the calibrated feature layer
7. Topic 24
   - close the loop with artifact usage and outcomes

This is the order that keeps the whole stack flowing:

- intake -> triage -> JobSync -> apply session -> CV/letter export -> status/outcomes

Do not invert it by pushing deeper automation or UI work ahead of the missing data and decision contracts.

### Cross-topic integration rule

Topics 18-24 should be implemented under one stable architecture doctrine:

- `JobPipe` is the adaptive core and may be rewritten section by section
- `JobSync` and `Reactive Resume` are external companion systems, not co-owned backend layers
- cross-repo changes must stay surgical, additive, and versioned

That means:

1. put new data models, projections, ranking logic, calibration logic, and experimentation logic inside `JobPipe`
2. use Topic 20 boundary objects to keep sibling seams thinner over time
3. treat sibling repos as receivers of refs, projections, artifacts, and launch/saveback seams
4. avoid shared schemas, shared internal business logic, or backend fusion across repos

If a planned task can be completed by strengthening `JobPipe`, that path should be preferred.

## Topic 22. Experimentation, Calibration, And Shadow Evaluation Toolpack

Status: in progress

Scope:
- make experimentation a built-in capability instead of an ad hoc audit habit
- improve scoring quality without risking hidden false negatives in the live user experience

Implementation targets:
- add first-class support for:
  - shadow scoring
  - threshold experiments
  - prompt/version comparison
  - tailoring-plan comparison
  - evidence-selection comparison
  - section-order / skill-order comparison
  - false-negative review sampling
  - connector-policy comparison
  - outcome-linked evaluation
- define safe experiment rules:
  - no hidden treatment that suppresses user-visible strong matches
  - prefer shadow mode and replay evaluation first

Validation:
- one experiment run can be recorded and compared without changing the main live shortlist
- the audit/debug surfaces can explain which model/prompt/threshold produced a decision
- docs record the safe-experiment rule explicitly

Tasks and dependencies:

### Task 22.1. Safe-experiment contract
Depends on:
- Topic 19
- Topic 21

Do:
- define the safe rules for experiments, shadow mode, replay mode, and review sampling

### Task 22.2. Experiment run model
Depends on:
- Task 22.1

Do:
- define and persist experiment metadata, inputs, and comparable outputs

### Task 22.3. First shadow-eval workflow
Depends on:
- Task 22.2

Do:
- implement one real shadow scoring / threshold comparison path

Suggested execution order:
1. Task 22.1
2. Task 22.2
3. Task 22.3

Runtime progress (2026-04-19 — Topic 22 first shadow-eval slice):
- `jobpipe/core/triage_v3.py` now supports parameterized threshold overrides for safe shadow comparison without touching the live defaults.
- `jobpipe/core/experiments.py` now defines the first local experiment-run contract and persistence helpers for:
  - shadow threshold comparisons
  - safe-rule recording
  - experiment index + detail persistence
  - false-negative review sampling from shadow results
- `jobpipe/cli/run_shadow_triage_experiment.py` now provides the first real Topic 22 workflow:
  - load existing triage-v3 artifacts
  - compare baseline vs candidate thresholds in shadow mode
  - persist one experiment summary under `reports/experiment_runs.json`
  - persist one detail file under `reports/experiments/<experiment_id>.json`
  - persist one prioritized review sample for likely baseline false negatives
- Safe experiment rule is now explicit in runtime as well as docs:
  - shadow only
  - no live shortlist suppression
  - compare against baseline
- The shadow workflow now replays from existing stage artifacts when bridge feature artifacts are missing.
- First useful local run:
  - experiment id `shadow_triage_ed5b9bb8b437`
  - candidate thresholds `review=44`, `shortlist=62`
  - compared `25` jobs
  - found `8` label changes, all upgrades, with no live-shortlist side effects
- First review-sampled local run:
  - experiment id `shadow_triage_48a8455ccb4c`
  - compared `25` jobs and found `8` upgrades again
  - produced `5` prioritized review items
  - prioritized baseline `discard -> review` promotions before weaker borderline cases
- `export_dashboard.py` now exposes a thin `experiments` payload surface:
  - `latest_shadow_eval`
  - `review_queue`
  - review items are enriched with current dashboard job context when `run_id` + `job_id` resolve locally
  - this makes Topic 22 visible in the working dashboard data flow instead of leaving it only in raw experiment files
- `reports/dashboard_template.html` now renders that Topic 22 surface in the Pipeline tab:
  - latest shadow-run summary cards
  - prioritized review queue
  - direct jump back into the Jobs queue via `selectJob(...)`
- The shadow CLI now supports feature-weight comparison in addition to pure threshold comparison:
  - `--feature-weights-json`
  - `--feature-weights-file`
  - `--candidate-name`
- First useful feature-weight local run:
  - experiment id `shadow_triage_2fb04b28117e`
  - kind `shadow_feature_weight_eval`
  - compared `25` jobs
  - found `4` upgrades and `0` downgrades
  - produced `5` review items under the same safe shadow-only rules
- Experiment adjudication is now local and persistent:
  - `experiment_review_state.json`
  - dashboard server endpoint `/api/experiment_review`
  - review items now carry stored human verdicts back into the dashboard payload
- `dashboard_template.html` now offers direct adjudication actions for review items in server mode:
  - `correct_miss`
  - `promote_rule_candidate`
  - `interesting_but_no`
  - `not_useful`
  - `clear`
- First live local adjudication was recorded against the latest feature-weight run:
  - experiment id `shadow_triage_2fb04b28117e`
  - job id `cb8af7fc-dc60-49eb-b76b-e4c0205d9889`
  - verdict `correct_miss`
- Topic 22 now derives a first calibration readout from adjudicated review items:
  - `export_dashboard.py` now carries `calibration_summary` alongside `adjudication_summary`
  - the summary reports:
    - reviewed count
    - positive vs rejected vs interesting-no counts
    - useful-signal rate
    - top positive review reasons
    - top rejected review reasons
  - `dashboard_template.html` now renders that calibration readout in the Pipeline experiment surface instead of showing only raw queue items
- This is still intentionally bounded:
  - calibration is descriptive, not self-tuning
  - no live threshold or weight changes are applied from adjudications yet
  - the next step should use this summary to compare candidate experiment variants more deliberately
- Topic 22 now compares recent shadow candidates on human-reviewed signal too, not just on raw upgrade counts:
  - `jobpipe/core/experiments.py` now exposes recent completed shadow-run summaries ordered by `created_at`
  - `export_dashboard.py` now derives `variant_comparison` plus `leading_variant`
  - each variant now carries:
    - candidate name
    - sample size
    - changed / upgrade counts
    - reviewed / positive / rejected counts
    - useful-signal rate
    - top positive / rejected reasons
  - `dashboard_template.html` now renders a first variant-comparison surface in the Pipeline tab
- This is still intentionally bounded:
  - the comparison is descriptive and operator-facing
  - it does not auto-promote thresholds or feature weights into live runtime
  - the next logical step is to capture explicit experiment dispositions or recommendations per candidate variant
- Topic 22 now supports explicit human dispositions for whole shadow candidates, not just individual review items:
  - `jobpipe/core/experiment_review_state.py` now persists `variant_reviews` alongside item-level review verdicts
  - allowed variant verdicts are:
    - `worth_promoting`
    - `needs_more_review`
    - `reject_variant`
  - `dashboard_server.py` now exposes `POST /api/experiment_variant_review`
  - `export_dashboard.py` now carries:
    - `experiments.variant_review_summary`
    - `variant_review` on each compared candidate
  - `variant_comparison` / `leading_variant` now respect explicit variant verdicts before falling back to reviewed useful-signal ranking
  - `dashboard_template.html` now exposes direct variant actions in the Pipeline compare surface:
    - `Worth promoting`
    - `Needs review`
    - `Reject variant`
    - `Clear`
- This is still intentionally bounded:
  - variant verdicts are operator decisions, not auto-promotion into live config
  - they improve ranking and coordination, but do not yet rewrite thresholds or feature weights automatically
  - the next logical step is to turn promoted variants into explicit promotion candidates or recommended config deltas
- Topic 22 now turns `worth_promoting` variants into an explicit promotion queue:
  - `jobpipe/core/experiments.py` now carries baseline config context through recent shadow-run summaries
  - `export_dashboard.py` now derives:
    - `experiments.promotion_candidates`
    - `experiments.promotion_summary`
  - each promotion candidate now includes a bounded `recommended_config_delta`:
    - review-threshold delta
    - shortlist-threshold delta
    - feature-weight deltas when present
  - each promotion candidate now also carries an explicit patch recommendation:
    - threshold overlay suggestion for `configs/pipeline.v1.yaml`
    - code-patch suggestion for `jobpipe/core/triage_v3.py` when feature weights differ
  - `dashboard_template.html` now renders this promotion queue in the Pipeline experiment surface before the general variant-comparison list
- This is still intentionally bounded:
  - promotion candidates are recommendations only
  - no automatic threshold or feature-weight writeback exists yet
  - the patch suggestion is still advisory and copy/review oriented
  - the next logical step is to turn this queue into a reviewed promotion workflow or structured config-delta approval path
- Topic 22 now has a local approval workflow for promotion-candidate patches:
  - `jobpipe/core/experiment_review_state.py` now persists `promotion_reviews` alongside item and variant adjudications
  - allowed promotion verdicts are:
    - `accepted_for_promotion`
    - `deferred_promotion`
    - `rejected_promotion`
  - `dashboard_server.py` now exposes `POST /api/experiment_promotion_review`
  - `export_dashboard.py` now carries:
    - `experiments.promotion_review_summary`
    - `promotion_review` on each promotion candidate
  - `dashboard_template.html` now exposes direct promotion-review actions in the Pipeline promotion queue:
    - `Accept`
    - `Defer`
    - `Reject`
    - `Clear`
- This is still intentionally bounded:
  - approval remains local state, not config writeback
  - accepted candidates still require a separate human patch/apply step
  - the next logical step is a structured patch-application workflow or exportable promotion ledger

## Topic 23. Advantageous-Match And Applicant-Pool Scoring

Status: done on 2026-04-20

Scope:
- make the north star more explicit in ranking, not just in generic fit scoring
- surface where Lars is likely to outperform the first-impression candidate pool

Implementation targets:
- add explicit advantageous-match features and scoring
- add applicant-pool or competition heuristics where evidence is strong enough
- feed that signal into ranking and triage review order without weakening hard safety rules

Validation:
- the new signal is visible in debugging and review surfaces
- the ranking change is explainable job by job
- calibration can compare whether the new signal improves shortlist quality

Tasks and dependencies:

### Task 23.1. Feature research
Depends on:
- Topics 19 and 22

Do:
- determine which features can support advantageous-match and applicant-pool scoring credibly

If blocked / uncertain:
- keep unsupported heuristics as research backlog, not live ranking logic

### Task 23.2. First explicit signal
Depends on:
- Task 23.1

Do:
- add one explainable advantageous-match signal into ranking/review order

Runtime progress (2026-04-19 — Topic 23 first advantageous-match slice):
- `jobpipe/stages/advantage_assessment_v3.py` now derives a richer explicit advantageous-match surface without changing live ranking yet:
  - `advantageous_match_score`
  - `differentiation_signals`
  - `applicant_pool_hypothesis`
  - `recruiter_hook`
- `jobpipe/core/schema.py` and `jobpipe/core/boundary_objects.py` now carry those signals into `AdvantageAssessmentV3` and `DecisionBrief`, so they are no longer trapped in raw stage JSON.
- `export_dashboard.py` now propagates the new advantageous-match fields into actionable `detail` payloads and boundary-object projections.
- `dashboard_template.html` now surfaces them in the Jobs detail pane through:
  - a richer recommendation narrative
  - differentiation signals in evidence items
  - applicant-pool hypothesis
  - advantageous-match score
- This is intentionally bounded:
  - no live ranking or shortlist thresholds were changed yet
  - the first value is explainability and operator visibility
  - the next logical step is to let one bounded advantageous-match signal influence review ordering or experiment comparisons safely

Runtime progress (2026-04-19 — Topic 23 bounded experiment-ordering slice):
- `export_dashboard.py` now lets advantageous-match influence one safe downstream ordering seam instead of live ranking:
  - latest shadow `review_queue` items are now secondarily ordered by `advantageous_match_score`
  - recent `variant_comparison` entries now carry:
    - `avg_advantageous_match_score`
    - `high_advantage_count`
    - `top_recruiter_hooks`
  - `promotion_candidates` now carry the same bounded advantageous-match summary and use it as a secondary sort signal after human verdicts and useful-signal rate
- `dashboard_template.html` now surfaces that bounded signal in the Pipeline experiment surface:
  - review items show advantageous-match score plus recruiter hook / pool view when available
  - variant comparison and promotion queue now show average advantageous-match strength and hook patterns
- This is still intentionally bounded:
  - live triage labels, thresholds, and shortlist decisions are unchanged
  - the new signal only affects review/comparison ordering in the experiment layer
- the next logical step is Topic 23 calibration, not immediate promotion into live ranking

Runtime progress (2026-04-19 — Topic 23 advantageous-signal calibration slice):
- `jobpipe/core/experiment_review_state.py` now derives a bounded `build_advantage_signal_calibration_summary(...)` readout from reviewed experiment items:
  - `high_advantage_reviewed`
  - `high_advantage_positive`
  - `high_advantage_useful_rate`
  - `lower_advantage_reviewed`
  - `lower_advantage_positive`
  - `lower_advantage_useful_rate`
  - `top_positive_hooks`
  - `top_negative_hooks`
- `export_dashboard.py` now carries that under `experiments.advantage_calibration_summary`, built from recent enriched review items rather than from raw live triage outputs.
- `dashboard_template.html` now surfaces that readout directly in the Pipeline experiment surface through:
  - a high-vs-lower advantageous useful-rate summary card
  - an `Advantage signal readout` block
  - top positive and negative recruiter-hook patterns
- This remains intentionally bounded:
  - no live ranking or threshold changes were made
  - the new readout only evaluates experiment-layer review signal quality
  - the next logical step is to turn that calibration readout into a bounded recommendation signal before any live-ordering change

Runtime progress (2026-04-19 — Topic 23 advantageous recommendation slice):
- `export_dashboard.py` now turns `advantage_calibration_summary` into one explicit bounded recommendation object:
  - `experiments.advantage_signal_recommendation`
  - statuses like `watch`, `promising`, `mixed`, `weak`, and `insufficient_signal`
  - a compact explanation plus recommended next action
- The same experiment-layer recommendation is now applied back onto recent candidates through:
  - `variant_comparison[*].advantage_signal_fit`
  - `promotion_candidates[*].advantage_signal_fit`
  - `leading_variant.advantage_signal_fit`
- `dashboard_template.html` now surfaces that in the Pipeline tab through:
  - an `Advantage verdict` summary card
  - recommendation text inside the `Advantage signal readout`
  - per-variant and per-promotion `advantage fit` notes
- This is still intentionally bounded:
  - no live triage ordering changed
  - no thresholds changed
  - the recommendation only helps judge shadow variants and promotion candidates more coherently

Runtime progress (2026-04-19 — Topic 23 promotion-readiness slice):
- Topic 23 no longer stops at advantage-fit notes on shadow candidates.
- `export_dashboard.py` now derives one explicit bounded readiness layer for promoted experiment candidates:
  - `promotion_candidates[*].promotion_readiness`
  - `experiments.promotion_readiness_summary`
- `promotion_readiness` now separates:
  - `ready_for_patch_review`
  - `needs_more_shadow_review`
  - `waiting_for_signal`
  - `hold_for_human_review`
  - `hold_weak_advantage_signal`
- the promotion queue is now partially ordered by that readiness layer after human verdicts, and `leading_variant` can inherit the same readiness signal when it is also the current promotion leader.
- `dashboard_template.html` now surfaces that through:
  - a `Patch-ready` summary card
  - readiness notes in the promotion queue
  - a compact readiness rollup inside the advantageous readout
- This is still intentionally bounded:
  - no live ranking changed
  - no config changed
  - readiness only improves shadow/promotion judgment before any human patch-approval step

Runtime progress (2026-04-20 — Topic 23 shortlist-quality calibration pass):
- Topic 23 now closes the remaining Task 23.3 gap by comparing whether stronger advantageous-match variants are actually producing better reviewed shortlist quality.
- `jobpipe/core/experiment_review_state.py` now derives:
  - `build_advantage_shortlist_quality_summary(...)`
  - high-vs-lower advantageous reviewed-variant counts
  - average useful-signal rates
  - worth-promoting rates
  - one bounded shortlist-quality status plus recommended action
- `export_dashboard.py` now carries that under:
  - `experiments.advantage_shortlist_quality_summary`
- `dashboard_template.html` now surfaces that through:
  - a `Shortlist quality` summary card
  - shortlist-quality detail lines inside the `Advantage signal readout`
- validation passed for the bounded comparison surface:
  - `compile_check.py`
  - `pytest tests/test_experiment_review_state.py tests/test_dashboard_contract.py -q`
- This remains intentionally bounded:
  - no live ranking change
  - no threshold writeback
  - the comparison only judges shadow shortlist quality and promotion signal maturity

Execution note:
- Topic 24 bounded readouts had already started landing in runtime, but Topic 23 remained the active execution topic until this Task 23.3 shortlist-quality comparison was implemented and validated.

### Task 23.3. Calibration pass
Depends on:
- Task 23.2

Do:
- compare whether the new signal improves shortlist quality

Suggested execution order:
1. Task 23.1
2. Task 23.2
3. Task 23.3

## Topic 24. Outcome Feedback And Learning Loop

Status: done on 2026-04-20

Scope:
- use apply/skip/interview/reject feedback to improve prioritization over time
- keep the learning loop inside JobPipe instead of turning JobSync into a second scoring engine

Implementation targets:
- define outcome-linked feedback objects
- capture enough artifact/context linkage to compare what was recommended, what was used, and what happened
- feed that back into calibration and ranking, not into opaque uncontrolled drift

Validation:
- at least one end-to-end outcome can be tied back to the decision context and artifacts used
- the learning loop produces an auditable signal, not just hidden model drift

Tasks and dependencies:

### Task 24.1. Outcome model
Depends on:
- Topics 20-23

Do:
- define how outcomes link back to:
  - decision context
  - artifact refs
  - source/connector context

### Task 24.2. First auditable loop
Depends on:
- Task 24.1

Do:
- implement one end-to-end auditable feedback path without silently changing live ranking

### Task 24.3. Learning-guided ranking improvements
Depends on:
- Task 24.2

Do:
- use the feedback loop to improve ranking/calibration in a controlled explainable way

Suggested execution order:
1. Task 24.1
2. Task 24.2
3. Task 24.3

Runtime progress (2026-04-19 — Topic 24 outcome-model slice):
- `jobpipe/core/schema.py` and `jobpipe/core/boundary_objects.py` now define one explicit `OutcomeFeedback` boundary object, instead of leaving outcome linkage implicit inside `application_state.json` plus ad hoc dashboard rows.
- `jobpipe/core/outcome_feedback.py` now owns the first bounded Topic 24 derived store:
  - `reports/outcome_feedback_state.json`
  - one outcome entry per `run_id::job_id`
  - links back to:
    - `DecisionBrief`
    - `ApplicationCaseProjection`
    - shared workflow status
    - artifact refs already used in the case
- `jobpipe/cli/export_dashboard.py` now persists that derived state on payload build and exposes a thin top-level `outcomes` payload:
  - `schema_version = jobpipe.outcomes-dashboard.v1`
  - `summary`
  - `recent_feedback`
- This is intentionally still bounded:
  - no live ranking or calibration changes are applied from outcomes yet
  - no sibling repo contracts changed
  - the first gain is one auditable, JobPipe-owned outcome model that ties status/artifact usage back to decision context

Runtime progress (2026-04-19 — Topic 24 auditable-loop slice):
- `jobpipe/core/outcome_feedback.py` now derives one explicit bounded `audit_summary` on top of `OutcomeFeedback`, so Topic 24 no longer stops at raw linkage plus recent items.
- The top-level `outcomes` payload now carries:
  - `summary`
  - `audit_summary`
  - `recent_feedback`
- `audit_summary` now compares the current case set through:
  - `by_final_decision`
  - `decision_status_matrix`
  - `apply_path_summary`
  - `artifact_effect_summary`
- This is still intentionally safe:
  - no live ranking or threshold changes
  - no automatic calibration writeback
  - the new value is an auditable matrix of what was recommended, what state the case reached, and whether artifacts were linked

Runtime progress (2026-04-19 — Topic 24 outcome-calibration slice):
- `jobpipe/core/outcome_feedback.py` now derives one bounded `calibration_summary` from the tracked outcome set, so Topic 24 no longer stops at descriptive audit tables only.
- The top-level `outcomes` payload now carries:
  - `summary`
  - `audit_summary`
  - `calibration_summary`
  - `recent_feedback`
- `calibration_summary` currently compares:
  - apply-like progression rate
  - non-apply progression rate
  - artifact-linked progression rate
  - no-artifact progression rate
- This is still intentionally safe:
  - no live ranking or threshold change
  - no automatic config/writeback behavior
  - the first gain is one explainable outcome-linked calibration readout that can later inform controlled ranking changes

Runtime progress (2026-04-19 — Topic 24 bounded recommendation slice):
- `jobpipe/core/outcome_feedback.py` now turns the outcome calibration readout into one explicit bounded `recommendation` object instead of leaving it as passive numbers only.
- The top-level `outcomes` payload now carries:
  - `summary`
  - `audit_summary`
  - `calibration_summary`
  - `recommendation`
  - `recent_feedback`
- `recommendation` currently evaluates:
  - decision-class signal (`reinforce_apply_bias`, `review_apply_thresholds`, `mixed_signal`, `insufficient_signal`)
  - artifact signal (`artifacts_associated_with_progress`, `artifact_effect_unclear`, `mixed_signal`, `insufficient_signal`)
  - bounded `confidence`
  - bounded `recommended_next_action`
- This is still intentionally safe:
  - no live ranking or config change
  - no automatic learning/writeback
  - the new value is one explicit outcome-driven guidance surface that can later feed controlled shadow ranking work

Runtime progress (2026-04-19 — Topic 24 dashboard-visibility slice):
- `reports/dashboard_template.html` now treats Topic 24 as a first-class operator-visible signal instead of leaving it hidden in payload JSON.
- The Pipeline tab now surfaces:
  - `Outcome loop` summary card
  - `Outcome verdict` summary card
  - one bounded `Outcome loop` readout block in the experiment/review surface
- That readout now shows:
  - tracked-case count
  - apply-like progression rate
  - artifact-linked progression rate
  - bounded next action and confidence
  - latest tracked outcome context
- This is still intentionally safe:
  - no new actions or writeback endpoints
  - no live ranking change
  - the gain is operator visibility into Topic 24 without turning the loop into autonomous behavior

Runtime progress (2026-04-19 — Topic 24 shadow-followup slice):
- `jobpipe/core/outcome_feedback.py` now derives one bounded `shadow_followup` object from the new outcome recommendation instead of forcing Topic 24 to jump straight from readout to live tuning.
- The top-level `outcomes` payload now carries:
  - `recommendation`
  - `shadow_followup`
- `shadow_followup` currently expresses:
  - `suggested_experiment`
  - `ready_for_shadow`
  - `confidence`
  - `rationale`
- This is still intentionally safe:
  - no live ranking change
  - no automatic experiment launch
  - the value is one explicit bridge from outcome learning into future shadow work, not uncontrolled auto-optimization

Runtime progress (2026-04-19 — Topic 24 outcome-to-shadow handoff slice):
- `jobpipe/cli/export_dashboard.py` now builds one explicit `experiments.outcome_shadow_handoff` object from the new Topic 24 outcome surfaces instead of leaving the handoff implicit across separate payload branches.
- That handoff currently carries:
  - `status`
  - `suggested_experiment`
  - `ready_for_shadow`
  - `confidence`
  - `decision_signal`
  - `artifact_signal`
  - `rationale`
- `reports/dashboard_template.html` now surfaces that as an `Outcome-to-shadow handoff` block directly inside the Pipeline experiment surface, so the operator can see whether the current outcome sample is mature enough to justify more shadow work.
- This is still intentionally safe:
  - no automatic experiment launch
  - no live ranking change
  - no config writeback
  - the gain is one clearer bounded handoff from Topic 24 back into the Topic 22 shadow lane

Runtime progress (2026-04-19 — Topic 24 outcome-backed shadow-candidate slice):
- `jobpipe/cli/export_dashboard.py` now classifies each shadow candidate against the new outcome-loop handoff instead of leaving that relationship only at the top-level handoff object.
- `variant_comparison`, `promotion_candidates`, and `leading_variant` now carry:
  - `outcome_shadow_fit`
- The experiments payload also now carries:
  - `outcome_shadow_summary`
- `reports/dashboard_template.html` now surfaces that directly in:
  - the `Leading variant` summary card
  - the `Promotion queue`
  - the `Variant comparison` block
  - one new `Outcome-backed` summary card
- This is still intentionally safe:
  - no shadow run is auto-launched
  - no promotion is auto-approved
  - no live ranking change
  - the gain is one clearer operational readout of which shadow candidates are actually supported by the current outcome loop

Runtime progress (2026-04-19 — Topic 24 outcome-backed promotion slice):
- `jobpipe/cli/export_dashboard.py` now turns the new outcome-backed shadow signal into one explicit promotion-level status instead of leaving promotion review to infer it from lower-level fields.
- `promotion_candidates` and `leading_variant` now carry:
  - `promotion_outcome_status`
- `promotion_summary` now also reports:
  - `outcome_backed_count`
  - `waiting_for_outcomes_count`
  - `not_outcome_backed_yet_count`
- `reports/dashboard_template.html` now surfaces that directly in:
  - the `Promotion queue` summary card
  - each promotion-candidate readout
  - the `Leading variant` summary card when applicable
- This is still intentionally safe:
  - no auto-promotion
  - no config writeback
  - no live ranking change
  - the gain is one explicit distinction between:
    - worth promoting in principle
    - worth promoting and already outcome-backed
    - worth promoting but still waiting for outcome evidence

Runtime progress (2026-04-20 — Topic 24 outcome-ranking guidance closeout):
- Task 24.3 is now closed with one explicit bounded ranking-guidance object instead of leaving outcome learning at outcome-backed tags and promotion-status labels only.
- `jobpipe/core/outcome_feedback.py` now derives:
  - `build_outcome_ranking_guidance(...)`
  - reviewed supported-vs-non-supported variant counts
  - useful-signal-rate and worth-promoting-rate deltas
  - one bounded `status`, `confidence`, `summary`, and `recommended_action`
- `jobpipe/cli/export_dashboard.py` now carries:
  - `experiments.outcome_ranking_guidance`
- The experiment surface now uses that outcome loop as a bounded secondary ordering signal only for:
  - `variant_comparison`
  - `promotion_candidates`
- `reports/dashboard_template.html` now surfaces that directly through:
  - an `Outcome ranking` summary card
  - supported-vs-non-supported shortlist-quality detail lines inside `Outcome-to-shadow handoff`
- Validation for the Topic 24 closeout slice:
  - `python -m pytest tests/test_outcome_feedback.py tests/test_dashboard_contract.py -q`
  - `python compile_check.py`
- Topic 24 is now complete in the documented sense:
  - the outcome loop is explicit
  - it is auditable
  - it produces one explainable bounded ranking signal
  - it still does not change live ranking, thresholds, or config automatically

## Topic 25. Baseline Cleanup And Git Checkpoint

Status: done on 2026-04-20

Scope:
- clean up the repo state after Topics 11-24 so work can continue from one deliberate checkpoint
- make the canonical docs and git state agree about what counts as active tracked project history
- avoid bundling generated/private-local material into that checkpoint

Implementation targets:
- review the current worktree against the roadmap and keep the scope limited to intentional JobPipe source/docs/tests
- keep local operational audit/status logs private while making the tracked docs self-contained and auditable
- run full validation for the current baseline instead of relying only on topic-local test slices
- create one clean git checkpoint on top of the documented baseline

Validation:
- `compile_check.py`
- full `pytest`
- manual review of `git status --short`
- the resulting checkpoint contains only intentional tracked source/docs/tests and excludes private/generated data

Tasks and dependencies:

### Task 25.1. Canonical-doc and git contract cleanup
Depends on:
- Topic 24

Do:
- make sure the tracked roadmap and architecture docs are self-contained even while local operational logs remain ignored for privacy
- record the cleanup/checkpoint work explicitly in the roadmap and status docs

### Task 25.2. Baseline validation pass
Depends on:
- Task 25.1

Do:
- run the full validation needed for a continuation baseline
- note any failures or scope mismatches explicitly before commit

### Task 25.3. Git checkpoint
Depends on:
- Task 25.2

Do:
- stage the intentional baseline
- create one continuation commit so the repo has a reliable restart point

Suggested execution order:
1. Task 25.1
2. Task 25.2
3. Task 25.3

Runtime progress (2026-04-20 — Topic 25 cleanup and checkpoint closeout):
- `.gitignore` explicitly keeps `AGENT_STATUS.md` and `AUDIT.md` local-only due to privacy, and the tracked docs no longer pretend those operational logs belong in public git history.
- The current worktree was reviewed as a coherent Topics 11-24 baseline rather than mixed scratch state:
  - source/docs/tests are included
  - private/generated data stays ignored
- `COMPANION_REVISIONS.json` now records the sibling repo revisions aligned with the current JobPipe continuation point instead of relying on memory or copied code:
  - local `jobsync` checkpoint on `codex/jobpipe-integration-baseline` at `4d7ee12`
  - clean `reactive-resume` baseline at `7df9b1e`
- Full baseline validation passed:
  - `python -m pytest -q`
  - `python compile_check.py`
- Topic 25 closes with one deliberate continuation checkpoint in git, so the repo can resume from a validated baseline instead of an uncommitted backlog.

## Topic 26. Companion Revision Drift Check

Status: done on 2026-04-20

Scope:
- make the pinned sibling-repo baseline actually checkable from JobPipe
- avoid relying on remembered sibling SHAs or manual git inspection before stack-level work

Implementation targets:
- add a JobPipe-side reader for `COMPANION_REVISIONS.json`
- add one CLI command that checks local companion path, git identity, branch, commit, and dirty state
- document how that command fits the polyrepo operating model

Validation:
- `python -m pytest tests/test_companion_revisions.py -q`
- `python compile_check.py`
- `python -m jobpipe.cli.check_companion_revisions --strict`

Outcomes:
- `jobpipe/core/companion_revisions.py` now owns the versioned manifest reader and local repo inspection logic
- `python -m jobpipe.cli.check_companion_revisions --strict` now provides one repeatable stack-baseline drift check from inside JobPipe
- the command reports:
  - missing local repo paths
  - non-git directories
  - branch / commit / remote mismatches
  - dirty sibling worktrees
- the canonical docs now treat companion revision pins as:
  - tracked JobPipe metadata
  - validated by a JobPipe CLI check
  - still separate from sibling source history

## Topic 27. Canonical Doc Audit And Roadmap Reset

Status: done on 2026-04-20

Scope:
- audit the canonical docs after Topics 22-26 so roadmap, architecture, and product vision agree again
- define the next executable arc instead of leaving the repo with no active topic after the baseline cleanup

Implementation targets:
- reconcile stale "current focus" and roadmap bullets that still describe completed work as pending
- update the canonical runbook to include the companion drift check where relevant
- add the next numbered implementation topics in the intended execution order

Validation:
- manual review of the canonical doc set:
  - `README.md`
  - `CLAUDE.md`
  - `PRODUCT_VISION.md`
  - `docs/architecture-plan.md`
  - `docs/mvp-task-plan.md`

Outcomes:
- the canonical docs now reflect the completed bounded shadow/advantage/outcome loop instead of describing it as wholly future work
- the runbook now includes the companion revision drift check
- the next numbered arc is explicit again, with one active next topic

## Topic 28. Scheduled Run Reliability And Freshness Baseline

Status: active

Scope:
- make the current stack reliable as a day-to-day operator system instead of a manually resumed engineering baseline
- turn freshness and repeatability into first-class runtime truths

Implementation targets:
- define one repeatable scheduled-run flow for JobPipe
- surface feed freshness / last-successful-run state in the control plane
- integrate companion-revision drift checking into the operator runbook before stack-level validation
- keep the scope inside JobPipe unless a sibling repo needs a minimal additive seam

Validation:
- one documented scheduled-run path exists and can be smoke-tested locally
- freshness state is visible without opening raw files
- the stack runbook can detect sibling drift before broader validation

## Topic 29. Person-Model Spine And Resume Source Adapters

Status: pending

Scope:
- replace parallel profile truth with one JobPipe-owned person/profile spine
- adapt current profile sources into stable derived objects without deep sibling coupling

Implementation targets:
- define the first persisted `ProfileSnapshot` / `TargetingProfile` / `TriageProfile` / `AuthoringProfile` family
- build adapters from `profile_pack.md`, `resume.json`, and Reactive Resume-compatible inputs
- keep Reactive Resume as an external resume system, not a runtime dependency

Validation:
- one canonical derived profile family exists and is persisted or rebuilt deterministically
- source provenance is explicit for every derived profile object

## Topic 30. Derived-Profile Consumer Migration

Status: pending

Scope:
- move real runtime consumers onto the new person/profile spine before adding more authoring complexity

Implementation targets:
- switch one deterministic consumer onto `TargetingProfile`
- switch one scoring consumer onto `TriageProfile`
- switch one authoring consumer onto `AuthoringProfile`

Validation:
- the selected consumers no longer depend primarily on raw `profile_pack.md` narrative text
- tests prove the new derived objects are actually being read in those paths

## Topic 31. Application-Pack Rewrite And Tailoring Plan

Status: pending

Scope:
- upgrade the current application-pack stage from one broad draft object into a thinner, more controllable authoring pipeline
- prefer structured selection and ordering over freeform rewriting

Implementation targets:
- define `TailoringPlan`-style selection outputs
- rewrite the application-pack pipeline around thinner decision and authoring briefs
- improve cover-letter/CV output quality through a multi-step authoring flow

Validation:
- one shortlisted job can produce a stronger bounded authoring package than the current single-pass pack flow
- the new outputs remain explainable and traceable to approved source content

## Topic 32. External Authoring Completion And Saveback Hardening

Status: pending

Scope:
- complete the current external authoring launch/saveback seam without collapsing external tools into JobPipe

Implementation targets:
- finish the operational Reactive Resume handoff
- finish deterministic export capture for CV / cover letter / screening answers
- keep JobSync mirroring at the ref/provenance layer only

Validation:
- one full case can move from JobPipe shortlist to external authoring to saveback with deterministic refs and artifact outputs
- no sibling repo absorbs JobPipe pipeline logic to make that happen

## Research Backlog

Use this section for items that are strategically important but still too uncertain to schedule as direct implementation.

### R1. Reactive Resume deep-automation seam

Questions:
- can we automate variant creation/export safely without owning upstream internals?
- are there stable APIs, export hooks, or link conventions we can rely on?
- can a structured tailoring plan be applied cleanly without mutating upstream truth in unsafe ways?

Needed before:
- any decision to go beyond launch + brief + export capture

### R2. Document-workspace deep automation

Questions:
- which document environment should be the real editing target?
- what automation/storage/export seam is stable enough to own?
- can AI-assisted editing be made good enough that manual edits become exceptional rather than required?

Needed before:
- any browser-driven or remote document automation topic

### R3. Applicant-pool / competition signal quality

Questions:
- which signals are robust enough to improve ranking without hand-wavy guesswork?

Needed before:
- broader advantageous-match ranking logic

### R4. Section-by-section rewrite boundaries

Questions:
- which current files should be strangled/replaced first?
- where can we remove old code quickly after switching one real consumer?

Needed before:
- any larger cleanup/rewrite effort that aims to reduce drift rather than add more layers

### R5. Prototype intake: CV tailoring + cover-letter generation

Source prototype:
- a local prototype folder outside the repo containing CV-tailoring and cover-letter-generation experiments
- if a `prototype/` folder is created under the repo for temporary comparison work, it must remain ignored and stay out of git

Backlog intent:
- treat this as a later bounded topic candidate after the current outcome/calibration arc, not as ad hoc inspiration mixed into the live runtime

Current contents observed:
- `1. Tailor cv`
- `2. Result on run against one job ad`
- `3. cover letter generation`
- `4. result of coverletter generation mot samme stilling som tidligere`

Questions:
- which parts are real architecture candidates versus one-off prompting experiments?
- how should the prototype map onto the current Topic 18-24 model:
  - structured tailoring
  - `TailoringPlan`
  - `AuthoringBrief`
  - Reactive Resume boundary
  - document/case artifact flow
- which ideas belong in a later bounded implementation topic for CV generation and cover-letter generation, and which should remain inspiration only?

Needed before:
- any later implementation topic that productizes this prototype into the main JobPipe stack
