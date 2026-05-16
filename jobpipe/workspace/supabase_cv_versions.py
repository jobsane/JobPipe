"""Supabase-backed cv_versions capability — durable store for the value-draft
suggestion/accept loop.

JobData schema:
  cv_versions(
    id SERIAL PRIMARY KEY,
    application_id INTEGER NOT NULL REFERENCES applications(id),
    version INTEGER NOT NULL DEFAULT 1,
    patches JSONB NOT NULL,            -- list of SuggestedPatch objects (in-flight)
    accepted_patches JSONB,            -- list of AcceptedPatch (after review)
    status TEXT DEFAULT 'draft',       -- draft / reviewed / exported
    rr_resume_id TEXT,                  -- RR resume id after export
    created_at / updated_at TIMESTAMPTZ
  )

Writes target the v1 row per application (single-version model for now);
"Mark sent" snapshot mode would bump version and clone the row immutable.

Best-effort: errors don't raise into the hub; caller falls back to disk-
backed override JSON when Supabase isn't configured.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .supabase_applications import SupabaseApplicationsCapability


_DEFAULT_TIMEOUT_SEC = 10


@dataclass(frozen=True)
class SupabaseCvVersionsCapability:
    supabase_url: str
    supabase_key: str
    applications: SupabaseApplicationsCapability
    timeout_sec: int = _DEFAULT_TIMEOUT_SEC

    def upsert_patches(
        self,
        job_id: str,
        *,
        patches: list[dict[str, Any]],
        accepted_patches: Optional[list[dict[str, Any]]] = None,
        status: str = "draft",
    ) -> bool:
        """Upsert the v1 cv_version for job_id. Returns True on 2xx."""
        if status not in ("draft", "reviewed", "exported"):
            return False
        app_id = self.applications.get_application_id(job_id)
        if app_id is None:
            return False

        payload: dict[str, Any] = {
            "application_id": app_id,
            "version": 1,
            "patches": patches,
            "status": status,
        }
        if accepted_patches is not None:
            payload["accepted_patches"] = accepted_patches

        existing = self._existing_row_id(app_id, version=1)
        headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }
        body = json.dumps(payload).encode("utf-8")
        if existing is not None:
            endpoint = (
                f"{self.supabase_url.rstrip('/')}/rest/v1/cv_versions"
                f"?id=eq.{existing}"
            )
            req = Request(endpoint, data=body, headers=headers, method="PATCH")
        else:
            endpoint = f"{self.supabase_url.rstrip('/')}/rest/v1/cv_versions"
            req = Request(endpoint, data=body, headers=headers, method="POST")

        try:
            with urlopen(req, timeout=self.timeout_sec) as resp:
                return 200 <= resp.status < 300
        except (HTTPError, URLError, TimeoutError, OSError):
            return False

    def accept_patch(self, job_id: str, patch: dict[str, Any]) -> bool:
        """Append one approved patch to accepted_patches. Reads the current
        list, appends, writes back. PostgREST doesn't expose JSONB-array-
        append natively, so a read-modify-write is the cheap path.
        """
        current = self.read_latest(job_id)
        accepted = list(current.get("accepted_patches") or []) if current else []
        accepted.append(patch)
        patches = list(current.get("patches") or []) if current else []
        return self.upsert_patches(
            job_id,
            patches=patches,
            accepted_patches=accepted,
            status="reviewed" if current else "draft",
        )

    def reject_patch(self, job_id: str, patch_id: str) -> bool:
        """Remove a patch from `patches` (in-flight) without accepting it."""
        current = self.read_latest(job_id)
        if not current:
            return False
        patches = [p for p in (current.get("patches") or []) if p.get("id") != patch_id]
        return self.upsert_patches(
            job_id,
            patches=patches,
            accepted_patches=current.get("accepted_patches"),
            status=current.get("status") or "draft",
        )

    def read_latest(self, job_id: str) -> Optional[dict[str, Any]]:
        app_id = self.applications.get_application_id(job_id)
        if app_id is None:
            return None
        endpoint = (
            f"{self.supabase_url.rstrip('/')}/rest/v1/cv_versions"
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
            "patches": row.get("patches") or [],
            "accepted_patches": row.get("accepted_patches") or [],
            "status": row.get("status") or "draft",
            "version": int(row.get("version") or 1),
            "rr_resume_id": row.get("rr_resume_id") or "",
            "updated_at": row.get("updated_at") or "",
        }

    def _existing_row_id(self, application_id: int, *, version: int) -> Optional[int]:
        endpoint = (
            f"{self.supabase_url.rstrip('/')}/rest/v1/cv_versions"
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


def from_env() -> Optional[SupabaseCvVersionsCapability]:
    url = os.environ.get("JOBPIPE_SUPABASE_URL")
    key = os.environ.get("JOBPIPE_SUPABASE_KEY")
    if not url or not key:
        return None
    apps = SupabaseApplicationsCapability(supabase_url=url, supabase_key=key)
    return SupabaseCvVersionsCapability(
        supabase_url=url, supabase_key=key, applications=apps
    )
