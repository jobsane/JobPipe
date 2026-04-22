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

---

- Date: 2026-04-21
- Task: T001 + Op 2
- Decision: T001 complete. Op 2 (OSS unification) executed end-to-end: PR #90 merged (inspect-db claim-layer views), archive tag `oss-main-pre-unify` pushed, `origin/main` force-updated `b8bc34c` → `9446998`. Coordinator scaffolding landed via PR #91. WHO_AM_I split landed via PR #97.
- Why: All T001 slices completed with founder sign-off. Main now reflects the unified private-lane codebase. Coordinator scaffolding (ai-playbook.md, current-state.json, execplans/) is live on main.
- Consequence: PRs target `main` directly. `codex/job-catalog-foundation*` lanes retired. T002 authoring MVP is the active implementation track.

---

- Date: 2026-04-21
- Task: T002 Sprint 1
- Decision: Sprint 1 closed — 5 slices, 5 PRs, all merged to main. Contract layer complete.
  - PR #92: Slice 1 — `AuthoringCaseContext` frozen dataclass
  - PR #93: Slice 2 — `GeneratedApplicationPackage` + `DocumentValidationResult`
  - PR #94: Slice 3 — `build_authoring_case_context` constructor
  - PR #95: Slice 4 — `build-authoring-context` smoke CLI hook
  - PR #98: Slice 5 — deterministic validation rules
- Why: Deterministic contract layer is a prerequisite for any agent integration. Option C compliance verified: no `crewai` import in any slice.
- Consequence: `jobpipe/authoring/` contract surface is stable. Sprint 2 (adapter + CLI) can proceed.

---

- Date: 2026-04-21
- Task: T002 Sprint 2
- Decision: Sprint 2 closed — 3 slices, 3 PRs, all merged to main. Adapter + CLI layer complete.
  - PR #99: Slice 6 — `--validate` flag on `build-authoring-context`
  - PR #100: Slice 7 — `AuthorAdapter` Protocol + `SimpleAgentAuthor`
  - PR #101: Slice 8 — author package persistence and CLI (`author-package` command)
- Why: Sprint exit test (10 passed, compile_check 81 files, --help verified) confirmed integration. Option C compliant throughout. Live data test deferred to first APPLY-decision run.
- Consequence: `jobpipe/authoring/` adapter surface is stable. `author-package` CLI is live. Sprint 3 (crewAI integration) can proceed. Three hygiene issues opened (#108/#109/#110), none blocking.

---

- Date: 2026-04-22
- Task: T002 Sprint 3
- Decision: Sprint 3 started — crewAI 1.14.2 selected as agent runtime (vendor-agnostic via LiteLLM, MCP-native). Isolated in Python 3.12 venv at `C:\Users\larsv\envs\crewai-env`. Slice 9 env confirmed working; Codex handles Slices 10/11/12 via orchestrator+sub-agent brief.
- Why: crewAI 1.14.2 is the lowest-friction option that satisfies: LiteLLM passthrough (model routing stays in JobPipe), MCP support, and Python 3.12 isolation from the Python 3.14 main env. Spec at `specs/crewai-integration-decision.md`.
- Consequence: `jobpipe_crewai/` is the permanent crewAI isolation boundary. Any `import crewai` outside that directory is a routing violation.

---

- Date: 2026-04-22
- Task: T002 Sprint 3
- Decision: Sprint 3 implementation closed — all implementation PRs merged to main. CrewAI author/critic loop + JobPipeAuthoringFlow + orchestration crew are live.
  - PR #107: crewAI author/critic loop (CrewAIAuthor, factory, 2-agent crew, isolated in `jobpipe_crewai/`)
  - PR #113: T002 Slice 5 — deterministic validation rules re-landed (Sprint 3 fixup)
  - PR #115: `JobPipeAuthoringFlow` — post-triage Flow + Crew orchestration (`#114`)
- Why: All invariants hold: no `crewai` import in `jobpipe/`, 20 tests pass across Python 3.12 and 3.14, compile_check 82 files. PR #115 completes the Flow layer required for Sprint 4 entry points.
- Consequence: S13 exit test (live APPLY-decision run) is the only remaining Sprint 3 exit criterion. Sprint 4 (docx rendering + flow entry point + finalize_step) is unblocked. Three hygiene issues (#108/#109/#110) are tracked but not blocking.

---

- Date: 2026-04-22
- Task: Governance
- Decision: Adopt tiered model routing from `specs/ai-toolchain-setup-2026-04-22.md`. Stop Opus on implementation review immediately. Fast-path rollout: Green XS slices use mini-prompt on issue, no execplan, no coordinator approval.
- Why: Solo-founder pace. Reversible micro-decisions should not require full coordinator loops. Coordinator overhead should match decision complexity.
- Consequence: `docs/ai-playbook.md` is the workflow source of truth. GitHub Issues + Project #6 serve as the append-only decision log. `docs/decisions.md` stays as the human-readable index of durable decisions only.

---

- Date: 2026-04-22
- Task: T002 Sprint 4
- Decision: Sprint 4 started. Three slices approved: S4-A (docx rendering), S4-B (flow_author.py CLI entry point), S4-C (finalize_step DB write-back). crewAI author/reviser included in Sprint 4, not a separate task. Orchestration crew (`#114`) built in Sprint 3 PR #115.
  - S4-A: PR #116 open (commit fa0deaa) — `render_cover_letter_docx` via Node.js subprocess. In review.
  - S4-B: Branch `codex/T002-s4b-flow-author` — handed to Codex 2026-04-22. Awaiting implementation.
  - S4-C: `finalize_step` DB write-back — Ready after S4-B merges.
- Why: Sprint 4 completes the document production pipeline: renders a real .docx, exposes a standalone crewAI entry point, and closes the write-back loop to the primary DB.
- Consequence: Sprint 4 exit criterion = all three slices merged + live `run_authoring_flow` smoke test passes on an APPLY-decision job. S13 exit test (Sprint 3) must also be confirmed before Sprint 4 close.
