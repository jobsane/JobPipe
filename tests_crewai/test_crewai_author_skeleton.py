import dataclasses
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_crewai_author_satisfies_protocol():
    from jobpipe.authoring.adapter import AuthorAdapter
    from jobpipe_crewai.author import CrewAIAuthor

    assert isinstance(CrewAIAuthor(), AuthorAdapter)


def test_crewai_author_returns_package():
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
    jobpipe_dir = REPO_ROOT / "jobpipe"
    for py_file in jobpipe_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        assert "import crewai" not in content, f"crewai import in {py_file}"
        assert "from crewai" not in content, f"crewai import in {py_file}"


def test_no_jobpipe_internals_in_crewai():
    crewai_dir = REPO_ROOT / "jobpipe_crewai"
    forbidden = ["jobpipe.core", "jobpipe.runtime", "primary_db"]
    for py_file in crewai_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for term in forbidden:
            assert term not in content, f"{term!r} in {py_file}"


def test_seam_json_roundtrip():
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
    try:
        serialised = ctx.model_dump_json()
    except AttributeError:
        serialised = json.dumps(dataclasses.asdict(ctx))
    recovered = json.loads(serialised)
    assert recovered["job_id"] == "j1"
