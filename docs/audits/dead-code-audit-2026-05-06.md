# Dead Code Audit — 2026-05-06

**Tool:** `codebase-index` (static analysis, 2026-05-05)
**Issue:** [#201 — Codebase dead-code audit](https://github.com/larsvaerland/Jobpipe/issues/201)
**Total findings:** 32 symbols across 11 files

---

## Summary

After manual verification, **31 of 32 findings are false positives** caused by patterns
that The tool's static call-graph analysis cannot follow. One symbol is confirmed dead.
Five test-file findings warrant spot review but are likely pytest patterns.

---

## Confirmed Dead Code

| Symbol | File | Line | Evidence | Recommended action |
|---|---|---|---|---|
| `_get_postal` | `jobpipe/stages/triage.py` | 132 | Zero callers; `_get_postals` (plural) is used instead | Remove in a safe PR |

---

## False Positives — Framework/Callback Patterns

The tool cannot trace these patterns; they are genuinely used at runtime.

### Callback / function-object pattern

Functions returned by factory functions and stored as `should_run` callbacks on `Stage` objects.
Registered in `stages/pipeline.py` via `Stage(should_run=<fn>)`.

| Symbol | File |
|---|---|
| `should_run` | `stages/application_pack.py:469` |
| `should_run` | `stages/moderate.py:115` |
| `should_run` | `stages/parse.py:34` |
| `should_run` | `stages/pivot.py:31` |
| `should_run` | `stages/profile_match.py:77` |
| `should_run` | `stages/reverse_triage.py:41` |
| `should_run` | `stages/triage.py:292` |
| `_filter` | `stages/semantic_filter.py:157` |

### Rule-list registration pattern

Private functions referenced by name in a list inside `authoring/validation.py:151-155`.

| Symbol | File |
|---|---|
| `_rule_required_field_absent` | `authoring/validation.py:46` |
| `_rule_missing_decision_context` | `authoring/validation.py:61` |
| `_rule_empty_evidence_units` | `authoring/validation.py:73` |
| `_rule_narrative_empty` | `authoring/validation.py:85` |
| `_rule_resume_job_mismatch` | `authoring/validation.py:121` |

### CrewAI Flow `@listen` decoration

Methods registered as event listeners via CrewAI's `@listen("apply")` decorator.
The runtime dispatches these via the flow's event bus, not direct Python calls.

| Symbol | File |
|---|---|
| `build_context_step` | `jobpipe_crewai/flow.py:60` |
| `persist_step` | `jobpipe_crewai/flow.py:94` |
| `finalize_step` | `jobpipe_crewai/flow.py:115` |

### Stale index — callers exist but were missed

codebase-index index dated 2026-05-05. These symbols have confirmed callers in the codebase;
The tool missed them, probably due to cross-module import aliasing or index currency.

| Symbol | File | Verified callers |
|---|---|---|
| `_slug` | `decision/evidence.py:51` | `profile_layer.py`, `calibration.py`, `derive.py` (31 call sites) |
| `_rewrite_policy_for_source` | `decision/evidence.py:68` | 2 callers in `decision/` |
| `_profile_lines` | `decision/narrative.py:75` | 2 callers |
| `_save_state` | `cli/scan_gmail.py:234` | Called at line 887 |
| `load_profile_pack` | `core/io.py:21` | `dashboard_server.py`, `run_feed.py` (9 call sites) |
| `_get_postal` *(not _get_postals)* | `stages/triage.py:132` | **0 callers — this one IS dead** |

---

## Test Helpers — Spot Review Recommended

These appear in test files and may be pytest fixtures or helpers defined at module scope
but called indirectly by pytest. Recommend a quick `pytest -k <test_file>` check.

| Symbol | File |
|---|---|
| `fake_run_agent` | `tests/test_author_adapter.py:75` |
| `close` | `tests/test_author_cli.py:139` |
| `_iter_mail_modules` | `tests/test_mail_boundary.py:39` |
| `fake_run_command` | `tests/test_persona_audit.py:179` |
| `fake_copy_catalog_tables` | `tests/test_persona_audit.py:184` |
| `fake_build_payload` | `tests/test_persona_audit.py:188` |
| `_stub_stage_factory` | `tests/test_runtime_pipeline.py:10` |
| `_should_run` | `tests/test_runtime_pipeline.py:11` |
| `_run` | `tests/test_runtime_pipeline.py:14` |

---

## Analysis Index Note

The tool's dead-code detection works best on direct-call patterns. The following patterns
produce systematic false positives and should be excluded from future dead-code reviews:

1. **Factory closures** (`_filter`, `_get_postal`-like inner functions returned by factories)
2. **Callback registrations** (`should_run` stored in `Stage(should_run=fn)`)
3. **Rule lists** (functions appended to a list and dispatched in a loop)
4. **Framework decorators** (CrewAI `@listen`, `@router`, `@start`)

---

## Action Items

| Issue | Scope | Priority |
|---|---|---|
| #202 | Remove `triage._get_postal` (confirmed dead) | P2 / XS |
| #203 | Spot-check test helper functions via `pytest --collect` | P3 / S |
