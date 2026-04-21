---
name: pr-summary
description: Use when implementation is complete and a concise summary of the diff, tests, and follow-up is needed.
allowed-tools: Read Grep Glob Bash(git status) Bash(git diff *) Bash(git log *)
---

Summarize the current changes for a pull request or handoff.

Include:
- what changed
- why it changed
- key files
- tests run
- remaining risks
- follow-up items

Prefer facts from the diff and test output over speculation. Durable decisions go in `docs/decisions.md`; live state changes go in `docs/current-state.json`.
