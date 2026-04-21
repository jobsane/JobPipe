# T002 Slice 1 — AuthoringCaseContext contract audit and definition (Issue #58)

**Sprint:** T002 Sprint 1
**Issue:** #58 `Task: Audit current application_pack inputs and define AuthoringCaseContext`
**Branch:** `codex/T002-authoring-mvp`
**Worker:** Codex (implementation)
**Planner:** Claude (this document)
**Risk label:** Green
**Date:** 2026-04-21

---

## One-sentence objective

Audit the current `application_pack` stage inputs, then define the frozen
`AuthoringCaseContext` dataclass in a new `jobpipe/authoring/` module — no
generation, no validation, no agent call — so the next slice has an exact,
testable contract to build against.

## Why this slice is first

The spec (`specs/ai-document-authoring-mvp-workflow-2026-04-21.md`) requires a
bounded authoring contract before anything else can be built. Without it, the
generation step in #60 would reach through raw pipeline internals, making the
document layer fragile and untestable. This slice closes that gap without
touching any runtime path, schema, or agent call.

---

## Audit findings (planner-completed, do not re-audit)

### Primary construction site

`jobpipe/stages/application_pack.py` — `_build_application_pack_payload()` at
line 179. This function assembles a flat dict from seven upstream sources before
calling the Claude agent. The new `AuthoringCaseContext` replaces that ad-hoc
dict assembly with a typed, frozen dataclass that can be constructed once and
passed through.

### Upstream source map

| `AuthoringCaseContext` field | Python type | Canonical source object | Location |
|---|---|---|---|
| `candidate_id` | `str` | `ctx.meta["candidate_id"]` | `JobContext.meta` (dict) |
| `job_id` | `str` | `ctx.job_id` | `JobContext.job_id` |
| `evaluation_id` | `str \| None` | `ctx.meta.get("evaluation_id")` — `None` for MVP | `JobContext.meta` |
| `job_summary` | `dict` | `ctx.job` keys: `title`, `employer_name`, `sector`, `applicationDue`, `sourceurl` + `ctx.parsed.role_summary` | `JobContext.job` (dict) + `JobParse` |
| `decision_brief` | `dict` | `ctx.moderator` (`final_decision`, `recommendation_reason`, `cv_focus`) + `decision_ctx.decision_table` (`act_now`, 4-D scores) | `ModeratorOut` + `JobDecisionTable` |
| `selected_evidence` | `list[dict]` | `evidence_ctx.selected_evidence_units` serialized | `CandidateEvidenceSelection[]` from `jobpipe/decision/models.py:178` |
| `narrative_brief` | `dict \| None` | `narrative_ctx.narrative_profile` + `narrative_ctx.job_narrative_assessment` | `CandidateNarrativeContext` from `jobpipe/decision/models.py:248` |
| `artifact_plan` | `dict \| None` | `None` — reserved, not populated in MVP | — |

### Key model locations

| Class | File | Line (approx) |
|---|---|---|
| `JobContext` | `jobpipe/model/schema.py` | 243 |
| `ApplicationPackOut` | `jobpipe/model/schema.py` | 108 |
| `ModeratorOut` | `jobpipe/model/schema.py` | — |
| `DecisionContext` | `jobpipe/decision/models.py` | 324 |
| `CandidateEvidenceContext` | `jobpipe/decision/models.py` | 192 |
| `CandidateEvidenceSelection` | `jobpipe/decision/models.py` | 178 |
| `CandidateNarrativeContext` | `jobpipe/decision/models.py` | 248 |
| `JobDecisionTable` | `jobpipe/decision/models.py` | 152 |
| `CandidateNarrativeProfile` | `jobpipe/decision/models.py` | 203 |
| `JobNarrativeAssessment` | `jobpipe/decision/models.py` | 238 |

### crewai status

**None found.** Agent framework in use is `openai-agents` (via `deepagents`
local fork). No `import crewai` or `from crewai` anywhere in `jobpipe/` or
`tests/`. This must remain true after this slice.

### anyio / async status

