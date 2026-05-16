"""Unit tests for SupabaseProfileCapability — mocked PostgREST."""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

from jobpipe.workspace.supabase_profile import SupabaseProfileCapability


class _FakeResp:
    def __init__(self, *, status: int = 200, body: Any = None):
        self.status = status
        self._body = body

    def __enter__(self) -> "_FakeResp":
        return self

    def __exit__(self, *_: Any) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._body or []).encode("utf-8")


def _cap() -> SupabaseProfileCapability:
    return SupabaseProfileCapability(
        supabase_url="https://test.supabase.co",
        supabase_key="test-key",
        user_id="00000000-0000-0000-0000-000000000001",
    )


def test_read_profile_returns_shape() -> None:
    cap = _cap()

    def fake_urlopen(req, timeout: int = 0):  # noqa: ARG001
        return _FakeResp(
            status=200,
            body=[
                {
                    "profile_md": "# Profile text",
                    "resume_json": {"basics": {"name": "Lars"}},
                    "rr_resume_id": "abc-rr",
                    "version": 3,
                    "updated_at": "2026-05-16T10:00:00+00:00",
                }
            ],
        )

    with patch("jobpipe.workspace.supabase_profile.urlopen", fake_urlopen):
        profile = cap.read_profile()

    assert profile is not None
    assert profile["version"] == 3
    assert profile["profile_md"] == "# Profile text"
    assert profile["resume_json"] == {"basics": {"name": "Lars"}}
    assert profile["rr_resume_id"] == "abc-rr"


def test_read_profile_handles_string_resume_json() -> None:
    """Some PostgREST clients return JSONB columns as strings — handle that."""
    cap = _cap()

    def fake_urlopen(req, timeout: int = 0):  # noqa: ARG001
        return _FakeResp(
            status=200,
            body=[
                {
                    "profile_md": "Profile",
                    "resume_json": '{"basics": {"name": "Lars"}}',
                    "rr_resume_id": "",
                    "version": 1,
                    "updated_at": "",
                }
            ],
        )

    with patch("jobpipe.workspace.supabase_profile.urlopen", fake_urlopen):
        profile = cap.read_profile()

    assert profile is not None
    assert profile["resume_json"] == {"basics": {"name": "Lars"}}


def test_read_profile_returns_none_when_absent() -> None:
    cap = _cap()

    def fake_urlopen(req, timeout: int = 0):  # noqa: ARG001
        return _FakeResp(status=200, body=[])

    with patch("jobpipe.workspace.supabase_profile.urlopen", fake_urlopen):
        assert cap.read_profile() is None


def test_read_profile_query_includes_user_id_filter() -> None:
    cap = _cap()
    captured: dict[str, Any] = {}

    def fake_urlopen(req, timeout: int = 0):  # noqa: ARG001
        captured["url"] = req.full_url
        return _FakeResp(status=200, body=[])

    with patch("jobpipe.workspace.supabase_profile.urlopen", fake_urlopen):
        cap.read_profile()

    assert "00000000-0000-0000-0000-000000000001" in captured["url"]
    # Includes the user_id=null fallback for legacy rows
    assert "user_id.is.null" in captured["url"]


def test_read_profile_soft_fails_on_http_error() -> None:
    from urllib.error import HTTPError

    cap = _cap()

    def fake_urlopen(req, timeout: int = 0):  # noqa: ARG001
        raise HTTPError(req.full_url, 500, "boom", {}, None)

    with patch("jobpipe.workspace.supabase_profile.urlopen", fake_urlopen):
        assert cap.read_profile() is None
