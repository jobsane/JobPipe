# Crew Contract — JobPipe ↔ Job hunter crew (CrewAI)

**Status:** Proposal v1 (2026-04-23). Drafted by the Job hunter crew side.
**Owner (crew side):** Lars (`CrewAI - Lars crews/Job hunter crew`)
**Owner (JobPipe side):** JobPipe maintainers
**Scope:** Defines how JobPipe feeds curated postings into the Job hunter crew,
how the crew feeds artefacts (tailored CV, cover letter, ready-to-apply pack)
back, and which system owns which state.

This file is the canonical contract. Do not change the schema or boundary
without updating this doc and pinging the crew-side owner.

---

## 1. Ownership boundary

Two systems, two status enums, two jobs. They do **not** share a
vocabulary and should not try to.

| Concern                                            | Owner    | Notes |
|----------------------------------------------------|----------|-------|
| Raw ingestion (NAV feeds, finn, LinkedIn, gmail)   | JobPipe  | 9k+ NAV records daily, dedupe, normalisation |
| Triage status enum (SKIP / REVIEW_* / APPLY / APPLY_STRONGLY) | JobPipe | Deterministic; lives entirely inside JobPipe. Not exposed to crew as a decision. |
| Curated candidate list                             | JobPipe  | Exports to crew; see §3 |
| LLM re-scoring (fit + realism) per posting         | **Crew** | Independent judgment, not a JobPipe rubber stamp |
| Keyword extraction, gap analysis                   | **Crew** | Keywords-Pydantic, GapAnalysis-Pydantic |
| CV tailoring (JSON Resume edits + bullet trace)    | **Crew** | Phase 3 — Validator pattern |
| Cover letter drafting                              | **Crew** | Phase 5 |
| Application workflow status enum (Found → Offer → Withdrawn) | **Crew** | GitHub Project #7 is the canonical schema. JobPipe DB + JobSync adapt. |
| Persistence / history of workflow state            | JobPipe DB + JobSync | Storage, not schema. Mirror the crew's enum. |
| CV template rendering (Reactive Resume)            | JobPipe / Reactive Resume | Crew emits JSON Resume; rendering lives elsewhere |

**Status enum canonical source:** GitHub Project #7
(`https://github.com/users/larsvaerland/projects/7`). When the crew's
Status enum changes, JobPipe and JobSync adapt their columns/field
values to match — not the other way around. JobPipe's own triage
bucket (SKIP/REVIEW_*/APPLY) is a **separate** field and stays
untouched; don't try to reconcile the two.

---

## 2. CrewAI's optimal needs (design principles you should respect)

These are preferences, not demands. If JobPipe already does things a
different way, check with the crew-side owner before changing.

1. **Narrow payloads, not fat context dumps.** Send what the scorer agent
   needs to reason about a single posting. Don't attach the whole
   profile_pack — the crew has its own profile module.
2. **Upstream signals as HINTS, not directives.** The scorer agent is told
   in its backstory to disagree with JobPipe when warranted. Don't ship
   a prompt that says "JobPipe decided APPLY, so recommend tailor" — the
   scorer will mimic and we lose the second opinion.
3. **No regex rule-smuggling in descriptions.** Don't paste JobPipe's
   hard-no / target-title regexes into the posting `description`. They
   bias the LLM into rules-mimicking mode instead of calibrated reasoning.
4. **Honest language tag.** Use `language: "no"` vs `"en"` vs `"unknown"`.
   The scorer adjusts realism_score against Norwegian-only roles (Lars is
   conversational NO, fluent EN).
5. **Let the crew batch.** The crew uses `kickoff_for_each(inputs_list)`.
   One JSONL file per run is easier to manage than one HTTP call per
   posting.
6. **Idempotent IDs.** `source:native_id` (e.g. `finn:12345`). The crew
   writes `output/fit_<id>.json` keyed on this.
7. **Drift early.** If your schema changes, bump a version header in
   the first line of the JSONL as a JSON `{"__meta__": {"version": "1.1"}}`
   record. The crew will surface the mismatch at the adapter boundary,
   not mid-LLM-call.

---

## 3. Forward flow: JobPipe → Crew

### 3.1 What to emit

A JSONL file at a well-known path (default: `exports/crew_postings.jsonl`),
one posting per line, UTF-8, no trailing commas, no wrapper array.

**Required keys** (marked `*`). Unknown keys are ignored:

```jsonc
{
  "id*":          "finn:12345",
  "source*":      "finn",            // arbeidsplassen | finn | linkedin | indeed | manual
  "title*":       "Senior Product Manager — AI Platform",
  "company*":     "Acme Norge AS",
  "location":     "Oslo, Norway (hybrid)",
  "language":     "en",              // no | en | unknown
  "description*": "Full JD text, HTML-stripped. Keep the full body — don't pre-filter.",
  "url":          "https://finn.no/job/12345",
  "posted_at":    "2026-04-20",
  "deadline":     "2026-05-15",
  "upstream_signals": [
    {
      "source_pipeline":        "jobpipe",
      "pipeline_run_id":        "2026-04-23T07:00:00Z#nav",
      "triage_decision":        "PROCEED",
      "triage_confidence":      0.82,
      "fit_score":              71,
      "pivot_score":            18,
      "final_decision":         "APPLY",         // APPLY_STRONGLY | APPLY | REVIEW_HIGH | REVIEW_LOW | SKIP
      "final_confidence":       0.77,
      "recommendation_reason":  "Matches PM + AI + Oslo; English ok.",
      "skip_reason":            null,
      "tags":                   ["pm", "ai", "oslo", "hybrid"]
    }
  ]
}
```

