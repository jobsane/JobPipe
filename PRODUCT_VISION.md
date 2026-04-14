# JobPipe — Product Vision

**Owner:** Lars Værland
**Last updated:** 2026-04-14

---

## North star

> **Finn jobbene der kandidaten er sterkere enn han ser ut på papiret.**

JobPipe's core purpose is not to match Lars to the most obvious jobs with the most applicants. It is to find the roles where he is an *advantageous match*: jobs in less obvious sectors, with broader scope than the title suggests, where the hiring manager cares more about delivery in complexity and cross-functional alignment than about narrow keyword matching. These are the roles where Lars's actual track record outperforms his CV's first impression.

This shapes everything: triage calibration, scoring, the shape of application packs, and which jobs get deep attention.

---

## What is JobPipe?

An AI-powered job hunting pipeline that automatically finds, scores, and prepares applications for jobs that match Lars's profile as a product owner / service owner / digital project leader. It replaces the manual process of scanning hundreds of irrelevant job ads daily with a system that surfaces only the 2–5% that are worth acting on — with special emphasis on the *advantageous matches* where Lars is more competitive than he appears at first glance.

---

## Value proposition

**For Lars (the user):**
- Never miss a strong match — the pipeline runs continuously against NAV's full job feed
- Never waste time on irrelevant ads — geo filter, title filter, and AI triage eliminate 95%+ before human review
- Always be prepared — application packs (positioning, evidence map, cover letter angle, interview prep) are pre-generated for top matches
- Always know where you stand — dashboard shows the full funnel, actionable jobs, and pipeline health

**If productized (future):**
- For mid-career professionals actively job hunting: upload your CV, set your preferences, get a daily shortlist with AI-scored matches and ready-made application materials
- Differentiator: multi-stage triage funnel that's cost-efficient (cheap models for filtering, expensive models only for top matches) + career-pivot scoring that catches non-obvious opportunities

---

## Success metrics

