from __future__ import annotations

import json
from pathlib import Path

from jobpipe.cli.dashboard_server import _persist_application_notes, _persist_profile_draft
from jobpipe.cli.mark_status import load_state


def test_persist_application_notes_updates_application_state(tmp_path: Path) -> None:
    state_path = tmp_path / "reports" / "application_state.json"

    entry = _persist_application_notes(state_path, "nav_001", "Follow up next week")
    state = load_state(state_path)

    assert entry["notes"] == "Follow up next week"
    assert entry["updated_at"].endswith("Z")
    assert state["applications"]["nav_001"]["notes"] == "Follow up next week"
    assert state["applications"]["nav_001"]["status"] == ""


def test_persist_profile_draft_normalizes_values_before_writing(tmp_path: Path) -> None:
    draft_path = tmp_path / "reports" / "profile_builder_state.json"

    clean = _persist_profile_draft(
        draft_path,
        {
            "headline": "Endringsleder | Produkteier",
            "experience_years": 12,
            "summary": None,
        },
    )

    stored = json.loads(draft_path.read_text(encoding="utf-8"))
    assert clean == stored
    assert stored["headline"] == "Endringsleder | Produkteier"
    assert stored["experience_years"] == "12"
    assert "summary" not in stored
