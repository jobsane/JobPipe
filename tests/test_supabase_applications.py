"""Unit tests for SupabaseApplicationsCapability.

Mocks urlopen — no real PostgREST traffic. Verifies request shape, status
mapping (hub-shape <-> applications.status), and edge cases.
"""
from __future__ import annotations

import io
import json
from typing import Any
from unittest.mock import patch

import pytest

from jobpipe.workspace.supabase_applications import (
    SupabaseApplicationsCapability,
    _state_to_status,
    _status_to_state,
)


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


def _cap() -> SupabaseApplicationsCapability:
    return SupabaseApplicationsCapability(
        supabase_url="https://test.supabase.co",
        supabase_key="test-key",
    )


def test_state_to_status_maps_decided_apply_drafting_to_shortlisted() -> None:
    assert _state_to_status("decided_apply", "drafting") == "shortlisted"


def test_state_to_status_maps_decided_apply_applied() -> None:
    assert _state_to_status("decided_apply", "applied") == "applied"


def test_state_to_status_maps_decided_skip_to_dismissed() -> None:
    assert _state_to_status("decided_skip", None) == "dismissed"


def test_state_to_status_to_review_is_shortlisted() -> None:
    assert _state_to_status("to_review", None) == "shortlisted"


def test_state_to_status_maps_ghosted_to_rejected() -> None:
    # "ghosted" is JobDesk's term for applications that went silent; we
    # collapse it to "rejected" on the canonical side.
    assert _state_to_status("decided_apply", "ghosted") == "rejected"


def test_status_to_state_round_trips_for_applied() -> None:
    state = _status_to_state("applied")
    assert state == {"decisionStatus": "decided_apply", "applicationStatus": "applied"}


def test_status_to_state_dismissed() -> None:
    state = _status_to_state("dismissed")
    assert state == {"decisionStatus": "decided_skip", "applicationStatus": None}


def test_status_to_state_shortlisted_is_to_review() -> None:
    state = _status_to_state("shortlisted")
    assert state == {"decisionStatus": "to_review", "applicationStatus": None}


def test_upsert_state_posts_correct_payload_and_returns_true() -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(req, timeout: int = 0):  # noqa: ARG001
        captured["method"] = req.get_method()
        captured["url"] = req.full_url
        captured["headers"] = dict(req.header_items())
        captured["body"] = _bytes_to_obj(req.data) if req.data else None
        return _FakeResp(status=201, body=None)

    with patch("jobpipe.workspace.supabase_applications.urlopen", fake_urlopen):
        ok = _cap().upsert_state(
            "job-xyz",
            decision_status="decided_apply",
            application_status="applied",
        )

    assert ok is True
    assert captured["method"] == "POST"
    assert captured["url"] == "https://test.supabase.co/rest/v1/applications"
    assert captured["body"]["job_id"] == "job-xyz"
    assert captured["body"]["status"] == "applied"
    # applied_at is auto-stamped on transition into applied state
    assert "applied_at" in captured["body"]
    # PostgREST upsert needs the merge-duplicates Prefer
    assert "merge-duplicates" in captured["headers"].get("Prefer", "")


def test_upsert_state_returns_false_on_invalid_status() -> None:
    # Hub-shape that maps to an invalid status would be filtered out before
    # we get here, but defensively the capability filters too.
    with patch("jobpipe.workspace.supabase_applications.urlopen") as up:
        ok = _cap().upsert_state("job-xyz", decision_status="garbage")
    assert ok is False
    up.assert_not_called()


def test_upsert_state_handles_http_error_softly() -> None:
    from urllib.error import HTTPError

    def fake_urlopen(req, timeout: int = 0):  # noqa: ARG001
        raise HTTPError(req.full_url, 500, "boom", {}, None)

    with patch("jobpipe.workspace.supabase_applications.urlopen", fake_urlopen):
        ok = _cap().upsert_state(
            "job-xyz", decision_status="decided_apply", application_status="applied"
        )
    # Best-effort: errors don't raise into the hub
    assert ok is False


def test_get_state_returns_hub_shaped_dict() -> None:
    def fake_urlopen(req, timeout: int = 0):  # noqa: ARG001
        return _FakeResp(
            status=200,
            body=[
                {
                    "status": "applied",
                    "applied_at": "2026-05-16T00:00:00+00:00",
                    "notes": None,
                }
            ],
        )

    with patch("jobpipe.workspace.supabase_applications.urlopen", fake_urlopen):
        state = _cap().get_state("job-xyz")

    assert state is not None
    assert state["decisionStatus"] == "decided_apply"
    assert state["applicationStatus"] == "applied"


def test_get_state_returns_none_for_missing() -> None:
    def fake_urlopen(req, timeout: int = 0):  # noqa: ARG001
        return _FakeResp(status=200, body=[])

    with patch("jobpipe.workspace.supabase_applications.urlopen", fake_urlopen):
        assert _cap().get_state("job-nope") is None


def test_list_state_omits_default_to_review_rows() -> None:
    def fake_urlopen(req, timeout: int = 0):  # noqa: ARG001
        return _FakeResp(
            status=200,
            body=[
                {"job_id": "job-1", "status": "applied", "notes": None},
                {"job_id": "job-2", "status": "shortlisted", "notes": None},
                {"job_id": "job-3", "status": "dismissed", "notes": "not interested"},
            ],
        )

    with patch("jobpipe.workspace.supabase_applications.urlopen", fake_urlopen):
        state = _cap().list_state()

    # Only non-default rows surface
    assert set(state.keys()) == {"job-1", "job-3"}
    assert state["job-3"]["decisionStatus"] == "decided_skip"
    assert state["job-3"]["skipReason"] == "not interested"


def test_clear_state_resets_to_to_review() -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(req, timeout: int = 0):  # noqa: ARG001
        captured["body"] = _bytes_to_obj(req.data) if req.data else None
        return _FakeResp(status=200, body=None)

    with patch("jobpipe.workspace.supabase_applications.urlopen", fake_urlopen):
        ok = _cap().clear_state("job-xyz")

    assert ok is True
    assert captured["body"]["status"] == "shortlisted"


def test_get_application_id_reuses_existing() -> None:
    calls = []

    def fake_urlopen(req, timeout: int = 0):  # noqa: ARG001
        calls.append(req.full_url)
        return _FakeResp(status=200, body=[{"id": 42}])

    with patch("jobpipe.workspace.supabase_applications.urlopen", fake_urlopen):
        app_id = _cap().get_application_id("job-xyz")

    assert app_id == 42
    # No upsert needed — only the read query fired
    assert len(calls) == 1


def test_get_application_id_creates_then_reads() -> None:
    """When no row exists, upsert a shortlisted row then re-read for the id."""
    calls = []
    bodies = []

    def fake_urlopen(req, timeout: int = 0):  # noqa: ARG001
        calls.append(req.get_method())
        if req.data:
            bodies.append(_bytes_to_obj(req.data))
        # First read: empty. Upsert: ok. Second read: returns id.
        if len(calls) == 1:
            return _FakeResp(status=200, body=[])
        if len(calls) == 2:
            return _FakeResp(status=201, body=None)
        return _FakeResp(status=200, body=[{"id": 99}])

    with patch("jobpipe.workspace.supabase_applications.urlopen", fake_urlopen):
        app_id = _cap().get_application_id("job-new")

    assert app_id == 99
    assert calls == ["GET", "POST", "GET"]
    # The upsert posted a shortlisted row for the new job_id
    assert bodies[0] == {"job_id": "job-new", "status": "shortlisted"}
