"""Supabase-backed applications capability for the canonical state migration.

Owns the `applications` table — per-job application lifecycle status that
JobDesk reads (`/applications`, `/follow-up`) and writes (decision actions
on `/cases/:id/*`).

The `applications` schema lives in JobData (sibling repo):
  applications(
    id SERIAL PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id),
    status TEXT NOT NULL DEFAULT 'shortlisted',
    applied_at TIMESTAMPTZ,
    notes TEXT,
    created_at, updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(job_id)
  )

Status values: shortlisted, applied, interview, offer, rejected, dismissed.

OSS single-user mode: the table has no user_id column yet — that's deferred
to the JobValve SaaS overlay. For now every row is "the user's".

Best-effort writes: PostgREST errors don't raise into the hub. The caller
(workspace_server) falls back to disk-backed case_state.json when Supabase
isn't configured or returns an error.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


_DEFAULT_TIMEOUT_SEC = 10
_VALID_STATUSES = {
    "shortlisted",
    "applied",
    "interview",
    "offer",
    "rejected",
    "dismissed",
}


# JobDesk uses its own decisionStatus/applicationStatus vocabulary. The hub's
# /case_state endpoint validates against VALID_DECISION_STATUSES /
# VALID_APPLICATION_STATUSES. This mapping converts the hub-shaped state into
# the applications.status value to persist.
#
# decision="decided_skip"  -> applications.status="dismissed"
# decision="decided_apply" + applicationStatus="drafting" -> "shortlisted"
# decision="decided_apply" + applicationStatus="applied" -> "applied"
# decision="decided_apply" + applicationStatus="interview" -> "interview"
# decision="decided_apply" + applicationStatus="ghosted" / "rejected" -> "rejected"
# decision="to_review" or unset -> "shortlisted"
def _state_to_status(decision_status: str, application_status: Optional[str]) -> str:
    if decision_status == "decided_skip":
        return "dismissed"
    if decision_status == "decided_apply":
        if application_status in ("applied", "interview", "offer", "rejected"):
            return application_status
        if application_status == "ghosted":
            return "rejected"
        return "shortlisted"
    return "shortlisted"


def _status_to_state(status: str) -> dict[str, Any]:
    """Reverse: project an applications.status value back into the hub shape
    that JobDesk's case-decisions store consumes."""
    if status == "dismissed":
        return {"decisionStatus": "decided_skip", "applicationStatus": None}
    if status in ("applied", "interview", "offer", "rejected"):
        return {"decisionStatus": "decided_apply", "applicationStatus": status}
    # shortlisted (default) -> no explicit decision yet
    return {"decisionStatus": "to_review", "applicationStatus": None}


