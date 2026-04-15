# Artifacts

Jobpipe is designed to leave a structured trail.

That is intentional.

The goal is not black-box automation. The goal is reviewable workflow support.

## Typical artifact flow

Every job that passes initial filters can produce a structured set of artifacts, for example:

```text
out_runs/<run_id>/<job_id>/
  00_input.json
  01_triage.json
  03_parsed.json
  04_profile_match.json
  05_pivot.json
  06_moderator.json
  07_application_pack.json
```

## Why artifacts matter

Artifacts help make the process:
- traceable
- explainable
- easier to debug
- easier to review
- easier to improve over time

## Typical outputs

Depending on the run, Jobpipe may generate:
- normalized job snapshots
- triage signals
- parsed requirements
- fit scoring
- pivot scoring
- final moderated decisions
- application-support material
- dashboard-ready output
- ledger or tracking data

## Practical benefit

This makes it possible to inspect what happened for a given job instead of treating the pipeline as a hidden chain of model calls.
