# JobPipe — Product Vision

**Owner:** Lars Værland
**Last updated:** 2026-04-19

---

## North star

> **Reduce cognitive noise in job hunting by making job-ad data do the screening work first.**

JobPipe's core purpose is not to help Lars read more job ads. It is to make the job-ad data pipeline remove as much irrelevant thinking as possible before human effort starts. The system should absorb feed noise, duplicate ads, missing-field chaos, weak matches, and repetitive context gathering so Lars spends his time only on the parts where human judgment matters: review, tailoring, application quality, and follow-up.

The specific strategic edge remains the same:

- find the roles where Lars is an *advantageous match*
- surface jobs in less obvious sectors or with broader scope than the title suggests
- prioritize cases where Lars's actual track record is stronger than the first impression his CV gives on paper

This shapes everything: triage calibration, scoring, the shape of application packs, and which jobs get deep attention.

The system should also prefer **selection over invention**:

- AI should choose, rank, reveal, hide, and reorder approved content wherever possible
- AI should not default to rewriting CV truth from scratch
- structured composition is preferable to AI fluff if it produces a stronger, more believable application

North-star rule for future planning:

- every major topic must improve how job-ad data is shaped for the next decision
- upstream layers should hold thicker, noisier truth
- downstream layers should receive smaller, more precise AI-ready briefs
- no topic should add workflow or UI complexity unless it clearly improves signal quality, reduces cognitive load, or increases action quality

---

## What is JobPipe?

An AI-powered job-ad intelligence pipeline that automatically finds, scores, and prepares applications for jobs that match Lars's profile as a product owner / service owner / digital project leader. It replaces the manual process of scanning hundreds of irrelevant job ads daily with a system that surfaces only the 2–5% that are worth acting on, with special emphasis on the *advantageous matches* where Lars is more competitive than he appears at first glance.

Operationally, JobPipe should become the control plane for the job hunt:
- source and lead intake
- profile-pack setup
- geo / domain / role targeting
- credentials and mailbox integrations
- analysis and triage
- application-packet preparation before a lead is promoted into the active application workspace

In other words:

- `JobPipe` should think hardest where manual thinking adds the least value
- the system should automate away cognitive noise before the job hunter ever sees it
- the system should preserve enough evidence and context that the user can still trust and override it

---

## Value proposition

**For Lars (the user):**
- Never miss a strong match — the pipeline runs continuously against NAV's full job feed
- Never waste time on irrelevant ads — connector-aware deterministic filters and AI triage eliminate the bulk of noise before human review
- Spend human effort only where it matters — review, tailoring, and application quality happen only after the system has done the screening work
- Always be prepared — application packs, authoring briefs, and saveback targets reduce the setup cost for top matches
- Always know where you stand — control-plane state, workflow state, and artifacts stay traceable across the stack

**If productized (future):**
- For mid-career professionals actively job hunting: upload your CV, set your preferences, get a daily shortlist with AI-scored matches and ready-made application materials
- Differentiator: multi-stage triage funnel that's cost-efficient (cheap models for filtering, expensive models only for top matches) + career-pivot scoring that catches non-obvious opportunities

### Structured tailoring thesis

The stronger long-term product is not "AI writes a CV".

It is:

- approved structured professional content
- AI-driven selection and ordering of that content
- rendering/export through the best-fit authoring tool

In practice this means the system should support:

- multiple approved variants of the same role narrative
- project variants by job type and language
- evidence atoms that can be pulled in without dragging the full history
- skill ordering by relevance to the ad
- section visibility and section order rules

The best output is therefore not always more text. It is a better-composed application package.

---

## Product tracks

### OSS JobPipe

The OSS version must be a real single-user product, not a crippled demo. It should:
- run locally
- be platform agnostic
- be portable across machines and repo checkouts
- keep delivering full value to tinkerers and active job hunters without hosted infrastructure

### Hosted / private JobPipe

The private version is a separate product track:
- multi-user
- hosted
- more advanced automation, collaboration, and admin functionality
- allowed to depend on managed infrastructure that the OSS version must not require

### Private data boundary

For the OSS product, versioned code and private user state must be separate concerns.

Target rule:
- the git repo contains code, templates, examples, and docs
- the user's private data lives in a stable user data root outside the repo
- switching branches, recloning the repo, or resetting tracked files must not force Gmail re-auth, profile re-entry, or dashboard state rebuild from scratch

Private user state includes:
- profile and CV source files
- credentials and tokens
- job/application history
- ledgers, caches, generated artifacts, and exports

