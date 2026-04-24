# Calibration Notes
Empirical tuning observations tied to specific jobs or run baselines. Treat each item as a pointer for the next tuning pass, not a decision.
## Geo
- `geo_postal_regex` covers `0xxx` / `1xxx` / `3xxx` / `4xxx`. Hard block with no exceptions. Reason: personal constraint (kids nearby in Oslo-area). Do not widen without explicit owner approval.
- FINN Chrome Extension capture does not set `postalCode`. Geo filter falls back to `work_county` derived from the `sted` field. Monitor for valid Oslo-area jobs being geo-SKIP'd.
## Title filters
- `hard_no_title_regex` historical block rate on one 500-job baseline: `16 / 500` Γëê 3.2%. Review periodically for new irrelevant patterns (`vaktmester`, `montor` observed).
- Semantic filter threshold currently `0.30` in `configs/pipeline.v1.yaml` (`docs/decision-model.md`). An earlier `0.45` killed 4 real interview-producing jobs scoring `0.33`ΓÇô`0.42`, which is why it was lowered.
## Known-hard edge cases
- Ringnes "Team Lead EDI" (real job offer). Scores `sim:0.33`, reaches the LLM, LLM decides SKIP because EDI/SAP specialist framing does not cleanly signal ownership. Before widening the threshold, consider adding EDI/SAP `teamleder` patterns to `weak_anchor_regex` or `very_strong_positive_regex`.
- TOMRA "Digital Product Manager, CMS" (real interview). Scored below `0.45` historically. Covered today by the `semantic_target_override` signal in `triage.py` ΓÇö a title matching `target_title_regex` bypasses a semantic SKIP.
## Pass-rate / cost baselines
- Pass rate target on a fresh ACTIVE-only feed: `2ΓÇô8%`.
- Token waste rate earlier baseline: `~29%` (borderline). Re-measure after any threshold or regex change.
- Geo + hard-no-title together eliminate ~54% of jobs before any LLM call on one historical sample. Further pre-LLM cost wins are most likely to come from feed-side filtering (NAV `styrk08` / occupation codes) rather than more LLM tiers.
## Candidate-profile watch
- `endringsledelse` as a positive keyword: defer promotion until Lars finishes the BI change-management module (target June 2026). Track whether adding it produces good matches when enabled.
## Application-pack quality
- `cv_highlights` and `cv_experience_refs` must have identical list lengths (enforced by `PACK_INSTRUCTIONS` in `jobpipe/stages/application_pack.py`). No code-level validation yet ΓÇö the LLM occasionally produces mismatched lists. Monitor in production runs; consider a post-stage assert.
## Source-data debt (not yet promoted)
- Apps Script: full 59-column NAV schema is not documented. Occupation codes (`styrk08`, `occ_level1`, `cat_code`, `cat_type`, `cat_name`) could enable pre-AI filtering and cut LLM cost significantly. See `docs/apps-script.md` for the throughput/index/archive items that are already tracked.
- `jobs_state.json` drift: manual edits to the Google Sheet can desync the local state; the pipeline may then skip or re-process jobs. Currently no automatic reconciliation.
## How to use this file
Treat each note as context for the next calibration run. When an item is resolved in code or config, delete it here ΓÇö do not leave `[RESOLVED]` carcasses behind. Architectural direction belongs in `docs/decision-model.md`, not here.