**Who emits SKIPs?** For now, only emit postings the crew should look at.
Default inclusion rule: `final_decision ∈ {APPLY_STRONGLY, APPLY, REVIEW_HIGH}`.
Do not emit `REVIEW_LOW` or `SKIP` unless Lars explicitly requests an audit
stream (see §5).

### 3.2 Proposed JobPipe CLI

Mirror the existing `jobpipe/cli/export_jobsync.py` pattern. Drop into
`jobpipe/cli/export_for_crew.py`:

```python
"""Export curated postings to the Job hunter crew as JSONL.

Mirrors export_jobsync.py. Reads job_evaluations via the existing
projections/dashboard.py::build_payload path, filters to actionable
decisions, and writes Posting-shaped JSONL.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from jobpipe.projections.dashboard import build_payload  # or equivalent

ACTIONABLE = {"APPLY_STRONGLY", "APPLY", "REVIEW_HIGH"}


def row_to_record(row: dict) -> dict:
    """Projection row → crew Posting record."""
    return {
        "id":          f"{row['source']}:{row['job_id']}",
        "source":      row["source"],              # finn | arbeidsplassen | ...
        "title":       row["title"],
        "company":     row["employer"],
        "location":    ", ".join(filter(None, [row.get("work_city"), row.get("work_county")])),
        "language":    row.get("language", "unknown"),
        "description": row["description"],         # full, HTML-stripped
        "url":         row.get("url"),
        "posted_at":   row.get("posted_at"),
        "deadline":    row.get("applicationDue"),
        "upstream_signals": [{
            "source_pipeline":       "jobpipe",
            "pipeline_run_id":       row.get("pipeline_run_id"),
            "triage_decision":       row.get("triage_decision"),
            "triage_confidence":     row.get("triage_confidence"),
            "fit_score":             row.get("fit_score"),
            "pivot_score":           row.get("pivot_score"),
            "final_decision":        row.get("final_decision"),
            "final_confidence":      row.get("final_confidence"),
            "recommendation_reason": row.get("recommendation_reason"),
            "skip_reason":           row.get("skip_reason"),
            "tags":                  row.get("tags", []),
        }],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="exports/crew_postings.jsonl")
    ap.add_argument("--include-review-low", action="store_true",
                    help="Include REVIEW_LOW — audit-only, inflates LLM cost.")
    args = ap.parse_args()

    payload = build_payload()  # same reader JobSync uses
    allow = set(ACTIONABLE)
    if args.include_review_low:
        allow.add("REVIEW_LOW")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for row in payload["items"]:
            if row.get("final_decision") not in allow:
                continue
            fh.write(json.dumps(row_to_record(row), ensure_ascii=False) + "\n")

    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
```

### 3.3 How the crew consumes it

```python
from job_hunter.sources import iter_jobpipe_postings

for posting in iter_jobpipe_postings(
    "exports/crew_postings.jsonl",
    allow_decisions={"APPLY_STRONGLY", "APPLY", "REVIEW_HIGH"},
    min_final_confidence=0.55,
):
    # hand each Posting to JobHunterCrew().crew().kickoff(inputs=...)
    ...
```

The adapter validates every record against `Posting` + `UpstreamSignal`
Pydantic schemas. A drift in JobPipe's schema surfaces as a validation
error at ingest, not mid-run.

---

## 4. Reverse flow: Crew → JobPipe

When the crew finishes tailoring a posting, it writes a handoff JSONL
record that JobPipe can pick up on the next cycle.

**Default path:** `exports/crew_handoffs.jsonl` (crew writes, JobPipe
reads).

```jsonc
{
  "posting_id":       "finn:12345",
  "timestamp":        "2026-04-23T11:42:00Z",
  "crew_run_id":      "jh-2026-04-23-001",
  "crew_decision":    "ready_to_apply",   // ready_to_apply | needs_manual_review | skipped
  "fit_score":        74,                  // crew's own judgment, NOT JobPipe's
  "realism_score":    58,
  "coverage_pct":     81,
  "rationale":        "Strong PM + AI fit. Norwegian bar met via conversational + written samples.",
  "artefacts": {
    "tailored_cv_path":    "output/cv_finn_12345.pdf",
    "cover_letter_path":   "output/cover_finn_12345.pdf",
    "tailored_resume_json":"output/resume_finn_12345.json"
  },
  "bullet_trace": {
    "cv_b_001": "master_b_017",   // tailored_bullet_id → source_bullet_id
    "cv_b_002": "master_b_024"
  }
}
```

