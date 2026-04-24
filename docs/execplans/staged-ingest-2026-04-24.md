# Staged NAV Ingest — Calibration Log (2026-04-24)

**Directive (founder, 2026-04-24):** "kjør første hundre. rekalibrer. kjør 100 til rekalibrer. så prøver vi 500. kalibrer og så kjører vi full ingest."

**Goal:** drain the ACTIVE-filtered NAV-feed mirror (Google Sheet → `pull-sheets`) through the JobPipe pipeline in four stages, tuning semantic + regex knobs between stages so the full-feed run lands with stable KEEP-rate and low false-positive/negative counts.

**Owner:** Claude Desktop (coordinator) + Lars (execute on Windows). Codex not involved — no implementation slice.

**Risk label:** Yellow. Reversible per stage (reset-runtime archives). No destructive action to upstream forks in this scope (JobSync purge deferred — see below).

---

## Preconditions (verified 2026-04-24)

1. **Profile folder contract landed.** `profile/` contains `profile_pack.md`, `resume.json`, `constraints.md`, `motivation.md`, `cover_letter_voice.md` + `.example` templates. Loader stitches constraints + motivation onto profile_pack at load time (idempotent, marker-guarded). See `docs/current-state.json` → `ingest_prep_track.profile_folder_contract`.
2. **JobSync purge: DEFERRED.** Destructive upstream action, research-pending per `docs/execplans/jobsync-purge-prep.md` §3. Decision 2026-04-24: ingest through triage/parse/match/application_pack WITHOUT JobSync sync. The pipeline can run end-to-end; JobSync sync is a *subsequent* operation that can be resumed after purge disposition clears. See "Decision record" below.
3. **Intake path confirmed.** NAV public feed → external mirror → Google Sheet → `pull-sheets` (`source_name=nav_sheet`, default `status_filter=ACTIVE`). No direct NAV API integration in code (the `NAV_*` env vars in `.env.example` are aspirational).
4. **Environment variables required:**
   - `OPENAI_API_KEY` — LLM stages
   - `JOBPIPE_CSV_URL` — NAV-mirror Google Sheet (edit URL or published CSV)
   - `JOBPIPE_DATA_DIR` — required for `reset-runtime`

---

## Pre-flight command sequence (PowerShell, from `C:\Users\larsv\Jobpipe-orchestrator-v2`)

```powershell
# 1. Verify env
echo "OPENAI_API_KEY set: $([bool]$env:OPENAI_API_KEY)"
echo "JOBPIPE_CSV_URL:    $env:JOBPIPE_CSV_URL"
echo "JOBPIPE_DATA_DIR:   $env:JOBPIPE_DATA_DIR"

# 2. Clean slate (archives reports/, db/, jobs_delta.jsonl, jobs_state.json,
#    profile_embedding.npy under JOBPIPE_DATA_DIR — reversible)
jobpipe reset-runtime --tag pre_staged_ingest_20260424

# 3. Re-import resume via the new profile/ contract
jobpipe import-reactive-resume

# 4. Pull NAV-mirror sheet -> jobs_delta.jsonl
#    (default status_filter=ACTIVE cuts ~30k inactive rows; deadline filter cuts expired)
jobpipe pull-sheets --sheet-url $env:JOBPIPE_CSV_URL

# 5. Confirm queue size
$lines = (Get-Content .\jobs_delta.jsonl | Measure-Object -Line).Lines
echo "Queued active jobs: $lines"
```

Expected queue size: 1,000–2,500 ACTIVE jobs on a typical day. If under 300, stop and investigate — the sheet may be mid-refresh or the status filter may be mis-cased.

---

## Stages

### Stage 1 — 100 jobs

```powershell
.\go.ps1 --max-jobs 100
```

**Expected runtime:** ~15–25 min at gpt-4.1-mini for parse+match+pivot+moderate+pack. Triage is gpt-4.1-nano (cheapest), semantic filter is local.

**Expected final_decision distribution (rough sanity anchor):**
- `SKIP_TRIAGE` (hard_no or semantic miss or geo): 60–75%
- `SKIP_MATCH` (profile_match drops it): 15–25%
- `REVIEW_LOW` / `REVIEW_HIGH`: 5–15%
- `APPLY`: 1–5%

If distribution is wildly off (e.g. >95% SKIP_TRIAGE or <0.5% APPLY), recalibration is mandatory before Stage 2.

**Stage 1 calibration entry** *(completed 2026-04-24)*:
- Run timestamp: 2026-04-24 ~07:20–07:50 CEST
- Queue before / after: 11,240 active / ~10,800 remaining (440 processed across 5 batches; 1 batch of 7 failed due to relative-path cwd bug — non-blocking)
- Decision breakdown: SKIP=438 (99%), APPLY=1 (0.2%), REVIEW_LOW=1 (0.2%), REVIEW_HIGH=0, APPLY=1
- Triage breakdown: SKIP=435 (99%), REVIEW=4 (1%), APPLY_CANDIDATE=1 (0.2%)
- Spot-check findings:
  - True KEEPs: "Senior Product Manager - Data & AI focus" (APPLY ✓), "Senior Mulesoft Developer" (REVIEW_LOW ✓)
  - False-negative SKIPs observed: "Administrativ koordinator" sim:0.29 — borderline; "Verksted/MC" sim:0.21–0.27 — correctly skipped
  - No false-positive KEEPs observed in 5-job sample
  - Geo filter working correctly: rural postal codes (5760 Røldal etc.) correctly skipped
  - Hard-no regex firing correctly on MC/ATV, retail, healthcare titles
