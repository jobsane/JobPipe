# Decisions Log

Durable decisions and rationale live here. Live task state belongs in
`docs/current-state.json`; task plans belong in `docs/execplans/`.

## Format

- Date:
- Task:
- Decision:
- Why:
- Consequence:

---

- Date: 2026-04-21
- Task: T001
- Decision: Use a thin dual-client setup with Claude as planner/orchestrator/reviewer and Codex as implementer.
- Why: This keeps planning, implementation, and review roles explicit while preserving the shared repo as source of truth.
- Consequence: Branch and worktree ownership must stay visible in the active execplan and current-state file.

- Date: 2026-04-21
- Task: T001
- Decision: Keep `PRODUCT_VISION.md` as the canonical product vision and use `docs/vision.md` only as a short AI-facing adapter.
- Why: The full product strategy already exists in the root planning spine; duplicating it in AI workflow docs would create drift.
- Consequence: AI agents should read the adapter for fast orientation but resolve product questions against `PRODUCT_VISION.md`.

- Date: 2026-04-21
- Task: T001
- Decision: Use `docs/ai-playbook.md` as the shared workflow home instead of duplicating process rules in `AGENTS.md` and `CLAUDE.md`.
- Why: Shared process belongs in one canonical location; root instruction files should stay short and role-specific.
- Consequence: `AGENTS.md` and `CLAUDE.md` point to the playbook for repo-state gates, approval gates, validation, and handoff rules.

- Date: 2026-04-21
- Task: T001
- Decision: Treat `AUDIT.md` and `AGENT_STATUS.md` as historical recovery material, not active canonical instruction sources.
- Why: They contain useful recovery evidence but also stale and wrong-repo content.
- Consequence: Useful current rules should be migrated into `docs/ai-playbook.md`, `docs/current-state.json`, `docs/decisions.md`, or task execplans before any future archive/delete action.

- Date: 2026-04-21
- Task: T001
- Decision: GitHub Project #6 remains the active execution board for backlog placement and sprint tracking.
- Why: The repo docs should stay high-level and should not duplicate the full backlog tree.
- Consequence: Durable product or roadmap consequences may be mirrored into repo docs, but active backlog state should stay in GitHub Project #6.
