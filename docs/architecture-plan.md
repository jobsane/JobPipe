# Architecture Plan

Last updated: 2026-04-20

This is the canonical architecture note for the active system. Fold architecture updates into this file instead of creating dated architecture snapshots.

## Red Line

The product only works if the same job can be traced cleanly from source input to final dashboard action:

1. source data arrives intact
2. cheap filters remove noise first
3. every stage leaves evidence
4. the ledger becomes the durable system of record
5. the dashboard projects that record without guessing

If a field is useful for filtering, debugging, scoring, or acting, it should either be carried explicitly or be intentionally excluded with a documented reason.

The product-level reason for this architecture is simple:

- the real value is the job-ad data
- the system should absorb cognitive noise before the user starts working
- architecture should preserve that advantage instead of scattering it across UI surfaces and sibling repos

## Actual Running Architecture

```text
NAV pam-stilling-feed
    ↓ Apps Script
Google Sheet (JobFeed)
    ↓ pull_sheets_csv.py
NAV connector output
    ↓ shared intake merge + dedupe
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

## JobSync Integration Target

The current dashboard stack is stable enough that the next integration step should not be a broad JobPipe refactor. The intended split is:

```text
source jobs + Gmail signals
    ↓
JobPipe
    - ingestion
    - filtering
    - scoring
    - evidence artifacts
    - application-state inference
    ↓
    promoted application packet + optional normalized status events
    ↓
    JobSync
    - operator workspace
    - manual application tracking
    - notes / tags / tasks / activities
    - application-case context
