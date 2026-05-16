"""Unit tests for SupabaseCoverLettersCapability — mocked PostgREST."""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from jobpipe.workspace.supabase_applications import SupabaseApplicationsCapability
from jobpipe.workspace.supabase_cover_letters import SupabaseCoverLettersCapability


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


def _bytes_to_obj(b: bytes) -> dict[str, Any]:
    return json.loads(b.decode("utf-8"))


def _cap() -> SupabaseCoverLettersCapability:
    apps = MagicMock(spec=SupabaseApplicationsCapability)
    apps.get_application_id.return_value = 42
    return SupabaseCoverLettersCapability(
        supabase_url="https://test.supabase.co",
        supabase_key="test-key",
        applications=apps,
    )


def test_upsert_content_creates_new_row_when_none_exists() -> None:
    """When there's no existing cover_letter for this application, POST a fresh row."""
    cap = _cap()
    requests: list[Any] = []

    def fake_urlopen(req, timeout: int = 0):  # noqa: ARG001
        requests.append({"method": req.get_method(), "url": req.full_url, "body": _bytes_to_obj(req.data) if req.data else None})
        # First call: GET existing → empty. Second call: POST new row → 201.
        if req.get_method() == "GET":
            return _FakeResp(status=200, body=[])
        return _FakeResp(status=201, body=None)

    with patch("jobpipe.workspace.supabase_cover_letters.urlopen", fake_urlopen):
        ok = cap.upsert_content("job-xyz", content="Dear hiring team,")

    assert ok is True
    assert len(requests) == 2
    assert requests[0]["method"] == "GET"
    assert requests[1]["method"] == "POST"
    assert requests[1]["body"]["application_id"] == 42
    assert requests[1]["body"]["content"] == "Dear hiring team,"
    assert requests[1]["body"]["version"] == 1
    assert requests[1]["body"]["status"] == "draft"


def test_upsert_content_patches_existing_row() -> None:
    """When a v1 row exists, PATCH it instead of creating a duplicate."""
    cap = _cap()
    requests: list[Any] = []

    def fake_urlopen(req, timeout: int = 0):  # noqa: ARG001
        requests.append({"method": req.get_method(), "url": req.full_url})
        if req.get_method() == "GET":
            return _FakeResp(status=200, body=[{"id": 7}])
        return _FakeResp(status=204, body=None)

    with patch("jobpipe.workspace.supabase_cover_letters.urlopen", fake_urlopen):
        ok = cap.upsert_content("job-xyz", content="Updated text.")

    assert ok is True
    assert requests[1]["method"] == "PATCH"
    assert "id=eq.7" in requests[1]["url"]


def test_upsert_content_rejects_empty_text() -> None:
    cap = _cap()
    with patch("jobpipe.workspace.supabase_cover_letters.urlopen") as up:
        assert cap.upsert_content("job-xyz", content="   ") is False
        assert cap.upsert_content("job-xyz", content="") is False
    up.assert_not_called()


def test_upsert_content_handles_missing_application_id() -> None:
    """If applications.get_application_id returns None, give up cleanly."""
    apps = MagicMock(spec=SupabaseApplicationsCapability)
    apps.get_application_id.return_value = None
    cap = SupabaseCoverLettersCapability(
        supabase_url="https://test.supabase.co",
        supabase_key="test-key",
        applications=apps,
    )
    with patch("jobpipe.workspace.supabase_cover_letters.urlopen") as up:
        assert cap.upsert_content("job-xyz", content="x") is False
    up.assert_not_called()


def test_read_latest_returns_shape() -> None:
    cap = _cap()

    def fake_urlopen(req, timeout: int = 0):  # noqa: ARG001
        return _FakeResp(
            status=200,
            body=[
                {
                    "content": "Dear team,",
                    "status": "draft",
                    "version": 1,
                    "updated_at": "2026-05-16T00:00:00+00:00",
                }
            ],
        )

    with patch("jobpipe.workspace.supabase_cover_letters.urlopen", fake_urlopen):
        result = cap.read_latest("job-xyz")

    assert result is not None
    assert result["content"] == "Dear team,"
    assert result["version"] == 1
    assert result["status"] == "draft"


def test_read_latest_returns_none_when_absent() -> None:
    cap = _cap()

    def fake_urlopen(req, timeout: int = 0):  # noqa: ARG001
        return _FakeResp(status=200, body=[])

    with patch("jobpipe.workspace.supabase_cover_letters.urlopen", fake_urlopen):
        assert cap.read_latest("job-nope") is None


