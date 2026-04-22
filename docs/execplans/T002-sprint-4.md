# T002 Sprint 4 — Execplan

**Sprint goal:** Cover letter `.docx` rendering + crewAI flow entry point + `finalize_step` DB write-back.

**Governing specs:**
- `specs/ai-document-authoring-mvp-workflow-2026-04-21.md`
- `specs/crewai-flow-architecture-2026-04-22.md`

**Base:** `origin/main` (post PR #107 merge; Sprint 3 PR #115 must merge before Slices B/C start)

---

## Ordered Slices

| Slice | Dependency | Branch | Worker | Status |
|---|---|---|---|---|
| A — `render_cover_letter_docx` | None — Python 3.14, no crewai | `codex/T002-s4a-render-docx` | Codex | **In review** — PR #116 open (fa0deaa) |
| B — `scripts/flow_author.py` entry point | PR #115 merged ✓ | `codex/T002-s4b-flow-author` | Codex | **Handed to Codex** 2026-04-22 |
| C — `finalize_step` DB write-back | PR #115 merged ✓ | `codex/T002-s4c-finalize-step` | Codex | Ready after B merges |

Slice B unblocked (PR #115 merged). Hand to Codex now.

---

## Slice A — `render_cover_letter_docx`

**Branch:** `codex/T002-s4a-render-docx`
**Base:** `origin/main`
**Python env:** Python 3.14 main venv (`python` / `py`)
**GitHub Project item:** Pending creation (create before Codex opens PR)

**Files:**

| Path | Action |
|---|---|
| `jobpipe/authoring/render_docx.py` | CREATE — Python subprocess wrapper |
| `jobpipe/authoring/_render_cover_letter.js` | CREATE — Node.js docx script |
| `tests/test_render_docx.py` | CREATE — 3 tests |

**Acceptance criteria:**
- 3 tests pass under Python 3.14
- `compile_check.py` passes
- No `crewai` import in `render_docx.py`

**Signatures Verified:** N/A — all files are new. No existing codebase symbols referenced in module templates. `compile_check.py` confirmed present at repo root.

**Escalation gates:** None tripped. No DB, no auth, no crewai import in `jobpipe/`, no new PyPI dependency (stdlib only + node subprocess), no schema change.

**Full Codex prompt:** see `## SLICE A CODEX PROMPT` section below.

---

## Slice B — `scripts/flow_author.py`

**Branch:** `codex/T002-s4b-flow-author`
**Base:** `origin/main` after PR #115 merged
**Python env:** crewai-env (`C:\Users\larsv\envs\crewai-env\Scripts\python.exe`)

**Blocked until PR #115 merged.**

Brief will be written after Lars confirms #115 is in.

---

## Slice C — `finalize_step` DB write-back

**Branch:** `codex/T002-s4c-finalize-step`
**Base:** `origin/main` after PR #115 merged
**Python env:** crewai-env

**Blocked until PR #115 merged.**

**Key DB API:** `connect_primary_db(path: str | Path)` + `primary_db_path()` from `jobpipe.core.primary_db`. Escalation gate: schema version check before writing any migration.

---

## Sprint Exit Criteria

- All three slices merged to `main`
- Live `run_authoring_flow` smoke test passes end-to-end on an APPLY-decision job (from Windows, crewai-env)
- Sprint 3 S13 exit test confirmed (if not already done before Sprint 4 starts)

---

## Open Sprint 3 Items (do not start Sprint 4 close until these are resolved)

| Item | Issue | Blocking? |
|---|---|---|
| PR #115 merged | #115 | Blocks B + C |
| S13 live exit test (APPLY-decision job run) | — | Not blocking A; blocking sprint close |
| Fix evidence_refs type drift | #108 | No — hygiene |
| Fix test_author_cli_no_crewai assertion | #109 | No — hygiene |
| Remove dead sys.modules lookup | #110 | No — hygiene |

Issues #108/#109/#110 are Green XS fast-path eligible next sprint.
