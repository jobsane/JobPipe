"""Local dashboard server for JobPipe.

Serves the dashboard at http://localhost:5100 and enables:
  - Direct status updates (no clipboard → terminal round-trip)
  - Auto-saving notes per job
  - Application pack generation from the browser
  - Live data refresh from SQLite (no HTML rebuild needed for status/notes changes)

Usage:
    python -m jobpipe.cli.dashboard_server          # start server, open browser
    python -m jobpipe.cli.dashboard_server --no-open  # start without opening browser
    python -m jobpipe.cli.dashboard_server --port 5200  # custom port
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from jobpipe.core.automation_state import (
    AUTOMATION_ACTIONS,
    append_automation_run,
    build_automation_payload,
    update_automation_run,
)
from jobpipe.core.boundary_objects import (
    build_artifact_plan_from_job_dir,
    build_authoring_brief,
    build_case_job_summary,
    build_decision_brief,
)
from jobpipe.core.experiment_review_state import (
    upsert_experiment_review,
    upsert_experiment_promotion_review,
    upsert_experiment_variant_review,
)
from jobpipe.core.intake_pipe import rebuild_intake_queue
from jobpipe.core.jobsync_authoring import sync_authoring_state
from jobpipe.core.paths import JOBPIPE_DATA_ROOT_ENV, JobPipePaths, bootstrap_private_data, get_jobpipe_paths
from jobpipe.core.projection_store import (
    build_projected_job_input,
    load_job_projection_bundle,
    projection_bundle_detail_projection,
    projection_bundle_input_enrichment,
    projection_decision_brief,
    projection_job_summary,
)
from jobpipe.core.settings_state import load_settings_state, persist_settings_state

# ── Paths ────────────────────────────────────────────────────────────────────
_DEFAULT_PATHS = get_jobpipe_paths()
PATHS = _DEFAULT_PATHS
STATE_PATH = PATHS.application_state_path
PROFILE_DRAFT_PATH = PATHS.profile_builder_state_path
SETTINGS_STATE_PATH = PATHS.settings_state_path
AUTOMATION_STATE_PATH = PATHS.automation_state_path
EXPERIMENT_REVIEW_STATE_PATH = PATHS.experiment_review_state_path
DASHBOARD_PATH = PATHS.dashboard_export_path
SQLITE_PATH = PATHS.ledger_sqlite_path
TEMPLATE_PATH = PATHS.dashboard_template_path
APPLY_TEMPLATE_PATH = PATHS.apply_template_path
OUT_RUNS = PATHS.out_runs_dir
PROFILE_PATH = PATHS.profile_pack_path
RESUME_PATH = PATHS.resume_json_path
RESUME_FIXED_PATH = PATHS.resume_fixed_json_path
CONFIG_PATH = PATHS.default_config_path
CONFIG_OVERLAYS: list[str] = []

PORT = 5100
APPLY_SESSION_VERSION = "jobpipe.apply-session.v1"
AUTHORING_STATE_VERSION = "jobpipe.authoring-state.v1"

# ── Background generation tracker ──
_gen_status: dict[str, str] = {}   # job_id → "running" | "done" | "error:<msg>"
_gen_lock = threading.Lock()

_prep_status: dict[str, dict] = {}  # job_id → {status, message, outputs}
_prep_lock = threading.Lock()

# ── Gmail OAuth setup tracker ──
_gmail_setup_status: dict[str, Any] = {}  # keys: "status", "message", "started_at"
_gmail_setup_lock = threading.Lock()
_STAGE_ALIASES = {"parse": "parsed", "moderate": "moderator"}
_DEFAULT_STAGE_ORDER = [
    "triage",
    "reverse_triage",
    "parsed",
    "profile_match",
    "pivot",
    "moderator",
    "application_pack",
]


def _apply_paths(paths: JobPipePaths) -> None:
    global PATHS
    global STATE_PATH, PROFILE_DRAFT_PATH, SETTINGS_STATE_PATH, AUTOMATION_STATE_PATH, EXPERIMENT_REVIEW_STATE_PATH, DASHBOARD_PATH, SQLITE_PATH
    global TEMPLATE_PATH, APPLY_TEMPLATE_PATH, OUT_RUNS, PROFILE_PATH
    global RESUME_PATH, RESUME_FIXED_PATH, CONFIG_PATH

    PATHS = paths
    STATE_PATH = paths.application_state_path
    PROFILE_DRAFT_PATH = paths.profile_builder_state_path
    SETTINGS_STATE_PATH = paths.settings_state_path
    AUTOMATION_STATE_PATH = paths.automation_state_path
    EXPERIMENT_REVIEW_STATE_PATH = paths.experiment_review_state_path
    DASHBOARD_PATH = paths.dashboard_export_path
    SQLITE_PATH = paths.ledger_sqlite_path
    TEMPLATE_PATH = paths.dashboard_template_path
    APPLY_TEMPLATE_PATH = paths.apply_template_path
    OUT_RUNS = paths.out_runs_dir
    PROFILE_PATH = paths.profile_pack_path
    RESUME_PATH = paths.resume_json_path
    RESUME_FIXED_PATH = paths.resume_fixed_json_path
    CONFIG_PATH = paths.default_config_path


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _clean_profile_draft(draft: Dict[str, Any]) -> Dict[str, str]:
    clean: Dict[str, str] = {}
    for key, value in draft.items():
        if value is None:
            continue
        clean[str(key)] = str(value)
    return clean


def _persist_profile_draft(path: Path, draft: Dict[str, Any]) -> Dict[str, str]:
    clean = _clean_profile_draft(draft)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(clean, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return clean


def _persist_settings_payload(path: Path, payload: Dict[str, Any]) -> Dict[str, Any]:
    return persist_settings_state(path, payload)


def _automation_action_map() -> Dict[str, Dict[str, str]]:
    return {
        action.key: {
            "label": action.label,
            "category": action.category,
        }
        for action in AUTOMATION_ACTIONS
    }


def _command_env() -> Dict[str, str]:
    env = os.environ.copy()
    env[JOBPIPE_DATA_ROOT_ENV] = str(PATHS.data_root)
    return env


def _tail_log_text(text: str, *, limit: int = 1200) -> str:
    cleaned = (text or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[-limit:]


def _run_subprocess_action(args: list[str], *, timeout: int = 120) -> Dict[str, Any]:
    completed = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(PATHS.repo_root),
        env=_command_env(),
        timeout=timeout,
        check=False,
    )
    stdout_clean = completed.stdout.strip()
    stderr_clean = completed.stderr.strip()
    combined = "\n".join(part for part in [stdout_clean, stderr_clean] if part)
    if stdout_clean:
        summary = stdout_clean.splitlines()[-1]
    elif stderr_clean:
        summary = stderr_clean.splitlines()[-1]
    else:
        summary = f"Exit code {completed.returncode}"
    return {
        "status": "succeeded" if completed.returncode == 0 else "failed",
        "exit_code": int(completed.returncode),
        "summary": summary,
        "log_excerpt": _tail_log_text(combined),
    }


def _run_automation_action(action_key: str) -> Dict[str, Any]:
    if action_key == "scheduled_full_run":
        return _run_subprocess_action(
            [
                sys.executable,
                "-m",
                "jobpipe.cli.run_scheduled_flow",
                "--data-root",
                str(PATHS.data_root),
            ],
            timeout=7200,
        )
    if action_key == "nav_refresh":
        return _run_subprocess_action(
            [
                sys.executable,
                "-m",
                "jobpipe.cli.pull_sheets_csv",
                "--only-changed",
                "--out",
                str(PATHS.nav_connector_path),
            ]
        )
    if action_key == "mailbox_leads_dry_run":
        return _run_subprocess_action(
            [
                sys.executable,
                "-m",
                "jobpipe.cli.sync_mailbox_leads",
                "--dry-run",
            ]
        )
    if action_key == "merge_connectors":
        counts = rebuild_intake_queue(
            nav_path=PATHS.nav_connector_path,
            leads_path=PATHS.leads_connector_path,
            out_path=PATHS.jobs_delta_path,
        )
        summary = (
            f"Merged queue rebuilt: nav {counts['nav_records']}, "
            f"leads {counts['lead_records']}, merged {counts['merged_records']}"
        )
        return {
            "status": "succeeded",
            "exit_code": 0,
            "summary": summary,
            "log_excerpt": summary,
        }
    if action_key == "export_dashboard":
        from jobpipe.cli.export_dashboard import export

        export(
            SQLITE_PATH,
            OUT_RUNS,
            TEMPLATE_PATH,
            DASHBOARD_PATH,
            state_path=STATE_PATH,
            config_path=CONFIG_PATH,
            config_overlays=CONFIG_OVERLAYS,
            profile_path=PROFILE_PATH,
            resume_path=RESUME_PATH,
            profile_draft_path=PROFILE_DRAFT_PATH,
            settings_path=SETTINGS_STATE_PATH,
        )
        summary = f"Dashboard rebuilt at {DASHBOARD_PATH}"
        return {
            "status": "succeeded",
            "exit_code": 0,
            "summary": summary,
            "log_excerpt": summary,
        }
    return {
        "status": "failed",
        "exit_code": 1,
        "summary": f"Unknown automation action: {action_key}",
        "log_excerpt": f"Unknown automation action: {action_key}",
    }


def _gmail_oauth_status() -> Dict[str, Any]:
    """Return current Gmail OAuth readiness without starting anything."""
    with _gmail_setup_lock:
        setup = dict(_gmail_setup_status)
    return {
        "credentials_present": PATHS.gmail_credentials_path.exists(),
        "token_present": PATHS.gmail_token_path.exists(),
        "credentials_path": str(PATHS.gmail_credentials_path),
        "token_path": str(PATHS.gmail_token_path),
        "setup_status": setup.get("status", "idle"),
        "setup_message": setup.get("message", ""),
        "setup_started_at": setup.get("started_at", ""),
    }


def _run_gmail_oauth_setup() -> None:
    """Background worker: run scan_gmail --setup."""
    with _gmail_setup_lock:
        _gmail_setup_status.update({"status": "running", "message": "Browser consent window opened. Complete authorization there.", "started_at": _utc_now_z()})
    try:
        result = _run_subprocess_action(
            [sys.executable, "-m", "jobpipe.cli.scan_gmail", "--setup"],
            timeout=300,
        )
        with _gmail_setup_lock:
            if result["exit_code"] == 0:
                _gmail_setup_status.update({"status": "done", "message": result["summary"]})
            else:
                _gmail_setup_status.update({"status": "error", "message": result.get("log_excerpt") or result["summary"]})
    except Exception as exc:
        with _gmail_setup_lock:
            _gmail_setup_status.update({"status": "error", "message": str(exc)})


def _start_automation_run(action_key: str) -> Dict[str, Any]:
    action = _automation_action_map().get(action_key)
    if not action:
        return {}

    run_id = f"run_{uuid4().hex[:12]}"
    run = {
        "run_id": run_id,
        "action_key": action_key,
        "label": action["label"],
        "category": action["category"],
        "status": "running",
        "started_at": _utc_now_z(),
        "finished_at": "",
        "exit_code": None,
        "summary": "Run started.",
        "log_excerpt": "",
    }
    append_automation_run(AUTOMATION_STATE_PATH, run)

    def _worker() -> None:
        result = _run_automation_action(action_key)
        update_automation_run(
            AUTOMATION_STATE_PATH,
            run_id,
            {
                "status": result.get("status", "failed"),
                "finished_at": _utc_now_z(),
                "exit_code": result.get("exit_code"),
                "summary": result.get("summary", ""),
                "log_excerpt": result.get("log_excerpt", ""),
            },
        )

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    return run


def _persist_application_notes(state_path: Path, job_id: str, notes: str) -> Dict[str, Any]:
    from jobpipe.cli.mark_status import _migrate_entry, load_state, save_state

    state = load_state(state_path)
    apps = state.setdefault("applications", {})
    entry = _migrate_entry(apps.get(job_id, {}))
    entry["notes"] = notes
    entry["updated_at"] = _utc_now_z()
    apps[job_id] = entry
    save_state(state_path, state)
    return entry


def _persist_experiment_review(
    state_path: Path,
    *,
    experiment_id: str,
    job_id: str,
    verdict: str,
    note: str = "",
    run_id: str = "",
    review_reason: str = "",
    review_priority: int | None = None,
) -> Dict[str, Any]:
    return upsert_experiment_review(
        state_path,
        experiment_id=experiment_id,
        job_id=job_id,
        verdict=verdict,
        note=note,
        run_id=run_id,
        review_reason=review_reason,
        review_priority=review_priority,
    )


def _persist_experiment_variant_review(
    state_path: Path,
    *,
    experiment_id: str,
    verdict: str,
    note: str = "",
    candidate_name: str = "",
    kind: str = "",
) -> Dict[str, Any]:
    return upsert_experiment_variant_review(
        state_path,
        experiment_id=experiment_id,
        verdict=verdict,
        note=note,
        candidate_name=candidate_name,
        kind=kind,
    )


def _persist_experiment_promotion_review(
    state_path: Path,
    *,
    experiment_id: str,
    verdict: str,
    note: str = "",
    candidate_name: str = "",
    kind: str = "",
) -> Dict[str, Any]:
    return upsert_experiment_promotion_review(
        state_path,
        experiment_id=experiment_id,
        verdict=verdict,
        note=note,
        candidate_name=candidate_name,
        kind=kind,
    )


def _path_entry(path: Path, *, label: str, purpose: str) -> Dict[str, Any]:
    return {
        "label": label,
        "purpose": purpose,
        "path": str(path),
        "exists": path.exists(),
    }


def _authoring_state_path(job_dir: Path) -> Path:
    return job_dir / "authoring_state.json"


def _clean_authoring_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _clean_artifact_refs(value: Any) -> list[Dict[str, str]]:
    refs: list[Dict[str, str]] = []
    if not isinstance(value, list):
        return refs
    for item in value[:8]:
        if not isinstance(item, dict):
            continue
        ref = {
            "kind": _clean_authoring_text(item.get("kind")),
            "label": _clean_authoring_text(item.get("label")),
            "path": _clean_authoring_text(item.get("path")),
            "url": _clean_authoring_text(item.get("url")),
        }
        if not any(ref[key] for key in ("label", "path", "url")):
            continue
        refs.append(ref)
    return refs


def _default_authoring_state(job_id: str, job_dir: Path) -> Dict[str, Any]:
    return {
        "schemaVersion": AUTHORING_STATE_VERSION,
        "jobId": job_id,
        "statePath": str(_authoring_state_path(job_dir)),
        "updatedAt": "",
        "resume": {
            "variantRef": "",
            "variantLabel": "",
            "sourceUrl": "",
            "exportRef": "",
            "exportLabel": "",
            "exportUrl": "",
            "exportFormat": "pdf",
            "exportedAt": "",
            "exportPdfPath": str(job_dir / "10_tailored_resume.pdf"),
            "exportJsonPath": str(job_dir / "10_tailored_resume.json"),
            "artifactRefs": [],
        },
        "coverLetter": {
            "documentRef": "",
            "documentLabel": "",
            "sourceUrl": "",
            "exportRef": "",
            "exportLabel": "",
            "exportUrl": "",
            "exportFormat": "docx",
            "exportedAt": "",
            "exportDocxPath": str(job_dir / "08_cover_letter.docx"),
            "artifactRefs": [],
        },
        "screeningAnswers": {
            "documentRef": "",
            "documentLabel": "",
            "sourceUrl": "",
            "exportRef": "",
            "exportLabel": "",
            "exportUrl": "",
            "exportFormat": "docx",
            "exportedAt": "",
            "exportDocxPath": str(job_dir / "09_screening_answers.docx"),
            "artifactRefs": [],
        },
    }


def _coerce_authoring_state(raw: Any, *, job_id: str, job_dir: Path) -> Dict[str, Any]:
    state = _default_authoring_state(job_id, job_dir)
    if not isinstance(raw, dict):
        return state

    state["updatedAt"] = _clean_authoring_text(raw.get("updatedAt"))
    section_fields = {
        "resume": (
            "variantRef",
            "variantLabel",
            "sourceUrl",
            "exportRef",
            "exportLabel",
            "exportUrl",
            "exportFormat",
            "exportedAt",
            "exportPdfPath",
            "exportJsonPath",
        ),
        "coverLetter": (
            "documentRef",
            "documentLabel",
            "sourceUrl",
            "exportRef",
            "exportLabel",
            "exportUrl",
            "exportFormat",
            "exportedAt",
            "exportDocxPath",
        ),
        "screeningAnswers": (
            "documentRef",
            "documentLabel",
            "sourceUrl",
            "exportRef",
            "exportLabel",
            "exportUrl",
            "exportFormat",
            "exportedAt",
            "exportDocxPath",
        ),
    }
    for section_name, field_names in section_fields.items():
        section_raw = raw.get(section_name)
        if not isinstance(section_raw, dict):
            continue
        for field_name in field_names:
            if field_name in section_raw:
                state[section_name][field_name] = _clean_authoring_text(section_raw.get(field_name))
        state[section_name]["artifactRefs"] = _clean_artifact_refs(section_raw.get("artifactRefs"))
    return state


def _load_authoring_state(job_dir: Path, job_id: str) -> Dict[str, Any]:
    state_path = _authoring_state_path(job_dir)
    if not state_path.exists():
        return _default_authoring_state(job_id, job_dir)
    try:
        raw = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    return _coerce_authoring_state(raw, job_id=job_id, job_dir=job_dir)


def _persist_authoring_state(job_dir: Path, job_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    state = _load_authoring_state(job_dir, job_id)
    section_fields = {
        "resume": (
            "variantRef",
            "variantLabel",
            "sourceUrl",
            "exportRef",
            "exportLabel",
            "exportUrl",
            "exportFormat",
            "exportedAt",
            "exportPdfPath",
            "exportJsonPath",
        ),
        "coverLetter": (
            "documentRef",
            "documentLabel",
            "sourceUrl",
            "exportRef",
            "exportLabel",
            "exportUrl",
            "exportFormat",
            "exportedAt",
            "exportDocxPath",
        ),
        "screeningAnswers": (
            "documentRef",
            "documentLabel",
            "sourceUrl",
            "exportRef",
            "exportLabel",
            "exportUrl",
            "exportFormat",
            "exportedAt",
            "exportDocxPath",
        ),
    }
    for section_name, field_names in section_fields.items():
        section_payload = payload.get(section_name)
        if not isinstance(section_payload, dict):
            continue
        for field_name in field_names:
            if field_name in section_payload:
                state[section_name][field_name] = _clean_authoring_text(section_payload.get(field_name))
        if "artifactRefs" in section_payload:
            state[section_name]["artifactRefs"] = _clean_artifact_refs(section_payload.get("artifactRefs"))
        if section_name == "resume":
            has_resume_export = any(
                state["resume"].get(field_name)
                for field_name in ("exportRef", "exportLabel", "exportUrl")
            )
            if has_resume_export and not state["resume"].get("exportedAt"):
                state["resume"]["exportedAt"] = _utc_now_z()
            if not state["resume"].get("exportFormat"):
                state["resume"]["exportFormat"] = "pdf"
        if section_name in ("coverLetter", "screeningAnswers"):
            has_doc_export = any(
                state[section_name].get(field_name)
                for field_name in ("exportRef", "exportLabel", "exportUrl")
            )
            if has_doc_export and not state[section_name].get("exportedAt"):
                state[section_name]["exportedAt"] = _utc_now_z()
            if not state[section_name].get("exportFormat"):
                state[section_name]["exportFormat"] = "docx"

    state["updatedAt"] = _utc_now_z()
    state_path = _authoring_state_path(job_dir)
    state_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return state


def _build_resume_handoff_brief(
    *,
    job: Dict[str, Any],
    pack: Dict[str, Any],
    match: Dict[str, Any],
    moderator: Dict[str, Any],
) -> str:
    title = _clean_authoring_text(job.get("title"))
    employer = _clean_authoring_text(job.get("employer_name") or job.get("company"))
    cv_highlights = [str(item) for item in (pack.get("cv_highlights") or []) if item]
    top_value_props = [str(item) for item in (pack.get("top_value_props") or []) if item]
    evidence_map = [str(item) for item in (pack.get("evidence_map") or []) if item]
    gap_mitigations = [str(item) for item in (pack.get("gap_mitigations") or []) if item]
    cv_focus = [str(item) for item in (moderator.get("cv_focus") or []) if item]
    overlaps = [str(item) for item in (match.get("overlaps") or []) if item]

    sections = [
        f"Tailor a resume variant for: {title} @ {employer}".strip(),
        "",
        "Prioritize these focus areas:",
    ]
    focus_items = cv_focus or top_value_props or overlaps
    if focus_items:
        sections.extend(f"- {item}" for item in focus_items[:6])
    else:
        sections.append("- Highlight the strongest relevant ownership and delivery evidence.")

    if cv_highlights:
        sections.extend(["", "Relevant CV highlights to preserve:"])
        sections.extend(f"- {item}" for item in cv_highlights[:6])
    if evidence_map:
        sections.extend(["", "Evidence map:"])
        sections.extend(f"- {item}" for item in evidence_map[:6])
    if gap_mitigations:
        sections.extend(["", "Gaps to mitigate in the variant:"])
        sections.extend(f"- {item}" for item in gap_mitigations[:4])

    sections.extend(
        [
            "",
            "Output requirements:",
            "- Save a final PDF to the deterministic resume PDF target.",
            "- Save structured source or export metadata to the deterministic resume JSON target.",
        ]
    )
    return "\n".join(sections).strip()


def _build_cover_letter_handoff_brief(
    *,
    job: Dict[str, Any],
    pack: Dict[str, Any],
    match: Dict[str, Any],
) -> str:
    title = _clean_authoring_text(job.get("title"))
    employer = _clean_authoring_text(job.get("employer_name") or job.get("company"))
    cover_letter_angle = _clean_authoring_text(pack.get("cover_letter_angle"))
    top_value_props = [str(item) for item in (pack.get("top_value_props") or []) if item]
    evidence_map = [str(item) for item in (pack.get("evidence_map") or []) if item]
    overlaps = [str(item) for item in (match.get("overlaps") or []) if item]
    gaps = [str(item) for item in (match.get("gaps") or []) if item]

    sections = [
        f"Draft a tailored cover letter for: {title} @ {employer}".strip(),
        "",
    ]
    if cover_letter_angle:
        sections.extend(["Target angle:", f"- {cover_letter_angle}"])
    if top_value_props:
        sections.extend(["", "Main value props to foreground:"])
        sections.extend(f"- {item}" for item in top_value_props[:5])
    if evidence_map:
        sections.extend(["", "Evidence to translate into the letter:"])
        sections.extend(f"- {item}" for item in evidence_map[:5])
    if overlaps:
        sections.extend(["", "Strong overlaps:"])
        sections.extend(f"- {item}" for item in overlaps[:5])
    if gaps:
        sections.extend(["", "Gaps to handle carefully:"])
        sections.extend(f"- {item}" for item in gaps[:3])
    sections.extend(
        [
            "",
            "Output requirements:",
            "- Keep the narrative concrete and submission-ready.",
            "- Save the working/final document back to the deterministic DOCX target.",
        ]
    )
    return "\n".join(sections).strip()


def _build_screening_handoff_brief(
    *,
    job: Dict[str, Any],
    pack: Dict[str, Any],
    match: Dict[str, Any],
) -> str:
    title = _clean_authoring_text(job.get("title"))
    employer = _clean_authoring_text(job.get("employer_name") or job.get("company"))
    interview_prep = [str(item) for item in (pack.get("interview_prep") or []) if item]
    top_value_props = [str(item) for item in (pack.get("top_value_props") or []) if item]
    overlaps = [str(item) for item in (match.get("overlaps") or []) if item]
    gaps = [str(item) for item in (match.get("gaps") or []) if item]

    sections = [
        f"Prepare screening-answer material for: {title} @ {employer}".strip(),
        "",
        "Use the same positioning as the application case.",
    ]
    if top_value_props:
        sections.extend(["", "Core value props:"])
        sections.extend(f"- {item}" for item in top_value_props[:5])
    if interview_prep:
        sections.extend(["", "Likely themes or prompts:"])
        sections.extend(f"- {item}" for item in interview_prep[:6])
    if overlaps:
        sections.extend(["", "Strong overlaps to reuse in answers:"])
        sections.extend(f"- {item}" for item in overlaps[:5])
    if gaps:
        sections.extend(["", "Gaps to acknowledge or mitigate if asked:"])
        sections.extend(f"- {item}" for item in gaps[:3])
    sections.extend(
        [
            "",
            "Output requirements:",
            "- Save the final screening-answer document back to the deterministic DOCX target.",
        ]
    )
    return "\n".join(sections).strip()


def _build_apply_session_manifest(
    *,
    job_id: str,
    job_dir: Path,
    job: Dict[str, Any],
    pack: Dict[str, Any],
    match: Dict[str, Any],
    pivot: Dict[str, Any],
    moderator: Dict[str, Any],
    cover_letter_draft: str,
    authoring_state: Optional[Dict[str, Any]] = None,
    reactive_resume_base_url: str = "",
    document_workspace_base_url: str = "",
    decision_brief_override: Optional[Dict[str, Any]] = None,
    job_summary_override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    source_url = (
        job.get("sourceurl")
        or job.get("link")
        or job.get("source_url")
        or ""
    )
    application_url = job.get("applicationUrl") or job.get("application_url") or ""
    session_manifest_path = job_dir / "apply_session.json"
    cover_letter_draft_path = job_dir / "cover_letter_draft.txt"
    cover_letter_docx_path = job_dir / "08_cover_letter.docx"
    screening_answers_docx_path = job_dir / "09_screening_answers.docx"
    tailored_resume_pdf_path = job_dir / "10_tailored_resume.pdf"
    tailored_resume_json_path = job_dir / "10_tailored_resume.json"
    authoring_state = _coerce_authoring_state(
        authoring_state or {},
        job_id=job_id,
        job_dir=job_dir,
    )
    reactive_resume_base_url = _clean_authoring_text(reactive_resume_base_url).rstrip("/")
    document_workspace_base_url = _clean_authoring_text(document_workspace_base_url).rstrip("/")
    resume_handoff_brief = _build_resume_handoff_brief(
        job=job,
        pack=pack,
        match=match,
        moderator=moderator,
    )
    cover_letter_handoff_brief = _build_cover_letter_handoff_brief(
        job=job,
        pack=pack,
        match=match,
    )
    screening_handoff_brief = _build_screening_handoff_brief(
        job=job,
        pack=pack,
        match=match,
    )

    final_cover_letter_text = cover_letter_draft or pack.get("cover_letter_text") or ""
    cv_highlights = [str(item) for item in (pack.get("cv_highlights") or []) if item]
    evidence_map = [str(item) for item in (pack.get("evidence_map") or []) if item]
    gap_mitigations = [str(item) for item in (pack.get("gap_mitigations") or []) if item]
    interview_prep = [str(item) for item in (pack.get("interview_prep") or []) if item]
    overlaps = [str(item) for item in (match.get("overlaps") or []) if item]
    gaps = [str(item) for item in (match.get("gaps") or []) if item]
    cv_focus = [str(item) for item in (moderator.get("cv_focus") or []) if item]

    save_targets = {
        "session_manifest": _path_entry(
            session_manifest_path,
            label="Apply session manifest",
            purpose="Local launch/saveback contract for this application case.",
        ),
        "cover_letter_draft_txt": _path_entry(
            cover_letter_draft_path,
            label="Cover-letter draft (.txt)",
            purpose="Autosaved working draft from the JobPipe application workspace.",
        ),
        "cover_letter_docx": _path_entry(
            cover_letter_docx_path,
            label="Cover letter (.docx)",
            purpose="Manual or AI-assisted final cover letter for submission.",
        ),
        "screening_answers_docx": _path_entry(
            screening_answers_docx_path,
            label="Screening answers (.docx)",
            purpose="Saved answers for screening questions or extra employer prompts.",
        ),
        "tailored_resume_pdf": _path_entry(
            tailored_resume_pdf_path,
            label="Tailored resume (.pdf)",
            purpose="Final exported CV variant ready for upload.",
        ),
        "tailored_resume_json": _path_entry(
            tailored_resume_json_path,
            label="Tailored resume source (.json)",
            purpose="Structured resume export or variant metadata from the authoring tool.",
        ),
    }
    built_decision_brief = build_decision_brief(
        final_decision=moderator.get("final_decision", ""),
        fit_score=match.get("fit_score"),
        pivot_score=pivot.get("pivot_score"),
        overlaps=overlaps,
        gaps=gaps,
        top_value_props=[str(item) for item in (pack.get("top_value_props") or []) if item],
        cv_focus=cv_focus,
        cover_letter_angle=pack.get("cover_letter_angle", ""),
    )
    decision_brief = (
        decision_brief_override
        if isinstance(decision_brief_override, dict) and decision_brief_override.get("schema_version")
        else built_decision_brief
    )
    authoring_briefs = {
        "resume": build_authoring_brief(
            artifact_kind="resume",
            objective="Create a tailored CV variant, then export PDF and structured source back to the save targets.",
            handoff_brief=resume_handoff_brief,
            launch_url=reactive_resume_base_url,
            inputs={
                "cvHighlights": cv_highlights,
                "topValueProps": [str(item) for item in (pack.get("top_value_props") or []) if item],
                "evidenceMap": evidence_map,
                "gapMitigations": gap_mitigations,
                "cvFocus": cv_focus,
            },
        ),
        "coverLetter": build_authoring_brief(
            artifact_kind="cover_letter",
            objective="Iterate on the cover letter in an external document environment, then save the final DOCX back to the target path.",
            handoff_brief=cover_letter_handoff_brief,
            launch_url=document_workspace_base_url,
            seed_text=final_cover_letter_text,
        ),
        "screeningAnswers": build_authoring_brief(
            artifact_kind="screening_answers",
            objective="Draft or refine screening answers using the same job context and save the final document back to the target path.",
            handoff_brief=screening_handoff_brief,
            launch_url=document_workspace_base_url,
            inputs={
                "topValueProps": [str(item) for item in (pack.get("top_value_props") or []) if item],
                "interviewPrep": interview_prep,
                "overlaps": overlaps,
                "gaps": gaps,
            },
        ),
    }
    artifact_plan = build_artifact_plan_from_job_dir(
        job_dir=job_dir,
        save_targets=save_targets,
    )
    built_job_summary = build_case_job_summary(
        title=job.get("title", ""),
        company=job.get("employer_name", job.get("company", "")),
        location=", ".join(part for part in [job.get("work_city", ""), job.get("work_county", "")] if part),
        job_source=job.get("job_source", "jobpipe"),
        source_url=source_url,
        application_url=application_url,
        application_due=job.get("applicationDue", ""),
        description_snippet=job.get("description_snip", ""),
    )
    job_summary = (
        job_summary_override
        if isinstance(job_summary_override, dict) and job_summary_override.get("title")
        else built_job_summary
    )
    source_url = job_summary.get("source_url", "") or source_url
    application_url = job_summary.get("application_url", "") or application_url
    open_urls = []
    for label, url in (
        ("job_ad", source_url),
        ("application_portal", application_url),
    ):
        if url and not any(existing["url"] == url for existing in open_urls):
            open_urls.append({"label": label, "url": url})
    artifact_save_targets = artifact_plan.get("save_targets", {}) if isinstance(artifact_plan, dict) else {}

    def _save_target_path(key: str) -> str:
        target = artifact_save_targets.get(key, {})
        if isinstance(target, dict):
            return str(target.get("path") or "")
        return ""

    def _authoring_status(section_name: str, planned_status: str, saveback_keys: tuple[str, ...]) -> str:
        section_state = authoring_state.get(section_name, {})
        if not isinstance(section_state, dict):
            section_state = {}
        if (
            section_state.get("exportRef")
            or section_state.get("exportLabel")
            or section_state.get("exportUrl")
        ):
            return "export_registered"
        if any(section_state.get(key) for key in saveback_keys) or section_state.get("artifactRefs"):
            return "saveback_registered"
        return planned_status

    return {
        "sessionVersion": APPLY_SESSION_VERSION,
        "generatedAt": _utc_now_z(),
        "jobId": job_id,
        "artifactRoot": str(job_dir),
        "decisionBrief": decision_brief,
        "authoringBriefs": authoring_briefs,
        "artifactPlan": artifact_plan,
        "saveback": {
            "registrationEndpoint": f"/api/authoring/{job_id}",
            "statePath": authoring_state["statePath"],
        },
        "authoringState": authoring_state,
        "job": {
            "title": job_summary["title"],
            "employer": job_summary["company"],
            "location": job_summary["location"],
            "deadline": job_summary["application_due"],
            "sourceUrl": job_summary["source_url"],
            "applicationUrl": job_summary["application_url"],
        },
        "jobSummary": job_summary,
        "launch": {
            "openUrls": open_urls,
            "localWorkspaceUrl": f"/apply/{job_id}",
        },
        "analysis": {
            "finalDecision": decision_brief["final_decision"],
            "fitScore": decision_brief["fit_score"],
            "pivotScore": decision_brief["pivot_score"],
            "pivotType": pivot.get("pivot_type", ""),
            "pivotRisk": pivot.get("potential_risk", ""),
            "positioningHeadline": pack.get("positioning_headline", ""),
            "coverLetterAngle": decision_brief["cover_letter_angle"],
            "topValueProps": decision_brief["top_value_props"],
            "evidenceMap": evidence_map,
            "gapMitigations": gap_mitigations,
            "overlaps": decision_brief["overlaps"],
            "gaps": decision_brief["gaps"],
            "cvFocus": decision_brief["cv_focus"],
        },
        "authoring": {
            "resume": {
                "tool": "reactive_resume",
                "status": _authoring_status("resume", "external_planned", ("variantRef", "sourceUrl")),
                "objective": authoring_briefs["resume"]["objective"],
                "launchUrl": authoring_briefs["resume"]["launch_url"],
                "handoffBrief": authoring_briefs["resume"]["handoff_brief"],
                "inputs": authoring_briefs["resume"]["inputs"],
                "registeredState": authoring_state["resume"],
                "saveTargets": {
                    "pdf": _save_target_path("tailored_resume_pdf"),
                    "json": _save_target_path("tailored_resume_json"),
                },
            },
            "coverLetter": {
                "tool": "document_workspace",
                "status": _authoring_status("coverLetter", "local_seed_ready", ("documentRef", "sourceUrl")),
                "objective": authoring_briefs["coverLetter"]["objective"],
                "seedText": authoring_briefs["coverLetter"]["seed_text"],
                "launchUrl": authoring_briefs["coverLetter"]["launch_url"],
                "handoffBrief": authoring_briefs["coverLetter"]["handoff_brief"],
                "registeredState": authoring_state["coverLetter"],
                "saveTargets": {
                    "draftTxt": _save_target_path("cover_letter_draft_txt"),
                    "docx": _save_target_path("cover_letter_docx"),
                },
            },
            "screeningAnswers": {
                "tool": "document_workspace",
                "status": _authoring_status("screeningAnswers", "context_ready", ("documentRef", "sourceUrl")),
                "objective": authoring_briefs["screeningAnswers"]["objective"],
                "launchUrl": authoring_briefs["screeningAnswers"]["launch_url"],
                "handoffBrief": authoring_briefs["screeningAnswers"]["handoff_brief"],
                "context": authoring_briefs["screeningAnswers"]["inputs"],
                "registeredState": authoring_state["screeningAnswers"],
                "saveTargets": {
                    "docx": _save_target_path("screening_answers_docx"),
                },
            },
        },
        "saveTargets": artifact_save_targets,
    }


def _build_pack_payload(
    *,
    job_id: str,
    ctx: Dict[str, Any],
) -> Dict[str, Any]:
    inp = ctx.get("job", {})
    pack = ctx.get("pack", {})
    match = ctx.get("match", {})
    pivot = ctx.get("pivot", {})
    moderator = ctx.get("moderator", {})
    detail_projection = ctx.get("detail_projection", {})
    if not isinstance(inp, dict):
        inp = {}
    if not isinstance(pack, dict):
        pack = {}
    if not isinstance(match, dict):
        match = {}
    if not isinstance(pivot, dict):
        pivot = {}
    if not isinstance(moderator, dict):
        moderator = {}
    if not isinstance(detail_projection, dict):
        detail_projection = {}

    projection_job_summary_value = projection_job_summary(detail_projection)
    projection_decision_brief_value = projection_decision_brief(detail_projection)

    built_job_summary = build_case_job_summary(
        title=inp.get("title", ""),
        company=inp.get("employer_name", inp.get("company", "")),
        location=", ".join(part for part in [inp.get("work_city", ""), inp.get("work_county", "")] if part),
        job_source=inp.get("job_source", inp.get("source", "jobpipe")),
        source_url=inp.get("sourceurl") or inp.get("link") or inp.get("source_url", ""),
        application_url=inp.get("applicationUrl") or inp.get("application_url", ""),
        application_due=inp.get("applicationDue", ""),
        description_snippet=(inp.get("description") or "")[:600],
    )
    job_summary = (
        projection_job_summary_value
        if projection_job_summary_value.get("title")
        else built_job_summary
    )
    built_decision_brief = build_decision_brief(
        final_decision=moderator.get("final_decision", ""),
        fit_score=match.get("fit_score"),
        pivot_score=pivot.get("pivot_score"),
        overlaps=match.get("overlaps", []),
        gaps=match.get("gaps", []),
        top_value_props=[str(item) for item in (pack.get("top_value_props") or []) if item],
        cv_focus=[str(item) for item in (moderator.get("cv_focus") or []) if item],
        cover_letter_angle=pack.get("cover_letter_angle", ""),
    )
    decision_brief = (
        projection_decision_brief_value
        if projection_decision_brief_value.get("schema_version")
        else built_decision_brief
    )

    overlaps = decision_brief.get("overlaps", []) if isinstance(decision_brief, dict) else []
    gaps = decision_brief.get("gaps", []) if isinstance(decision_brief, dict) else []
    if not overlaps:
        overlaps = match.get("overlaps", [])
    if not gaps:
        gaps = match.get("gaps", [])

    return {
        "job_id": job_id,
        "job": {
            "title": job_summary.get("title", ""),
            "employer": job_summary.get("company", ""),
            "source_url": job_summary.get("source_url", ""),
            "application_url": job_summary.get("application_url", ""),
            "deadline": job_summary.get("application_due", ""),
            "description_snip": job_summary.get("description_snippet", ""),
        },
        "jobSummary": job_summary,
        "decisionBrief": decision_brief,
        "pack": pack,
        "overlaps": overlaps,
        "gaps": gaps,
        "has_docx": bool(ctx.get("has_docx")),
        "cover_letter_draft": ctx.get("cover_letter_draft", ""),
        "job_dir": str(ctx.get("job_dir", "")),
    }


def _persist_apply_session_manifest(job_dir: Path, manifest: Dict[str, Any]) -> Dict[str, Any]:
    manifest_path = job_dir / "apply_session.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def _load_workspace_context(job_id: str) -> Optional[Dict[str, Any]]:
    job_dir = _find_job_run_dir(job_id)
    if not job_dir:
        return None

    input_payload: Dict[str, Any] = {}
    bundle = load_job_projection_bundle(
        PATHS.projection_store_path,
        run_id=job_dir.parent.name,
        job_id=job_id,
    )
    input_projection = projection_bundle_input_enrichment(bundle)
    detail_projection = projection_bundle_detail_projection(bundle)
    input_path = job_dir / "00_input.json"
    if input_path.exists():
        raw = json.loads(input_path.read_text(encoding="utf-8"))
        input_payload = raw.get("job", raw)
    else:
        input_payload = build_projected_job_input(
            job_id=job_id,
            input_projection=input_projection,
            detail_projection=detail_projection,
        )

    projection_decision_brief_value = projection_decision_brief(detail_projection)

    pack = _read_stage_json(job_dir, "application_pack")
    if not pack:
        draft_path = job_dir / "application_pack_draft.json"
        if draft_path.exists():
            pack = json.loads(draft_path.read_text(encoding="utf-8"))
        elif projection_decision_brief_value:
            pack = {
                "positioning_headline": projection_decision_brief_value.get("positioning_angle", ""),
                "top_value_props": projection_decision_brief_value.get("top_value_props", []),
                "evidence_map": [],
                "gap_mitigations": [],
                "cover_letter_angle": projection_decision_brief_value.get("cover_letter_angle", ""),
                "cover_letter_text": "",
                "interview_prep": [],
                "cv_highlights": [],
            }

    match = _read_stage_json(job_dir, "profile_match")
    if not match and projection_decision_brief_value:
        match = {
            "fit_score": projection_decision_brief_value.get("fit_score"),
            "overlaps": projection_decision_brief_value.get("overlaps", []),
            "gaps": projection_decision_brief_value.get("gaps", []),
        }

    pivot = _read_stage_json(job_dir, "pivot")
    if not pivot and projection_decision_brief_value:
        pivot = {
            "pivot_score": projection_decision_brief_value.get("pivot_score"),
        }

    moderator = _read_stage_json(job_dir, "moderator")
    if not moderator and projection_decision_brief_value:
        moderator = {
            "final_decision": projection_decision_brief_value.get("final_decision", ""),
            "cv_focus": projection_decision_brief_value.get("cv_focus", []),
            "recommendation_reason": projection_decision_brief_value.get("rationale", ""),
        }

    cover_letter_draft = ""
    cover_letter_draft_path = job_dir / "cover_letter_draft.txt"
    if cover_letter_draft_path.exists():
        cover_letter_draft = cover_letter_draft_path.read_text(encoding="utf-8")

    return {
        "job_dir": job_dir,
        "job": input_payload,
        "pack": pack,
        "match": match,
        "pivot": pivot,
        "moderator": moderator,
        "detail_projection": detail_projection,
        "has_docx": (job_dir / "07_cv_highlights.docx").exists(),
        "cover_letter_draft": cover_letter_draft,
    }


# ── HTTP handler ──────────────────────────────────────────────────────────────

class DashboardHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        # Minimal logging — only errors
        if args and str(args[1]) not in ("200", "204"):
            print(f"[server] {self.path} {args[1]}", file=sys.stderr)

    # ── Helpers ──

    def _send_json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str, status: int = 200) -> None:
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")

    def _read_body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", 0))
            if not length:
                return {}
            return json.loads(self.rfile.read(length))
        except Exception:
            return {}

    # ── CORS preflight ──

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # ── GET ──

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path in ("/", "/dashboard"):
            self._get_dashboard()

        elif path == "/api/data":
            self._get_data()

        elif path == "/api/gen_status":
            job_id = (params.get("job_id") or [""])[0]
            with _gen_lock:
                status = _gen_status.get(job_id, "idle")
            self._send_json({"job_id": job_id, "status": status})

        elif path.startswith("/apply/"):
            job_id = path[len("/apply/"):].strip("/")
            self._get_apply_workspace(job_id)

        elif path.startswith("/api/pack/"):
            job_id = path[len("/api/pack/"):].strip("/")
            self._get_pack(job_id)

        elif path.startswith("/api/apply_session/"):
            job_id = path[len("/api/apply_session/"):].strip("/")
            self._get_apply_session(job_id)

        elif path.startswith("/api/authoring/"):
            job_id = path[len("/api/authoring/"):].strip("/")
            self._get_authoring(job_id)

        elif path.startswith("/api/draft/"):
            job_id = path[len("/api/draft/"):].strip("/")
            self._get_draft(job_id)

        elif path.startswith("/api/jobs/") and path.endswith("/authoring-session"):
            job_id = path[len("/api/jobs/"):-len("/authoring-session")].strip("/")
            self._get_authoring_session(job_id)

        elif path.startswith("/api/jobs/") and path.endswith("/prepare-application/status"):
            job_id = path[len("/api/jobs/"):-len("/prepare-application/status")].strip("/")
            self._get_prepare_application_status(job_id)

        elif path == "/api/resume":
            self._get_resume()

        elif path == "/api/gmail/status":
            self._send_json(_gmail_oauth_status())

        elif path.startswith("/download/"):
            # /download/<job_id>/filename.ext
            parts = path[len("/download/"):].strip("/").split("/", 1)
            job_id = parts[0] if parts else ""
            filename = parts[1] if len(parts) > 1 else ""
            self._download_file(job_id, filename)

        else:
            self._send_json({"error": "Not found"}, 404)

    def _get_dashboard(self):
        try:
            from jobpipe.cli.export_dashboard import build_dashboard_html
            marker = (
                f'<meta name="jobpipe-server" content="1">'
                f'<meta name="jobpipe-port" content="{PORT}">'
            )
            html, _payload = build_dashboard_html(
                SQLITE_PATH,
                OUT_RUNS,
                TEMPLATE_PATH,
                state_path=STATE_PATH,
                config_path=CONFIG_PATH,
                config_overlays=CONFIG_OVERLAYS,
                profile_path=PROFILE_PATH,
                resume_path=RESUME_PATH,
                profile_draft_path=PROFILE_DRAFT_PATH,
                settings_path=SETTINGS_STATE_PATH,
                head_injection=marker,
            )
            self._send_html(html)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _get_data(self):
        """Return fresh payload from SQLite — no HTML rebuild needed."""
        try:
            from jobpipe.cli.export_dashboard import build_payload
            payload = build_payload(
                SQLITE_PATH,
                OUT_RUNS,
                state_path=STATE_PATH,
                config_path=CONFIG_PATH,
                config_overlays=CONFIG_OVERLAYS,
                profile_path=PROFILE_PATH,
                resume_path=RESUME_PATH,
                profile_draft_path=PROFILE_DRAFT_PATH,
                settings_path=SETTINGS_STATE_PATH,
            )
            self._send_json(payload)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    # ── POST ──

    def do_POST(self):
        path = urlparse(self.path).path
        body = self._read_body()

        if path == "/api/status":
            self._post_status(body)
        elif path == "/api/notes":
            self._post_notes(body)
        elif path == "/api/profile_draft":
            self._post_profile_draft(body)
        elif path == "/api/settings":
            self._post_settings(body)
        elif path == "/api/experiment_review":
            self._post_experiment_review(body)
        elif path == "/api/experiment_variant_review":
            self._post_experiment_variant_review(body)
        elif path == "/api/experiment_promotion_review":
            self._post_experiment_promotion_review(body)
        elif path == "/api/generate":
            self._post_generate(body)
        elif path == "/api/automation/run":
            self._post_automation_run(body)
        elif path == "/api/rebuild":
            self._post_rebuild()
        elif path.startswith("/api/authoring/"):
            job_id = path[len("/api/authoring/"):].strip("/")
            self._post_authoring(job_id, body)
        elif path.startswith("/api/draft/"):
            job_id = path[len("/api/draft/"):].strip("/")
            self._post_draft(job_id, body)
        elif path == "/api/chat":
            self._post_chat(body)
        elif path == "/api/gmail/authorize":
            self._post_gmail_authorize()
        elif path.startswith("/api/jobs/") and path.endswith("/prepare-application"):
            job_id = path[len("/api/jobs/"):-len("/prepare-application")].strip("/")
            self._post_prepare_application(job_id, body)
        elif path.startswith("/api/jobs/") and path.endswith("/authoring-chat"):
            job_id = path[len("/api/jobs/"):-len("/authoring-chat")].strip("/")
            self._post_authoring_chat(job_id, body)
        elif path.startswith("/api/jobs/") and "/authoring-patch/" in path and path.endswith("/accept"):
            parts = path[len("/api/jobs/"):].strip("/").split("/authoring-patch/")
            job_id = parts[0].strip("/")
            patch_id = parts[1].replace("/accept", "").strip("/") if len(parts) > 1 else ""
            self._post_authoring_patch_accept(job_id, patch_id)
        elif path.startswith("/api/jobs/") and "/authoring-patch/" in path and path.endswith("/reject"):
            parts = path[len("/api/jobs/"):].strip("/").split("/authoring-patch/")
            job_id = parts[0].strip("/")
            patch_id = parts[1].replace("/reject", "").strip("/") if len(parts) > 1 else ""
            self._post_authoring_patch_reject(job_id, patch_id)
        else:
            self._send_json({"error": "Not found"}, 404)

    def _post_status(self, body: dict):
        job_id = body.get("job_id", "")
        token = body.get("token", "")
        notes = body.get("notes", "")
        if not job_id or not token:
            self._send_json({"error": "job_id and token required"}, 400)
            return
        try:
            from jobpipe.cli.mark_status import add_stage
            add_stage(
                job_id=job_id,
                token=token,
                state_path=STATE_PATH,
                notes=notes,
                source="manual",
            )
            self._send_json({"ok": True, "job_id": job_id, "token": token})
        except SystemExit as e:
            self._send_json({"error": f"Invalid token: {token}"}, 400)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _post_notes(self, body: dict):
        job_id = body.get("job_id", "")
        notes = body.get("notes", "")
        if not job_id:
            self._send_json({"error": "job_id required"}, 400)
            return
        try:
            _persist_application_notes(STATE_PATH, job_id, notes)
            self._send_json({"ok": True, "job_id": job_id})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _post_generate(self, body: dict):
        job_id = body.get("job_id", "")
        if not job_id:
            self._send_json({"error": "job_id required"}, 400)
            return
        with _gen_lock:
            if _gen_status.get(job_id) == "running":
                self._send_json({"ok": True, "status": "already_running", "job_id": job_id})
                return
            _gen_status[job_id] = "running"
        t = threading.Thread(target=_run_generation, args=(job_id,), daemon=True)
        t.start()
        self._send_json({"ok": True, "status": "started", "job_id": job_id})

    def _post_profile_draft(self, body: dict):
        draft = body.get("draft", {})
        if not isinstance(draft, dict):
            self._send_json({"error": "draft must be an object"}, 400)
            return
        try:
            clean = _persist_profile_draft(PROFILE_DRAFT_PATH, draft)
            self._send_json({"ok": True, "fields": len(clean)})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _post_settings(self, body: dict):
        settings = body.get("settings", {})
        if not isinstance(settings, dict):
            self._send_json({"error": "settings must be an object"}, 400)
            return
        try:
            clean = _persist_settings_payload(SETTINGS_STATE_PATH, settings)
            self._send_json({"ok": True, "updated_at": clean.get("updated_at", "")})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _post_experiment_review(self, body: dict):
        experiment_id = str(body.get("experiment_id") or "").strip()
        job_id = str(body.get("job_id") or "").strip()
        verdict = str(body.get("verdict") or "").strip()
        note = str(body.get("note") or "").strip()
        run_id = str(body.get("run_id") or "").strip()
        review_reason = str(body.get("review_reason") or "").strip()
        review_priority_raw = body.get("review_priority")
        if not experiment_id or not job_id:
            self._send_json({"error": "experiment_id and job_id required"}, 400)
            return
        try:
            review_priority = int(review_priority_raw or 0)
        except Exception:
            review_priority = 0
        try:
            entry = _persist_experiment_review(
                EXPERIMENT_REVIEW_STATE_PATH,
                experiment_id=experiment_id,
                job_id=job_id,
                verdict=verdict,
                note=note,
                run_id=run_id,
                review_reason=review_reason,
                review_priority=review_priority,
            )
            self._send_json({"ok": True, "review": entry, "job_id": job_id, "experiment_id": experiment_id})
        except ValueError as e:
            self._send_json({"error": str(e)}, 400)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _post_experiment_variant_review(self, body: dict):
        experiment_id = str(body.get("experiment_id") or "").strip()
        verdict = str(body.get("verdict") or "").strip()
        note = str(body.get("note") or "").strip()
        candidate_name = str(body.get("candidate_name") or "").strip()
        kind = str(body.get("kind") or "").strip()
        if not experiment_id:
            self._send_json({"error": "experiment_id required"}, 400)
            return
        try:
            entry = _persist_experiment_variant_review(
                EXPERIMENT_REVIEW_STATE_PATH,
                experiment_id=experiment_id,
                verdict=verdict,
                note=note,
                candidate_name=candidate_name,
                kind=kind,
            )
            self._send_json({"ok": True, "variant_review": entry, "experiment_id": experiment_id})
        except ValueError as e:
            self._send_json({"error": str(e)}, 400)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _post_experiment_promotion_review(self, body: dict):
        experiment_id = str(body.get("experiment_id") or "").strip()
        verdict = str(body.get("verdict") or "").strip()
        note = str(body.get("note") or "").strip()
        candidate_name = str(body.get("candidate_name") or "").strip()
        kind = str(body.get("kind") or "").strip()
        if not experiment_id:
            self._send_json({"error": "experiment_id required"}, 400)
            return
        try:
            entry = _persist_experiment_promotion_review(
                EXPERIMENT_REVIEW_STATE_PATH,
                experiment_id=experiment_id,
                verdict=verdict,
                note=note,
                candidate_name=candidate_name,
                kind=kind,
            )
            self._send_json({"ok": True, "promotion_review": entry, "experiment_id": experiment_id})
        except ValueError as e:
            self._send_json({"error": str(e)}, 400)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _post_automation_run(self, body: dict):
        action_key = str(body.get("action_key") or "").strip()
        if not action_key:
            self._send_json({"error": "action_key required"}, 400)
            return
        try:
            run = _start_automation_run(action_key)
            if not run:
                self._send_json({"error": f"Unknown automation action: {action_key}"}, 404)
                return
            self._send_json(
                {
                    "ok": True,
                    "run": run,
                    "automations": build_automation_payload(PATHS, state_path=AUTOMATION_STATE_PATH),
                }
            )
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _get_authoring(self, job_id: str):
        job_dir = _find_job_run_dir(job_id)
        if not job_dir:
            self._send_json({"error": "Job not found"}, 404)
            return
        try:
            self._send_json(_load_authoring_state(job_dir, job_id))
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _post_authoring(self, job_id: str, body: dict):
        job_dir = _find_job_run_dir(job_id)
        if not job_dir:
            self._send_json({"error": "Job not found"}, 404)
            return
        if not isinstance(body, dict):
            self._send_json({"error": "body must be an object"}, 400)
            return
        try:
            state = _persist_authoring_state(job_dir, job_id, body)
            jobsync_sync = sync_authoring_state(PATHS, job_id, state)
            self._send_json({"ok": True, "authoringState": state, "jobsyncSync": jobsync_sync})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _get_apply_workspace(self, job_id: str):
        """Serve the application writing workspace for a specific job."""
        workspace_path = APPLY_TEMPLATE_PATH
        if not workspace_path.exists():
            self._send_html(
                "<h1>apply_template.html not found</h1>"
                "<p>The application workspace template is missing from the tracked repo reports/ directory.</p>",
                503,
            )
            return
        try:
            html = workspace_path.read_text(encoding="utf-8")
            marker = (
                f'<meta name="jobpipe-server" content="1">'
                f'<meta name="jobpipe-port" content="{PORT}">'
                f'<meta name="jobpipe-job-id" content="{job_id}">'
            )
            html = html.replace("</head>", marker + "\n</head>", 1)
            self._send_html(html)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _get_pack(self, job_id: str):
        """Return parsed application pack data for a job."""
        ctx = _load_workspace_context(job_id)
        if not ctx:
            self._send_json({"error": "Job not found"}, 404)
            return
        try:
            self._send_json(_build_pack_payload(job_id=job_id, ctx=ctx))
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _get_apply_session(self, job_id: str):
        ctx = _load_workspace_context(job_id)
        if not ctx:
            self._send_json({"error": "Job not found"}, 404)
            return
        try:
            authoring_state = _load_authoring_state(ctx["job_dir"], job_id)
            settings_state = load_settings_state(SETTINGS_STATE_PATH)
            reactive_resume = (settings_state.get("integrations", {}) or {}).get("reactive_resume", {}) or {}
            reactive_resume_base_url = (
                reactive_resume.get("base_url", "")
                if reactive_resume.get("enabled")
                else ""
            )
            document_workspace = (settings_state.get("integrations", {}) or {}).get("document_workspace", {}) or {}
            document_workspace_base_url = (
                document_workspace.get("base_url", "")
                if document_workspace.get("enabled")
                else ""
            )
            detail_projection = ctx.get("detail_projection", {})
            projection_job_summary_value = projection_job_summary(detail_projection)
            projection_decision_brief_value = projection_decision_brief(detail_projection)
            manifest = _build_apply_session_manifest(
                job_id=job_id,
                job_dir=ctx["job_dir"],
                job=ctx["job"],
                pack=ctx["pack"],
                match=ctx["match"],
                pivot=ctx["pivot"],
                moderator=ctx["moderator"],
                cover_letter_draft=ctx["cover_letter_draft"],
                authoring_state=authoring_state,
                reactive_resume_base_url=reactive_resume_base_url,
                document_workspace_base_url=document_workspace_base_url,
                decision_brief_override=projection_decision_brief_value,
                job_summary_override=projection_job_summary_value,
            )
            _persist_apply_session_manifest(ctx["job_dir"], manifest)
            self._send_json(manifest)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _get_resume(self):
        """Return the parsed resume.json."""
        resume_path = RESUME_PATH
        if not resume_path.exists():
            resume_path = RESUME_FIXED_PATH
        if not resume_path.exists():
            self._send_json({"error": f"resume.json not found under {PATHS.reports_dir}"}, 404)
            return
        try:
            self._send_json(json.loads(resume_path.read_text(encoding="utf-8")))
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _get_draft(self, job_id: str):
        job_dir = _find_job_run_dir(job_id)
        if not job_dir:
            self._send_json({"draft": ""})
            return
        p = job_dir / "cover_letter_draft.txt"
        self._send_json({"draft": p.read_text(encoding="utf-8") if p.exists() else ""})

    def _post_draft(self, job_id: str, body: dict):
        job_dir = _find_job_run_dir(job_id)
        if not job_dir:
            self._send_json({"error": "Job not found"}, 404)
            return
        try:
            text = body.get("cover_letter", "")
            (job_dir / "cover_letter_draft.txt").write_text(text, encoding="utf-8")
            self._send_json({"ok": True})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _download_file(self, job_id: str, filename: str):
        """Serve a binary file from the job's run directory."""
        # Safety: only allow specific file types
        allowed = {".docx", ".pdf", ".txt", ".json"}
        if not any(filename.endswith(ext) for ext in allowed):
            self._send_json({"error": "File type not allowed"}, 403)
            return
        job_dir = _find_job_run_dir(job_id)
        if not job_dir:
            self._send_json({"error": "Job not found"}, 404)
            return
        fpath = job_dir / filename
        # If a .docx is requested but doesn't exist, fall back to cover_letter_draft.txt
        if not fpath.exists() and filename == "08_cover_letter.docx":
            txt_path = job_dir / "cover_letter_draft.txt"
            if txt_path.exists():
                data = txt_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Content-Disposition", 'attachment; filename="cover_letter.txt"')
                self._cors()
                self.end_headers()
                self.wfile.write(data)
                return
        if not fpath.exists():
            self._send_json({"error": f"{filename} not found for this job"}, 404)
            return
        try:
            data = fpath.read_bytes()
            content_type = {
                ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ".pdf": "application/pdf",
                ".txt": "text/plain; charset=utf-8",
                ".json": "application/json; charset=utf-8",
            }.get(fpath.suffix, "application/octet-stream")
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self._cors()
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _post_chat(self, body: dict):
        """Proxy chat messages to OpenAI with job context as system prompt."""
        from jobpipe.authoring.cover_letter_generator import _banned_violations
        job_id = body.get("job_id", "")
        messages = body.get("messages", [])  # [{role, content}, ...]
        if not messages:
            self._send_json({"error": "messages required"}, 400)
            return
        try:
            last_user_msg = messages[-1].get("content", "") if messages else ""
            prior_msgs = messages[:-1]

            # Gate: if this is a first-turn cover letter request and we have no
            # narrative_why_me_now, return the motivation question directly —
            # never let the LLM embed instruction text in the letter body.
            if _is_cover_letter_request(last_user_msg) and not prior_msgs:
                has_narrative = bool(_read_narrative_why_me_now(job_id))
                if not has_narrative:
                    self._send_json({
                        "reply": (
                            "Hva er det ved akkurat denne rollen og denne arbeidsgiveren "
                            "som motiverer deg nå? Og hvorfor søker du akkurat nå — "
                            "hva skjedde eller endret seg for deg i det siste?"
                        )
                    })
                    return

            # Load job context for system prompt
            system = _build_chat_system_prompt(job_id)

            from openai import OpenAI
            from jobpipe.core.io import load_env_file
            load_env_file(PATHS.env_file)
            client = OpenAI()

            api_messages = [{"role": "system", "content": system}] + messages

            # Chain-of-thought pass: only when prior conversation exists
            if _is_cover_letter_request(last_user_msg) and prior_msgs:
                cot = _run_cot_pass(client, system, prior_msgs)
                if cot:
                    api_messages.append({"role": "assistant", "content": cot})
                    api_messages.append({
                        "role": "user",
                        "content": (
                            "Skriv nå motivasjonsbrevet basert på verdivurderingen over og "
                            "kandidatens svar i samtalen. Følg alle regler i systempromptet."
                        ),
                    })

            reply = ""
            for _attempt in range(3):
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=api_messages,
                    temperature=0.4,
                    max_tokens=1200,
                )
                reply = response.choices[0].message.content or ""
                violations = _banned_violations(reply)
                if not violations:
                    break
                correction = (
                    f"Svaret ditt inneholdt disse totalforbudte frasene: {violations}. "
                    "Disse er forbudt selv om de finnes i evidensdata. Skriv om uten dem — "
                    "bruk konkrete selskaps-, team- eller prosjektnavn i stedet."
                )
                api_messages.append({"role": "assistant", "content": reply})
                api_messages.append({"role": "user", "content": correction})

            self._send_json({"reply": reply})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _get_prepare_application_status(self, job_id: str):
        with _prep_lock:
            status = dict(_prep_status.get(job_id, {"status": "idle", "message": "", "outputs": {}}))
        self._send_json(status)

    def _post_prepare_application(self, job_id: str, body: dict):
        model = body.get("model") or "gpt-4o"
        with _prep_lock:
            if (_prep_status.get(job_id) or {}).get("status") == "running":
                self._send_json({"ok": True, "status": "already_running"})
                return
            _prep_status[job_id] = {"status": "running", "message": "Starting...", "outputs": {}}
        t = threading.Thread(target=_run_prepare_application, args=(job_id, model), daemon=True)
        t.start()
        self._send_json({"ok": True, "status": "started"})

    def _get_authoring_session(self, job_id: str):
        job_dir = _find_job_run_dir(job_id)
        if not job_dir:
            self._send_json({"error": "Job not found"}, 404)
            return
        from jobpipe.authoring.session_store import get_or_create_session
        session = get_or_create_session(job_dir, job_id, "default")
        self._send_json(session.model_dump(mode="json"))

    def _post_authoring_chat(self, job_id: str, body: dict):
        message = body.get("message", "").strip()
        if not message:
            self._send_json({"error": "message required"}, 400)
            return
        job_dir = _find_job_run_dir(job_id)
        if not job_dir:
            self._send_json({"error": "Job not found"}, 404)
            return
        try:
            from jobpipe.authoring.session_store import (
                add_suggested_patch,
                append_chat_turn,
                get_or_create_session,
                save_session,
            )
            from jobpipe.model.schema import SuggestedPatch
            import uuid as _uuid

            session = get_or_create_session(job_dir, job_id, "default")

            # Gate: first-turn cover letter request with no narrative → return question directly
            is_first_turn = not any(
                t.get("role") == "assistant" for t in session.chat_history
            )
            if _is_cover_letter_request(message) and is_first_turn:
                has_narrative = bool(_read_narrative_why_me_now(job_id))
                if not has_narrative:
                    q = (
                        "Hva er det ved akkurat denne rollen og denne arbeidsgiveren "
                        "som motiverer deg nå? Og hvorfor søker du akkurat nå — "
                        "hva skjedde eller endret seg for deg i det siste?"
                    )
                    session = append_chat_turn(session, "user", message)
                    session = append_chat_turn(session, "assistant", q)
                    save_session(job_dir, session)
                    self._send_json({"reply": q, "patches": []})
                    return

            session = append_chat_turn(session, "user", message)

            system = _build_chat_system_prompt(job_id)
            messages_for_api = [{"role": "system", "content": system}]
            for turn in session.chat_history[:-1]:  # exclude the turn we just added
                messages_for_api.append({"role": turn["role"], "content": turn["content"]})
            messages_for_api.append({"role": "user", "content": message})

            from openai import OpenAI
            from jobpipe.core.io import load_env_file
            from jobpipe.authoring.cover_letter_generator import _banned_violations
            load_env_file(PATHS.env_file)
            client = OpenAI()

            # Chain-of-thought pass: only when prior conversation exists
            prior_turns = messages_for_api[1:-1]  # between system and last user msg
            if _is_cover_letter_request(message) and prior_turns:
                cot = _run_cot_pass(client, system, prior_turns)
                if cot:
                    messages_for_api.append({"role": "assistant", "content": cot})
                    messages_for_api.append({
                        "role": "user",
                        "content": (
                            "Skriv nå motivasjonsbrevet basert på verdivurderingen over og "
                            "kandidatens svar i samtalen. Følg alle regler i systempromptet."
                        ),
                    })

            reply = ""
            for _attempt in range(3):
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=messages_for_api,
                    temperature=0.4,
                    max_tokens=1200,
                )
                reply = response.choices[0].message.content or ""
                violations = _banned_violations(reply)
                if not violations:
                    break
                correction = (
                    f"Svaret ditt inneholdt disse totalforbudte frasene: {violations}. "
                    "Disse er forbudt selv om de finnes i evidensdata. Skriv om uten dem — "
                    "bruk konkrete selskaps-, team- eller prosjektnavn i stedet."
                )
                messages_for_api.append({"role": "assistant", "content": reply})
                messages_for_api.append({"role": "user", "content": correction})
            session = append_chat_turn(session, "assistant", reply)

            # Extract [PATCH: kind=..., section=...]...text...[/PATCH] markers, or wrap full reply
            import re as _re
            patch_re = _re.compile(
                r"\[PATCH:\s*kind=(?P<kind>\w+)(?:,\s*section=(?P<section>[^\]]+))?\]"
                r"(?P<text>.*?)\[/PATCH\]",
                _re.DOTALL,
            )
            patches = []
            for m in patch_re.finditer(reply):
                kind = m.group("kind").strip()
                if kind not in ("cover_letter", "summary", "headline", "section_bullet"):
                    kind = "cover_letter"
                patch = SuggestedPatch(
                    patch_id=str(_uuid.uuid4()),
                    kind=kind,
                    section_ref=(m.group("section") or "").strip(),
                    suggested_text=m.group("text").strip(),
                    created_at=session.updated_at,
                )
                session = add_suggested_patch(session, patch)
                patches.append(patch.model_dump(mode="json"))

            save_session(job_dir, session)
            self._send_json({"reply": reply, "patches": patches})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _post_authoring_patch_accept(self, job_id: str, patch_id: str):
        if not patch_id:
            self._send_json({"error": "patch_id required"}, 400)
            return
        job_dir = _find_job_run_dir(job_id)
        if not job_dir:
            self._send_json({"error": "Job not found"}, 404)
            return
        try:
            from jobpipe.authoring.session_store import accept_patch, load_session, save_session
            session = load_session(job_dir)
            if not session:
                self._send_json({"error": "No authoring session found"}, 404)
                return
            session = accept_patch(session, patch_id)
            save_session(job_dir, session)
            accepted = next(
                (p for p in session.accepted_patches if p.patch_id == patch_id), None
            )
            # If a cover_letter patch is accepted, also write it to cover_letter_draft.txt
            orig_patch = next(
                (p for p in session.suggested_patches if p.patch_id == patch_id), None
            )
            if orig_patch and orig_patch.kind == "cover_letter" and accepted:
                (job_dir / "cover_letter_draft.txt").write_text(
                    accepted.accepted_text, encoding="utf-8"
                )
            self._send_json({"ok": True, "accepted_patch": accepted.model_dump(mode="json") if accepted else None})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _post_authoring_patch_reject(self, job_id: str, patch_id: str):
        if not patch_id:
            self._send_json({"error": "patch_id required"}, 400)
            return
        job_dir = _find_job_run_dir(job_id)
        if not job_dir:
            self._send_json({"error": "Job not found"}, 404)
            return
        try:
            from jobpipe.authoring.session_store import load_session, reject_patch, save_session
            session = load_session(job_dir)
            if not session:
                self._send_json({"error": "No authoring session found"}, 404)
                return
            session = reject_patch(session, patch_id)
            save_session(job_dir, session)
            self._send_json({"ok": True})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _post_gmail_authorize(self):
        """Start Gmail OAuth setup in a background thread (opens browser consent)."""
        with _gmail_setup_lock:
            current = _gmail_setup_status.get("status", "idle")
        if current == "running":
            self._send_json({"ok": True, "status": "already_running", **_gmail_oauth_status()})
            return
        if not PATHS.gmail_credentials_path.exists():
            self._send_json(
                {
                    "error": "credentials_missing",
                    "message": f"Gmail credentials file not found at {PATHS.gmail_credentials_path}. "
                    "Download it from Google Cloud Console (OAuth2 Desktop App) and place it there, then retry.",
                },
                400,
            )
            return
        t = threading.Thread(target=_run_gmail_oauth_setup, daemon=True)
        t.start()
        self._send_json({"ok": True, "status": "started", **_gmail_oauth_status()})

    def _post_rebuild(self):
        try:
            from jobpipe.cli.export_dashboard import export
            export(
                SQLITE_PATH,
                OUT_RUNS,
                TEMPLATE_PATH,
                DASHBOARD_PATH,
                state_path=STATE_PATH,
                config_path=CONFIG_PATH,
                config_overlays=CONFIG_OVERLAYS,
                profile_path=PROFILE_PATH,
                resume_path=RESUME_PATH,
                profile_draft_path=PROFILE_DRAFT_PATH,
                settings_path=SETTINGS_STATE_PATH,
            )
            self._send_json({"ok": True, "message": "Dashboard rebuilt"})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)


