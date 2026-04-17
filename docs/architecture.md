# Architecture Notes

## Current Runtime Shape

The current public JobPipe codebase still reflects a practical pipeline runtime:

- connectors and imports feed normalized job rows into the pipeline
- staged evaluation lives under `jobpipe/stages/`
- shared runtime helpers live under `jobpipe/core/`
- output is synced into local reporting state
- the dashboard is exported from that local state

## Planning Constraint

This repository is not being framed as a generic AI pipeline anymore.

The planning truth is:

- candidate-first
- hiring-aware
- local-first
- privacy-respecting
- evidence-backed

## Boundary Reminder

The dashboard and reports are projections.

The durable product direction should center on better decision state, evidence handling, monitoring, and follow-up rather than on broad UI surface area.
