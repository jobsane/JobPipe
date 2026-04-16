"""Mark or query application status for jobs in the sidecar state file.

New model (v2): each job has a list of stages that have occurred + an optional terminal outcome.
  stages    Ordered list of milestones that have been reached. Additive — marking a stage
            twice is idempotent (re-marks the date, optionally updates notes).
  outcome   Terminal resolution: 'accepted' | 'rejected' | 'dismissed' | null

Valid stages (accumulate over time):
    shortlisted       Reviewed, decided to pursue
    called            Pre-application phone call made (norsk standard)
    applied           Application submitted
    interview         First interview
    second_interview  Second round interview

Valid outcomes (mutually exclusive terminal states):
    accepted          Got the job — offer accepted
    rejected          Rejected by employer
    dismissed         Decided not to apply / withdrew

Usage examples:
    python -m jobpipe.cli.mark_status JOB_ID shortlisted
    python -m jobpipe.cli.mark_status JOB_ID called --notes "Snakket med Kari Nordmann"
    python -m jobpipe.cli.mark_status JOB_ID applied --notes "Sendt via Webcruiter"
    python -m jobpipe.cli.mark_status JOB_ID interview
    python -m jobpipe.cli.mark_status JOB_ID second_interview
    python -m jobpipe.cli.mark_status JOB_ID rejected --notes "Fikk ikke videre"
    python -m jobpipe.cli.mark_status JOB_ID accepted
    python -m jobpipe.cli.mark_status JOB_ID dismissed
    python -m jobpipe.cli.mark_status --list
    python -m jobpipe.cli.mark_status --list --filter-status applied
    python -m jobpipe.cli.mark_status JOB_ID clear
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from jobpipe.core.io import load_env_file

load_env_file(".env")

from jobpipe.core.paths import application_state_path, primary_db_path
from jobpipe.core.primary_db import (
    connect_primary_db,
    delete_application_tracking,
    ensure_candidate,
    insert_application_event,
    upsert_application_summary,
)

# Stages that accumulate — order matters for display
VALID_STAGES = ["shortlisted", "called", "applied", "interview", "second_interview"]

# Terminal outcomes — mutually exclusive
VALID_OUTCOMES = {"accepted", "rejected", "dismissed"}

# All recognised tokens (stages + outcomes + clear)
ALL_VALID = set(VALID_STAGES) | VALID_OUTCOMES | {"clear"}

# Display labels
STAGE_LABELS = {
    "shortlisted":       "Shortlisted",
    "called":            "Pre-call made",
    "applied":           "Applied",
    "interview":         "Interview",
    "second_interview":  "2nd interview",
}
OUTCOME_LABELS = {
    "accepted":  "Accepted ✅",
    "rejected":  "Rejected ❌",
    "dismissed": "Dismissed ⚫",
}
# Icon per effective status (for --list)
STATUS_ICON = {
    "shortlisted":      "🟡",
    "called":           "📞",
    "applied":          "🔵",
    "interview":        "🟢",
    "second_interview": "🟣",
    "accepted":         "✅",
    "rejected":         "❌",
    "dismissed":        "⚫",
}

DEFAULT_STATE_PATH = application_state_path()
DEFAULT_DB_PATH = primary_db_path()
DEFAULT_CANDIDATE_ID = (os.environ.get("JOBPIPE_CANDIDATE_ID") or "default").strip() or "default"


def _console_text(text: str, stream) -> str:
    encoding = getattr(stream, "encoding", None) or "utf-8"
    try:
        text.encode(encoding)
        return text
    except UnicodeEncodeError:
        return text.encode(encoding, errors="replace").decode(encoding, errors="replace")


def _print(text: str = "", *, file=sys.stdout) -> None:
    print(_console_text(text, file), file=file)


# ---------------------------------------------------------------------------
# Migration helpers
# ---------------------------------------------------------------------------

def _migrate_entry(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Upgrade a v1 entry (single 'status' field) to v2 (stages + outcome)."""
    if "stages" in raw:
        return raw  # Already v2

    old_status = raw.get("status", "")
    entry = {k: v for k, v in raw.items() if k != "status"}

    if old_status in VALID_OUTCOMES:
        # e.g. rejected / dismissed — assume the job was applied before outcome
        stages: List[str] = []
        if old_status == "rejected":
            stages = ["applied"]  # reasonable assumption
        elif old_status == "dismissed":
            stages = []
        entry["stages"] = stages
        entry["outcome"] = old_status
    elif old_status in VALID_STAGES:
        # Reconstruct a plausible stage list up to and including this stage
        idx = VALID_STAGES.index(old_status)
        # Only include stages that definitely happened (applied → interview is an upgrade)
        # For shortlisted, just [shortlisted]. For applied+, include applied.
        if old_status == "shortlisted":
            entry["stages"] = ["shortlisted"]
        elif old_status == "interview":
            entry["stages"] = ["applied", "interview"]
        elif old_status == "second_interview":
            entry["stages"] = ["applied", "interview", "second_interview"]
        else:
            entry["stages"] = [old_status]
        entry["outcome"] = None
    else:
        entry["stages"] = []
        entry["outcome"] = None

    return entry


