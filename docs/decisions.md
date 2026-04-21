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

- Date: 2026-04-21
- Task: Op 2 (OSS unification)
- Decision: Force-update `origin/main` from `b8bc34c` to the PR #90 merge commit `9446998`, preserving the old `main` tip as annotated tag `oss-main-pre-unify`. Path B (archive + force-update) over Path A (merge --allow-unrelated-histories). PR #90 merged first as a merge commit to preserve review history (Option A ordering).
- Why: `origin/main` and the real codebase had unrelated histories. Preserving both lineages permanently in main would make the public OSS story permanently confusing. No multi-user or paid work exists yet, so the force-update cost is low and one-time. The archive tag preserves provenance.
- Consequence: From now on, PRs target `main` directly. The `codex/job-catalog-foundation*` private lanes are retired. Any external clone of the old main must hard-reset. Rollback command is recorded in `docs/current-state.json` under `op2_lane.rollback_command`.

- Date: 2026-04-21
- Task: T002 (authoring MVP)
- Decision: Option C (hybrid) for the author/revise layer. Deterministic contracts (`AuthoringCaseContext`, `GeneratedApplicationPackage`, `DocumentValidationResult`) stay JobPipe-native and must not import any agent framework. crewAI (if adopted later) enters only behind a JobPipe-owned adapter inside the author/revise module, which has a typed, framework-agnostic interface.
- Why: Data is the product. JobPipe is the engine. Locking contracts to any one agent framework (crewAI or otherwise) would trade the product's differentiator for short-term velocity. Keeping the runtime layer swappable preserves the replaceability principle we apply to reactive-resume and jobsync.
- Consequence: Any slice that imports `crewai` into the contract layer is a routing violation and must be rejected in review. The "no `crewai` import in contract modules or their tests" rule must appear as acceptance criteria on every T002 slice that touches contracts.
