# Full re-evaluation runbook

Use this when you want to wipe all jobs + evaluation state and re-evaluate the entire active sheet from scratch. The pipe ends up with: every ACTIVE job whose `applicationDue` is in the future, freshly evaluated against the current decision-tier configuration.

This is the heaviest operation the pipeline supports. Time budget at ~5-15s/job: roughly 16-48 hours for ~11,000 jobs. Run it overnight or over a weekend.

## Prerequisites

- `JOBPIPE_DATA_DIR` set in `.env` (canonical: `C:\Users\larsv\JobpipeData`)
- `JOBPIPE_CSV_URL` set in `.env` (the published Google Sheet CSV)
- Schema fix `f761678` (env preload before fast-path dispatch) merged
- No drain currently running. Verify:
  ```powershell
  Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.Path -match 'Jobpipe' }
  ```

## What gets archived vs. preserved

`reset-runtime` **archives** (moves into `JobpipeData\_archives\<tag>\`):
- `db/` (entire SQLite DB — jobs, source_records, evaluations, **candidates, candidate_profiles, candidate_feedback_events, calibration**, watchlists, audit tables)
- `.jobpipe_tmp/`, `artifacts/`, `cache/`, `exports/`, `out_runs/`, `reports/`
- `jobs_delta.jsonl`, `jobs_expired.jsonl`, `jobs_state.json`
- `profile_embedding.npy`, `suggested_jobs.jsonl`

**Preserved** (untouched):
- `candidate_inputs/profile_pack.md` (profile lives on the filesystem, not in the DB)
- `secrets/`
- Anything outside the archive list

**Restored automatically** into the fresh baseline (default behavior):
- `db/application_state.json` (job mark-status / applied state)

**Recoverable from archive** (will need manual restore if you want them back):
- Feedback rows in `candidate_feedback_events`
- Calibration overrides in `candidate_calibration_settings`
- Default Candidate row (auto-recreated on next run, but with fresh ID)

## Commands

Run from `C:\Users\larsv\Jobpipe` in PowerShell.

### 1. Pre-flight cleanup (worktree-root duplicates from pre-fix dual-DB era)

```powershell
Remove-Item C:\Users\larsv\Jobpipe\jobs_state.json, C:\Users\larsv\Jobpipe\jobs_delta.jsonl -Force -ErrorAction SilentlyContinue
Remove-Item C:\Users\larsv\Jobpipe\reports\jobpipe.sqlite -Force -ErrorAction SilentlyContinue
```

### 2. Archive runtime + create fresh baseline

```powershell
cd C:\Users\larsv\Jobpipe
.venv\Scripts\python.exe -m jobpipe.cli.main reset-runtime --tag pre_full_revaluation_$(Get-Date -Format yyyyMMdd)
```

Verify the archive landed:
```powershell
Get-ChildItem C:\Users\larsv\JobpipeData\_archives\pre_full_revaluation_$(Get-Date -Format yyyyMMdd) -Recurse | Measure-Object -Property Length -Sum
```

### 3. Run the full drain (no cap)

```powershell
.venv\Scripts\python.exe -m jobpipe.cli.main drain-queue --candidate-id default `
  *>&1 | Tee-Object -FilePath drain_full_revaluation_$(Get-Date -Format yyyyMMdd_HHmm).log
```

`drain-queue` internally calls `pull-sheets` → batch process → `sync-evaluations`. No need to call them separately. Defaults:
- `--max-jobs 0` (unlimited)
- `--max-loops 200` (safety cap; one loop = one batch = 50 jobs by default, so 200 loops = 10,000 jobs — bump to `--max-loops 500` for full sheet)
- `--batch-size 50`
- `--skip-processed` ON (irrelevant on a fresh DB; keep default)
- `--status-filter ACTIVE` (the only ACTIVE jobs from the sheet enter)
- `--skip-expired-deadline` ON (drops jobs with past `applicationDue`)

For a guaranteed full run on ~11k jobs:
```powershell
.venv\Scripts\python.exe -m jobpipe.cli.main drain-queue --candidate-id default --max-loops 500 `
  *>&1 | Tee-Object -FilePath drain_full_revaluation_$(Get-Date -Format yyyyMMdd_HHmm).log
```

### 4. Verify result

```powershell
.venv\Scripts\python.exe -m jobpipe.cli.main inspect-db --show summary
```

Expect: `jobs ≈ 11,000`, `source_records ≈ 11,000-11,500`, `evaluations ≈ jobs` (one per processed job), `candidates = 1`, `feedback = 0` (was archived), `pipeline_runs > 0`.

## Variants

**Re-evaluate without wiping the DB** (keeps feedback + history, reprocesses every existing job):
```powershell
.venv\Scripts\python.exe -m jobpipe.cli.main drain-queue --candidate-id default `
  --reset-state --no-skip-processed --max-loops 500
```

**Capped re-eval (test slice of N jobs)**:
```powershell
.venv\Scripts\python.exe -m jobpipe.cli.main drain-queue --candidate-id default --max-jobs 400
```

## Recovery

If the drain crashes mid-run, the partial DB at `JobpipeData\db\jobpipe.sqlite` is intact and can be resumed:
```powershell
.venv\Scripts\python.exe -m jobpipe.cli.main drain-queue --candidate-id default --max-loops 500
```
Default `--skip-processed` ON will skip jobs already evaluated and continue from where it stopped.

If you need to roll back entirely, pull the archive back:
```powershell
$tag = "pre_full_revaluation_<your-date>"
$src = "C:\Users\larsv\JobpipeData\_archives\$tag"
$dst = "C:\Users\larsv\JobpipeData"
# Copy db/, jobs_state.json, jobs_delta.jsonl back, overwriting the fresh baseline
Copy-Item "$src\db\*" "$dst\db\" -Recurse -Force
Copy-Item "$src\jobs_state.json" "$dst\" -Force -ErrorAction SilentlyContinue
Copy-Item "$src\jobs_delta.jsonl" "$dst\" -Force -ErrorAction SilentlyContinue
```

## Risks / gotchas

- **Time**: 11k jobs × ~5-15s = 16-48 h. Run on a machine that can stay awake. Consider `powercfg /requestsoverride PROCESS python.exe SYSTEM` if needed.
- **API cost**: every job runs the LLM stack (triage → match → moderator → optional pack). Estimate cost from your provider's tier before launching.
- **Feedback loss**: 4 (current) feedback rows are archived, not restored. If they were valuable for calibration, restore them manually from `_archives/<tag>/db/jobpipe.sqlite` after the drain completes.
- **Calibration drift**: a fresh run uses whatever `decision_tiers.yaml` / `semantic_filter_threshold` is currently set. If you tuned these mid-stage previously, the full re-eval is the new baseline going forward.

## Related docs

- `docs/calibration-notes.md` — tier thresholds + post-stage tuning history
- `docs/public-loop-test-howto.md` — smaller staged re-validation pattern
- `docs/cli.md` — full CLI reference
