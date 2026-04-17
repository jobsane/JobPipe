# OSS Scope

## What The Public Repo Is For

The public JobPipe repository should become a real OSS-first foundation for local-first, evidence-backed job-search decision workflows.

It should be useful even without any later commercial layer.

## What Belongs In Public

- core local-first workflow code
- generic ingestion and normalization logic
- evaluation and projection tooling that is useful on its own
- public docs and examples
- safe contributor-facing extension surfaces
- privacy-respecting local runtime behavior

## What Does Not Need To Be Public Later

If a later private/commercial layer is built, it can own:

- premium workflow packaging
- tuned policy packs
- sensitive or brittle connectors
- proprietary calibration logic
- commercial UX and product packaging

That future layer does not belong in this public repo today.

## Public Boundary Rule

This repository must not become crippleware.

The public side should stand on its own. The commercial edge, if it exists later, should come from execution quality, tuned workflows, and product packaging, not from making the OSS layer intentionally weak.
