# Stage 1 Handoff — Opus → Sonnet Orchestrator (2026-04-24)

**Purpose:** hand off the JobPipe staged-NAV-ingest coordination session
from the Opus orchestrator to a fresh Sonnet orchestrator. Everything
up to and including Stage 1 pre-flight has been executed. The Sonnet
orchestrator's job is to (1) confirm pre-flight completed cleanly,
(2) run Stage 1 (`.\go.ps1 --max-jobs 100` or equivalent), and
(3) fill in the Stage 1 calibration entry in
`docs/execplans/staged-ingest-2026-04-24.md`.

Keep it tight. Do not re-plan the staged ingest. The execplan is the
source of truth; this is only the session bridge.

---

## 1. Session-start — read these in order

1. `CLAUDE.md` (orchestrator role)
2. `docs/ai-playbook.md` (workflow rules)
3. `docs/current-state.json` (live state — `current_slice` should be
   `stage_1_100_jobs`; ingest_prep_track.status should be
   `stage_1_ready`)
4. **`docs/execplans/staged-ingest-2026-04-24.md`** — canonical Stage 1
   plan. Read the "Pre-flight", "Stages → Stage 1", and
   "Recalibration loop" sections.
5. `docs/orchestrator-git-workflow.md` — sandbox-vs-Windows git rules
   (reads via PowerShell/Desktop Commander, writes handed to Lars).
6. This file.

Then run the `jobpipe-orchestrator` skill's session-start procedure to
get a current-state snapshot.

---

## 2. What is already done

Committed + pushed to `ops/orchestrator-v2` by the Opus session:

- `a8add21` — `profile: add profile/ folder contract + stitched loader`
  (paths.py, candidate_data.py, import_reactive_resume.py, .gitignore,
  profile/README.md, 3 .example templates)
- `97fa786` — `docs: staged NAV ingest plan, git workflow doc,
  current-state update` (staged-ingest execplan, orchestrator git
  workflow doc, jobsync-purge-prep execplan, current-state.json)

Project #6 items created:

- `PVTI_lAHOCSFbLc4BJUdazgq0w8c` — Staged NAV ingest - calibration log
  (2026-04-24)
- `PVTI_lAHOCSFbLc4BJUdazgq0xKI` — JobSync purge research - parked

Pre-flight executed:

1. `jobpipe reset-runtime --tag pre_staged_ingest_20260424` — archived
   4 paths (baseline reset).
2. `jobpipe reset-runtime --tag pre_staged_ingest_20260424_v2` — second
   archive after env fix (see §3).
3. `jobpipe import-reactive-resume` (no positional arg, new default
   path) — imported `profile\resume.json`,
   `profile_version_id: profile_c572d8ceaa88`.
4. `jobpipe pull-sheets --sheet-url $env:JOBPIPE_CSV_URL` — **completed
   cleanly** (ran detached; both wrapper PID 27728 and child PID 10612
   exited). Final log tail (in `.\pull_sheets_run.log`):
   ```
   Status filter: ACTIVE - skipped 25798 rows
   Deadline filter: on - skipped 4050 rows with past deadlines
   Read rows: 11493 (dedupe=on)
   Wrote 11493 rows to C:\Users\larsv\JobpipeData\db\jobs_delta.jsonl
   Mirrored canonical jobs: 11493 -> C:\Users\larsv\JobpipeData\db\jobpipe.sqlite
   Expired events: 777 (ACTIVE->INACTIVE transitions)
   ```
   **Queue: 11,493 active jobs.** Much bigger than the earlier guess
   (1k–2.5k) — update your mental model: the NAV feed is fat. Stage 1
   `--max-jobs 100` still processes exactly 100, so this doesn't change
   the plan, but cost/time extrapolations to "full ingest" must be
   based on 11.5k, not 2.5k.

---

## 3. Environmental notes — important, do not skip

### 3.1 Run cwd + venv

- **cwd:** `C:\Users\larsv\Jobpipe-orchestrator-v2`
- **python/jobpipe:** `C:\Users\larsv\Jobpipe\.venv\Scripts\python.exe`
  (or `jobpipe.exe`)
- **.env:** Lars's `.env` lives at `C:\Users\larsv\Jobpipe\.env`. The
  orchestrator worktree has no `.env` file. Source it into the current
  PS session before running anything:

```powershell
foreach ($raw in Get-Content C:\Users\larsv\Jobpipe\.env) {
    $line = $raw.Trim()
    if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) { continue }
    $parts = $line.Split("=", 2)
    $key = $parts[0].Trim()
    $value = $parts[1].Trim().Trim('"').Trim("'")
    [Environment]::SetEnvironmentVariable($key, $value, "Process")
}
```

### 3.2 Editable install — points at orchestrator-v2 now

The venv at `C:\Users\larsv\Jobpipe\.venv` had its editable install
remapped this session. Verify:

