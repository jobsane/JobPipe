from __future__ import annotations

import json
import subprocess
from pathlib import Path

from jobpipe.core.companion_revisions import (
    build_companion_revision_report,
    inspect_companion_revision,
    load_companion_revisions,
)


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr or completed.stdout)
    return (completed.stdout or "").strip()


def _init_git_repo(path: Path, *, branch: str = "main", remote_url: str = "https://example.test/repo.git") -> str:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-b", branch)
    _git(path, "config", "user.name", "Test User")
    _git(path, "config", "user.email", "test@example.com")
    (path / "README.md").write_text("fixture\n", encoding="utf-8")
    _git(path, "add", "README.md")
    _git(path, "commit", "-m", "init")
    _git(path, "remote", "add", "origin", remote_url)
    return _git(path, "rev-parse", "HEAD")


def _write_manifest(root: Path, companion_entries: list[dict]) -> None:
    payload = {
        "schema_version": "jobpipe.companion-revisions.v1",
        "recorded_at": "2026-04-20",
        "policy": {"mode": "polyrepo"},
        "companions": companion_entries,
    }
    (root / "COMPANION_REVISIONS.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_load_companion_revisions_reads_versioned_manifest(tmp_path: Path) -> None:
    sibling = tmp_path / "jobsync"
    commit = _init_git_repo(sibling)
    _write_manifest(
        tmp_path,
        [
            {
                "id": "jobsync",
                "path": "jobsync",
                "remote": "https://example.test/repo.git",
                "branch": "main",
                "commit": commit,
                "sync_role": "Integration seam",
                "status": "local_only_checkpoint",
            }
        ],
    )

    records = load_companion_revisions(tmp_path)

    assert len(records) == 1
    assert records[0].id == "jobsync"
    assert records[0].resolved_path(tmp_path) == sibling.resolve()


def test_inspect_companion_revision_reports_aligned_repo(tmp_path: Path) -> None:
    sibling = tmp_path / "jobsync"
    commit = _init_git_repo(sibling)
    _write_manifest(
        tmp_path,
        [
            {
                "id": "jobsync",
                "path": "jobsync",
                "remote": "https://example.test/repo.git",
                "branch": "main",
                "commit": commit,
                "sync_role": "Integration seam",
                "status": "local_only_checkpoint",
            }
        ],
    )

    record = load_companion_revisions(tmp_path)[0]
    check = inspect_companion_revision(record, base_dir=tmp_path)

    assert check.status == "aligned"
    assert check.actual_branch == "main"
    assert check.actual_commit == commit
    assert check.actual_remote == "https://example.test/repo.git"
    assert check.dirty is False


def test_build_companion_revision_report_flags_dirty_repo(tmp_path: Path) -> None:
    sibling = tmp_path / "jobsync"
    commit = _init_git_repo(sibling)
    (sibling / "README.md").write_text("dirty\n", encoding="utf-8")
    _write_manifest(
        tmp_path,
        [
            {
                "id": "jobsync",
                "path": "jobsync",
                "remote": "https://example.test/repo.git",
                "branch": "main",
                "commit": commit,
                "sync_role": "Integration seam",
                "status": "local_only_checkpoint",
            }
        ],
    )

    report = build_companion_revision_report(tmp_path)

    assert report["status"] == "drift"
    assert report["companions"][0]["status"] == "dirty"
    assert report["companions"][0]["dirty"] is True


def test_build_companion_revision_report_flags_commit_mismatch(tmp_path: Path) -> None:
    sibling = tmp_path / "reactive-resume"
    actual_commit = _init_git_repo(sibling, remote_url="https://example.test/reactive-resume.git")
    _write_manifest(
        tmp_path,
        [
            {
                "id": "reactive-resume",
                "path": "reactive-resume",
                "remote": "https://example.test/reactive-resume.git",
                "branch": "main",
                "commit": "0" * 40,
                "sync_role": "Resume subsystem baseline",
                "status": "upstream_clean_baseline",
            }
        ],
    )

    report = build_companion_revision_report(tmp_path)

    assert report["status"] == "drift"
    assert report["companions"][0]["status"] == "commit_mismatch"
    assert report["companions"][0]["actual_commit"] == actual_commit
