# CLI Usage

This document collects common command-line entry points and examples.

## Main run

```powershell
.\go.ps1
```

Useful options:

```powershell
.\go.ps1 -DryRun
.\go.ps1 -NoOpen
```

## Gmail setup and scan

Optional Gmail support:

```powershell
python -m jobpipe.cli.scan_gmail --setup
python -m jobpipe.cli.scan_gmail
```

## Manual application status updates

```powershell
python -m jobpipe.cli.mark_status JOB_ID shortlisted
python -m jobpipe.cli.mark_status JOB_ID applied
python -m jobpipe.cli.mark_status JOB_ID interview
python -m jobpipe.cli.mark_status JOB_ID rejected --notes "Form letter"
python -m jobpipe.cli.mark_status JOB_ID dismissed
python -m jobpipe.cli.mark_status --list
```

## Notes

Use the CLI when you want more direct control than the one-shot runner provides.

For broader workflow structure, see:
- `README.md`
- `docs/configuration.md`
- `docs/decision-model.md`
