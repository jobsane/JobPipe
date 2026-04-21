# Roadmap

This is the short execution view.

Canonical planning source:

- [MASTER_PLAN.md](MASTER_PLAN.md)

Canonical execution board:

- [GitHub Project #6 - JobPipe](https://github.com/users/larsvaerland/projects/6)

Canonical product thesis:

- [PRODUCT_VISION.md](PRODUCT_VISION.md)

Current planning audit:

- [specs/platform-alignment-audit.md](specs/platform-alignment-audit.md)

This file stays intentionally high-level.

Use the GitHub Project for:

- active backlog placement
- initiative / epic / feature / story / task hierarchy
- sprint selection
- release milestone grouping

Do not duplicate the full backlog tree here.

## Current phase

JobPipe is in a public hardening and audit-preparation phase.

The goal is not broad feature expansion. The goal is to make the public single-user OSS loop stable, credible, and generalizable before broader expansion.

## Now

### 1. Public loop hardening

Deliver:

- clean-install reliability
- real local-data end-to-end operation
- stronger onboarding defaults
- reduced connector/runtime surprises in the normal loop

### 2. Dashboard trustworthiness

Deliver:

- calm public dashboard behavior
- stronger evidence / risk / next-action presentation
- monitoring noise reduction
- public polish without degrading local-first simplicity

### 3. Persona-based audit setup

Deliver:

- one frozen audit corpus
- one frozen config baseline
- 4 synthetic candidate personas
- one repeatable audit matrix for public quality checks

### 4. Audit-driven hardening

Deliver:

- tighten specialist / public-transition / early-adjacent differentiation
- reduce product-leadership inertia for non-reference candidate shapes
- reduce monitoring/watchlist noise in the public dashboard
- rerun the persona matrix after each hardening slice and convert findings into bounded fixes

Current concrete findings source:

- [specs/persona-audit-findings-2026-04-17.md](specs/persona-audit-findings-2026-04-17.md)
- [specs/agentic-jobpilot-salvage-audit-2026-04-19.md](specs/agentic-jobpilot-salvage-audit-2026-04-19.md)
- [specs/integration-surface-inventory-2026-04-19.md](specs/integration-surface-inventory-2026-04-19.md)

## Next

### 5. Deeper public quality improvements

Deliver:

- source-quality visibility cleanup
- monitoring/change-event deduplication
- stronger sample/demo path for public OSS use

### 6. Local calibration refinement

Deliver:

- better local calibration interpretation
- stronger capability-gap refinement
- more reliable feedback-aware prioritization
- only bounded shadow-eval or outcome-loop work that fits the canonical `decision` + `projections` model

### 7. Controlled expansion of the public workbench

Deliver:

- stronger candidate-state bootstrap path
- safer examples and fixtures
- more credible first-run experience for non-reference users
- controlled tailoring research imported from local prototypes only through the canonical evidence/narrative model
- thin explicit sibling seams only where they reinforce the canonical model:
  - [specs/jobsync-integration-seam.md](specs/jobsync-integration-seam.md)
  - [specs/reactive-resume-integration-seam.md](specs/reactive-resume-integration-seam.md)

## After that

### 8. Broader deployment options

Deliver:

- optional Postgres-backed deployment using the same domain model
- broader public extension points where justified
- private-layer buildout on top of the stabilized public foundation

## Later

Only after the local-first model is stable:

1. broader multi-user support
2. candidate/advisor workflows beyond direct file editing
3. later private/commercial implementation built on top of the public foundation
4. selective retrieval improvements where they solve a proven problem

## Backlog only

These are not active roadmap items now and should not be treated as the current build path:

1. evaluate whether Supabase should ever be used as an optional new database/deployment substrate on top of the same canonical JobPipe model
2. review the deactivated NAV Supabase Edge ingestion script as a possible future intake backlog item only, not as the current canonical ingestion path
3. evaluate GitHub-native agent delegation, issue-form discipline, and project automation as workflow-governance improvements; see [specs/github-workflow-governance-audit-2026-04-21.md](specs/github-workflow-governance-audit-2026-04-21.md)

## Explicit non-goals for now

- recruiter-side product scope
- full ATS feature parity
- mass auto-apply
- broad workflow automation beyond the current loop
- generic AI copilot positioning
- full resume-builder parity
- vector-database-first architecture
- premature repo split before public scope and boundaries are stable
- public multi-user login
- turning persona audits into a public account system
