---
name: handoff-writer
description: Use when a planning or exploration task needs a clean execution handoff in docs/execplans/<task>.md.
allowed-tools: Read Grep Glob Edit Write
---

Write a compact handoff note that another agent can execute from.

Include:
- goal
- why this exists
- scope
- files likely involved
- risks
- tests
- approval needs
- rollback note

Write task-specific handoffs in `docs/execplans/`. Keep them short, concrete, and implementation-ready.