def test_upsert_content_soft_fails_on_http_error() -> None:
    from urllib.error import HTTPError

    cap = _cap()

    def fake_urlopen(req, timeout: int = 0):  # noqa: ARG001
        if req.get_method() == "GET":
            return _FakeResp(status=200, body=[])
        raise HTTPError(req.full_url, 500, "boom", {}, None)

    with patch("jobpipe.workspace.supabase_cover_letters.urlopen", fake_urlopen):
        assert cap.upsert_content("job-xyz", content="x") is False


def test_upsert_editor_session_creates_row_when_no_v1_exists() -> None:
    cap = _cap()
    calls: list[Any] = []

    def fake_urlopen(req, timeout: int = 0):  # noqa: ARG001
        calls.append({"method": req.get_method(), "body": _bytes_to_obj(req.data) if req.data else None})
        if req.get_method() == "GET":
            return _FakeResp(status=200, body=[])
        return _FakeResp(status=201, body=None)

    with patch("jobpipe.workspace.supabase_cover_letters.urlopen", fake_urlopen):
        ok = cap.upsert_editor_session("job-xyz", {"target": "App letter", "motivation": None})

    assert ok is True
    # GET to find existing → none → POST to create with editor_session
    assert calls[0]["method"] == "GET"
    assert calls[1]["method"] == "POST"
    assert calls[1]["body"]["editor_session"]["target"] == "App letter"
    assert calls[1]["body"]["content"] == ""  # empty placeholder
    assert calls[1]["body"]["application_id"] == 42


def test_upsert_editor_session_patches_existing_row() -> None:
    cap = _cap()
    calls: list[Any] = []

    def fake_urlopen(req, timeout: int = 0):  # noqa: ARG001
        calls.append({"method": req.get_method(), "url": req.full_url, "body": _bytes_to_obj(req.data) if req.data else None})
        if req.get_method() == "GET":
            return _FakeResp(status=200, body=[{"id": 7}])
        return _FakeResp(status=204, body=None)

    with patch("jobpipe.workspace.supabase_cover_letters.urlopen", fake_urlopen):
        ok = cap.upsert_editor_session("job-xyz", {"target": "App", "plan": {}})

    assert ok is True
    assert calls[1]["method"] == "PATCH"
    assert "id=eq.7" in calls[1]["url"]
    # PATCH only sets editor_session — doesn't overwrite content
    assert "content" not in calls[1]["body"]
    assert calls[1]["body"]["editor_session"]["target"] == "App"


def test_read_editor_session_returns_jsonb_value() -> None:
    cap = _cap()

    def fake_urlopen(req, timeout: int = 0):  # noqa: ARG001
        return _FakeResp(
            status=200,
            body=[
                {
                    "content": "letter text",
                    "status": "draft",
                    "version": 1,
                    "updated_at": "",
                    "editor_session": {"target": "X", "plan": {"section_count": 3}},
                }
            ],
        )

    with patch("jobpipe.workspace.supabase_cover_letters.urlopen", fake_urlopen):
        session = cap.read_editor_session("job-xyz")

    assert session == {"target": "X", "plan": {"section_count": 3}}


def test_read_editor_session_returns_none_when_jsonb_is_null() -> None:
    cap = _cap()

    def fake_urlopen(req, timeout: int = 0):  # noqa: ARG001
        return _FakeResp(
            status=200,
            body=[{"content": "x", "status": "draft", "version": 1, "updated_at": "", "editor_session": None}],
        )

    with patch("jobpipe.workspace.supabase_cover_letters.urlopen", fake_urlopen):
        assert cap.read_editor_session("job-xyz") is None


def test_clear_editor_session_patches_null() -> None:
    cap = _cap()
    body_sent: dict[str, Any] = {}

    def fake_urlopen(req, timeout: int = 0):  # noqa: ARG001
        if req.get_method() == "GET":
            return _FakeResp(status=200, body=[{"id": 7}])
        body_sent.update(_bytes_to_obj(req.data) if req.data else {})
        return _FakeResp(status=204, body=None)

    with patch("jobpipe.workspace.supabase_cover_letters.urlopen", fake_urlopen):
        ok = cap.clear_editor_session("job-xyz")

    assert ok is True
    assert body_sent["editor_session"] is None


def test_clear_editor_session_idempotent_when_no_row() -> None:
    cap = _cap()

    def fake_urlopen(req, timeout: int = 0):  # noqa: ARG001
        return _FakeResp(status=200, body=[])

    with patch("jobpipe.workspace.supabase_cover_letters.urlopen", fake_urlopen):
        assert cap.clear_editor_session("job-nope") is True
