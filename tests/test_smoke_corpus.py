"""Validates the smoke corpus structure covers APPLY, REVIEW, and SKIP cases.

Corpus lives at tests/fixtures/smoke_corpus/. Used as the shared test dataset
for issues #9 (bounded intake path) and #10 (bounded ingest mode).
"""
from __future__ import annotations

import json
from pathlib import Path

CORPUS_DIR = Path(__file__).parent / "fixtures" / "smoke_corpus"
REQUIRED_ARTIFACTS = ["00_input.json", "01_triage.json", "05_moderator.json"]
REQUIRED_FINAL_DECISIONS = {"APPLY", "REVIEW", "SKIP"}


def _job_dirs() -> list[Path]:
    return sorted(d for d in CORPUS_DIR.iterdir() if d.is_dir())


def test_corpus_dir_exists() -> None:
    assert CORPUS_DIR.exists(), f"Smoke corpus directory missing: {CORPUS_DIR}"


def test_corpus_has_at_least_three_entries() -> None:
    dirs = _job_dirs()
    assert len(dirs) >= 3, f"Expected >= 3 job dirs, found {len(dirs)}"


def test_each_entry_has_required_artifacts() -> None:
    for job_dir in _job_dirs():
        for artifact in REQUIRED_ARTIFACTS:
            path = job_dir / artifact
            assert path.exists(), f"Missing {artifact} in {job_dir.name}"


def test_artifacts_are_valid_json_objects() -> None:
    for job_dir in _job_dirs():
        for artifact in REQUIRED_ARTIFACTS:
            path = job_dir / artifact
            data = json.loads(path.read_text(encoding="utf-8"))
            assert isinstance(data, dict), f"{artifact} in {job_dir.name} is not a JSON object"


def test_input_has_title_and_employer() -> None:
    for job_dir in _job_dirs():
        data = json.loads((job_dir / "00_input.json").read_text(encoding="utf-8"))
        assert data.get("title"), f"00_input.json in {job_dir.name} missing 'title'"
        assert data.get("employer_name"), f"00_input.json in {job_dir.name} missing 'employer_name'"


def test_corpus_covers_all_decision_types() -> None:
    decisions = set()
    for job_dir in _job_dirs():
        mod = json.loads((job_dir / "05_moderator.json").read_text(encoding="utf-8"))
        decisions.add(mod.get("final_decision", "").upper())
    missing = REQUIRED_FINAL_DECISIONS - decisions
    assert not missing, f"Corpus missing final_decision types: {missing}"


def test_apply_entry_fit_score_at_least_70() -> None:
    for job_dir in _job_dirs():
        mod = json.loads((job_dir / "05_moderator.json").read_text(encoding="utf-8"))
        if mod.get("final_decision", "").upper() == "APPLY":
            assert mod.get("fit_score", 0) >= 70, (
                f"APPLY entry {job_dir.name} has fit_score {mod.get('fit_score')} (< 70)"
            )


def test_skip_entry_fit_score_below_30() -> None:
    for job_dir in _job_dirs():
        mod = json.loads((job_dir / "05_moderator.json").read_text(encoding="utf-8"))
        if mod.get("final_decision", "").upper() == "SKIP":
            assert mod.get("fit_score", 100) < 30, (
                f"SKIP entry {job_dir.name} has fit_score {mod.get('fit_score')} (>= 30)"
            )
