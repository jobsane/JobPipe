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

- Date: 2026-05-06
- Task: pipeline hardening / date normalisation
- Decision: Normalise `applicationDue` to ISO `YYYY-MM-DD` at ingest in `pull_sheets_csv`, not only in the downstream sync tools.
- Why: Multiple formats arrive from Google Sheets (`dd.mm.yyyy`, `dd/mm/yyyy`, `dd-mm-yyyy`). Normalising only in `sync_ledger` / `sync_evaluations` means raw connector JSONL files, the intake queue, and any consumer that reads `ctx.job["applicationDue"]` directly (triage prompt header, `application_pack`, `profile_match`) all see the un-normalised value. Root normalisation ensures every downstream consumer receives consistent ISO dates.
- Consequence: `pull_sheets_csv._normalize_due()` is the canonical normalisation point. `sync_ledger._parse_date_maybe()` and `sync_evaluations._parse_date_maybe()` remain as safety nets for records already queued. Any future connector that writes `applicationDue` must normalise to ISO before appending to the connector JSONL.

- Date: 2026-05-06
- Task: pipeline hardening / date normalisation
- Decision: Use `str.startswith(_OPEN_DEADLINE_PREFIXES)` (prefix match) rather than exact set membership for open-deadline keywords (`snarest`, `asap`, `fortløpende`, `løpende`, `rolling`).
- Why: Real job postings use `snarest mulig`, `snarest mulig oppstart`, etc. An exact-match check silently misses multi-word variants, letting them reach `parse_iso()` which returns the epoch sentinel — effectively treating "rolling deadline" as an unknown that could be skipped by the expiry filter.
- Consequence: `_OPEN_DEADLINE_PREFIXES` in `pull_sheets_csv` and `_common.py` are the two canonical locations. Any new open-deadline synonym must be added to both. The prefix approach means a value beginning with one of the prefixes is always treated as open regardless of what follows — this is intentional and acceptable.

- Date: 2026-05-06
- Task: pipeline hardening / schema validation
- Decision: Use a Pydantic `before`-mode `field_validator` on `AdvantageAssessmentV3` to truncate long LLM-generated strings to 237 chars + "…" rather than raising `ValidationError`.
- Why: LLMs occasionally produce strings slightly over the 240-char display limit. A hard `ValidationError` propagates as a `pipeline_error.json`, leaving the job with no `final_decision` in the ledger — silently losing a potentially good lead. Truncating is always preferable to losing the record; the display cap exists for UI density, not data integrity.
- Consequence: The truncation applies to `recruiter_hook`, `applicant_pool_hypothesis`, and `summary` on `AdvantageAssessmentV3`. If other models show similar over-length failures, apply the same pattern. Do not raise `ValidationError` for cosmetic display-length limits.

- Date: 2026-05-06
- Task: pipeline hardening / code deduplication
- Decision: `jobpipe/stages/pipeline.py::build_stages` is the single source of truth; `run_feed.py` imports from it.
- Why: `run_feed.py` carried a ~160-line duplicate of `build_stages` that was missing `triage_profile_summary`, `targeting_title_patterns`, and all v3 `cache_key_fn` parameters. The live path always used `run_feed.py`'s version (which shadowed `pipeline.py`), so no behaviour changed, but the drift created a latent correctness risk and confused future contributors about which definition was authoritative.
- Consequence: `pipeline.py::build_stages` must always be kept current. `run_feed.py` must never re-introduce a local `build_stages`. Any new stage added to the supported order must be wired in `pipeline.py`.

- Date: 2026-05-08
- Task: S5-HUB-PLAN-01
- Decision: Name the backend-side common connection point `ApplicationWorkspaceHub` and make it the owner of JobDesk-facing backend capability contracts, projections, command boundaries, adapter routing, and provenance-safe payloads.
- Why: JobDesk needs a stable backend contract that can connect JobPipe, JobSane, JobData, Reactive Resume, future API/MCP wrappers, SQLite/artifacts, and later Supabase without depending on the legacy dashboard or exposing storage internals.
- Consequence: New JobDesk integration work must target ApplicationWorkspaceHub capabilities first. The old dashboard may be referenced for behavior but must not become the dependency for JobDesk pathways.

- Date: 2026-05-08
- Task: S5-HUB-01
- Decision: Place the initial hub contract skeleton in `jobpipe.workspace`, with storage-agnostic value objects in `jobpipe.workspace.contracts` and capability protocols in `jobpipe.workspace.hub`.
- Why: The contracts need a neutral package that is not tied to the old dashboard, CLI server, storage adapter, API transport, or any single companion project.
- Consequence: Future storage adapters, API/MCP wrappers, and JobDesk-facing projections must depend on `jobpipe.workspace` contracts instead of importing dashboard-era payloads.

- Date: 2026-05-08
- Task: S5-SB-01
- Decision: Treat hosted JobData Supabase as a NAV intake source only, feeding the existing JobPipe connector staging seam through `pull_supabase_jobs.py` and `drain_queue.py`.
- Why: Supabase already contains NAV-ingested rows, but JobDesk's case read model is owned by JobDeskIntegrationGateway/ApplicationWorkspaceHub. The smallest safe integration is to map Supabase NAV rows into existing JobPipe intake records, then let the normal JobPipe run, catalog, SQLite, and artifact path own downstream outputs.
- Consequence: Supabase NAV intake must not become a direct JobDesk dependency, ApplicationWorkspaceHub storage adapter, old-dashboard dependency, or write-back path. Future work should harden the existing puller and tests before adding any Supabase output/status adapter.

- Date: 2026-05-08
- Task: S5-SB-02
- Decision: Keep `public.jobs` as the default Supabase NAV intake relation and allow `public.jobs_active` only through explicit configuration until hosted view exposure is validated.
- Why: `public.jobs` with explicit `status=eq.ACTIVE` and `expires_at > now` is the existing proven route. Supabase REST can expose views, but view access still depends on schema exposure, grants, and RLS behavior, so switching defaults before live validation would add avoidable intake risk.
- Consequence: `pull_supabase_jobs.py` accepts only `jobs` and `jobs_active`, skips incomplete rows before they reach AI processing, preserves NAV-only fields as connector metadata, and leaves output in current JobPipe SQLite/artifact storage with Supabase write-back deferred.
