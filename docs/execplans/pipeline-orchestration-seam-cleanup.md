# Pipeline Orchestration Seam Cleanup — Execplan

**Goal:** Reduce ambiguity in the live pipeline orchestration seam across
`jobpipe/cli/run_feed.py`, `jobpipe/core/runner.py`, and
`jobpipe/stages/reverse_triage.py` without casually changing pipeline
semantics.

**Status:** Planning ready. Do not start runtime implementation until a GitHub
Project #6 item exists for this slice.

**Related docs:**
- `MASTER_PLAN.md`
- `PRODUCT_VISION.md`
- `ROADMAP.md`
- `OSS_SCOPE.md`
- `DEPENDENCY_POLICY.md`
- `docs/ai-playbook.md`
- `docs/module-ownership.md`
- `docs/live-paths.md`
- `docs/deprecation-map.md`

---

## Why This Slice Exists

This is the highest-confusion seam in the repo for AI-assisted and human edits.

Today:
- `jobpipe/cli/run_feed.py` owns stage assembly, DB run bookkeeping, per-job
  execution, and post-run index repair.
- `jobpipe/core/runner.py` is still a live execution dependency, not dead glue.
- `jobpipe/stages/reverse_triage.py` is config-disabled by default but still
  live in code, schema, and sync assumptions.

This is a boundary-cleanup slice, not a behavior-invention slice.

---

## Current Evidence

**Live references already verified:**
- `jobpipe/cli/run_feed.py` imports `PipelineRunner` and `Stage` from
  `jobpipe/core/runner.py`
- `jobpipe/cli/run_feed.py` imports
  `reverse_triage_stage_factory` from `jobpipe/stages/reverse_triage.py`
- `jobpipe/cli/sync_evaluations.py` still loads reverse-triage artifacts
- `jobpipe/model/schema.py` still carries reverse-triage state
- `configs/pipeline.v1.yaml` comments out `reverse_triage` in the active stage
  list but keeps reverse-triage thresholds/settings

**Implication:**
- `run_feed.py` is still the live feed entrypoint and orchestration
  concentration point
- `core/runner.py` is still a live execution utility
- `reverse_triage.py` is not dead code; it is an inactive-by-default optional
  stage

---

## Scope

### In Scope
- Clarify and tighten ownership of stage assembly
- Thin `jobpipe/cli/run_feed.py` where possible without changing behavior
- Reassess whether `jobpipe/core/runner.py` is in the right boundary for now
- Make `reverse_triage` status explicit: supported optional stage vs retirement
  candidate
- Update docs if classifications change

### Out of Scope
- Decision-model rewrite
- Threshold tuning
- New stage semantics
- Schema migrations
- Authoring / crewAI work
- Connector changes
- Broad cleanup across unrelated `core/` or `cli/` modules

---

## Guardrails

Treat these as escalation points, not cleanup opportunities:
- stage order changes
- stage enable/disable defaults
- artifact numbering or naming changes
- DB run bookkeeping behavior changes
- sync artifact contract changes
- reverse-triage removal from schema, sync, and config in a partial state

If a change affects pipeline semantics, stop and escalate before implementing.

---

## Recommended Slice Shape

### Phase 1 — Freeze Current Behavior

1. Capture current responsibilities explicitly:
   - `run_feed.py`: config loading, stage-order normalization, stage assembly,
     run directory creation, DB bookkeeping, per-job execution, post-run index
     repair
   - `core/runner.py`: `Stage` shape, stage execution, artifact reload/write,
     index append behavior
   - `reverse_triage.py`: optional stage factory, skip/revive behavior, schema
     coupling
2. Run a focused validation baseline before moving code:
   - targeted tests for touched modules
   - `python compile_check.py`
   - bounded smoke path if direct tests are missing

### Phase 2 — Separate Assembly From Execution

1. Extract stage assembly out of `jobpipe/cli/run_feed.py`
2. Keep `run_feed.py` as a thinner CLI/orchestration entrypoint
3. Preserve stage alias/default order behavior unless explicitly changed

**Default recommendation:** move stage-construction logic first; do not move
`PipelineRunner` in the first pass unless the new owner is clearly better.

### Phase 3 — Make `reverse_triage` Status Explicit

Choose one of:
- **Keep:** treat `reverse_triage` as a supported optional stage, config-disabled
  by default
- **Retire:** remove it in one coordinated slice across config, code, schema,
  and sync

**Default recommendation:** keep it as supported optional stage for now. Do not
retire it opportunistically inside the orchestration cleanup pass.

### Phase 4 — Isolate Operational Helpers

If it materially reduces ambiguity without changing behavior:
- isolate post-run index repair into a named helper
- isolate DB pipeline-run bookkeeping into narrow helpers

These are readability moves, not semantic moves.

### Phase 5 — Update Repo Maps

If the implementation lands:
- update `docs/module-ownership.md`
- update `docs/live-paths.md`
- update `docs/deprecation-map.md`

---

## Validation

Minimum validation for the runtime slice:
- targeted tests for touched modules
- `python compile_check.py`
- bounded feed-path smoke test relevant to the seam

If artifact layout or sync assumptions are touched:
- explicitly verify `jobpipe/cli/sync_evaluations.py` still matches the runtime
  artifact contract

---

## Acceptance Criteria

- `jobpipe/cli/run_feed.py` is thinner or has materially clearer ownership
  boundaries
- `jobpipe/core/runner.py` is either intentionally retained in place or moved
  with a clearer owner boundary
- `jobpipe/stages/reverse_triage.py` has an explicit status, not an accidental
  half-supported state
- pipeline semantics are unchanged unless explicitly approved
- the repo maps are updated if classifications changed

---

## Stop Gate

Do not start implementation until:
1. a GitHub Project #6 item exists for this slice, and
2. the worker prompt links to that item explicitly

This execplan is planning-only until that gate is satisfied.