```

This is a product split, not a UI swap. JobPipe remains the system that decides why a job is worth acting on. JobSync becomes the system used to work the shortlist.

### Three-System Target

The intended stack is not just `JobPipe + JobSync`. It is:

1. `JobPipe`
   - intake engine
   - triage and scoring
   - application packet and apply session generation
   - pipeline memory and calibration
2. `JobSync`
   - long-term operator shell
   - active application workflow
   - notes, tasks, activities, and follow-up
3. `Reactive Resume`
   - canonical resume structure
   - resume variants
   - tailored CV editing and export

This is better than either extreme:

- continuing to grow the current JobPipe local dashboard into the final operator product
- forcing JobPipe pipeline internals into JobSync's current backend model

The preferred direction is:

- reuse as much of JobSync's shell and app-level underpinnings as is useful
- keep JobPipe as the engine and evidence-producing runtime
- keep Reactive Resume as the resume subsystem instead of rebuilding resume truth elsewhere

### Source-Of-Truth Matrix

| Concern | Owner |
|---|---|
| connector staging, raw lead intake, source dedupe, stage artifacts, calibration history | `JobPipe` |
| curated application cases, notes, tasks, manual statuses, follow-up workflow | `JobSync` |
| resume structure, resume variants, resume export truth | `Reactive Resume` |
| final submission action | human operator |

### Shared Boundary Objects

The right common ground is a small set of explicit domain objects, not one giant shared store:

- `ProfileSnapshot`
- `ResumeVariantRef`
- `CanonicalJob`
- `SourceVariant`
- `ApplicationCase`
- `ApplicationPacket`
- `ApplySession`
- `ArtifactRef`
- `StatusEvent`
- `OutcomeFeedback`

Rule:
- share stable domain objects across boundaries
- do not share raw pipeline staging or backend-specific storage models
- keep the noisy source/pipeline data in JobPipe and the curated workflow data in JobSync

### Architecture Decision: JobPipe-First, Surgical Sibling Integration

The preferred integration style for this stack is **not** gradual backend fusion across `JobPipe`, `JobSync`, and `Reactive Resume`.

It is:

- aggressive cleanup, modularization, and redesign inside `JobPipe`
- conservative, versioned, and minimal seams to sibling systems
- explicit ownership of unstable adaptation inside `JobPipe`

This is the practical meaning of "integration" here:

- `JobPipe` adapts to sibling systems
- sibling systems do not absorb `JobPipe` pipeline complexity
- boundaries stay thin enough that sibling repos can evolve independently

Choose:

- a local-first modular monolith inside `JobPipe`
- a stronger internal projection/data layer inside `JobPipe`
- typed boundary contracts to sibling systems
- refs, projections, and artifact metadata across repo boundaries
- small additive receiver seams in siblings only when necessary

Avoid:

- shared internal business logic across repos
- shared database schemas
- direct dependence on sibling internal storage models
- moving raw pipeline datasets into sibling systems
- requiring sibling repos to carry `JobPipe` orchestration, calibration, or experimentation behavior

Boundary rules:

1. If a change can be solved entirely inside `JobPipe`, solve it inside `JobPipe`.
2. Touch a sibling repo only when a minimal receiver seam is truly required.
3. Prefer imports, exports, refs, and projections over deep runtime coupling.
4. Version every cross-repo payload that matters.
5. Keep pipeline volatility, calibration logic, and experimental logic inside `JobPipe`.

This architecture is better for the real workflow because it optimizes for:

- predictable behavior
- low operational fragility
- simpler local maintenance
- easier auditing when something drifts
- fewer moving parts in the active daily workflow

It also matches the actual project constraint:

- `JobPipe` is the repo under active control
- `JobSync` and `Reactive Resume` are external sibling systems that should be integrated surgically, not co-owned architecturally

### AI-Ready Derived Object Family

The current runtime still mixes narrative profile text, exported resume JSON, stage artifacts, and mirrored cross-system metadata too loosely.

The next architectural step should be a derived object family inside `JobPipe`:

1. `ProfileSnapshot`
   - compact structured summary derived from Reactive Resume-compatible resume data plus local targeting settings
   - not a raw markdown blob and not a direct mirror of an external resume DB
2. `TargetingProfile`
   - deterministic-filter inputs only
   - titles, geography, domain constraints, connector policy
3. `TriageProfile`
   - compact scoring input for semantic filter, triage, profile match, and pivot
4. `AuthoringProfile`
   - richer evidence and story inputs for CV/cover-letter/screening briefs
5. `ApplicationCaseProjection`
   - thin JobSync-facing operational projection rather than thick pipeline exhaust

Rule:

- early pipeline stages should consume compact structured inputs
- late cross-system boundaries should consume smaller task-specific briefs
- `JobPipe` may keep thick/raw truth internally, but it should not mirror that whole dataset across boundaries

### Greenfield Rewrite Target

If the system were built from scratch for the north star, the major sections would be:

1. source intelligence layer
   - ingestion
   - normalization
   - dedupe
   - provenance
2. person model layer
   - structured resume truth
   - approved role/project variants
   - evidence atoms
   - skill inventory
   - narrative profile
3. decision layer
   - eligibility
   - match features
   - advantage assessment
   - narrative strategy
   - tailoring plan
4. authoring/export layer
   - CV render plan
   - cover-letter brief
   - screening-answer brief
   - artifact export capture
5. workflow layer
   - application cases
   - tasks/notes/statuses
   - artifact refs
6. experimentation layer
   - shadow runs
   - evaluation samples
   - calibration results

That is the preferred long-term shape for JobPipe too. Future rewrites should therefore happen section by section, not as more patches on top of broad mixed-responsibility files.

### Structured Resume / Tailoring Model

The intended resume model is not "AI writes a CV". It is "AI composes from approved structured content".

Preferred greenfield objects:

- `ResumeMaster`
- `RoleRecord`
- `RoleVariant`
- `ProjectRecord`
- `ProjectVariant`
- `EvidenceAtom`
- `SkillAtom`
- `SkillCluster`
- `NarrativeProfile`
- `SectionPolicy`
- `TailoringPlan`

Meaning:

- one real role can have several approved narrative variants
- one project can have several approved variants by language or job type
- evidence should be stored in smaller approved atoms that can be selected without dragging the whole cabinet into every export
- the AI should primarily decide:
  - what to show
  - what to hide
  - what order to use
  - which approved variant to choose

Rule:

- prefer selection, ranking, visibility, and ordering over freeform rewriting
- treat final prose generation as a later, narrower stage

### Topic 18 Target: Person Model And Resume Underlay

Topic 18 should create the first real `JobPipe`-owned person-model layer.

Its purpose is:

- stop using `profile_pack.md`, exported resume JSON, and sibling resume assumptions as parallel runtime truths
- define one structured underlay that downstream filters, triage, and authoring can consume safely
- keep `Reactive Resume` as the preferred editing/rendering surface without making Topic 18 depend on deep upstream changes there

#### Canonical objects

1. `ResumeMaster`
   - top-level structured resume object for one person
   - fields should include:
     - `resume_master_id`
     - `source_type`
     - `source_ref`
     - `default_language`
     - `role_record_ids[]`
     - `project_record_ids[]`
     - `skill_atom_ids[]`
     - `narrative_profile_id`
     - `updated_at`
     - `schema_version`
2. `RoleRecord`
   - one factual work-history entry
   - fields should include:
     - `role_record_id`
     - `company`
     - `title`
     - `location`
     - `date_range`
     - `canonical_facts`
     - `role_variant_ids[]`
     - `evidence_atom_ids[]`
     - `tags[]`
3. `RoleVariant`
   - approved narrative version of one real role
   - fields should include:
     - `role_variant_id`
     - `role_record_id`
     - `label`
     - `language`
     - `target_tags[]`
     - `summary`
     - `preferred_evidence_atom_ids[]`
     - `suppressed_evidence_atom_ids[]`
     - `tone_profile`
4. `ProjectRecord`
   - canonical project entry
   - fields should include:
     - `project_record_id`
     - `name`
     - `canonical_facts`
     - `project_variant_ids[]`
     - `evidence_atom_ids[]`
     - `tags[]`
5. `ProjectVariant`
   - approved project version by language or target type
   - fields should include:
     - `project_variant_id`
     - `project_record_id`
     - `label`
     - `language`
     - `target_tags[]`
     - `summary`
     - `preferred_evidence_atom_ids[]`
6. `EvidenceAtom`
   - smallest approved reusable proof unit
   - fields should include:
     - `evidence_atom_id`
     - `source_type`
     - `source_id`
     - `language`
     - `text`
     - `tags[]`
     - `skills[]`
     - `domains[]`
     - `seniority_signals[]`
     - `strength_score`
     - `approved`
7. `SkillAtom`
   - one skill/tool/domain signal
   - fields should include:
     - `skill_atom_id`
     - `name`
     - `aliases[]`
     - `category`
     - `strength`
     - `evidence_atom_ids[]`
8. `NarrativeProfile`
   - small human-authored brand/polish layer
   - fields should include:
     - `narrative_profile_id`
     - `voice_traits[]`
     - `preferred_positioning[]`
     - `do_not_claim[]`
     - `language_preferences`
     - `operator_notes`

#### Derived runtime profiles

Topic 18 should also define the first real derived runtime family:

1. `ProfileSnapshot`
   - compact overall summary for downstream use
   - fields should include:
     - `profile_snapshot_id`
     - `resume_master_id`
     - `target_roles[]`
     - `domain_strengths[]`
     - `seniority_profile`
     - `location_preferences`
     - `core_skills[]`
     - `core_evidence_atom_ids[]`
     - `constraints`
2. `TargetingProfile`
   - deterministic-filter inputs only
   - fields should include:
     - `allowed_geos[]`
     - `blocked_geos[]`
     - `target_title_patterns[]`
     - `hard_no_title_patterns[]`
     - `preferred_domains[]`
     - `connector_policies`
3. `TriageProfile`
   - compact scoring input
   - fields should include:
     - `role_summary`
     - `advantageous_match_hypotheses[]`
     - `transferable_strengths[]`
     - `skill_clusters[]`
     - `must_not_miss_patterns[]`
     - `evidence_atoms_compact[]`
4. `AuthoringProfile`
   - richer evidence and storyline input
   - fields should include:
     - `strongest_storylines[]`
     - `selected_evidence_atom_ids[]`
     - `work_history_refs[]`
     - `project_refs[]`
     - `value_prop_templates[]`
     - `gap_handling_templates[]`
     - `writing_constraints[]`

#### Storage and projection needs

Topic 18 should establish a `JobPipe`-owned projection layer for the person model. The minimum useful projection set is:

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

These do not need to be the final physical table names, but Topic 18 should define:

- primary identity
- versioning
- source provenance
- update/rebuild rules
- whether each object is persisted, cached, or derived on demand

#### Adapter inputs

Topic 18 should treat current inputs like this:

- `profile_pack.md`
  - source/edit artifact
  - useful for narrative cues and targeting policy extraction
  - not primary runtime truth
- `reports/resume.json`
  - import/interchange artifact
  - useful for role/project/evidence extraction
  - not sole runtime truth
- `Reactive Resume`
  - preferred external structured resume surface
  - adapter/import source when available
  - not a required deep implementation dependency for Topic 18

#### First consumers to switch

Topic 18 should not try to move the entire runtime at once.

The first useful switch set is:

1. one deterministic consumer
   - likely title/domain/geo targeting setup
2. one scoring consumer
   - likely semantic filter or profile match input preparation
3. one authoring consumer
   - likely apply-session resume/cover-letter brief generation

#### Migration order

Preferred migration order:

1. define the canonical objects and derived runtime profiles
2. define the projection/storage model and rebuild rules
3. build adapters from `profile_pack.md` and `reports/resume.json`
4. populate the first `ProfileSnapshot` family
5. switch one deterministic consumer
6. switch one scoring consumer
7. switch one authoring consumer
8. demote old shapes in docs/runtime from "truth" to "source artifact"

Rule:

- do not block Topic 18 on deep `Reactive Resume` integration work
- do not create new sibling-system runtime coupling just to get a cleaner person model
- make `JobPipe` own the adaptation burden first

### Data Density By Boundary

The same job can have different intentionally-shaped representations:

1. `JobPipe` thick truth
   - raw source variants
   - parsed/enriched job data
   - triage evidence
   - calibration traces
   - authoring context
2. `JobSync` operational projection
   - canonical job summary
   - rationale
   - active workflow state
   - artifact refs
3. authoring brief
   - only the structured context needed for the current CV / cover-letter / screening task

This is the preferred shape:

- do not ship full raw + derived datasets everywhere
- do not make JobSync or external tools ingest the whole JobPipe warehouse
- derive smaller objects for the next AI or human decision instead

### Narrow-Truth Stage Rule

No stage should see all available context by default.

Each stage should read only the smallest truth needed for its single job:

1. `CanonicalJob`
   - job/ad truth only
2. `TargetingDecision`
   - job truth + targeting rules only
3. `MatchFeatures`
   - job truth + structured profile truth only
4. `AdvantageAssessment`
   - match features + evidence inventory only
5. `NarrativeStrategy`
   - selected job/evidence signals + small human narrative layer
6. `TailoringPlan`
   - structured resume object only
7. `AuthoringBrief`
   - selected outputs from earlier stages only

This is preferred over repeated giant prompts that re-read the whole job, the whole CV, and the whole chain of previous outputs every time.

### Ownership Boundaries

JobPipe owns:

- source intake
- dedupe and filtering
- scoring, recommendation, and explainability
- ledger truth and artifact provenance
- Gmail-derived application-state inference
- generated pack / drafting prompts and packet metadata
- control-plane setup for:
  - profile pack
  - geo / domain / role targeting
  - credentials and secrets
  - Gmail / external-source integrations
  - lead promotion into the shortlist
- the adapter layer that turns resume/profile inputs into derived profile objects for filters, scoring, and authoring

JobSync owns:

- operator-facing dashboard and daily workspace
- tracked-job CRUD
- notes and tags
- tasks and activities
- question bank
- application-case status after a job is promoted
- artifact links and case context for jobs already being worked

External authoring tools own:

- tailored CV creation and export
- cover-letter and screening-answer drafting/editing
- final artifact generation before manual submission

Reactive Resume remains the preferred upstream source for resume structure and variant truth, but JobPipe should own the adapter layer that converts that material into AI-ready derived objects for the rest of the pipeline.

The best long-term split is:

- Reactive Resume owns editing and rendering of structured resume truth
- JobPipe owns job-specific tailoring logic and `TailoringPlan` generation
- JobSync owns operator workflow and visibility into which plan/export/artifacts were actually used

Do not duplicate ownership for discovery, pipeline reasoning, mailbox classification, or primary artifact authoring inside JobSync in v1.

### Phase-1 JobSync Compatibility Rule

The immediate goal is a minimal seam, not a deep JobSync fork.

Phase 1 should prefer:

- importing curated JobPipe leads into JobSync as `new`
- keeping JobSync's existing tracked-job flow and statuses intact
- avoiding broad UI/schema churn in the external JobSync repo unless the change is generally useful upstream
- keeping any JobPipe-specific logic in a thin connector or importer layer, not scattered through JobSync internals

JobPipe may still normalize its own outward-facing status vocabulary for connector use, but that should not force JobSync to abandon its existing `new`-first tracked workflow in the first integration slice.

### Application Packet Contract

The real boundary is not "write into JobSync tables". It is "promote a lead into an application case".

That packet should carry:

- external identity
- job metadata
- job ad snapshot / source content
- source URL and apply URL
- JobPipe score and rationale
- gap analysis and positioning angle
- cover-letter brief
- screening-question context when available
- CV-highlights / tailoring guidance
- artifact-folder or saveback metadata

The packet should be stable on the JobPipe side even if the receiving workflow evolves.

### JobPipe Apply-Session Contract

The first implemented apply-time seam lives in JobPipe's local workspace, not inside JobSync.

Current local contract:

- `dashboard_server.py` serves `GET /api/apply_session/<job_id>`
- the endpoint persists `apply_session.json` into the job's artifact folder
- the manifest is versioned as `jobpipe.apply-session.v1`

The manifest currently carries:

- job/ad/application URLs for launch-time browser actions
- deterministic saveback targets for:
  - tailored resume PDF
  - tailored resume JSON/source export
  - cover-letter TXT draft
  - cover-letter DOCX
  - screening-answer DOCX
- JobPipe-side analysis and drafting context:
  - decision, fit/pivot, overlaps/gaps
  - positioning headline
  - cover-letter angle
  - CV highlights, evidence map, gap mitigations

This is intentionally local-first:

1. one user click in the local workspace can open the relevant URLs
2. external authoring tools have a stable manifest and saveback target set
3. JobPipe does not have to pretend Reactive Resume or a document workspace is already wired through code

The remaining external orchestration still belongs outside this repo:

- JobSync-side `apply` button wiring
- Reactive Resume launch/automation
- document-workspace automation for cover-letter and screening-answer authoring

### Current Topic 17 Saveback Slice

The first real external-authoring implementation slice now exists on the JobPipe side of the boundary.

Current local saveback seam:

- `dashboard_server.py` now exposes `POST /api/authoring/<job_id>`
- each job artifact folder can now persist `authoring_state.json`
- the apply-session manifest now carries:
  - `authoringState`
  - `saveback.registrationEndpoint`
  - `authoring.resume.launchUrl` when Reactive Resume is enabled in settings
  - `authoring.resume.handoffBrief` for copy/paste handoff into the external resume tool
  - `authoring.coverLetter.launchUrl` and `authoring.screeningAnswers.launchUrl` when the document workspace is enabled in settings
  - `authoring.coverLetter.handoffBrief` and `authoring.screeningAnswers.handoffBrief` for copy/paste handoff into the external document tool

This slice is intentionally narrow:

1. Reactive Resume and document tools stay external
2. JobPipe can launch Reactive Resume and the configured document workspace from the apply session when configured
3. JobPipe records which resume variant / document refs belong to the case
4. deterministic save targets stay local-first and unchanged
5. saveback registration can preserve `ResumeVariantRef` / `ArtifactRef`-style metadata before any deeper automation exists

What it does not do yet:

- drive Reactive Resume automatically beyond opening the configured tool URL and handing off a brief
- automate cover-letter or screening-answer editing in a document tool

### Current Cross-Repo Authoring Writeback Slice

The next Topic 17 boundary slice is now real too:

- `dashboard_server.py` now best-effort syncs saved `authoring_state.json` refs into JobSync after local saveback registration succeeds
- `jobpipe/core/jobsync_authoring.py` emits a dedicated `jobpipe.authoring-sync.v1` envelope instead of overloading job import or status sync
- the sibling `jobsync` repo now exposes `POST /api/integrations/jobpipe/authoring`
- JobSync merges the synced authoring refs into the matching imported job's `externalData`
- JobSync's job-details view can now surface the registered resume / cover-letter / screening-answer refs without changing tracked-job workflow/status tables

This keeps the writeback seam narrow:

1. JobPipe remains the local source of truth for apply-session state and saveback registration
2. JobSync only mirrors the registered refs into `externalData` for operator visibility
3. no new authoring sync step rewrites JobSync statuses, notes, or tracked-job semantics

What it still does not do:

- drive Reactive Resume automatically beyond opening the configured tool URL and handing off a brief
- automate cover-letter or screening-answer editing in a document tool
- push authored files themselves into JobSync storage automatically

### Current Resume Export Capture Slice

The next narrow resume-side slice is now implemented on top of the same boundary:

- the apply workspace can now register the actual exported resume artifact used for the case, not just the selected Reactive Resume variant
- `authoring_state.json` now preserves:
  - `variantRef`
  - `variantLabel`
  - `sourceUrl`
  - `exportRef`
  - `exportLabel`
  - `exportUrl`
  - `exportFormat`
  - `exportedAt`
- JobPipe still keeps the deterministic local resume save targets as the primary saveback contract
- JobSync mirrors the richer resume-export metadata into `externalData` only for operator visibility

This is still intentionally narrow:

1. Reactive Resume remains external
2. JobPipe records which resume export was actually used for the case
3. JobSync mirrors that fact without becoming the resume-variant source of truth
4. no browser automation or backend coupling to Reactive Resume is required

### Current Document Export Capture Slice

The same exported-artifact capture pattern now exists for the document side of the boundary:

- the apply workspace can now register the actual exported cover-letter and screening-answer artifacts used for the case, not just the live external document refs
- `authoring_state.json` now preserves for both document sections:
  - `documentRef`
  - `documentLabel`
  - `sourceUrl`
  - `exportRef`
  - `exportLabel`
  - `exportUrl`
  - `exportFormat`
  - `exportedAt`
- JobPipe still keeps the deterministic local DOCX save targets as the primary saveback contract
- JobSync mirrors that richer document-export metadata into `externalData` only for operator visibility

This is still intentionally narrow:

1. the document tool remains external
2. JobPipe records which exported cover letter and screening-answer artifacts were actually used for the case
3. JobSync mirrors that fact without becoming document storage
4. no document-editor automation or backend coupling is required

### Legacy Runtime Shapes To Demote

Two current shapes are still useful, but should increasingly be treated as source/edit artifacts rather than direct runtime truth:

1. `profile_pack.md`
   - still useful as a human-editable reference and source document
   - not ideal as the direct early-stage AI input for multiple pipeline stages
2. `application_pack`
   - still useful as a broad per-case assembly artifact
   - too wide to remain the only downstream handoff object forever

Preferred direction:

- keep those artifacts as editable/source-rich layers
- derive thinner structured runtime objects from them
- avoid making them the direct shape passed into every AI and integration step

### Triage V2 Direction

Triage should be rethought as a value-creation layer, not only a sorting layer.

It should progressively answer:

1. is this in scope?
2. how strong is the evidence match?
3. where is Lars unusually strong?
4. what objections are likely?
5. what is the winning narrative angle?
6. what should the CV emphasize structurally?
7. what should the cover letter sound like?

That implies a narrower sequence of outputs:

- `TargetingDecision`
- `MatchFeatures`
- `AdvantageAssessment`
- `NarrativeStrategy`
- `TailoringPlan`
- `AuthoringBrief`

This is better than one broad triage/application-pack blob because each touch can do one thing precisely and stay relatively unaware of unrelated noise.

### Triage V3 Specification

The preferred next runtime is not "one smarter triage prompt". It is a staged feature-and-ranking pipeline.

Rule:

1. cheap deterministic gates first
2. schema-bound attribute extraction second
3. calibrated ranking third
4. ambiguity resolution only for borderline cases
5. narrative and authoring work only for shortlisted jobs

#### Stage stack

1. `CanonicalJob`
   - input truth:
     - connector records
     - source enrichment
     - dedupe/provenance
   - job:
     - one clean job truth with preserved source variants
2. `HardGates`
   - input truth:
     - canonical job
     - `TargetingProfile`
     - connector policy
   - job:
     - cheaply discard impossible jobs before any richer AI scoring
3. `TriageFeatures`
   - input truth:
     - canonical job
     - `TriageProfile`
     - structured resume/evidence inventory
   - job:
     - extract narrow comparable signals with confidence and evidence spans
4. `TriageDecision`
   - input truth:
     - hard-gate result
     - triage features
   - job:
     - first-pass ranking into `discard`, `review`, `shortlist`
5. `AmbiguityPass`
   - input truth:
     - borderline `TriageDecision`
     - selected conflicting features only
   - job:
     - resolve uncertain or contradictory cases without re-reading everything
6. `AdvantageAssessment`
   - input truth:
     - shortlisted job
     - selected feature evidence
   - job:
     - explain where Lars is unusually strong and where recruiters may hesitate
7. `NarrativeStrategy`
   - input truth:
     - advantage/objection signals
     - small human `NarrativeProfile`
   - job:
     - define the winning angle, not final prose
8. `TailoringPlan`
   - input truth:
     - structured resume object family
     - narrative strategy
   - job:
     - select, hide/show, and reorder approved CV content
9. `AuthoringBrief`
   - input truth:
     - canonical job
     - narrative strategy
     - tailoring plan
   - job:
     - feed the final CV / cover-letter / screening-answer authoring steps

#### Hard gate shape

`HardGates` should stay deterministic and cheap. Initial required fields:

- `title_gate`
- `language_gate`
- `sector_gate`
- `geo_gate`
- `remote_gate`
- `must_have_tech_gate`
- `duplicate_gate`

Connector rule:

- broad-feed `NAV` jobs use the full hard-gate stack
- pre-vetted suggested leads may bypass selected deterministic gates by explicit connector policy
- connector exceptions must stay visible in the output contract

#### Feature shape

The six-dimensional proposal is useful, but better treated as a feature family than as the final truth.

Preferred first-pass `TriageFeatures` fields:

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

Normalization rule:

- high score always means "good for Lars"
- therefore:
  - `legacy_burden = 100` means low legacy drag
  - `geospatial_friction = 100` means low travel friction
  - `remote_veracity = 100` means highly credible flexibility

Each feature should carry:

- `score`
- `confidence`
- `reason`
- `evidence_spans`

`evidence_spans` should point back to short snippets from:

- job title
- job body
- metadata
- connector/source metadata

This keeps the model auditable and makes calibration easier.

#### Decision shape

`TriageDecision` should remain simple and reproducible:

- `label = discard|review|shortlist`
- `weighted_score`
- `confidence`
- `needs_ambiguity_pass`
- `blockers[]`
- `boosts[]`
- `summary`

The first live version can start with hand-tuned weights and overrides, but the contract should assume later calibration.

#### Narrative shape

`NarrativeStrategy` is not final prose. It should capture:

- `positioning_angle`
- `top_value_props[]`
- `objections_to_handle[]`
- `cv_focus_order[]`
- `cover_letter_strategy`

This is the first layer that should answer:

- why Lars could win this role
- what the recruiter may doubt
- what the CV should bring forward structurally
- what tone and emphasis should drive the letter

#### Why this is the preferred 2026 shape

It matches the best current engineering pattern:

- decomposition over monolithic reasoning
- structured outputs over loose free text
- calibrated multidimensional rubrics over a single opaque score
- reranking over prompt-only "final judgment"

The important principle is:

- the dimensions are features
- the ranking layer is a separate concern
- the narrative layer is a later concern

### End-To-End Dependency Spine

The preferred product flow should now be read as one dependency spine from intake to finished application:

1. intake connectors
   - produce `SourceJobVariant`
   - preserve provenance and channel policy
2. canonicalization + dedupe
   - produce `CanonicalJob`
   - preserve alternate-source traceability
3. deterministic targeting
   - consume `TargetingProfile`
   - produce `HardGates`
4. feature extraction and first-pass ranking
   - consume `TriageProfile`
   - produce `TriageFeatures` and `TriageDecision`
5. shortlist understanding
   - produce `AdvantageAssessment` and `NarrativeStrategy`
6. structured CV composition
   - consume `ResumeMaster` family
   - produce `TailoringPlan`
7. artifact-specific authoring
   - produce `AuthoringBrief`
   - external tools create exported artifacts
8. workflow projection
   - produce `ApplicationCaseProjection`
   - JobSync owns tasks, notes, and statuses after promotion
9. saveback and outcome loop
   - `ArtifactRef`
   - `StatusEvent`
   - `OutcomeFeedback`
10. experimentation and calibration
   - compare gates, features, rankers, tailoring plans, and outcomes without risking hidden live regressions

Upstream/downstream rule:

- upstream layers keep thicker and noisier truth
- downstream layers receive thinner and more task-specific objects
- no downstream layer should receive the full warehouse unless debugging explicitly requires it

### Data And Storage Needs

The preferred JobPipe-owned derived data layer should eventually expose at least these entities:

| Entity | Purpose |
|---|---|
| `source_variants` | raw connector/source variants per job before canonical merge |
| `canonical_jobs` | one durable job truth plus provenance |
| `job_requirements` | parsed requirement/responsibility fragments for later reuse |
| `targeting_profiles` | deterministic-filter inputs |
| `profile_snapshots` | compact person-underlay objects for scoring |
| `resume_masters` | mirrored/adapter view of approved structured resume content |
| `evidence_atoms` | reusable approved evidence snippets |
| `triage_feature_sets` | auditable features with confidence and evidence spans |
| `triage_decisions` | first-pass ranking results and ambiguity flags |
| `advantage_assessments` | why Lars could win and where he may be weak |
| `narrative_strategies` | positioning and objection-handling strategies |
| `tailoring_plans` | CV composition plans over approved content |
| `authoring_briefs` | thin artifact-specific briefs |
| `application_case_projections` | JobSync-facing operational projections |
| `artifact_refs` | exported CV / letter / answer refs and provenance |
| `status_events` | mailbox/manual/application lifecycle signals |
| `outcome_feedback` | interviews, rejections, offers, dismissals tied back to decision context |
| `experiment_runs` | shadow runs, thresholds, prompt/ranker comparisons |
| `evaluation_samples` | holdouts, adjudication samples, false-negative review sets |

Storage rule:

- `JobPipe` should own this projection layer
- `JobSync` should not become the warehouse for raw job or triage internals
- `Reactive Resume` should not become the warehouse for workflow or ranking internals

### Logical Structure By Subsystem

If this is rewritten section by section, the clean subsystem split should be:

1. intake
   - connectors
   - staging
   - canonicalization
   - dedupe
2. person model
   - resume underlay
   - evidence atoms
   - narrative profile
   - targeting profile
3. decision engine
   - hard gates
   - triage features
   - first-pass ranking
   - ambiguity resolver
   - advantage assessment
   - narrative strategy
4. authoring
   - tailoring plan
   - authoring brief
   - saveback/export capture
5. workflow/sync
   - application case projection
   - JobSync sync seam
   - status/outcome ingestion
6. experimentation
   - shadow runs
   - calibration
   - eval sampling

This is the preferred rewrite order too, because it keeps the red line from source data to finished application visible at every step.

### Section-By-Section Rewrite Rule

Given the amount of inherited shape in JobPipe, future architectural cleanup should prefer bounded rewrites by subsystem:

1. intake
2. person model
3. decision engine
4. authoring/export
5. workflow/sync
6. experimentation

Recommended rewrite method:

- build the new section beside the old one
- switch one real consumer at a time
- validate
- demote or remove the old section quickly after the new path is proven

This is preferred over one big-bang rewrite and over endless patching of bloated mixed-purpose files.

### Experimentation And Calibration As First-Class Architecture

The product will need experimentation support as part of the runtime, not as a side habit.

That should eventually include:

- shadow scoring runs
- prompt/version comparison
- threshold experiments
- connector-policy comparison
- holdout review sampling
- false-negative review workflows
- outcome-linked calibration

Important rule:

- do not run naive experiments that hide strong matches from the user
- prefer shadow mode, replay evaluation, and reversible review sampling over live hidden treatment changes

### Current Cross-Repo Apply Slice

Topic 12 is now real as a minimal cross-repo implementation:

- JobPipe exposes `GET /api/apply_session/<job_id>` and persists `apply_session.json`
- JobSync exposes `POST /api/integrations/jobpipe/jobs` as a thin curated-import receiver
- imported JobSync tracked jobs now carry:
  - `externalSource`
  - `externalId`
  - `externalData`
- JobSync's job-details view can:
  - launch the JobPipe application workspace
  - fetch the live apply-session manifest
  - open the job-ad and application-portal URLs
  - show the deterministic saveback targets returned by JobPipe

This keeps the working seam narrow:

1. JobPipe remains the source of truth for analysis, drafting context, and saveback targets
2. JobSync remains the active tracked-job workspace
3. Reactive Resume and document authoring are still external tools, not embedded subsystems

Current environment seam:

- JobPipe -> JobSync import:
  - `JOBSYNC_SYNC_TOKEN`
- JobSync -> JobPipe apply launch:
  - `JOBPIPE_BASE_URL` or `NEXT_PUBLIC_JOBPIPE_BASE_URL`

## Intake Pipe Boundary

JobPipe now treats intake as a connector problem first.

There are two connector families:

1. `NAV` feed intake
2. mailbox-derived suggested leads (`FINN` today, `LinkedIn` later)

Mailbox recommendation intake and mailbox status updates are explicitly separate flows.

Lead intake flow:

```text
NAV feed
    ↓ Apps Script / Sheet bridge
