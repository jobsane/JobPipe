---
name: narrow-fix
description: Use for tiny, high-confidence code fixes in a dirty repo or stale branch when only a few files should change, unrelated local work must be preserved, and the goal is to avoid broad cleanup or accidental overwrite.
---

1. Check `git status --short` and the current branch before changing code.
2. Identify the exact target files and preserve unrelated local changes.
3. Trace only enough existing behavior to fix the defect. Do not widen scope into cleanup, renames, or speculative hardening.
4. Prefer replayable changes when the branch is stale: isolate the intended diff so it can be moved onto a fresh branch later.
5. Touch only the files needed for the fix. Treat tracked deletions and config churn as suspect unless they are explicitly in scope.
6. Run the smallest relevant targeted test first. If code changed beyond a one-line comment or string, run the repo compile check too.
7. Report exact commands run, files touched, residual risks, and anything intentionally left out.
8. Stop and escalate before resets, destructive deletes, schema changes, auth, billing, deploy, pipeline-semantics changes, or broad model-cost changes.
