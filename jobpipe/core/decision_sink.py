"""Persist triage decisions to Supabase as the canonical store.

Part of the Supabase-canonical state migration (see Epic in Project 6 / JobPipe):
the `triage_decisions` table is the single source of truth for per-user
job verdicts; the legacy file artifacts (out_runs/<id>/index.jsonl) become
debug-only once Supabase writes are confirmed reliable end-to-end.

OSS single-user mode uses a fixed sentinel user_id. The JobValve SaaS
overlay overrides this via the JOBPIPE_USER_ID env var (auth-resolved
per request).

All upserts are best-effort: if Supabase is unreachable or unconfigured,
the file artifact remains the fallback record. The sink never raises into
the pipeline — a triage failure must not be a Supabase failure.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# OSS single-user sentinel. JobValve overlay sets JOBPIPE_USER_ID per request.
_OSS_SENTINEL_USER_ID = "00000000-0000-0000-0000-000000000001"

_DEFAULT_TIMEOUT_SEC = 10


def get_user_id() -> str:
    """Return the user_id to write decisions under.

    OSS mode: fixed sentinel UUID. JobValve overlay: JOBPIPE_USER_ID env var.
    """
    return os.environ.get("JOBPIPE_USER_ID") or _OSS_SENTINEL_USER_ID


def get_profile_version(profile_pack_path: Path) -> Optional[str]:
    """Return a stable version string derived from the profile_pack content.

    Used to detect stale decisions: when profile_pack.md changes, its hash
    changes, and the reconciler can re-triage everything decided under the
    old version.
    """
    if not profile_pack_path.exists():
        return None
    digest = hashlib.sha256(profile_pack_path.read_bytes()).hexdigest()
    return digest[:16]


def _signals_payload(summary: Dict[str, Any]) -> Dict[str, Any]:
    """Bundle the triage-related fields from snapshot_summary into the
    `signals` jsonb column. Excludes job_id/title/employer/decision/score
    which have their own columns."""
    keys = (
        "triage_decision",
        "triage_confidence",
        "triage_signals",
        "triage_v3_label",
        "triage_v3_weighted_score",
        "triage_v3_confidence",
        "triage_v3_needs_ambiguity",
        "triage_ambiguity_label",
        "advantage_type",
        "advantageous_match_score",
        "advantage_review_priority",
        "narrative_positioning_angle",
        "narrative_brand_frame",
        "pivot_score",
        "confidence",
    )
    return {k: summary.get(k) for k in keys if summary.get(k) is not None}


def load_decided_job_ids(
    *,
    user_id: Optional[str] = None,
    profile_version: Optional[str] = None,
    timeout_sec: int = _DEFAULT_TIMEOUT_SEC,
) -> set:
    """Return job_ids that already have a decision in Supabase for this user.

    When `profile_version` is given, only decisions written under that exact
    profile version are returned — stale decisions (older profile) are
    excluded so the reconciler/drain can re-triage them after a profile change.

    Best-effort: returns empty set on missing config, HTTP error, or any
    other failure. Callers must treat Supabase as advisory until canonical
    migration completes.
    """
    url = os.environ.get("JOBPIPE_SUPABASE_URL")
    key = os.environ.get("JOBPIPE_SUPABASE_KEY")
    if not url or not key:
        return set()

    effective_user_id = user_id or get_user_id()
    params = [f"user_id=eq.{effective_user_id}", "select=job_id"]
    if profile_version:
        params.append(f"profile_version=eq.{profile_version}")
    query = "&".join(params)
    endpoint = f"{url.rstrip('/')}/rest/v1/triage_decisions?{query}"

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
    }
    req = Request(endpoint, headers=headers, method="GET")
    try:
        with urlopen(req, timeout=timeout_sec) as resp:
            if resp.status >= 400:
                return set()
            data = json.load(resp)
            return {row["job_id"] for row in data if row.get("job_id")}
    except (HTTPError, URLError, TimeoutError, OSError):
        return set()


def upsert_decision(
    summary: Dict[str, Any],
    *,
    profile_version: Optional[str] = None,
    timeout_sec: int = _DEFAULT_TIMEOUT_SEC,
) -> bool:
    """Upsert one triage decision into Supabase. Returns True on success.

    Required env: JOBPIPE_SUPABASE_URL, JOBPIPE_SUPABASE_KEY (service role).
    Returns False (no raise) on missing config or any HTTP error.
    """
    url = os.environ.get("JOBPIPE_SUPABASE_URL")
    key = os.environ.get("JOBPIPE_SUPABASE_KEY")
    if not url or not key:
        return False

    decision = summary.get("final_decision")
    job_id = summary.get("job_id")
    if not decision or not job_id:
        return False

    payload = {
        "user_id": get_user_id(),
        "job_id": job_id,
        "decision": decision,
        "score": summary.get("fit_score"),
        "signals": _signals_payload(summary),
        "profile_version": profile_version,
    }

    endpoint = f"{url.rstrip('/')}/rest/v1/triage_decisions"
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        # PostgREST upsert: matches existing (user_id, job_id) and merges new values
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    req = Request(endpoint, data=body, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=timeout_sec) as resp:
            return 200 <= resp.status < 300
    except (HTTPError, URLError, TimeoutError, OSError):
        return False