Google Sheet
    ↓ pull_sheets_csv.py
NAV connector output

Gmail recommendation emails
    ↓ scan_gmail --scan-suggestions
reports/suggested_jobs.jsonl
    ↓ sync_mailbox_leads / pull_suggested
mailbox suggested-lead connector output

NAV connector output + mailbox suggested-lead connector output
    ↓ shared intake merge + dedupe
jobs_delta.jsonl
    ↓ run_feed.py
connector-aware deterministic filters -> triage -> rest of pipeline
```

Status-update flow:

```text
Gmail application emails
    ↓ scan_gmail
reports/application_state.json
    ↓ export_dashboard.py / JobPipe outward status normalization
dashboard + operator sync surfaces
```

Rules:

1. `NAV` and mailbox suggested leads remain separate connectors until the shared intake merge point
2. mailbox-derived status updates do not create new leads; they update application tracking state
3. the shared merged queue remains `jobs_delta.jsonl` in the current OSS runtime
4. lead-source specific scraping queues such as `suggested_jobs.jsonl` are staging inputs, not alternate pipeline lanes
5. dedupe must happen before the rest of the pipeline sees the merged jobs
6. when duplicates collide across sources, `NAV` is the pragmatic canonical record unless the suggested-lead variant is the only copy with materially missing fields filled in
7. source provenance must survive dedupe so the pipeline/debug surfaces still know the alternates

Deterministic pre-triage policy:

1. `NAV` feed jobs go through the normal deterministic gate stack
2. mailbox/platform-suggested leads bypass `geo` block
3. mailbox/platform-suggested leads bypass semantic pre-filter elimination
4. mailbox/platform-suggested leads must still be killed by `hard_no_title_regex`
5. surviving mailbox/platform-suggested leads go straight to triage review

Current implementation:

- `jobpipe/core/lead_intake.py` defines the versioned shared lead-connector metadata for mailbox/lead-style sources
- `jobpipe/cli/sync_mailbox_leads.py` is the settings-aware mailbox recommendation entrypoint
- `jobpipe/core/intake_pipe.py` now defines the explicit connector staging, shared merge + dedupe, and `NAV` canonical precedence rules for pre-pipe intake
- `pull_sheets_csv.py` now stages the broad `NAV` sheet-backed feed into `<data-root>/reports/nav_connector.jsonl` instead of writing directly into the merged queue
- `pull_suggested.py`, `pull_finn_search.py`, and `pull_finn_ext.py` now all write through lead-style connector staging in `<data-root>/reports/leads_connector.jsonl` before the pipeline sees the merged jobs
- `drain_queue.py` now rebuilds `<data-root>/jobs_delta.jsonl` from connector staging, processes the merged queue, and prunes consumed connector rows afterward
- `pull_suggested.py` already enriches `FINN` mailbox leads from the website before merge, but it does not yet do the richer delta-aware "reuse an existing partial record unless fields are missing" merge behavior

### Shared Workflow Status Model

JobPipe should keep richer internal state:

- `app_stages`
- `app_outcome`
- `app_notes`
- `events`

But expose one normalized `app_status` for integration and UI consumption when a connector needs it.

### JobPipe Status Normalization

Map current JobPipe stage/outcome detail to the shared status set:

- `shortlisted` -> `draft`
- `called` -> `draft`
- `applied` -> `applied`
- `interview` -> `interview`
- `second_interview` -> `interview`
- `accepted` -> `offer`
- `rejected` -> `rejected`
- `dismissed` -> `dismissed`

Normalization precedence:

1. terminal outcome wins
2. otherwise use the most advanced stage reached
3. collapse detailed stages into the shared workflow buckets above

This keeps JobPipe detail intact while avoiding duplicate meanings across systems.

### Integration Contract

The integration should use explicit external identity fields instead of fuzzy matching:

- `externalSource`
- `externalId`
- `externalStatusSource`
- `externalStatusAt`
- `externalStatusMeta`
- `syncMode`

If and when JobSync adds an import seam, it should treat JobPipe-imported jobs as externally identified records and upsert them by `[externalSource, externalId]`.

### Connector-First Compatibility Rule

To stay resilient against upstream JobSync changes, the real stable seam should sit on the JobPipe side of the boundary:

1. JobPipe emits a versioned connector envelope
2. a thin connector translates that envelope into whatever the current JobSync receiver expects
3. JobPipe does not depend on JobSync internals such as status row order, Prisma schema details, or UI assumptions

Current preferred envelope:

- `contractVersion`
- `producer`
- `kind`
- `sentAt`
- `userEmail`
- `jobs` or `events`

This keeps the core JobPipe contract stable even if:

- JobSync changes route names
- JobSync changes auth wiring
- JobSync changes field names internally

The connector can be:

- an HTTP bridge into JobSync
- an outbox reader that imports JSON files
- a future upstream JobSync plugin or endpoint implementation

For the current JobPipe implementation, the preferred seam is:

1. HTTP POST to a minimal receiver that accepts the versioned envelope
2. `--outbox-only` / local outbox files as the fallback when no receiver is available yet

That keeps the contract testable now without forcing immediate sibling-repo changes.

### Upstream-Friendly API Suggestion

If a patch is proposed upstream, prefer a small additive API instead of deep coupling:

1. `POST /api/integrations/jobpipe/jobs`
   Accept a versioned curated-job import envelope.
2. `POST /api/integrations/jobpipe/status`
   Accept a versioned application-status-sync envelope.
3. Authenticate with one integration token header, not an interactive session requirement.
4. Upsert only by `[externalSource, externalId]`.
5. Preserve local manual override if supported; external sync should update metadata without forcing status changes in override mode.

That is small enough to upstream without asking JobSync to adopt JobPipe pipeline logic or abandon its existing tracked-job workflow.

### Sync Directions

Phase 1:

- JobPipe -> JobSync curated job import as `new`
- optional JobPipe -> JobSync metadata sync that does not fight local workflow choices
- JobPipe -> external authoring surfaces through packet/artifact handoff

Phase 2:

- apply-time orchestration across JobSync + Reactive Resume + document drafting surface
- JobSync -> JobPipe manual status / notes writeback, only if needed after the one-way model is stable
- richer status harmonization, only if the minimal import flow proves insufficient

Do not start with full bidirectional field sync or a large status rewrite. Keep the seam narrow until the imported-workspace model is proven.

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

## Companion UI Split

The working target is not one monolithic dashboard. It is a split system with separate responsibilities.

### JobPipe UI

JobPipe should remain the control plane and setup surface. Grounded in the current codebase, it already has:

- `Jobs`
- `Pipeline`
- `Profile & CV`
- `Application Workspace`
- `Debug / Data`

From:

- `DASHBOARD_SPEC.md`
- `reports/dashboard_template.html`
- `reports/apply_template.html`
- `jobpipe/cli/dashboard_server.py`

The intended JobPipe page model should become:

1. Settings & Integrations
   API keys, Google/Gmail auth, NAV/Sheet setup, external tool links, profile-pack source, secrets.
2. Sources & Ingestion
   Feed health, Sheet visibility, raw import diagnostics, recommended-lead intake from email/Finn.
3. Triage Review
   Why a job passed or failed, score distributions, pipeline truth.
4. Profile & Resume Source
   Canonical resume/profile import, geo/domain/role targeting, Reactive Resume import/export touchpoints.
5. Sync Health
   JobSync export state, apply-packet health, mailbox sync truth.

The first implemented slice of that control plane is now live inside JobPipe's dashboard payload/runtime:

- versioned local settings state at `<data-root>/reports/settings_state.json`
- a `settings` payload object exposed by `build_payload()`
- a first-class `Settings / Integrations` page in the local dashboard shell

The next implemented slice is now live as well:

- the old top-pill dashboard shell is replaced by a sidebar app shell inside the shared local dashboard runtime
- a versioned `automations` payload object now exposes connector counts, action definitions, and recent local run history
- local automation state persists at `<data-root>/reports/automation_runs.json`
- the dashboard server now exposes `POST /api/automation/run` so connector/control-plane actions can be triggered one by one from the shell instead of hiding behind one massive pull
- the first automation-facing actions are intentionally narrow and local:
  - refresh NAV connector staging
  - mailbox lead intake dry run
  - rebuild the merged pre-triage queue
  - rebuild the dashboard export

This slice is intentionally narrow:

- editable targeting and connector state live in JobPipe
- secret values do not enter the payload
- mailbox ingestion and authoring automation still remain later topics
- the app shell remains part of the current local HTML/runtime surface rather than claiming a separate frontend-framework migration

JobPipe should not try to become the day-to-day application workspace.

### JobSync UI

Grounded in the current upstream JobSync route tree, the existing pages are:

- `/dashboard`
- `/dashboard/myjobs`
- `/dashboard/tasks`
- `/dashboard/activities`
- `/dashboard/questions`
- `/dashboard/profile`
- `/dashboard/settings`
- `/dashboard/admin`
- `/dashboard/automations`

Grounded in the current upstream app structure, JobSync already exposes pages for dashboard, tracked jobs, tasks, activities, questions, profile, settings, admin, and automations.

If adopted as the operator workspace, JobSync should own:

1. active application queue
2. notes and manual status work
3. tasks and follow-up
4. artifact links per job
5. day-to-day review of jobs already chosen for action
6. the `apply` launch point for opening links and kicking off external authoring flows

### JobSync As A Reference App, Not A Backend Dependency

The current JobPipe dashboard shell is still too close to a large report page with local-app behavior bolted on. JobSync demonstrates a more scalable app shape:

- app shell and route structure
- list/detail workflow
- wizard-driven configuration flows
- automation list, run history, and logs
- durable operator-facing CRUD patterns

That makes JobSync a strong reference point for the next JobPipe UI architecture.

But the reuse rule must stay narrow:

- reuse UI and workflow patterns where they fit
- do not assume JobSync automation internals can become JobPipe's discovery/triage backend

Grounded in the current sibling-repo audit, JobSync automations are tightly coupled to:

- JSearch as the discovery source
- JobSync resume records as the AI-match source of truth
- local AI provider settings and API keys
- JobSync's own `Automation`, `AutomationRun`, and discovered-job storage model

In the current local setup, the saved automation wizard flow works, but the actual run path is blocked because there are no stored API keys and the local env has empty `RAPIDAPI_KEY` and `OPENAI_API_KEY` values. That means the automation surface is proven as a UI pattern, not yet as a reusable backend for JobPipe.

The architecture rule for the next UI topic is therefore:

1. treat JobSync as a reference app shell
2. reuse layout and operations patterns deliberately
3. keep JobPipe pipeline, mailbox intake, and scoring logic owned by JobPipe
4. integrate across explicit contracts instead of collapsing JobPipe into JobSync internals

The same rule applies to Reactive Resume:

1. use it as the structured resume subsystem
2. feed profile/resume signal into the rest of the stack through explicit contracts, exports, or references
3. do not absorb resume-authoring internals into either JobPipe or JobSync unless there is a strong reason to take that ownership on purpose

### Reactive Resume Touchpoints

Reactive Resume should remain the external resume subsystem, not just a one-off export tool.

Grounded in the official docs, it provides:

- self-hosting with Docker
- JSON schema for structured resume data
- JSON and PDF export
- public share links and multiple resume variants

References:

- `https://github.com/AmruthPillai/Reactive-Resume`
- `https://docs.rxresume.org/self-hosting/docker`
- `https://docs.rxresume.org/guides/json-resume-schema`

