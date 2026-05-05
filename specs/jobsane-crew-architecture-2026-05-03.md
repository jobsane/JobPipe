# Jobsane Sub-Crew Architecture

Date: 2026-05-03

## Purpose

This spec defines the intended CrewAI sub-crew architecture for AI-assisted job application authoring.
It sits downstream of `specs/ai-document-authoring-mvp-workflow-2026-04-21.md` and is the agent
runtime layer that Option C reserves: deterministic contracts and validation stay JobPipe-native;
crewAI enters only inside the author/revise agent layer.

The goal is to produce high-quality, natural-sounding application materials (tailored CV, cover
letter, screening question answers, interview prep) grounded in JobPipe's canonical candidate state,
with the candidate reviewing and editing outputs before anything is submitted.

---

## Dependencies

This spec cannot be implemented until:

1. **T002 Sprint 1 complete** — `AuthoringCaseContext`, `GeneratedApplicationPackage`, and
   `DocumentValidationResult` contracts exist in `jobpipe/model/`
2. **CrewAI dependency review** (#86) — security and dependency audit before adoption
3. **Reactive Resume seam** — `tailored_cv_plan` and `record-reactive-resume-document` CLI working
4. **JobSync seam** — `export-jobsync` and `record-jobsync-event` CLI working

---

## Design Principles

1. JobPipe remains the system of record. Crews receive data from JobPipe and write results back
   through the existing seams. No canonical state lives in a crew output directly.
2. Crews are transient processors. They receive the minimum data needed, do work, return structured
   results. They do not own state between runs.
3. Data sovereignty over local compute. Cloud LLM APIs are acceptable. The value is that all
   candidate data, triage results, and generated artifacts are owned by the candidate and live in
   JobPipe's local state — not in any cloud platform.
4. Contracts are agent-runtime-swappable. The input/output contracts must not couple to CrewAI
   primitives. If a better agent framework appears, the contracts survive the swap.
5. The candidate reviews everything. No material is submitted without passing through the candidate's
   editor. Crews produce drafts; the candidate approves finals.
6. Sub-crews are independently replaceable. Each crew is a separate unit. A better CV crew can
   replace the CV crew without touching the cover letter crew.

---

## Non-Goals

- No mass auto-apply.
- No freeform document generation that bypasses evidence provenance.
- No canonical state moving into crew outputs or cloud services.
- No deep coupling between sibling repos (jobsane, jobsync, Reactive Resume internals).
- No single monolithic crew doing everything — specialisation is intentional.

---

## Trigger

The candidate reviews the curated job shortlist in jobsync and clicks **Apply**.

jobsync fires:

```
jobpipe trigger-authoring JOB_ID
```

JobPipe assembles `AuthoringCaseContext` from its canonical state and hands it to the crew flow.

---

## Architecture Overview

```
jobsync "Apply" click
  → jobpipe trigger-authoring JOB_ID
  → AuthoringCaseContext (assembled by JobPipe from canonical state)
  ↓
[Ground Layer Crew]
  → ground_layer bundle
  ↓
  ┌─────────────────────────────┐
  │  CV Tailoring Crew          │  → Reactive Resume JSON → candidate review in RR GUI
  └─────────────────────────────┘
  ↓ (after candidate approves CV)
  ┌─────────────────────────────┐
  │  Cover Letter Crew          │  → rich text → candidate review in jobsync editor
  └─────────────────────────────┘
  ↓ (if screening questions present)
  ┌─────────────────────────────┐
  │  Screening Questions Crew   │  → structured Q&A → candidate review in jobsync editor
  └─────────────────────────────┘
  ↓ (after application submitted)
  ┌─────────────────────────────┐
  │  Interview Prep Crew        │  → prep materials → jobsync
  └─────────────────────────────┘
```

All outputs write back to JobPipe via existing seams:
- CV: `jobpipe record-reactive-resume-document`
- Cover letter, screening answers, interview prep: `jobpipe record-jobsync-event` /
  `document_ref_event`

---

## Ground Layer Crew

**Purpose:** Assemble a rich, enriched context bundle from all available signals. Runs once per
application trigger. All downstream crews consume this bundle — it is never reassembled per crew.

**Source repos:** tonykipkemboi/resume-optimization-crew pattern + jobsane's Serper integration

### Agents

**Job Analyzer**
- Input: raw job ad (URL or text) + `AuthoringCaseContext` from JobPipe
- Does: parses the ad, maps stated requirements against Jobpipe's triage signals (claims,
  selection signals, decision brief, gap analysis), identifies what the ad emphasises vs. what
  JobPipe already assessed
