# CrewAI Flow + Crew Architecture for JobPipe

**Date:** 2026-04-22  
**Status:** Sprint 3 planning — approved for implementation  
**Governs:** `jobpipe_crewai/flow.py`, `jobpipe_crewai/state.py`  
**Related:** `specs/crewai-integration-decision.md`, GitHub issue #114

---

## Core principle

CrewAI Flows provide deterministic event-driven orchestration. CrewAI Crews provide
autonomous multi-agent collaboration. JobPipe uses both: the Flow wraps the existing
Python pipeline stages with proper state, routing, and checkpointing; the Crew handles
the one step where autonomous collaboration adds real value — authoring.

Everything that is pure logic (routing, filtering, persistence, export) stays as Python
inside `@listen` / `@router` methods. The LLM is only called where it has to be:
triage (existing single-LLM stage, unchanged) and authoring (Author + Critic crew).

---

## Flow diagram

```
JobPipeFlow(Flow[JobPipeState])
│
├── @start()
│   intake_step(job_id)
│   └── Load job dict from primary DB
│
├── @router(intake_step)
│   route_by_source()
│   └── suggested_by_platform=True  → "direct"    (bypass semantic filter)
│       suggested_by_platform=False → "filter"
│
├── @listen("filter")
│   semantic_filter_step()
│   └── Calls existing jobpipe.stages.semantic_filter
│       score < threshold → state.decision = "SKIP", return "skip"
│       score >= threshold → return "triage"
│
├── @listen(or_("direct", "triage"))
│   triage_step()
│   └── Calls existing jobpipe.stages.triage (unchanged, single LLM call)
│       Sets state.decision, state.score, state.decision_brief
│
├── @router(triage_step)
│   route_decision()
│   └── APPLY_STRONGLY | APPLY → "apply"
│       REVIEW             → "queue"
│       SKIP | *           → "done"
│
├── @listen("apply")
│   build_context_step()
│   └── Calls build_authoring_case_context() → state.authoring_context
│
├── @listen("apply")
│   author_crew_step()                    ★ THE CREW
│   └── build_authoring_crew(state.authoring_context, model)
│       Author Agent → draft cover letter + CV projection
│       Critic Agent → validate claims, flag gaps, suggest fixes
│       Sets state.package
│
├── @listen("apply")
│   persist_step()
│   └── persist_generated_package(conn, state.package, ...)
│       Sets state.document_id
│
├── @listen("apply")
│   export_step()
│   └── Export to JobSync (existing export stage)
│       Sets state.exported = True
│
└── @listen(or_("queue", "done", "skip"))
    finalize_step()
    └── Update job status in DB, log outcome
```

---

## State model

```python
# jobpipe_crewai/state.py
from pydantic import BaseModel, Field

class JobPipeState(BaseModel):
    # Input
    job_id: str = ""
    job_data: dict = Field(default_factory=dict)
    suggested_by_platform: bool = False

    # Triage
    semantic_score: float = 0.0
    decision: str = ""          # APPLY_STRONGLY | APPLY | REVIEW | SKIP
    score: float = 0.0
    decision_brief: dict = Field(default_factory=dict)

    # Authoring
    authoring_context: dict = Field(default_factory=dict)
    package: dict = Field(default_factory=dict)

    # Persistence
    document_id: str = ""
    exported: bool = False

    # Audit
    errors: list[str] = Field(default_factory=list)
```

---

## Flow skeleton