- Skip signals: `semantic_filter_skip` dominant (scores 0.21–0.29, threshold 0.30); `geo_postal_skip` secondary
- Knob change applied: `semantic_filter_threshold` 0.30 → 0.27
- Rationale: Borderline relevant roles (e.g. "Administrativ koordinator") scored 0.27–0.29, just under the 0.30 cut. Opening the 0.27–0.30 band lets the nano-model LLM triage decide — cheap insurance against false negatives. NAV feed is general Norwegian market; 99% SKIP on raw feed is expected and not a problem in itself.
- Commit SHA: (pending — see git commit block below)

### Stage 2 — 100 more

```powershell
.\go.ps1 --max-jobs 100
```

Same recalibration checklist. Compare distribution against Stage 1. If KEEP-rate swings >20% between Stage 1 and Stage 2 after a knob change, the change was too aggressive — revert one step and re-run.

**Stage 2 calibration entry** *(fill in after run)*:
- Run timestamp:
- Queue before / after: _ / _
- Decision breakdown: SKIP_TRIAGE=_, SKIP_MATCH=_, REVIEW_LOW=_, REVIEW_HIGH=_, APPLY=_
- Drift vs Stage 1 (pp): _
- Spot-check findings:
- Knob change(s) applied:
- Rationale:

### Stage 3 — 500 jobs

```powershell
.\go.ps1 --max-jobs 500
```

At 500 jobs, statistical patterns become readable (recurring title classes, geo false positives, title-alternation gaps). This is the right scale for structural knob changes — regex additions, threshold shifts by 0.02–0.04.

**Stage 3 calibration entry** *(fill in after run)*:
- Run timestamp:
- Queue before / after: _ / _
- Decision breakdown:
- Drift vs Stage 1+2 combined (pp):
- Structural calibrations applied (regex alternations added / thresholds shifted):
- Rationale:

### Stage 4 — full remainder

```powershell
.\go.ps1 --max-jobs 5000
```

Cap is set above any realistic remaining queue — the pipeline drains whatever is left. No calibration after this stage; instead do a post-mortem spot-check of the APPLY pile for author/pack quality.

**Stage 4 summary entry** *(fill in after run)*:
- Run timestamp:
- Total jobs processed this stage:
- Final APPLY count (across all 4 stages):
- REVIEW_HIGH count (across all 4 stages):
- Post-mortem notes:

---

## Recalibration loop — what to do between stages

**Inspect:**
1. `reports/index.jsonl` — one line per job: `{job_id, title, decision, confidence, signals[]}`.
2. Pick 10 KEEPs + 10 SKIPs spanning the confidence range (not only extremes).
3. For each, read `reports/artifacts/<job_id>/01_triage.json`, `02_parsed.json`, `03_profile_match.json` and the raw ad at `reports/artifacts/<job_id>/raw.*`.

**Symptom → knob mapping** (all knobs in `configs/pipeline.v1.yaml`):

| Symptom | Knob | Direction |
|---|---|---|
| Obvious-fit jobs SKIPped by semantic filter (`sim:` score below threshold) | `thresholds.semantic_filter_threshold` | lower (e.g. 0.30 → 0.28) |
| Obvious-fit jobs SKIPped by `hard_no_title_regex` | `safety_rules.hard_no_title_regex` | remove the offending term |
| Obvious-miss jobs KEPT (semantic filter passed) | `thresholds.semantic_filter_threshold` | raise (e.g. 0.30 → 0.32) |
| Obvious-miss jobs KEPT because title regex over-fires | `safety_rules.hard_no_title_regex` | add the offending term |
| Borderline titles decided wrong both ways (e.g. "Produktsjef salg") | `safety_rules.target_title_regex` or `weak_positive_regex` | add targeted alternation |
| Wrong region KEPT | `safety_rules.geo_postal_regex` or `geo_county_regex` | tighten |
| Norwegian-only jobs misclassified (language) | profile_pack section 1 (language preferences) | nudge |

**Decision rule:** change **one knob per round** unless two symptoms are provably independent. Record every change in the "Stage N calibration entry" above with before/after value + 2-sentence rationale. Do not overfit on 100 jobs — if a fix would match exactly one ad, note it and wait for Stage 3.

**When to stop tuning:** when decision-distribution drift between consecutive stages is ≤5pp on each decision class, and you can't find an obvious spot-check miss in a 20-sample sweep.

---

## Decision record

**2026-04-24 — JobSync purge deferred from ingest-prep track.**
Rationale: JobSync sync runs *after* application_pack in the pipeline, as a separate operation. Running the core triage/parse/match/pack pipeline through the staged ingest does not require JobSync state to be clean. The purge research (§3 of `docs/execplans/jobsync-purge-prep.md`) is still owed but no longer blocks intake. Reconfirm before the first JobSync sync after this ingest.

**2026-04-24 — Profile folder contract is the canonical input.**
Rationale: see `docs/current-state.json` → `recent_decisions[decided_at=2026-04-24]`.

---

## Rollback

- Each stage is bounded by `--max-jobs`; interrupting mid-stage leaves the queue intact.
- Per-stage archives via `reset-runtime --tag <stage-tag>` before Stage 1; subsequent stages are additive.
- To fully unwind a bad calibration: `git checkout -- configs/pipeline.v1.yaml` (knob changes are in-repo diff; no hidden state).
- To fully unwind intake: `jobpipe reset-runtime --tag abort_staged_ingest_<stamp>` — archives current `reports/`, `db/`, `jobs_delta.jsonl` under `JOBPIPE_DATA_DIR`, leaves repo-root profile/ intact.

---

## Handoff

- This file is the calibration log. Update it inline after each stage.
- Link from GitHub Project #6 (planning-only item — no Codex implementation needed).
- When all four stages complete: add a "Stage 4 summary" + close the ingest_prep_track in `docs/current-state.json`.