# ── Background generation ─────────────────────────────────────────────────────

def _find_job_run_dir(job_id: str) -> Optional[Path]:
    """Find the most recent run directory that contains this job's artifacts."""
    if not OUT_RUNS.exists():
        return None
    candidates = []
    for run_dir in OUT_RUNS.iterdir():
        if not run_dir.is_dir():
            continue
        job_dir = run_dir / job_id
        if not job_dir.is_dir():
            continue
        bundle = load_job_projection_bundle(
            PATHS.projection_store_path,
            run_id=run_dir.name,
            job_id=job_id,
        )
        has_projection = bool(
            projection_bundle_input_enrichment(bundle)
            or projection_bundle_detail_projection(bundle)
        )
        has_runtime_artifacts = any(
            _find_stage_artifact(job_dir, stage_name)
            for stage_name in ("profile_match", "pivot", "moderator", "application_pack")
        )
        if (job_dir / "00_input.json").exists() or has_projection or has_runtime_artifacts:
            # Use mtime of the run directory as ordering key.
            candidates.append((run_dir.stat().st_mtime, job_dir))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def _find_stage_artifact(job_dir: Path, stage_name: str) -> Optional[Path]:
    names = {stage_name}
    for raw_name, canonical_name in _STAGE_ALIASES.items():
        if stage_name in (raw_name, canonical_name):
            names.add(raw_name)
            names.add(canonical_name)
    matches = sorted(
        path for path in job_dir.glob("*.json")
        if any(path.name.endswith(f"_{name}.json") for name in names)
    )
    return matches[-1] if matches else None