```powershell
C:\Users\larsv\Jobpipe\.venv\Scripts\python.exe -c "import __editable___jobpipe_0_1_0_finder as f; print(f.MAPPING)"
# expected: {'jobpipe': 'C:\\Users\\larsv\\Jobpipe-orchestrator-v2\\jobpipe'}
```

If the map shows `C:\\Users\\larsv\\Jobpipe\\jobpipe` instead, the map
is stale — flip it:

```powershell
C:\Users\larsv\Jobpipe\.venv\Scripts\python.exe -m pip install -e C:\Users\larsv\Jobpipe-orchestrator-v2 --no-deps --quiet
```

### 3.3 cwd gotcha

When cwd is `C:\Users\larsv\Jobpipe`, Python's cwd-first sys.path
lookup finds the stale `Jobpipe\jobpipe\` subdirectory before the
editable finder resolves. Always run from
`C:\Users\larsv\Jobpipe-orchestrator-v2` (or a neutral parent).

### 3.4 Git on Windows only

Do NOT try `git status` from the Linux sandbox via Bash. It fails
because `.git` points at a Windows-native path. Use
`mcp__Desktop_Commander__start_process` → PowerShell for all git
reads. Writes (commit, push) go to Lars as command blocks per
`docs/orchestrator-git-workflow.md`.

### 3.5 Sub-shell fragility

PowerShell sessions spawned via Desktop Commander can drop if a long
command exceeds the 60s MCP-level timeout (even when Desktop Commander
itself permits longer). For long pipeline runs, launch via
`Start-Process` with `-RedirectStandardOutput` + `-NoNewWindow`
detached, then poll the log file. Example:

```powershell
$p = Start-Process -FilePath "C:\Users\larsv\Jobpipe\.venv\Scripts\python.exe" `
    -ArgumentList @("-m","jobpipe.cli.pull_sheets_csv","--sheet-url",$env:JOBPIPE_CSV_URL) `
    -RedirectStandardOutput .\pull_sheets_run.log `
    -RedirectStandardError .\pull_sheets_run.err `
    -WorkingDirectory (Get-Location) -PassThru -NoNewWindow
Write-Host "PID: $($p.Id)"
```

Then poll with:

```powershell
Get-Process -Id <PID> -ErrorAction SilentlyContinue
Get-Content .\pull_sheets_run.log -Tail 10
```

If the process is gone, check the log + err for completion.

---

## 4. Pick up here

### 4.1 Confirm pull-sheets completed

Already done by the Opus session — final queue size **11,493**.
Re-verify if anything feels stale:

```powershell
cd C:\Users\larsv\Jobpipe-orchestrator-v2
Get-ChildItem C:\Users\larsv\JobpipeData\db\jobs_delta.jsonl |
    Select-Object Length, LastWriteTime
(Get-Content C:\Users\larsv\JobpipeData\db\jobs_delta.jsonl |
    Measure-Object -Line).Lines
```

Note: the file lives under `$env:JOBPIPE_DATA_DIR\db\jobs_delta.jsonl`
(not the cwd) because `JOBPIPE_DATA_DIR` is set.

### 4.2 Decision point — go/no-go for Stage 1

Before pressing go, confirm:

- ✅ `jobs_delta.jsonl` has ~11,493 lines (confirmed)
- ✅ `JOBPIPE_DATA_DIR = C:\Users\larsv\JobpipeData` in env
- ✅ `OPENAI_API_KEY` set
- ✅ editable install map points at orchestrator-v2
- ✅ cwd is `C:\Users\larsv\Jobpipe-orchestrator-v2`

Ask Lars for the go before running — Stage 1 is ~500 LLM calls and
real money. Do not just fire.

### 4.3 Run Stage 1

```powershell
# from C:\Users\larsv\Jobpipe-orchestrator-v2, env sourced:
C:\Users\larsv\Jobpipe\.venv\Scripts\jobpipe.exe run --max-jobs 100
# or if go.ps1 expects .venv in cwd and you prefer the wrapper, run
# from C:\Users\larsv\Jobpipe: cd C:\Users\larsv\Jobpipe; .\go.ps1
# — but then the module resolution gotcha in §3.3 applies, so run the
# jobpipe CLI directly from orchestrator cwd.
```

Monitor via log. Expected runtime ~15–25 min at gpt-4.1-mini.

### 4.4 Fill in the Stage 1 calibration entry

In `docs/execplans/staged-ingest-2026-04-24.md`, under
"Stage 1 calibration entry", fill:

- Run timestamp
- Queue before / after
- Decision breakdown: SKIP_TRIAGE=_, SKIP_MATCH=_, REVIEW_LOW=_, REVIEW_HIGH=_, APPLY=_
- Spot-check findings (10 KEEPs + 10 SKIPs from `reports/index.jsonl`)
- Knob change(s) applied (if any; see the symptom→knob table in the
  execplan)
- Rationale (2 sentences)
- Commit SHA (if knob change committed)

Do NOT proceed to Stage 2 until Lars has signed off on the Stage 1
results.

### 4.5 Commit the calibration entry

Prepare this block for Lars to paste on Windows:

```powershell
cd C:\Users\larsv\Jobpipe-orchestrator-v2
git status --short
# expect only: M docs/execplans/staged-ingest-2026-04-24.md
# (and any knob-change file if applied)

