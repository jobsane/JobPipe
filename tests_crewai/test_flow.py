from __future__ import annotations

from unittest.mock import MagicMock, patch

from jobpipe_crewai.flow import JobPipeAuthoringFlow, run_authoring_flow
from jobpipe_crewai.state import JobPipeState


def test_state_defaults():
    state = JobPipeState()

    assert state.job_id == ""
    assert state.decision == ""
    assert state.errors == []
    assert state.exported is False


def test_state_accepts_valid_fields():
    state = JobPipeState(job_id="j1", decision="APPLY", score=0.8)

    assert state.score == 0.8


def test_route_decision_apply():
    for decision in ("APPLY_STRONGLY", "APPLY"):
        flow = JobPipeAuthoringFlow(job_id="j1")
        flow.state.decision = decision
        assert flow.route_decision() == "apply"


def test_route_decision_review():
    flow = JobPipeAuthoringFlow(job_id="j1")
    flow.state.decision = "REVIEW"

    assert flow.route_decision() == "queue"


def test_route_decision_skip():
    flow = JobPipeAuthoringFlow(job_id="j1")
    flow.state.decision = "SKIP"

    assert flow.route_decision() == "done"


def test_route_decision_error():
    flow = JobPipeAuthoringFlow(job_id="j1")
    flow.state.errors.append("not found")

    assert flow.route_decision() == "done"


def test_intake_step_not_found():
    flow = JobPipeAuthoringFlow(job_id="j1")
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = None

    with patch("jobpipe_crewai.flow.get_primary_db_conn", return_value=mock_conn):
        flow.load_decision_step()

    assert len(flow.state.errors) == 1
    assert "not found" in flow.state.errors[0]


def test_intake_step_found():
    flow = JobPipeAuthoringFlow(job_id="j1")
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = {
        "job_id": "j1",
        "suggested_by_platform": 0,
        "title": "PM",
        "decision": "APPLY",
    }

    with patch("jobpipe_crewai.flow.get_primary_db_conn", return_value=mock_conn):
        flow.load_decision_step()

    assert flow.state.job_data["title"] == "PM"
    assert flow.state.decision == "APPLY"
    assert flow.state.errors == []


def test_author_crew_step_valid_json():
    flow = JobPipeAuthoringFlow(job_id="j1")
    flow.state.authoring_context = {"candidate_id": "c1", "job_id": "j1"}
    mock_crew = MagicMock()
    mock_crew.kickoff.return_value = (
        '{"cover_letter_draft": "Hei", "tailored_cv_projection": {}, '
        '"evidence_refs": [], "gap_notes": []}'
    )

    with patch("jobpipe_crewai.flow.build_authoring_crew", return_value=mock_crew):
        flow.author_crew_step()

    assert flow.state.package["cover_letter_draft"] == "Hei"
    assert flow.state.errors == []


def test_author_crew_step_invalid_json():
    flow = JobPipeAuthoringFlow(job_id="j1")
    flow.state.authoring_context = {}
    mock_crew = MagicMock()
    mock_crew.kickoff.return_value = "not json"

    with patch("jobpipe_crewai.flow.build_authoring_crew", return_value=mock_crew):
        flow.author_crew_step()

    assert len(flow.state.errors) == 1
    assert flow.state.package["cover_letter_draft"] == "not json"


def test_run_authoring_flow_returns_state():
    flow = JobPipeAuthoringFlow(job_id="j1")
    flow.state.decision = "SKIP"
    flow.kickoff = lambda: None

    with patch("jobpipe_crewai.flow.JobPipeAuthoringFlow", return_value=flow):
        state = run_authoring_flow("j1")

    assert isinstance(state, JobPipeState)
    assert state.job_id == "j1"


def test_no_crewai_static_import():
    from pathlib import Path

    for fname in ["flow.py", "state.py"]:
        text = (Path("jobpipe_crewai") / fname).read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            assert not (
                stripped.startswith("from crewai")
                and "flow" not in stripped
                and "Flow" not in stripped
            ), f"Unexpected top-level crewai import in {fname}: {line}"