This boundary is now implemented in the active OSS runtime contract. The remaining work is to keep docs, habits, and future features aligned with it so private state does not creep back into the repo surface.

---

## Intended companion-product model

The planned user workflow is not one monolithic app. It is a companion stack with separate responsibilities:

- **JobPipe** decides what is worth acting on and prepares the handoff
- **JobSync** becomes the live application-case workspace after promotion
- **Reactive Resume** is the tailored CV authoring and export surface
- **Word / Docs-style editing** is the cover-letter and screening-answer iteration surface

The critical seam is: **promote a lead into an application case**.

That means the key JobPipe output is not just a score. It is an application packet containing:
- job metadata and source identity
- the job ad snapshot and apply URL
- match rationale and gap analysis
- cover-letter angle and screening-answer context
- CV highlights / tailoring guidance
- target artifact folder and linkage metadata

From that point on, JobSync should track the active case while external authoring tools produce the actual submission artifacts.

---

## Source-of-truth split

The intended stack is better if ownership is explicit instead of blurred.

### Integration doctrine

The product should be built with a **JobPipe-first, surgically integrated** architecture:

- reshape and modularize `JobPipe` aggressively as needed
- keep `JobSync` and `Reactive Resume` as external companion systems
- prefer thin, versioned seams over deep shared internals

The practical rule is:

- if a problem can be solved inside `JobPipe`, solve it inside `JobPipe`
- only touch sibling repos for the smallest receiver seam that the workflow truly needs

This preserves product agility without turning the rest of the stack into fragile hidden dependencies.

### JobPipe owns

- source connectors and staging
- dedupe before the main pipe
- triage, scoring, and explainability
- application-packet generation
- apply-session generation
- raw stage artifacts, pipeline memory, and calibration data
- control-plane settings for targeting, integrations, and mailbox lead intake

### JobSync owns

- the main operator shell once a lead becomes a live case
- active application queue
- notes, tasks, activities, and manual follow-up
- tracked case state after promotion
- artifact links and case-facing context

### Reactive Resume owns

- canonical resume structure
- resume variants
- tailored CV editing
- resume export artifacts and references

Reactive Resume should therefore be treated as the preferred structured resume surface, but JobPipe should still own the job-specific tailoring logic that selects which approved content is shown for a given case.

### Shared common ground

These objects should travel cleanly across boundaries instead of each repo inventing its own loose copy:

- `ProfileSnapshot`
- `ResumeVariantRef`
- `CanonicalJob`
- `ApplicationCase`
- `ApplicationPacket`
- `ApplySession`
- `ArtifactRef`
- `StatusEvent`
- `OutcomeFeedback`

The resume side of that common ground will eventually need more detail too:

- `ResumeMaster`
- `RoleRecord`
- `RoleVariant`
- `ProjectVariant`
- `EvidenceAtom`
- `SkillAtom`
- `NarrativeProfile`
- `TailoringPlan`

This is better than one giant shared store. The target is two durable systems plus contracts:

1. `JobPipe` pipeline store for noisy source data, stage outputs, and calibration
2. `JobSync` operational store for curated cases and human workflow
3. versioned contracts between them, with Reactive Resume feeding resume truth into the stack

### AI-ready data-shape rule

The stack should not move one giant accumulated dataset from system to system.

Instead:

1. `JobPipe` keeps the thick source and stage truth
2. each downstream step receives a smaller derived object shaped for that exact decision
3. exported artifacts and refs record what was actually used at apply time

That means the durable truth is primarily:

- structured job data
- structured profile/resume-derived context
- structured decision context
- artifact references
- outcome/status events

Generated text itself is important working material, but it is not the main thing to optimize for across boundaries. The system should optimize for the most precise structured context possible right before review, authoring, and apply.

### Triage v3 rule

The next triage model should not be one larger, friendlier prompt.

It should be:

1. hard deterministic gates
2. schema-bound feature extraction
3. calibrated first-pass ranking
4. ambiguity resolution only for borderline cases
5. narrative strategy only for shortlist-worthy jobs

The six-dimensional model is therefore useful as a feature family, but not as the final truth by itself. The system should prefer:

- features with confidence and evidence spans
- ranking over raw prompt intuition
- later narrative strategy over early prose generation

This keeps triage precise, debuggable, and compatible with both small local models and later calibration.

---

## Success metrics

