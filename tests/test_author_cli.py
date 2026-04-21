from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from jobpipe.authoring.case_context import AuthoringCaseContext
from jobpipe.authoring.output_models import DocumentValidationResult, GeneratedApplicationPackage
from jobpipe.authoring import author_cli


def _ctx() -> AuthoringCaseContext:
    return AuthoringCaseContext(
        candidate_id="cand-1",
        job_id="job-001",
        evaluation_id="run-abc:job-001",
        job_summary={"title": "Product Manager", "role_summary": "Lead product discovery."},
        decision_brief={"final_decision": "APPLY", "recommendation_reason": "Strong fit."},
        selected_evidence=[{"evidence_unit_id": "evidence-1"}],
        narrative_brief=None,
        artifact_plan=None,
    )


def _package() -> GeneratedApplicationPackage:
    return GeneratedApplicationPackage(
        job_id="job-001",
        cover_letter_draft="Dette er et kort søknadsutkast.",
        tailored_cv_projection={"highlights": ["Ledet roadmap"], "experience_refs": ["evidence-1"]},
        evidence_refs=[{"evidence_unit_id": "evidence-1"}],
        gap_notes=[],
    )


class _FakeAuthor:
    def __init__(self, model: str = "gpt-4o-mini") -> None:
        self.model = model

    def generate(self, ctx: AuthoringCaseContext) -> GeneratedApplicationPackage:  # noqa: ARG002
        return _package()


def _args(**overrides) -> argparse.Namespace:
    values = {
        "job": "job-001",
        "model": "test-model",
        "no_persist": True,
        "validate": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_author_cli_help() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "jobpipe.cli.main", "author-package", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--job" in result.stdout
    assert "--model" in result.stdout
    assert "--no-persist" in result.stdout
    assert "--validate" in result.stdout


def test_author_cli_no_persist_prints_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(author_cli, "_load_context_for_job", lambda job_id: _ctx())
    monkeypatch.setattr(author_cli, "SimpleAgentAuthor", _FakeAuthor)

    assert author_cli._run(_args(no_persist=True)) == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert data["job_id"] == "job-001"
    assert data["cover_letter_draft"]


def test_author_cli_persist_called(monkeypatch, capsys) -> None:
    calls = []
    monkeypatch.setattr(author_cli, "_load_context_for_job", lambda job_id: _ctx())
    monkeypatch.setattr(author_cli, "SimpleAgentAuthor", _FakeAuthor)
    monkeypatch.setattr(author_cli, "connect_primary_db", lambda path: _FakeConn())
    monkeypatch.setattr(
        author_cli,
        "persist_generated_package",
        lambda conn, package, *, candidate_id, evaluation_id: calls.append(
            (conn, package, candidate_id, evaluation_id)
        ) or "apkg_test",
    )

    assert author_cli._run(_args(no_persist=False)) == 0
    capsys.readouterr()

    assert len(calls) == 1
    assert calls[0][2] == "cand-1"
    assert calls[0][3] == "run-abc:job-001"


def test_author_cli_validate_fails_exits_2(monkeypatch, capsys) -> None:
    monkeypatch.setattr(author_cli, "_load_context_for_job", lambda job_id: _ctx())
    monkeypatch.setattr(
        author_cli,
        "validate_authoring_context",
        lambda ctx: DocumentValidationResult(
            passed=False,
            score=0.8,
            failures=["[required_field_absent] candidate_id is absent or blank"],
            warnings=[],
        ),
    )

    assert author_cli._run(_args(validate=True, no_persist=True)) == 2
    captured = capsys.readouterr()

    assert "passed=False" in captured.err


def test_author_cli_no_crewai() -> None:
    text = Path("jobpipe/authoring/author_cli.py").read_text(encoding="utf-8")

    assert "crewai" not in text
    assert "autogen" not in text
    assert "langchain" not in text


class _FakeConn:
    def __init__(self) -> None:
        self.committed = False
        self.closed = False

    def commit(self) -> None:
        self.committed = True

    def close(self) -> None:
        self.closed = True
