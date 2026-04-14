# Jobpipe

An AI-powered job hunting pipeline for the Norwegian job market. Ingests listings from NAV and FINN.no, runs a cost-tiered triage and scoring pipeline, generates application drafts for top matches, and tracks application status automatically via Gmail — all from a single command.

```powershell
.\go.ps1
```

---

## The problem it solves

Manually reviewing hundreds of job listings per week is slow, noisy, and inconsistent. Jobpipe automates the parts where AI outperforms human attention — filtering, ranking, and first-pass evaluation — so time can be spent on the parts that actually require human judgment: writing, relationships, and decisions.

---

## How it works

```
NAV pam-stilling-feed + FINN.no
    ↓  Apps Script (hourly, ~50 jobs/run) + pull_finn_search.py
Google Sheet / JSONL input
    ↓  pull_sheets_csv.py  (delta pull, active listings only)

Pipeline stages (per job):
    [FREE]   Geo postal filter        Oslo / Akershus / Vestfold-Telemark / Agder
    [FREE]   Hard-no title regex      Trades, retail, clinical, 1st-line support, etc.
    [FREE]   Semantic pre-filter      Multilingual cosine similarity vs. candidate profile
    [NANO]   Triage                   gpt-4.1-nano → SKIP / REVIEW / APPLY + noise_level
    [MINI]   Parse                    gpt-4.1-mini → structured job requirements
    [MINI]   Profile match            gpt-4.1-mini → fit_score 0–100 (4 dimensions)
    [MINI]   Pivot                    gpt-4.1-mini → pivot_score 0–100
    [FREE]   Moderate                 Deterministic thresholds → final decision
    [MINI]   Application pack         Draft cover letter + CV highlights (APPLY+ only)

    ↓  sync_ledger.py   →  reports/ledger.sqlite
    ↓  export_dashboard.py  →  reports/dashboard.html  (self-contained, opens in browser)

Gmail integration:
    scan_gmail.py  →  auto-detects application confirmations, interviews, rejections
                   →  updates application_state.json without manual input
```

**Design principle:** free filters run before any LLM call. The geo filter, regex filter, and semantic pre-filter eliminate the majority of listings at zero cost, so LLM spend is concentrated on genuinely relevant jobs.

---

## Decision tiers

| Decision | Condition |
|---|---|
| `APPLY_STRONGLY` | fit_score ≥ 78 |
| `APPLY` | fit_score ≥ 67 |
| `REVIEW_HIGH` | fit_score ≥ 58 |
| `REVIEW_LOW` | fit_score ≥ 30 |
| `SKIP` | fit_score < 30 or hard filter triggered |

Thresholds live in `configs/pipeline.v1.yaml` and are applied at export time — no re-run needed after changes.

---

## Per-job artifacts

Every job that passes initial filters produces a full artifact trail:

```
out_runs/<run_id>/<job_id>/
  00_input.json          Normalized job snapshot
  01_triage.json         AI triage signal + noise_level
  03_parsed.json         Structured requirements
  04_profile_match.json  fit_score + dimension breakdown
  05_pivot.json          pivot_score + rationale
  06_moderator.json      Final decision + reasoning
  07_application_pack.json  Cover letter draft + CV highlights (APPLY+ only)
```

Every decision is traceable. No hidden logic.

---

## Setup

**Requirements:** Python 3.11+, OpenAI API key, Google Sheets access (for NAV feed)

```powershell
# Create virtual environment and install dependencies
python -m venv .venv
.venv\Scripts\pip install -e .

# Configure environment
copy .env.example .env
# Fill in OPENAI_API_KEY and JOBPIPE_CSV_URL in .env

# Configure your candidate profile
copy profile_pack.example.md profile_pack.md
# Edit profile_pack.md with your own roles, geo preferences, and background
```

### Gmail integration (optional)

```powershell
# One-time OAuth setup
python -m jobpipe.cli.scan_gmail --setup

# Scan inbox and update application status
python -m jobpipe.cli.scan_gmail
```

Requires Gmail API credentials from Google Cloud Console — see `docs/gmail_filter_spec.md`.

---

## Running the pipeline

```powershell
.\go.ps1              # Full run: pull → process → sync → open dashboard
.\go.ps1 -DryRun      # Test mode: 2 jobs only, no browser
.\go.ps1 -NoOpen      # Full run, skip auto-opening browser
```

Manual steps are available in `CLAUDE.md` for finer control.

---

## Application tracking

```powershell
python -m jobpipe.cli.mark_status JOB_ID shortlisted
python -m jobpipe.cli.mark_status JOB_ID applied
python -m jobpipe.cli.mark_status JOB_ID interview
python -m jobpipe.cli.mark_status JOB_ID rejected --notes "Form letter"
python -m jobpipe.cli.mark_status JOB_ID dismissed
python -m jobpipe.cli.mark_status --list
```

---

## Adapting to your own job search

Jobpipe is built around a `profile_pack.md` file that defines your target roles, geographic constraints, keyword signals, and career evidence. The pipeline uses this file as the truth source for all triage and scoring decisions.

Start from `profile_pack.example.md` and replace with your own:
- Target role titles and seniority level
- Geographic whitelist (postal code ranges)
- Hard-no role types
- Keyword tiers (role anchors, domain signals, noise signals)
- Career evidence bullets in STAR format

The rest of the pipeline adapts automatically.

---

## Key files

| File | Purpose |
|---|---|
| `go.ps1` | One-shot runner |
| `configs/pipeline.v1.yaml` | Models, thresholds, regex patterns |
| `profile_pack.example.md` | Candidate profile template |
| `jobpipe/stages/` | Pipeline stage implementations |
| `jobpipe/cli/` | CLI entry points |
| `apps_script/` | Google Apps Script for NAV feed ingestion |
| `CLAUDE.md` | Full architecture and operating guide |

---

## License

MIT © Lars Værland