**No async tests exist.** `pytest-asyncio>=0.23.0` is in dev deps but no
`@pytest.mark.asyncio` decorators are present. All tests are synchronous.
`AuthoringCaseContext` is a pure frozen dataclass — no async code required for
this slice. If a future slice calls into the `openai-agents` runtime, use
`asyncio.run()` in test helpers rather than introducing a new anyio dependency.

### Existing fixtures

`tests/fixtures/personas/` has four resume-only fixtures (persona_a–d). No
full-case fixture combining job + evaluation + narrative exists yet — that is
Slice 2 (#59), not this one.

---

## Files to create / edit

### Create: `jobpipe/authoring/__init__.py`

Empty init. Makes `jobpipe.authoring` a package.

### Create: `jobpipe/authoring/case_context.py`

Define the `AuthoringCaseContext` frozen dataclass exactly as specified below.
No builder function, no agent call, no generation logic — the contract only.

```python
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class AuthoringCaseContext:
    """
    Immutable authoring contract for one candidate × one job.

    Constructed once from existing JobPipe state before any document
    generation. All fields should be serialisable (plain dicts and lists)
    so the context can be logged and rehydrated without re-running the
    pipeline.

    Fields
    ------
    candidate_id:
        Candidate identifier, from JobContext.meta["candidate_id"].
    job_id:
        Job identifier, from JobContext.job_id.
    evaluation_id:
        Optional evaluation run identifier. None for MVP; reserved for
        when multiple evaluations per job are stored.
    job_summary:
        Flat dict with keys: title, employer_name, sector, application_due,
        source_url, role_summary. Drawn from JobContext.job + JobParse.
    decision_brief:
        Flat dict with keys from ModeratorOut (final_decision,
        recommendation_reason, cv_focus) and JobDecisionTable (act_now,
        can_do_score, can_get_score, should_want_score, can_explain_score).
    selected_evidence:
        List of serialised CandidateEvidenceSelection dicts — the already-
        filtered evidence units chosen for this specific job. Limit 6 by
        convention (see application_pack stage).
    narrative_brief:
        Optional dict with keys from CandidateNarrativeProfile
        (core_identity, future_direction, motivation_themes, pivot_thesis)
        and JobNarrativeAssessment (direction_fit_score,
        motivation_fit_score, story_strength_score, motivation_brief).
        None if narrative context was not computed.
    artifact_plan:
        Reserved for future use. None in the MVP.
    """

    candidate_id: str
    job_id: str
    evaluation_id: str | None
    job_summary: dict
    decision_brief: dict
    selected_evidence: list[dict]
    narrative_brief: dict | None
    artifact_plan: dict | None
```

### Create: `tests/test_authoring_case_context.py`

Unit tests for `AuthoringCaseContext`. All tests must be synchronous.

Tests required:

1. **Construction happy path** — instantiate with all fields; confirm field access returns correct values and the instance is frozen (`frozen=True` blocks attribute assignment).
2. **Frozen enforcement** — assigning to any field raises `FrozenInstanceError` (or `dataclasses.FrozenInstanceError`).
3. **None fields** — `evaluation_id=None`, `narrative_brief=None`, `artifact_plan=None` are all valid; no TypeError.
4. **Type shape** — `selected_evidence` accepts `list[dict]`; `job_summary` and `decision_brief` accept `dict`. No Pydantic validation here; plain dicts are fine.
5. **No crewai import (grep assertion)** — test that running `grep -r "crewai" jobpipe/ --include="*.py"` returns no output. This can be implemented as a subprocess call returning empty stdout. Mark this test clearly so it is easy to find: `test_no_crewai_import`.

---

## Files explicitly out of scope

Do not touch these. Stop and escalate to the coordinator if any of them appears to be required:

- `jobpipe/stages/application_pack.py` — no changes in this slice
- `jobpipe/decision/models.py` — no changes; read for reference only
- `jobpipe/model/schema.py` — no changes
- `jobpipe/core/` — no changes
- `configs/`, `specs/`, `docs/` beyond this execplan — no changes
- `pyproject.toml` — no new dependencies; `authoring` package is pure stdlib plus existing jobpipe imports
- `AUDIT.md`, `AGENT_STATUS.md` — historical; do not update

---

## Acceptance criteria

1. `jobpipe/authoring/__init__.py` exists and is importable.
2. `jobpipe/authoring/case_context.py` defines `AuthoringCaseContext` as a `@dataclass(frozen=True)` with the eight fields listed in the source map.
3. All field names and types match the spec (`specs/ai-document-authoring-mvp-workflow-2026-04-21.md` lines 56–65) exactly. Do not add, remove, or rename fields in this slice.
4. All five tests in `tests/test_authoring_case_context.py` pass.
5. `test_no_crewai_import` passes — grep returns empty stdout.
6. `python compile_check.py` exits 0.
7. No new runtime dependency introduced. `authoring/case_context.py` imports only from Python stdlib and existing `jobpipe` packages.
8. The module does not import from `crewai`, `crewai_tools`, `autogen`, `langchain`, or any external agent framework.

---

## Validation commands (run in order, report verbatim)

```bash
# 1. Targeted test
python -m pytest tests/test_authoring_case_context.py -v

# 2. Compile check
python compile_check.py

# 3. Importability smoke
python -c "from jobpipe.authoring.case_context import AuthoringCaseContext; print('ok')"

# 4. No-crewai grep (must return empty output)
grep -r "crewai" jobpipe/ --include="*.py" && echo "FAIL: crewai found" || echo "ok: no crewai"
```

**anyio note:** No anyio usage is expected or needed for this slice. `AuthoringCaseContext` is a pure dataclass. All tests are synchronous. Do not add `anyio` or `pytest-anyio` to solve a problem that does not exist here.

**Do NOT run `jobpipe run --dry-run`** for this slice — it does not touch the pipeline runtime path.

---

## Risk label

**Green.** New package, two new files, five synchronous tests. No schema, auth, billing, secret, deploy, pipeline-semantic, model-cost, or OSS/Workbench boundary surface.

---

## Escalation gates

Stop and ask the coordinator before acting if any of the following surfaces during implementation:

- Any reason to edit `application_pack.py`, `decision/models.py`, or `model/schema.py`
- Any new runtime dependency beyond stdlib + existing jobpipe packages
- Any async code path that requires event-loop infrastructure
- Any ambiguity about field naming or typing that would affect the Slice 2 fixture contract
- Any OSS/Workbench boundary question

---

## Founder decision needed

None for this slice as scoped.

---

## Self-review pass (8-item checklist)

Verified against `docs/ai-playbook.md` §"Slice Brief Self-Review":

1. **Scope inside T002.md / #58** — ✅ Only `AuthoringCaseContext` definition and unit tests. No generation, no agent call, no fixture.
2. **No crewai import anywhere** — ✅ Grep assertion confirms none exist; acceptance criteria and `test_no_crewai_import` enforce it going forward.
3. **No #82–#89 scope** — ✅ Supabase, hosted shell, and agent framework work explicitly excluded.
4. **Escalation gates defined** — ✅ Five gates listed above.
5. **Acceptance criteria are testable and deterministic** — ✅ Eight named criteria, all binary pass/fail.
6. **Validation commands specified** — ✅ Four ordered commands; anyio noted as N/A for this slice with the reason why.
7. **Risk label assigned** — ✅ Green, with justification.
8. **No TODO placeholders in Codex prompt** — ✅ Verified below.

---

## Codex worker prompt (ready-to-paste)

```
You are the Codex implementer on worktree ../Jobpipe-codex-v2, branch
codex/T002-authoring-mvp. Implement T002 Slice 1 (Issue #58): define the
AuthoringCaseContext frozen dataclass in a new jobpipe/authoring/ module.
Coordinator has APPROVED this slice as of 2026-04-21. Proceed.

Read first (in order):
  CLAUDE.md
  PRODUCT_VISION.md
  DEPENDENCY_POLICY.md
  docs/ai-playbook.md
  docs/current-state.json
  docs/execplans/T002.md
  docs/execplans/T002-slice-1.md  ← primary instruction source
  specs/ai-document-authoring-mvp-workflow-2026-04-21.md (lines 40-77)
  jobpipe/decision/models.py (read-only reference for upstream types)
  jobpipe/model/schema.py (read-only reference for JobContext)
  jobpipe/stages/application_pack.py (read-only reference; do not edit)

Scope — create these files only:

  1. jobpipe/authoring/__init__.py
     Empty init file. Makes jobpipe.authoring a package.

  2. jobpipe/authoring/case_context.py
     Define AuthoringCaseContext as a @dataclass(frozen=True) with exactly
     these eight fields (names and types must match the spec exactly):

       candidate_id: str
       job_id: str
       evaluation_id: str | None
       job_summary: dict
       decision_brief: dict
       selected_evidence: list[dict]
       narrative_brief: dict | None
       artifact_plan: dict | None

     Include a docstring per field explaining the canonical source (see
     docs/execplans/T002-slice-1.md §"Upstream source map" for the mapping).
     No builder function. No agent call. No generation logic. Contract only.
     Import only from Python stdlib and existing jobpipe packages.
     Do not import from crewai, crewai_tools, autogen, langchain, or any
     external agent framework.

  3. tests/test_authoring_case_context.py
     Five synchronous tests (no async, no anyio, no pytest.mark.asyncio):

     test_construction_happy_path
       Instantiate AuthoringCaseContext with all fields populated.
       Assert field access returns the values passed in.

     test_frozen_enforcement
       After construction, attempt to assign to any field.
       Assert dataclasses.FrozenInstanceError (or AttributeError) is raised.

     test_none_fields_valid
       Instantiate with evaluation_id=None, narrative_brief=None,
       artifact_plan=None. No TypeError should be raised.

     test_selected_evidence_is_list_of_dicts
       Pass selected_evidence as a list of dicts. Assert len matches.

     test_no_crewai_import
       Use subprocess.run to execute:
         grep -r "crewai" jobpipe/ --include="*.py"
       Assert returncode == 1 (grep returns 1 when no match found) AND
       stdout is empty. If any match is found, fail the test with a
       descriptive message.

Out of scope — do not touch, stop and escalate if required:
  jobpipe/stages/application_pack.py
  jobpipe/decision/models.py
  jobpipe/model/schema.py
  jobpipe/core/ (any file)
  configs/, specs/, docs/ (except reading for reference)
  pyproject.toml (no new dependencies)
  AUDIT.md, AGENT_STATUS.md

Runtime dependencies:
  stdlib only for the new module: dataclasses, __future__.
  Tests may use subprocess (stdlib) for the grep assertion.
  No new packages. No crewai. No anyio.

Validation — run in order and paste verbatim output into your handoff:
  python -m pytest tests/test_authoring_case_context.py -v
  python compile_check.py
  python -c "from jobpipe.authoring.case_context import AuthoringCaseContext; print('ok')"
  grep -r "crewai" jobpipe/ --include="*.py" && echo "FAIL: crewai found" || echo "ok: no crewai"

Do NOT run jobpipe run --dry-run. This slice does not touch the pipeline path.

Approval gates — stop and ask the coordinator before acting if:
  Any reason to edit application_pack.py, decision/models.py, or schema.py
  Any new runtime dependency beyond stdlib + existing jobpipe packages
  Any async code path requiring event-loop infrastructure
  Any ambiguity about field naming or typing that would affect Slice 2
  Any OSS/Workbench boundary question

Report back with:
  Exact list of files created (paths and line counts)
  Verbatim output of all four validation commands above
  One-line confirmation that no crewai import exists in jobpipe/
  One-line confirmation that no new runtime dependency was introduced
  Any escalation flags or unexpected findings
```

---

## Status

Approved — ready for Codex handoff on `codex/T002-authoring-mvp`. Tracked on GitHub Project #6 linked to issue #58 (Status: Ready, Priority: P1, Agent-ready). Planner approval stamped 2026-04-21. Escalation gates in the Codex worker prompt remain in force during implementation.
