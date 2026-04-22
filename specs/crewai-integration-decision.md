# crewAI Integration Decision

**Date:** 2026-04-22  
**Status:** Decision recorded — spike closed  
**Author:** Coordinator (Lars + Claude orchestrator session)  
**Related issues:** #86 (crewAI spike), Sprint 3 scoping

---

## Why this document exists

This document captures everything established in the crewAI investigation spike so that neither Lars nor any agent needs to re-litigate these decisions. It records the full reasoning, findings, constraints, and architectural decisions as stable reference for Sprint 3 planning and all future implementation work.

---

## The question we were answering

JobPipe Sprint 2 shipped `SimpleAgentAuthor` (using the `openai-agents` SDK) behind the `AuthorAdapter` Protocol. The question was whether to replace or supplement that with crewAI, and whether crewAI + MCP is the right path for the full loop (multi-agent authoring, real-time editing, Reactive Resume integration).

---

## Strategic reasoning for crewAI (Lars's reasoning, recorded)

Two forces pull toward crewAI:

**1. Vendor agnosticism**  
`openai-agents` SDK is OpenAI-specific. It aims to monetize its ecosystem and steers toward OpenAI's product vision. JobPipe needs to route candidate data through GDPR-compliant EU/local models (Norwegian market, `Personopplysningsloven`). crewAI uses LiteLLM as its model routing layer — any model, any provider, same agent logic. This is the right long-term position for a product that will mature as the AI scene matures.

**2. Modular connector-style architecture**  
crewAI treats agents and tools as pluggable connectors. This matches the product vision: JobPipe should be a modular system where new capabilities (evidence lookup, resume editing, cover-letter critique, ATS validation) can be added as agent tools without rewiring the core. crewAI's `@tool` decorator and `MCPServerAdapter` are the natural fit.

**The goal right now:**  
Make the job hunt usable end-to-end. Lars needs a job. The authoring loop (evidence → CV → cover letter → apply) has to work. crewAI + MCP is the path that gets there while building toward the right long-term architecture.

---

## What LiteLLM is (recorded for future agents)

LiteLLM is a model-routing library built into crewAI 1.x. It presents a unified OpenAI-compatible interface in front of all major providers: OpenAI, Anthropic, Azure, Mistral, Ollama, Cohere, Bedrock, and others. crewAI agents call LiteLLM; LiteLLM calls whichever model is configured. This means:

- The agent code does not change when you switch models.
- GDPR-sensitive data can be routed to EU-hosted or local models without changing agent logic.
- Cost and latency can be optimised per-task (cheap model for routing, expensive model for synthesis).
- crewAI does not require OpenAI. It works with Claude, Mistral, local Ollama, or anything LiteLLM supports.

This is what makes crewAI vendor-agnostic in practice.

---

## What crewAI + MCP means together

crewAI 1.14.2 ships `mcp~=1.26.0` as a first-class dependency. This is not an add-on — it is bundled. crewAI agents can consume MCP tool servers directly via `MCPServerAdapter`. This means:

