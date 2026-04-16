# JobPipe

*A local-first job search operating system.*

JobPipe ingests job leads, filters noise cheaply, scores the jobs worth attention, tracks application state, and exports a dashboard the candidate can actually use.

It is currently built as a single-user, local-first Python system. The codebase is structured so it can grow into a broader product later, but the current goal is operational clarity and decision quality, not SaaS surface area.

## What it does

JobPipe handles five linked problems:

1. intake from job feeds and suggestion sources
2. cheap filtering before expensive model calls
3. candidate-specific scoring and moderation
4. application-state tracking and follow-up
5. export of a dashboard plus application-support artifacts

The core promise is simple: spend attention and model cost only on jobs that still look plausible after the cheapest filters have done their work.

## Current architecture

JobPipe now runs on a primary SQLite database plus filesystem artifacts:

- `jobpipe.sqlite` stores candidate state, evaluations, application events, generated document metadata, and suggestion leads
- `out_runs/<run_id>/<job_id>/` keeps per-job stage artifacts for traceability
- `reports/dashboard.html` and `reports/dashboard_data.json` are derived exports
- `reports/evaluations_latest.csv` is a derived reporting export

The normal runtime flow is:

```text
job intake -> staged evaluation -> sync_evaluations -> primary DB -> export_dashboard
```

Legacy `ledger.sqlite` is removed from the runtime model. The primary DB is now the canonical state layer.

## Quick start

Requirements:

- Python 3.11+
- OpenAI API key
- published CSV URL for the source sheet
- optional Gmail API credentials for Gmail scanning

Setup:

```powershell
python -m venv .venv
.venv\Scripts\pip install -e .
copy .env.example .env
copy profile_pack.example.md profile_pack.md
```

Recommended for real use: keep candidate data outside the repo.

```powershell
set JOBPIPE_DATA_DIR=C:\Users\yourname\JobpipeData
```

Then configure:

- `.env` with `OPENAI_API_KEY` and `JOBPIPE_CSV_URL`
- `profile_pack.md` with the candidate search profile
- optional `resume.json` and Gmail credentials under `JOBPIPE_DATA_DIR`

Smoke test:

```powershell
.\go.ps1 -DryRun
```

Normal run:

```powershell
.\go.ps1
```

## Documentation map

Start here, depending on what you need:

- [PRODUCT_VISION.md](PRODUCT_VISION.md): product thesis, scope, and guiding principles
- [ROADMAP.md](ROADMAP.md): current execution priorities and sequencing
- [docs/architecture.md](docs/architecture.md): codebase and runtime architecture
- [docs/configuration.md](docs/configuration.md): env vars, candidate data, and runtime layout
- [docs/cli.md](docs/cli.md): operational command reference
- [docs/decision-model.md](docs/decision-model.md): evaluation stages and thresholds
- [docs/artifacts.md](docs/artifacts.md): runtime outputs and traceability model
- [docs/dashboard.md](docs/dashboard.md): dashboard data model and UI intent
- [docs/profile-pack.md](docs/profile-pack.md): candidate profile guidance
- [docs/apps-script.md](docs/apps-script.md): Google Apps Script operational notes
- [TESTING.md](TESTING.md): validation expectations
- [CONTRIBUTING.md](CONTRIBUTING.md): contribution rules

## Scope boundaries

JobPipe is:

- a decision-support system for job search
- local-first and traceability-focused
- opinionated about cheap filters before deeper AI evaluation
- structured around one candidate today, with explicit candidate IDs for future growth

JobPipe is not:

- an ATS replacement
- a mass auto-apply bot
- a resume-builder product
- a multi-tenant platform today

## Status

The repository is in active consolidation.

Current priorities are:

- keep the DB-first architecture coherent
- improve application-pack quality
- harden source intake and follow-up tracking
- keep the documentation and runtime model aligned

## License

MIT