The system is healthy when it reduces cognitive waste without hiding real opportunity.

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
- As Lars, I want a settings dashboard where I can maintain my profile pack, geo rules, domain/role targets, and credentials without digging through files
- As Lars, I want Gmail-driven lead intake and mailbox-status detection so inbox signals feed the system without becoming manual bookkeeping
- As Lars, I want recommended jobs from email/Finn to enter JobPipe as separate suggested-lead connectors so they can bypass the broad-feed source filter but still be deduped before triage
- As Lars, I want shortlisted jobs promoted into JobSync as `new` cases that then follow JobSync's normal workflow
- As Lars, I want clicking `apply` in the active workspace to open the job ad and application portal while also starting tailored CV and cover-letter drafting workflows
- As Lars, I want the final CV, cover letter, and screening-answer drafts saved back into the application folder tied to that case
- As Lars, I want JobPipe to have a real settings/control-plane UI instead of a growing report shell so profile, targeting, secrets, and connectors live in one durable place

### Future / aspirational
- As Lars, I want the system to learn from my apply/reject decisions and improve triage over time
- As Lars, I want to receive a daily email digest with my top 3 matches
- As Lars, I want to compare my profile against a specific job ad on demand (not just batch)

---

## Architecture overview

```
NAV API (pam-stilling-feed)
    ↓ Apps Script (hourly; currently ~50 jobs/run, planned 200)
Google Sheet (JobFeed)
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
    ↓ run_feed.py (staged pipeline)
    ├─ [NAV] normal deterministic gate stack
    │   ├─ [FREE] Geo postal filter (0/1/3/4xxx)
    │   ├─ [FREE] Hard-no title regex
    │   └─ [FREE] Semantic pre-filter
    ├─ [SUGGESTED] pre-vetted deterministic gate stack
    │   ├─ skip geo block
    │   ├─ [FREE] Hard-no title regex
    │   └─ skip semantic pre-filter
    ├─ [NANO] AI triage (gpt-4.1-nano)
    ├─ [MINI] Parse (extract structured requirements)
    ├─ [MINI] Profile match (fit score 0-100)
    ├─ [MINI] Pivot (career pivot potential 0-100)
    ├─ [FREE] Moderate (deterministic thresholds → final decision)
    └─ [MINI] Application pack (only for APPLY/APPLY_STRONGLY)
    ↓
<data-root>/out_runs/<run_id>/<job_id>/ (per-job artifacts)
    ↓ sync_ledger.py
<data-root>/reports/ledger.sqlite (deduplicated, latest state per job)
    ↓ export_dashboard.py / dashboard_server.py
<data-root>/exports/dashboard.html + local interactive dashboard
```

**Cost funnel design:** The most expensive model (gpt-4.1) only runs for the ~1% of jobs that score APPLY or higher. The cheapest model (nano) handles the 95%+ that need to be filtered. This makes the system affordable to run continuously.

---

## Target operating flow

1. JobPipe ingests jobs and external leads through separate connectors.
2. `NAV` remains the pragmatic canonical source when duplicate jobs collide across connectors, unless a suggested-lead variant is the only record with materially missing fields filled in.
3. JobPipe dedupes connector output before the rest of the pipeline sees the jobs.
4. Broad-feed `NAV` jobs go through the full deterministic gate stack, while pre-vetted suggested leads bypass `geo` and semantic pre-filter elimination but still honor hard-no title blocking.
5. JobPipe filters, scores, and explains which leads are worth action.
6. A promising lead is promoted into an application case with a structured packet.
7. JobSync receives that case as a `new` tracked job and owns the day-to-day workflow after promotion.
8. When Lars clicks `apply`, the system should:
   - open the job ad and the application portal in new tabs
   - trigger tailored CV work through Reactive Resume or a connected authoring flow
   - trigger cover-letter / screening-answer drafting in a document-oriented AI workspace
9. Lars edits the generated artifacts manually.
10. Final files are saved into the application folder for that job.
11. Lars submits manually.
12. Mailbox signals and manual updates continue to drive follow-up and status tracking.

The final submission step remains manual by design. The automation target is preparation, context carry-through, and tracking, not blind auto-apply.

---


---

## Design principles

