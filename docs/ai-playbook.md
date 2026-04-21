# AI Playbook

This is the shared operating workflow for AI-assisted JobPipe work.

`PRODUCT_VISION.md` is the canonical product vision. `docs/vision.md` is only a
short orchestrator-facing adapter.

## Default Workflow

1. Confirm repo state with `git status --short` and `git branch --show-current`.
2. Read the canonical planning spine listed in `AGENTS.md` or `CLAUDE.md`.
3. Read `docs/current-state.json`.
4. Read the relevant task file in `docs/execplans/`.
5. Choose one coherent next step.
6. Implement or review only that step.
7. Run the relevant validation.
8. Update live state, task notes, or durable decisions when the work changes them.

Do not start a new sprint or topic on top of unclear git state. Classify unclear
state as active sprint work, unfinished prior sprint work, unrelated user work,
or unexpected drift before proceeding.

## Worker Split

- Claude Desktop is the planner, orchestrator, and reviewer.
- Codex Desktop is the implementation worker.
- Claude maps ambiguity, chooses the next safe step, and reviews evidence.
- Codex implements approved changes, keeps diffs narrow, and reports exact test
  results.

## Worker And Model Routing

Model tier defaults, tuned for cost/effect against JobPipe operation scope.

| Operation | Worker | Model tier | Extended thinking |
|---|---|---|---|
| Coordinator routing, decomposition, cross-doc audit | Claude Desktop (planner) | Opus | On |
| Spec / PRD / acceptance-criteria drafting | Claude Desktop or Claude Code | Opus when fuzzy, Sonnet when scoped | On for review, off for first draft |
| Code review of a Codex PR | Claude Desktop or Claude Code | Sonnet | On |
| Docs-only cleanup, drift reconciliation | Claude Desktop or Codex | Sonnet | Off |
| Approved-slice implementation | Codex | GPT-5 default; GPT-5 mini only for rename/format diffs | n/a |
| Debugging with nonlocal cause | Codex | o-series reasoning | n/a |
| Commit messages, PR bodies, standups, stakeholder notes | Either | Sonnet; Haiku for mechanical formatting | Off |

Defaults:

- Start on Sonnet for clearly scoped work. Step up to Opus when the redo cost
  of a wrong answer exceeds the token cost.
- Turn on extended thinking for coordinator routing, cross-doc audit, code
  review, and acceptance-criteria writing. Off for drafting, summarizing, and
  formatting.
- Step down to Haiku only on mechanical transforms with a cheap oracle (test,
  schema, diff check) that will catch errors fast.

Hard lines - no tier drop, always Opus with extended thinking:

- auth, billing, migrations, deployment, secrets, destructive deletes
- pipeline semantics, scoring, selection logic
- OSS/Workbench boundary changes
- model-cost changes

These surfaces are also escalation gates under `## Approval Gates`; this
section only states that a cheaper tier must not be used on them.

## Branch And Worktree Rules

- One task should have one lead worker and one owned branch.
- Claude branches use `claude/<task-id>-<slug>`.
- Codex branches use `codex/<task-id>-<slug>`.
- Orchestration branches may use `ops/<slug>`.
- If both clients contribute code, integrate through an explicit merge branch or
  reviewed PR flow.
- Do not edit another worker's branch unless explicitly instructed.
- Never commit directly to `main`.

The current local worktree layout is recorded in `docs/current-state.json` and
task-specific setup notes belong in `docs/execplans/`.

## Change Rules

- Prefer the smallest safe change.
- Keep diffs focused and reversible.
- Avoid unrelated edits and broad refactors during narrow fixes.
- Do not add dependencies unless necessary and justified against
  `DEPENDENCY_POLICY.md`.
- Do not change architecture casually; planning and runtime truth should move
  together.
- Preserve traceability in pipeline behavior, state writes, and exported outputs.
- Keep private data, credentials, runtime DBs, caches, artifacts, and generated
  documents out of git.
- Keep `prototype/` out of git unless a task explicitly promotes something into
  the product tree.

## Approval Gates

Require explicit approval before:

- database schema changes
- auth, session, or permission changes
- billing or payment logic changes
- deployment or infrastructure config changes
- secret handling changes
- destructive deletes or resets
- analytics or privacy changes
- public API breaking changes
- material pipeline-semantic changes
- material model-cost changes
- OSS/private boundary changes

Risk labels:

- Green: safe to proceed within the approved scope.
- Yellow: proceed carefully and summarize before merge.
- Red: stop and escalate before action.

## Validation And Evidence

For meaningful code changes:

1. Run the most relevant targeted test.
2. Run `python compile_check.py`.
3. Run a smoke path on a small fixture or dry-run path when relevant.
4. Confirm output format is unchanged unless intentionally updated.

Preferred smoke path:

