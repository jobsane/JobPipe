import dataclasses
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
pytest.importorskip("crewai")


def _make_ctx():
    from jobpipe.authoring.case_context import AuthoringCaseContext

    return AuthoringCaseContext(
        candidate_id="c1",
        job_id="j1",
        evaluation_id="e1",
        job_summary={"title": "Engineer", "company": "Acme"},
        decision_brief={"match_score": 0.85, "claim_targets": ["Python"]},
        selected_evidence=[{"id": "ev1", "role": "Backend Eng", "bullets": ["Built APIs"]}],
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
    from jobpipe.authoring.output_models import GeneratedApplicationPackage
    from jobpipe_crewai.author import CrewAIAuthor

    fake = json.dumps(
        {
            "cover_letter_draft": "Dear Hiring Manager...",
            "tailored_cv_projection": {
                "headline": "Backend Engineer",
                "summary_text": "...",
                "sections": [],
            },
            "evidence_refs": ["ev1"],
            "gap_notes": [],
        }
    )

    with patch("jobpipe_crewai.author.build_authoring_crew") as mock_build:
        mock_crew = MagicMock()
        mock_crew.kickoff.return_value = fake
        mock_build.return_value = mock_crew
        pkg = CrewAIAuthor().generate(_make_ctx())

    assert isinstance(pkg, GeneratedApplicationPackage)
    assert pkg.cover_letter_draft == "Dear Hiring Manager..."
    assert pkg.evidence_refs == ["ev1"]


def test_crew_handles_non_json_output():
    from jobpipe.authoring.output_models import GeneratedApplicationPackage
    from jobpipe_crewai.author import CrewAIAuthor

    with patch("jobpipe_crewai.author.build_authoring_crew") as mock_build:
        mock_crew = MagicMock()
        mock_crew.kickoff.return_value = "Here is your letter. Dear Hiring Manager..."
        mock_build.return_value = mock_crew
        pkg = CrewAIAuthor().generate(_make_ctx())

    assert isinstance(pkg, GeneratedApplicationPackage)
    assert len(pkg.cover_letter_draft) > 0
    assert any("not valid JSON" in n for n in pkg.gap_notes)


def test_no_langchain_or_autogen():
    crewai_dir = REPO_ROOT / "jobpipe_crewai"
    for py_file in crewai_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        assert "langchain" not in content, f"langchain in {py_file}"
        assert "autogen" not in content, f"autogen in {py_file}"