The intended touchpoints are:

1. import a canonical resume/profile into JobPipe
2. create or edit CV variants in Reactive Resume
3. trigger tailored resume generation/editing from the active application case
4. link the relevant Reactive Resume variant or exported artifact back to the job record in JobSync

Reactive Resume should not become the workflow hub or replace JobSync.
It should be the source of `ResumeVariantRef` truth for the rest of the stack.

Grounded operation notes from the official docs:

- Reactive Resume self-hosting is documented as a Docker Compose stack with:
  - app
  - PostgreSQL
  - printer service
- the official docs treat `APP_URL`, `DATABASE_URL`, `PRINTER_ENDPOINT`, and `AUTH_SECRET` as required
- the current documented local URL example is `http://localhost:3000`
- the official JSON schema endpoint is `https://rxresu.me/schema.json`

This means JobPipe should integrate with Reactive Resume at the JSON/file/link layer, not by assuming it is a lightweight single-container sidecar.

### NAV / Sheets Bridge

The NAV -> Google Sheets -> JobPipe bridge should be treated as its own companion codebase.

Grounded in the current running architecture, JobPipe already assumes:

- NAV feed data lands in Google Sheets first
- JobPipe then pulls deltas into `<data-root>/jobs_delta.jsonl`

From:

- `pull_sheets_csv.py`
- `docs/gmail_filter_spec.md`
- the current runtime diagram in this file

