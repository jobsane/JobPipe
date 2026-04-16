# Configuration

## Baseline setup

Start from:

```powershell
copy .env.example .env
copy profile_pack.example.md profile_pack.md
```

At minimum, set:

- `OPENAI_API_KEY`
- `JOBPIPE_CSV_URL`

## Recommended runtime layout

For normal use, keep candidate data outside the repo:

```powershell
JOBPIPE_DATA_DIR=C:\Users\yourname\JobpipeData
```

With that set, JobPipe can resolve:

- `profile_pack.md`
- `resume.json`
- `application_state.json`
- `gmail_credentials.json`
- `gmail_token.json`
- `suggested_jobs.jsonl`
- `profile_embedding.npy`
- `db/jobpipe.sqlite`

## Important env vars

### Required

- `OPENAI_API_KEY`
- `JOBPIPE_CSV_URL`

### Common optional

- `JOBPIPE_DATA_DIR`
- `JOBPIPE_CANDIDATE_ID`
- `JOBPIPE_PROFILE_PATH`
- `JOBPIPE_RESUME_JSON`
- `JOBPIPE_DB_PATH`
- `JOBPIPE_EXPORT_DIR`
- `JOBPIPE_ARTIFACT_DIR`
- `JOBPIPE_DOCUMENTS_DIR`

### Gmail-related

- `JOBPIPE_GMAIL_CREDENTIALS_PATH`
- `JOBPIPE_GMAIL_TOKEN_PATH`

## Candidate profile inputs

There are two practical candidate inputs today:

- `profile_pack.md`
- `resume.json`

They are still valid working files, but the runtime is moving toward the primary DB as the canonical state layer. Use `bootstrap_state_db` to import current local candidate data into the DB.

## Pipeline configuration

Pipeline behavior is controlled in:

- `configs/pipeline.v1.yaml`

This file defines:

- stage order
- model choices
- thresholds
- regex rules
- FINN search defaults

## Source-specific notes

### Sheet intake

The main batch path expects a published CSV URL, not a private edit URL, unless you are explicitly using the sheet URL mode.

### Gmail

Gmail integration is optional. If enabled, it can:

- detect application-state changes
- ingest suggestion emails from supported sources

See:

- [docs/cli.md](cli.md)
- [docs/gmail_filter_spec.md](gmail_filter_spec.md)

## Safe change strategy

1. Change one control point at a time.
2. Prefer a dry run after threshold or config changes.
3. Keep candidate data separate from code.
4. Treat exported files as derived outputs, not configuration.