1. **Cheap before smart** — free filters before LLM calls, but the deterministic gate stack can differ by connector when the source has already pre-vetted relevance.
2. **Never miss a strong match** — safety overrides catch false negatives on keywords even when the LLM says SKIP.
3. **Every decision is debuggable** — every stage writes a JSON artifact. No hidden logic.
4. **Incremental, not monolithic** — process deltas, not the full feed. Don't re-process unless input changed.
5. **Human in the loop** — the system recommends, Lars decides. No auto-apply.
6. **Lars interacts with the output, not the feed** — NAV, LinkedIn, Finn.no all flow in silently. The inbox is a data pipe. Lars sees only what survived connector merge, dedupe, and triage in the dashboard.
7. **Noise is a cost** — every irrelevant job that reaches Lars wastes attention. Minimize noise at the earliest, cheapest layer possible.
8. **Reduce cognitive load, don't add to it** — Lars has high IQ but average working memory and processing speed (Alva Labs profile). The system should externalize memory, pre-generate language, chunk decisions, and surface one clear action at a time. Application packs are not for reading — they are for *acting*. Every output should answer: "what do I do right now?"
9. **Motivation articulation is a first-class output** — one of the hardest parts of applying is expressing *why* clearly. The application pack must generate ready-to-use motivation language in Norwegian, not generic summaries. The user should be able to copy and adapt, not write from scratch.
10. **Private data must survive versioning** — repo operations must not behave like account resets. Local credentials, profile data, ledgers, and application state should survive branch switches and fresh clones through a stable data-root boundary outside tracked code.

---

## Product management structure

The project should be managed through a small set of explicit artifacts with different jobs:

- `PRODUCT_VISION.md`
  - north star
  - product principles
  - long-term roadmap
  - Now / Next / Later product priorities
- `docs/architecture-plan.md`
  - boundary rules
  - source-of-truth split
  - integration seams
- `docs/mvp-task-plan.md`
  - ordered short-term execution plan
  - one active topic at a time
  - concrete exit criteria and validation
- `AUDIT.md`
  - bugs
  - quality issues
  - debt
  - audit history
- `AGENT_STATUS.md`
  - current topic state
  - recent changes
  - cross-workstream handoffs

Rule:

- put strategy and long-term direction here
- put ordered implementation work in `docs/mvp-task-plan.md`
- put defects and debt in `AUDIT.md`
- put session state and handoffs in `AGENT_STATUS.md`
- do not create extra planning files unless the user explicitly asks for a new artifact

---

## Multi-source architecture (planned)

The pipeline is designed to receive jobs from multiple sources through separate connectors that merge into one shared pre-triage queue. Sources are not treated identically from the first byte onward:

- `NAV` is the broad canonical feed
- mailbox-derived suggested leads are already weakly pre-vetted by the platform
- connector policy therefore differs before triage

The merge rule is:

- separate connectors in
- dedupe before the main pipe
- preserve provenance
- prefer `NAV` as the pragmatic canonical record when duplicates collide

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
| Application status (applied, interview, rejected) | `<data-root>/reports/application_state.json` |
| Raw job input (immutable) | `<data-root>/out_runs/*/00_input.json` |

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
- [x] Advantageous match scoring: explicit signal when job is in a non-obvious sector or broader than title suggests
- [ ] Automated daily run (Windows Task Scheduler or Cowork scheduled task)
- [ ] Fix buildIndex_() performance in Apps Script (raise MAX_ENTRIES_PER_RUN 50→200)
- [ ] Gmail auto-labeling: route LinkedIn/Finn.no alerts to SOKNADSPILOT, skip inbox
- [ ] LinkedIn email lead extraction: parse alert emails → jobs_leads.jsonl
- [x] Add a first-class Settings / Integrations surface in JobPipe for profile pack, geo/domain/role targeting, secret presence, and connector state
- [x] Treat recommended jobs from mailbox/Finn as first-class leads that enter triage through the same lead connector before shortlist promotion
- [x] Keep Gmail recommendation intake separate from Gmail-derived status updates so new leads and application tracking do not collapse into one flow
- [x] Define the application-packet contract used to hand shortlisted leads into JobSync and external authoring flows
- [x] Keep JobSync changes minimal: import shortlisted leads as `new` and let the existing JobSync workflow own later manual progression
- [x] Add the minimal apply-time launch contract: JobSync can now open the job ad/application portal and the live JobPipe apply workspace with deterministic saveback targets
- [x] Replace the legacy JobPipe dashboard shell with a first app-style control-plane shell and automation page inside the current local runtime
- [ ] Add full external-authoring automation on top of that launch contract for CV and cover-letter workflows
- [x] Unify dashboard runtime and data contract so static export and local server show the same truth
- [x] Add a Profile & CV page driven by `<data-root>/profile_pack.md` and `<data-root>/reports/resume.json`
- [ ] Deadline alert: flag jobs expiring within 7 days in dashboard
- [x] Define a local-first data root so credentials, profile data, ledgers, and exports survive repo versioning without re-setup
- [x] Add a bounded experimentation, advantageous-match, and outcome-feedback loop inside JobPipe without auto-changing live ranking or config
- [x] Add a companion-revision pin file plus drift-check command so the local polyrepo stack can be validated against one checkpoint