That bridge is operationally important, but it is not part of the JobPipe runtime itself. The right boundary is:

1. separate Apps Script repo for:
   - NAV API fetch logic
   - Sheet write/update logic
   - script deployment/setup notes
2. JobPipe repo for:
   - consuming the exported Sheet/CSV contract
   - validating/importing the resulting feed

Do not mix Apps Script source into the JobPipe repo just because JobPipe depends on its output.

## Local Multi-Repo Operating Model

For easiest maintenance, keep each external project separate.

Recommended rule:

- separate git repos for active codebases
- separate deployment folders for Docker/env files when no source modifications are needed
- separate private data from repo checkouts

Why:

1. upstream updates stay simple
2. local changes are attributable to the correct project
3. you avoid turning JobPipe into an umbrella vendor repo

### Companion Revision Pins

When a JobPipe checkpoint depends on local sibling-repo state, record that dependency in `COMPANION_REVISIONS.json`.

Rules:

1. record sibling repo `remote`, `branch`, and `commit`, not copied source code
2. if a sibling change is local-only, checkpoint it in the sibling repo itself before updating the JobPipe pin file
3. use the JobPipe commit plus `COMPANION_REVISIONS.json` as the auditable stack baseline
4. do not treat the pin file as permission to widen the integration seam or vendor upstream code into JobPipe