```python
# jobpipe_crewai/flow.py
from crewai.flow.flow import Flow, listen, router, start, or_
from jobpipe_crewai.state import JobPipeState
from jobpipe_crewai.crew import build_authoring_crew

class JobPipeOrchestrationFlow(Flow[JobPipeState]):

    def __init__(self, job_id: str, model: str = "gpt-4o-mini"):
        super().__init__()
        self.state.job_id = job_id
        self._model = model

    @start()
    def intake_step(self):
        from jobpipe.core.primary_db import get_primary_db_conn
        conn = get_primary_db_conn()
        row = conn.execute(
            "SELECT * FROM jobs WHERE job_id = ?", (self.state.job_id,)
        ).fetchone()
        conn.close()
        if not row:
            self.state.errors.append(f"job_id {self.state.job_id} not found")
            return "done"
        self.state.job_data = dict(row)
        self.state.suggested_by_platform = bool(
            self.state.job_data.get("suggested_by_platform", False)
        )

    @router(intake_step)
    def route_by_source(self):
        if self.state.errors:
            return "done"
        return "direct" if self.state.suggested_by_platform else "filter"

    @listen("filter")
    def semantic_filter_step(self):
        from jobpipe.stages.semantic_filter import build_semantic_filter
        sf = build_semantic_filter()
        score = sf.score(self.state.job_data)
        self.state.semantic_score = score
        # threshold from config; 0.0 disables filter (calibration in progress)

    @router(semantic_filter_step)
    def route_after_filter(self):
        from jobpipe.core.config import load_config
        cfg = load_config()
        threshold = cfg.get("semantic_filter_threshold", 0.0)
        if threshold > 0.0 and self.state.semantic_score < threshold:
            self.state.decision = "SKIP"
            return "done"
        return "triage"

    @listen(or_("direct", "triage"))
    def triage_step(self):
        from jobpipe.stages.triage import run_triage
        result = run_triage(self.state.job_data)
        self.state.decision = result.decision
        self.state.score = result.score
        self.state.decision_brief = result.decision_brief or {}

    @router(triage_step)
    def route_decision(self):
        if self.state.decision in ("APPLY_STRONGLY", "APPLY"):
            return "apply"
        if self.state.decision == "REVIEW":
            return "queue"
        return "done"

    @listen("apply")
    def build_context_step(self):
        from jobpipe.authoring.builder import build_authoring_case_context
        ctx = build_authoring_case_context(self.state.job_id)
        try:
            self.state.authoring_context = ctx.model_dump()
        except AttributeError:
            import dataclasses
            self.state.authoring_context = dataclasses.asdict(ctx)

    @listen("apply")
    def author_crew_step(self):
        crew = build_authoring_crew(self.state.authoring_context, self._model)
        result = crew.kickoff()
        import json
        raw = str(result) if result else ""
        try:
            self.state.package = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            self.state.package = {"cover_letter_draft": raw}
            self.state.errors.append("author crew output was not valid JSON")

    @listen("apply")
    def persist_step(self):
        from jobpipe.authoring.output_models import GeneratedApplicationPackage
        from jobpipe.authoring.persist import persist_generated_package
        from jobpipe.core.primary_db import get_primary_db_conn
        pkg = GeneratedApplicationPackage(**self.state.package,
                                          job_id=self.state.job_id)
        conn = get_primary_db_conn()
        self.state.document_id = persist_generated_package(
            conn, pkg,
            candidate_id=self.state.authoring_context.get("candidate_id", "default"),
        )
        conn.commit()
        conn.close()

    @listen(or_("queue", "done"))
    def finalize_step(self):
        from jobpipe.core.primary_db import get_primary_db_conn
        conn = get_primary_db_conn()
        conn.execute(
            "UPDATE jobs SET status = ? WHERE job_id = ?",
            (self.state.decision.lower(), self.state.job_id),
        )
        conn.commit()
        conn.close()


def run_flow(job_id: str, model: str = "gpt-4o-mini") -> JobPipeState:
    flow = JobPipeOrchestrationFlow(job_id=job_id, model=model)
    flow.kickoff()
    return flow.state
```

---

## What stays unchanged

| Component | Status | Notes |
|---|---|---|
| `jobpipe_crewai/crew.py` | Unchanged | `build_authoring_crew()` plugs directly into `author_crew_step` |
| `jobpipe_crewai/author.py` | Unchanged | `CrewAIAuthor` still valid as `AuthorAdapter` for `author-package` CLI |
| `jobpipe/stages/triage.py` | Unchanged | Called as a function from `triage_step` |
| `jobpipe/stages/semantic_filter.py` | Unchanged | Called as a function from `semantic_filter_step` |
| `jobpipe/authoring/persist.py` | Unchanged | Called from `persist_step` |
| `go.ps1` | Unchanged (for now) | Still valid; Flow is an additional entry point |

---

## What to build (Sprint 3)

| File | Action | Notes |
|---|---|---|
| `jobpipe_crewai/state.py` | CREATE | `JobPipeState(BaseModel)` |
| `jobpipe_crewai/flow.py` | CREATE | `JobPipeOrchestrationFlow` + `run_flow()` |
| `tests_crewai/test_flow.py` | CREATE | Flow tests, all stages monkeypatched |

Python environment requirement: `<=3.13` for crewAI import. Do not run in the
Python 3.14 Codex worktree. Tests in `tests_crewai/` run in the crewAI venv.

---

## Future additions (Sprint 4+)

- `jobpipe_crewai/tools.py` — MCP tools callable by agents: `read_job_evidence`,
  `get_candidate_profile`, `lookup_job_decision` — enables agents to fetch live
  context rather than having it injected as a JSON blob
- `@CrewBase` refactor of `build_authoring_crew` — YAML-configured agents/tasks,
  proper CrewAI project structure under `jobpipe_crewai/config/`
- Narrative crew step — a `NarrativeCrew` before `author_crew_step` that builds
  the candidate's story arc from profile data, passes it to the Author
- Checkpoint resume — `from_checkpoint` parameter on `flow.kickoff()` for retrying
  failed author steps without re-running triage
- LinkedIn intake as a parallel `@start` — multiple intake sources feed the same Flow

---

## Why not a Crew for triage?

The existing `triage.py` stage already uses a single LLM call with structured output
(`TriageOut`). Wrapping it in a Crew would add overhead (agent scaffolding, task
delegation) without adding autonomy — there is no benefit to multiple agents arguing
about whether to apply for a job. The Crew is reserved for authoring because Author
→ Critic is a genuinely adversarial loop: the Critic challenges unsupported claims,
which produces better output than any single-pass LLM call.

---

## Codex environment requirement

Before handing to Codex: confirm Python ≤3.13 venv path and that `crewai>=1.14.2`
is installed. The `tests_crewai/` suite must run against this venv, not the main
Python 3.14 worktree.

Stop gate: if Codex reports Python 3.14 during `python --version`, halt and ask
the coordinator for the correct venv path before proceeding.
