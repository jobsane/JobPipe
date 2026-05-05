"""Tests for the bounded ingest mode (issue #10).

Validates that `jobpipe run-feed` is registered as a CLI command and that
the smoke corpus input JSONL is well-formed for use as a bounded corpus.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

CORPUS_JSONL = Path(__file__).parent / "fixtures" / "smoke_corpus_input.jsonl"


def test_run_feed_registered_in_cli() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "jobpipe.cli.main", "run-feed", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"jobpipe run-feed --help exited {result.returncode}:\n{result.stderr}"
    )
    assert "--jobs" in result.stdout, "Expected --jobs in run-feed help output"


def test_smoke_corpus_input_exists() -> None:
    assert CORPUS_JSONL.exists(), f"smoke_corpus_input.jsonl missing: {CORPUS_JSONL}"


def test_smoke_corpus_input_has_three_entries() -> None:
    lines = [l for l in CORPUS_JSONL.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 3, f"Expected 3 entries, found {len(lines)}"


def test_smoke_corpus_input_entries_are_valid_json() -> None:
    lines = [l for l in CORPUS_JSONL.read_text(encoding="utf-8").splitlines() if l.strip()]
    for i, line in enumerate(lines):
        obj = json.loads(line)
        assert isinstance(obj, dict), f"Line {i} is not a JSON object"
        assert obj.get("title"), f"Line {i} missing 'title'"
        assert obj.get("employer_name"), f"Line {i} missing 'employer_name'"