Current JobPipe-side verification seam:

- `python -m jobpipe.cli.check_companion_revisions --strict`

That command checks the pinned local path, git identity, branch, commit, and dirty state for each recorded companion repo before broader stack validation.

Recommended local layout:

```text
<workspace-root>/
  agentic_jobpilot/         # this repo
  jobsync/                  # sibling repo if you customize JobSync
  reactive-resume/          # optional sibling repo if you customize it
  nav-jobpipe-sheet-sync/   # sibling repo for Apps Script + Sheet/NAV bridge
  stacks/
    jobsync-local/          # compose/env/data if only deploying JobSync
    reactive-resume-local/  # compose/env/data if only deploying Reactive Resume
```

This is a standard polyrepo workflow. Developers usually work with sibling repos plus one parent workspace folder, not by nesting unrelated upstream repositories inside the main application repo.

### Install And Run Order

For a clean local operator setup, bring the systems up in this order:

1. JobPipe
   - validate current pipeline/export/server behavior first
   - this repo already has the local-first path contract in `jobpipe/core/paths.py`
   - the local UI is served by `jobpipe/cli/dashboard_server.py`
2. JobSync
   - install and validate as a separate app
   - the upstream README quickstart is `git clone`, `cd jobsync`, `docker compose up`
   - the current upstream compose uses port `3737`, SQLite at `file:/data/dev.db`, and persistent volume `./jobsyncdb/data:/data`
