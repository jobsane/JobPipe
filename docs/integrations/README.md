# JobPipe external integrations

> **Historical (2026-05-13).** This document predates the removal of the JobSync integration.
> JobSync was an upstream/companion review surface that JobDesk + workspace_server have now replaced.
> Sections referencing jobsync modules, CLIs, or schemas reflect the older architecture and are
> kept for context only.


**Last updated:** 2026-04-21

This directory documents how JobPipe integrates with external projects. The
rule is **slim seams, replaceable adapters, minimum integration**. JobPipe is
the engine; the external projects are noise-reducing surfaces around it.

## Role split

| Project          | Role in the workflow                                             | Fork? | Integration style                    | Canonical seam spec                                  |
| ---------------- | ---------------------------------------------------------------- | ----- | ------------------------------------ | ---------------------------------------------------- |
| JobPipe          | Engine. Canonical decision state, evidence, claims, narrative.   | n/a   | n/a                                  | `MASTER_PLAN.md`, `PRODUCT_VISION.md`                |
| reactive-resume  | GUI / resume editor. Structured resume interchange surface.      | No    | JSON round-trip via JobPipe CLIs     | `specs/reactive-resume-integration-seam.md`          |
| jobsync          | Candidate-facing decision + application-status surface.          | No    | Event-based CLIs                     | `specs/jobsync-integration-seam.md`                  |
| crewAI           | Prospective agent runtime for author/revise loop.                | Yes*  | Not yet integrated (hybrid / Option C) | `specs/ai-document-authoring-mvp-workflow-2026-04-21.md` |

\* `larsvaerland/crewAI` is a tracking fork of `crewaiinc/crewai`. The fork
exists as scaffolding; it should carry real patches only when crewAI is
actually integrated.

## Mental model

> Data is the product. JobPipe is the engine. The rest is hiding the noise
> up until the candidate presses apply.

- **JobPipe** owns canonical decision state: evidence units, claims,
  selection signals, narrative profiles, decision tables, tailoring plans.
- **reactive-resume** is a very good GUI/editor for structured resumes.
  It renders and edits. It does not decide what to tailor. Its optional
  `Resume Analysis` feature may serve as a post-tailoring QA layer, never
  as a canonical source.
- **jobsync** is the candidate-facing decision and tracking surface. It
  consumes compact projections and emits workflow events. It does not own
  job evaluation, claim, narrative, or selection semantics.
- **crewAI** is the planned author/revise runtime inside JobPipe's tailoring
  flow. Contracts that cross the agent boundary (`AuthoringCaseContext`,
  `GeneratedApplicationPackage`, `DocumentValidationResult`) stay
  JobPipe-native and agent-runtime-swappable.

## Integration policy

1. Depend on upstream at a pinned version. Do not fork unless a specific
   patch JobPipe cannot live without exists (and try to contribute
   upstream first).
2. Never import external project internals from JobPipe directly. Go
   through a single JobPipe-owned adapter module per external project.
   Replacing the external project means rewriting only the adapter.
3. Treat cross-seam changes (new fields, new endpoints, new events) as
   boundary-level work. Extend the adapter contract rather than leak
   external types into the JobPipe canonical model.
4. Keep license compatibility explicit before vendoring anything. Default
   is "remain external."

## Current status

- reactive-resume: slim JSON seam in place via `jobpipe import-reactive-resume`,
  `jobpipe export-reactive-resume-plan`, `jobpipe record-reactive-resume-document`.
  Canonical ownership of tailoring decisions remains in JobPipe.
- jobsync: slim event seam in place via `jobpipe export-jobsync` and
  `jobpipe record-jobsync-event`. Canonical ownership of decision state
  remains in JobPipe.
- crewAI: prospective. Integration path deferred behind T002
  (AI document authoring MVP). Option C decided 2026-04-21: deterministic
  contracts JobPipe-native, agent-runtime layer pluggable.

## When adding a new integration

Before writing code:

1. Add or update the seam spec in `specs/`.
2. Add the integration row to the table above.
3. Confirm license compatibility with the public OSS repo policy
   (`DEPENDENCY_POLICY.md`).
4. Decide on fork-vs-upstream per the integration policy above.
5. Land the adapter as a single JobPipe-owned module. Do not expose the
   external project's types to the rest of the codebase.
