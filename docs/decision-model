# Decision Model

Jobpipe uses a staged decision model.

The goal is simple:
- eliminate obvious noise cheaply
- spend deeper evaluation on stronger candidates
- keep the final outcome understandable

## Flow

1. Free or low-cost filters remove obvious poor matches
2. Deeper model-assisted steps evaluate stronger candidates
3. Deterministic moderation applies final decision tiers

## Current decision tiers

| Decision | Condition |
|---|---|
| `APPLY_STRONGLY` | fit_score >= 78 |
| `APPLY` | fit_score >= 67 |
| `REVIEW_HIGH` | fit_score >= 58 |
| `REVIEW_LOW` | fit_score >= 30 |
| `SKIP` | fit_score < 30 or hard filter triggered |

## Why this approach

This structure exists to:
- reduce unnecessary cost
- improve consistency
- keep logic reviewable
- avoid treating every listing as equally worthy of attention

## Important note

Thresholds are not meant to be treated as magic truth. They are working controls that make the workflow more structured and easier to tune over time.

## Configuration source

Thresholds and related settings live in:

- `configs/pipeline.v1.yaml`

Changes to thresholds should be validated with a dry run or focused testing before being trusted.
