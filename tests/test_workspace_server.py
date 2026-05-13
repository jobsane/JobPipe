from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from jobpipe.cli.workspace_server import build_server


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_run(root: Path, run_id: str = "jobpipe_v1_server") -> Path:
    run_dir = root / run_id
    job_dir = run_dir / "job-1"
    job_dir.mkdir(parents=True)
    (run_dir / "index.jsonl").write_text(
        json.dumps(
            {
                "job_id": "job-1",
                "title": "Product Manager",
                "employer": "Example AS",
                "triage_v3_weighted_score": 81,
                "final_decision": "APPLY",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_json(
        job_dir / "00_input.json",
        {
            "job_id": "job-1",
            "title": "Product Manager",
            "normalized_title": "Product Manager",
            "employer_name": "Example AS",
            "description_html": "Hybrid platform role with stakeholder work.",
            "applicationUrl": "https://example.test/apply",
            "sourceurl": "https://example.test/job",
            "work_city": "Oslo",
        },
    )
    _write_json(
        job_dir / "bridge_triage_features.json",
        {
            "core_tech_alignment": {"score": 80, "reason": "Platform work matches."},
            "role_specificity": {"score": 75, "reason": "Product ownership is explicit."},
            "operating_fit": {"score": 70, "reason": "Stakeholder work fits."},
            "requirement_density": {"score": 62, "reason": "Requirements are manageable."},
            "stakeholder_complexity": {"score": 64, "reason": "Complexity is useful."},
            "autonomy_level": {"score": 70, "reason": "Autonomy is visible."},
            "geospatial_friction": {"score": 55, "reason": "Oslo is workable."},
            "remote_veracity": {"score": 55, "reason": "Hybrid is stated."},
            "legacy_burden": {"score": 35, "reason": "Legacy burden needs framing."},
        },
    )
    _write_json(
        job_dir / "bridge_triage_decision_v3.json",
        {
            "label": "shortlist",
            "weighted_score": 81,
            "confidence": 75,
            "blockers": ["Legacy burden needs framing"],
            "boosts": ["Strong product overlap"],
            "summary": "Worth review effort.",
        },
    )
    _write_json(
        job_dir / "10_moderator.json",
        {
            "final_decision": "APPLY",
            "recommendation_reason": "Apply with product framing.",
            "cv_focus": ["Platform ownership"],
            "feedback_flags": [],
        },
    )
    return run_dir


def _start_server(out_root: Path):
    server = build_server(out_root=out_root, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    return server, f"http://{host}:{port}"


def _get_json(url: str) -> dict:
    with urlopen(url, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _get_error(url: str) -> tuple[int, dict]:
    try:
        _get_json(url)
    except HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))
    raise AssertionError("expected HTTPError")


def test_workspace_server_health_endpoint(tmp_path: Path) -> None:
    _write_run(tmp_path)
    server, base_url = _start_server(tmp_path)
    try:
        payload = _get_json(f"{base_url}/healthz")
    finally:
        server.shutdown()
        server.server_close()

    assert payload == {"schemaVersion": "jobpipe.workspace.health.v1", "status": "ok"}


def test_workspace_server_lists_latest_run_cases(tmp_path: Path) -> None:
    _write_run(tmp_path)
    server, base_url = _start_server(tmp_path)
    try:
        payload = _get_json(f"{base_url}/cases")
    finally:
        server.shutdown()
        server.server_close()

    assert payload["schemaVersion"] == "jobpipe.workspace.cases.list.v1"
    assert payload["runId"] == "jobpipe_v1_server"
    assert payload["cases"][0]["id"] == "job-1"
    assert payload["cases"][0]["company"] == "Example AS"
    assert payload["cases"][0]["decisionSignalKeys"] == [
        "can_do",
        "can_get",
        "should_want",
        "can_explain",
    ]


def test_workspace_server_lists_explicit_run_cases(tmp_path: Path) -> None:
    _write_run(tmp_path, "jobpipe_v1_11111111")
    _write_run(tmp_path, "jobpipe_v1_22222222")
    server, base_url = _start_server(tmp_path)
    try:
        payload = _get_json(f"{base_url}/cases?run_id=jobpipe_v1_11111111")
    finally:
        server.shutdown()
        server.server_close()

    assert payload["runId"] == "jobpipe_v1_11111111"
    assert payload["cases"][0]["id"] == "job-1"


def test_workspace_server_gets_case_detail(tmp_path: Path) -> None:
    _write_run(tmp_path)
    server, base_url = _start_server(tmp_path)
    try:
        payload = _get_json(f"{base_url}/cases/job-1")
    finally:
        server.shutdown()
        server.server_close()

    assert payload["schemaVersion"] == "jobpipe.workspace.cases.get.v1"
    assert payload["case"]["id"] == "job-1"
    assert payload["case"]["summary"] == "Worth review effort."
    assert payload["case"]["artifacts"][0]["id"].startswith("artifact:job-1:")
    serialized = json.dumps(payload, ensure_ascii=False)
    assert str(tmp_path) not in serialized
    assert "https://example.test" not in serialized


def test_workspace_server_gets_case_materials(tmp_path: Path) -> None:
    _write_run(tmp_path)
    server, base_url = _start_server(tmp_path)
    try:
        payload = _get_json(f"{base_url}/cases/job-1/materials")
    finally:
        server.shutdown()
        server.server_close()

    assert payload["schemaVersion"] == "jobpipe.workspace.materials.v1"
    assert payload["runId"] == "jobpipe_v1_server"
    assert payload["caseId"] == "job-1"
    assert payload["resume"]["status"] == "missing"
    assert payload["valueDraft"]["status"] == "missing"
    assert payload["finalReadiness"]["status"] == "blocked"
    assert payload["finalReadiness"]["blockers"]
    assert {ref["kind"] for ref in payload["finalReadiness"]["artifactRefs"]} == {
        "10_moderator",
        "bridge_triage_decision_v3",
        "bridge_triage_features",
    }
    serialized = json.dumps(payload, ensure_ascii=False)
    assert str(tmp_path) not in serialized
    assert "description_html" not in serialized


def test_workspace_server_case_not_found(tmp_path: Path) -> None:
    _write_run(tmp_path)
    server, base_url = _start_server(tmp_path)
    try:
        status, payload = _get_error(f"{base_url}/cases/missing")
    finally:
        server.shutdown()
        server.server_close()

    assert status == 404
    assert payload["error"]["code"] == "case_not_found"


def test_workspace_server_materials_case_not_found(tmp_path: Path) -> None:
    _write_run(tmp_path)
    server, base_url = _start_server(tmp_path)
    try:
        status, payload = _get_error(f"{base_url}/cases/missing/materials")
    finally:
        server.shutdown()
        server.server_close()

    assert status == 404
    assert payload["error"]["code"] == "case_not_found"


def test_workspace_server_run_not_found(tmp_path: Path) -> None:
    _write_run(tmp_path)
    server, base_url = _start_server(tmp_path)
    try:
        status, payload = _get_error(f"{base_url}/cases?run_id=missing")
    finally:
        server.shutdown()
        server.server_close()

    assert status == 404
    assert payload["error"]["code"] == "run_not_found"


# ----- tailoring_plan endpoint -----------------------------------------------


_APPLICATION_PACK_SAMPLE: dict = {
    "positioning_headline": "Strong product/platform fit",
    "top_value_props": ["Platform ownership", "Stakeholder fluency"],
    "evidence_map": ["Led platform consolidation"],
    "gap_mitigations": ["Pair on Norwegian docs"],
    "cover_letter_angle": "Lead with platform ownership",
    "cover_letter_text": "Dear hiring team, I am writing to apply...",
    "cv_highlights": ["Owned platform across 12 markets"],
    "cv_experience_refs": ["Senior PM, Example AS (2020-2024)"],
}


def _write_run_with_pack(root: Path, run_id: str = "jobpipe_v1_pack") -> Path:
    """Extends ``_write_run`` with a populated 11_application_pack.json."""

    run_dir = _write_run(root, run_id)
    job_dir = run_dir / "job-1"
    _write_json(job_dir / "11_application_pack.json", _APPLICATION_PACK_SAMPLE)
    _write_json(
        job_dir / "02_parsed.json",
        {
            "tools_tech": ["Python", "SQL"],
            "domain_tags": ["platform"],
            "requirements_must": ["Stakeholder management"],
        },
    )
    _write_json(
        job_dir / "03_profile_match.json",
        {
            "fit_score": 80,
            "overlaps": ["Platform ownership"],
            "gaps": ["No Norwegian docs experience"],
            "hard_blockers": [],
        },
    )
    return run_dir


def _post_json(url: str, payload: dict) -> dict:
    import urllib.request

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_error(url: str, payload: dict) -> tuple[int, dict]:
    try:
        _post_json(url, payload)
    except HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))
    raise AssertionError("expected HTTPError")


def test_tailoring_plan_get_returns_pipeline_projection(tmp_path: Path) -> None:
    _write_run_with_pack(tmp_path)
    server, base_url = _start_server(tmp_path)
    try:
        payload = _get_json(f"{base_url}/cases/job-1/tailoring_plan")
    finally:
        server.shutdown()
        server.server_close()

    assert payload["schemaVersion"] == "jobpipe.workspace.tailoring_plan.v1"
    assert payload["runId"] == "jobpipe_v1_pack"
    assert payload["caseId"] == "job-1"
    plan = payload["plan"]
    assert plan is not None
    assert plan["source"] == "pipeline"
    assert plan["positioningAngle"] == "Strong product/platform fit"
    assert plan["valueProposition"]["messagePillars"] == [
        "Platform ownership",
        "Stakeholder fluency",
    ]
    assert plan["coverLetter"]["text"].startswith("Dear hiring team")
    assert plan["coverLetter"]["language"] == "en"
    # Serialisation must be camelCase across the wire
    assert "positioning_angle" not in plan
    assert "value_proposition" not in plan


def test_tailoring_plan_get_returns_null_plan_when_pack_absent(
    tmp_path: Path,
) -> None:
    _write_run(tmp_path)  # no application_pack
    server, base_url = _start_server(tmp_path)
    try:
        payload = _get_json(f"{base_url}/cases/job-1/tailoring_plan")
    finally:
        server.shutdown()
        server.server_close()
    assert payload["plan"] is None


def test_tailoring_plan_post_persists_jobsane_override(tmp_path: Path) -> None:
    _write_run_with_pack(tmp_path)
    server, base_url = _start_server(tmp_path)
    override = {
        "positioningAngle": "JobSane-refined positioning",
        "reactiveResumeUrl": "http://localhost:3000/dashboard/resumes/abc123",
        "coverLetter": {
            "text": "Refined cover letter draft.",
            "language": "en",
        },
    }
    try:
        post_payload = _post_json(
            f"{base_url}/cases/job-1/tailoring_plan", override
        )
        # Read-back via GET to verify persistence + merge with pipeline
        get_payload = _get_json(f"{base_url}/cases/job-1/tailoring_plan")
    finally:
        server.shutdown()
        server.server_close()

    plan = post_payload["plan"]
    assert plan["source"] == "merged"  # both pipeline + jobsane contributed
    assert plan["positioningAngle"] == "JobSane-refined positioning"  # override won
    assert plan["reactiveResumeUrl"].endswith("/abc123")
    # JobSane didn't touch valueProposition → pipeline value survives
    assert plan["valueProposition"]["messagePillars"] == [
        "Platform ownership",
        "Stakeholder fluency",
    ]
    # GET sees the same merged shape
    assert get_payload["plan"]["positioningAngle"] == "JobSane-refined positioning"
    assert get_payload["plan"]["coverLetter"]["text"] == "Refined cover letter draft."

    # On-disk: override file exists under state_root/case_tailoring/<id>.json
    override_path = tmp_path.parent / "case_state" / "case_tailoring" / "job-1.json"
    assert override_path.exists()


def test_tailoring_plan_post_clear_action_removes_override(tmp_path: Path) -> None:
    _write_run_with_pack(tmp_path)
    server, base_url = _start_server(tmp_path)
    try:
        _post_json(
            f"{base_url}/cases/job-1/tailoring_plan",
            {"positioningAngle": "Will be removed"},
        )
        clear_payload = _post_json(
            f"{base_url}/cases/job-1/tailoring_plan", {"action": "clear"}
        )
    finally:
        server.shutdown()
        server.server_close()

    assert clear_payload["cleared"] is True
    # Plan reverts to pipeline-only after clear
    assert clear_payload["plan"]["source"] == "pipeline"
    assert clear_payload["plan"]["positioningAngle"] == "Strong product/platform fit"

    # Override file is gone
    override_path = tmp_path.parent / "case_state" / "case_tailoring" / "job-1.json"
    assert not override_path.exists()


def test_tailoring_plan_post_rejects_unknown_fields(tmp_path: Path) -> None:
    _write_run_with_pack(tmp_path)
    server, base_url = _start_server(tmp_path)
    try:
        status, error = _post_error(
            f"{base_url}/cases/job-1/tailoring_plan",
            {"randomField": "not allowed"},
        )
    finally:
        server.shutdown()
        server.server_close()
    assert status == 400
    assert error["error"]["code"] == "invalid_plan"


def test_tailoring_plan_post_writeback_creates_plan_for_case_without_pack(
    tmp_path: Path,
) -> None:
    """JobSane can write back a plan even for cases without application_pack on disk."""
    _write_run(tmp_path)  # no application_pack artifact
    server, base_url = _start_server(tmp_path)
    try:
        payload = _post_json(
            f"{base_url}/cases/job-1/tailoring_plan",
            {
                "positioningAngle": "JobSane-only plan",
                "coverLetter": {"text": "Written from scratch", "language": "en"},
            },
        )
    finally:
        server.shutdown()
        server.server_close()
    assert payload["plan"]["source"] == "jobsane"
    assert payload["plan"]["positioningAngle"] == "JobSane-only plan"


def test_tailoring_plan_does_not_expose_filesystem_paths(tmp_path: Path) -> None:
    """Workspace contract: no raw paths leak through any tailoring endpoint."""
    _write_run_with_pack(tmp_path)
    server, base_url = _start_server(tmp_path)
    try:
        get_payload = _get_json(f"{base_url}/cases/job-1/tailoring_plan")
        post_payload = _post_json(
            f"{base_url}/cases/job-1/tailoring_plan",
            {"positioningAngle": "Refined"},
        )
    finally:
        server.shutdown()
        server.server_close()
    for payload in (get_payload, post_payload):
        serialized = json.dumps(payload, ensure_ascii=False)
        assert str(tmp_path) not in serialized
        assert "out_runs" not in serialized
        assert "C:\\" not in serialized


def test_workspace_server_does_not_import_forbidden_sources() -> None:
    source = Path("jobpipe/cli/workspace_server.py").read_text(encoding="utf-8")

    assert "dashboard" not in source
    assert "supabase" not in source.lower()
    assert "sqlite3" not in source


def test_workspace_server_help() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "jobpipe.cli.workspace_server", "--help"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--out-root" in result.stdout
    assert "--port" in result.stdout


def test_workspace_server_registered_in_main_cli() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "jobpipe.cli.main", "workspace-server", "--help"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--out-root" in result.stdout
