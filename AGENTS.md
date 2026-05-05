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

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **Jobpipe** (5005 symbols, 8332 relationships, 258 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/Jobpipe/context` | Codebase overview, check index freshness |
| `gitnexus://repo/Jobpipe/clusters` | All functional areas |
| `gitnexus://repo/Jobpipe/processes` | All execution flows |
| `gitnexus://repo/Jobpipe/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