```text
jobpipe run --dry-run
```

Fallback:

```text
python -m jobpipe.cli.main run --dry-run
```

Windows wrapper:

```powershell
.\go.ps1 -DryRun
```

For docs and planning changes, verify that root docs, `OSS_SCOPE.md`,
`DEPENDENCY_POLICY.md`, architecture specs, active specs, and roadmap sequencing
do not contradict each other.

Do not say work is validated unless the exact commands were run and reported.
Do not say the repo is clean unless `git status --short` was checked.

## Handoff Rules

- Update `docs/current-state.json` for live task status, current branch, risks,
  blockers, and next decisions.
- Update `docs/execplans/<task>.md` for task-specific scope, plan, validation,
  rollback, and handoff notes.
- Update `docs/decisions.md` for durable decisions and rationale.
- Do not use `AUDIT.md` or `AGENT_STATUS.md` as active canonical instruction
  sources; treat them as historical recovery material unless explicitly
  revalidated.

## GitHub Project execution board

GitHub Project #6 is the canonical execution board for JobPipe.

Operating rules:

- Every implementable task should exist as a GitHub issue or draft issue on
  Project #6 before Codex starts code work.
- Planner output must reference the GitHub issue or project item when one
  exists.
- PRs should link back to the corresponding issue.
- `docs/current-state.json` and `docs/execplans/*` remain the repo-local
  memory layer; project status of record lives on Project #6.
- If a task is not yet on Project #6, stop and ask the founder whether to
  create a draft issue or a full issue.

Repo-doc rules:

- Do not duplicate the full backlog tree into repo markdown.
- Mirror only durable product direction or high-level roadmap consequences
  into repo docs.

Coordinator output schema (use for all routing turns):

    TASK CLASSIFICATION:
    GITHUB PROJECT ITEM STATUS:
    CHOSEN WORKER:
    BRANCH NAME:
    ONE-STEP OBJECTIVE:
    CONTEXT FILES:
    SUCCESS CRITERIA:
    TESTS REQUIRED:
    APPROVAL STATUS:
    EXACT WORKER PROMPT:

`GITHUB PROJECT ITEM STATUS` values: `Linked: #<number>`, `Draft: <id>`,
`Pending creation`, or `Not required (planning-only)`.

Detailed governance lives in
`specs/github-workflow-governance-audit-2026-04-21.md`.

## PR target branch

Since Op 2 (2026-04-21, see `docs/decisions.md`), PRs target `main` directly.
The `codex/job-catalog-foundation*` private lanes are retired. Do not open PRs
against those branches.

## Slice Brief Self-Review (planner runs before handing up to coordinator)

Before the planner worker sends a slice brief + Codex prompt to the
coordinator, the planner must pass every item below. If any item fails, fix
the brief before sending. Sending a brief that fails these is a routing
violation.

1. **Scope**: one slice, single-file or two-file diff preferred. Anything
   larger requires an explicit "why smaller won't work" sentence.
2. **Canonical-source map**: every field the slice introduces is mapped to
   its existing canonical source (or explicitly marked "new canonical field").
   No parallel truth models.
3. **Escalation gates named**: the brief lists every Approval Gate from
   `docs/ai-playbook.md` §Approval Gates the slice could plausibly touch, and
   asserts none are tripped. If one is tripped, stop — coordinator decides.
4. **Contract purity (T002 only)**: if the slice touches authoring contracts,
   acceptance criteria include "no `crewai` import in module or tests," with
   an automated check (import assertion or CI grep).
5. **Tests**: targeted test named, pattern matches existing proven tests in
   the same area. Python 3.14 + anyio workaround is respected where relevant
   (`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 -p no:debugging -p no:cacheprovider`).
6. **Reversibility**: single commit, clean revert path, no migration, no
   runtime state changes. If not reversible, flag as Yellow/Red and escalate.
7. **GitHub Project link**: the slice has a Project #6 item (draft or
   issue). Coordinator output schema (`GITHUB PROJECT ITEM STATUS`) is
   populated.
8. **Prompt self-containedness**: the Codex prompt contains everything Codex
   needs — file paths, acceptance criteria, escalation gates, out-of-scope
   list, test commands. Codex should not need to re-read multi-file planning
   context to implement.

If all eight pass, hand up. If one fails, fix or escalate.

## Codex Worker Prompt Template

The planner uses this as the starting shape for every Codex prompt. T001
Slice 1's prompt is the reference implementation.