def _read_stage_json(job_dir: Path, stage_name: str) -> dict:
    path = _find_stage_artifact(job_dir, stage_name)
    if not path:
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _run_prepare_application(job_id: str, model: str) -> None:
    """Background worker: call prepare_application.main() in-process and record outputs."""
    try:
        from jobpipe.cli.prepare_application import main as _prep_main
        argv = [
            job_id,
            "--runtime-profile", "live_local",
            "--data-root", str(PATHS.data_root),
            "--model", model,
            "--ledger-sqlite", str(SQLITE_PATH),
        ]
        with _prep_lock:
            _prep_status[job_id] = {"status": "running", "message": "Generating CV patch and cover letter...", "outputs": {}}
        _prep_main(argv)
        exports = PATHS.data_root / "exports"
        outputs = {
            "cv_path": str(exports / f"reactive_resume_patched_{job_id}.json"),
            "letter_path": str(exports / f"cover_letter_{job_id}.md"),
            "audit_path": str(exports / f"tailoring_audit_{job_id}.json"),
        }
        with _prep_lock:
            _prep_status[job_id] = {"status": "done", "message": "Generation complete.", "outputs": outputs, "prepared_at": _utc_now_z()}
    except SystemExit as e:
        with _prep_lock:
            _prep_status[job_id] = {"status": "error", "message": str(e), "outputs": {}}
    except Exception as e:
        with _prep_lock:
            _prep_status[job_id] = {"status": "error", "message": str(e), "outputs": {}}


