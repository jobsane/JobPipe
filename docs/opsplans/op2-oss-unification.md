# Op 2 — OSS Unification

**Status:** Plan-only. Nothing in this doc has been executed. Every destructive step is gated on explicit founder approval.

**Lane:** Runs in parallel with the authoring-MVP lane (T002). Independent of T001 / PR #90.

**Date:** 2026-04-21

## Problem

`origin/main` (at `b8bc34c`) and the real-codebase lineage used by `codex/job-catalog-foundation` (at `3a5d2ca`, pre-PR #90) share **no common ancestor**. `gh pr create --base main` fails with `GraphQL: The codex/job-catalog-foundation-v2 branch has no history in common with main` for that reason.

This blocks the OSS promise: "one fully functional single-user local codebase, contributable back." Today a contributor cloning `main` does not get the real product.

## Current state (verified 2026-04-21)

- `origin/main` — `b8bc34c feat: redesign public dashboard as decision workbench`. Disconnected from the working lane.
- `origin/codex/job-catalog-foundation` — `3a5d2ca docs: structure ai authoring mvp plan`. The real-codebase integration lane.
- `origin/codex/job-catalog-foundation-v2` — `f4b3062 T001 Slice 1 inspect claim-layer views`. PR #90, in review, targeting `codex/job-catalog-foundation`.
- No other code branch currently uses `main` as a base.

## Target state

- `origin/main` points at the post-PR-#90 head of `codex/job-catalog-foundation`, so a fresh `git clone` yields the real codebase.
- The pre-unification `main` is preserved as an immutable tag for forensic and attribution purposes.
- `docs/integrations/README.md` exists as a shallow pointer at the two existing seam specs, so a first-time cloner finds the external-project story immediately.

## Selected path — Path B (archive + reset)

Archive the current `main` as `refs/tags/oss-main-pre-unify`, then force-update `main` to the post-PR-#90 head of `codex/job-catalog-foundation`.

### Why Path B, not Path A

- **Path A (`git merge --allow-unrelated-histories`)** preserves the old `main` history by welding it to the real codebase. That drags unrelated public-main lineage into a repo whose stated OSS story is "one clean single-user local codebase with documented integrations." It produces a merge commit whose content is misleading — no code was actually merged, the new head wins every file conflict.
- **Path B** loses nothing: the old `main` survives as a permanent tag, and `git log refs/tags/oss-main-pre-unify` remains a full historical read. What's gained is a clean `main` whose `HEAD` actually builds and runs JobPipe.
- Founder confirmed: no paid/multi-user work has been done on the old `main` lineage that would be destroyed. The private lane is effectively already the intended OSS state.

## Slices (approval-gated)

### Slice 1 — **this doc** (completed by publishing)

Plan-only. No repo mutation. Reversible by deleting the file. This is the artifact you are reading.

### Slice 2 — archive tag

```bash
git fetch origin
git tag oss-main-pre-unify b8bc34c -m "Archive of origin/main before OSS unification; see docs/opsplans/op2-oss-unification.md"
git push origin refs/tags/oss-main-pre-unify
```

**Reversible:** yes — deleting a tag on origin is `git push --delete origin oss-main-pre-unify`. No branch state changes.

**Approval required:** low — tag creation is additive.

### Slice 3 — RED GATE: force-update `main`

**Pre-condition:** PR #90 merged into `codex/job-catalog-foundation`. Name the post-merge head `<MERGED_SHA>`.

```bash
git fetch origin
git push origin +<MERGED_SHA>:refs/heads/main
```

**Irreversible in the open-source sense:** external forks and clones already tracking the old `main` will see a diverged upstream on their next fetch. The old commits survive via the archive tag, so nothing is technically lost — but consumers of the old `main` must run `git fetch && git reset --hard origin/main` (or re-clone) to pick up the new lineage.

**Approval required:** explicit founder sign-off after slices 1 and 2. Do not automate. Do not batch with any other push.

**Local-safety posture before executing:** the force-push is scripted with an explicit ref-spec (`+<MERGED_SHA>:refs/heads/main`), never `--force-with-lease` against `HEAD`, so there is no ambiguity about which branch is being rewritten.

### Slice 4 — integrations README

Small docs slice on `claude/<task>-unify-integrations-readme` or an `ops/` branch:

- Create `docs/integrations/README.md` listing reactive-resume, jobsync, and crewAI (planned).
- Each entry: one-paragraph purpose, link to the governing spec (`specs/reactive-resume-integration-seam.md`, `specs/jobsync-integration-seam.md`, `specs/ai-document-authoring-mvp-workflow-2026-04-21.md`), and a "status: integrated / in progress / planned" line.
- No behavior change. Reversible by revert.

## Rollback

If Slice 3 executes and is later regretted:

```bash
git push origin +<OLD_MAIN_SHA_FROM_TAG>:refs/heads/main
# where OLD_MAIN_SHA_FROM_TAG = b8bc34c, preserved in refs/tags/oss-main-pre-unify
```

This reverts `main` to the pre-unification state. External consumers who fetched the intermediate state will need to reset again.

The archive tag must not be deleted until the unification has been stable for a meaningful period (suggested: at least through two subsequent PRs landing on `main` without issue).

## Validation

### After Slice 2

- `git ls-remote --tags origin | grep oss-main-pre-unify` returns the expected sha.
- `git fetch origin && git show refs/tags/oss-main-pre-unify --stat` matches the old `main` tree.

### After Slice 3

- `git ls-remote --heads origin main` returns `<MERGED_SHA>`.
- Fresh clone (`git clone https://github.com/larsvaerland/Jobpipe.git /tmp/jobpipe-clean && cd /tmp/jobpipe-clean && python compile_check.py`) succeeds.
- `jobpipe --help` resolves at the new `main`.
- No open PR against `main` from before the unification is silently retargeted (there shouldn't be any — PR #90 targets `codex/job-catalog-foundation`, not `main`).

### After Slice 4

- `docs/integrations/README.md` renders cleanly on GitHub.
- Each linked spec exists at the listed path on `main`.

## Out of scope

- Renaming branches (`codex/job-catalog-foundation` stays as it is for now; may be revisited in a later hygiene slice).
- Closing or retargeting the old `main`'s open PRs, if any — this plan assumes none exist; verify before Slice 3.
- GitHub repository settings changes (default branch is already `main`; no change).
- Public announcement / changelog entry — out of scope for this initiative; belongs in a release-communication slice if / when OSS traction warrants one.

## Approval status

Slice 1: self-approving (plan-only doc). Slice 2: pending founder go-ahead. Slice 3: pending founder go-ahead, independently, after Slice 2 is visible on origin and PR #90 is merged. Slice 4: can run concurrently with Slice 3 or after.

## Escalation gates still in force

This plan touches the OSS/private boundary (CLAUDE.md escalation list). It does not touch auth, billing, schema, secrets, or runtime data. If the force-push step ever needs to be expanded to rewrite other branches, stop and re-escalate.
