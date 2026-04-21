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
