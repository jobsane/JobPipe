# Artifacts

## Purpose

JobPipe keeps a structured artifact trail so evaluation decisions stay inspectable.

Artifacts are not an accident. They are part of the product's trust model.

## Main artifact families

### Run artifacts

Per-job stage outputs live under:

```text
out_runs/<run_id>/<job_id>/
```

Typical files in the current stage order:

```text
00_input.json
01_triage.json
02_parsed.json
03_profile_match.json
04_pivot.json
05_moderator.json
06_application_pack.json
```

If `reverse_triage` is enabled, numbering shifts accordingly for that run.

### Primary DB

`jobpipe.sqlite` is the canonical state layer for:

- candidate state
- application events
- latest evaluations
- run history
- suggestion leads
- generated document metadata

### Exported outputs

Derived exports include:

- `reports/dashboard.html`
- `reports/dashboard_data.json`
- `reports/evaluations_latest.csv`

### Generated documents

Generated application material is stored on disk, while metadata is indexed into the primary DB.

## Why this matters

The artifact model makes it possible to answer:

- why did this job get skipped?
- what changed between runs?
- what document was generated for this job?
- what exactly did the model output at each stage?

That is materially better than a pipeline that emits only a final label.
