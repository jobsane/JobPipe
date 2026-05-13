# Minimum Profile Fields for Tailoring

Defines the minimum viable profile contract that must be present for the CV tailoring and cover letter authoring crews to produce valid, evidence-grounded output.

> **Draft — requires Lars's review before #13 (profile import) implementation starts.**
> The required/preferred split reflects current code behaviour. Lars should confirm the minimum set matches his actual job-hunt needs.

---

## What Tailoring Currently Reads

From `jobpipe/stages/application_pack.py:_load_resume_context`:

| Source | Fields extracted |
|--------|----------------|
| `resume_json.work[]` | `name`/`company`, `position`, `startDate`, `endDate`, `summary` (≤200 chars), `highlights[]` |
| `resume_json.projects[]` | `name`, `description` (≤200 chars) |
| `resume_json.education[]` | `institution`, `area`, `studyType` |
| `profile_pack_md` | Full markdown — positioning, narrative, evidence claims, constraints |
| `motivation.md` | What Lars wants from the role (values, direction, growth) |
| `constraints.md` | Hard limits (role type, location, company size, culture) |
| `cover_letter_voice.md` | Tone rules, sentence style, what not to write |

---

## Required Fields

If any of these are missing or empty, tailoring must use the fallback path (see below). The crew must not fabricate content to fill gaps.

### `resume_json` (JSON Resume format)

| Field | Why required |
|-------|-------------|
| `work[]` — at least 1 entry | Cannot produce a tailored CV without work history |
| `work[0].position` | Job title is the primary relevance signal |
| `work[0].name` or `work[0].company` | Employer name anchors timeline credibility |
| `work[0].highlights[]` — at least 1 item | Evidence bullets are the tailoring raw material |

### `profile_pack_md`

| Field | Why required |
|-------|-------------|
| Non-empty profile_pack_md | Contains positioning and narrative that scopes every tailoring decision |

---

## Preferred Fields (Tailoring Degrades Without These)

| Source | Field | Degradation if absent |
|--------|-------|-----------------------|
| `resume_json.basics` | `name` | Cover letter salutation falls back to "Candidate" |
| `resume_json.basics` | `headline` | Positioning tagline missing from CV header |
| `resume_json.basics` | `summary` | Professional summary section empty |
| `resume_json.work[]` | `summary` | Crew uses highlights only; context thinner |
| `resume_json.work[]` | `startDate`, `endDate` | Timeline not shown; reduces credibility signal |
| `resume_json.skills[]` | any entry | Skills section absent from tailored CV |
| `resume_json.projects[]` | any entry | Portfolio evidence missing |
| `resume_json.education[]` | any entry | Education section absent |
| `motivation.md` | non-empty | Cover letter motivation paragraph generic |
| `constraints.md` | non-empty | Crew may propose roles that violate hard limits |
| `cover_letter_voice.md` | non-empty | Cover letter uses default tone; may not match Lars's voice |

---

## Fallback Path

When a required field is missing:

1. **Log a structured warning** in the authoring context builder:
   ```json
   {"missing_field": "work[].highlights", "fallback": "using work summary only"}
   ```

2. **Add a `gap_notes` entry** to `GeneratedApplicationPackage`:
   ```json
   {"gap": "no work highlights found", "effect": "tailored CV bullets sparse — add highlights to resume.json"}
   ```

3. **Crew behaviour:**
   - Produce output for all fields that DO have data
   - Note gaps explicitly (do not invent content)
   - Never fabricate experience, dates, highlights, or qualifications

4. **Structural validity rule:** The crew must always produce a structurally valid output even with gaps. A sparse but accurate CV is better than a complete but fabricated one.

---

## Evidence Provenance Rule

Every claim in crew-generated output must cite a source from this contract:

| Claim type | Must cite |
|-----------|-----------|
| Work achievement / highlight | `resume_json.work[i].highlights[j]` |
| Skill claim | `resume_json.skills[k]` or `profile_pack_md` evidence unit |
| Narrative / motivation | `motivation.md` or `profile_pack_md` |
| Education credential | `resume_json.education[m]` |

No crew output may introduce a claim without a traceable source in the profile. This is the "no fake CV claims" guardrail from the North Star.

---

## Import Contract (for #13)

When the profile import from Reactive Resume completes (`jobpipe import-reactive-resume`), it must produce a `candidate_profiles` row where:

- `resume_json` satisfies at least the **required** fields above
- `profile_pack_md` is non-empty
- A validation step reports which preferred fields are missing

The import must not silently store an incomplete profile — it must log the gap report so the candidate knows what to fill before running the tailoring crew.
