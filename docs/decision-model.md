# Decision Model

## Objective

The decision model exists to:

- eliminate obvious noise cheaply
- reserve deeper evaluation for plausible jobs
- produce final decisions that can be inspected and tuned

## Stage order

The current configured stage order is:

1. `triage`
2. `parse`
3. `profile_match`
4. `pivot`
5. `moderate`
6. `application_pack`

`reverse_triage` remains available in the codebase but is currently disabled in `configs/pipeline.v1.yaml`.

## Cheap filters

Before the deeper model steps matter, JobPipe applies several low-cost filters:

- geo filter
- hard-no title regex
- semantic filter
- safety overrides around target titles and positive signals

These are intentionally earlier than the heavier scoring stages.

## Final decision tiers

Current thresholds from `configs/pipeline.v1.yaml`:

| Decision | Threshold |
|---|---|
| `APPLY_STRONGLY` | `fit_score >= 78` |
| `APPLY` | `fit_score >= 67` |
| `REVIEW_HIGH` | `fit_score >= 58` |
| `REVIEW_LOW` | `fit_score >= 30` |
| `SKIP` | `fit_score < 30` or earlier filter stop |

Other important thresholds:

- semantic filter threshold: `0.30`
- hard review floor: `review_min_fit = 30`
- review-high split: `review_high_min_fit = 58`

## Interpretation

The important point is not that the numbers are universally correct. The point is that:

- the thresholds are explicit
- they are easy to inspect
- they can be tuned against observed outcomes

## Reviewability

Every job leaves behind enough state to understand:

- which filter or stage stopped it
- what the fit and pivot scores were
- why the final decision tier was assigned

This is why JobPipe uses deterministic moderation after model-assisted evaluation.

## Where to change it

Edit:

- `configs/pipeline.v1.yaml`

Then validate with:

- targeted tests where available
- `compile_check.py`
- `.\go.ps1 -DryRun`
