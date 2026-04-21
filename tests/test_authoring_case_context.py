from __future__ import annotations

import subprocess
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from jobpipe.authoring.case_context import AuthoringCaseContext


def _case_context(**overrides: object) -> AuthoringCaseContext:
    values = {
        "candidate_id": "candidate-1",
        "job_id": "job-1",
        "evaluation_id": "eval-1",
        "job_summary": {
            "title": "Product Manager",
            "employer_name": "Example AS",
            "sector": "Technology",
            "application_due": "2026-05-01",
            "source_url": "https://example.test/job-1",
            "role_summary": "Lead product discovery and delivery.",
        },
        "decision_brief": {
            "final_decision": "APPLY",
            "recommendation_reason": "Strong overlap with product leadership.",
            "cv_focus": ["roadmap", "stakeholder alignment"],
            "act_now": "pursue_now",
            "can_do_score": 84,
            "can_get_score": 76,
            "should_want_score": 81,
            "can_explain_score": 88,
        },
        "selected_evidence": [
            {
                "evidence_unit_id": "evidence-1",
                "canonical_text": "Led cross-functional roadmap work.",
                "relevance_score": 91,
            }
        ],
        "narrative_brief": {
            "core_identity": ["Product leader"],
            "future_direction": ["AI-enabled services"],
            "motivation_brief": "The role fits the candidate's current direction.",
        },
        "artifact_plan": {"target": "cover_letter"},
    }
    values.update(overrides)
    return AuthoringCaseContext(**values)


def test_construction_happy_path() -> None:
    context = _case_context()

    assert context.candidate_id == "candidate-1"
    assert context.job_id == "job-1"
    assert context.evaluation_id == "eval-1"
    assert context.job_summary["title"] == "Product Manager"
    assert context.decision_brief["final_decision"] == "APPLY"
    assert context.selected_evidence[0]["evidence_unit_id"] == "evidence-1"
    assert context.narrative_brief == {
        "core_identity": ["Product leader"],
        "future_direction": ["AI-enabled services"],
        "motivation_brief": "The role fits the candidate's current direction.",
    }
    assert context.artifact_plan == {"target": "cover_letter"}


def test_frozen_enforcement() -> None:
    context = _case_context()

    with pytest.raises((FrozenInstanceError, AttributeError)):
        context.job_id = "job-2"


def test_none_fields_valid() -> None:
    context = _case_context(
        evaluation_id=None,
        narrative_brief=None,
        artifact_plan=None,
    )

    assert context.evaluation_id is None
    assert context.narrative_brief is None
    assert context.artifact_plan is None


def test_selected_evidence_is_list_of_dicts() -> None:
    selected_evidence = [
        {"evidence_unit_id": "evidence-1"},
        {"evidence_unit_id": "evidence-2"},
    ]

    context = _case_context(selected_evidence=selected_evidence)

    assert isinstance(context.selected_evidence, list)
    assert all(isinstance(row, dict) for row in context.selected_evidence)
    assert len(context.selected_evidence) == 2


def test_no_crewai_import() -> None:
    env = None
    git_grep_dir = Path("C:/Program Files/Git/usr/bin")
    if git_grep_dir.exists():
        import os

        env = dict(os.environ)
        env["PATH"] = f"{git_grep_dir}{os.pathsep}{env.get('PATH', '')}"

    result = subprocess.run(
        ["grep", "-r", "crewai", "jobpipe/", "--include=*.py"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert result.returncode == 1, f"Unexpected crewai reference found:\n{result.stdout}"
    assert result.stdout == ""
