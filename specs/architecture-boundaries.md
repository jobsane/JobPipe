# Architecture Boundaries

**Last updated:** 2026-04-30

This spec defines the architectural boundaries the next implementation pass should follow.

It is not a request to immediately rewrite the codebase. It is the boundary contract the repo should now inherit.

Canonical planning sources:

- [../MASTER_PLAN.md](../MASTER_PLAN.md)
- [../OSS_SCOPE.md](../OSS_SCOPE.md)
- [../DEPENDENCY_POLICY.md](../DEPENDENCY_POLICY.md)
- [canonical-data-model.md](canonical-data-model.md)

---

## Purpose

The goal of this pass is to lock:

- public package and module boundaries
- runtime storage boundaries
- the OSS/private seam
- the target repo structure the public repo should move toward
- the migration order required to get there safely

The goal is **not** to force a clean-slate rewrite.

---

## Settled truths this spec inherits

These decisions are already settled and should not be reopened in the next implementation pass:

- JobPipe remains the umbrella project name.
- JobPipe remains the public OSS/framework name.
- A later private/commercial implementation may be named **JobPipe Workbench**.
- JobPipe is a candidate-first, hiring-aware, local-first career intelligence workbench.
- The product mechanism is:
  - structured evidence
  - explicit decision support
  - living monitoring
  - better action
- Data is the product.
- Connectors are adapters.
- Dashboards and external tools are projections.
- AI is a bounded interpretation layer, not the operational control plane.
- The near-term product substrate is:
  1. job claims
  2. hiring-aware decision tables / selection signals
  3. candidate evidence units
  4. candidate narrative profiles
  5. watchlists / change events

---

## Architecture goals

The architecture should now optimize for:

1. a clean public OSS foundation
2. low-friction local-first operation
3. strong canonical state boundaries
4. thin connector boundaries
5. inspectable decision outputs
6. a future premium/private layer that can sit on top cleanly
7. incremental migration from the current codebase

---

## Canonical public package slices

The public repo should converge toward seven architectural slices.

### 1. `jobpipe/cli`

Purpose:

- canonical operator interface
- thin command surfaces
- no durable business logic

Rules:

- keep commands thin
- parse args, call public runtime/services, exit
- do not accumulate connector-specific logic here over time

### 2. `jobpipe/runtime`

Purpose:

- paths
- config loading
- DB lifecycle and migrations
- canonical intake and cross-source dedup services
- runner orchestration
- compatibility/export helpers
- shared IO and storage coordination

Current mapping:

- mostly lives inside `jobpipe/core/paths.py`, `config.py`, `io.py`, `runner.py`, `job_catalog.py`, and parts of `primary_db.py`

Why this needs a distinct slice:

- the current `core/` package mixes runtime concerns with domain/model concerns

### 3. `jobpipe/model`

Purpose:

- canonical public domain model
- schemas for core state
- stable public object vocabulary

This should own the durable public shapes for:

- candidate
- candidate profile
- canonical job
- source record
- job evaluation
- application events/summary
- generated documents
- claims
- selection signals
- decision tables
- evidence units
- narrative profiles
- watchlists/change events

Current mapping:

- split today across `jobpipe/core/schema.py`, `primary_db.py`, and specs

### 4. `jobpipe/connectors`

Purpose:

- source access
- fetch
- parse raw source payloads
- normalize into canonical source records

Rules:

- stop at normalization
- do not own candidate-specific decision logic
- do not own final ranking logic
- do not own dashboard/export behavior

Expected sub-slices:

- `connectors/nav`
- `connectors/finn`
- `connectors/mail`
- generic file/feed helpers

Current mapping:

- much of this still lives inside `jobpipe/cli/*`

### 5. `jobpipe/decision`

Purpose:

- interpretation layers that transform canonical data into explicit candidate-facing decision state

This slice should absorb the next product substrate:

- claims
- hiring-aware selection logic
- decision tables
- evidence selection logic
- narrative assessment logic
- monitoring/change interpretation

Current mapping:

- currently spread across `jobpipe/stages/*` and prompt-shaped runtime behavior

Current first implementation slice:

- deterministic `job_claims`
- deterministic `selection_signals`
- deterministic `selection_assessment`
- deterministic `decision_table`
- deterministic `candidate_evidence_units`
- deterministic job-specific evidence selection
- deterministic `candidate_narrative_profile`
- deterministic `job_narrative_assessment`
- deterministic `watchlists`
- deterministic `change_events`
- deterministic `candidate_calibration_summary`
- deterministic `job_calibration_assessment`
- public derivation helpers consumed by the dashboard export path
- public evidence-selection helpers consumed by `application_pack`
- public narrative helpers consumed by `application_pack`
- persistence adapters that promote job claims, selection state, decision tables, watchlists, and change events through `sync_evaluations`
- persistence adapters that promote candidate evidence and narrative state through `application_pack`

Important rule:

- this slice owns **decision semantics**
- it should not own raw source access or projection rendering

### 6. `jobpipe/projections`

Purpose:

- dashboard export
- report export
- document export
- future public example/demo surfaces

Rules:

- consume canonical state
- do not become the source of truth
- do not hide business logic that should live in `decision/`

Current mapping:

- dashboard projection logic now lives in `jobpipe/projections/dashboard.py`
- `jobpipe/cli/export_dashboard.py` remains a thin compatibility wrapper for the command surface

### 7. `jobpipe/compat`

Purpose:

- compatibility shims for legacy file names, old CLI behavior, or transitional exports

Why:

- the migration should be incremental
- compatibility should be explicit rather than hidden in random path logic

This slice may remain small, but naming it explicitly makes transition work easier to isolate and later remove.

---

## Transitional mapping from the current codebase

Current public package layout is still:

- `jobpipe/cli`
- `jobpipe/core`
- `jobpipe/stages`
- `jobpipe/runtime`
- `jobpipe/model`
- `jobpipe/decision`
- `jobpipe/projections`
- `jobpipe/connectors`

That is acceptable as a transitional shape, but it is not the clean long-term public boundary model.

### Transitional interpretation

- `cli/` stays
- `core/` is transitional and should be gradually split into:
  - `runtime/`
  - `model/`
  - small remaining compatibility helpers if needed
- `stages/` stays temporarily as the execution surface for the current pipeline, but should gradually give up durable product semantics to `decision/`
- current stage-builder wiring belongs in `jobpipe/stages/pipeline.py`, not in `jobpipe/runtime/`
- `runtime/` must stay below the execution surface and must not import `jobpipe.stages.*`

This means the next implementation work should prefer:

- new stable model logic -> `model/`
- new storage/runtime logic -> `runtime/`
- new source logic -> `connectors/`
- new decision semantics -> `decision/`
- new export/rendering logic -> `projections/`

and avoid continuing to enlarge `core/` as a catch-all.

---

## Runtime storage boundaries

The intended runtime boundary remains `JOBPIPE_DATA_DIR`.

Canonical external data roots:

- `db/`
- `artifacts/`
- `exports/`
- `documents/`
- `cache/`
- `secrets/`

Rules:

- repo = code, docs, specs, templates, examples
- external data root = user state, runtime state, generated artifacts, credentials, caches

Transitional compatibility:

- `reports/` and `out_runs/` may still exist in the repo during migration
- they should be treated as compatibility/default fallback names, not as target architecture

---

## OSS / private seam

The public repo should expose stable interfaces and baseline implementations.

The later private/commercial layer should add premium implementations on top of those interfaces.

### Public should own

- canonical models
- runtime boundaries
- baseline connector interfaces
- baseline projection interfaces
- baseline decision object structures
- thin public command surfaces
- public examples and fixtures

### Private may own later

- tuned policy packs
- premium ranking heuristics
- calibration assets and learned defaults
- sensitive connectors
- premium workflow bundles
- premium UX and packaging

### Seam design rule

The public repo should own the **interfaces and default baseline behavior**.

The private layer should own **better policies and premium implementations**, not alternate schemas or a different product story.

That seam is the architectural protection against open-core confusion.

Current authoring seam:

- `jobpipe/authoring/` owns the public authoring adapter contract, case context, output model, validation, persistence, and simple/local author implementation.
- `jobpipe_crewai/` is an optional CrewAI implementation outside `jobpipe/`.
- `jobpipe/` may dynamically import `jobpipe_crewai` through the author factory when requested, but it must not statically import CrewAI or make CrewAI a core runtime requirement.

---

## Public extension points

The architecture should preserve public extension points in four places:

1. connectors
2. decision policies
3. projections
4. local runtime/configuration

Extension points should be:

- explicit
- documented
- testable
- independent of private code

The public repo should never require private modules to remain coherent.

---

## Dependency shape

The public architecture should follow the dependency policy already set:

- use maintained permissive OSS directly for generic infrastructure
- wrap third-party runtimes where JobPipe should own the public abstraction
- build custom where product differentiation lives

This means:

- the public architecture should not expose an agent framework or document renderer as its canonical interface
- those should sit behind JobPipe-owned slices

---

## Target public repo structure

The public repo should converge toward a structure like this:

```text
jobpipe/
  cli/
  runtime/
  model/
  connectors/
  decision/
  projections/
  compat/
configs/
docs/
specs/
tests/
examples/         # later, public showcase/demo fixtures
```

Important note:

- this is a target boundary model, not an instruction to move every file immediately

---

## Recommended migration sequence

### Step 1. Lock naming and runtime roots

Deliver:

- `JOBPIPE_DATA_DIR` as the intended runtime boundary
- canonical naming around `artifacts/`, `exports/`, `documents/`
- compatibility handling isolated more explicitly

### Step 2. Introduce new boundary slices without deleting old ones

Deliver:

- create empty or minimal `runtime/`, `model/`, `connectors/`, `decision/`, `projections/`, `compat/` packages as needed
- route only new work into them first

### Step 3. Move source-specific logic out of CLI modules

Deliver:

- mail/Gmail logic begins moving to `connectors/mail`
- NAV/FINN ingestion begins moving to connector slices

### Step 4. Move canonical schemas and stable model code out of `core/`

Deliver:

- durable public state shapes consolidated in `model/`
- DB/runtime orchestration logic stays in `runtime/`

### Step 5. Build the decision substrate in the new slice

Deliver:

- `job_claims`
- `job_selection_signals`
- `job_decision_tables`
- evidence and narrative assessments

### Step 6. Move export/rendering logic behind projection boundaries

Deliver:

- dashboard/report/document rendering moved toward `projections/`
- projection assets separated from generated outputs

### Step 7. Collapse or shrink transitional packages later

Deliver:

- `core/` shrinks materially or becomes compatibility-only
- `stages/` becomes an execution surface over `decision/`, not the home of all durable reasoning semantics

---

## What should remain deferred

Do not do these in the architecture pass itself:

- full repo split into public/private repos
- rewrite every CLI or connector in one pass
- rename every module purely for aesthetics
- introduce a server-first architecture
- introduce vector-db-first architecture
- build premium/private-only code paths in the public repo

---

## Success criteria

This architecture pass is successful if:

- the public repo now has a clear target package boundary model
- the OSS/private seam is technically legible
- runtime roots are unambiguous
- the refactor sequence is incremental and practical
- new implementation work can stop enlarging `core/` and `cli/` in the wrong directions

If future implementation follows this spec, the repo should become easier to maintain, easier to extend publicly, and easier to build a later private layer on top of without another reset.