**What JobPipe should do with this:**
- Update the posting row with a workflow-status field whose values
  **match the crew's Project #7 Status enum** (Found / Scored /
  Tailored / Ready to apply / Applied / Screening / Interview / Offer /
  Rejected / Skipped / Withdrawn). This is the canonical workflow
  vocabulary.
- Keep your existing `final_decision` field (SKIP/REVIEW_*/APPLY)
  untouched — that's the JobPipe triage bucket, a separate dimension.
  Do NOT collapse the two into one field.
- Do NOT overwrite JobPipe's own `fit_score`. The crew's `fit_score` is
  a second opinion on the same posting and belongs on a separate
  column (`crew_fit_score`, `crew_realism_score`).
- Optionally surface the artefact paths on the JobSync board so Lars can
  review from one place.

---

## 5. Audit stream (optional)

To catch JobPipe's known Norwegian-keyword bias against English remote EU
roles, the crew wants the option to pull a small `REVIEW_LOW`/`SKIP`
audit sample weekly.

Proposal: a second CLI flag `--audit-sample N` on `export_for_crew.py`
that emits N random REVIEW_LOW/SKIP records to
`exports/crew_audit_sample.jsonl`. The crew re-scores them with the
normal scorer. Any re-score with `fit_score >= 65` surfaces as a
potential false-negative in JobPipe's triage rules.

Lars has indicated this is already partially wired via the existing
test-loop. If you want the crew to take it over, say so.

---

## 6. Triggering the crew from JobPipe (optional)

If JobPipe wants to kick the crew after an export:

### Option A — Shell (lowest friction)

```bash
# inside the crew repo, with the venv active
python -m job_hunter.main --posting exports/crew_postings.jsonl --batch
```

Not implemented yet — current `main.run()` takes a single posting. Add
`--batch` that loops `iter_jobpipe_postings` and calls
`crew.kickoff_for_each(inputs_list)`. Tracked as a Phase 5 task.

### Option B — CrewAI Flow webhook (later)

When the crew is wrapped in a `crewai.flow.Flow`, expose a
`POST /trigger` endpoint. JobPipe posts `{"posting_id": "...", "export_path": "..."}`
and the flow handles batching, cost caps, and result writeback.

**Prefer Option A** until Lars's volume justifies a service. Budget cap
still applies: `CREW_MONTHLY_CAP=25` per month for the Job hunter crew.

---

## 7. What the crew has already done (2026-04-23)

1. **Schemas extended** — `Posting` now carries `upstream_signals: list[UpstreamSignal]`.
   See `src/job_hunter/schemas.py`.
2. **Scorer de-biased** — `job_scorer.backstory` explicitly names JobPipe
   as a keyword-heavy Norwegian pipeline with a known under-scoring bias
   on English remote EU roles. Agent is told to form its own judgment.
3. **Phase 2 agents wired** — `keyword_extractor` (gpt-4o-mini) and
   `gap_analyzer` (haiku) with context-chained task output.
4. **Adapter added** — `src/job_hunter/sources/jobpipe_adapter.py`
   reads a JSONL export shaped like §3.1.
5. **Smoke test** — 15 offline checks, covering the adapter round-trip
   and Phase 2 YAML wiring.

## 8. What's still open

- JobPipe-side: add `jobpipe/cli/export_for_crew.py` per §3.2.
- Crew-side: `--batch` mode + reverse JSONL writer (§4).
- Both sides: agree on the `crew_handoff_status` field name if JobPipe
  wants to render it on the JobSync board.
- Both sides: decide whether the audit stream (§5) is crew-run or
  JobPipe-run.

---

## 9. Change log

- **2026-04-23 (v1.2)** — Integration surfaces locked:
  - **Resume schema:** Crew's internal output stays JSON Resume
    (`profile/resume.json`). Crew owns the JSON Resume → Reactive
    Resume `ResumeData` converter. Reactive Resume is the renderer,
    not the schema authority. If Lars swaps renderer later, the
    converter is the only thing that changes.
  - **JobSync inbound route:** Crew uses the existing
    `POST /api/integrations/jobpipe/jobs` as-is (cosmetic naming
    aside). All adapter code stays on the crew side — JobSync does
    not need changes for the crew to start POSTing.
  - **JobSync auth:** `X-JobPipe-Token` shared-secret header, value
    from JobSync's `JOBSYNC_SYNC_TOKEN` env var. Note: the separate
    API-key system inside JobSync is for its own AI/admin features
    and is **not** used for cross-system integration.
  - **Reactive Resume auth:** `x-api-key` header, value TBD (Lars to
    confirm). Crew reads it from `REACTIVE_RESUME_API_KEY` env.
- **2026-04-23 (v1.1)** — Boundary clarified: the two systems keep
  **separate status enums**. JobPipe's triage bucket (SKIP/REVIEW_*/
  APPLY) stays internal to JobPipe. The crew's Project #7 workflow
  Status enum (Found → Offer → Withdrawn) is canonical for the
  application lifecycle; JobPipe DB and JobSync adapt their schema to
  it. JobPipe DB remains the persistence layer.
- **2026-04-23 (v1)** — Initial draft.
