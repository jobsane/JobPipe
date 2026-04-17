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
import sys
import threading
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

from jobpipe.core.paths import JOBPIPE_DATA_ROOT_ENV, JobPipePaths, bootstrap_private_data, get_jobpipe_paths

# ── Paths ────────────────────────────────────────────────────────────────────
_DEFAULT_PATHS = get_jobpipe_paths()
PATHS = _DEFAULT_PATHS
STATE_PATH = PATHS.application_state_path
PROFILE_DRAFT_PATH = PATHS.profile_builder_state_path
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

# ── Background generation tracker ──
_gen_status: dict[str, str] = {}   # job_id → "running" | "done" | "error:<msg>"
_gen_lock = threading.Lock()
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
    global STATE_PATH, PROFILE_DRAFT_PATH, DASHBOARD_PATH, SQLITE_PATH
    global TEMPLATE_PATH, APPLY_TEMPLATE_PATH, OUT_RUNS, PROFILE_PATH
    global RESUME_PATH, RESUME_FIXED_PATH, CONFIG_PATH

    PATHS = paths
    STATE_PATH = paths.application_state_path
    PROFILE_DRAFT_PATH = paths.profile_builder_state_path
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

        elif path.startswith("/api/draft/"):
            job_id = path[len("/api/draft/"):].strip("/")
            self._get_draft(job_id)

        elif path == "/api/resume":
            self._get_resume()

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
        elif path == "/api/generate":
            self._post_generate(body)
        elif path == "/api/rebuild":
            self._post_rebuild()
        elif path.startswith("/api/draft/"):
            job_id = path[len("/api/draft/"):].strip("/")
            self._post_draft(job_id, body)
        elif path == "/api/chat":
            self._post_chat(body)
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
        job_dir = _find_job_run_dir(job_id)
        if not job_dir:
            self._send_json({"error": "Job not found"}, 404)
            return
        try:
            # Load pack data (may be in draft or main artifact file)
            pack = _read_stage_json(job_dir, "application_pack")
            if not pack:
                draft_path = job_dir / "application_pack_draft.json"
                if draft_path.exists():
                    pack = json.loads(draft_path.read_text(encoding="utf-8"))

            # Load job input for context
            inp = {}
            if (job_dir / "00_input.json").exists():
                raw = json.loads((job_dir / "00_input.json").read_text(encoding="utf-8"))
                inp = raw.get("job", raw)

            # Load match data for overlaps/gaps
            match = _read_stage_json(job_dir, "profile_match")

            # Check for existing files
            has_docx = (job_dir / "07_cv_highlights.docx").exists()
            has_draft = (job_dir / "cover_letter_draft.txt").exists()
            cover_letter_draft = ""
            if has_draft:
                cover_letter_draft = (job_dir / "cover_letter_draft.txt").read_text(encoding="utf-8")

            self._send_json({
                "job_id": job_id,
                "job": {
                    "title": inp.get("title", ""),
                    "employer": inp.get("employer_name", inp.get("company", "")),
                    "source_url": (
                        inp.get("sourceurl")
                        or inp.get("link")
                        or inp.get("applicationUrl")
                        or inp.get("application_url", "")
                    ),
                    "deadline": inp.get("applicationDue", ""),
                    "description_snip": (inp.get("description") or "")[:600],
                },
                "pack": pack,
                "overlaps": match.get("overlaps", []),
                "gaps": match.get("gaps", []),
                "has_docx": has_docx,
                "cover_letter_draft": cover_letter_draft,
                "job_dir": str(job_dir),
            })
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
        job_id = body.get("job_id", "")
        messages = body.get("messages", [])  # [{role, content}, ...]
        if not messages:
            self._send_json({"error": "messages required"}, 400)
            return
        try:
            # Load job context for system prompt
            system = _build_chat_system_prompt(job_id)

            from openai import OpenAI
            from jobpipe.core.io import load_env_file
            load_env_file(PATHS.env_file)
            client = OpenAI()

            response = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[{"role": "system", "content": system}] + messages,
                temperature=0.7,
                max_tokens=1200,
            )
            reply = response.choices[0].message.content
            self._send_json({"reply": reply})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

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
        if (job_dir / "00_input.json").exists():
            # Use mtime of the run directory as ordering key
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


