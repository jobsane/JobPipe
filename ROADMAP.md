# Roadmap

## Current phase

JobPipe is in a consolidation phase:

- the runtime model is being cleaned up around the primary DB
- repo-local noise is being pushed out of the codebase
- docs are being aligned with the actual operating model

The purpose of this phase is to make the system easier to trust, easier to run, and easier to evolve.

## Now

These are the next high-value items for the current single-user, local-first product:

1. Improve application-pack quality so generated material is genuinely useful with minimal editing.
2. Harden daily operation: scheduled runs, source reliability, and clearer failure handling.
3. Improve candidate-state quality: profile, resume, and application history should stay coherent in the primary DB.
4. Keep the dashboard focused on actionability rather than reporting noise.
5. Finish documentation cleanup so public docs, internal specs, and runtime behavior agree.

## Next

After the current cleanup phase, the next product layer should be:

1. stronger multi-source intake
2. better deduplication across source records
3. clearer advantageous-match signals
4. richer dashboard views for expiring jobs, source quality, and generated documents
5. better feedback loops from status and outcome data

## Later

Only after the local-first model is stable:

1. optional Postgres-backed deployment using the same domain model
2. candidate-specific configuration workflows beyond direct file editing
3. broader multi-user support
4. selective embedding and retrieval improvements where they solve a proven problem

## Explicit non-goals for now

- full ATS feature parity
- mass auto-apply
- broad workflow automation beyond the current job-search loop
- premature UI surface for every internal setting
- vector-database-first architecture
