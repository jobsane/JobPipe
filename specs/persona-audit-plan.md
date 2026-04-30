# Persona Audit Plan

**Last updated:** 2026-04-17

## Purpose

This spec defines the next deep public-OSS audit for JobPipe.

The goal is to verify that the current single-user, local-first product loop is:

- operationally stable
- credible for real local use
- not overfit to one candidate profile
- producing explanations and prioritization that remain coherent across materially different candidate shapes

This is not a multi-user feature spec.

It is a public-quality and generalization audit for a single-user OSS workbench.

---

## Why this is the next step

The current public repo now has the essential substrate in place:

- canonical runtime roots
- canonical intake and cross-source deduplication
- a first public decision layer
- persisted claims, selection assessments, decision tables, evidence, narrative, watchlists, change events, and calibration outputs
- a usable dashboard projection
- a functioning clean-install path against a real local data root

That shifts the next public question from:

- "Can JobPipe run?"

to:

- "Does JobPipe behave credibly for more than one candidate shape?"

The next risk is no longer missing core product direction.

The next risk is silent overfitting to the current reference candidate.

---

## Audit scope

This audit should test four things:

1. onboarding defaults
2. scoring and prioritization behavior
3. explanation quality
4. dashboard usability as a candidate-facing decision surface

It should do that using:

- one live local corpus
- one frozen configuration baseline
- multiple synthetic candidate personas

Persona fixtures are synthetic calibration and regression fixtures.
They exist to test whether JobPipe generalizes beyond one operator profile.
They are not default user data, product assumptions, or evidence that the first four personas cover the market.

---

## Product-line constraint

This audit stays aligned with current product boundaries:

- public JobPipe remains single-user and local-first
- personas are test fixtures, not concurrent user accounts
- there is no public login system in scope
- there is no OSS multi-tenant dashboard in scope

Later private implications are allowed only as boundary notes:

- real multi-user support
- password login
- per-user workspaces
- advisor/admin workflows

Those belong to the later private layer if they are pursued.

---

## Audit inputs

The audit should freeze these inputs before comparison starts:

### 1. Job corpus baseline

One stable corpus from the current live local state:

- canonical jobs in the primary DB
- preserved replay inputs for evaluated jobs
- recent job run events
- current application summary/events
- generated document metadata where relevant

This is the shared market input for all personas.

If a valuable evaluated job is no longer present as a live canonical catalog row, the audit baseline should fall back to the preserved replay input captured from the original evaluated artifact set.

The current runnable implementation should freeze two corpus files locally:

- one full live corpus snapshot
- one small stratified audit slice used for the first runnable matrix

The first runnable matrix should use a bounded slice by default so the public OSS audit stays practical in cost and latency.

Default slice rule:

- `2` jobs from the current actionable bucket
- `2` jobs from the current review bucket
- `2` jobs from the current skip bucket

The full live corpus is still frozen alongside that slice so later deeper audits can expand without redefining the baseline.

### 2. Config baseline

Freeze the current public config used in the audit:

- `configs/pipeline.v1.yaml`
- semantic threshold
- moderation thresholds
- review/apply splits
- any active source filters used in the audit run

Committed live-baseline template:

- `specs/persona-audit-baseline.template.yaml`

### 3. Persona fixtures

Each persona should define:

- profile pack
- resume JSON
- candidate positioning summary
- search constraints
- target roles
- negative signals
- location rules

These should be synthetic and safe to publish.

They should remain intentionally limited:

- useful for initial calibration without personal data
- useful for regression checks after threshold, prompt, decision, or projection changes
- not treated as representative market research
- not used as default profiles for normal users

Committed fixture location:

- `tests/fixtures/personas/manifest.json`
- `tests/fixtures/personas/<persona_id>/profile_pack.md`
- `tests/fixtures/personas/<persona_id>/resume.json`

### 4. Evaluation protocol

For each persona, run the same workflow slice and collect the same outputs:

- decision distribution
- top-ranked actionable roles
- strongest skips
- strongest adjacent/non-obvious matches
- generated evidence selection
- narrative plausibility
- dashboard quality

---

## Persona set

The first matrix should use 4 personas.

That is enough variance to expose overfitting without turning the audit into infrastructure.

### Persona A — Current reference shape

Purpose:

