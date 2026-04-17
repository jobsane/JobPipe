# JobPipe - Master Plan

## Purpose

This is the canonical planning document for the public JobPipe repository.

Use it to keep scope, naming, sequencing, and repo boundaries coherent.

## Canonical Product Thesis

JobPipe is a candidate-first, hiring-aware, local-first career intelligence workbench.

Plain-language fallback: job-search decision system.

Core mechanism:

`structured evidence -> explicit decision support -> living monitoring -> better action`

## Public Repo Role

This repository is the clean new public baseline for JobPipe.

It should evolve into a genuinely useful OSS-first foundation that is:

- useful to single users
- useful to tinkerers and developers
- credible as public proof-of-work
- compatible with a later private/commercial layer built on top

## Naming Architecture

- `JobPipe` = umbrella project and OSS/framework name
- `JobPipe Workbench` = reserved name direction for a later private/commercial implementation
- `jobpipe` = package and repo-facing code name

Retired worknames should not reappear in docs, metadata, repo names, or public messaging.

## Current Implementation Truth

The current codebase still reflects its pipeline origins:

- staged evaluation under `jobpipe/stages/`
- shared runtime helpers under `jobpipe/core/`
- runtime outputs under `reports/` and `out_runs/`

That is acceptable for the current code, but it is not the long-term public framing.

## Near-Term Build Sequence

1. Keep the repo and naming clean.
2. Tighten privacy and local data boundaries.
3. Improve the explicit decision substrate:
   - job claims
   - decision tables
   - evidence units
   - narrative profiles
   - watchlists and change events
4. Improve the public OSS boundary and contribution surfaces.
5. Only later, define and build a private/commercial layer on top.

## Repo Scope

The public repo should focus on:

- local-first ingestion and evaluation workflows
- inspectable decision support
- reusable candidate/job data handling
- public docs, examples, and tooling

It should not become:

- a recruiter platform
- an ATS
- a generic AI assistant
- a vague open-core teaser

## Canonical Document Hierarchy

1. `MASTER_PLAN.md`
2. `PRODUCT_VISION.md`
3. `ROADMAP.md`
4. `OSS_SCOPE.md`
5. `DEPENDENCY_POLICY.md`
6. supporting docs and implementation notes

## Release Baseline

This repo should now be treated as the clean new baseline for JobPipe.

The practical release target is a fresh early public baseline rather than a legacy continuation. That means:

- one repo story
- one active canonical codebase
- no nested mirror repos
- no retired worknames
- no stale public identity tied to the old project framing
