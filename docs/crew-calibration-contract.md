# Crew Calibration Contract — JobPipe → Job hunter crew

**Status:** Proposal v1 (2026-04-24). Drafted by the Job hunter crew side.
**Owner (crew side):** Lars (`CrewAI - Lars crews/Job hunter crew`)
**Owner (JobPipe side):** JobPipe orchestrator (calibration skill author)
**Scope:** Defines the shape of the calibration artifact JobPipe emits after
each tuning pass (first 100 / 200 / 500 jobs) so the Job hunter crew can
consume it without re-deriving signal.

This is a sibling to `crew-contract.md` (which covers the per-job handoff).
This doc covers the *meta* feedback loop: how tuning insights propagate
from JobPipe into crew-side agent configuration and into `profile_pack.md`.

---

## 1. Principle — profile_pack.md is the single truth

The crew and JobPipe both read `profile_pack.md` as the authoritative
candidate signal. Neither system writes to it unilaterally.

Calibration artifacts from JobPipe should therefore:
- **Propose** diffs to `profile_pack.md` (human-readable before/after, with
  reasoning).
- **Not auto-commit.** Lars reviews and applies diffs manually, after which
  both systems re-read the file.

Anything that belongs strictly inside JobPipe (semantic threshold,
`geo_postal_regex`, model choice) stays in JobPipe config and is not
part of this artifact.

---

## 2. Required artifact shape

JobPipe emits one calibration artifact per tuning pass. Target location:

```
C:\Users\larsv\Jobpipe-orchestrator-v2\calibration\<YYYY-MM-DD>_<batch_size>.json
```

With a human-readable sibling:

```
C:\Users\larsv\Jobpipe-orchestrator-v2\calibration\<YYYY-MM-DD>_<batch_size>.md
```

The JSON is what the crew's `calibrate` task parses. The MD is what Lars
reads before approving.

### 2.1 JSON schema (minimum viable)

```json
{
  "artifact_version": "1.0",
  "batch_id": "2026-04-24_n100",
  "batch_size": 100,
  "generated_at": "2026-04-24T12:00:00Z",

  "summary": {
    "jobs_ingested": 100,
    "triage_skip": 62,
    "triage_review": 25,
    "triage_apply": 13,
    "skip_reasons": {
      "geo_postal": 28,
      "geo_county": 5,
      "hard_no_title": 11,
      "semantic_below_threshold": 14,
      "pay_below_floor": 2,
      "other": 2
    }
  },

  "false_positives": [
    {
      "job_id": "nav-12345",
      "title": "Senior Sales Manager - Nordics",
      "company": "Acme",
      "triage_decision": "REVIEW_LIKELY",
      "lars_override": "SKIP",
      "pattern": "title contains 'Sales Manager' — should have been hard_no",
      "proposed_profile_pack_change": {
        "section": "4",
        "action": "add hard_no_title pattern: 'sales manager'"
      }
    }
  ],

  "false_negatives": [
    {
      "job_id": "nav-67890",
      "title": "Tjenesteutviklingsleder digital",
      "company": "Ruter",
      "triage_decision": "SKIP",
      "lars_override": "APPLY",
      "pattern": "title 'Tjenesteutviklingsleder' not in target_titles",
      "proposed_profile_pack_change": {
        "section": "1",
        "action": "add target_title variant: 'Tjenesteutviklingsleder'"
      }
    }
  ],

  "threshold_observations": {
    "semantic_filter_threshold": 0.30,
    "mean_score_passed": 0.54,
    "mean_score_skipped": 0.18,
    "boundary_cases_in_0.25_to_0.35": 7,
    "recommendation": "hold at 0.30 — boundary band is noisy but not dominant"
  },

  "geo_observations": {
    "jobs_with_postal_code": 78,
    "jobs_passed_postal_filter": 71,
    "corridor_distribution": {
      "agder_4xxx": 22,
      "telemark_3xxx": 8,
      "oslo_0xxx": 28,
      "romerike_1xxx": 13
    },
    "note_for_crew": "Agder-corridor 48xx-49xx: 18 jobs (commute-feasible from Arendal). Others require relocation consideration."
  },

  "pay_observations": {
    "jobs_with_salary_listed": 19,
    "below_floor": 2,
    "within_preferred": 11,
    "above_preferred": 6
  },

  "proposed_profile_pack_diff": {
    "human_readable": "calibration/2026-04-24_n100.md",
    "sections_touched": ["1", "4", "5"],
    "risk_level": "low"
  },

  "raw_decisions_file": "calibration/2026-04-24_n100_raw.jsonl"
}
```

