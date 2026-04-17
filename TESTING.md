# Testing

## Minimum Checks

Run these before closing a meaningful change:

```powershell
python compile_check.py
python -m pytest
```

## Runtime Check

For workflow-facing changes, also run a bounded local check when appropriate:

```powershell
.\go.ps1 -DryRun
```

## Documentation Check

For planning or repo-facing changes:

- confirm README, plan, and vision do not contradict each other
- confirm retired worknames are not reintroduced
- confirm the public OSS-first scope is still clear
