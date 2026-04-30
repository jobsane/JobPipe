# Testing

## Principles

- Prefer small targeted tests.
- Keep one smoke path for the main workflow.
- Validate behavior changes before merging.
- Do not mix broad refactors and feature work in one change unless the task is explicitly a cleanup pass.
- Docs-only planning changes do not require runtime tests, but they do require cross-doc consistency checks.

## Minimum checks for code changes

For any meaningful code change:

1. Run the most relevant targeted test.
2. Run `python compile_check.py`.
3. Run a smoke test on a small fixture or dry-run path.
4. Confirm output format is unchanged unless intentionally updated.
5. Confirm the dashboard or other key derived exports still generate as expected.

Current audit baseline:

- `python compile_check.py` should pass.
- `python -m pytest tests/test_architecture_boundaries.py tests/test_runtime_pipeline.py -q` should pass.
- `python -m pytest tests/test_evaluation_state.py -q` should pass.
- `python -m pytest -q` should pass.
- `python -m jobpipe.cli.main run --dry-run --no-open` should pass.

The persona fixtures under `tests/fixtures/personas/` are synthetic calibration and regression fixtures.
They are safe public test data, not default user profiles and not product assumptions.

The current Windows audit baseline is expected to run without external `grep`.

## Practical rule

Every change should include one of:

- an updated test
- a new focused test
- a short manual validation note explaining why automated coverage was not added

## Smoke test

Preferred smoke test:

```text
jobpipe run --dry-run --no-open
```

Current meaning:
- bounded local smoke path
- skips live sheet intake
- processes at most two already-queued jobs if a local delta exists
- still runs sync/export so the canonical CLI and projection path are exercised
- zero processed jobs is acceptable when the local queue is empty

Fallback:

```text
python -m jobpipe.cli.main run --dry-run --no-open
```

Windows wrapper:

```powershell
.\go.ps1 -DryRun -NoOpen
```

For a step-by-step manual validation path with explicit success and failure outcomes, use [docs/public-loop-test-howto.md](docs/public-loop-test-howto.md).

## Planning / docs-only changes

For planning and docs alignment work:

1. verify the root docs do not contradict each other
2. verify `OSS_SCOPE.md` and `DEPENDENCY_POLICY.md` match the current planning layer
3. verify `specs/architecture-boundaries.md` matches the current planning layer and roadmap sequencing
4. verify `docs/` terminology matches the current planning layer
5. verify active specs and roadmap sequencing do not drift

## What to watch closely

Changes in these areas need extra care:

- filtering thresholds
- decision tiers
- claim extraction or selection logic
- output structure
- artifact/export generation
- Gmail or mail-ingestion behavior
- config-driven behavior
- DB schema or primary-state reads/writes