```
CONTEXT
- Task: <T-ID> slice <N>
- Governing spec(s): <path>
- GitHub Project item: <id or number>
- Branch: codex/<task-id>-<slug>
- Base: main

GOAL
- <one sentence, no ambiguity>

IN SCOPE
- <exact files to create or touch>
- <exact shapes to produce>

OUT OF SCOPE (explicit no-go list)
- <do not touch these files>
- <do not add these dependencies>
- <do not expand into these parked issues>

CONSTRAINTS
- <e.g., no `crewai` import in contract modules>
- <e.g., Python 3.14 + anyio test workaround applies>
- <e.g., reuse canonical source X, do not parallel-model>

ACCEPTANCE CRITERIA
- <test name(s) pass>
- `python compile_check.py` succeeds
- <automated rule check, e.g., grep/import assertion>
- <output shape matches governing spec field table>

VALIDATION COMMANDS (run exactly these)
- <command 1>
- <command 2>

ESCALATION GATES
- Stop and ask the coordinator before: <list specific to this task>
- Stop and ask before any Approval Gate from docs/ai-playbook.md
  §Approval Gates

DELIVERABLE
- One commit on branch codex/<task-id>-<slug>
- PR into main, linked to Project #6 item
- Report: commands run, test output, files touched, any surprises
```

The planner should not invent new sections. If a section does not apply,
write `N/A` under it rather than delete it — reviewers scan the same shape
across slices.

## Sprint Loops

A **sprint** is a sequence of slices from one governing spec, inside one MVP
scope, that planner and Codex can chew through without a coordinator
re-routing turn per slice. The coordinator sets the sprint goal + slice
ordering once in the task execplan; the rest runs on the loops below.

### Planner standing loop (per slice, inside an active sprint)

1. Read the governing spec + task execplan + Slice Brief Self-Review.
2. Pick the next slice from the sprint's ordered list.
3. Run Slice Brief Self-Review. If any item fails → stop and ping coordinator
   with a one-paragraph routing question. Do not draft further.
4. If all pass: draft slice brief, Codex prompt (using the template), and
   Project #6 draft. Hand up for checklist review.
5. On coordinator approval, hand Codex the prompt.
6. Start the next slice's brief while Codex implements the current one
   (pipelined).

### Codex standing loop (per approved slice)

1. Read the approved Codex prompt. Do not re-derive scope.
2. Implement on `codex/<task-id>-<slug>`.
3. Run validation commands exactly as listed.
4. Open PR into `main`, link Project #6 item.
5. Report: commands run, test output, files touched, any surprises.
6. On review feedback: address, push to same branch, re-run validation.
7. On merge: mark Project #6 item Done, pick up next approved prompt.

### Coordinator standing loop (per sprint)

1. Set sprint goal + ordered slice list in the task execplan.
2. For each planner hand-up: run Slice Brief Self-Review as checklist.
   Approve, narrow with one sentence, or escalate to Approval Gate.
3. For each Codex PR: run code review. Approve, request changes, or
   escalate.
4. When sprint exit trips, re-engage in Opus mode to set the next sprint.

### Sprint exit criteria

Close the sprint when any of:

- All sprint slices merged.
- An Approval Gate trips.
- Scope needs to expand beyond the sprint's governing spec.
- A decision needs to land in `docs/decisions.md` (durable, Opus-level).

## Cheap Delegation

Each role should delegate the cheapest safe way. The goal is: Opus coordinator
only pays Opus tokens for judgment that actually needs Opus. Same pattern for
planner and Codex.

| Role | Delegate what | To | Trigger |
|---|---|---|---|
| Coordinator | Codebase search / file discovery | Explore subagent (quick or medium) | Finding files, symbols, call sites |
| Coordinator | Slice Brief checklist pass | Sonnet subagent via Agent tool | Hand-up with no Approval Gate flagged |
| Coordinator | Routine PR code review (no gate flagged) | Sonnet subagent (code-review skill) | PR is small, scope matches approved brief |
| Coordinator | Docs-drift scan across root docs | Sonnet subagent | Mechanical cross-file comparison |
| Coordinator | Commit message / PR body drafting | Haiku or Sonnet | Formatting-only text |
| Planner | Field-to-source audit | Explore subagent | Mapping canonical sources for a slice brief |
| Planner | Pattern-match existing tests | Explore subagent | Finding a test to mirror |
| Planner | Codex prompt draft polishing | Sonnet subagent | Template is filled, polish only |
| Codex | Rename / format-only diffs | GPT-5 mini | Pure mechanical edits with a test oracle |
| Codex | Test-output transcription | Stays on primary tier | Correctness judgment required |

### Never delegate (escalate instead)

- Any Approval Gate (auth, billing, migrations, deployment, secrets,
  destructive deletes, pipeline semantics, scoring/selection, OSS/Workbench
  boundary, model-cost).
- Any "this feels wrong but I can't say why" signal.
- Any cross-task architectural decision.
- Any route that could blur Option C (a `crewai` import entering a contract
  module).

When in doubt, escalate cheap and early, not expensive and late.