def _effective_status(entry: Dict[str, Any]) -> str:
    """Return the most advanced current state for backward-compat display and scan_gmail."""
    if entry.get("outcome"):
        return entry["outcome"]
    stages = entry.get("stages", [])
    if not stages:
        return ""
    # Return last stage that is in VALID_STAGES (preserves order)
    for s in reversed(VALID_STAGES):
        if s in stages:
            return s
    return stages[-1]


def _current_stage(entry: Dict[str, Any]) -> str:
    stages = entry.get("stages", [])
    if not stages:
        return ""
    for s in reversed(VALID_STAGES):
        if s in stages:
            return s
    return stages[-1]


def _sync_job_to_primary_db(
    *,
    candidate_id: str,
    job_id: str,
    token: str,
    entry: Dict[str, Any] | None,
    db_path: Path,
    source: str,
) -> None:
    try:
        conn = connect_primary_db(db_path)
        try:
            ensure_candidate(conn, candidate_id=candidate_id)

            if token == "clear" or entry is None:
                delete_application_tracking(conn, candidate_id=candidate_id, job_id=job_id)
                conn.commit()
                return

            event_time = entry.get("email_date") or entry.get("updated_at") or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            effective_source = (source or entry.get("source") or "manual").strip() or "manual"
            metadata = {
                "stages": list(entry.get("stages", [])),
                "outcome": entry.get("outcome") or "",
                "effective_status": _effective_status(entry),
                "email_subject": entry.get("email_subject", ""),
                "email_date": entry.get("email_date", ""),
            }

            insert_application_event(
                conn,
                {
                    "application_event_id": f"app_{uuid.uuid4().hex[:20]}",
                    "candidate_id": candidate_id,
                    "job_id": job_id,
                    "event_type": token,
                    "event_at": event_time,
                    "source": effective_source,
                    "notes": entry.get("notes", ""),
                    "metadata_json": metadata,
                    "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                },
            )

            upsert_application_summary(
                conn,
                {
                    "candidate_id": candidate_id,
                    "job_id": job_id,
                    "current_stage": _current_stage(entry),
                    "current_outcome": entry.get("outcome") or "",
                    "effective_status": _effective_status(entry),
                    "last_event_at": event_time,
                    "notes_latest": entry.get("notes", ""),
                    "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                },
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        print(f"[WARN] primary DB sync failed for {job_id}: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def load_state(path: Path) -> Dict[str, Any]:
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            # Migrate all entries
            apps = raw.get("applications", {})
            raw["applications"] = {jid: _migrate_entry(e) for jid, e in apps.items()}
            return raw
        except Exception as e:
            print(f"Warning: could not read {path}: {e}", file=sys.stderr)
    return {"version": 2, "updated_at": "", "applications": {}}


def save_state(path: Path, state: Dict[str, Any]) -> None:
    state["version"] = 2
    state["updated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    # Write a computed backward-compat 'status' field on every entry
    for entry in state.get("applications", {}).values():
        entry["status"] = _effective_status(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------

def add_stage(
    job_id: str,
    token: str,
    state_path: Path,
    notes: str = "",
    source: str = "manual",
    email_subject: str = "",
    email_date: str = "",
    db_path: Path = DEFAULT_DB_PATH,
    candidate_id: str = DEFAULT_CANDIDATE_ID,
    quiet: bool = False,
) -> None:
    state = load_state(state_path)
    apps = state.setdefault("applications", {})

    if token == "clear":
        if job_id in apps:
            del apps[job_id]
            save_state(state_path, state)
            _sync_job_to_primary_db(
                candidate_id=candidate_id,
                job_id=job_id,
                token=token,
                entry=None,
                db_path=db_path,
                source=source,
            )
            if not quiet:
                _print(f"[OK] Cleared status for {job_id}")
        else:
            if not quiet:
                _print(f"No entry found for {job_id}")
        return

    if token not in ALL_VALID - {"clear"}:
        print(
            f"Error: unknown token '{token}'.\n"
            f"  Stages:   {', '.join(VALID_STAGES)}\n"
            f"  Outcomes: {', '.join(sorted(VALID_OUTCOMES))}",
            file=sys.stderr,
        )
        sys.exit(1)

    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    entry = _migrate_entry(apps.get(job_id, {}))

    # Preserve existing notes if none supplied
    if not notes and entry.get("notes"):
        notes = entry["notes"]
    if notes:
        entry["notes"] = notes

    if email_subject:
        entry["email_subject"] = email_subject
    elif entry.get("email_subject"):
        pass  # keep existing

    if email_date:
        entry["email_date"] = email_date

    entry["updated_at"] = now_iso
    entry.setdefault("source", source)

    if token in VALID_OUTCOMES:
        entry["outcome"] = token
        label = OUTCOME_LABELS.get(token, token)
        if not quiet:
            _print(f"[OK] {job_id} → outcome: {label}")
    else:
        # Additive stage
        stages: List[str] = entry.setdefault("stages", [])
        if token not in stages:
            stages.append(token)
            label = STAGE_LABELS.get(token, token)
            if not quiet:
                _print(f"[OK] {job_id} → stage added: {label}")
        else:
            label = STAGE_LABELS.get(token, token)
            if not quiet:
                _print(f"[OK] {job_id} → stage already present: {label} (notes updated if supplied)")

    apps[job_id] = entry
    save_state(state_path, state)
    _sync_job_to_primary_db(
        candidate_id=candidate_id,
        job_id=job_id,
        token=token,
        entry=entry,
        db_path=db_path,
        source=source,
    )


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

STAGE_ICONS = {
    "shortlisted":      "🟡",
    "called":           "📞",
    "applied":          "🔵",
    "interview":        "🟢",
    "second_interview": "🟣",
}

def _format_stages(entry: Dict[str, Any]) -> str:
    stages = entry.get("stages", [])
    outcome = entry.get("outcome")
    parts = []
    for s in VALID_STAGES:
        if s in stages:
            parts.append(f"{STAGE_ICONS.get(s, '•')}{STAGE_LABELS.get(s, s)}")
    if outcome:
        parts.append(OUTCOME_LABELS.get(outcome, outcome))
    return " → ".join(parts) if parts else "(ingen stage)"


def list_statuses(state_path: Path, filter_status: str = "") -> None:
    state = load_state(state_path)
    apps = state.get("applications", {})
    if not apps:
        _print("No application status entries found.")
        return

    rows = sorted(apps.items(), key=lambda x: x[1].get("updated_at", ""), reverse=True)

    if filter_status:
        def _matches(entry: Dict[str, Any]) -> bool:
            if filter_status in entry.get("stages", []):
                return True
            if filter_status == entry.get("outcome"):
                return True
            # Also support old-style single-status filter
            return _effective_status(entry) == filter_status
        rows = [(jid, e) for jid, e in rows if _matches(e)]

    _print(f"\n{'Job ID':<42} {'Timeline':<60} {'Updated'}")
    _print("─" * 110)
    for job_id, entry in rows:
        timeline = _format_stages(entry)
        updated = (entry.get("updated_at") or "")[:10]
        _print(f"{STATUS_ICON.get(_effective_status(entry), '  ')} {job_id:<40} {timeline:<60} {updated}")
        if entry.get("notes"):
            _print(f"   {'':40} ↳ {entry['notes'][:100]}")

    _print(f"\nTotal: {len(rows)}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(
        description="Mark or list application status for JobPipe jobs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("job_id", nargs="?", help="Job ID to update (omit with --list)")
    ap.add_argument(
        "status",
        nargs="?",
        metavar="STAGE_OR_OUTCOME",
        help=(
            f"Stage to add: {', '.join(VALID_STAGES)}  |  "
            f"Outcome: {', '.join(sorted(VALID_OUTCOMES))}  |  clear"
        ),
    )
    ap.add_argument("--notes", default="", help="Optional notes / context")
    ap.add_argument(
        "--pre-call-notes",
        default="",
        help="Notes from pre-application phone call (shortcut: also sets 'called' stage)",
    )
    ap.add_argument(
        "--state",
        default=str(DEFAULT_STATE_PATH),
        help=f"Path to application_state.json (default: {DEFAULT_STATE_PATH})",
    )
    ap.add_argument(
        "--db",
        default=str(DEFAULT_DB_PATH),
        help=f"Path to primary jobpipe.sqlite (default: {DEFAULT_DB_PATH})",
    )
    ap.add_argument(
        "--candidate-id",
        default=DEFAULT_CANDIDATE_ID,
        help=f"Candidate ID for primary DB writes (default: {DEFAULT_CANDIDATE_ID})",
    )
    ap.add_argument("--list", action="store_true", help="List all tracked applications")
    ap.add_argument(
        "--filter-status",
        default="",
        help="Filter --list by stage or outcome (e.g. applied, interview, rejected)",
    )

    args = ap.parse_args(argv)
    state_path = Path(args.state)
    db_path = Path(args.db)

    if args.list:
        list_statuses(state_path, filter_status=args.filter_status)
        return

    if not args.job_id or not args.status:
        ap.print_help()
        sys.exit(1)

    notes = args.notes
    if args.pre_call_notes:
        notes = args.pre_call_notes if not notes else f"{notes} | pre-call: {args.pre_call_notes}"

    add_stage(
        job_id=args.job_id,
        token=args.status,
        state_path=state_path,
        notes=notes,
        source="manual",
        db_path=db_path,
        candidate_id=args.candidate_id,
    )

    # If --pre-call-notes supplied but stage isn't 'called', also auto-add 'called'
    if args.pre_call_notes and args.status != "called":
        add_stage(
            job_id=args.job_id,
            token="called",
            state_path=state_path,
            notes=args.pre_call_notes,
            source="manual",
            db_path=db_path,
            candidate_id=args.candidate_id,
        )


if __name__ == "__main__":
    main()
