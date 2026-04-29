# AI Document Authoring MVP Workflow

Date: 2026-04-21

## Purpose

This spec translates the pasted AI-document-generation / Supabase / unified-dashboard plan into a dependency-compliant JobPipe workflow.

The plan is now represented in GitHub Project #6 as issues #56-#89. This document records the governing interpretation so implementation does not drift into adopting Copilot's generated architecture literally.

## Core Decision

The first usable path is **not** Supabase, CrewAI, FastAPI, or a new unified React shell.

The first usable path is:

1. take one already-evaluated actionable job;
2. build a structured authoring context from existing JobPipe state;
3. generate evidence-backed CV and cover-letter drafts;
4. validate drafts before treating them as usable;
5. allow bounded refinement/versioning;
6. save final document refs back to the JobPipe case.

Only after that works should JobPipe evaluate a Supabase-backed private Workbench or third-party agent framework.

## Guardrails

- JobPipe remains local-first for the MVP.
- Generated documents are derived artifacts, not source of truth.
- Large generated files live under `JOBPIPE_DATA_DIR/documents`.
- Canonical metadata and provenance stay in JobPipe state.
- Reactive Resume remains an optional editor/render surface.
- JobSync remains a workflow/status companion.
- Supabase remains optional deployment/storage research until the local MVP is working.
- CrewAI, AutoGen, LangChain, and similar frameworks require dependency/security review before adoption.

## Minimal MVP Flow

```text
actionable job
  -> AuthoringCaseContext
  -> structured application package
  -> validation report
  -> draft CV / cover letter
  -> user + AI refinement
  -> final document refs
  -> JobPipe case state
```

## First Contract Sketch

The first implementation should build a narrow case context instead of letting the generator reach through raw artifacts.

```python
@dataclass(frozen=True)
class AuthoringCaseContext:
    candidate_id: str
    job_id: str
    evaluation_id: str | None
    job_summary: dict
    decision_brief: dict
    selected_evidence: list[dict]
    narrative_brief: dict | None
    artifact_plan: dict | None
```

The first package output should remain structured before any DOCX/PDF rendering.

```python
class GeneratedApplicationPackage(BaseModel):
    job_id: str
    cover_letter_draft: str
    tailored_cv_projection: dict
    evidence_refs: list[str]
    gap_notes: list[str]
    validation: dict | None = None
```

The first quality gate should be explicit and deterministic where possible.

```python
class DocumentValidationResult(BaseModel):
    passed: bool
    score: float
    failures: list[str]
    warnings: list[str]
```

## Project Breakdown

### Local Authoring MVP

Parent: #56 `Epic: Usable AI application authoring MVP`

Ready first:

- #57 `Feature: One-case authoring contract from existing JobPipe data`
- #58 `Task: Audit current application_pack inputs and define AuthoringCaseContext`
- #59 `Task: Create frozen one-job authoring fixture`
- #60 `Story: Generate one structured application package from a bounded case`
- #61 `Task: Add one-case authoring smoke command or test helper`
- #62 `Feature: Quality-gated document generation`
- #63 `Task: Implement deterministic document validation checklist`

Backlog behind the first contract:

- #64 `Story: Persist validation report and flag failed generated outputs`
- #65 `Task: Add golden-output tests for good and bad document drafts`
- #66 `Feature: Case-scoped cover-letter draft and refinement loop`
- #67 `Story: Generate editable cover-letter draft from tailored CV context`
- #68 `Task: Add revise-cover-letter operation with chat feedback payload`
- #69 `Task: Record cover-letter versions and final DOCX refs`
- #70 `Feature: Evidence-backed tailored CV projection MVP`
- #71 `Story: Render ATS-safe tailored CV projection from selected evidence`
- #72 `Task: Map tailored_cv_projection to Reactive Resume patch/export plan`
- #73 `Task: Record rendered CV artifact refs and provenance`
- #74 `Feature: Local document persistence and version history`
- #75 `Task: Extend generated_documents metadata for draft/refined/final states`
- #76 `Story: Rehydrate latest document state in dashboard/apply workspace`
- #77 `Task: Keep generated documents under JOBPIPE_DATA_DIR documents root`
- #78 `Feature: Dashboard authoring workspace MVP`
- #79 `Story: Surface apply workspace from actionable jobs to generated docs`
- #80 `Task: Show generation status, validation issues, latest document refs, and next action`
- #81 `Task: Add local regenerate, refine, and save-final controls behind existing seams`

### Optional Workbench / Supabase Path

Parent: #82 `Epic: Unified Workbench shell and optional Supabase backend`

This stays backlog until #56 produces a usable local MVP.

- #83 `Spike: Decide SQLite-to-Supabase domain mapping without replacing local-first`
- #84 `Task: Define shared module contracts for JobPipe, JobSync, and Reactive Resume`
- #85 `Spike: Evaluate Supabase auth, RLS, storage, and realtime for private Workbench`
- #86 `Spike: Evaluate CrewAI, AutoGen, and LangChain for wrapped document-agent runtime`
- #87 `Feature: Hosted/private dashboard shell wrapping the modules`
- #88 `Task: Define event and broadcast contract for dashboard shell`
- #89 `Task: Define migration gate from local MVP to Supabase-backed Workbench`

## Review Recommendation

Review #56 first as the controlling epic.

If accepted, the first sprint should take only:

- #58
- #59
- #60
- #61
- #63

Do not start #82 or any Supabase/hosted-shell work until the local authoring MVP has a working one-case generation, validation, and saveback loop.

## Validation Standard

For the first implementation slice:

- focused tests for case-context construction;
- focused tests for validation checklist pass/fail behavior;
- `python compile_check.py`;
- one local one-case authoring smoke path;
- no full NAV queue drain.

## Success Criteria

The MVP is usable when the candidate can:

1. open/select one worthwhile job;
2. generate a structured application package from JobPipe state;
3. see whether the draft passed validation;
4. revise or regenerate without overwriting provenance;
5. save final CV and cover-letter refs back to the JobPipe case;
6. continue tracking application status through the existing JobPipe/JobSync seam.

## Explicit Non-goals

- no mass auto-apply;
- no full resume-builder replacement;
- no broad hosted platform before local proof;
- no unreviewed third-party agent framework dependency;
- no deep sibling-repo coupling;
- no freeform document generation that bypasses evidence provenance.
