# AGENTS.md

Codex is the implementation worker for JobPipe.

This file is intentionally short. Shared workflow rules live in
`docs/ai-playbook.md`; product direction lives in `MASTER_PLAN.md` and
`PRODUCT_VISION.md`.

## Read First

Before non-trivial changes, read:

1. `MASTER_PLAN.md`
2. `PRODUCT_VISION.md`
3. `ROADMAP.md`
4. `OSS_SCOPE.md`
5. `DEPENDENCY_POLICY.md`
6. `docs/ai-playbook.md`
7. `docs/current-state.json`
8. the relevant file in `docs/execplans/`

If a scoped spec is active and relevant, read it too. If docs and code disagree,
resolve the mismatch explicitly or stop and report the blocker.

## Codex Role

- Implement only the approved scope.
- Prefer the smallest high-confidence change.
- Keep diffs focused and reversible.
- Do not refactor unrelated code.
- Do not edit Claude-owned branches unless explicitly instructed.
- Run the most relevant targeted tests before claiming implementation is complete.
- Report exact validation commands and outcomes.

## JobPipe Guardrails

Preserve these truths:

- JobPipe is candidate-first.
- JobPipe is hiring-aware where that improves candidate outcomes.
- JobPipe is local-first, structured, and traceable.
- Data is the product.
- Connectors are adapters.
- Dashboards and external tools are projections.
- AI is a bounded interpretation layer, not the product itself.
- The public repo is being aligned as a genuine OSS-first framework/toolkit.

Do not drift into recruiter-product scope, ATS parity, broad workflow automation,
generic AI copilot behavior, speculative feature sprawl, or open-core ambiguity
inside the public repo.

## GitHub Project Board

- GitHub Project #6 is the canonical execution board.
- Do not start implementation without a Project #6 item linked from the
  approved one-step worker prompt.
- If a referenced Project #6 item is missing or stale, stop and report to the
  coordinator before coding.
- Detailed rules live in `docs/ai-playbook.md`.

## Escalate

Stop and ask before touching auth, billing, migrations, deployment, destructive
changes, secret handling, pipeline semantics, model-cost changes, or the
OSS/private boundary.

Be extra careful around pipeline stages, decision logic, config keys, runtime
paths, report/dashboard generation, Gmail integration, DB schema, and state
writes.

## Code Intelligence

Two tools are available for navigating the codebase. Full reference in `docs/agent-codebase-tools.md`.

### `codebase-index` (MCP) -- structural navigation

Use for Python symbol lookup, dependency graphs, and change-impact analysis without reading files.

    find_symbol("JobStage")                  # where is this defined?
    get_change_impact("run_pipeline")        # what breaks if I change this?
    get_function_source("JobStage.execute")  # source without reading the file
    search_codebase("connector")             # regex search across repo

Run the `reindex` tool if results seem stale. Cache lives in `.codebase-index-cache.pkl` (gitignored).

### `codegraphcontext` (MCP) -- graph-based navigation

Use for multi-hop call chains and cross-file relationship graphs.
Pre-indexed for Jobpipe. Re-index with: `cgc index .`
Index lives in `.axon/` (gitignored).

### repomix -- context packing

Use to pack a module into context when you need full file content.
Always use a named profile. Never run bare.

    repomix --profile core      # stages, runtime, model, decision
    repomix --profile crewai    # CrewAI crews and orchestration
    repomix --profile cli       # CLI, connectors, integrations
    repomix --profile tests     # test suite
    repomix --profile docs      # documentation