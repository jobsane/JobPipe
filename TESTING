# Testing

## Principles

- Prefer small targeted tests
- Keep one smoke test for the main workflow
- Validate behavior changes before merging
- Do not mix feature work and broad refactoring in one change

## Minimum checks

For any meaningful code change:

1. Run the most relevant targeted test
2. Run a smoke test on a small fixture dataset
3. Confirm output format is unchanged unless intentionally updated
4. Confirm the dashboard or key artifacts still generate as expected

## Practical rule

Every change should have one of these:
- an updated test
- a new focused test
- a short manual validation note explaining why automated coverage was not added

## Smoke test

Typical smoke test:

```powershell
.\go.ps1 -DryRun
```

This should be enough to confirm the pipeline still runs through its key steps without needing a full production-style run.

## What to watch closely

Changes that affect these areas need extra care:
- filtering thresholds
- decision tiers
- output structure
- artifact generation
- Gmail status handling
- config-driven behavior