- baseline comparison against the current real design center

Shape:

- senior-ish digital/product/operations profile
- strong cross-functional delivery and platform work
- adjacent-fit across product, transformation, operations, CRM, service, and program roles

### Persona B — Domain-credible but narrower specialist

Purpose:

- test whether JobPipe over-promotes broad management/product roles when the profile is actually specialist-shaped

Shape:

- individual-contributor analytics / operations / systems specialist
- weaker people-leadership signals
- stronger technical or tooling depth

### Persona C — Public-sector transition candidate

Purpose:

- test hiring-aware realism around title continuity, domain continuity, and evidence burden

Shape:

- private-sector background
- plausible public-sector pivot
- stronger process, governance, and program logic than direct public-sector domain history

### Persona D — Early-to-mid career non-obvious but plausible mover

Purpose:

- test whether the system can separate promising adjacent roles from unrealistic stretch roles

Shape:

- lighter seniority
- strong evidence in a narrower role family
- credible but constrained pivot surface

---

## Audit questions

For each persona, answer:

1. Are the top actionable roles actually plausible for this candidate?
2. Are the top skips actually good skips?
3. Are adjacent opportunities surfaced where they should be?
4. Are title/domain continuity penalties too weak or too strong?
5. Are evidence units selected in a way that would support a credible application?
6. Does the narrative layer make the move clearer or noisier?
7. Does calibration behave as a local interpretation layer rather than a hidden override?
8. Does the dashboard remain understandable and trustworthy from the candidate’s point of view?

---

## Audit outputs

The audit should produce one comparable bundle per persona:

- decision summary
- top 20 actionable roles
- top 20 review roles
- top 20 strongest skips worth sanity-checking
- evidence selection examples
- narrative assessment examples
- dashboard screenshots or dashboard notes
- false-positive / false-negative notes

And one roll-up comparison:

- cross-persona decision distribution
- shared failure patterns
- onboarding pain points
- threshold or heuristic issues
- model/data gaps

---

## What to score manually

The first audit should not pretend everything can be measured automatically.

These dimensions should be reviewed manually:

- top-rank plausibility
- skip correctness
- adjacent-role credibility
- evidence usefulness
- narrative plausibility
- dashboard trust/readability

Recommended rating scale:

- `strong`
- `acceptable`
- `weak`
- `broken`

---

## Failure patterns to watch

The audit should explicitly look for:

- Lars-overfitting
- management-title inflation
- public-sector optimism without enough evidence
- specialist undervaluation
- weak handling of constrained geographies
- evidence selection that mirrors keywords without substance
- narrative overreach
- monitoring noise that obscures real change
- calibration summaries that imply false certainty

---

## Expected outcomes

The audit is successful if it produces:

1. a list of real onboarding/default issues
2. a list of real ranking/scoring issues
3. a list of explanation/evidence issues
4. a dashboard usability correction list
5. a clear public/private boundary note for anything that should not be solved in OSS

The first runnable matrix findings now live in:

- `specs/persona-audit-findings-2026-04-17.md`

The audit is not successful if it only produces:

- generic impressions
- "works for me" comments
- visual-only notes detached from decision quality

---

## Public vs private implications

### Public OSS should cover

- single-user persona fixtures
- reproducible audit corpus
- evaluation notes and failure modes
- threshold and heuristic hardening
- better onboarding defaults
- better dashboard trustworthiness

### Later private layer may cover

- real multiple-user workspaces
- login/authentication
- advisor/admin review surfaces
- shared evaluation infrastructure
- proprietary calibration packs
- private comparison datasets

The audit should call out these implications, but not pull the public repo into solving them now.

---

## Execution order

1. Freeze one live corpus and one config baseline.
2. Freeze one small stratified audit slice from that corpus for the first runnable matrix.
3. Create the first four synthetic persona packs.
4. Collect dashboard and decision outputs.
5. Review false positives, false negatives, and explanation quality.
6. Write one hardening report with prioritized fixes.

---

## Acceptance criteria

This audit plan is ready to execute when:

- the persona set is explicit
- the shared corpus and config baseline are explicit
- the review dimensions are explicit
- the public/private boundary is explicit
- the expected outputs are explicit

At that point the next implementation topic can be:

- build the persona fixtures
- freeze the audit corpus
- run the first matrix
