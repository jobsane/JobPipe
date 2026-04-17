# JobPipe - Product Vision

## Core Thesis

JobPipe is a candidate-first, hiring-aware, local-first career intelligence workbench.

It exists to help a serious job seeker identify and act on the opportunities they are genuinely competitive for by turning job data, candidate data, and application history into:

- structured evidence
- explicit decision support
- living monitoring
- better action

## Why It Matters

Most job-search tools optimize for more listings, more drafts, or more automation surface.

JobPipe should optimize for better judgment:

- which roles are actually worth pursuing
- where the candidate is stronger than the first impression suggests
- what evidence supports the case
- what changed since the last review
- what the next action should be

## Primary User

The current user is a serious, privacy-conscious job seeker working through a high-noise search process and needing better prioritization, clearer evidence, and lower cognitive overhead.

## Wedge

The wedge is not resume generation and not volume automation.

The wedge is:

- decision quality
- evidence reuse
- candidate-first but hiring-aware evaluation
- repeated value through monitoring and follow-up

## Product Direction

The strongest next substrate is:

1. job claims
2. hiring-aware decision tables and selection signals
3. candidate evidence units
4. candidate narrative profiles
5. watchlists and change events

Those layers should eventually make JobPipe less dependent on ad hoc scoring output and more grounded in inspectable, reusable, local-first decision state.

## Public / Private Shape

This public repository should become a real OSS framework/toolkit foundation.

If a later commercial layer exists, it should build on top of the public foundation rather than live ambiguously inside it. The likely naming direction is:

- `JobPipe` for the public project
- `JobPipe Workbench` for a later private/commercial implementation

## Non-Goals For This Phase

Not now:

- full recruiter platform
- ATS replacement
- mass auto-apply
- generic AI copilot positioning
- broad automation suite
- platform breadth before the core decision layer is sound

## Design Principles

1. Data is the product.
2. Connectors are adapters.
3. Dashboards and external tools are projections.
4. AI is a bounded interpretation layer, not the product identity.
5. Privacy and local-first operation are constraints, not decoration.
6. The repo should tell one coherent story in public.
