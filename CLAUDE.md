# Claude Agent Instructions: JobPipe / Agentic JobPilot

## Read these files first — every session, no exceptions

Before writing any code or making any changes, read these files in order:

1. **`docs/mvp-task-plan.md`** — ordered execution contract. Identify the active topic before touching code.
2. **`docs/architecture-plan.md`** — ownership and boundary contract. Confirm the work is implementable without hidden repo coupling.
3. **`AUDIT.md`** — deep audit log. Open bugs, data quality issues, tech debt. Check your section; fix what you can.
4. **`CLAUDE.md`** — repo operating guide. Follow the working rules here.

Then read supporting docs as needed:
- `AGENT_STATUS.md` — shared memory bus. Current state of all workstreams, what changed recently, open handoffs.
- `PRODUCT_VISION.md` — product goals, success metrics, and long-range user workflow.
- `README.md` / `DASHBOARD_SPEC.md` / other subsystem docs when relevant.

After making changes: **update your sections in AGENT_STATUS.md and AUDIT.md**.

## Documentation discipline

Keep documentation inside the canonical files. Do not create extra dated audits, duplicate agent guides, loose research dumps, or backup planning notes unless the user explicitly asks for a new artifact.

Canonical set:
- `README.md` — repo entrypoint and operator quickstart
- `CLAUDE.md` — repo operating guide
- `AGENT_STATUS.md` — current workstream state and handoffs
- `AUDIT.md` — defects, data-quality issues, debt, and audit history
- `PRODUCT_VISION.md` — strategy, success metrics, and roadmap
- `docs/architecture-plan.md` — architecture and red-line contract
- `docs/mvp-task-plan.md` — ordered implementation plan
- `DASHBOARD_SPEC.md` — dashboard and payload contract

Only keep specialized docs when they support a specific subsystem with ongoing operational value, such as `APPS_SCRIPT_CHANGES.md` or `docs/gmail_filter_spec.md`.

---

## What this repo is

