# Module Ownership

This file is the short ownership map for the current public JobPipe repo.

Use it to answer:

- which package owns a capability today
- whether a path is canonical, transitional, or compatibility-only
- what kinds of edits are safe in that path

Read this together with:

- [docs/architecture.md](C:/Users/larsv/Jobpipe-codex-v2/docs/architecture.md)
- [docs/decision-model.md](C:/Users/larsv/Jobpipe-codex-v2/docs/decision-model.md)
- [MASTER_PLAN.md](C:/Users/larsv/Jobpipe-codex-v2/MASTER_PLAN.md)

Status meanings:

- `canonical`: target public ownership boundary
- `transitional`: live code path, but not the desired long-term home
- `compat`: bridge or shim surface; avoid enlarging it
- `projection`: read/export surface built on canonical state

| Path | Architectural role | Status | Common mistake | Safe changes |
|---|---|---|---|---|
| `jobpipe/model/` | Canonical schema and domain-model boundary | canonical | Adding runtime logic or pipeline orchestration here | Schema clarification, type cleanup, contract docs |
| `jobpipe/decision/` | Canonical decision substrate: claims, selection, decision table, evidence, narrative, monitoring, calibration | canonical | Re-implementing these concepts in `stages/` or `projections/` | Deterministic logic, persistence adapters, decision-model tests |
| `jobpipe/projections/` | Read/export layer over canonical state | projection | Writing new source-of-truth state here | Projection shaping, export formatting, dashboard read models |
| `jobpipe/runtime/` | Canonical runtime roots and storage-boundary logic | canonical | Adding product semantics that belong in `decision/` or `model/` | Path helpers, catalog/runtime boundary cleanup, adapter surfaces |
| `jobpipe/connectors/` | Provider adapters and input normalization | canonical | Letting connector-specific behavior become product logic | Provider/session helpers, parsing, normalization, connector tests |
| `jobpipe/cli/` | Canonical operator interface and thin orchestration layer | canonical | Hiding core product logic directly in CLI modules | Argument parsing, orchestration, thin wrappers over owned modules |
| `jobpipe/core/` | Transitional shared IO, DB helpers, legacy ownership, compat shims | transitional | Treating it as the permanent home for new product logic | Narrow bug fixes, extraction into `runtime/` or `model/`, compat preservation |
| `jobpipe/stages/` | Evaluation pipeline execution order and stage orchestration | transitional | Expanding stage-local logic that should live in `decision/` | Stage wiring, prompt/stage behavior, narrow pipeline fixes |
| `jobpipe/compat/` | Reserved compatibility boundary | compat | Building new features here | Only explicit compatibility shims |
| `configs/` | Runtime thresholds, stage order, model choices, rules | canonical | Treating config changes as no-risk text edits | Threshold/routing edits with validation and explicit review |
| `docs/` | Runtime/operator explanation and architecture memory | canonical | Duplicating backlog or stale branch-specific instructions | Architecture docs, operator docs, cleanup maps |
| `specs/` | Forward-looking design targets and seam specs | canonical | Treating every spec as already implemented truth | Active-spec maintenance, seam planning, future design notes |

## Active package notes

### `jobpipe/model`

- Keep it narrow.
- This should describe JobPipe's objects, not orchestrate workflow.

### `jobpipe/decision`

- This is where durable product meaning should accumulate.
- If a change modifies candidate/job interpretation, check whether it belongs here before touching `stages/`.

### `jobpipe/projections`

- Projection code should consume canonical state and shape outputs.
- It should not become an alternate decision engine.

### `jobpipe/runtime`

- Runtime ownership is still being pulled out of `core/`.
- Prefer new path/root/catalog cleanup here instead of enlarging `core/`.

### `jobpipe/cli`

- Commands should stay thin.
- If a CLI module needs heavy logic, extract that logic into the owning package first.

### `jobpipe/core`

- This is the biggest AI-edit trap in the repo.
- Many files are live, but several are transitional and should not become the default home for new work.

### `jobpipe/stages`

- Stages are still on the live path.
- That does not make them the canonical owner of every concept they currently touch.

## Current worktree caveat

This worktree contains `jobpipe/authoring/` and `jobpipe_crewai/` directories only as local `__pycache__` leftovers; there are no tracked source files there in the current `main` worktree state.

Treat those directories as absent for ownership purposes in this worktree until real tracked source files exist again.
