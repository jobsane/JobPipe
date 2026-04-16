# JobPipe Product Vision

**Last updated:** 2026-04-17

## Product thesis

JobPipe should help a job seeker spend time where they have the best odds, not where the market is loudest.

The product is not trying to automate the whole job search. It is trying to produce a narrower, better decision surface:

- fewer irrelevant jobs to read
- clearer prioritization among plausible jobs
- stronger follow-up structure once a job becomes actionable
- better raw material for applications when the match is real

## Current wedge

JobPipe starts with one concrete workflow:

1. ingest jobs from one or more sources
2. kill obvious noise cheaply
3. score the jobs worth deeper inspection
4. track what happened after the candidate acted

That wedge matters because it solves the highest-friction part of the job-search loop before drifting into broader platform work.

## Reference user

The current reference candidate is Lars. The system is tuned around a real search profile and real workflow pain, which is useful because it forces the product to solve concrete problems instead of generic ones.

That said, the architecture is now explicitly candidate-scoped:

- candidate IDs are first-class
- candidate profile state has a canonical home
- the primary DB supports future multi-user growth without changing the product model

## Product promise

JobPipe should make these statements true:

- I do not have to read hundreds of weak matches to find a few strong ones.
- I can explain why a job was recommended or skipped.
- I can see my live action list and application state in one place.
- I can generate usable application material without losing traceability.

## Principles

1. Cheap filters before expensive model calls.
2. Structured state before clever automation.
3. Traceability over black-box convenience.
4. Candidate decisions stay human.
5. Local-first is a feature, not a temporary inconvenience.
6. Product scope should expand only when the current workflow is coherent.

## What the product is

JobPipe is:

- a local-first job-search workflow system
- a candidate-specific decision engine
- a traceable pipeline with inspectable artifacts
- a stateful application tracker

JobPipe is not:

- a mass auto-apply tool
- a generic resume builder
- an ATS replacement
- a multi-tenant SaaS product today

## Product shape today

The current system is organized around one primary state layer plus derived artifacts:

- primary DB for candidate state, evaluations, suggestion leads, application events, and document metadata
- artifact files for stage-by-stage debugging and review
- exported dashboard for decision support
- optional Gmail integration for status and suggestion intake

This is the right product shape for the current stage. It keeps the system operationally useful without dragging the repo into premature platform complexity.

## Strategic differentiation

The strongest differentiator is not “AI writes application text.” That is now table stakes.

The stronger differentiator is:

- cheap filtering before deep evaluation
- candidate-specific fit and pivot scoring
- traceable decisions that can be tuned
- one system that spans intake, prioritization, follow-up, and document support

Longer term, the distinctive product opportunity is *advantageous match detection*: surfacing roles where the candidate is more competitive than the title or sector implies.

## Success measures

Primary operating metrics:

- strong matches surfaced per week
- false negatives on clearly relevant jobs
- triage pass rate
- wasted deep-evaluation spend on jobs that should have died earlier
- time from source ingestion to dashboard visibility

Secondary product metrics:

- dashboard usefulness in daily operation
- application-state accuracy
- document usefulness for top matches
- runtime reliability and setup clarity

## Product boundaries for the next stage

The next stage of JobPipe should stay disciplined:

- finish the DB-first local architecture
- improve application-pack quality
- improve source intake and candidate-state quality
- keep the docs, code, and runtime model aligned

It should not yet broaden into:

- multi-user auth and settings UI
- hosted SaaS packaging
- dedicated vector-database architecture
- large surface-area workflow automation

## Future direction

If JobPipe proves stable and useful in this form, the next natural expansion is:

1. stronger multi-source intake and deduplication
2. better advantageous-match signals
3. candidate learning from outcomes
4. optional server-backed deployment with the same domain model

That future should be a storage and deployment evolution, not a product rewrite.

## Related docs

- [README.md](README.md)
- [ROADMAP.md](ROADMAP.md)
- [docs/architecture.md](docs/architecture.md)
- [specs/canonical-data-model.md](specs/canonical-data-model.md)
