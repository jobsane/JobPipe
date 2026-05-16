"""Supabase-backed cover letters capability for the canonical state migration.

Owns the `cover_letters` table — durable record of the cover letter text the
user / JobsaneEditor has saved for each application. Replaces the disk-backed
override-file pattern at <state-root>/tailoring/<case_id>.json.

JobData schema:
  cover_letters(
    id SERIAL PRIMARY KEY,
    application_id INTEGER NOT NULL REFERENCES applications(id),
    version INTEGER NOT NULL DEFAULT 1,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',  -- draft / reviewed / sent
    created_at, updated_at TIMESTAMPTZ DEFAULT NOW()
  )

FK to applications means we need an applications row first — the partner
SupabaseApplicationsCapability.get_application_id helper handles that.

Best-effort writes: PostgREST errors don't raise into the hub. Caller falls
back to disk-backed tailoring override JSON when Supabase isn't configured.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .supabase_applications import SupabaseApplicationsCapability


_DEFAULT_TIMEOUT_SEC = 10


@dataclass(frozen=True)
class SupabaseCoverLettersCapability:
    supabase_url: str
    supabase_key: str
    applications: SupabaseApplicationsCapability
    timeout_sec: int = _DEFAULT_TIMEOUT_SEC

    def upsert_content(
        self,
        job_id: str,
        *,
        content: str,
        language: Optional[str] = None,  # noqa: ARG002 — accepted, not stored (schema has no column)
        angle: Optional[str] = None,  # noqa: ARG002 — same
    ) -> bool:
        """Upsert the latest cover_letter for job_id. Returns True on 2xx.

        Single-version model for now: we overwrite the same row (the v1
        snapshot) on every save. When "Mark sent" lands (M3 #72) we'll
        bump version and create an immutable copy.
        """
        text = (content or "").strip()
        if not text:
            return False

        app_id = self.applications.get_application_id(job_id)
        if app_id is None:
            return False

        # Look up existing cover_letter row for this application + version=1
        # so we PATCH-update the same row rather than creating duplicates.
        existing_id = self._existing_row_id(app_id, version=1)
        payload: dict[str, Any] = {
            "application_id": app_id,
            "version": 1,
            "content": text,
            "status": "draft",
        }
        headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }

        if existing_id is not None:
            # PATCH the existing row by id (no UNIQUE constraint we can rely on
            # — schema only has PK).
            endpoint = (
                f"{self.supabase_url.rstrip('/')}/rest/v1/cover_letters"
                f"?id=eq.{existing_id}"
            )
            req = Request(
                endpoint, data=json.dumps(payload).encode("utf-8"), headers=headers, method="PATCH"
            )
        else:
            endpoint = f"{self.supabase_url.rstrip('/')}/rest/v1/cover_letters"
            req = Request(
                endpoint, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
            )

        try:
            with urlopen(req, timeout=self.timeout_sec) as resp:
                return 200 <= resp.status < 300
        except (HTTPError, URLError, TimeoutError, OSError):
            return False

    def _existing_row_id(self, application_id: int, *, version: int) -> Optional[int]:
        endpoint = (
            f"{self.supabase_url.rstrip('/')}/rest/v1/cover_letters"
            f"?application_id=eq.{application_id}&version=eq.{version}&select=id"
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
        try:
            return int(rows[0]["id"])
        except (KeyError, TypeError, ValueError):
            return None

    def read_latest(self, job_id: str) -> Optional[dict[str, Any]]:
        """Return {content, status, version, updated_at, editor_session} for
        the latest cover_letter for job_id, or None."""
        app_id = self.applications.get_application_id(job_id)
        if app_id is None:
            return None
        endpoint = (
            f"{self.supabase_url.rstrip('/')}/rest/v1/cover_letters"
            f"?application_id=eq.{app_id}&order=version.desc&limit=1"
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
        return {
            "content": row.get("content") or "",
            "status": row.get("status") or "draft",
            "version": int(row.get("version") or 1),
            "updated_at": row.get("updated_at") or "",
            "editor_session": row.get("editor_session"),
        }

    def upsert_editor_session(self, job_id: str, session: dict[str, Any]) -> bool:
        """Persist the JobsaneEditor in-flight session for job_id.

        Stores the JSON in `cover_letters.editor_session` (JSONB) on the
        v1 row for the application. If no v1 row exists yet, creates one
        with empty content so we have somewhere to hang the session.
        Replaces the localStorage-backed src/lib/jobsane-editor/draft-store.ts
        scratch state with canonical Supabase state.
        """
        app_id = self.applications.get_application_id(job_id)
        if app_id is None:
            return False

        headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }
        existing_id = self._existing_row_id(app_id, version=1)
        if existing_id is not None:
            endpoint = (
                f"{self.supabase_url.rstrip('/')}/rest/v1/cover_letters"
                f"?id=eq.{existing_id}"
            )
            payload = {"editor_session": session}
            req = Request(
                endpoint, data=json.dumps(payload).encode("utf-8"), headers=headers, method="PATCH"
            )
        else:
            # No row yet — create one with empty content + the session.
            endpoint = f"{self.supabase_url.rstrip('/')}/rest/v1/cover_letters"
            payload = {
                "application_id": app_id,
                "version": 1,
                "content": "",
                "status": "draft",
                "editor_session": session,
            }
            req = Request(
                endpoint, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
            )

        try:
            with urlopen(req, timeout=self.timeout_sec) as resp:
                return 200 <= resp.status < 300
        except (HTTPError, URLError, TimeoutError, OSError):
            return False

    def read_editor_session(self, job_id: str) -> Optional[dict[str, Any]]:
        """Read the in-flight editor session for job_id, or None."""
        latest = self.read_latest(job_id)
        if not latest:
            return None
        return latest.get("editor_session") or None

    def clear_editor_session(self, job_id: str) -> bool:
        """Wipe the editor session JSON for job_id (sets column to NULL)."""
        app_id = self.applications.get_application_id(job_id)
        if app_id is None:
            return False
        existing_id = self._existing_row_id(app_id, version=1)
        if existing_id is None:
            return True  # no row, nothing to clear — idempotent success
        endpoint = (
            f"{self.supabase_url.rstrip('/')}/rest/v1/cover_letters"
            f"?id=eq.{existing_id}"
        )
        headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }
        body = json.dumps({"editor_session": None}).encode("utf-8")
        req = Request(endpoint, data=body, headers=headers, method="PATCH")
        try:
            with urlopen(req, timeout=self.timeout_sec) as resp:
                return 200 <= resp.status < 300
        except (HTTPError, URLError, TimeoutError, OSError):
            return False


def from_env() -> Optional[SupabaseCoverLettersCapability]:
    """Construct from JOBPIPE_SUPABASE_URL/KEY. Returns None if not set."""
    url = os.environ.get("JOBPIPE_SUPABASE_URL")
    key = os.environ.get("JOBPIPE_SUPABASE_KEY")
    if not url or not key:
        return None
    apps = SupabaseApplicationsCapability(supabase_url=url, supabase_key=key)
    return SupabaseCoverLettersCapability(
        supabase_url=url, supabase_key=key, applications=apps
    )