### Primary (weekly review)
| Metric | Target | Current | Status |
|--------|--------|---------|--------|
| Strong matches surfaced (APPLY + APPLY_STRONGLY) | 3–10/week | ~1/500 jobs | Feed quality issue, not pipeline issue |
| False negatives (relevant jobs wrongly SKIP'd) | 0 | 0 verified (500-job test) | On target |
| Triage pass rate | 2–8% | 1.4% | Acceptable — feed is noisy |
| Token waste (triage-pass → moderator-SKIP) | <30% | 29% | Borderline, monitor |
| Time from job posted to Lars seeing it | <24 hours | Unknown (trigger schedule TBD) | Needs measurement |

### Secondary (monthly review)
| Metric | Target | Notes |
|--------|--------|-------|
| Total unique jobs processed | Growing | Currently 4,255 |
| Pipeline uptime | Daily runs | Currently manual |
| Cost per APPLY-quality match | <$0.50 | Mostly nano calls, should be well under |
| Dashboard usability | Opens daily, acts on top matches | V1 built, iterating |

---

## User stories

### Core (implemented)
- As Lars, I want to see only jobs that match my profile so I don't waste time reading irrelevant ads
- As Lars, I want jobs scored by fit AND pivot potential so I can see both safe matches and stretch opportunities
- As Lars, I want application materials pre-generated so I can apply quickly to top matches
- As Lars, I want a dashboard showing my action list sorted by fit score so I know what to apply to today

### In progress
- As Lars, I want the pipeline to run automatically so I don't have to trigger it manually
- As Lars, I want the import to only pull active jobs so the pipeline is fast and cheap
- As Lars, I want to see pipeline health metrics so I can tell if the triage is tuned correctly

### Planned
- As Lars, I want to filter by occupation code before AI triage so I skip obviously irrelevant categories at zero cost
- As Lars, I want expiring-soon alerts so I don't miss application deadlines
- As Lars, I want to mark jobs as "applied" / "rejected" / "interview" and track my application funnel

### Future / aspirational
- As Lars, I want the system to learn from my apply/reject decisions and improve triage over time
- As Lars, I want to receive a daily email digest with my top 3 matches
- As Lars, I want to compare my profile against a specific job ad on demand (not just batch)

---

## Architecture overview

```
NAV API (pam-stilling-feed)
    ↓ Apps Script (trigger, 200 jobs/run)
Google Sheet (JobFeed, ~35,850 rows)
    ↓ pull_sheets_csv.py (status filter: ACTIVE only)
jobs_delta.jsonl
    ↓ run_feed.py (staged pipeline)
    ├─ [FREE] Geo postal filter (0/1/3/4xxx)
    ├─ [FREE] Hard-no title regex
    ├─ [NANO] AI triage (gpt-4.1-nano)
    ├─ [MINI] Reverse triage (low-confidence reconsideration)
    ├─ [MINI] Parse (extract structured requirements)
    ├─ [MINI] Profile match (fit score 0-100)
    ├─ [MINI] Pivot (career pivot potential 0-100)
    ├─ [FREE] Moderate (deterministic thresholds → final decision)
    └─ [FULL] Application pack (only for APPLY/APPLY_STRONGLY)
    ↓
out_runs/<run_id>/<job_id>/ (per-job artifacts)
    ↓ sync_ledger.py
reports/ledger.sqlite (deduplicated, latest state per job)
    ↓ export_dashboard.py
reports/dashboard.html (self-contained, opens in browser)
```

**Cost funnel design:** The most expensive model (gpt-4.1) only runs for the ~1% of jobs that score APPLY or higher. The cheapest model (nano) handles the 95%+ that need to be filtered. This makes the system affordable to run continuously.

---


---

## Design principles

1. **Cheap before smart** — free filters (geo, regex) before LLM calls. Always.
2. **Never miss a strong match** — safety overrides catch false negatives on keywords even when the LLM says SKIP.
3. **Every decision is debuggable** — every stage writes a JSON artifact. No hidden logic.
4. **Incremental, not monolithic** — process deltas, not the full feed. Don't re-process unless input changed.
5. **Human in the loop** — the system recommends, Lars decides. No auto-apply.
6. **Lars interacts with the output, not the feed** — NAV, LinkedIn, Finn.no all flow in silently. The inbox is a data pipe. Lars sees only what survived all filters, in the dashboard.
7. **Noise is a cost** — every irrelevant job that reaches Lars wastes attention. Minimize noise at the earliest, cheapest layer possible.
8. **Reduce cognitive load, don't add to it** — Lars has high IQ but average working memory and processing speed (Alva Labs profile). The system should externalize memory, pre-generate language, chunk decisions, and surface one clear action at a time. Application packs are not for reading — they are for *acting*. Every output should answer: "what do I do right now?"
9. **Motivation articulation is a first-class output** — one of the hardest parts of applying is expressing *why* clearly. The application pack must generate ready-to-use motivation language in Norwegian, not generic summaries. The user should be able to copy and adapt, not write from scratch.

---

## Multi-source architecture (planned)

The pipeline is designed to receive jobs from multiple sources through a single contact point. Sources are kept entirely separate from pipeline logic — each source writes to `jobs_leads.jsonl` in a normalized format, and the pipeline treats all sources identically from that point forward.

### Contact point schema

```jsonl
{
  "job_id": "li_4399048987",
  "source": "linkedin_alert",
  "title": "Prosjektleder IT",
  "employer": "Atea Norge",
  "work_city": "Oslo",
  "source_url": "https://linkedin.com/jobs/view/4399048987",
  "seen_at": "2026-04-12"
}
```

`job_id` is always `{source_prefix}_{source_id}`:
- `nav_` — NAV pam-stilling-feed (current)
- `li_` — LinkedIn job alert email
- `fn_` — Finn.no job agent email

### Source modules (current and planned)

| Source | Status | Data quality | Notes |
|--------|--------|-------------|-------|
| NAV pam-stilling-feed | ✅ Live | Full (title, employer, description, postal, deadline) | Via Google Sheet → pull_sheets_csv.py |
| LinkedIn job alerts | Planned | Partial (title, employer, city, job ID — no description) | Parse from email body, 6+ jobs per email |
| Finn.no job agent | Planned | TBD — need to inspect email format | |
| LinkedIn API / scrape | Future | Full if accessible | LinkedIn has no public job API |
| Finn.no API | Future | Full (UNLEASH partner API, worth investigating) | Structured, may replace email parsing |

### Deduplication

The same job frequently appears on NAV, LinkedIn, and Finn.no simultaneously. Strategy:

- **Phase 1 (now):** Accept source-prefixed duplicates as separate ledger records. Volume is low enough that this is acceptable noise.
- **Phase 2 (when multi-source is live):** Deduplicate at `sync_ledger` time by matching `(employer_normalized, title_normalized)` within a 14-day window. Keep the record with the fullest data as canonical; mark others with `canonical_id`.

### Source of truth

| Concern | Source of truth |
|---------|----------------|
| Job data (title, employer, description, scores) | `ledger.sqlite` |
| Application status (applied, interview, rejected) | `reports/application_state.json` |
| Raw job input (immutable) | `out_runs/*/00_input.json` |

### Gmail as a data pipe

LinkedIn and Finn.no deliver pre-filtered, AI-matched leads directly to the inbox via job alert emails. These alerts are the output of their own recommendation models — free lead generation that's already pre-filtered against Lars's profile.

The Gmail automation layer (planned) intercepts these before Lars sees them:

```
LinkedIn/Finn.no alert arrives
    ↓ Gmail filter → auto-label + skip inbox (never interrupts Lars)
    ↓ Scheduled script (daily)
    ├─ [FREE] Title hard-no regex (on subject line alone)
    ├─ [FREE] Geo filter (city name → allowed list)
    ├─ [FREE] Employer sector filter
    └─ survivors → jobs_leads.jsonl → pipeline
```

Alert emails that fail the free filters are archived without Lars ever seeing them. Only pipeline output (the dashboard) reaches Lars.

**Alert strategy:** More saved searches on LinkedIn/Finn.no = more lead volume. Different search queries can be treated as separate channels and measured by triage pass rate over time — optimizing which alerts to keep is the same problem as optimizing a sales lead source.

---

## Product version roadmap

### v1 — Get Lars interviews (current focus)
**North star for v1:** Lars gets interviews. Pipeline finds the right jobs, application packs make applying fast and targeted.

#### v1 done ✅
- Triage prompt tuned (0 false negatives on favorites set)
- Profile updated: data/insight roles, operative stepping-stone logic, pay floors
- Dashboard V2: Pipeline Health, triage signals, scatter plot, location
- Application tracking: mark_status.py (multi-stage: shortlisted → called → applied → interview → outcome) + scan_gmail.py
- index.jsonl self-healing: post-run repair + wrapped try/except
- Dashboard status UI: milestone timeline + stage/outcome buttons
- sync_ledger root cause fix (URL/location fields)
- Status filter on pull_sheets_csv.py (ACTIVE-only, deadline filter)
- Geo false-pass fix (remote/hybrid checks specific fields only)
- Agent coordination system (AGENT_STATUS.md, CLAUDE.md)

#### v1 in progress / next
- [ ] **Application pack quality upgrade (agentic):** Replace single-shot gpt-4.1-mini call with a multi-step agentic pipeline using a capable model (o3 / gpt-4.1). The agent iterates on the cover letter and CV highlights across multiple reasoning steps — drafting, self-critiquing against job requirements, checking for authentic voice, and refining language. Target: output that requires minimal editing before sending. Hardest part of the pipeline to get right; highest ROI for interview conversion.
- [ ] Advantageous match scoring: explicit signal when job is in a non-obvious sector or broader than title suggests
- [ ] Automated daily run (Windows Task Scheduler or Cowork scheduled task)
- [ ] Fix buildIndex_() performance in Apps Script (raise MAX_ENTRIES_PER_RUN 50→200)
- [ ] Gmail auto-labeling: route LinkedIn/Finn.no alerts to SOKNADSPILOT, skip inbox
- [ ] LinkedIn email lead extraction: parse alert emails → jobs_leads.jsonl
- [ ] Deadline alert: flag jobs expiring within 7 days in dashboard

---

### v2 — Better than the competition (advantageous match engine)
**North star for v2:** JobPipe is systematically better than manual job hunting — not just faster, but smarter about which jobs to prioritize. Lars wins in the rooms where the odds are actually good.

Key capabilities v2 must add:
- **Advantageous match scoring** (not just fit score): quantify how much Lars is likely to stand out *given the likely applicant pool*. Sector novelty, title ambiguity, breadth of scope = higher advantage score.
- **Applicant pool signal**: use job ad language, sector, and posting channel to estimate competition level. Niche ads in non-obvious sectors → smaller pool of canonical candidates → Lars more likely to be shortlisted.
- **Feedback loop**: learn from Lars's apply/skip/interview/reject decisions. Surface patterns: which features predict that Lars actually applies AND gets responses?
- **Channel quality metrics**: triage pass rate per source (NAV vs LinkedIn vs Finn.no) in dashboard.
- **On-demand single job analysis**: Lars pastes a Finn URL, gets a full pack in <2 minutes.
- **Deduplication across sources** at sync_ledger.

---

### v3 — Platform (future)
**North star for v3:** Any mid-career professional can use the system. The pipeline becomes modular, configurable, and deployable for other users.

Key capabilities v3 would need:
- Multi-user profiles (each with their own profile_pack, geo rules, thresholds)
- UI for configuration (no YAML editing)
- Non-NAV sources (Finn API, LinkedIn API, custom job boards)
- Managed hosting (not self-hosted on user's Windows machine)
- Commercial model TBD

---

## Now / Next / Later (operational)

### Now
- [ ] **Application pack — agentic rewrite:** Multi-step agent (o3 / gpt-4.1) for cover letter and CV highlights. Self-critique loop, authentic Norwegian language, output ready to send with minimal editing.
- [ ] Automated daily run setup (Cowork scheduled task)
- [ ] Fix Apps Script buildIndex_() performance

### Next (weeks)
- [ ] LinkedIn email lead extraction
- [ ] Advantageous match signal in triage + dashboard
- [ ] Occupation code pre-filtering (NAV styrk08 codes)
- [ ] Geo filter for city-name-based sources (LinkedIn leads have city, not postal code)

### Later (months)
- [ ] Feedback loop from application outcomes
- [ ] Finn.no API investigation
- [ ] Channel quality metrics
- [ ] On-demand single job analysis