- Output: `job_analysis` (structured — requirements, emphasis, named gaps, match score)

**Company Researcher**
- Input: employer name + job context
- Does: Serper search — recent news, LinkedIn presence, strategic direction, stated culture,
  known pain points, hiring signals, team/department context
- Output: `company_brief` (what to reference beyond the job ad to address a real need or focus)

### Ground Layer Output Bundle

```python
@dataclass(frozen=True)
class GroundLayer:
    authoring_context: AuthoringCaseContext   # from JobPipe
    job_analysis: dict                         # Job Analyzer output
    company_brief: dict                        # Company Researcher output
    match_score: float                         # visible in jobsync pre-apply
    named_gaps: list[str]                      # visible in jobsync pre-apply
```

`match_score` and `named_gaps` should be surfaced in jobsync before the candidate clicks Apply —
so the decision to apply is informed by what the gap actually is.

---

## CV Tailoring Crew

**Purpose:** Produce a tailored CV grounded in evidence, targeted at this specific job and company.

**Source repo:** jobsane (unikill066/smart-agentic-ats-resume) — remapped

### Agents

**Personal Profiler**
- Input: `ground_layer.authoring_context` (evidence units, narrative profile, claims)
- Does: maps candidate strengths against job and company context; identifies what to
  foreground, suppress, and emphasise
- Note: reads from AuthoringCaseContext only — does not scrape GitHub or external sources

**Resume Strategist**
- Input: Personal Profiler output + full `ground_layer`
- Does: produces the tailored CV targeting Reactive Resume JSON schema; applies evidence
  selection, section ordering, claim targeting, and rewrite constraints from
  `tailored_cv_plan` contract
- Output: Reactive Resume JSON patch + `tailored_cv_projection`

### Output

- `tailored_cv_projection` → `jobpipe export-reactive-resume-plan JOB_ID`
- Rendered in Reactive Resume GUI for candidate review and editing
- Final saved via `jobpipe record-reactive-resume-document JOB_ID`

---

## Cover Letter Crew

**Purpose:** Produce a natural-sounding, company-specific cover letter that echoes the CV's
evidence and addresses a real company need or focus. Candidate reviews and edits before use.

**Source repo:** loglux/AIJobMate — adapted (CV Writer → Cover Letter Writer, QA Reviewer kept)

### Agents

**Cover Letter Writer**
- Input: full `ground_layer` + finalised `tailored_cv_projection` (must reflect approved CV,
  not a draft — letter and CV must agree)
- Does: writes the cover letter grounded in the company brief (references a specific initiative,
  need, or cultural signal) and the candidate's narrative motivation brief; natural language
  quality is the primary goal
- Model: strongest available (Claude Sonnet or GPT-4o) — this is where quality matters most

**QA Reviewer**
- Input: Cover Letter Writer draft + `ground_layer`
- Does: checks for — generic phrases, missing company reference, weak opening, claims not
  echoed in CV evidence, unnatural language, length
- Output: pass/fail + named issues
- If failed: Cover Letter Writer reruns with QA feedback before presenting to candidate

### Output

- Rich text (markdown) → jobsync Tiptap editor for candidate review and editing
- Final saved via `jobpipe record-jobsync-event JOB_ID` + `document_ref_event`

---

## Screening Questions Crew

**Purpose:** Produce tailored answers to screening questions grounded in the same evidence base.
Triggered only when the application requires screening answers rather than (or in addition to)
a cover letter.

### Agents

**Question Analyzer**
- Input: screening questions (text) + `ground_layer`
- Does: maps each question to the most relevant evidence units, claims, and company signals

**Answer Strategist**
- Input: Question Analyzer output + `ground_layer`
- Does: writes answers grounded in specific evidence; each answer references real experience
  units, not generic claims; natural sounding

### Output

- Structured Q&A → jobsync editor for candidate review and editing
- Final saved via `document_ref_event`

---

## Interview Prep Crew

**Purpose:** Produce interview preparation materials after the application is submitted.
Triggered by a jobsync status event (e.g. `interview_scheduled`).

**Source:** jobsane's Interview Preparer agent — extracted and extended

### Agents

**Interview Preparer**
- Input: full `ground_layer` + submitted CV + submitted cover letter
- Does: likely questions (technical and behavioural), company-specific angles from
  `company_brief`, talking points grounded in evidence units, gap mitigation angles
- Output: structured prep document → jobsync

---

## Flow Orchestration

