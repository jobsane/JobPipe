# T002 Slice 6 — `--validate` flag on `build-authoring-context` CLI

**Sprint:** T002 Sprint 2
**Issue:** #63-followup (deferred from Slice 5 brief)
**Branch:** `codex/T002-authoring-mvp`
**Worker:** Codex (implementation)
**Risk label:** Green
**Date:** 2026-04-22

---

## 1. Scope

### In scope

Two existing files, additions only:

```
jobpipe/authoring/smoke_cli.py      — add --validate flag + wiring
tests/test_authoring_smoke_cli.py   — add tests for --validate behaviour
```

### Behaviour

When `--validate` is passed:

1. Build the `AuthoringCaseContext` as normal.
2. Call `validate_authoring_context(ctx)` (already on main in
   `jobpipe/authoring/validation.py`).
3. Print the validation summary to stderr (so stdout JSON stays clean).
4. Return exit code `0` if `result.passed` is True, `2` if False
   (distinct from argparse error exit `1`).

When `--validate` is **not** passed: behaviour is identical to Slice 4 —
no change.

### Validation summary format (stderr)

```
[validate] passed=True  score=1.00  failures=0  warnings=0
```

or on failure:

```
[validate] passed=False  score=0.60  failures=2  warnings=1
  FAIL: [missing_decision_context] decision_brief is missing required key: 'final_decision'
  FAIL: [empty_evidence_units] selected_evidence is empty ...
  WARN: [narrative_empty] narrative_brief is present but has no content ...
```

### Non-goals

- Do **not** modify any other file.
- Do **not** add a new module.
- Do **not** change the JSON stdout shape.
- Do **not** add external dependencies.
- Do **not** touch `case_context.py`, `output_models.py`, `builder.py`,
  `validation.py`, or any CLI file other than `smoke_cli.py`.

---

## 2. Signatures Verified Against origin/main @ d101e58

| Symbol | File | Signature |
|---|---|---|
| `validate_authoring_context` | `jobpipe/authoring/validation.py` | `def validate_authoring_context(ctx: AuthoringCaseContext) -> DocumentValidationResult:` |
| `DocumentValidationResult.passed` | `jobpipe/authoring/output_models.py` | `passed: bool` |
| `DocumentValidationResult.score` | `jobpipe/authoring/output_models.py` | `score: float` |
| `DocumentValidationResult.failures` | `jobpipe/authoring/output_models.py` | `failures: list[str]` |
| `DocumentValidationResult.warnings` | `jobpipe/authoring/output_models.py` | `warnings: list[str]` |
| `_add_arguments(p)` | `jobpipe/authoring/smoke_cli.py` | `def _add_arguments(p: argparse.ArgumentParser) -> None:` |
| `_run(args)` | `jobpipe/authoring/smoke_cli.py` | `def _run(args: argparse.Namespace) -> int:` |
| existing args fields | `jobpipe/authoring/smoke_cli.py` | `artifacts_root`, `run`, `job`, `candidate`, `out` |

---

## 3. Implementation notes

In `_add_arguments`:
```python
p.add_argument(
    "--validate",
    action="store_true",
    default=False,
    help="Run deterministic validation rules on the built context and report.",
)
```

In `_run`, after building `ctx`:
```python
if args.validate:
    from jobpipe.authoring.validation import validate_authoring_context
    result = validate_authoring_context(ctx)
    _print_validation_result(result)
    if not result.passed:
        return 2
```

New helper (private, in smoke_cli.py):
```python
def _print_validation_result(result: DocumentValidationResult) -> None:
    import sys
    summary = (
        f"[validate] passed={result.passed}"
        f"  score={result.score:.2f}"
        f"  failures={len(result.failures)}"
        f"  warnings={len(result.warnings)}"
    )
    print(summary, file=sys.stderr)
    for f in result.failures:
        print(f"  FAIL: {f}", file=sys.stderr)
    for w in result.warnings:
        print(f"  WARN: {w}", file=sys.stderr)
```

**Existing tests** pass `argparse.Namespace(...)` without a `validate` field.
After the change, `_run` reads `args.validate`. Fix existing tests by adding
`validate=False` to each `argparse.Namespace(...)` call in the test file.

---

## 4. Tests to add (in `tests/test_authoring_smoke_cli.py`)

Mirror the existing `test_cli_run_writes_stdout` pattern.

1. `test_validate_flag_passes_on_good_context` — monkeypatch
   `build_context_for_job` to return `_sentinel_context()` (it passes
   validation). Assert `_run(args)` returns `0` and stderr contains
   `passed=True`.

2. `test_validate_flag_fails_on_bad_context` — monkeypatch
   `build_context_for_job` to return an `AuthoringCaseContext` with
   `candidate_id=""` (triggers `required_field_absent`). Assert `_run(args)`
   returns `2` and stderr contains `passed=False` and `FAIL:`.

3. `test_validate_flag_absent_returns_zero` — no `--validate`, monkeypatched
   context. Assert `_run(args)` still returns `0` (regression guard).

4. `test_no_crewai_import` — already exists; keep it passing (smoke_cli.py
   must still have no crewai/autogen/langchain import after the change).

---

## 5. Acceptance criteria

- [ ] `--validate` flag accepted by `build-authoring-context` subcommand.
- [ ] Validation summary printed to stderr; stdout JSON unchanged.
- [ ] Exit code `0` on passed, `2` on failed.
- [ ] All existing tests in `test_authoring_smoke_cli.py` still pass (update
  Namespace calls as needed).
- [ ] 3 new tests added and passing.
- [ ] `python compile_check.py` exits 0.
- [ ] `test_no_crewai_import` passes.

---

## 6. Validation commands

```
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_authoring_smoke_cli.py -v -p no:debugging -p no:cacheprovider --basetemp .pytest-tmp
python compile_check.py
```

---

## 7. Project linkage

- Project: #6
- Branch: codex/T002-authoring-mvp
- Sprint: 2, Slice 6
