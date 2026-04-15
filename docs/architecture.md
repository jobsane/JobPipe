# Architecture Notes

This is a lightweight overview of how Jobpipe is organized.

## High-level shape

Jobpipe follows a staged workflow:

1. pull or receive job data
2. normalize input
3. apply cheap filtering
4. run deeper evaluation where justified
5. moderate into final decisions
6. sync data into tracking outputs
7. generate reports and dashboard output

## Key ideas

- cheap filtering before expensive model calls
- deterministic moderation after model-assisted evaluation
- traceable artifact generation
- practical outputs over opaque automation

## Useful files

| File | Purpose |
|---|---|
| `go.ps1` | One-shot runner |
| `configs/pipeline.v1.yaml` | Models, thresholds, regex patterns |
| `profile_pack.example.md` | Candidate profile template |
| `jobpipe/stages/` | Pipeline stage implementations |
| `jobpipe/cli/` | CLI entry points |
| `apps_script/` | Google Apps Script for NAV feed ingestion |
| `reports/` | Generated outputs such as ledger and dashboard |

## Scope note

This is a solo-built project. The architecture is meant to stay understandable and practical, not perform complexity for its own sake.
