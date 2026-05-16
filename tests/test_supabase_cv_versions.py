"""Unit tests for SupabaseCvVersionsCapability — mocked PostgREST."""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from jobpipe.workspace.supabase_applications import SupabaseApplicationsCapability
from jobpipe.workspace.supabase_cv_versions import SupabaseCvVersionsCapability


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


def _cap() -> SupabaseCvVersionsCapability:
    apps = MagicMock(spec=SupabaseApplicationsCapability)
    apps.get_application_id.return_value = 42
    return SupabaseCvVersionsCapability(
        supabase_url="https://test.supabase.co",
        supabase_key="test-key",
        applications=apps,
    )


def test_upsert_patches_creates_new_row() -> None:
    cap = _cap()
    calls: list[Any] = []

    def fake_urlopen(req, timeout: int = 0):  # noqa: ARG001
        calls.append({"method": req.get_method(), "body": _bytes_to_obj(req.data) if req.data else None})
        if req.get_method() == "GET":
            return _FakeResp(status=200, body=[])
        return _FakeResp(status=201, body=None)

    with patch("jobpipe.workspace.supabase_cv_versions.urlopen", fake_urlopen):
        ok = cap.upsert_patches(
            "job-xyz",
            patches=[{"id": "p1", "section": "experience", "proposed": "..."}],
        )

    assert ok is True
    assert calls[0]["method"] == "GET"  # existing row lookup
    assert calls[1]["method"] == "POST"
    assert calls[1]["body"]["application_id"] == 42
    assert calls[1]["body"]["patches"][0]["id"] == "p1"
    assert calls[1]["body"]["status"] == "draft"


def test_upsert_patches_patches_existing_row() -> None:
    cap = _cap()
    calls: list[Any] = []

    def fake_urlopen(req, timeout: int = 0):  # noqa: ARG001
        calls.append({"method": req.get_method(), "url": req.full_url})
        if req.get_method() == "GET":
            return _FakeResp(status=200, body=[{"id": 7}])
        return _FakeResp(status=204, body=None)

    with patch("jobpipe.workspace.supabase_cv_versions.urlopen", fake_urlopen):
        ok = cap.upsert_patches("job-xyz", patches=[])

    assert ok is True
    assert calls[1]["method"] == "PATCH"
    assert "id=eq.7" in calls[1]["url"]


def test_upsert_patches_rejects_invalid_status() -> None:
    cap = _cap()
    with patch("jobpipe.workspace.supabase_cv_versions.urlopen") as up:
        ok = cap.upsert_patches("job-xyz", patches=[], status="zombie")
    assert ok is False
    up.assert_not_called()


def test_upsert_patches_when_application_id_missing() -> None:
    apps = MagicMock(spec=SupabaseApplicationsCapability)
    apps.get_application_id.return_value = None
    cap = SupabaseCvVersionsCapability(
        supabase_url="https://test.supabase.co",
        supabase_key="test-key",
        applications=apps,
    )
    with patch("jobpipe.workspace.supabase_cv_versions.urlopen") as up:
        ok = cap.upsert_patches("job-xyz", patches=[])
    assert ok is False
    up.assert_not_called()


def test_accept_patch_appends_to_accepted_patches() -> None:
    cap = _cap()
    state: dict[str, Any] = {
        "phase": "read",
        "existing": {
            "patches": [{"id": "p1"}],
            "accepted_patches": [],
            "status": "draft",
            "version": 1,
            "rr_resume_id": "",
            "updated_at": "",
        },
        "wrote": None,
    }

    def fake_urlopen(req, timeout: int = 0):  # noqa: ARG001
        if req.get_method() == "GET":
            if state["phase"] == "read":
                # First GET is for read_latest (returns existing row)
                state["phase"] = "existing-id"
                return _FakeResp(
                    status=200,
                    body=[
                        {
                            "patches": state["existing"]["patches"],
                            "accepted_patches": state["existing"]["accepted_patches"],
                            "status": state["existing"]["status"],
                            "version": 1,
                            "rr_resume_id": "",
                            "updated_at": "",
                        }
                    ],
                )
            # Second GET is _existing_row_id lookup before upsert
            return _FakeResp(status=200, body=[{"id": 7}])
        # PATCH
        state["wrote"] = _bytes_to_obj(req.data) if req.data else None
        return _FakeResp(status=204, body=None)

    with patch("jobpipe.workspace.supabase_cv_versions.urlopen", fake_urlopen):
        ok = cap.accept_patch("job-xyz", {"id": "p1", "approved": True})

    assert ok is True
    assert state["wrote"] is not None
    assert len(state["wrote"]["accepted_patches"]) == 1
    assert state["wrote"]["accepted_patches"][0]["id"] == "p1"
    assert state["wrote"]["status"] == "reviewed"


def test_reject_patch_removes_from_patches() -> None:
    cap = _cap()
    written: dict[str, Any] = {}

    def fake_urlopen(req, timeout: int = 0):  # noqa: ARG001
        if req.get_method() == "GET":
            # read_latest first call
            if "select=id" not in req.full_url:
                return _FakeResp(
                    status=200,
                    body=[
                        {
                            "patches": [{"id": "p1"}, {"id": "p2"}],
                            "accepted_patches": [],
                            "status": "draft",
                            "version": 1,
                            "rr_resume_id": "",
                            "updated_at": "",
                        }
                    ],
                )
            return _FakeResp(status=200, body=[{"id": 7}])
        written.update(_bytes_to_obj(req.data) if req.data else {})
        return _FakeResp(status=204, body=None)

    with patch("jobpipe.workspace.supabase_cv_versions.urlopen", fake_urlopen):
        ok = cap.reject_patch("job-xyz", "p1")

    assert ok is True
    ids = [p["id"] for p in written["patches"]]
    assert ids == ["p2"]


def test_read_latest_returns_shape() -> None:
    cap = _cap()

    def fake_urlopen(req, timeout: int = 0):  # noqa: ARG001
        return _FakeResp(
            status=200,
            body=[
                {
                    "patches": [{"id": "p1"}],
                    "accepted_patches": [{"id": "p0"}],
                    "status": "reviewed",
                    "version": 2,
                    "rr_resume_id": "abc-123",
                    "updated_at": "2026-05-16T00:00:00+00:00",
                }
            ],
        )

    with patch("jobpipe.workspace.supabase_cv_versions.urlopen", fake_urlopen):
        result = cap.read_latest("job-xyz")

    assert result is not None
    assert result["version"] == 2
    assert result["status"] == "reviewed"
    assert result["patches"] == [{"id": "p1"}]
    assert result["accepted_patches"] == [{"id": "p0"}]
    assert result["rr_resume_id"] == "abc-123"


def test_read_latest_returns_none_when_absent() -> None:
    cap = _cap()

    def fake_urlopen(req, timeout: int = 0):  # noqa: ARG001
        return _FakeResp(status=200, body=[])

    with patch("jobpipe.workspace.supabase_cv_versions.urlopen", fake_urlopen):
        assert cap.read_latest("job-nope") is None