def _stage_output_path(job_dir: Path, cfg, stage_name: str) -> Path:
    order_raw = list(getattr(cfg, "stages", None) or _DEFAULT_STAGE_ORDER)
    order = [_STAGE_ALIASES.get(name, name) for name in order_raw]
    canonical_name = _STAGE_ALIASES.get(stage_name, stage_name)
    if canonical_name not in order:
        raise ValueError(f"Stage not configured: {canonical_name}")
    return job_dir / f"{order.index(canonical_name) + 1:02d}_{canonical_name}.json"


_COT_PROMPT_CHAT = """Du er en søknadsekspert. Du skal IKKE skrive et brev. Du skal gjøre en intern verdivurdering i punktform.

Svar KUN med korte analytiske punkter — ikke avsnitt, ikke brevtekst.

1. UTFORDRING: [én setning om arbeidsgiverens egentlige problem/veikryss]
2. VERDIFRAME:
   - [selskap/prosjekt A] → [hva arbeidsgiveren konkret får]
   - [selskap/prosjekt B] → [hva arbeidsgiveren konkret får]
   - [utdanning/modul] → [hva arbeidsgiveren konkret får]
3. POSISJONERING: [én setning om hva denne kandidaten har som de fleste søkere mangler]
4. ÅPNER: [én setning som åpner brevet med arbeidsgiverens situasjon — ingen «Jeg», ingen kandidatønske]
5. HVA ARBEIDSGIVEREN FÅR (oppsummert): [én setning]

Maks 150 ord totalt. Bare punkter."""

