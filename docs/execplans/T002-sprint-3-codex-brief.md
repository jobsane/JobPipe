# T002 Sprint 3 — Codex Multi-Task Brief

**Written:** 2026-04-22  
**Branch:** `codex/T002-authoring-mvp`  
**Base:** `origin/main` (post-PR-#101, commit e73b001)  
**Governing spec:** `specs/ai-document-authoring-mvp-workflow-2026-04-21.md`  
**Decision record:** `specs/crewai-integration-decision.md`

---

## How to run this brief

Work through Tasks 1, 2, and 3 in order. After each task:

1. Run the validation commands.
2. If all pass: commit with the label below, then proceed to the next task immediately without waiting.
3. If a validation fails: fix it. If you cannot fix it within 2 attempts, stop and report the failure.
4. After Task 3 passes: open one PR covering all commits.

Do not ask for permission between tasks. Do not wait for a response between tasks. Move forward unless a **STOP GATE** is hit.

---

## STOP GATES — halt immediately if any of these occur

- You are about to add `import crewai` (or `from crewai`) anywhere inside `jobpipe/` — **invariant violation**
- `insert_generated_document`, `AuthoringCaseContext`, `GeneratedApplicationPackage`, or `DocumentValidationResult` signatures do not match what is described here — **confirm before proceeding**
- A validation command produces errors you cannot resolve in 2 attempts
- You need to touch a file not listed in the task's file table
- You would need to add `langchain`, `autogen`, or any Supabase import anywhere
- You would need to change the DB schema

When stopped: report what you found, what you tried, and what decision is needed.

---

## Step 0 — Verify prerequisites before writing any code

Run these checks. If any fail, report and stop.

```cmd
cd C:\Users\larsv\Jobpipe-codex-v2
git fetch origin
git reset --hard origin/main
```

Then confirm:

```cmd
git log --oneline -3
```

Expected: tip is `e73b001` (or the current origin/main tip — confirm it includes the T002 Sprint 2 slices).

```cmd
python -m jobpipe.cli.main author-package --help
```

Expected: shows `--job`, `--model`, `--no-persist`, `--validate`.

```cmd
python compile_check.py
```

Expected: passes with 0 errors.

```cmd
dir C:\Users\larsv\envs\crewai-env\Scripts\python.exe
```

Expected: file exists. If it does not exist, **STOP** — the crewAI Python 3.12 env has not been set up yet.

Grep for existing `author_factory.py` and `jobpipe_crewai/` to confirm they do not exist yet:

```cmd
dir jobpipe\authoring\author_factory.py 2>nul || echo NOT FOUND
dir jobpipe_crewai 2>nul || echo NOT FOUND
```

Both should say NOT FOUND. If either exists, read its contents and report before proceeding.

---

## Task 1 — `jobpipe_crewai` module + `CrewAIAuthor` skeleton

**Commit label:** `feat(crewai): CrewAIAuthor skeleton — isolated module, AuthorAdapter seam`

### Files to create

| Path | Action |
|---|---|
| `jobpipe_crewai/__init__.py` | CREATE — empty |
| `jobpipe_crewai/author.py` | CREATE — `CrewAIAuthor` class |
| `jobpipe_crewai/prompts.py` | CREATE — placeholder prompt strings |
| `tests_crewai/__init__.py` | CREATE — empty |
| `tests_crewai/test_crewai_author_skeleton.py` | CREATE — 5 seam tests |

**`jobpipe_crewai/` is a sibling of `jobpipe/` at repo root. It is NOT inside `jobpipe/`.**

No other files may be touched in Task 1.

### `jobpipe_crewai/__init__.py`

Empty file.

### `jobpipe_crewai/prompts.py`

```python
AUTHOR_SYSTEM = (
    "You are an expert CV and cover letter author. "
    "You write evidence-backed, ATS-safe application documents. "
    "You only include claims supported by the provided evidence units."
)

CRITIC_SYSTEM = (
    "You are an application quality critic. "
    "You validate CV and cover letter drafts against provided evidence refs and job claim targets. "
    "You flag unsupported claims, missing evidence, and ATS hygiene issues."
)
```

### `jobpipe_crewai/author.py`

```python
import dataclasses
import json
from typing import TYPE_CHECKING

from jobpipe.authoring.case_context import AuthoringCaseContext
from jobpipe.authoring.output_models import GeneratedApplicationPackage


class CrewAIAuthor:
    """crewAI implementation of AuthorAdapter.

    Isolated module — this file may import crewai freely.
    jobpipe/ must never import this module statically.
    """

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        self._model = model

    def generate(self, ctx: AuthoringCaseContext) -> GeneratedApplicationPackage:
        """Generate a cover letter + CV projection from AuthoringCaseContext.

        Skeleton: returns a structurally valid stub. Real crew wired in Task 3.
        """
        return GeneratedApplicationPackage(
            job_id=ctx.job_id,
            cover_letter_draft="[stub — crewAI crew not yet wired]",
            tailored_cv_projection={},
            evidence_refs=[],
            gap_notes=["CrewAIAuthor skeleton — real crew wired in Sprint 3 Task 3"],
        )
```

### `tests_crewai/test_crewai_author_skeleton.py`

5 tests. Run under the **Python 3.12 crewAI env** (`C:\Users\larsv\envs\crewai-env\Scripts\python.exe`).

```python
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_crewai_author_satisfies_protocol():
    """CrewAIAuthor must satisfy AuthorAdapter Protocol."""
    from jobpipe.authoring.adapter import AuthorAdapter
    from jobpipe_crewai.author import CrewAIAuthor
    assert isinstance(CrewAIAuthor(), AuthorAdapter)


def test_crewai_author_returns_package():
    """generate() must return a GeneratedApplicationPackage."""
    import dataclasses
    from jobpipe.authoring.case_context import AuthoringCaseContext
    from jobpipe.authoring.output_models import GeneratedApplicationPackage
    from jobpipe_crewai.author import CrewAIAuthor

    ctx = AuthoringCaseContext(
        candidate_id="c1",
        job_id="j1",
        evaluation_id=None,
        job_summary={"title": "Engineer"},
        decision_brief={"match_score": 0.8},
        selected_evidence=[],
        narrative_brief=None,
        artifact_plan=None,
    )
    pkg = CrewAIAuthor().generate(ctx)
    assert isinstance(pkg, GeneratedApplicationPackage)
    assert pkg.job_id == "j1"


def test_no_crewai_in_jobpipe():
    """jobpipe/ must never contain 'import crewai' or 'from crewai'."""
    jobpipe_dir = REPO_ROOT / "jobpipe"
    for py_file in jobpipe_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        assert "import crewai" not in content, f"crewai import found in {py_file}"
        assert "from crewai" not in content, f"crewai import found in {py_file}"


def test_no_jobpipe_db_in_crewai():
    """jobpipe_crewai/ must not import jobpipe.core or jobpipe.runtime directly."""
    crewai_dir = REPO_ROOT / "jobpipe_crewai"
    forbidden = ["jobpipe.core", "jobpipe.runtime", "primary_db"]
    for py_file in crewai_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for term in forbidden:
            assert term not in content, f"Forbidden import {term!r} found in {py_file}"


def test_seam_json_roundtrip():
    """AuthoringCaseContext must serialise to JSON and back without error."""
    import dataclasses
    from jobpipe.authoring.case_context import AuthoringCaseContext

    ctx = AuthoringCaseContext(
        candidate_id="c1",
        job_id="j1",
        evaluation_id="e1",
        job_summary={"title": "Engineer"},
        decision_brief={"match_score": 0.8},
        selected_evidence=[{"id": "ev1", "bullets": ["Did X"]}],
        narrative_brief={"tone": "confident"},
        artifact_plan=None,
    )
    serialised = json.dumps(dataclasses.asdict(ctx))
    recovered = json.loads(serialised)
    assert recovered["job_id"] == "j1"
    assert recovered["selected_evidence"][0]["id"] == "ev1"
```

Note: if `AuthoringCaseContext` is a pydantic model rather than a dataclass, replace `dataclasses.asdict(ctx)` with `ctx.model_dump()`. Check the actual class definition before writing the test.

### Task 1 validation commands

```cmd
REM Run under the crewAI Python 3.12 env
C:\Users\larsv\envs\crewai-env\Scripts\python.exe -m pytest tests_crewai/test_crewai_author_skeleton.py -v

REM Run under the main Python 3.14 env (just the import check)
python compile_check.py
```

All 5 tests must pass. `compile_check.py` must pass.

### Task 1 commit

```cmd
git add jobpipe_crewai/ tests_crewai/
git commit -m "feat(crewai): CrewAIAuthor skeleton — isolated module, AuthorAdapter seam"
```

**Proceed immediately to Task 2.**

---

## Task 2 — Author factory + `--author` CLI flag

**Commit label:** `feat(authoring): AuthorAdapter factory + --author flag`

### Files to create / touch

| Path | Action |
|---|---|
| `jobpipe/authoring/author_factory.py` | CREATE — `build_author(name, model)` |
| `jobpipe/authoring/author_cli.py` | MODIFY — add `--author` argument |
| `tests/test_author_factory.py` | CREATE — 5 factory tests |

No other files may be touched in Task 2.

### `jobpipe/authoring/author_factory.py`

```python
"""Factory for AuthorAdapter implementations.

Uses importlib for the crewai branch so that jobpipe/ never statically
imports crewai. The crewai module is loaded only when --author crewai is
requested.
"""
import importlib

from jobpipe.authoring.adapter import AuthorAdapter


def build_author(name: str = "simple", model: str = "gpt-4o-mini") -> AuthorAdapter:
    """Return the named AuthorAdapter implementation.

    Args:
        name: "simple" (default) or "crewai"
        model: model string passed to the author constructor

    Returns:
        An object satisfying the AuthorAdapter Protocol.

    Raises:
        ValueError: if name is not recognised.
        ImportError: if name == "crewai" and jobpipe_crewai is not installed.
    """
    if name == "simple":
        from jobpipe.authoring.simple_agent_author import SimpleAgentAuthor
        return SimpleAgentAuthor(model=model)
    elif name == "crewai":
        mod = importlib.import_module("jobpipe_crewai.author")
        return mod.CrewAIAuthor(model=model)
    else:
        raise ValueError(
            f"Unknown author {name!r}. Valid values: 'simple', 'crewai'"
        )
```

### `jobpipe/authoring/author_cli.py` modification

Add `--author` argument to `add_arguments`:

```python
p.add_argument(
    "--author",
    default="simple",
    choices=["simple", "crewai"],
    help="Author implementation to use (default: simple)",
)
```

Replace the `SimpleAgentAuthor(model=args.model)` instantiation line with:

```python
from jobpipe.authoring.author_factory import build_author
author = build_author(name=args.author, model=args.model)
```

### `tests/test_author_factory.py`

5 tests. Run under the **main Python 3.14 env** (standard pytest suite).

```python
import pytest
from jobpipe.authoring.adapter import AuthorAdapter
from jobpipe.authoring.author_factory import build_author
from jobpipe.authoring.simple_agent_author import SimpleAgentAuthor


def test_factory_returns_simple_by_default():
    author = build_author()
    assert isinstance(author, SimpleAgentAuthor)


def test_factory_simple_explicit():
    author = build_author("simple")
    assert isinstance(author, SimpleAgentAuthor)


def test_factory_simple_satisfies_protocol():
    author = build_author("simple")
    assert isinstance(author, AuthorAdapter)


def test_factory_unknown_raises():
    with pytest.raises(ValueError, match="Unknown author"):
        build_author("nonsense")


def test_factory_no_static_crewai_import():
    """author_factory.py must not contain a static crewai import."""
    from pathlib import Path
    factory_src = (
        Path(__file__).resolve().parent.parent
        / "jobpipe" / "authoring" / "author_factory.py"
    ).read_text(encoding="utf-8")
    assert "import crewai" not in factory_src
    assert "from crewai" not in factory_src
```

Note: do NOT add a test for `build_author("crewai")` in the Python 3.14 suite — that import chain requires the Python 3.12 crewAI env. The crewai factory path is tested via `tests_crewai/` only.

### Task 2 validation commands

```cmd
REM Main Python 3.14 suite
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_author_factory.py tests/test_author_cli.py -v -p no:debugging -p no:cacheprovider --basetemp .pytest-tmp

REM Verify --author appears in --help
python -m jobpipe.cli.main author-package --help

REM compile check
python compile_check.py
```

All 5 factory tests must pass. All existing 5 `test_author_cli.py` tests must still pass (no regression). `--help` must show `--author`. `compile_check.py` must pass.

### Task 2 commit

```cmd
git add jobpipe/authoring/author_factory.py jobpipe/authoring/author_cli.py tests/test_author_factory.py
git commit -m "feat(authoring): AuthorAdapter factory + --author flag"
```

**Proceed immediately to Task 3.**

---

## Task 3 — Real 2-agent Author/Critic crew

**Commit label:** `feat(crewai): author+critic crew — 2 agents, bounded revision loop`

### Files to create / touch

| Path | Action |
|---|---|
| `jobpipe_crewai/crew.py` | CREATE — crew factory function |
| `jobpipe_crewai/author.py` | MODIFY — wire real crew in `generate()` |
| `jobpipe_crewai/prompts.py` | MODIFY — add author + critic task prompts |
| `tests_crewai/test_crewai_crew.py` | CREATE — 5 crew unit tests |

No other files may be touched in Task 3.

### `jobpipe_crewai/crew.py`

```python
"""crewAI crew factory for the author/critic authoring loop."""
import json
from crewai import Agent, Crew, Process, Task
from jobpipe_crewai.prompts import (
    AUTHOR_SYSTEM,
    CRITIC_SYSTEM,
    AUTHOR_TASK_TEMPLATE,
    CRITIC_TASK_TEMPLATE,
)


def build_authoring_crew(payload: dict, model: str) -> Crew:
    """Build a 2-agent sequential crew for one authoring case.

    Args:
        payload: serialised AuthoringCaseContext dict
        model: LiteLLM-compatible model string (e.g. "gpt-4o-mini")

    Returns:
        A configured crewAI Crew ready to kickoff().
    """
    author_agent = Agent(
        role="CV and Cover Letter Author",
        goal=(
            "Draft a tailored CV projection and cover letter from the provided "
            "candidate evidence and job context. Only include claims supported "
            "by the evidence units."
        ),
        backstory=AUTHOR_SYSTEM,
        llm=model,
        verbose=False,
        max_iter=2,
    )

    critic_agent = Agent(
        role="Application Quality Critic",
        goal=(
            "Validate the draft against provided evidence refs and job claim targets. "
            "Flag unsupported claims, missing evidence, ATS hygiene issues, and tone problems."
        ),
        backstory=CRITIC_SYSTEM,
        llm=model,
        verbose=False,
        max_iter=2,
    )

    context_str = json.dumps(payload, indent=2)

    author_task = Task(
        description=AUTHOR_TASK_TEMPLATE.format(context=context_str),
        expected_output=(
            "A JSON object with keys: cover_letter_draft (string), "
            "tailored_cv_projection (dict with keys: headline, summary_text, sections), "
            "evidence_refs (list of evidence unit id strings used), "
            "gap_notes (list of strings for any gaps or missing evidence)."
        ),
        agent=author_agent,
    )

    critic_task = Task(
        description=CRITIC_TASK_TEMPLATE.format(context=context_str),
        expected_output=(
            "A JSON object with keys: passed (bool), issues (list of strings), "
            "suggestions (list of strings). If passed is true, issues may be empty."
        ),
        agent=critic_agent,
        context=[author_task],
    )

    return Crew(
        agents=[author_agent, critic_agent],
        tasks=[author_task, critic_task],
        process=Process.sequential,
        verbose=False,
    )
```

### `jobpipe_crewai/prompts.py` additions

Append to the existing file:

```python
AUTHOR_TASK_TEMPLATE = """
You are writing a job application for the following case. Use ONLY the evidence
units provided in the context. Do not invent experience or skills.

Context:
{context}

Produce a JSON object with:
- cover_letter_draft: a 3-paragraph cover letter (plain text, no markdown)
- tailored_cv_projection: dict with keys headline (str), summary_text (str), sections (list of dicts with role/bullets)
- evidence_refs: list of evidence unit IDs you used
- gap_notes: list of any gaps between job requirements and available evidence
"""

CRITIC_TASK_TEMPLATE = """
Review the cover letter and CV projection produced by the Author agent.
Check them against the job context and evidence units below.

Context:
{context}

Produce a JSON object with:
- passed: true if the draft is acceptable, false if significant issues exist
- issues: list of specific problems (unsupported claims, missing evidence, ATS issues)
- suggestions: list of concrete improvements
"""
```

### `jobpipe_crewai/author.py` — wire real crew

Replace the `generate()` stub with:

```python
import dataclasses
import json
from jobpipe.authoring.case_context import AuthoringCaseContext
from jobpipe.authoring.output_models import GeneratedApplicationPackage
from jobpipe_crewai.crew import build_authoring_crew


class CrewAIAuthor:
    def __init__(self, model: str = "gpt-4o-mini") -> None:
        self._model = model

    def generate(self, ctx: AuthoringCaseContext) -> GeneratedApplicationPackage:
        # Serialise context — do not pass Python objects across the seam
        try:
            payload = ctx.model_dump()           # pydantic
        except AttributeError:
            payload = dataclasses.asdict(ctx)    # dataclass fallback

        crew = build_authoring_crew(payload, self._model)
        result = crew.kickoff()

        # Parse crew output — be defensive, crew output may not be clean JSON
        raw = str(result) if result else ""
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            # Crew returned prose — treat as cover letter draft, note the parse failure
            return GeneratedApplicationPackage(
                job_id=ctx.job_id,
                cover_letter_draft=raw,
                tailored_cv_projection={},
                evidence_refs=[],
                gap_notes=["crewAI output was not valid JSON — raw text returned"],
            )

        return GeneratedApplicationPackage(
            job_id=ctx.job_id,
            cover_letter_draft=parsed.get("cover_letter_draft", raw),
            tailored_cv_projection=parsed.get("tailored_cv_projection", {}),
            evidence_refs=parsed.get("evidence_refs", []),
            gap_notes=parsed.get("gap_notes", []),
        )
```

### `tests_crewai/test_crewai_crew.py`

5 tests. All monkeypatched — no real LLM calls. Run under Python 3.12 crewAI env.

```python
import json
import dataclasses
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _make_ctx():
    from jobpipe.authoring.case_context import AuthoringCaseContext
    return AuthoringCaseContext(
        candidate_id="c1",
        job_id="j1",
        evaluation_id="e1",
        job_summary={"title": "Engineer", "company": "Acme"},
        decision_brief={"match_score": 0.85, "claim_targets": ["Python", "APIs"]},
        selected_evidence=[{"id": "ev1", "role": "Backend Engineer", "bullets": ["Built APIs"]}],
        narrative_brief={"tone": "confident"},
        artifact_plan=None,
    )


def test_crew_has_two_agents():
    from jobpipe_crewai.crew import build_authoring_crew
    ctx = _make_ctx()
    try:
        payload = ctx.model_dump()
    except AttributeError:
        payload = dataclasses.asdict(ctx)
    crew = build_authoring_crew(payload, "gpt-4o-mini")
    assert len(crew.agents) == 2


def test_crew_has_two_tasks():
    from jobpipe_crewai.crew import build_authoring_crew
    ctx = _make_ctx()
    try:
        payload = ctx.model_dump()
    except AttributeError:
        payload = dataclasses.asdict(ctx)
    crew = build_authoring_crew(payload, "gpt-4o-mini")
    assert len(crew.tasks) == 2


def test_crew_output_parses_to_package():
    from jobpipe_crewai.author import CrewAIAuthor
    from jobpipe.authoring.output_models import GeneratedApplicationPackage

    fake_output = json.dumps({
        "cover_letter_draft": "Dear Hiring Manager, ...",
        "tailored_cv_projection": {"headline": "Backend Engineer", "summary_text": "...", "sections": []},
        "evidence_refs": ["ev1"],
        "gap_notes": [],
    })

    with patch("jobpipe_crewai.author.build_authoring_crew") as mock_build:
        mock_crew = MagicMock()
        mock_crew.kickoff.return_value = fake_output
        mock_build.return_value = mock_crew

        pkg = CrewAIAuthor().generate(_make_ctx())

    assert isinstance(pkg, GeneratedApplicationPackage)
    assert pkg.cover_letter_draft == "Dear Hiring Manager, ..."
    assert pkg.evidence_refs == ["ev1"]


def test_crew_handles_non_json_output():
    """If crew returns prose instead of JSON, it should not raise."""
    from jobpipe_crewai.author import CrewAIAuthor
    from jobpipe.authoring.output_models import GeneratedApplicationPackage

    with patch("jobpipe_crewai.author.build_authoring_crew") as mock_build:
        mock_crew = MagicMock()
        mock_crew.kickoff.return_value = "Here is your cover letter. Dear Hiring Manager..."
        mock_build.return_value = mock_crew

        pkg = CrewAIAuthor().generate(_make_ctx())

    assert isinstance(pkg, GeneratedApplicationPackage)
    assert len(pkg.cover_letter_draft) > 0
    assert any("not valid JSON" in note for note in pkg.gap_notes)


def test_no_langchain_in_crewai_module():
    crewai_dir = REPO_ROOT / "jobpipe_crewai"
    for py_file in crewai_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        assert "langchain" not in content, f"langchain found in {py_file}"
        assert "autogen" not in content, f"autogen found in {py_file}"
```

### Task 3 validation commands

```cmd
REM All crewai tests (Tasks 1 + 3)
C:\Users\larsv\envs\crewai-env\Scripts\python.exe -m pytest tests_crewai/ -v

REM Main suite regression check (Tasks 1 + 2)
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_author_factory.py tests/test_author_cli.py -v -p no:debugging -p no:cacheprovider --basetemp .pytest-tmp

REM compile check
python compile_check.py
```

All 10 `tests_crewai/` tests must pass. All 10 main-suite tests must pass. `compile_check.py` must pass.

### Task 3 commit

```cmd
git add jobpipe_crewai/ tests_crewai/
git commit -m "feat(crewai): author+critic crew — 2 agents, bounded revision loop"
```

---

## Final step — open one PR

```cmd
git push origin codex/T002-authoring-mvp
```

Open PR against `main` with:

**Title:** `T002 Sprint 3: crewAI author/critic loop (isolated module, AuthorAdapter seam)`

**Body:**
```
## Sprint 3 summary

Adds the crewAI authoring layer behind the existing AuthorAdapter Protocol seam.
jobpipe/ contains zero crewai imports — the boundary is enforced by tests.

### Changes

**Task 1 — `jobpipe_crewai` module + `CrewAIAuthor` skeleton**
- `jobpipe_crewai/__init__.py`, `author.py`, `prompts.py`
- `tests_crewai/test_crewai_author_skeleton.py` (5 tests)
- Proves isolation: `test_no_crewai_in_jobpipe` + `test_no_jobpipe_db_in_crewai`

**Task 2 — Author factory + `--author` flag**
- `jobpipe/authoring/author_factory.py`: `build_author(name, model)`
- `jobpipe/authoring/author_cli.py`: `--author simple|crewai`
- `tests/test_author_factory.py` (5 tests)
- Factory uses `importlib` — no static crewai import in jobpipe/

**Task 3 — Real 2-agent crew**
- `jobpipe_crewai/crew.py`: Author + Critic agents, sequential process
- `jobpipe_crewai/author.py`: real crew wired, defensive JSON parsing
- `tests_crewai/test_crewai_crew.py` (5 tests, all monkeypatched)

### Test results
- `tests_crewai/`: 10/10 passed (Python 3.12 crewAI env)
- `tests/test_author_factory.py + test_author_cli.py`: 10/10 passed (Python 3.14)
- `compile_check.py`: passed

### Invariant check
No `import crewai` or `from crewai` anywhere under `jobpipe/`. Verified by `test_no_crewai_in_jobpipe`.

### Sprint 3 exit test
`C:\Users\larsv\envs\crewai-env\Scripts\python.exe -m jobpipe.cli.main author-package --job <id> --author crewai --no-persist`
Run this after merge against a real APPLY-decision job and report the result.
```

---

## Acceptance criteria (15 items — check all before submitting PR)

1. `jobpipe_crewai/__init__.py`, `author.py`, `prompts.py`, `crew.py` exist.
2. `CrewAIAuthor` satisfies `isinstance(CrewAIAuthor(), AuthorAdapter)`.
3. `CrewAIAuthor.generate()` returns a valid `GeneratedApplicationPackage`.
4. `crew.py` builds a crew with exactly 2 agents and 2 tasks.
5. `crew.py` uses `Process.sequential`.
6. Non-JSON crew output is handled gracefully (no raise, gap note added).
7. `jobpipe/authoring/author_factory.py` exists with `build_author(name, model)`.
8. `author_factory.py` uses `importlib.import_module` for the crewai branch (no static import).
9. `--author` flag present in `jobpipe author-package --help`, choices: `simple`, `crewai`.
10. All existing `test_author_cli.py` tests still pass with default `--author simple`.
11. All 10 `tests_crewai/` tests pass under Python 3.12 crewAI env.
12. All 5 `test_author_factory.py` tests pass under Python 3.14.
13. `compile_check.py` passes on all new files.
14. No `import crewai` / `from crewai` anywhere under `jobpipe/`.
15. No `langchain`, `autogen`, or Supabase import anywhere in new files.
