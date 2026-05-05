"""Architecture-boundary tests for the core JobPipe slices.

Codified version of the rules in specs/architecture-boundaries.md (§2-§6).

These tests AST-parse each module in a slice and assert that it does NOT
import from packages that would break the intended direction of dependency.
They protect the clean state already achieved on this branch against
accidental regression.

Scope covered:
  - jobpipe.model        (§3) — pure canonical shapes; must not depend on
                                 any other jobpipe package.
  - jobpipe.runtime      (§2) — paths/DB/IO/intake; depends on model only.
                                 Must not depend on cli, stages, projections,
                                 decision, or connectors.
  - jobpipe.decision     (§5) — decision semantics; may depend on runtime
                                 (persistence), core (transitional IO/db), and
                                 model. Must not depend on cli, stages,
                                 projections, or connectors.
  - jobpipe.projections  (§6) — projections consume canonical state; may
                                 depend on runtime.paths, model, decision
                                 (read-only), and core transitional helpers.
                                 Must not depend on cli, stages, or connectors.

The mail connector has its own, narrower invariants in
tests/test_mail_boundary.py.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
JOBPIPE = REPO_ROOT / "jobpipe"


def _iter_py_modules(package_rel: str) -> list[Path]:
    pkg = JOBPIPE / package_rel
    return sorted(p for p in pkg.glob("*.py") if p.name != "__pycache__")


def _imported_modules(source: str) -> set[str]:
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _forbidden_hits(imported: set[str], forbidden_prefixes: tuple[str, ...]) -> set[str]:
    return {
        name
        for name in imported
        if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden_prefixes)
    }


# --- jobpipe.model (§3) ---

# Model is the most foundational layer. It should depend on ZERO jobpipe.*
# packages. Only third-party (pydantic etc.) and stdlib imports allowed.

@pytest.mark.parametrize(
    "module_path",
    _iter_py_modules("model"),
    ids=lambda p: f"model/{p.name}",
)
def test_model_has_no_jobpipe_dependencies(module_path: Path) -> None:
    # model/schema.py is an intentional re-export shim: after the v3-triage
    # refactor, jobpipe.core.schema became the canonical schema module and
    # model/schema.py forwards everything from there (plus the JobSync /
    # ReactiveResume models not yet moved to core).  This one known import is
    # explicitly allowed; all other model files must stay dependency-free.
    _REEXPORT_ALLOWLIST: dict[str, set[str]] = {
        "schema.py": {"jobpipe.core.schema"},
    }
    imported = _imported_modules(module_path.read_text(encoding="utf-8"))
    internal = {name for name in imported if name == "jobpipe" or name.startswith("jobpipe.")}
    allowed = _REEXPORT_ALLOWLIST.get(module_path.name, set())
    violations = internal - allowed
    assert not violations, (
        f"{module_path.name} imports other jobpipe packages: {sorted(violations)}. "
        "jobpipe.model must stay pure-schema (see specs/architecture-boundaries.md §3)."
    )


# --- jobpipe.runtime (§2) ---

_RUNTIME_FORBIDDEN = (
    "jobpipe.cli",
    "jobpipe.stages",
    "jobpipe.projections",
    "jobpipe.decision",
    "jobpipe.connectors",
)


@pytest.mark.parametrize(
    "module_path",
    _iter_py_modules("runtime"),
    ids=lambda p: f"runtime/{p.name}",
)
def test_runtime_does_not_depend_on_higher_slices(module_path: Path) -> None:
    imported = _imported_modules(module_path.read_text(encoding="utf-8"))
    violations = _forbidden_hits(imported, _RUNTIME_FORBIDDEN)
    assert not violations, (
        f"{module_path.name} imports forbidden higher-layer packages: "
        f"{sorted(violations)}. jobpipe.runtime must stay beneath cli, stages, "
        "projections, decision, and connectors "
        "(see specs/architecture-boundaries.md §2)."
    )


# --- jobpipe.decision (§5) ---

# Decision may use runtime (persistence adapters), model (shapes), and the
# transitional jobpipe.core helpers (now_iso, primary_db). It must NOT reach
# up into cli/stages/projections or sideways into connectors.

_DECISION_FORBIDDEN = (
    "jobpipe.cli",
    "jobpipe.stages",
    "jobpipe.projections",
    "jobpipe.connectors",
)


@pytest.mark.parametrize(
    "module_path",
    _iter_py_modules("decision"),
    ids=lambda p: f"decision/{p.name}",
)
def test_decision_does_not_depend_on_higher_slices(module_path: Path) -> None:
    imported = _imported_modules(module_path.read_text(encoding="utf-8"))
    violations = _forbidden_hits(imported, _DECISION_FORBIDDEN)
    assert not violations, (
        f"{module_path.name} imports forbidden packages: {sorted(violations)}. "
        "jobpipe.decision must not depend on cli, stages, projections, or "
        "connectors (see specs/architecture-boundaries.md §5)."
    )


# --- jobpipe.projections (§6) ---

# Projections consume canonical state. They may read from runtime paths,
# model shapes, decision outputs (read-only), and transitional core helpers.
# They must NOT reach into cli, stages (transitional execution surface), or
# connectors (raw source payloads).

_PROJECTIONS_FORBIDDEN = (
    "jobpipe.cli",
    "jobpipe.stages",
    "jobpipe.connectors",
)


@pytest.mark.parametrize(
    "module_path",
    _iter_py_modules("projections"),
    ids=lambda p: f"projections/{p.name}",
)
def test_projections_do_not_depend_on_cli_stages_or_connectors(module_path: Path) -> None:
    imported = _imported_modules(module_path.read_text(encoding="utf-8"))
    violations = _forbidden_hits(imported, _PROJECTIONS_FORBIDDEN)
    assert not violations, (
        f"{module_path.name} imports forbidden packages: {sorted(violations)}. "
        "jobpipe.projections must consume canonical state, not reach into cli, "
        "stages, or connectors (see specs/architecture-boundaries.md §6)."
    )


# --- Sanity check that the slices actually exist ---

def test_all_target_slices_exist() -> None:
    """Guard against renamed/moved packages silently skipping boundary tests."""
    for slice_name in ("runtime", "model", "decision", "projections"):
        pkg = JOBPIPE / slice_name
        assert pkg.is_dir(), f"Expected jobpipe/{slice_name} to exist"
        assert (pkg / "__init__.py").is_file(), (
            f"Expected jobpipe/{slice_name}/__init__.py to exist"
        )
        modules = _iter_py_modules(slice_name)
        assert modules, f"No Python modules found in jobpipe/{slice_name}"