@dataclass(frozen=True)
class SupabaseApplicationsCapability:
    supabase_url: str
    supabase_key: str
    timeout_sec: int = _DEFAULT_TIMEOUT_SEC

    def upsert_state(
        self,
        job_id: str,
        *,
        decision_status: str,
        application_status: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> bool:
        """Upsert one row in `applications` for job_id. Returns True on 2xx.

        Maps hub-shape (decisionStatus + applicationStatus) → applications.status
        and sets applied_at when status moves into a post-shortlisted state.
        """
        if decision_status not in ("to_review", "decided_apply", "decided_skip"):
            return False
        status = _state_to_status(decision_status, application_status)
        if status not in _VALID_STATUSES:
            return False

        payload: dict[str, Any] = {
            "job_id": job_id,
            "status": status,
        }
        # applied_at: stamp once when status leaves shortlisted/dismissed for
        # the first time. PostgREST upsert will leave applied_at as-is for
        # subsequent reads if we don't set it.
        if status in ("applied", "interview", "offer"):
            from datetime import datetime, timezone
            payload["applied_at"] = datetime.now(timezone.utc).isoformat()
        if notes is not None:
            payload["notes"] = notes

        endpoint = f"{self.supabase_url.rstrip('/')}/rest/v1/applications"
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Content-Type": "application/json",
            # Upsert on the UNIQUE(job_id) constraint
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }
        req = Request(endpoint, data=body, headers=headers, method="POST")
        try:
            with urlopen(req, timeout=self.timeout_sec) as resp:
                return 200 <= resp.status < 300
        except (HTTPError, URLError, TimeoutError, OSError):
            return False

    def clear_state(self, job_id: str) -> bool:
        """Reset the application back to 'shortlisted' (clears prior decision).

        We don't actually DELETE the row — that would lose history once we
        add audit timestamps. Just status='shortlisted' + applied_at=null.
        """
        return self.upsert_state(
            job_id, decision_status="to_review", application_status=None
        )

    def get_state(self, job_id: str) -> Optional[dict[str, Any]]:
        """Read one row back as the hub-shaped state dict, or None if absent."""
        endpoint = (
            f"{self.supabase_url.rstrip('/')}/rest/v1/applications"
            f"?job_id=eq.{quote(job_id, safe='')}&select=status,applied_at,notes"
        )
        req = Request(
            endpoint,
            headers={
                "apikey": self.supabase_key,
                "Authorization": f"Bearer {self.supabase_key}",
            },
            method="GET",
        )
        try:
            with urlopen(req, timeout=self.timeout_sec) as resp:
                if resp.status >= 400:
                    return None
                rows = json.load(resp)
        except (HTTPError, URLError, TimeoutError, OSError):
            return None
        if not rows:
            return None
        row = rows[0]
        state = _status_to_state(row.get("status") or "shortlisted")
        if row.get("notes"):
            state["skipReason"] = row["notes"] if state.get("decisionStatus") == "decided_skip" else None
        return state

    def list_state(self) -> dict[str, dict[str, Any]]:
        """Read all rows back as {job_id: state}. Used by GET /case_state."""
        endpoint = (
            f"{self.supabase_url.rstrip('/')}/rest/v1/applications"
            f"?select=job_id,status,notes&order=updated_at.desc"
        )
        req = Request(
            endpoint,
            headers={
                "apikey": self.supabase_key,
                "Authorization": f"Bearer {self.supabase_key}",
            },
            method="GET",
        )
        try:
            with urlopen(req, timeout=self.timeout_sec) as resp:
                if resp.status >= 400:
                    return {}
                rows = json.load(resp)
        except (HTTPError, URLError, TimeoutError, OSError):
            return {}
        out: dict[str, dict[str, Any]] = {}
        for row in rows:
            jid = row.get("job_id")
            if not jid:
                continue
            state = _status_to_state(row.get("status") or "shortlisted")
            # Only surface non-default rows — saves bandwidth + matches the
            # disk-backed behavior where unset cases simply aren't in the dict.
            if state["decisionStatus"] == "to_review" and state["applicationStatus"] is None:
                continue
            if row.get("notes") and state["decisionStatus"] == "decided_skip":
                state["skipReason"] = row["notes"]
            out[jid] = state
        return out

    def get_application_id(self, job_id: str) -> Optional[int]:
        """Return the applications.id for job_id, upserting a shortlisted
        row if none exists. Used by cover_letters / cv_versions to satisfy
        their FK to applications.id.
        """
        endpoint = (
            f"{self.supabase_url.rstrip('/')}/rest/v1/applications"
            f"?job_id=eq.{quote(job_id, safe='')}&select=id"
        )
        req = Request(
            endpoint,
            headers={
                "apikey": self.supabase_key,
                "Authorization": f"Bearer {self.supabase_key}",
            },
            method="GET",
        )
        try:
            with urlopen(req, timeout=self.timeout_sec) as resp:
                if resp.status >= 400:
                    return None
                rows = json.load(resp)
        except (HTTPError, URLError, TimeoutError, OSError):
            return None
        if rows:
            try:
                return int(rows[0]["id"])
            except (KeyError, TypeError, ValueError):
                return None

        # Not found — upsert a shortlisted row, then re-read.
        if not self.upsert_state(
            job_id, decision_status="to_review", application_status=None
        ):
            return None
        # PostgREST upsert with return=minimal doesn't echo the id; re-query.
        req = Request(
            endpoint,
            headers={
                "apikey": self.supabase_key,
                "Authorization": f"Bearer {self.supabase_key}",
            },
            method="GET",
        )
        try:
            with urlopen(req, timeout=self.timeout_sec) as resp:
                if resp.status >= 400:
                    return None
                rows = json.load(resp)
        except (HTTPError, URLError, TimeoutError, OSError):
            return None
        if not rows:
            return None
        try:
            return int(rows[0]["id"])
        except (KeyError, TypeError, ValueError):
            return None


def from_env() -> Optional[SupabaseApplicationsCapability]:
    """Construct from JOBPIPE_SUPABASE_URL/KEY. Returns None if not set."""
    url = os.environ.get("JOBPIPE_SUPABASE_URL")
    key = os.environ.get("JOBPIPE_SUPABASE_KEY")
    if not url or not key:
        return None
    return SupabaseApplicationsCapability(supabase_url=url, supabase_key=key)
