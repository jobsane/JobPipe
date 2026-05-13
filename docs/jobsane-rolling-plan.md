# JobSane Rolling Plan

> **Historical (2026-05-13).** This document predates the removal of the JobSync integration.
> JobSync was an upstream/companion review surface that JobDesk + workspace_server have now replaced.
> Sections referencing jobsync modules, CLIs, or schemas reflect the older architecture and are
> kept for context only.


## Current Strategic Theme

Persistence seam and application loop foundation — before authoring, get the data contracts and event seam right.

## Open Slices — Sprint JobSane-1

| # | Title | Type | Status |
|---|-------|------|--------|
| #158 | Add JobSane North Star and rolling plan docs | docs | this issue |
| #167 | Map direct persistence hotspots | research, no code | Ready |
| #163 | Define JobPipe persistence seam and repository contracts | design doc | Ready |
| #159 | Define canonical application lifecycle and artifact contract | design doc | Ready |
| #165 | Define source event contract for leads, enrichment, and external signals | design doc | Ready |
| #166 | Define status reconciliation policy from events to canonical lifecycle | design doc | Ready |
| #168 | Define trigger policy for event-driven actions and decision briefs | design doc | Ready |

## Blocked on (before authoring implementation can start)

- T002 Sprint 1 contracts: `AuthoringCaseContext`, `GeneratedApplicationPackage`, `DocumentValidationResult` must exist in `jobpipe/model/`
- CrewAI dependency review (#86) — security and dependency audit
- Reactive Resume seam operational (`record-reactive-resume-document` CLI working)
- JobSync seam operational (`export-jobsync` and `record-jobsync-event` CLIs working)

## Next Implementation Milestone (after above)

- Ground Layer Crew (Job Analyzer + Company Researcher)
- CV Tailoring Crew wired to `AuthoringCaseContext`
- Cover Letter Crew with QA Reviewer
- Flow orchestration with candidate approval gate

---

Keep this doc updated as slices complete. Do not over-specify implementation order for slices more than 2 sprints ahead.
