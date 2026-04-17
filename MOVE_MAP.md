# Move Map

## Purpose

This document answers the practical question:

- what in the current `JobPipe` repository stays public
- what should only start private in `JobPipe Workbench`
- what can later be split behind a public interface without weakening the OSS repo

This is a move map, not an immediate migration plan. The current public repo remains the canonical working codebase.

## Core Rule

Do not move current public code to private unless one of these is true:

- it becomes clearly proprietary and tuned to business workflow
- it depends on private evaluation or outcome data
- it creates connector or operational exposure that should not live publicly

## Current Public Code: Keep Public

These should remain public in the current codebase.

### Runtime and shared foundations

- `jobpipe/core/config.py`
- `jobpipe/core/io.py`
- `jobpipe/core/runner.py`
- `jobpipe/core/schema.py`

Why:

- generic runtime and data plumbing
- reusable OSS value
- not moat-critical on their own

### Public CLI workflow surfaces

- `jobpipe/cli/run_feed.py`
- `jobpipe/cli/drain_queue.py`
- `jobpipe/cli/sync_ledger.py`
- `jobpipe/cli/export_dashboard.py`
- `jobpipe/cli/mark_status.py`
- `jobpipe/cli/pull_sheets_csv.py`
- `jobpipe/cli/pull_finn_search.py`
- `jobpipe/cli/pull_finn_ext.py`
- `jobpipe/cli/pull_suggested.py`
- `jobpipe/cli/scan_gmail.py`

Why:

- these are the visible OSS workflow surface
- they demonstrate the local-first system credibly
- they are useful to single users and tinkerers without undermining the business

### Public stage logic

- `jobpipe/stages/triage.py`
- `jobpipe/stages/reverse_triage.py`
- `jobpipe/stages/parse.py`
- `jobpipe/stages/profile_match.py`
- `jobpipe/stages/pivot.py`
- `jobpipe/stages/moderate.py`
- `jobpipe/stages/semantic_filter.py`
- `jobpipe/stages/application_pack.py`
- `jobpipe/stages/_common.py`

Why:

- current stage logic is the OSS proof-of-work
- generic staged evaluation is a public strength, not a private moat by itself
- later private workflow can extend this rather than replacing it by secrecy

### Public config and prompt baselines

- `configs/pipeline.v1.yaml`
- `configs/application_pack_prompt.md`

Why:

- baseline prompts and thresholds should stay inspectable
- they are part of the public credibility of the system
- private tuning should come later as overlays or separate policy packs, not by erasing the public baseline

### Public docs and templates

- `reports/dashboard_template.html`
- `docs/*`
- repo-facing planning docs

Why:

- these make the public repo legible and usable

## Current Public Code: Keep Public, But Prepare Interfaces

These should stay public now, but later private layers may depend on them through stable contracts or extension points.

### `jobpipe/stages/application_pack.py`

Keep public:

- current generic application-pack generation

Later private additions:

- tuned product workflow around evidence selection
- proprietary narrative refinement logic
- business-specific packaging of candidate outputs

### `jobpipe/cli/scan_gmail.py`

Keep public:

- baseline Gmail status and suggestion handling

Possible later private layer:

- sensitive connector variants
- private classification heuristics tied to internal workflow
- product-specific monitoring behavior

### `configs/pipeline.v1.yaml`

Keep public:

- baseline thresholds and model routing

Possible later private layer:

- tuned policy packs
- private calibration overlays
- market- or workflow-specific decision packs

## Future Private Work: Start In JobPipe Workbench

These should begin in the private repo rather than in the public repo.

### Policy packs

Private home:

- `policy_packs/`

Examples:

- tuned decision and prioritization policies
- higher-trust workflow defaults
- product-specific heuristics for ranking and follow-up

### Calibration layers

Private home:

- `calibration/`

Examples:

- private calibration rules
- internal outcome-pattern logic
- tuned adjustments based on private evaluation datasets

### Sensitive connectors

Private home:

- `private_connectors/`

Examples:

- brittle or compliance-sensitive connector implementations
- source integrations that create operational exposure
- anything not appropriate as a public maintenance burden

### Business workflow orchestration

Private home:

- future workbench workflow modules

Examples:

- premium workflow packaging
- commercial user flow logic
- private operational orchestration that does not improve the OSS foundation directly

### Internal experiments and evaluation

Private home:

- `experiments/`

Examples:

- proprietary benchmark corpora
- candidate-specific evaluation experiments
- internal tuning and product-quality tests

## What Should Not Move

Do not move these private just to protect the business:

- generic utility code
- public CLI surfaces
- baseline stage implementations
- public docs and templates
- inspectable threshold/config baselines

If something is generic and useful, it should remain public.

## Practical Next Rule

When new work is added:

- if it improves the generic local-first foundation, add it to `JobPipe`
- if it is tuned, proprietary, or commercially sensitive, add it to `JobPipe Workbench`
- if it spans both, keep the interface public and the tuned implementation private