_COVER_LETTER_TRIGGERS = ("motivasjonsbrev", "søknadsbrev", "skriv brev", "skriv søknad")


def _read_narrative_why_me_now(job_id: str) -> str:
    """Return the narrative_why_me_now for a job if it looks like a real narrative, else ''."""
    try:
        job_dir = _find_job_run_dir(job_id)
        if not job_dir:
            return ""
        for fname in ("09_narrative_strategy_v3.json", "09_narrative_strategy.json"):
            nf = job_dir / fname
            if nf.exists():
                nd = json.loads(nf.read_text(encoding="utf-8"))
                val = str(nd.get("why_me_now") or "").strip()
                if len(val) >= 200 and val[-1] in ".!?»":
                    return val
                break
        for pfname in ("11_application_pack.json", "07_application_pack.json"):
            pf = job_dir / pfname
            if pf.exists():
                pd = json.loads(pf.read_text(encoding="utf-8"))
                val = str(pd.get("narrative_why_me_now") or "").strip()
                if len(val) >= 200 and val[-1] in ".!?»":
                    return val
                break
    except Exception:
        pass
    return ""


def _is_cover_letter_request(message: str) -> bool:
    """True when the user message is asking for a cover letter."""
    m = message.lower()
    return any(t in m for t in _COVER_LETTER_TRIGGERS)


