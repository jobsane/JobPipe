# Legacy Merge Plan

## Baseline

- Clean repo: `larsvaerland/Jobpipe`
- Working copy: `C:\Users\larsv\Jobpipe`
- Comparison remote: `legacy = larsvaerland/Job-Hunter-Pilot`
- Current baseline branch: `origin/main`

## Branch reality

- `legacy/main` is just `legacy/v2-triage` merged forward.
- Compare from `legacy/v2-triage`, not from `legacy/main`.
- Divergence is large enough that a branch merge is unsafe:
  - `origin/main...legacy/v2-triage` = `34` commits on public only, `27` on legacy only

## High-level conclusion

Do **not** merge `legacy/v2-triage` wholesale into `origin/main`.

The remaining legacy-only diffs fall into three groups:

1. Private or generated files that must stay out of the public repo
2. Regressions where current `origin/main` is clearly better
3. A small number of helper-script ideas that may be worth re-adding selectively

## Port Now

None as a blind import.

Reason:
- The strongest pipeline work from the legacy branch appears to already be present in current `origin/main`
- The remaining diffs are mostly regressions, private data, or local helper files

## Port Later

These can be reconsidered as small manual ports if they still solve a real problem:

- `run_detailed_report.cmd`
  - Thin wrapper around `python -m jobpipe.cli.sync_ledger --detailed-report --only-non-expired`
  - Useful only as a convenience script

- `run_reports.ps1`
  - Useful if a CSV/JSON shortlist export is still needed outside the dashboard
  - Should be reviewed and probably rebuilt around current ledger/export behavior rather than copied as-is

- `docs/next-steps.md`
  - Only if rewritten to be repo-safe
  - Current legacy version references private workflow files like `AGENT_STATUS.md` and `AUDIT.md`

- `import_check.py`
  - Low value
  - Only worth adding if import validation becomes part of a real smoke-test workflow

## Do Not Port

### Private or local-only data

- `.env`
- `profile_pack.md`
- `reports/resume.json`
- `.jobpipe_tmp/jobs_batch_001_0053.jsonl`
- `reports/.fuse_hidden*`

### Agent memory / local coordination files

- `AGENT_STATUS.md`
- `AUDIT.md`
- `COWORK_PROJECT_INSTRUCTIONS.md`
- `PROJECT_INSTRUCTIONS.md`

### Repo hygiene regressions

- `.gitignore`
  - Legacy branch removes ignores for personal data and local working files

- `profile_pack.example.md`
  - Legacy branch deletes the safe example file and replaces it with a personal profile file

### Documentation regressions

- `README.md`
  - Current public README is the better public-facing baseline

- `PRODUCT_VISION.md`
  - Current public version is more mature and more aligned with the repo as a product-facing project

- Deletions from legacy branch that should not be accepted:
  - `CHANGELOG.md`
  - `CONTRIBUTING.md`
  - `LICENSE`
  - `PRODUCT.md`
  - `ROADMAP.md`
  - `TESTING.md`
  - `docs/architecture.md`
  - `docs/artifacts.md`
  - `docs/cli.md`
  - `docs/configuration.md`
  - `docs/decision-model.md`
  - `docs/profile-pack.md`
  - `specs/current-change.md`

### Code regressions where public main is better

- `jobpipe/cli/run_feed.py`
  - Legacy removes index write protection / recovery behavior

- `jobpipe/cli/mark_status.py`
  - Legacy simplifies the state model and loses multi-stage lifecycle richness

- `jobpipe/cli/export_dashboard.py`
  - Legacy removes richer application-state fields used by the dashboard

- `reports/dashboard_template.html`
  - Legacy simplifies status UX and removes richer milestone/timeline behavior

- `configs/pipeline.v1.yaml`
  - Legacy shortens target-title coverage and weakens the current matching surface

## Working rule for this repo

Use this policy when bringing work over from the legacy repo:

- Start from `origin/main`
- Port manually, file by file
- Prefer current public behavior when there is a conflict
- Never copy private profile/resume/env data into the repo
- Never weaken `.gitignore`
- Never delete public docs unless there is a deliberate replacement already reviewed

## Recommended next execution step

1. Create a work branch from `main`
2. Rebuild only the convenience/reporting scripts you still want
3. Keep candidate data out of git and design a separate data location for profile/resume later
4. After the repo is clean, decide on the next architectural move:
   - local structured data layer first
   - multi-user/server/database work second
