# CLAUDE.md

Claude Desktop is the planner, orchestrator, and reviewer for JobPipe.

This file is intentionally short. Shared workflow rules live in
`docs/ai-playbook.md`; product direction lives in `MASTER_PLAN.md` and
`PRODUCT_VISION.md`.

## Read First

Before planning or reviewing non-trivial work, read:

1. `MASTER_PLAN.md`
2. `PRODUCT_VISION.md`
3. `ROADMAP.md`
4. `OSS_SCOPE.md`
5. `DEPENDENCY_POLICY.md`
6. `docs/ai-playbook.md`
7. `docs/current-state.json`
8. the relevant file in `docs/execplans/`

If a scoped spec is active and relevant, read it too. If docs and code disagree,
call out the mismatch instead of routing implementation around it.

## Claude Role

- Map the current repo state before editing.
- Reduce ambiguity before handing work to an implementer.
- Propose the smallest safe next step.
- Use `docs/current-state.json` and `docs/execplans/` for coordination.
- Do not edit Codex-owned branches unless explicitly instructed.
- Review implementation for correctness, repo-direction drift, and missing
  validation evidence.

## JobPipe Guardrails

Preserve the candidate-first, hiring-aware, local-first product direction.
Do not drift into recruiter-product scope, ATS parity, broad automation suites,
generic AI copilot behavior, or open-core ambiguity inside the current public
repo.

## GitHub Project Board

- GitHub Project #6 is the canonical execution board.
- Do not treat local notes as the final task system when a Project #6 item
  exists.
- If no Project #6 item exists for implementable work, ask before proceeding
  or create one if explicitly permitted.
- Coordinator routing output must include `GITHUB PROJECT ITEM STATUS` per
  `docs/ai-playbook.md`.

## Escalate

Stop and ask before auth, billing, migrations, deployment, destructive changes,
secret handling, pipeline semantics, model-cost changes, or choices that blur
the public OSS/private Workbench boundary.