---

### v2 — Better than the competition (advantageous match engine)
**North star for v2:** JobPipe is systematically better than manual job hunting — not just faster, but smarter about which jobs to prioritize. Lars wins in the rooms where the odds are actually good.

Key capabilities v2 must add:
- **Structured tailoring over approved content**: the system should produce `TailoringPlan`-style selection outputs that choose role variants, project variants, evidence atoms, skills, and section order instead of relying on broad AI rewriting.
- **AI-ready profile underlay**: derive compact, structured profile objects from Reactive Resume plus JobPipe settings so filters, triage, and authoring stop consuming incompatible profile shapes.
- **Derived boundary objects**: replace thick cross-system payloads with smaller purpose-built objects such as `TargetingProfile`, `TriageProfile`, `AuthoringProfile`, and `ApplicationCaseProjection`.
- **Experimentation toolpack**: make calibration, shadow scoring, threshold comparison, and holdout review part of the product instead of ad hoc manual analysis.
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
- Managed hosting for the private product track
- Clean separation between OSS single-user local mode and hosted multi-user mode
- Commercial model TBD

---

## Now / Next / Later (operational)

### Now
- [ ] **Application pack — agentic rewrite:** Multi-step authoring pipeline for cover letter and CV highlights, using the thinner decision/authoring briefs instead of the old broad packet shape.
- [ ] Automated daily run setup (Cowork scheduled task)
- [ ] Fix Apps Script buildIndex_() performance
- [ ] Make scheduled operation auditable:
  - companion drift preflight in the normal runbook
  - feed freshness timestamp and stale-run visibility
  - one repeatable local operator checklist for the full stack
- [ ] Define the first real JobPipe person/profile spine:
  - `ProfileSnapshot`
  - `TargetingProfile`
  - `TriageProfile`
  - `AuthoringProfile`
  - `ApplicationCaseProjection`

### Next (weeks)
- [ ] LinkedIn email lead extraction
- [ ] Occupation code pre-filtering (NAV styrk08 codes)
- [ ] Geo filter for city-name-based sources (LinkedIn leads have city, not postal code)
- [ ] Replace direct early-stage dependence on `profile_pack.md` narrative text with a derived profile adapter layer fed by Reactive Resume-compatible source data and local targeting settings
- [ ] Define the structured resume-tailoring model and source adapters:
  - `ResumeMaster`
  - `RoleRecord`
  - `RoleVariant`
  - `ProjectVariant`
  - `EvidenceAtom`
  - `SkillAtom`
  - `NarrativeProfile`
  - `TailoringPlan`
- [ ] Migrate one deterministic consumer and one scoring consumer onto the new profile/person-model spine
- [ ] Make the external authoring flow operationally complete without overcoupling:
  - Reactive Resume launch + AI-supported editing handoff
  - deterministic CV export capture
  - deterministic cover-letter and screening-answer export storage/registration
- [ ] Add deadline and freshness signals that support day-to-day operation, not just offline debugging

### Later (months)
- [ ] Full external-authoring automation across JobSync, Reactive Resume, and the cover-letter drafting workspace
- [ ] Automated artifact saveback and per-case file linking
- [ ] Promote the bounded outcome-feedback loop into a reviewed config/change workflow without auto-tuning live runtime
- [ ] Finn.no API investigation
- [ ] Channel quality metrics
- [ ] On-demand single job analysis
- [ ] Broaden the experiment toolpack from the current bounded shadow/review loop into:
  - connector-policy comparison
  - larger replay datasets
  - reviewed promotion writeback
- [ ] Add applicant-pool scoring on top of the current advantageous-match signal once the person/profile spine is stable
- [ ] Use outcome feedback to tune ranking and review order through reviewed promotion workflows without turning JobSync into a second scoring engine

## Research Backlog

These are important, but should stay as research until the dependency order is clearer.

- **Reactive Resume deep automation**
  - determine whether narrow automation beyond launch/handoff/export capture is stable enough to own without taking on upstream internals
- **Document-workspace deep automation**
  - determine the real editing/storage/export target before committing to browser-driven automation
- **Applicant-pool signal design**
  - identify which competition signals are strong enough to drive ranking without hand-wavy heuristics
- **Structured resume composition seam**
  - determine how far Reactive Resume can support variant/module-level composition directly versus what must live as a JobPipe-owned overlay model