3. Reactive Resume
   - install and validate separately
   - the official self-hosting guide uses Docker Compose with app + Postgres + printer
   - the documented local example URL is `http://localhost:3000`

Do not start by wiring the stack together. Validate each project independently, then add the integration seam.

### Repo Versus Deployment Folder

Use this rule set:

1. If you will change source code, keep a sibling repo.
2. If you only need to run the app, keep a deployment folder with compose/env/volume data.
3. Do not copy upstream code into `agentic_jobpilot` unless you intend to fork and own long-term divergence.
4. If a JobPipe checkpoint depends on sibling changes, record the sibling SHA in `COMPANION_REVISIONS.json`.

For the current plan, that means:

- `agentic_jobpilot/` stays its own repo
- `jobsync/` should be a sibling repo if you add JobPipe integration endpoints or UI changes
- `reactive-resume/` does not need to be cloned unless you decide to customize it beyond stock self-hosting and JSON import/export
- `nav-jobpipe-sheet-sync/` should be a separate repo for Apps Script development and deployment

### Boundary Enforcement Rules

To keep the repos clean during development:

1. exchange data only through explicit seams
   - Google Sheet / CSV / JSONL
   - HTTP integration endpoints
   - artifact links / IDs
2. do not copy source modules across repos
3. keep deployment/runtime files with the app that owns them
4. keep private state out of every repo and inside mounted/local data directories

Practical examples:

- JobPipe may document the Sheet contract, but it should not contain the Apps Script implementation
- JobSync may expose import/status endpoints, but it should not embed JobPipe stage logic
- Reactive Resume may be linked/imported via JSON, but it should not become the source of pipeline truth
- future JobPipe containerization should mount `JOBPIPE_DATA_ROOT` instead of relocating private state into the image

## Validation Standard

A change is not done until these hold:

- field origin is documented
- field owner is clear
- field survives to ledger or is intentionally excluded
- dashboard reads explicit values instead of inferring from gaps
- tests cover the contract where code exists
