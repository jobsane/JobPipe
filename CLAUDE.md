# Claude Rules for This Repo

Mission: make the smallest safe change that solves the stated problem.

## Hard rules

- Do not scan the whole repo unless explicitly asked.
- Only inspect files listed in `specs/current-change.md`.
- Do not refactor unrelated code.
- Do not rename files or symbols unless explicitly requested.
- Do not add dependencies unless approved.
- Do not change architecture without documenting why.
- Keep diffs small and reversible.

## Change budget

- Max 3 files changed unless justified
- Max 120 lines touched unless justified
- One logical change per commit
- No feature and refactor in the same change

## Output format

Return only:
1. diagnosis
2. patch summary
3. risks
4. validation steps

## Testing rules

- Add or update a focused test when behavior changes
- If no test is added, explain why
- Prefer narrow validation over broad repo-wide churn

## Protected areas

Be extra careful around:
- pipeline stages
- output structure
- decision logic
- config keys
- report generation
- Gmail integration

## Escalate instead of guessing when

- business rules are unclear
- a change affects pipeline semantics
- a change affects model cost
- a change widens scope beyond the original request