An AI-powered job hunting pipeline that pulls jobs from a Google Sheet (sourced from NAV's pam-stilling-feed API), runs a staged agentic triage + scoring pipeline (OpenAI Agents SDK), writes per-job JSON artifacts, and produces a shared dashboard/control-plane surface for both static export and local server mode.

**Design principles (from PRODUCT_VISION.md):**
1. **Cheap before smart** — free filters before any LLM call, but the deterministic gate stack can differ by connector when the source has already pre-vetted relevance.
2. **Never miss a strong match** — safety overrides catch false negatives even when the LLM says SKIP.
3. **Every decision is debuggable** — every stage writes a JSON artifact. No hidden logic.
4. **Incremental, not monolithic** — process deltas, not the full feed.
5. **Human in the loop** — the system recommends, Lars decides. No auto-apply.

Product thesis:
- the actual value is the job-ad data and what the system can infer from it
- the system should remove cognitive noise before the user spends effort
- the user should spend time on review, tailoring, applying, and follow-up, not on feed scanning

<<<<<<< HEAD
Planning split:
- `PRODUCT_VISION.md` = north star and long-term roadmap
- `docs/architecture-plan.md` = ownership and boundaries
- `docs/mvp-task-plan.md` = ordered short-term execution
- `AUDIT.md` = defects / quality / debt
- `AGENT_STATUS.md` = current state and handoffs

## Sprint discipline

Treat the active roadmap topic as the current sprint.

Sprint sequence:
1. confirm what the docs intend
2. verify the intended change is implementable in the current codebase
3. make the smallest doc correction first if the plan and code reality disagree
4. implement only the active sprint/topic
5. run sprint-relevant validation before calling it done
6. clean up topic-local clutter that is safe to remove
7. align canonical docs with what actually shipped
8. update `AUDIT.md` and `AGENT_STATUS.md` with changes, validation, open items, and deviations
9. only then checkpoint/sync repo state

Definition of done:
- working code or an explicit doc-only correction when code would be dishonest
- validation run and recorded
- docs aligned
- audit/history updated
- continuation state clear enough that the next agent can understand both the big picture and the current sprint details without reverse-engineering chat logs

---

## Companion system target

This repo is not the whole product surface.

The intended stack is:

1. `JobPipe`
   - intake engine
   - triage and scoring
   - application-packet and apply-session generation
   - pipeline memory, artifacts, and calibration
2. `JobSync`
   - long-term operator shell
   - active application queue
   - notes, tasks, follow-up, and manual workflow
3. `Reactive Resume`
   - structured resume system
   - CV variants and exports

Boundary rule:
- reuse `JobSync` patterns and underpinnings where they improve shell, routing, CRUD, and automation UX
- do not move JobPipe connector, scoring, or stage-storage internals into JobSync
- do not turn JobPipe's current local dashboard shell into the long-term day-to-day operator workspace
- treat the current JobPipe shell as a control-plane and debug surface that can remain local-first even if the main operator shell moves elsewhere

Common-ground objects should be explicit and versioned:
- `ProfileSnapshot`
- `ResumeVariantRef`
- `CanonicalJob`
- `ApplicationCase`
- `ApplicationPacket`
- `ApplySession`
- `ArtifactRef`
- `StatusEvent`
- `OutcomeFeedback`

Source-of-truth rule:
- JobPipe owns pipeline/runtime truth
- JobSync owns active application-workflow truth
- Reactive Resume owns resume-structure truth

Authoring rule:
- JobPipe owns structured tailoring, case-scoped chat state, patch tracking, and saveback provenance
- Reactive Resume owns manual CV editing, analysis, and export
- Word / Docs-style tools own manual cover-letter editing and export
- the user should be able to chat with JobPipe on the same case while editing externally

---

## Architecture

```
NAV API (pam-stilling-feed)
    ↓ Apps Script (trigger-based, ~hourly, 50 jobs/run)
Google Sheet (JobFeed tab, ~35,850 rows × 59 cols)
    ↓ pull_sheets_csv.py
NAV connector output

Gmail recommendation emails
    ↓ scan_gmail --scan-suggestions
suggested_jobs.jsonl
    ↓ sync_mailbox_leads / pull_suggested
suggested-lead connector output

NAV connector output + suggested-lead connector output
    ↓ shared intake merge + dedupe
<data-root>/jobs_delta.jsonl
    ↓ run_feed.py / drain_queue.py
    ├─ [NAV]        Geo postal filter    → SKIP if outside 0xxx/1xxx/3xxx/4xxx
    ├─ [NAV]        Hard-no title regex  → SKIP on irrelevant titles
    ├─ [NAV]        Semantic pre-filter  → cosine similarity vs profile (multilingual-MiniLM)
    ├─ [SUGGESTED]  Hard-no title regex  → still applies to pre-vetted leads
    ├─ [NANO]       Triage               → SKIP / REVIEW / APPLY signal + noise_level score
    ├─ [MINI]       Parse                → structured job requirements
    ├─ [MINI]       Profile match        → fit_score 0-100 (4 dimensions: role/domain/seniority/skills)
    ├─ [MINI]       Pivot                → pivot_score 0-100
    ├─ [FREE]       Moderate             → final_decision (deterministic thresholds)
    └─ [DEEP]       Application pack     → deepagents + FilesystemBackend, only for APPLY / APPLY_STRONGLY
    # Reverse triage disabled — redundant given current triage accuracy. Re-enable in YAML if needed.
    ↓
<data-root>/out_runs/<run_id>/<job_id>/         per-job JSON artifacts
    ↓ sync_ledger.py
<data-root>/reports/ledger.sqlite               deduplicated, latest state per job
    ↓ export_dashboard.py
<data-root>/exports/dashboard.html              self-contained HTML, opens in browser
```

---

## File ownership

| Workstream | Owns |
|---|---|
| Pipeline chat | `jobpipe/stages/`, `jobpipe/core/`, `configs/`, `<data-root>/profile_pack.md` |
| Dashboard chat | `reports/dashboard_template.html`, `<data-root>/exports/dashboard.html`, `jobpipe/cli/export_dashboard.py`, `jobpipe/core/automation_state.py`, `jobpipe/cli/dashboard_server.py` |
| API import chat | Apps Script code, `jobpipe/cli/pull_sheets_csv.py` |
| Shared (all) | `jobpipe/cli/sync_ledger.py`, `AGENT_STATUS.md`, `AUDIT.md`, `PRODUCT_VISION.md`, `DASHBOARD_SPEC.md` |

**Do not modify another workstream's owned files without noting it in AGENT_STATUS.md.**

---

## Stage pipeline detail

### Per-job artifact layout

```
out_runs/<run_id>/<job_id>/
  00_input.json          normalized job snapshot (always written)
  01_triage.json         AI triage result
  02_reverse_triage.json only when triage=SKIP and NOT geo-skip or hard-no
  03_parsed.json
  04_profile_match.json
  05_pivot.json
  06_moderator.json
  07_application_pack.json  only for APPLY / APPLY_STRONGLY

out_runs/<run_id>/index.jsonl   run summary (one line per job)
```

### Stage factory interface

```python
def stage_factory(...) -> tuple[should_run_fn, run_fn]:
    def should_run(ctx: JobContext) -> bool: ...
    def run(ctx: JobContext, job_dir: Path) -> dict: ...
    return should_run, run
```

`run_feed.py` wraps these into `Stage(name, should_run, run, out_filename, ...)` objects.

### Decision tiers and thresholds (from `configs/pipeline.v1.yaml`)

| Threshold | Value | Meaning |
|---|---|---|
| `review_min_fit` | 30 | Hard floor — SKIP regardless of pivot score |
| `review_high_min_fit` | 58 | Separates REVIEW_LOW vs REVIEW_HIGH |
| `apply_fit` | 67 | Minimum for APPLY |
| `apply_strong_fit` | 78 | Minimum for APPLY_STRONGLY |
| `pivot_boost_apply` | 78 | Pivot score needed to boost a borderline job to APPLY |
| `reverse_triage_min_conf` | 0.60 | Confidence threshold to trigger reverse triage (disabled) |
| `semantic_filter_threshold` | 0.30 | Cosine similarity floor before LLM triage (multilingual-MiniLM) |

Final decisions: `SKIP`, `REVIEW_LOW`, `REVIEW_HIGH`, `APPLY`, `APPLY_STRONGLY`

---

## Hard rules — never break these

### 1. No LLM calls before hard filters
Geo and title filtering happen in `triage.py` **before** any LLM call. This is the primary cost control. Do not move these checks or add LLM calls before them.

Connector exception:
- mailbox/platform-suggested leads are already weakly pre-vetted by the source platform
- they may bypass `geo` and semantic pre-filter elimination
- they must still honor `hard_no_title_regex`
- this exception must be implemented explicitly by connector policy, not by silently weakening the broad `NAV` feed rules

### 2. Geo SKIPs must not enter reverse triage
In `reverse_triage.should_run()`, return `False` if `triage_signals` contains `geo_postal_skip` or `geo_skip`. Geo blocks are hard and personal — not subject to reconsideration.

### 3. Geo filter covers four postal code ranges
Allowed: `0xxx`, `1xxx`, `3xxx`, `4xxx` (Oslo, Akershus, Vestfold/Telemark, Agder).
Regex: `^([0134])(00[1-9]|0[1-9]\d|[1-9](0[1-9]|[1-9]\d))$`
Remote/hybrid override: `(?i)(remote|fjern|hjemmekontor|hybrid)` — checked against specific work-arrangement fields + first 300 chars of description ONLY. Not the full description (causes false passes from "hybrid culture" mentions).
If no postal code AND no county/municipal fallback matches → SKIP.

### 4. Connector merge happens before the main pipe
`NAV` feed intake and mailbox suggested-lead intake are separate connectors. They must merge and dedupe before the rest of the pipeline sees the jobs.

Canonical preference:
- treat `NAV` as the pragmatic canonical source when duplicate jobs collide across connectors
- keep alternate-source provenance for debugging and later UI use
- only prefer the suggested-lead variant over `NAV` when it is the only record with materially missing fields filled in
### 5. Moderate stage is deterministic — no LLM
`moderate.py` applies only the YAML thresholds. No OpenAI calls here. Final decisions must be reproducible from the moderator input alone.

### 6. Every stage writes a JSON artifact
Even for skipped stages, the decision must be traceable. If a stage errors, write an error payload rather than silently failing — or ensure the pipeline continues with that job marked as failed.

### 7. Output schema is additive
When modifying a stage, preserve existing output fields. Add new fields freely. Do not rename or remove fields without also updating `sync_ledger.py`, `export_dashboard.py`, and `DASHBOARD_SPEC.md`.

### 8. YAML has no duplicate keys
`configs/pipeline.v1.yaml` must not have duplicate top-level keys (Python's yaml loader silently drops them). Keep all regex patterns quoted. Keep the `stages:` list stable unless explicitly changing the pipeline.

---

## CLI commands (standard / Windows PowerShell)

### One-shot runner (recommended)
```powershell
.\go.ps1              # pull + process + sync + open dashboard
.\go.ps1 -DryRun      # 2 jobs only, no browser open (test mode)
.\go.ps1 -NoOpen      # full run, skip auto-opening browser
```
`go.ps1` always uses `.venv\Scripts\python.exe` — no system Python issues.
It now delegates the canonical scheduled flow to `python -m jobpipe.cli.run_scheduled_flow`, which also records companion preflight and feed-freshness state.

Local user state now lives under a stable JobPipe data root outside the repo:
- Windows: `~/JobpipeData`
- macOS: `~/Library/Application Support/JobPipe`
- Linux: `$XDG_DATA_HOME/jobpipe` or `~/.local/share/jobpipe`
- Override with `JOBPIPE_DATA_ROOT`

### Manual steps (advanced)
Always use `.venv\Scripts\python.exe` to ensure deepagents and all deps are available.

#### Pull delta from Sheet
```powershell
.venv\Scripts\python.exe -m jobpipe.cli.pull_sheets_csv --only-changed
```

#### Run pipeline (bounded)
```powershell
$env:OPENAI_AGENTS_DISABLE_TRACING="1"
.venv\Scripts\python.exe -m jobpipe.cli.run_feed --jobs $HOME\JobpipeData\jobs_delta.jsonl --max 100 --overwrite
```

#### Drain queue (pull + run until done)
```powershell
$env:OPENAI_AGENTS_DISABLE_TRACING="1"
.venv\Scripts\python.exe -m jobpipe.cli.drain_queue --batch-size 100 --overwrite
```

### Sync ledger + regenerate dashboard
```powershell
python -m jobpipe.cli.sync_ledger
python -m jobpipe.cli.export_dashboard
start $HOME\JobpipeData\exports\dashboard.html
```

### Mark application status (manual)
```powershell
python -m jobpipe.cli.mark_status JOB_ID shortlisted        # reviewed, intend to apply
python -m jobpipe.cli.mark_status JOB_ID applied            # application submitted
python -m jobpipe.cli.mark_status JOB_ID interview          # interview received
python -m jobpipe.cli.mark_status JOB_ID rejected --notes "Form letter"
python -m jobpipe.cli.mark_status JOB_ID dismissed          # decided not to apply
python -m jobpipe.cli.mark_status --list                    # show all tracked
python -m jobpipe.cli.mark_status --list --filter-status applied
```

### Scan Gmail for application emails (auto-detect)
```powershell
# First-time setup (one-time OAuth consent):
python -m jobpipe.cli.scan_gmail --setup

# Regular use:
python -m jobpipe.cli.scan_gmail --dry-run        # preview matches, no writes
python -m jobpipe.cli.scan_gmail                  # scan last 90 days, write updates
python -m jobpipe.cli.scan_gmail --days 30 -v     # verbose, last 30 days
```
Gmail credentials: `<data-root>/reports/gmail_credentials.json` (download from Google Cloud Console)
Gmail token: `<data-root>/reports/gmail_token.json` (auto-created after --setup)
Never overwrites manual entries. Only upgrades status (applied → interview → rejected).

### Intake Gmail recommendation leads (separate from status updates)
```powershell
python -m jobpipe.cli.sync_mailbox_leads --dry-run
python -m jobpipe.cli.sync_mailbox_leads
```
Rule:
- mailbox recommendation leads must stage as lead-connector input, then merge into the shared pre-triage `jobs_delta.jsonl` queue before filters and triage
- Gmail-derived status updates stay in `application_state.json` and do not create new leads

### Compile check (run before every commit)
```powershell
.venv\Scripts\python.exe compile_check.py
```

### Companion revision drift check
```powershell
.venv\Scripts\python.exe -m jobpipe.cli.check_companion_revisions --strict
```
Use this before stack-level validation when the current JobPipe checkpoint depends on sibling repos.

### Scheduled flow
```powershell
.venv\Scripts\python.exe -m jobpipe.cli.run_scheduled_flow --max-jobs 1
.\go.ps1 -DryRun
```
`run_scheduled_flow` is the canonical operator path under Topic 28.
It writes `<data-root>/reports/scheduled_run_state.json` and blocks on sibling drift unless explicitly overridden.

### Test with small batch first
```powershell
.\go.ps1 -DryRun
```
Always test with `-DryRun` (2 jobs) before a full run.

---

## Working conventions

### Making changes
1. Read AGENT_STATUS.md + AUDIT.md + PRODUCT_VISION.md first.
2. Check file ownership — confirm you're not stepping on another workstream.
3. Make small, focused changes. Preserve output schemas.
4. Run compile check after every change.
5. Test with `--max 2` before `--max 100`.
6. Update your section in AGENT_STATUS.md and AUDIT.md.

### When proposing code changes
- Provide exact file paths
- Provide complete function blocks (copy/paste safe)
- Explain how to test with a single command
- Note any schema changes that affect downstream consumers (ledger, dashboard)

### Ledger and deduplication
`ledger.sqlite` has two tables:
- `ledger` — latest state per `job_id` (upserted on each sync)
- `events` — run history (one row per job per run)

`drain_queue.py` skips jobs already in the ledger by default. Use `--ledger-sqlite <data-root>\reports\ledger.sqlite` to specify a non-default path.

### Data freshness
Pipeline runs are currently manual. After each run:
1. `sync_ledger` to update `ledger.sqlite`
2. `export_dashboard` to rebuild `dashboard.html`
3. Check AGENT_STATUS.md for any cross-workstream requests that this run's data might unblock.

---

## Key data files

| File | Purpose |
|---|---|
| `configs/pipeline.v1.yaml` | Pipeline config — models, stages, thresholds, regex |
| `<data-root>/profile_pack.md` | Candidate profile — truth source for triage and matching |
| `<data-root>/reports/nav_connector.jsonl` | Staged broad-feed intake from the NAV Sheet/API connector |
| `<data-root>/reports/leads_connector.jsonl` | Staged lead-style intake from mailbox suggestions, search, and manual capture connectors |
| `<data-root>/jobs_delta.jsonl` | Shared merged pre-triage queue rebuilt from connector staging before pipeline processing |
| `<data-root>/jobs_state.json` | Change tracking state for delta pull |
| `<data-root>/reports/ledger.sqlite` | Deduplicated job ledger (tables: `ledger`, `events`) |
| `<data-root>/reports/ledger_latest.csv` | CSV export of ledger for quick inspection |
| `reports/dashboard_template.html` | Dashboard HTML template (use `/*__DASHBOARD_DATA__*/` placeholder) |
| `<data-root>/exports/dashboard.html` | Built dashboard — self-contained, embeds data inline |
| `<data-root>/reports/application_state.json` | Application tracking sidecar — manual + Gmail-detected statuses |
| `<data-root>/reports/gmail_credentials.json` | Gmail OAuth2 client credentials (download from Google Cloud Console) |
| `<data-root>/reports/gmail_token.json` | Gmail OAuth2 token — auto-created by `scan_gmail --setup` |

---

## Current known issues (see AUDIT.md for full list)

- Geo classification in the dashboard may miscount — some jobs flagged as "geo-blocked" are actually moderator SKIPs at fit<30 with missing stage files. Needs explicit `skip_reason` signal.
- `triage_signals` empty for some older ledger jobs — sync_ledger didn't read `01_triage.json` during those runs.
- `scan_gmail.py` requires Gmail API credentials setup before first use — see CLI commands above.
- Semantic filter multilingual model (paraphrase-multilingual-MiniLM-L12-v2) still needs calibration follow-up — threshold is currently 0.30 after verified false negatives at 0.45. Recheck `sim:X.XX` tags in `01_triage.json` after a fresh 50+ job sample and only raise it if known-good jobs still survive.
- `go.ps1 --dry-run` (double-dash) is silently ignored by PowerShell — use `.\go.ps1 -DryRun` instead.

---

## Code Intelligence

Three tools are available. Full reference in `docs/agent-codebase-tools.md`.

### `codebase-index` (MCP) -- structural navigation (Python)
Use for symbol lookup, dependency graphs, and change-impact analysis without reading files.

    find_symbol("JobStage")                  # where is this defined?
    get_change_impact("run_pipeline")        # what breaks if I change this?
    get_function_source("JobStage.execute")  # source without reading the file
    search_codebase("connector")             # regex search across repo

Run `reindex` if results seem stale. Cache: `.codebase-index-cache.pkl` (gitignored).

### `codegraphcontext` (MCP) -- graph-based navigation (Python)
Use for multi-hop call chains and cross-file relationship graphs.
Pre-indexed. Re-index with: `cgc index .`  Index: `.axon/` (gitignored).

### repomix -- context packing (all languages)
Use to pack a module into context when you need full file content.
Always use a named profile. Never run bare.

    repomix --profile core      # stages, runtime, model, decision
    repomix --profile crewai    # CrewAI crews and orchestration
    repomix --profile cli       # CLI, connectors, integrations
    repomix --profile tests     # test suite
    repomix --profile docs      # documentation