# JobPipe

JobPipe is a candidate-first, hiring-aware, local-first career intelligence workbench.

Plain-language fallback: JobPipe is a job-search decision system. It helps a serious job seeker turn messy listings, candidate evidence, and application history into clearer decisions about what to pursue, how to position it, and what changed since the last review.

This repository is the clean new public baseline for JobPipe. Former worknames are retired and should not be reused.

## What This Repo Is

- The public OSS-first foundation for JobPipe.
- A practical local-first codebase for job ingestion, evaluation, dashboard export, and follow-up tracking.
- The place where the public model, tooling, and workflow foundation should stay understandable and useful on their own.

This repo is not the commercial layer. If a later private product exists, it should build on top of this foundation rather than blur the public boundary.

## Product Thesis

JobPipe is built around:

- structured evidence
- explicit decision support
- living monitoring
- better action

The long-term product mechanism is:

`structured evidence -> explicit decision support -> living monitoring -> better action`

## Current Scope

Today, the codebase provides a working local-first pipeline around:

- importing and normalizing jobs from external sources
- evaluating and scoring jobs against a candidate profile
- generating application-oriented outputs for stronger matches
- syncing results into a local ledger
- projecting the current state into a dashboard
- tracking status updates through manual input and Gmail

The implementation still carries some older runtime names such as `reports/` and `out_runs/`. Those are current implementation details, not the product category or public positioning.

## What JobPipe Is Not

Not in scope for this repo or this phase:

- full recruiter product
- ATS replacement
- mass auto-apply
- broad workflow automation suite
- generic AI copilot
- resume-builder business
- platform breadth for its own sake

## Canonical Planning Docs

Read these first:

1. [MASTER_PLAN.md](/C:/Users/larsv/.codex/worktrees/8b1c/agentic_jobpilot/MASTER_PLAN.md)
2. [PRODUCT_VISION.md](/C:/Users/larsv/.codex/worktrees/8b1c/agentic_jobpilot/PRODUCT_VISION.md)
3. [ROADMAP.md](/C:/Users/larsv/.codex/worktrees/8b1c/agentic_jobpilot/ROADMAP.md)
4. [OSS_SCOPE.md](/C:/Users/larsv/.codex/worktrees/8b1c/agentic_jobpilot/OSS_SCOPE.md)
5. [DEPENDENCY_POLICY.md](/C:/Users/larsv/.codex/worktrees/8b1c/agentic_jobpilot/DEPENDENCY_POLICY.md)
6. [BOUNDARY_MAP.md](/C:/Users/larsv/.codex/worktrees/8b1c/agentic_jobpilot/BOUNDARY_MAP.md)
7. [MOVE_MAP.md](/C:/Users/larsv/.codex/worktrees/8b1c/agentic_jobpilot/MOVE_MAP.md)

Supporting docs:

- [CONTRIBUTING.md](/C:/Users/larsv/.codex/worktrees/8b1c/agentic_jobpilot/CONTRIBUTING.md)
- [TESTING.md](/C:/Users/larsv/.codex/worktrees/8b1c/agentic_jobpilot/TESTING.md)
- [CLAUDE.md](/C:/Users/larsv/.codex/worktrees/8b1c/agentic_jobpilot/CLAUDE.md)
- [docs/architecture.md](/C:/Users/larsv/.codex/worktrees/8b1c/agentic_jobpilot/docs/architecture.md)
- [docs/dashboard.md](/C:/Users/larsv/.codex/worktrees/8b1c/agentic_jobpilot/docs/dashboard.md)

## Current Repo Map

| Path | Role |
|---|---|
| `jobpipe/cli/` | command entrypoints |
| `jobpipe/core/` | current shared runtime logic |
| `jobpipe/stages/` | staged evaluation pipeline |
| `configs/` | prompts, thresholds, and pipeline config |
| `docs/` | repo-facing operational notes |
| `reports/` | current generated outputs and local sidecars |
| `tests/` | automated checks |

## Running The Current Code

```powershell
.\go.ps1
```

Useful direct commands:

```powershell
python -m pytest
python compile_check.py
python -m jobpipe.cli.export_dashboard
python -m jobpipe.cli.scan_gmail --dry-run
```

Optional private policy/config overlays can be applied on top of the public baseline config:

```powershell
python -m jobpipe.cli.run_feed --config .\configs\pipeline.v1.yaml --config-overlay C:\path\to\overlay.yaml
.\go.ps1 -ConfigOverlay C:\path\to\overlay.yaml
```

The baseline stays public. Overlays are the intended seam for later private policy packs.

## Packaging

The package name is `jobpipe`.

If a separate private/commercial layer is introduced later, the naming direction is:

- `JobPipe` = umbrella project and OSS/framework identity
- `JobPipe Workbench` = later private/commercial implementation

The working public/private split is defined in [BOUNDARY_MAP.md](/C:/Users/larsv/.codex/worktrees/8b1c/agentic_jobpilot/BOUNDARY_MAP.md).
The concrete code-placement guidance lives in [MOVE_MAP.md](/C:/Users/larsv/.codex/worktrees/8b1c/agentic_jobpilot/MOVE_MAP.md).

## License

MIT © Lars Værland
