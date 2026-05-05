"""Tests for the bounded-intake CLI command (issue #9).

Validates that `jobpipe bounded-intake` is registered in MODULE_COMMANDS
and that bounded_intake.py exposes the expected --corpus / --no-sync flags.
"""
from __future__ import annotations

import subprocess
import sys


def test_bounded_intake_registered_in_cli() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "jobpipe.cli.main", "bounded-intake", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"jobpipe bounded-intake --help exited {result.returncode}:\n{result.stderr}"
    )
    assert "--corpus" in result.stdout, "Expected --corpus in bounded-intake help output"


def test_bounded_intake_no_sync_flag_present() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "jobpipe.cli.main", "bounded-intake", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--no-sync" in result.stdout, "Expected --no-sync in bounded-intake help output"


def test_bounded_intake_missing_corpus_exits_nonzero() -> None:
    result = subprocess.run(
        [
            sys.executable, "-m", "jobpipe.cli.bounded_intake",
            "--corpus", "nonexistent_file_that_cannot_exist.jsonl",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, "Expected nonzero exit when corpus file is missing"
