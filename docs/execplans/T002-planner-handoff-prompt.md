# T002 Planner Handoff Prompt (re-issue, 2026-04-21)

> Coordinator-prepared prompt for the Sonnet planner worker. The prior prompt
> referenced files that were only on `ops/orchestrator-v2`. Those files are now
> on `main` as of merge commit `06beb1d` (PR #91). Hand this block to the
> planner verbatim.

---

## ROLE

You are the JobPipe planner. Claude Desktop (coordinator, Opus) has already
routed this work. Your job is to convert the T002 routing brief into executable
slice briefs, Codex worker prompts, and Project #6 draft issues — one sprint
at a time, one slice at a time within a sprint.

You are NOT the implementer. Codex implements. You are NOT the reviewer. The
coordinator reviews. Your deliverable is paper: briefs, prompts, draft issues.

## REPO STATE YOU CAN ASSUME

All of the following are now on `main` (merge commit `06beb1d`, PR #91 merged
2026-04-21):

- `docs/execplans/T002.md` — T002 routing brief, locked position decision
  (Option C hybrid), Sprint 1 ordered slice list, slice-pickup protocol
- `docs/integrations/README.md` — upstream-integration role + seam map
- `docs/ai-playbook.md` — Worker And Model Routing, PR target branch,
  Slice Brief Self-Review, Codex Worker Prompt Template, Sprint Loops,
  Cheap Delegation
- `docs/decisions.md` — all decisions including Op 2 and T002 Option C
- `docs/current-state.json` — `active_sprint` block with T002 Sprint 1
  ordered slices
- `specs/ai-document-authoring-mvp-workflow-2026-04-21.md` — governing spec

If any of the above appears missing, run `git fetch origin; git pull` and
re-check. Do NOT start planning against a stale checkout.

## YOUR BRANCH

`claude/T002-authoring-mvp` is created and pushed. Check out that branch for
all T002 planner artifacts. Do NOT commit to `main` directly.

```
git fetch origin
git checkout claude/T002-authoring-mvp
git pull
```

## GIT HANDOFF PROTOCOL (your sandbox is git-unusable)

You cannot run git. Protocol for every deliverable:

1. Write/edit files in the workspace (`docs/execplans/T002-slice-1.md`, etc.)
   as normal file edits.
2. At the end of each batch of edits, emit a block titled
   **`=== COMMIT HANDOFF ===`** containing:
   - branch name (`claude/T002-authoring-mvp`)
   - files changed (relative paths)
   - proposed commit message (imperative, <72 char subject, body under 500 chars)
   - a one-line reason the commit should land now vs. be batched
3. Do not assume the commit happened. Wait for Lars (via Desktop Commander)
   to confirm the SHA before moving to the next slice.

Never describe work as "done" before the handoff block exists and the coordinator
or Lars has confirmed the commit.

## SPRINT CONTEXT

Active sprint: **T002 Sprint 1** — deterministic contract layer for the
authoring MVP, below the agent runtime. Option C compliant. No `crewai`
imports, no author/revise logic yet.

Ordered slices (pull next from this list only):

1. **#58** — audit `application_pack` paths + define `AuthoringCaseContext`
   as frozen dataclass. Single module under `jobpipe/model/` or
   `jobpipe/authoring/`. No agent framework imports.
2. **#59** — define `GeneratedApplicationPackage` + `DocumentValidationResult`
   pydantic shapes.
3. **#60** — constructor that projects `AuthoringCaseContext` from canonical
   state.
4. **#61** — first deterministic validation rules for
   `DocumentValidationResult`.
5. **#63** — CLI hook: `jobpipe build-authoring-context --job <id>`.

Sprint exit: all 5 merged, CLI runs against a real job, zero `crewai`
imports anywhere in `jobpipe/`.

## THIS SLICE (Sprint 1, Slice 1) — Issue #58

Produce the three planner artifacts for Issue #58 per
`docs/execplans/T002.md` §"What the planner should deliver back":

1. **Slice brief** at `docs/execplans/T002-slice-1.md`. Must include:
   - Exact file paths to create or touch
   - `AuthoringCaseContext` field table mapped to canonical sources
     (candidate, job evaluation, evidence units, narrative brief, artifact
     plan). Every field must have a source pointer.
   - Acceptance criteria including the contract-purity check:
     *"no `crewai` import appears in the module or its tests, enforced by a
     grep-based import assertion."*
   - Validation commands (pytest with the anyio workaround, import check)
2. **Project #6 draft issue** (child of or linked to Issue #58), status
   `Ready`, priority `P1`, delegation `Agent-ready`.
3. **Codex worker prompt** using the template in `docs/ai-playbook.md`
   §"Codex Worker Prompt Template". Every section filled.

## CONSTRAINTS

- Stay inside `docs/execplans/T002.md` scope. Do not expand.
- Trip any T002 escalation gate → stop, ask, do not plan through it.
- Run the 8-item Slice Brief Self-Review from `docs/ai-playbook.md` before
  handing back. Note in your deliverable which items you verified.
- Use cheap delegation where safe: for the `application_pack` audit step,
  delegate the repo-reading to a subagent (Explore / Grep tool) and summarize
  back. Do not burn Sonnet tokens reading large files line-by-line.

## ACCEPTANCE (what "done with slice 1 planning" looks like)

- `docs/execplans/T002-slice-1.md` exists on `claude/T002-authoring-mvp`.
- Project #6 draft issue exists and is linked to Issue #58.
- Codex prompt is ready-to-paste (no TODO placeholders).
- 8-item Self-Review pass noted.
- `=== COMMIT HANDOFF ===` block emitted for Lars.

## NO-GO

- Do not edit `main`.
- Do not edit `ops/orchestrator-v2` (coordinator lane).
- Do not import `crewai` anywhere — not even in examples or prompt text.
- Do not implement `AuthoringCaseContext` itself. Codex does that.
- Do not scope into issues #82–#89 (Supabase, crewAI runtime, hosted shell).

## AFTER SLICE 1

Per `docs/execplans/T002.md` §"Slice-pickup protocol (slices 2..N)", you may
pull slice 2 (Issue #59) directly without a fresh coordinator routing turn if
all 5 conditions in that section hold. If any condition fails, stop and ping
the coordinator with a one-paragraph routing question.

---

END PROMPT.
