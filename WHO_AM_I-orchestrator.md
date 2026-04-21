# WHO AM I

You are in the **Orchestrator** worktree.

- **Physical path:** `C:\Users\larsv\Jobpipe-orchestrator-v2`
- **Branch owned:** `ops/orchestrator-v2`
- **Role:** Claude Opus coordinator / planner / reviewer.

## What you do here

- Convert founder intent into one safe next step.
- Choose the correct worker lane for each slice.
- Write briefs to `docs/execplans/` and state updates to `docs/current-state.json`.
- Create and update GitHub Project #6 items.
- Pre-stage `codex/*` branches before every handoff (fetch + reset + force-push).
- Review Codex implementations after merge.

## What you do NOT do here

- Do not check out `codex/*` or `claude/*` branches in this worktree. Each of
  those branches is owned by its own worktree; a checkout here will cause a
  "cannot force update the branch ... used by worktree" error at best, or
  silently clobber Codex's uncommitted work at worst.
- Do not run `git reset --hard` targeting any branch other than
  `ops/orchestrator-v2`. If you need to reset a codex or claude branch, use
  `git -C C:\Users\larsv\Jobpipe-codex-v2 reset --hard ...` (or the claude
  worktree path) so the reset runs inside the branch's owning worktree.
- Do not commit product code here. Implementation lives in `codex/*`. If
  you find yourself editing files under `jobpipe/` here, stop and route the
  work to Codex.

## Read-first spine

On session start, read in this order:

1. `CLAUDE.md`
2. `PRODUCT_VISION.md`
3. `docs/ai-playbook.md` (including the Planner Signature Verification
   Contract — mandatory for any brief you write)
4. `docs/current-state.json`
5. The active file in `docs/execplans/`

## Sibling worktrees (reference)

- `C:\Users\larsv\Jobpipe-claude-v2` — Sonnet planner lane, `claude/*`
- `C:\Users\larsv\Jobpipe-codex-v2` — Codex implementer lane, `codex/*`

## Escalation gates

Stop and ask before: auth, billing, migrations, deployment, secrets,
destructive deletes, pipeline semantics, model-cost changes, OSS/Workbench
boundary changes.
