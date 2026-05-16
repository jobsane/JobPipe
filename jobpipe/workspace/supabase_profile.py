"""Supabase-backed candidate_profile capability — read-only profile fetcher.

JobData schema:
  candidate_profile(
    id SERIAL PRIMARY KEY,
    version INTEGER DEFAULT 1,
    profile_md TEXT NOT NULL,
    resume_json JSONB NOT NULL,
    rr_resume_id TEXT,
    user_id UUID,
    created_at / updated_at TIMESTAMPTZ
  )

OSS sentinel: rows are scoped by user_id when present (per the canonical-
state principle — multi-user-shaped from day one). The OSS single-user
mode uses the sentinel UUID set in decision_sink.get_user_id; the JobValve
overlay binds user_id to auth.users via RLS.

Reads the highest-version row for the active user. Used by:
- workspace_server GET /profile endpoint (replaces JobSane's direct
  Supabase fetch in src/jobsane/tools/profile_tool.py).
- JobDesk /profile page via gateway.profile.getProfile.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from jobpipe.core.decision_sink import get_user_id


_DEFAULT_TIMEOUT_SEC = 10


@dataclass(frozen=True)
class SupabaseProfileCapability:
    supabase_url: str
    supabase_key: str
    user_id: str = field(default_factory=get_user_id)
    timeout_sec: int = _DEFAULT_TIMEOUT_SEC

    def read_profile(self) -> Optional[dict[str, Any]]:
        """Return the highest-version candidate_profile row for the active
        user, or None. Shape:
          {
            "profile_md": str,
            "resume_json": dict,
            "rr_resume_id": str,
            "version": int,
            "updated_at": str,
          }
        """
        # Scope to user_id if present; rows with NULL user_id are pre-pivot
        # legacy and should be reachable in OSS single-user mode too.
        params = [
            f"or=(user_id.eq.{quote(self.user_id, safe='')},user_id.is.null)",
            "select=profile_md,resume_json,rr_resume_id,version,updated_at",
            "order=version.desc",
            "limit=1",
        ]
        endpoint = (
            f"{self.supabase_url.rstrip('/')}/rest/v1/candidate_profile"
            f"?{'&'.join(params)}"
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
        resume_json = row.get("resume_json") or {}
        if isinstance(resume_json, str):
            try:
                resume_json = json.loads(resume_json)
            except json.JSONDecodeError:
                resume_json = {}
        return {
            "profile_md": row.get("profile_md") or "",
            "resume_json": resume_json,
            "rr_resume_id": row.get("rr_resume_id") or "",
            "version": int(row.get("version") or 1),
            "updated_at": row.get("updated_at") or "",
        }


def from_env() -> Optional[SupabaseProfileCapability]:
    url = os.environ.get("JOBPIPE_SUPABASE_URL")
    key = os.environ.get("JOBPIPE_SUPABASE_KEY")
    if not url or not key:
        return None
    return SupabaseProfileCapability(supabase_url=url, supabase_key=key)
