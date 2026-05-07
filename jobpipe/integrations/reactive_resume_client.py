"""Reactive Resume REST API client (OpenAPI layer).

RR v5 exposes a REST API at /api/openapi/.
Auth: x-api-key header (create key in RR UI → Settings → API Keys).

Key endpoints:
  POST /api/openapi/resumes/import   — import resume data, returns new resume ID
  PUT  /api/openapi/resumes/{id}     — replace resume data
  GET  /api/openapi/resumes          — list resumes
  GET  /api/openapi/resumes/{id}     — get resume by ID
  PATCH /api/openapi/resume/{id}     — JSON Patch (RFC 6902) partial update
"""
from __future__ import annotations

import requests


def _headers(api_key: str) -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    if api_key:
        h["x-api-key"] = api_key
    return h


def _base(base_url: str) -> str:
    return base_url.rstrip("/") + "/api/openapi"


def import_resume(
    base_url: str,
    resume_data: dict,
    *,
    api_key: str = "",
) -> str:
    """Create a new resume from data. Returns the new resume ID."""
    resp = requests.post(
        f"{_base(base_url)}/resumes/import",
        json={"data": resume_data},
        headers=_headers(api_key),
        timeout=15,
    )
    resp.raise_for_status()
    body = resp.json()
    # Response is a plain string ID or wrapped object
    if isinstance(body, str):
        return body
    return str(body.get("id") or body.get("data") or body)


def update_resume(
    base_url: str,
    resume_id: str,
    resume_data: dict,
    *,
    api_key: str = "",
    name: str = "",
) -> dict:
    """Replace the data (and optionally name) of an existing resume."""
    payload: dict = {"data": resume_data}
    if name:
        payload["name"] = name
    resp = requests.put(
        f"{_base(base_url)}/resumes/{resume_id}",
        json=payload,
        headers=_headers(api_key),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def list_resumes(base_url: str, *, api_key: str = "") -> list[dict]:
    """Return all resumes for the authenticated user (without full data)."""
    resp = requests.get(
        f"{_base(base_url)}/resumes",
        headers=_headers(api_key),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def get_resume(base_url: str, resume_id: str, *, api_key: str = "") -> dict:
    """Return a single resume with full data."""
    resp = requests.get(
        f"{_base(base_url)}/resumes/{resume_id}",
        headers=_headers(api_key),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def get_resume_url(base_url: str, resume_id: str) -> str:
    """Return the builder URL for a resume."""
    return f"{base_url.rstrip('/')}/builder/{resume_id}"


# ---------------------------------------------------------------------------
# Legacy shim — kept so existing callers don't break while we migrate
# ---------------------------------------------------------------------------

def push_resume_to_rr(
    base_url: str,
    resume_json: dict,
    *,
    token: str = "",
) -> dict:
    """Compat shim: import resume_json as new resume. Returns {"id": <id>}."""
    resume_id = import_resume(base_url, resume_json, api_key=token)
    return {"id": resume_id}


def update_resume_in_rr(
    base_url: str,
    resume_id: str,
    resume_json: dict,
    *,
    token: str = "",
) -> dict:
    """Compat shim: update resume by ID with resume_json as data."""
    return update_resume(base_url, resume_id, resume_json, api_key=token)


__all__ = [
    "import_resume",
    "update_resume",
    "list_resumes",
    "get_resume",
    "get_resume_url",
    "push_resume_to_rr",
    "update_resume_in_rr",
]
