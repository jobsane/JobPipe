from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from jobpipe.authoring.adapter import AuthorAdapter
from jobpipe.authoring.case_context import AuthoringCaseContext
from jobpipe.authoring.output_models import GeneratedApplicationPackage
from jobpipe.authoring.simple_agent_author import SimpleAgentAuthor


class _FakeRunResult:
    def __init__(self, output):
        self.final_output = output


def _ctx() -> AuthoringCaseContext:
    return AuthoringCaseContext(
        candidate_id="cand-1",
        job_id="job-001",
        evaluation_id="run-abc:job-001",
        job_summary={
            "title": "Product Manager",
            "employer_name": "Acme AS",
            "sector": "Technology",
            "application_due": "2026-05-01",
            "source_url": "https://example.test/job-001",
            "role_summary": "Lead product discovery.",
        },
        decision_brief={
            "final_decision": "APPLY",
            "recommendation_reason": "Strong fit.",
            "cv_focus": ["roadmap"],
            "act_now": "pursue_now",
            "can_do_score": 84,
            "can_get_score": 76,
            "should_want_score": 81,
            "can_explain_score": 88,
        },
        selected_evidence=[
            {"evidence_unit_id": "evidence-1", "canonical_text": "Led roadmap work."}
        ],
        narrative_brief={
            "core_identity": ["Product leader"],
            "future_direction": ["AI services"],
            "motivation_themes": [],
            "pivot_thesis": ["Credible move"],
            "direction_fit_score": 82,
            "motivation_fit_score": 79,
            "story_strength_score": 88,
            "motivation_brief": "The role fits.",
        },
        artifact_plan=None,
    )


def _author_output() -> SimpleNamespace:
    return SimpleNamespace(
        cover_letter_draft="Dette er et kort søknadsutkast.",
        tailored_cv_projection={
            "highlights": [
                "Ledet veikartarbeid på tvers av fagmiljøer.",
                "Oversatte brukerbehov til prioriterte leveranser.",
                "Koordinerte interessenter gjennom produktbeslutninger.",
                "Brukte evidens til å spisse budskapet.",
            ],
            "experience_refs": ["evidence-1", "evidence-1", "evidence-1", "evidence-1"],
        },
        evidence_refs=["evidence-1"],
        gap_notes=["Ingen kritiske gap identifisert."],
    )


def _patch_run_agent(monkeypatch):
    def fake_run_agent(agent, input_text: str, trace=None):  # noqa: ARG001
        return _FakeRunResult(_author_output())

    monkeypatch.setattr("jobpipe.authoring.simple_agent_author.run_agent", fake_run_agent)


def test_simple_author_implements_protocol() -> None:
    assert isinstance(SimpleAgentAuthor(), AuthorAdapter)


def test_generate_returns_generated_application_package(monkeypatch) -> None:
    _patch_run_agent(monkeypatch)
    author = SimpleAgentAuthor()

    result = author.generate(_ctx())

    assert isinstance(result, GeneratedApplicationPackage)


def test_generate_propagates_job_id(monkeypatch) -> None:
    _patch_run_agent(monkeypatch)
    ctx = _ctx()

    result = SimpleAgentAuthor().generate(ctx)

    assert result.job_id == ctx.job_id


def test_generate_cover_letter_and_projection_populated(monkeypatch) -> None:
    _patch_run_agent(monkeypatch)

    result = SimpleAgentAuthor().generate(_ctx())

    assert result.cover_letter_draft != ""
    assert isinstance(result.tailored_cv_projection, dict)
    assert result.tailored_cv_projection["highlights"]
    assert result.tailored_cv_projection["experience_refs"]


def test_no_crewai_import() -> None:
    for path in (
        Path("jobpipe/authoring/adapter.py"),
        Path("jobpipe/authoring/simple_agent_author.py"),
    ):
        text = path.read_text(encoding="utf-8")
        assert "crewai" not in text
        assert "autogen" not in text
        assert "langchain" not in text