- A `jobpipe-mcp-server` that exposes evidence units, decision briefs, narrative profiles, and job claims as MCP tools becomes immediately consumable by crewAI agents.
- Claude in Word (via Microsoft's MCP connector) can also consume the same `jobpipe-mcp-server` for real-time document co-piloting.
- The MCP server is the canonical context bridge — it does not duplicate JobPipe state, it surfaces it.

crewAI + MCP is a single path, not two separate integrations.

---

## crewAI vs openai-agents: functional difference

| Capability | openai-agents 0.6.4 | crewAI 1.14.2 |
|---|---|---|
| Model support | OpenAI only | Any model via LiteLLM |
| Multi-agent orchestration | Handoff pattern (linear) | Crew + Process (sequential, hierarchical, parallel) |
| MCP support | External, add-on | Bundled (`mcp~=1.26.0`) |
| Memory / persistence | Not included | Built-in (short/long term, entity memory) |
| Tool definition | `@function_tool` decorator | `@tool` decorator + `MCPServerAdapter` |
| Vendor lock-in | Hard OpenAI dependency | None — LiteLLM routes to any provider |
| Python 3.14 support | Works (pure Python) | Blocked (see below) |

---

## Installation findings: Python version constraint

### The constraint

crewAI 1.14.2 declares `python>=3.10,<3.14`. JobPipe currently runs on Python 3.14.0 (`C:\Python314\python.exe`).

Bypassing the version ceiling with `--ignore-requires-python` resolves the crewAI package itself, but fails at `pydantic-core 2.33.2`. pydantic-core compiles a Rust extension via pyo3 0.24.1, which hard-caps at Python 3.13:

```
error: the configured Python interpreter version (3.14) is newer than PyO3's maximum supported version (3.13)
```

Setting `PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1` does not resolve this — maturin's subprocess does not honour the env var in this context. This is a hard blocker on Python 3.14, not a version ceiling that can be bypassed.

### The resolution

**Python 3.12** is already installed on Lars's machine as the default `python` command (`C:\Users\larsv\AppData\Local\Programs\Python\Python312\python.exe`, Python 3.12.5). crewAI 1.14.2 supports Python 3.10–3.13. Python 3.12 is the correct install target.

This is not a compromise — it is the right architecture anyway (see isolation rule below).

### Expected install command (Python 3.12 target)

```cmd
python -m pip install crewai
```

Where `python` resolves to Python 3.12.5. No `--ignore-requires-python` needed.

---

## Architectural decision: strict isolation

### The rule

**crewAI is an external runtime, not a JobPipe dependency.**

JobPipe does not `import crewai`. crewAI does not import JobPipe internals. The boundary is enforced at the `AuthorAdapter` Protocol seam (see below). Both projects will mature quickly as the AI scene evolves. The seam must stay thin enough that either side can be upgraded or replaced without touching the other.

### Why this matters

crewAI's dependency surface is large (chromadb, lancedb, grpcio, kubernetes client, opentelemetry stack). These are runtime infrastructure concerns that have nothing to do with JobPipe's candidate decision semantics. Pulling them into JobPipe's core would bloat the install, create conflict risk, and blur the public OSS boundary.

crewAI also evolves fast. A strict seam means JobPipe does not need to track crewAI's internal API changes.

### What "separate" means in practice

- crewAI runs in its own Python environment (Python 3.12 venv or separate install).
- JobPipe communicates with crewAI via the `AuthorAdapter` Protocol — a one-method interface over frozen dataclasses.
- crewAI receives context as a serialised JSON payload derived from `AuthoringCaseContext`. It does not receive raw JobPipe objects.
- crewAI returns a `GeneratedApplicationPackage`-compatible JSON payload. JobPipe deserialises it.
- No crewAI import appears in any file under `jobpipe/`.
- crewAI lives under a separate module tree: `jobpipe_crewai/` or as a completely separate package.

---

## The integration seam

### `AuthorAdapter` Protocol (already exists, Slice 7)

```python
# jobpipe/authoring/adapter.py
from typing import Protocol, runtime_checkable
from jobpipe.authoring.case_context import AuthoringCaseContext
from jobpipe.authoring.output_models import GeneratedApplicationPackage

@runtime_checkable
class AuthorAdapter(Protocol):
    def generate(self, ctx: AuthoringCaseContext) -> GeneratedApplicationPackage: ...
```

This is the only seam. `CrewAIAuthor` implements this Protocol identically to `SimpleAgentAuthor`. From JobPipe's perspective, they are interchangeable.

### What crosses the seam (inbound to crewAI)

`AuthoringCaseContext` serialised as JSON:
- `candidate_id`, `job_id`, `evaluation_id`
- `job_summary` — job title, company, description, required skills
- `decision_brief` — match score, key claims, selection rationale
- `selected_evidence` — evidence units (role, bullets, dates, tags)
- `narrative_brief` — tone, positioning, voice constraints
- `artifact_plan` — section order, suppression rules, rewrite constraints

crewAI receives this as a structured JSON string. It does not receive the Python objects.

### What crosses the seam (outbound from crewAI)

`GeneratedApplicationPackage`-compatible JSON:
- `job_id`
- `cover_letter_draft` — string
- `tailored_cv_projection` — dict (section plan, bullets, headline)
- `evidence_refs` — list of evidence unit IDs used
- `gap_notes` — list of identified gaps
- `validation` — optional validation result dict

JobPipe deserialises this into `GeneratedApplicationPackage`. Provenance stays in JobPipe.

### What crewAI must NOT receive

- Raw `job_claims`, `job_selection_signals`, `job_decision_tables`
- JobPipe SQLite connection or schema
- Any mutable JobPipe state
- Canonical evidence selection logic (that stays in `jobpipe/decision/`)

---

## The MCP server seam (future)

A `jobpipe-mcp-server` will surface JobPipe context as MCP tools. This enables:

1. **crewAI agents** consuming it via `MCPServerAdapter` to look up evidence, check claims, query the decision brief in real time during generation.
2. **Claude in Word** (via Microsoft's MCP connector) consuming the same server for real-time document co-piloting while Lars edits a CV or cover letter.

The MCP server exposes read-only tools only. It does not write to JobPipe state. Write-back flows through the existing `persist_generated_package` path.

Candidate tools to expose:
- `get_evidence_units(job_id)` — returns selected evidence for a given job
- `get_decision_brief(job_id)` — returns match score, claims, rationale
- `get_narrative_brief(candidate_id)` — returns tone/voice constraints
- `get_job_summary(job_id)` — returns job metadata

This server is Sprint 3+ work. It should be a standalone FastAPI/Starlette MCP server, not embedded in `jobpipe/`.

---

## The full loop vision (recorded for Sprint 3 scoping)

The intended full loop, in order:

```
jobpipe author-package --job <id>
  -> AuthoringCaseContext (JobPipe)
  -> CrewAIAuthor.generate(ctx)
      -> Author agent: draft CV projection + cover letter
      -> Critic agent: validate against evidence + claims
      -> Revision loop (bounded, 1-2 passes)
  -> GeneratedApplicationPackage (JSON, back to JobPipe)
  -> persist_generated_package (JobPipe DB)
  -> Reactive Resume: optional editor/renderer surface
      -> user edits in RR UI
      -> Claude in Word: real-time co-pilot via jobpipe-mcp-server
  -> final document refs saved to JobPipe case
  -> JobSync: status tracking
```

This is not Sprint 3 scope in full. Sprint 3 should deliver the `CrewAIAuthor` adapter and a working author+critic crew. The MCP server and RR integration follow after the authoring loop is stable.

---

## Reactive Resume role (unchanged from seam spec)

Reactive Resume remains an optional editor/renderer surface. It does not own:
- evidence selection
- claim targeting
- section ordering strategy
- narrative constraints
- tailoring decision logic

It receives a `tailored_cv_projection` and renders it. The real-time editing vision (Lars editing in RR while chatting with an agent) is powered by the `jobpipe-mcp-server` — the agent reads from JobPipe context, not from the RR editor state.

See `specs/reactive-resume-integration-seam.md` for the full RR boundary spec.

---

## Claude in Word

Microsoft's MCP connector already enables Claude to co-pilot Word documents. This means the "real-time editing with an agent that remembers" use case for cover letters is already partially available for Word. The missing piece is the `jobpipe-mcp-server` giving Claude access to the candidate's evidence and job context during that session.

This is not a new product to build — it is a context bridge (the MCP server) connecting an already-working Microsoft integration to JobPipe's data.

---

## Installation path forward

1. **Create isolated Python 3.12 environment for crewAI work:**
   ```cmd
   python -m venv C:\Users\larsv\envs\crewai-env
   C:\Users\larsv\envs\crewai-env\Scripts\activate
   pip install crewai
   ```
   (`python` resolves to 3.12.5 — no flags needed.)

2. **Smoke test:**
   ```python
   import crewai; print(crewai.__version__)
   from crewai import Agent, Task, Crew, Process
   from crewai_tools import MCPServerAdapter
   from mcp import ClientSession
   print("OK")
   ```

3. **crewAI module location:** `jobpipe_crewai/` (sibling package, separate repo or top-level directory), NOT inside `jobpipe/`.

4. **JobPipe imports:** `jobpipe` imports only `AuthorAdapter` Protocol and `GeneratedApplicationPackage` + `AuthoringCaseContext` frozen dataclasses. No crewAI.

5. **Python version:** JobPipe continues on Python 3.14. crewAI runs on Python 3.12. They communicate via the JSON seam, not shared interpreter state. If a subprocess call is needed, it is a clean JSON-in / JSON-out subprocess — or the adapter runs in the 3.12 env and JobPipe calls it via a thin HTTP/subprocess bridge.

---

## What does NOT change in JobPipe

- `AuthorAdapter` Protocol — already correct
- `AuthoringCaseContext` — already correct
- `GeneratedApplicationPackage` — already correct  
- `persist_generated_package` — already correct
- `jobpipe author-package` CLI — already correct
- Canonical decision logic in `jobpipe/decision/` — untouched
- Evidence selection policy — untouched
- `specs/canonical-data-model.md`, `specs/controlled-cv-tailoring.md` — untouched

The seam already exists. Sprint 3 adds `CrewAIAuthor` on the other side of it.

---

## Open risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| crewAI 1.x API changes break `CrewAIAuthor` | Medium | Isolated module, version-pinned, easy to swap |
| Python 3.14 support for crewAI (pydantic-core / pyo3) | Will resolve when pyo3 updates beyond 3.13 ceiling | Monitor; not blocking since crewAI is isolated |
| subprocess/HTTP bridge latency between 3.14 and 3.12 envs | Low for authoring batch use | Acceptable; cover letter gen is not latency-critical |
| Reactive Resume API instability | Low (self-hosted fork) | Thin seam, JSON only, no deep coupling |

---

## GitHub Project #6 items

- **#86** — Spike: crewAI/AutoGen/LangChain evaluation → **DONE**. Decision: crewAI 1.14.2, isolated env, Python 3.12. AutoGen/LangChain rejected.
- **Sprint 3 new items** (to be created): `CrewAIAuthor` adapter, author+critic crew, `jobpipe-mcp-server` spike.

---

## Decision summary (one paragraph)

crewAI 1.14.2 is the right framework for JobPipe's authoring layer: vendor-agnostic via LiteLLM, MCP-native, modular by design. It cannot run on Python 3.14 due to pydantic-core's pyo3 Rust extension ceiling, but this is not a blocker — crewAI must be isolated in its own Python 3.12 environment anyway. The boundary is the `AuthorAdapter` Protocol: one method, JSON in, JSON out. JobPipe never imports crewAI. crewAI never imports JobPipe internals. Both will evolve independently. The `jobpipe-mcp-server` is the context bridge that enables crewAI agents (and Claude in Word) to read candidate evidence and decision context at runtime without coupling to JobPipe's internals.