git add docs/execplans/staged-ingest-2026-04-24.md <maybe configs/pipeline.v1.yaml>
git commit -m "ingest: Stage 1 calibration entry + <knob if any>

<2-3 sentence why>

Refs: docs/execplans/staged-ingest-2026-04-24.md"
git push origin ops/orchestrator-v2
```

Per `docs/orchestrator-git-workflow.md`, the orchestrator does NOT run
the commit — it prepares the block and hands it to Lars.

---

## 5. What NOT to do

- Do **not** run Stage 2 or Stage 3. Each stage waits on Lars's sign-off.
- Do **not** touch the JobSync purge — deferred per
  `docs/execplans/jobsync-purge-prep.md` §3 decision.
- Do **not** stage `profile/` blanket-style. Always use explicit paths.
  Personal files are gitignored but `git add profile/` would attempt
  to stage `.example` + `README.md` only, which is fine — but if you
  ever need to add new personal files to the gitignore, extend the
  "Personal profile folder" block in `.gitignore` first.
- Do **not** amend commits that are already pushed.
- Do **not** run `git add -A` or `git add .` — stage explicit paths.
- Do **not** flip the editable install back to Jobpipe/ without asking
  Lars.

---

## 6. Escalation gates (CLAUDE.md short-list)

Stop and ask Lars before any of:

- DB schema migration
- Auth, billing, deployment, secrets
- Destructive git ops on main
- JobSync sync (deferred purge means this is not safe to run after
  ingest without confirming disposition first)
- Running Stage 2/3/full without Stage 1 results reviewed

---

## 7. Decisions worth knowing about

From `docs/current-state.json → recent_decisions[decided_at=2026-04-24]`:

- **JobSync purge deferred** — research owed per
  `docs/execplans/jobsync-purge-prep.md` §3, but no longer blocks
  intake. Reconfirm before the first JobSync sync after this ingest.
- **Profile folder contract** — canonical input. `profile/` mirrors
  CrewAI Job Hunter Crew layout. `constraints.md` and `motivation.md`
  get stitched onto `profile_pack.md` at load time (idempotent via
  `<!-- PROFILE_SIBLINGS_APPLIED -->` marker).

---

## 8. Open risks / known gaps

- The execplan Precondition 3 ("Intake path confirmed") says "no
  direct NAV API integration in code". Confirmed — `NAV_*` env vars in
  `.env.example` are aspirational. Stage 1 runs through
  Google-Sheet-mirror only.
- The orchestrator worktree has no `.env` and no `.venv`. All runs
  rely on Jobpipe/'s venv + Jobpipe/'s .env (sourced into process). If
  Lars switches machines or recreates the venv, the editable map will
  need to be flipped again per §3.2.
- `profile/cover_letter_voice.md` is gitignored but has no `.example`
  template. When onboarding a new candidate, we'd need to create a
  voice reference from scratch. Flag for a future slice if generic
  voice guidance is useful to ship.

---

## 9. Quick verification (run this first)

```powershell
cd C:\Users\larsv\Jobpipe-orchestrator-v2
# env
foreach ($raw in Get-Content C:\Users\larsv\Jobpipe\.env) { $line=$raw.Trim(); if(-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")){continue}; $parts=$line.Split("=",2); [Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim().Trim('"').Trim("'"), "Process") }
# editable map
C:\Users\larsv\Jobpipe\.venv\Scripts\python.exe -c "import __editable___jobpipe_0_1_0_finder as f; import json; print(json.dumps(f.MAPPING))"
# sanity
C:\Users\larsv\Jobpipe\.venv\Scripts\python.exe -c "from jobpipe.runtime.paths import profile_dir, profile_pack_path, resume_json_path; print('dir:', profile_dir()); print('pack exists:', profile_pack_path().exists()); print('resume exists:', resume_json_path().exists())"
# git
git -C C:\Users\larsv\Jobpipe-orchestrator-v2 status --short
git -C C:\Users\larsv\Jobpipe-orchestrator-v2 branch --show-current
git -C C:\Users\larsv\Jobpipe-orchestrator-v2 log --oneline -5
# queue size (pull-sheets already completed; just confirm file is there)
(Get-Content C:\Users\larsv\JobpipeData\db\jobs_delta.jsonl | Measure-Object -Line).Lines
```

If everything above is green, proceed to §4.2 (§4.1 is already done —
queue is 11,493).