def _run_cot_pass(client, system_prompt: str, messages_so_far: list) -> str:
    """
    Run a silent chain-of-thought value-reasoning pass before cover letter generation.
    Returns the reasoning text, or "" on failure.
    """
    try:
        cot_messages = [{"role": "system", "content": _COT_PROMPT_CHAT}]
        # Include the job context from the system prompt as a user turn
        cot_messages.append({"role": "user", "content": system_prompt})
        # Include any prior conversation (e.g. the user's why-now answer)
        for m in messages_so_far:
            if m.get("role") in ("user", "assistant"):
                cot_messages.append(m)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=cot_messages,
            temperature=0.3,
            max_tokens=500,
        )
        return (response.choices[0].message.content or "").strip()
    except Exception:
        return ""


def _build_chat_system_prompt(job_id: str) -> str:
    """Build a rich system prompt for the AI chat using the job's pipeline context."""
    base = (
        "Du er en norsk søknadsassistent. Du hjelper kandidaten med å skrive motivasjonsbrev og spisse CV-punkter.\n\n"
        "CV-en gjør den faktamessige tunge løftingen. Brevets oppgave er å svare på tre spørsmål rekrutterer har:\n"
        "1. Hvorfor vil du ha akkurat denne jobben?\n"
        "2. Hva er det ved denne rollen/arbeidsgiveren som treffer deg spesifikt?\n"
        "3. Hvorfor nå?\n\n"
        "Struktur (språklig bue — hvert avsnitt svarer på neste spørsmål rekrutterer stiller):\n"
        "- Avsnitt 1: Ramm inn ARBEIDSGIVERENS utfordring og hva rollen faktisk sitter i. "
        "IKKE begynn med «Jeg», IKKE begynn med kandidatens ønske eller motivasjon. "
        "Ikke «Å ha X som ønsket arbeidsgiver...». Vis at du forstår HVA JOBBEN ER.\n"
        "- Avsnitt 2: Operasjonelt bevis — navngi selskaper, prosjekter, verktøy. "
        "Minimum 3 konkrete navn. Vis at du KAN gjøre jobben.\n"
        "- Avsnitt 3 (hjerteavsnittet): Motivasjon — HVORFOR akkurat denne jobben, HVORFOR nå. "
        "Bruk kandidatens egne ord fra narrative_why_me_now om tilgjengelig. "
        "Koble BI-studier (modulnavn, prosjektnavn) til det arbeidsgiveren etterspør. Gap maks én setning.\n"
        "- Avsnitt 4 (valgfritt, maks 2 setninger): Ekte lokal eller personlig kontekst.\n\n"
        "AVSLUTNINGSFORBUD: Brevet skal IKKE ha en generisk avslutningssetning. "
        "Ingen «ser frem til», ingen «bidra til [selskapets] mål», ingen «kombinere erfaring med innsikt». "
        "Avslutt på noe konkret og initiativtakende — eller ikke avslutt med en egen avslutningssetning i det hele tatt.\n\n"
        "Absolutte regler:\n"
        "- BARE brevteksten. Ingen «Til [selskap]», ingen «Med vennlig hilsen», ingen [Navn]. 3–4 avsnitt.\n"
        "- Verdiframe: Hvert punkt svarer på «hva får arbeidsgiveren?», ikke «hva har jeg gjort?». "
        "Setninger starter ikke med «Jeg» — arbeidsgiveren er protagonisten. "
        "Snu fra selvbeskrivelse til levert verdi: ikke «Jeg har erfaring med X» men "
        "«X på tvers av Y markeder gir [arbeidsgiver] en kandidat som ikke trenger onboarding på Z». "
        "«Jeg» er tillatt som grammatisk lim midt i en setning, aldri som åpningsord.\n"
        "- Skriv bare fakta som finnes i CV-bevisene. Oppfinn ingenting. Kurs er ikke arbeidserfaring. "
        "BI Executive Master-moduler med prosjektnavn er substansiell evidens.\n"
        "- Hvert avsnitt MÅ inneholde minst 2–3 konkrete navn (selskap, prosjekt, verktøy) fra CV-bevisene.\n"
        "- HARD BLOCK — disse frasene er totalforbudt, selv om de finnes i job description eller evidence:\n"
        "  «tverrfaglige team», «tverrfaglig team», «tverrfaglig samarbeid», «kontinuerlig forbedring»,\n"
        "  «praktisk og resultatorientert», «skape verdi», «reell verdi», «brukervennlige løsninger»,\n"
        "  «interessenter», «endringsprosesser», «engasjert», «motivert for å bidra», «cross-functional»,\n"
        "  «offentlig sektor», «brenner for», «sterk kommunikator», «sterk teknisk forståelse»,\n"
        "  «sterk teknisk», «sterk forståelse», «sterke resultater», «sterk faglig»,\n"
        "  «helhetlige løsninger», «brukeren i sentrum», «brukerfokus»,\n"
        "  «robuste og fleksible løsninger», «ser frem til å bidra med min kompetanse»,\n"
        "  «ser frem til muligheten til å», «ser frem til å kunne», «ser frem til å bringe»,\n"
        "  «anvende min kompetanse», «bringe min kompetanse», «solid fundament for å bidra»,\n"
        "  «bidra til utviklingen av», «bidra til bane nors», «bidra til deres»,\n"
        "  «i en ny kontekst», «støtte deres mål om», «i deres mål om»,\n"
        "  «en spennende mulighet for meg», «kombinere min praktiske erfaring med»,\n"
        "  «selv om jeg ikke har eksplisitt erfaring», «selv om jeg ikke har direkte erfaring»,\n"
        "  «selv om jeg mangler direkte erfaring», «selv om jeg mangler eksplisitt erfaring»,\n"
        "  «rask til å tilpasse meg», «raskt å tilpasse meg», «raskt tilpasse meg»,\n"
        "  «bygge nødvendig domenekunnskap», «bygge nødvendig kunnskap»,\n"
        "  «tilegne meg ny domenekunnskap», «tilegne meg kunnskap om».\n"
        "  Skriv aldri disse ordene/frasene — bruk konkrete navn og fakta i stedet.\n"
        "- Aldri oppgi karakterer eller grades — nevn prosjektnavn og tema, ikke resultatet.\n"
        "- Gap nevnes maks én gang, i én setning, aldri i åpningen og aldri som eget avsnitt.\n"
        "- 3–4 avsnitt, 300–400 ord totalt. Cool professional register.\n\n"
    )

    # Load supplementary profile files if they exist alongside profile_pack
    _voice_guide = None
    _motivation_context = None
    try:
        from pathlib import Path as _Path
        _profile_dir = _Path(str(PROFILE_PATH)).parent
        _vg = _profile_dir / "cover_letter_voice.md"
        _mc = _profile_dir / "motivation.md"
        if _vg.exists():
            _voice_guide = _vg.read_text(encoding="utf-8")
        if _mc.exists():
            _motivation_context = _mc.read_text(encoding="utf-8")
    except Exception:
        pass
    ctx = _load_workspace_context(job_id)
    if not ctx:
        return base

    pack_payload = _build_pack_payload(job_id=job_id, ctx=ctx)
    job = pack_payload.get("job", {})
    pack = pack_payload.get("pack", {})
    decision_brief = pack_payload.get("decisionBrief", {})
    overlaps = pack_payload.get("overlaps", [])
    gaps = pack_payload.get("gaps", [])
    if not isinstance(job, dict):
        job = {}
    if not isinstance(pack, dict):
        pack = {}
    if not isinstance(decision_brief, dict):
        decision_brief = {}
    if not isinstance(overlaps, list):
        overlaps = []
    if not isinstance(gaps, list):
        gaps = []

    context_parts = [base]
    if job.get("title"):
        context_parts.append(f"**Stilling:** {job.get('title')} @ {job.get('employer', '')}")
    positioning_headline = pack.get("positioning_headline") or decision_brief.get("positioning_angle", "")
    if positioning_headline:
        context_parts.append(f"**Posisjoneringsoverskrift:** {positioning_headline}")
    cover_letter_angle = pack.get("cover_letter_angle") or decision_brief.get("cover_letter_angle", "")
    if cover_letter_angle:
        context_parts.append(f"**Søknadsvinkel:** {cover_letter_angle}")
    top_value_props = pack.get("top_value_props") or decision_brief.get("top_value_props") or []
    if top_value_props:
        context_parts.append("**Toppverdier:**\n" + "\n".join(f"- {v}" for v in top_value_props))
    if pack.get("evidence_map"):
        context_parts.append("**Bevis-kart:**\n" + "\n".join(f"- {e}" for e in pack["evidence_map"]))
    if pack.get("gap_mitigations"):
        context_parts.append("**Gap-håndtering:**\n" + "\n".join(f"- {g}" for g in pack["gap_mitigations"]))
    if overlaps:
        context_parts.append("**Overlaps:** " + ", ".join(str(item) for item in overlaps[:6]))
    if gaps:
        context_parts.append("**Gaps:** " + ", ".join(str(item) for item in gaps[:4]))
    if pack.get("cv_highlights"):
        context_parts.append("**CV-highlights:**\n" + "\n".join(f"- {h}" for h in pack["cv_highlights"]))

    # --- narrative_why_me_now: read directly from artifact JSON (fail-safe) ---
    _narrative_why_me_now: Optional[str] = None
    try:
        _job_dir = _find_job_run_dir(job_id)
        if _job_dir:
            # Primary source: 09_narrative_strategy_v3.json → why_me_now
            for _fname in ("09_narrative_strategy_v3.json", "09_narrative_strategy.json"):
                _nf = _job_dir / _fname
                if _nf.exists():
                    _nd = json.loads(_nf.read_text(encoding="utf-8"))
                    _val = str(_nd.get("why_me_now") or "").strip()
                    # Only use if it looks like a real narrative: ≥200 chars and ends on punctuation
                    _is_real_narrative = len(_val) >= 200 and _val[-1] in ".!?»"
                    _narrative_why_me_now = _val if _is_real_narrative else None
                    break
            # Fallback: application pack may carry it directly
            if not _narrative_why_me_now:
                for _pfname in ("11_application_pack.json", "07_application_pack.json"):
                    _pf = _job_dir / _pfname
                    if _pf.exists():
                        _pd = json.loads(_pf.read_text(encoding="utf-8"))
                        _val = str(_pd.get("narrative_why_me_now") or "").strip()
                        _is_real_narrative = len(_val) >= 200 and _val[-1] in ".!?»"
                        _narrative_why_me_now = _val if _is_real_narrative else None
                        break
    except Exception:
        pass

    if _narrative_why_me_now:
        context_parts.append(
            "**NARRATIVE — hvorfor denne jobben, hvorfor nå (hjerteavsnittet — bruk dette direkte):**\n"
            + _narrative_why_me_now[:600]
        )
    else:
        context_parts.append(
            "**MOTIVASJON (avsnitt 3):** Kandidaten har oppgitt sin motivasjon i samtalen over. "
            "Bruk den eksplisitt og konkret i hjerteavsnittet. "
            "Ikke oppfinn generisk motivasjon — bruk ordene kandidaten selv brukte."
        )

    # Load actual CV evidence units so the model has specific company/project facts
    try:
        import sqlite3 as _sqlite3
        from jobpipe.core.candidate_data import (
            load_candidate_profile_pack as _load_pp,
            load_candidate_resume_json as _load_rj,
        )
        from jobpipe.cli.generate_cover_letter import build_authoring_context as _bac

        _db = _sqlite3.connect(str(SQLITE_PATH))
        _db.row_factory = _sqlite3.Row
        _row = _db.execute("SELECT * FROM ledger WHERE job_id = ?", (job_id,)).fetchone()
        if _row:
            _profile = _load_pp(str(PROFILE_PATH))
            _resume = _load_rj(str(RESUME_PATH)) or {}
            _auth = _bac(dict(_row), _profile, _resume, "default")

            evidence_lines = []
            for ev in _auth.selected_evidence[:6]:
                src = ev.get("source_ref", "")
                text = (ev.get("canonical_text") or "")[:180]
                if text:
                    evidence_lines.append(f"- [{src}] {text}")
            if evidence_lines:
                context_parts.append(
                    "**CV-bevis (bruk disse fakta direkte — selskapsnavn, prosjektnavn, verktøy MÅ med i brevet):**\n"
                    + "\n".join(evidence_lines)
                )

            if _auth.cover_letter_strategy:
                context_parts.append(f"**Søknadsvinkel (følg denne nøye):** {_auth.cover_letter_strategy[:300]}")
            if _auth.recruiter_hook:
                context_parts.append(f"**Åpningsinspirasjon:** {_auth.recruiter_hook[:200]}")
            if _auth.differentiation_signals:
                context_parts.append(
                    "**Differensieringssignaler (vev 1–2 inn naturlig):** "
                    + "; ".join(_auth.differentiation_signals[:3])
                )
    except Exception:
        pass  # Evidence enrichment is best-effort — fall back to pack context

    # Inject supplementary profile files
    if _voice_guide:
        context_parts.append(
            "**Stilguide (voice_guide) — følg disse reglene for register, åpninger og avslutninger:**\n"
            + _voice_guide[:3000]
        )
    if _motivation_context:
        context_parts.append(
            "**Kandidatens faktabase (motivation_context) — bruk kun det som er relevant for stillingen:**\n"
            + _motivation_context[:2000]
        )

    return "\n\n".join(context_parts)