def _stage_output_path(job_dir: Path, cfg, stage_name: str) -> Path:
    order_raw = list(getattr(cfg, "stages", None) or _DEFAULT_STAGE_ORDER)
    order = [_STAGE_ALIASES.get(name, name) for name in order_raw]
    canonical_name = _STAGE_ALIASES.get(stage_name, stage_name)
    if canonical_name not in order:
        raise ValueError(f"Stage not configured: {canonical_name}")
    return job_dir / f"{order.index(canonical_name) + 1:02d}_{canonical_name}.json"


def _build_chat_system_prompt(job_id: str) -> str:
    """Build a rich system prompt for the AI chat using the job's pipeline context."""
    job_dir = _find_job_run_dir(job_id)
    base = (
        "Du er en norsk søknadsassistent for Lars Værland, en erfaren produkt- og "
        "tjenesteeier med bakgrunn fra digitalisering, offentlig sektor og produktledelse. "
        "Du hjelper Lars med å skrive og spisse søknadsbrev og CV-punkter på norsk. "
        "Skriv handlingsorientert, konkret og uten klisjeer. Unngå overtydelig selvskryt. "
        "Aldri bruk tankestrek (—). Søknadsbrev skal være 230–260 ord.\n\n"
    )
    if not job_dir:
        return base

    inp = json.loads((job_dir / "00_input.json").read_text(encoding="utf-8")) if (job_dir / "00_input.json").exists() else {}
    job = inp.get("job", inp)
    match = _read_stage_json(job_dir, "profile_match")
    pack = _read_stage_json(job_dir, "application_pack")
    if not pack:
        draft_path = job_dir / "application_pack_draft.json"
        if draft_path.exists():
            pack = json.loads(draft_path.read_text(encoding="utf-8"))

    context_parts = [base]
    if job.get("title"):
        context_parts.append(f"**Stilling:** {job.get('title')} @ {job.get('employer_name', '')}")
    if pack.get("positioning_headline"):
        context_parts.append(f"**Posisjoneringsoverskrift:** {pack['positioning_headline']}")
    if pack.get("cover_letter_angle"):
        context_parts.append(f"**Søknadsvinkel (AI-generert):** {pack['cover_letter_angle']}")
    if pack.get("top_value_props"):
        context_parts.append("**Toppverdier:**\n" + "\n".join(f"- {v}" for v in pack["top_value_props"]))
    if pack.get("evidence_map"):
        context_parts.append("**Bevis-kart (jobbkrav → Lars sin erfaring):**\n" + "\n".join(f"- {e}" for e in pack["evidence_map"]))
    if pack.get("gap_mitigations"):
        context_parts.append("**Gap-håndtering:**\n" + "\n".join(f"- {g}" for g in pack["gap_mitigations"]))
    if match.get("overlaps"):
        context_parts.append("**Overlaps:** " + ", ".join(match["overlaps"][:6]))
    if match.get("gaps"):
        context_parts.append("**Gaps:** " + ", ".join(match["gaps"][:4]))
    if pack.get("cv_highlights"):
        context_parts.append("**CV-highlights (tilpasset denne jobben):**\n" + "\n".join(f"- {h}" for h in pack["cv_highlights"]))

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

        # Read the existing stage JSONs to reconstruct JobContext
        inp = json.loads((job_dir / "00_input.json").read_text(encoding="utf-8")) if (job_dir / "00_input.json").exists() else {}
        triage = _read_stage_json(job_dir, "triage")
        parsed = _read_stage_json(job_dir, "parsed")
        match = _read_stage_json(job_dir, "profile_match")
        pivot = _read_stage_json(job_dir, "pivot")
        moderate = _read_stage_json(job_dir, "moderator")

        if not inp:
            with _gen_lock:
                _gen_status[job_id] = "error:00_input.json missing or empty"
            return

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

        job_data = inp.get("job", inp)  # handle both root-level and nested
        job_id_val = job_data.get("id") or job_data.get("job_id") or job_id

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

        # Populate ctx with existing stage results using Pydantic model_validate
        try:
            if triage:
                ctx.triage = TriageOut.model_validate(triage)
            if parsed:
                ctx.parsed = JobParse.model_validate(parsed)
            if match:
                ctx.profile_match = ProfileMatchOut.model_validate(match)
            if pivot:
                ctx.pivot = PivotOut.model_validate(pivot)
            if moderate:
                ctx.moderator = ModeratorOut.model_validate(moderate)
        except Exception as e:
            print(f"[server] Warning: could not restore stage context for {job_id}: {e}", file=sys.stderr)

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

    server = HTTPServer(("localhost", PORT), DashboardHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[server] Stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