### 2.2 Markdown sibling (human-readable)

At minimum:

1. Executive summary (3-5 bullets: what changed, why, risk level).
2. Proposed profile_pack diff, shown as concrete before/after blocks.
3. Top 5 false-positives with reasoning.
4. Top 5 false-negatives with reasoning.
5. Recommendation: accept diff / re-tune / investigate further.

### 2.3 Raw decisions JSONL (optional but useful)

One line per job triaged, with:
- `job_id`, `title`, `company`, `triage_decision`, `confidence`, `signals`,
  `lars_override` (if any), `semantic_score`, `postal`, `county`.

Used by the crew if we later want to train a lightweight classifier or
spot-check patterns JobPipe didn't flag.

---

## 3. What the crew will do with this

The crew consumes the artifact in three places:

1. **`profile_pack.md` diff review** — crew's `calibrate` task reads the
   proposed diff, cross-checks against crew-side signal (cover letter voice
   corpus, application outcomes once Phase 5 lands), and flags conflicts.
   Lars approves → single commit updates profile_pack → both systems re-read.

2. **Crew-internal agent tuning** — some signals shape crew agents directly,
   not profile_pack:
   - `threshold_observations` → CVTailor's confidence cutoff (don't tailor
     for sub-threshold jobs).
   - `false_positive` patterns → CoverLetter agent's skip list (don't draft
     for patterns triage should have caught).
   - `geo_observations.corridor_distribution` → application tracker tags
     (commute vs relocation) for sorting.

3. **Reality check on voice corpus** — if `false_negatives` include jobs Lars
   would genuinely have wanted, cross-reference with `cover_letter_voice.md`
   to see if the positioning in seksjon 0 is too narrow.

---

## 4. What the crew will NOT write back (yet)

Until Phase 3-5 + Gmail tracker are in place, the crew is consume-only.
Later additions to this contract will cover:

- **Application outcome artifact** (crew → JobPipe): interview rate,
  rejection reasons, silence rate per company/role-type. Feeds profile_pack
  seksjon 5 keyword weights and seksjon 4 hard_no refinements.
- **Cover letter voice-fit scores:** how well crew's drafted letters
  matched Lars's cool-register rules. Signal for agent-prompt tuning,
  not JobPipe.
- **CVTailor bullet-resonance:** which seksjon 7 evidence bullets
  correlate with APPLY outcomes. Feeds back into which evidence to
  prioritize.

---

## 5. Cadence

- First artifact: after first 100 jobs (current batch).
- Second: after 300 jobs (cumulative), if first pass showed drift.
- Third: after 500 jobs, expected to be the tuning-stable point.
- After that: on-demand, only when drift is suspected.

Artifacts are additive — keep all of them in `calibration/`. The crew
reads the latest plus the previous one (for delta analysis).

---

## 6. Open questions for orchestrator

1. Can the raw decisions JSONL include `semantic_score` per job, or is that
   model-internal and not surfaceable?
2. For `lars_override`, how are overrides captured? (Manual CSV? GitHub
   Project status change? Inline comment?) — the crew needs to know the
   capture channel so it can cross-reference.
3. Will the artifact be regenerated if Lars updates `profile_pack.md`
   mid-batch, or only on fresh batches?

---

## 7. Change log

- **2026-04-24 v1** — Initial proposal by Job hunter crew side.
