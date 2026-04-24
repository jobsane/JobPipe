# JobPipe Pull Connectors — Reference

**Audience:** CrewAI Job Hunter crew, external integrators, MCP server design.
**Status:** Current as of 2026-04-24. All four connectors are implemented and in production.

---

## Overview

JobPipe has four pull connectors — independent sources that feed job leads into the
shared pipeline queue (`jobs_delta.jsonl`). All four write the same JSONL format and
flow into the same triage → parse → profile_match → pivot → moderate → application_pack
pipeline stages.

```
NAV Sheet ──────────────────────────────────────────────┐
FINN keyword search ─────────────────────────────────── ▶  jobs_delta.jsonl → pipeline
FINN suggested (platform-recommended / Gmail leads) ─── ┘
Suggested leads (DB-queued) ─────────────────────────── ┘
```

Each connector is a standalone Python module callable via `jobpipe <command>` or
`python -m jobpipe.cli.<module>`.

---

## Connector 1 — NAV Sheet (`pull-sheets`)

**Module:** `jobpipe.cli.pull_sheets_csv`
**CLI:** `jobpipe pull-sheets --sheet-url $env:JOBPIPE_CSV_URL`

### What it does
Pulls the NAV public job feed from a Google Sheets mirror (updated externally by a
separate sync process). The sheet contains the full Norwegian national job feed — all
sectors, all regions — roughly 11,000–14,000 ACTIVE rows on a typical day.

### Filters applied at pull time (pre-AI, free)
| Filter | Default | Notes |
|---|---|---|
| `--status-filter ACTIVE` | ON | Drops ~30k INACTIVE rows immediately |
| `--skip-expired-deadline` | ON | Drops jobs where `applicationDue` is a past date. Exempts: `"snarest"`, `"asap"`, `"fortløpende"` |
| Deduplication by `uuid` | ON | Keeps newest version per job; tie-breaks on longer `description_html` |

### Key fields emitted
`uuid`, `job_id`, `title`, `employer_name`, `description_html`, `sourceurl`, `link`,
`applicationUrl`, `applicationDue`, `work_city`, `work_county`, `work_postalCode`,
`workLocations_json`, `sector`, `status`, `ad_updated`, `sistEndret`

### ACTIVE→INACTIVE tracking
Jobs that were ACTIVE in a previous pull but are now INACTIVE are written to
`jobs_expired.jsonl`. The `sync_evaluations` step uses this to mark closed jobs
in the DB, preventing them from surfacing in the KEEP pile after their deadline passes.

### When to use
- Primary feed — run before every calibration pass or full ingest
- Daily batch operation via `go.ps1`
- Calibration: combine with `drain_queue --batch-size 100 --max-loops N`

---

## Connector 2 — FINN Keyword Search (`pull-finn-search`)

**Module:** `jobpipe.cli.pull_finn_search`
**CLI:** `jobpipe pull-finn-search --max 40`

### What it does
Scrapes FINN.no public search pages using role-specific keyword queries configured in
`configs/pipeline.v1.yaml` under `finn_search.queries`. For each query it fetches
search result pages, extracts finnkodes, cross-references against the primary DB
(skips already-processed jobs), then fetches full job content for new ones using
JSON-LD → Next.js → HTML fallback.

### Current query set (from pipeline.v1.yaml)
- Produktansvarlig / produkteier / produktleder
- Digitaliseringsleder / konsulent
- IT-prosjektleder / rådgiver
- Tjenesteeier / systemansvarlig / plattformansvarlig
- CRM / Salesforce / ServiceNow
- E-commerce / netthandel / konvertering
- Endringsleder / forretningsutvikler / organisasjonsutvikling
- Programleder / PMO / portefølje / tjenesteforvalter

### Special behaviour
- Jobs tagged `suggested_by_platform=true` — **bypasses the semantic pre-filter**.
  The LLM triage stage decides directly. This is correct: FINN keyword results are
  already role-filtered, so semantic scoring would be redundant noise.
- Anti-bot time guard: only runs 09:00–19:00 Oslo time. Random 3–9s delays between
  fetches. Max 40 fetches per run.
- `--dry-run` mode lists new finnkodes without fetching content.

### When to use
- Daily alongside NAV pull for role-targeted top-up
- On-demand: "find more leads matching [query]" — add a query to YAML, run once
- Useful when NAV feed is stale or geo filter is cutting too aggressively

---

## Connector 3 — FINN Suggested / Gmail Leads (`pull-suggested`)

**Module:** `jobpipe.cli.pull_suggested`
**CLI:** `jobpipe pull-suggested --max 20`

### What it does
Processes platform-recommended job leads that were queued by `scan_gmail
--scan-suggestions`. These are jobs that FINN or LinkedIn emailed as suggestions
(e.g. "Jobs that match your profile"). The module reads queued leads from the primary
DB (`suggestion_leads` table), fetches full content from FINN.no for each, normalises
to pipeline JSONL format, and appends to `jobs_delta.jsonl`.

### Special behaviour
- Same `suggested_by_platform=true` tag as FINN keyword search — bypasses semantic filter.
- Same anti-bot time guard (09:00–19:00 Oslo, random delays, max 20/run).
- LinkedIn suggestions are queued but not yet auto-fetched (different scraping approach
  needed). They appear as pending entries in the DB.
- Falls back to `suggested_jobs.jsonl` if DB is unavailable.

### When to use
- After `scan_gmail --scan-suggestions` has run and populated the leads queue
- Part of the daily `go.ps1 -WithSuggestions` flow
- Not useful standalone unless Gmail scan has already run

---

## Connector 4 — FINN Extension (`pull-finn-ext`)

**Module:** `jobpipe.cli.pull_finn_ext`
**CLI:** `jobpipe pull-finn-ext`

### What it does
Fetches full content for individual FINN job URLs. Designed for manual or
browser-extension-triggered additions — a specific finn URL is queued and this
connector fetches and normalises it. Complements the keyword search connector
for one-off additions.

### When to use
- Manual adds: you spot a job directly on FINN and want to push it through the pipe
- Browser extension integration (future)
- Testing a specific job without running a full search pass

---

## Shared output format

All four connectors write to `jobs_delta.jsonl` (or a named delta file). One JSON
object per line, UTF-8. Key fields common to all sources:

```json
{
  "job_id": "stable-hash-or-uuid",
  "title": "Senior Product Manager",
  "employer_name": "Acme AS",
  "description_html": "<p>...</p>",
  "sourceurl": "https://nav.no/stillinger/...",
  "applicationUrl": "https://...",
  "applicationDue": "2026-05-30T00:00:00" ,
  "work_city": "Oslo",
  "work_county": "Oslo",
  "work_postalCode": "0150",
  "sector": "Privat",
  "suggested_by_platform": false,
  "source": "nav_sheet"
}
```

`suggested_by_platform=true` is set by connectors 2, 3, 4. It signals to the triage
stage to skip the semantic pre-filter.

---

## Which connector to use when

| Need | Connector |
|---|---|
| Full Norwegian market sweep | NAV Sheet (`pull-sheets`) |
| Targeted role search, high precision | FINN keyword (`pull-finn-search`) |
| Platform recommendations from email | FINN suggested (`pull-suggested`) |
| Single specific job URL | FINN extension (`pull-finn-ext`) |
| Daily automated operation | All four via `go.ps1 -WithSuggestions` |
| Calibration / staged ingest | NAV Sheet via `drain_queue` |