def _run_generation(job_id: str) -> None:
    """
    Run the application_pack stage for a single job.
    Finds the job's existing run directory, loads all stage outputs,
    and re-runs just the application_pack stage with --overwrite.
    """
    try:
        job_dir = _find_job_run_dir(job_id)
        if not job_dir:
            with _gen_lock:
                _gen_status[job_id] = "error:no run directory found for this job"
            return

        # Reuse the shared Topic 21 workspace context so generation follows the
        # same projection-backed job/match/pivot/moderator rules as the live readers.
        workspace_ctx = _load_workspace_context(job_id)
        if not workspace_ctx or not isinstance(workspace_ctx.get("job"), dict) or not workspace_ctx.get("job"):
            with _gen_lock:
                _gen_status[job_id] = "error:workspace context missing or empty"
            return

        triage = _read_stage_json(job_dir, "triage")
        parsed = _read_stage_json(job_dir, "parsed")
        match = workspace_ctx.get("match") or {}
        pivot = workspace_ctx.get("pivot") or {}
        moderate = workspace_ctx.get("moderator") or {}

        # Build a minimal JobContext
        from jobpipe.core.config import load_config
        from jobpipe.core.io import load_env_file, load_profile_pack
        from jobpipe.core.schema import (
            JobContext, RunMeta,
            TriageOut, JobParse, ProfileMatchOut, PivotOut, ModeratorOut,
        )
        from jobpipe.stages.application_pack import application_pack_stage_factory

        load_env_file(PATHS.env_file)
        cfg = load_config(str(CONFIG_PATH), overlays=CONFIG_OVERLAYS)
        profile_pack = load_profile_pack(str(PROFILE_PATH))

        job_data = workspace_ctx.get("job", {})
        job_id_val = job_data.get("id") or job_data.get("job_id") or job_id

        if match and "match_level" not in match:
            fit_score = int(match.get("fit_score") or 0)
            match = {
                "fit_score": fit_score,
                "match_level": "strong" if fit_score >= 75 else ("medium" if fit_score >= 45 else "weak"),
                "overlaps": list(match.get("overlaps") or []),
                "gaps": list(match.get("gaps") or []),
                "hard_blockers": list(match.get("hard_blockers") or []),
                "notes": str(match.get("notes") or ""),
            }

        if pivot and (
            "pivot_type" not in pivot
            or "potential_risk" not in pivot
            or "why_it_matters" not in pivot
        ):
            pivot = {
                "pivot_score": int(pivot.get("pivot_score") or 0),
                "pivot_type": str(pivot.get("pivot_type") or "adjacent"),
                "potential_risk": str(pivot.get("potential_risk") or "medium"),
                "why_it_matters": list(pivot.get("why_it_matters") or []),
            }

        if moderate and ("confidence" not in moderate or "recommendation_reason" not in moderate):
            moderate = {
                "final_decision": str(moderate.get("final_decision") or ""),
                "confidence": float(moderate.get("confidence") or 0.8),
                "recommendation_reason": str(moderate.get("recommendation_reason") or ""),
                "cv_focus": list(moderate.get("cv_focus") or []),
                "feedback_flags": list(moderate.get("feedback_flags") or []),
            }

        meta = RunMeta(
            run_id="server_gen",
            pipeline_name="dashboard_server",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        ctx = JobContext(
            meta=meta,
            job_id=job_id_val,
            job=job_data,
            profile_pack=profile_pack,
        )

        # Populate ctx with existing stage results using Pydantic model_validate.
        # Validate each stage independently so a thin fallback object in one stage
        # does not block recovery of later stages like moderator.
        for stage_name, payload, model_cls, attr_name in (
            ("triage", triage, TriageOut, "triage"),
            ("parsed", parsed, JobParse, "parsed"),
            ("profile_match", match, ProfileMatchOut, "profile_match"),
            ("pivot", pivot, PivotOut, "pivot"),
            ("moderator", moderate, ModeratorOut, "moderator"),
        ):
            if not payload:
                continue
            try:
                setattr(ctx, attr_name, model_cls.model_validate(payload))
            except Exception as e:
                print(
                    f"[server] Warning: could not restore {stage_name} context for {job_id}: {e}",
                    file=sys.stderr,
                )

        # Run application_pack stage
        model = cfg.models.get("application_pack", "gpt-4.1")
        should_run, run_fn = application_pack_stage_factory(model=model)
        if not should_run(ctx):
            with _gen_lock:
                _gen_status[job_id] = "error:application_pack would not run — job is not APPLY/APPLY_STRONGLY, or moderator stage missing"
            return

        result = run_fn(ctx, str(job_dir))
        if not result.application_pack:
            with _gen_lock:
                _gen_status[job_id] = "error:application_pack stage returned no payload"
            return

        # Write the canonical stage artifact using the configured stage order.
        out_path = _stage_output_path(job_dir, cfg, "application_pack")
        out_path.write_text(
            json.dumps(result.application_pack.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        with _gen_lock:
            _gen_status[job_id] = "done"
        print(f"[server] Generation complete for {job_id} → {out_path}", file=sys.stderr)

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"[server] Generation failed for {job_id}: {e}\n{tb}", file=sys.stderr)
        with _gen_lock:
            _gen_status[job_id] = f"error:{e}"


# ── Entry point ───────────────────────────────────────────────────────────────

def main(argv=None):
    global CONFIG_OVERLAYS, CONFIG_PATH, PORT
    ap = argparse.ArgumentParser(description="JobPipe local dashboard server")
    ap.add_argument("--port", type=int, default=PORT, help=f"Port to listen on (default: {PORT})")
    ap.add_argument("--no-open", action="store_true", help="Don't open browser automatically")
    ap.add_argument(
        "--data-root",
        default="",
        help=f"JobPipe user data root (default: {_DEFAULT_PATHS.data_root})",
    )
    ap.add_argument(
        "--config",
        default="",
        help=f"Pipeline config YAML (default: {_DEFAULT_PATHS.default_config_path})",
    )
    ap.add_argument("--config-overlay", action="append", default=[], help="Optional config overlay YAML. Can be passed multiple times.")
    args = ap.parse_args(argv)
    paths = get_jobpipe_paths(args.data_root or None)
    os.environ[JOBPIPE_DATA_ROOT_ENV] = str(paths.data_root)
    bootstrap_private_data(paths, include_artifacts=True)
    _apply_paths(paths)
    CONFIG_PATH = Path(args.config) if args.config else paths.default_config_path
    CONFIG_OVERLAYS = args.config_overlay or []
    PORT = args.port

    url = f"http://localhost:{PORT}"
    print(f"JobPipe Dashboard Server starting on {url}")
    print(f"  Data root: {PATHS.data_root.resolve()}")
    print(f"  SQLite:    {SQLITE_PATH.resolve()}")
    print(f"  State:     {STATE_PATH.resolve()}")
    print(f"  Template:  {TEMPLATE_PATH.resolve()}")
    print(f"  Export:    {DASHBOARD_PATH.resolve()}")
    print(f"  Config:    {CONFIG_PATH.resolve()}")
    if CONFIG_OVERLAYS:
        print(f"  Overlays:  {', '.join(CONFIG_OVERLAYS)}")
    print(f"  Press Ctrl+C to stop.\n")

    # Open browser after a short delay (let server bind first)
    if not args.no_open:
        def _open():
            import time; time.sleep(0.8)
            webbrowser.open(url)
        threading.Thread(target=_open, daemon=True).start()

    server = ThreadingHTTPServer(("localhost", PORT), DashboardHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[server] Stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
