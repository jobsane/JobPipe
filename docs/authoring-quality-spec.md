# Authoring Quality Spec

Issues: [#132](https://github.com/larsvaerland/Jobpipe/issues/132) · [#133](https://github.com/larsvaerland/Jobpipe/issues/133) · closes [#131](https://github.com/larsvaerland/Jobpipe/issues/131).

This document is the canonical source for:
- Authoring principles (stable, prompt-independent)
- CV quality rubric
- Cover letter quality rubric
- Language routing policy
- Validator contract

The principles section below separates the *what* (product contract) from the *how* (prompt wording). Prompts in `cover_letter_generator.py` may be reworded; these principles must not change without a deliberate product decision.

---

## Authoring principles

These principles are extracted from the prototype prompt and generalised into a stable product contract. They apply regardless of which model, prompt template, or agent generates the document.

### 1. Evidence-first

Every factual claim in a generated document must trace to a named source in `selected_evidence` or `motivation_context`. The system must never invent employers, projects, tools, roles, or outcomes.

*Constraint:* A document that contains a claim with no evidence anchor fails truthfulness. Validators warn when no evidence terms appear in the output.

### 2. Anti-genericness

Generic phrases that could appear in any applicant's letter — buzzwords, clichés, gap apologies, content-free closing phrases — are banned. The banned phrase lists (Norwegian and English) are the implementation of this principle; they extend over time as new patterns emerge.

*Constraint:* Any banned phrase found in output is a blocking failure. The generator retries automatically; validators surface remaining violations.

### 3. Role-fit framing (employer-as-protagonist)

Documents answer the question "what does the employer get?", not "what have I done?". Every paragraph converts candidate experience into employer-facing value. Sentences do not open with "I".

*Constraint:* This is enforced by the system prompt structure (value frame rule). It is not mechanically checkable in the current validator but is part of the cover letter rubric.

### 4. Language discipline

The document language matches the job ad language. Norwegian is the default because it is the primary candidate market. English is used when the job ad is predominantly English. The candidate can override via `language_override`.

*Constraint:* Language routing is deterministic and offline — no model call needed. See the Language routing policy section for the detection algorithm and threshold.

### 5. Truthfulness and gap honesty

Gaps are acknowledged at most once, briefly, and always linked to concrete compensating evidence (study module, project, role transition). The system never minimises or hides gaps, and never inflates qualifications.

*Constraint:* Validators do not currently score gap handling mechanically. This principle is enforced via the system prompt rule ("Gap mentioned at most once, never in the opening, never an apology").

### 6. Prompt wording vs product contract

The system prompts in `cover_letter_generator.py` are implementation details. They may be reworded, translated, or split across model turns. The product contract is this document. Any change to a principle here must be intentional and reviewed; prompt changes that preserve the principles need no separate approval.

---

All deterministic validators must implement these rules exactly. Future agent reviewers must be able to evaluate output against this spec without consulting the code.

---

## Language routing policy

| Condition | Document language |
|---|---|
| `ctx.language_override == "no"` | Norwegian |
| `ctx.language_override == "en"` | English |
| `language_override` is empty | Auto-detected from job ad |
| Auto-detect: ≥ 6% of words are Norwegian function words | Norwegian |
| Auto-detect: < 6% threshold | English |
| Text shorter than 10 words | Norwegian (default) |

**Implementation:** `jobpipe/authoring/language_routing.py` — `detect_job_language()` and `get_document_language()`.

Norwegian function word set used for detection: og, eller, er, av, til, for, med, på, ikke, som, det, de, at, fra, men, om, seg, ved, også, når, under, etter, over, mot, sin, vi, du, din, deg, han, hun, dem, nå, her, der, alle, hvilke, hva, hvem, hvor, hvordan, hvorfor, kan, skal, vil, har, var, bli, blir, ble, søker, stillingen, arbeidsgiveren, kandidaten.

---

## Cover letter quality rubric

### Word count
- Minimum: 150 words (error below this)
- Maximum: 600 words (error above this)
- Target: 300–450 words (3–4 paragraphs)

### Structure
1. **Paragraph 1 — Role and organisational challenge.** Opens with the employer's situation, not "I" or self-introduction. Uses `cover_letter_strategy` or `recruiter_hook`.
2. **Paragraph 2 — Operational evidence.** Names companies, tools, and projects. At least 2 concrete names.
3. **Paragraph 3 — Motivation: why this job, why now.** Uses `narrative_why_me_now` if available; otherwise builds from `motivation_context`.
4. **Paragraph 4 (optional).** Max 2 sentences. Local connection or personal context only if genuinely relevant.

### Value frame (applies to all paragraphs)
- Every point answers "what does the employer get?", not "what have I done?"
- "I" is allowed as grammatical glue mid-sentence, never as an opener
- Each paragraph contains at least one concrete name from `selected_evidence` or `motivation_context`

### Gap rule
- Gaps mentioned at most once, in one sentence, never in the opening paragraph
- Link the gap to something concrete (study module, project, role)
- Never apologise

### What must not appear
- Opener starting with "I" or a self-introduction
- Invented facts (employers, projects, tools not in evidence)
- Grades or academic scores (module names and project names are acceptable)
- Any phrase from the banned phrase lists (see below)

---

## CV quality rubric

### Word count
- Minimum: 100 words (error below this)
- Maximum: 1200 words (error above this)

### Evidence requirement
- Each claimed skill or competency is backed by at least one named employer, project, or tool
- No generic self-descriptions without a concrete anchor

### Tailoring
- CV projection highlights 4–6 items most relevant to the specific job requirements
- Items are drawn from `selected_evidence`, not invented
- Evidence refs list matches the number of highlights

---

## Banned phrase lists

### Norwegian (applies when language = 'no')

These phrases are forbidden in output even when they appear in input evidence or job descriptions.

**Generic clichés:**
- tverrfaglige team / tverrfaglig team / tverrfaglig samarbeid
- kontinuerlig forbedring
- interessenter
- endringsprosesser
- brukervennlige løsninger
- skape verdi / reell verdi
- praktisk og resultatorientert
- motivert for å bidra / spesielt motivert
- cross-functional
- sterk teknisk / sterk forståelse / sterk kommunikator / sterke resultater
- offentlig sektor
- rask tilpasningsevne
- vilje til å bygge
- tverrfaglig koordinering
- brukeren i sentrum / brukerfokus
- helhetlige løsninger

**Weak gap apology patterns:**
- selv om jeg ikke har eksplisitt erfaring
- selv om jeg ikke har direkte erfaring
- selv om jeg mangler direkte erfaring
- selv om jeg mangler eksplisitt erfaring
- rask til å tilpasse meg / raskt å tilpasse meg / raskt tilpasse meg
- bygge nødvendig domenekunnskap / bygge nødvendig kunnskap
- tilegne meg ny domenekunnskap / tilegne meg kunnskap om

**Generic closing variants:**
- robuste og fleksible løsninger
- ser frem til å bidra med min kompetanse
- ser frem til muligheten til å / ser frem til å kunne / ser frem til å bringe / ser frem til å anvende / ser frem til å kombinere
- anvende min kompetanse / bringe min kompetanse
- solid fundament for å bidra
- støtte deres mål om / i deres mål om
- bidra til utviklingen av / bidra til deres
- i en ny kontekst
- en spennende mulighet for meg
- kombinere min praktiske erfaring med / kombinere min erfaring med den strategiske

**Alternatives when expressing the concept:**
- "tverrfaglige team" → name the actual teams: "scrum-teamet hos Brownells", "merkle og møller"
- "kontinuerlig forbedring" → describe what was improved: "reduserte onboarding-tid", "utrulling av Zendesk i 12 markeder"

### English (applies when language = 'en')

**Generic clichés:**
- cross-functional teams
- continuous improvement
- stakeholders
- change management
- user-friendly solutions
- create value / deliver value
- results-oriented
- motivated to contribute
- strong technical skills / strong communication skills / strong understanding
- public sector

**Weak gap apology patterns:**
- although i don't have direct experience
- although i lack direct experience
- quickly adapt to
- build the necessary knowledge
- acquire the necessary knowledge

**Generic closing variants:**
- looking forward to contributing
- looking forward to the opportunity
- looking forward to bringing my skills
- apply my skills / bring my expertise
- solid foundation for contributing
- support your goals
- contribute to the development of
- an exciting opportunity for me
- combine my experience with

---

## Validator contract

### `validate_authoring_context(ctx: AuthoringCaseContext) → DocumentValidationResult`

Validates the authoring input context before generation. Checks:
- Required fields present (candidate_id, job_id, job_summary, decision_brief, selected_evidence)
- decision_brief contains required keys
- selected_evidence is non-empty
- narrative_brief has content if present
- narrative_brief evidence refs resolve to selected_evidence ids

**Module:** `jobpipe/authoring/validation.py`

### `validate_document_content(draft, language, selected_evidence, doc_type) → DocumentValidationResult`

Validates the generated document after generation. Checks:
- Word count within limits for doc_type
- No banned phrases for the given language
- At least one evidence reference appears in the draft (warning only)

**Module:** `jobpipe/authoring/validation.py`

### `DocumentValidationResult` schema

```python
class DocumentValidationResult(BaseModel):
    passed: bool          # True iff failures == []
    score: float          # clamp(1.0 - (errors * 0.2 + warnings * 0.05), 0.0, 1.0)
    failures: list[str]   # blocking errors — prefixed with [rule_name]
    warnings: list[str]   # non-blocking issues — prefixed with [rule_name]
```

The schema is additive: new fields may be added, existing fields must not be renamed or removed.

### Scoring formula

```
score = clamp(1.0 - (n_errors × 0.2 + n_warnings × 0.05), 0.0, 1.0)
```

A document with 0 errors and 0 warnings scores 1.0. Each error costs 0.2; each warning costs 0.05. Score cannot go below 0.0.

---

## Implementation locations

| Contract | File |
|---|---|
| Language detection | `jobpipe/authoring/language_routing.py` |
| Context validator | `jobpipe/authoring/validation.py` — `validate_authoring_context()` |
| Document validator | `jobpipe/authoring/validation.py` — `validate_document_content()` |
| Cover letter generator (wires language) | `jobpipe/authoring/cover_letter_generator.py` |
| `language_override` field | `jobpipe/authoring/case_context.py` — `AuthoringCaseContext.language_override` |
