# Live Paths

This file lists the active runtime paths that matter for code changes.

It is not a backlog doc. It is a "what actually runs" map.

Read this together with:

- [docs/architecture.md](architecture.md)
- [jobpipe/cli/main.py](../jobpipe/cli/main.py)

## 1. Canonical operator path

The canonical operator entrypoint is:

```text
python -m jobpipe.cli.main ...
```

Primary commands are registered in:

- [jobpipe/cli/main.py](../jobpipe/cli/main.py)

The `run` command remains the normal orchestration path for the single-user loop.

## 2. Main runtime flow

```mermaid
flowchart TD
    A["Source intake<br/>pull_sheets / pull_finn_* / scan_gmail / pull_suggested"] --> B["run_feed"]
    B --> C["Per-job stage artifacts"]
    C --> D["sync_evaluations"]
    D --> E["Primary SQLite DB"]
    E --> F["jobpipe.projections.dashboard"]
    E --> G["Other projections / exports"]
```

## 3. Evaluation path

Current default stage order from [configs/pipeline.v1.yaml](../configs/pipeline.v1.yaml):

1. `triage`
2. `parse`
3. `profile_match`
4. `pivot`
5. `moderate`
6. `application_pack`

`reverse_triage` is still a supported optional stage in the runtime model, but
it is disabled in the current default config path.

Stage modules live under:

- [jobpipe/stages](../jobpipe/stages)

Current stage-builder wiring lives in:

- [jobpipe/stages/pipeline.py](../jobpipe/stages/pipeline.py)

Important rule:

- `stages/` is the live execution path
- `decision/` is the intended canonical home for durable decision semantics
- `runtime/` must not import `stages/`

## 4. Decision-state promotion path

```mermaid
flowchart TD
    A["Stage outputs + job input"] --> B["jobpipe.decision.* derivation"]
    B --> C["jobpipe.cli.sync_evaluations"]
    C --> D["Primary DB promoted rows"]
    D --> E["dashboard / exports / follow-up surfaces"]
```

Key owner modules:

- [jobpipe/decision](../jobpipe/decision)
- [jobpipe/cli/sync_evaluations.py](../jobpipe/cli/sync_evaluations.py)
- [jobpipe/core/primary_db.py](../jobpipe/core/primary_db.py)

## 5. Projection path

```mermaid
flowchart TD
    A["Primary DB"] --> B["jobpipe.projections.dashboard"]
    A --> C["jobpipe.projections.jobsync"]
    A --> D["jobpipe.projections.reactive_resume"]
    B --> E["CLI export wrappers"]
    C --> E
    D --> E
```

Key rule:

- projections consume canonical state
- projections should not become alternate sources of truth

## 6. Connector path

Mail/Gmail provider logic is extracted under:

- [jobpipe/connectors/mail](../jobpipe/connectors/mail)

Operational orchestration still enters through:

- [jobpipe/cli/scan_gmail.py](../jobpipe/cli/scan_gmail.py)

Key rule:

- connector code normalizes provider data
- candidate/job meaning belongs elsewhere

## 7. Runtime boundary path

```mermaid
flowchart TD
    A["Repo code"] --> B["jobpipe.runtime.paths"]
    B --> C["JOBPIPE_DATA_DIR roots"]
    C --> D["db/"]
    C --> E["artifacts/"]
    C --> F["exports/"]
    C --> G["documents/"]
    C --> H["cache/"]
    C --> I["secrets/"]
```

Key owner modules:

- [jobpipe/runtime/paths.py](../jobpipe/runtime/paths.py)
- [jobpipe/runtime/catalog.py](../jobpipe/runtime/catalog.py)

## 8. Known drift / caution zones

These paths are live but easy to mis-edit:

- `jobpipe/core/`
- `jobpipe/stages/`
- `jobpipe/cli/`

Before changing them, answer:

1. Is this the active path?
2. Is this also the canonical owner?
3. If not, should the fix land in the owner package and the live path stay thin?
