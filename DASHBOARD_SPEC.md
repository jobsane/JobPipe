# JobPipe Dashboard Spec

## Role

The dashboard is a projection of local JobPipe state.

It is useful because it reduces review overhead and makes current decisions legible, but it is not the product definition. The product logic should live in data, evaluation, and decision state first. The dashboard is one consumer of that state.

## Current Inputs

The current implementation primarily reads from:

- `reports/ledger.sqlite`
- `reports/application_state.json`
- generated artifacts under `out_runs/`

Those names reflect the current runtime implementation and may evolve later. They are not the product category.

## What The Dashboard Should Emphasize

- what merits attention now
- what has already been reviewed or acted on
- which jobs look strong, borderline, or weak
- what follow-up is needed
- whether the pipeline is behaving credibly

## What The Dashboard Should Not Become

- a generic BI surface
- a recruiter dashboard
- a kitchen-sink control panel
- a substitute for a coherent decision model
