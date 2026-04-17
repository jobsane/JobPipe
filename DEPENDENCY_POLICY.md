# Dependency Policy

## Goal

Use maintained OSS modules for generic infrastructure. Build custom code where the differentiation actually lives.

## Prefer

Prefer dependencies that are:

- actively maintained
- clearly documented
- operationally boring for a solo maintainer
- compatible with local-first use
- permissively licensed

Preferred license families:

- MIT
- BSD
- Apache-2.0
- ISC
- PSF

## Wrap Or Compose

Wrap or compose libraries for:

- LLM orchestration
- connectors
- export/render helpers
- embeddings or model backends

Those dependencies should not define the long-term public identity of the project.

## Build Custom

Build custom code where JobPipe differentiates:

- candidate/job evaluation logic
- structured evidence handling
- decision support semantics
- monitoring and follow-up logic
- privacy-preserving local workflow design

## Avoid

Avoid foundational dependencies that are:

- weakly maintained
- operationally heavy without strong payoff
- viral or commercially awkward from a licensing perspective
- source-available but not actually open

In practice, avoid introducing GPL, AGPL, SSPL, BSL, or no-license dependencies into the core public foundation unless there is a very strong reason.
