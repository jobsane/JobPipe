# OSS Scope

**Last updated:** 2026-04-17

This file defines what the current public JobPipe repo is for.

It exists to keep the public story, contribution surface, and later business boundary coherent without forcing a premature repo split.

For target package slices, runtime roots, and the public OSS/private seam, pair this file with [specs/architecture-boundaries.md](specs/architecture-boundaries.md).

## Public repo purpose

The current public repo should become a genuinely useful OSS-first framework/toolkit for:

- local-first job-search intelligence workflows
- canonical candidate/job/evaluation state
- structured evidence and inspectable decisions
- watchlist and change-detection workflows
- projections, examples, and extension points

Public value should be real even if no later commercial product ever materializes.

## Naming relationship

Current naming decisions:

- `JobPipe` = umbrella project name
- `JobPipe` = OSS/framework name
- `JobPipe Workbench` = reserved name for a later private/commercial implementation if that split happens

The public repo should therefore be described as:

- the public JobPipe framework/toolkit

not as:

- a teaser for a secret product
- a fake open-core repo
- a recruiter platform

## What belongs in the public repo

Public scope should include:

- canonical models and schemas
- local-first runtime behavior
- CLI and operator surfaces
- public package boundaries that keep runtime, model, connectors, decision logic, and projections distinct
- artifact/export/document abstractions
- generic adapters and projection hooks
- baseline pipeline behavior
- public authoring adapter contracts and local/simple baseline authoring behavior
- public examples, fixtures, and demos
- docs that explain the public model, workflow, and extension points

The repo should remain useful for:

- developers
- hobbyists
- tinkerers
- single users
- contributors who want to extend a real local-first toolkit

## What should stay out of current public scope

Do not treat the public repo as the place to build:

- recruiter-product workflows
- ATS feature parity
- mass auto-apply features
- premium-only business logic
- sensitive or brittle commercial connectors
- private calibration assets or proprietary outcome datasets
- commercial packaging and premium workflow bundles

Those may belong to a later private/commercial layer, but they do not need to be represented as first-class public scope now.

## Later private/commercial layer

The later private/commercial layer is legitimate in planning terms, but it is not the main scope of this repo today.

That later layer may build on the public foundation by adding:

- tuned decision logic
- premium workflow bundles
- calibration and learned defaults
- sensitive or high-maintenance connectors
- premium packaging and product UX

The private layer should depend on the public foundation, not replace it.

## Optional extension seams

Optional implementation packages may live beside `jobpipe/` when they are useful proof-of-work or integration surfaces.

Current example:

- `jobpipe_crewai/` is an optional CrewAI implementation of the public authoring adapter seam.

Rules:

- optional extensions must not be required for the core public runtime to import or run
- `jobpipe/` may load optional implementations dynamically through public adapter contracts
- optional extensions must not define alternate canonical schemas, alternate product stories, or private-only assumptions
- CrewAI, private policy packs, premium connectors, or sibling-product integrations must remain behind explicit seams

## Contribution surface

Good public contributions strengthen:

- canonical models
- local runtime and path handling
- adapter boundaries
- projection and export quality
- tests, fixtures, and examples
- setup, documentation, and public ergonomics

Contributions should not implicitly widen the repo into:

- a mixed open/private codebase
- a broad job-search super-app
- recruiter-tech scope

## Current rule

Until an explicit repo split happens, treat this public repo as:

- the canonical public planning and model layer
- the public OSS implementation surface
- the proof-of-work surface people can inspect, run, and extend
- the place where public boundary contracts are defined before any later private layer exists

Do not assume that every future commercial workflow belongs here.