The sub-crews are orchestrated by a CrewAI `Flow` — the same pattern already in use in JobVibe
(`LocalCodingFlow`, `VibeCodingFlow`).

```
@start       → Ground Layer Crew
@listen(GL)  → CV Tailoring Crew
@listen(CV_APPROVED) → Cover Letter Crew  [triggered by candidate save in RR]
@listen(GL)  → Screening Questions Crew   [parallel with CV if questions present]
@listen(APPLICATION_SUBMITTED) → Interview Prep Crew
```

The flow must not advance CV → Cover Letter until the candidate has approved the CV in Reactive
Resume. The `record-reactive-resume-document` write-back is the approval signal.

---

## Model Routing

| Crew / Agent | Recommended model | Reason |
|---|---|---|
| Job Analyzer | GPT-4o mini or Claude Haiku | Structured parsing, not prose |
| Company Researcher | GPT-4o mini | Web results summarisation |
| Personal Profiler | GPT-4o mini or Claude Haiku | Structured mapping |
| Resume Strategist | Claude Sonnet or GPT-4o | Quality matters |
| Cover Letter Writer | Claude Sonnet (primary) | Natural language quality is critical |
| QA Reviewer | Claude Haiku or GPT-4o mini | Checking, not generating |
| Answer Strategist | Claude Sonnet | Quality matters |
| Interview Preparer | GPT-4o mini or Claude Haiku | Bullet points, not prose |

Per-agent model selection must be configurable — not hardcoded. This is the pattern from
AIJobMate that should be preserved.

---

## Data Sovereignty

Cloud LLM API calls are acceptable. The principle is:

- All canonical state lives in JobPipe (local SQLite/files)
- Crew outputs are derived artifacts, not source of truth
- LLM APIs receive data transiently for inference — they do not store candidate state
- Use Anthropic and OpenAI API tiers with training data opt-out confirmed
- No crew output permanently lives in a cloud service the candidate does not control

---

## Source Repo Mapping

| Sub-crew | Base repo | Key adaptations needed |
|---|---|---|
| Ground Layer | tonykipkemboi/resume-optimization-crew + jobsane Serper | Split into two agents; output as `GroundLayer` dataclass |
| CV Tailoring | unikill066/smart-agentic-ats-resume (jobsane) | Remove Serper from Researcher; remap to read AuthoringCaseContext; output Reactive Resume JSON |
| Cover Letter | loglux/AIJobMate | Swap Gradio for CLI; swap Ollama for configurable model; wire to ground_layer input |
| Screening Questions | New — thin crew | No external base; pattern from Answer Strategist concept |
| Interview Prep | jobsane Interview Preparer | Extract as standalone crew; extend with company_brief input |

---

## Relationship to Existing Specs

This spec sits above:

- `specs/ai-document-authoring-mvp-workflow-2026-04-21.md` — governing authoring contracts
- `specs/reactive-resume-integration-seam.md` — CV output surface
- `specs/jobsync-integration-seam.md` — cover letter / screening / status output surface
- `specs/controlled-cv-tailoring.md` — CV tailoring constraints
- `specs/candidate-narrative-model.md` — narrative profile input
- `specs/job-claims-model.md` — claims input

Crews are consumers of the contracts defined in those specs. They must not redefine or bypass them.

---

## First Implementation Slice

After T002 Sprint 1 completes and CrewAI dependency review (#86) passes:

1. Ground Layer Crew — Job Analyzer + Company Researcher; outputs `ground_layer` bundle
2. `match_score` and `named_gaps` surfaced in jobsync before Apply
3. CV Tailoring Crew — wired to consume `AuthoringCaseContext`; outputs Reactive Resume JSON
4. Cover Letter Crew — wired to receive finalised CV projection; QA Reviewer included
5. Flow orchestration — GL → CV → Cover Letter sequence with candidate approval gate

Screening Questions and Interview Prep crews are follow-on slices.

---

## Success Criteria

This architecture is successful if:

1. Clicking Apply in jobsync triggers a crew run that produces a tailored CV in Reactive Resume
   and a cover letter in jobsync without the candidate assembling any data manually
2. The cover letter references something specific from the company brief — not a template
3. CV and cover letter agree on the evidence they cite
4. The candidate can edit both in their respective UIs and save finals back to JobPipe
5. All canonical state remains in JobPipe after the run
6. Any sub-crew can be replaced without affecting the others

It fails if:

- Canonical tailoring logic drifts into crew prompts rather than JobPipe contracts
- Crew outputs become the source of truth rather than derived artifacts
- The letter sounds generic or does not reference the specific company context
- The flow advances without candidate approval of the CV
