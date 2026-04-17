# JobPipe Agent Instructions

## Read First

Before making repo-facing changes, read:

1. `README.md`
2. `MASTER_PLAN.md`
3. `PRODUCT_VISION.md`
4. `ROADMAP.md`
5. `OSS_SCOPE.md`
6. `DEPENDENCY_POLICY.md`

## Canonical Repo Truth

This repository is the clean new public baseline for JobPipe.

It is:

- candidate-first
- hiring-aware
- local-first
- privacy-respecting
- evidence-backed
- OSS-first in public scope

It is not:

- a recruiter platform
- an ATS
- a generic AI copilot
- an ambiguous old pipeline brand

## Naming Rules

- Use `JobPipe` consistently.
- Do not reintroduce retired worknames anywhere in the repo.
- If a later private/commercial layer is discussed, the reserved name direction is `JobPipe Workbench`.

## Practical Rules

- Keep the current root repo as the only active canonical codebase.
- Do not recreate nested repo mirrors inside this repository.
- Keep generated state, credentials, and private user data out of version control.
- Treat `reports/` and `out_runs/` as current runtime names, not the public product category.

## Change Discipline

- Prefer focused changes with explicit validation.
- Keep planning docs aligned with each other.
- When changing public-facing language, optimize for one coherent story over legacy compatibility.
