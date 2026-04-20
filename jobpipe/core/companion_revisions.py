from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from jobpipe.core.paths import repo_root


COMPANION_REVISIONS_SCHEMA = "jobpipe.companion-revisions.v1"


@dataclass(frozen=True)
class CompanionRevision:
    id: str
    path: str
    remote: str
    branch: str
    commit: str
    sync_role: str
    status: str

    def resolved_path(self, base_dir: Path) -> Path:
        return (base_dir / self.path).resolve()


@dataclass(frozen=True)
class CompanionRevisionCheck:
    companion_id: str
    expected_path: str
    resolved_path: str
    pinned_remote: str
    pinned_branch: str
    pinned_commit: str
    sync_role: str
    pin_status: str
    exists: bool
    is_git_repo: bool
    actual_remote: str
    actual_branch: str
    actual_commit: str
    dirty: bool
    status: str
    notes: List[str]

    @property
    def aligned(self) -> bool:
        return self.status == "aligned"


def companion_revisions_path(base_dir: Path | None = None) -> Path:
    root = Path(base_dir).resolve() if base_dir else repo_root()
    return root / "COMPANION_REVISIONS.json"


def load_companion_revisions(base_dir: Path | None = None) -> List[CompanionRevision]:
    path = companion_revisions_path(base_dir)
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema_version = str(payload.get("schema_version") or "")
    if schema_version != COMPANION_REVISIONS_SCHEMA:
        raise ValueError(f"Unsupported companion revisions schema: {schema_version or '<missing>'}")

    companions = payload.get("companions")
    if not isinstance(companions, list):
        raise ValueError("COMPANION_REVISIONS.json must contain a companions list")

    records: List[CompanionRevision] = []
    for item in companions:
        if not isinstance(item, dict):
            raise ValueError("Each companion entry must be an object")
        records.append(
            CompanionRevision(
                id=str(item.get("id") or "").strip(),
                path=str(item.get("path") or "").strip(),
                remote=str(item.get("remote") or "").strip(),
                branch=str(item.get("branch") or "").strip(),
                commit=str(item.get("commit") or "").strip(),
                sync_role=str(item.get("sync_role") or "").strip(),
                status=str(item.get("status") or "").strip(),
            )
        )

    missing = [record.id for record in records if not record.id or not record.path or not record.commit]
    if missing:
        raise ValueError(f"Companion entries missing required fields: {', '.join(missing)}")
    return records


def _run_git(repo_path: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(repo_path),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        raise RuntimeError(stderr or f"git {' '.join(args)} failed with code {completed.returncode}")
    return (completed.stdout or "").strip()


def inspect_companion_revision(record: CompanionRevision, *, base_dir: Path | None = None) -> CompanionRevisionCheck:
    root = Path(base_dir).resolve() if base_dir else repo_root()
    target_path = record.resolved_path(root)
    notes: List[str] = []

    if not target_path.exists():
        return CompanionRevisionCheck(
            companion_id=record.id,
            expected_path=record.path,
            resolved_path=str(target_path),
            pinned_remote=record.remote,
            pinned_branch=record.branch,
            pinned_commit=record.commit,
            sync_role=record.sync_role,
            pin_status=record.status,
            exists=False,
            is_git_repo=False,
            actual_remote="",
            actual_branch="",
            actual_commit="",
            dirty=False,
            status="missing_repo",
            notes=["Local companion path is missing."],
        )

    git_dir = target_path / ".git"
    if not git_dir.exists():
        return CompanionRevisionCheck(
            companion_id=record.id,
            expected_path=record.path,
            resolved_path=str(target_path),
            pinned_remote=record.remote,
            pinned_branch=record.branch,
            pinned_commit=record.commit,
            sync_role=record.sync_role,
            pin_status=record.status,
            exists=True,
            is_git_repo=False,
            actual_remote="",
            actual_branch="",
            actual_commit="",
            dirty=False,
            status="not_git_repo",
            notes=["Local companion path exists but is not a git repo."],
        )

    actual_commit = _run_git(target_path, "rev-parse", "HEAD")
    actual_branch = _run_git(target_path, "branch", "--show-current")
    actual_remote = ""
    try:
        actual_remote = _run_git(target_path, "remote", "get-url", "origin")
    except RuntimeError:
        notes.append("Git remote 'origin' is not configured.")

    dirty = bool(_run_git(target_path, "status", "--porcelain"))

    status = "aligned"
    if actual_commit != record.commit:
        status = "commit_mismatch"
        notes.append("Pinned commit does not match local HEAD.")
    elif dirty:
        status = "dirty"
        notes.append("Working tree is dirty relative to the pinned commit.")

    if actual_branch and record.branch and actual_branch != record.branch:
        notes.append("Pinned branch does not match the current local branch.")
        if status == "aligned":
            status = "branch_mismatch"

    if actual_remote and record.remote and actual_remote != record.remote:
        notes.append("Pinned remote does not match local origin.")
        if status == "aligned":
            status = "remote_mismatch"

    return CompanionRevisionCheck(
        companion_id=record.id,
        expected_path=record.path,
        resolved_path=str(target_path),
        pinned_remote=record.remote,
        pinned_branch=record.branch,
        pinned_commit=record.commit,
        sync_role=record.sync_role,
        pin_status=record.status,
        exists=True,
        is_git_repo=True,
        actual_remote=actual_remote,
        actual_branch=actual_branch,
        actual_commit=actual_commit,
        dirty=dirty,
        status=status,
        notes=notes,
    )


def check_companion_revisions(base_dir: Path | None = None) -> List[CompanionRevisionCheck]:
    root = Path(base_dir).resolve() if base_dir else repo_root()
    records = load_companion_revisions(root)
    return [inspect_companion_revision(record, base_dir=root) for record in records]


def build_companion_revision_report(base_dir: Path | None = None) -> Dict[str, Any]:
    checks = check_companion_revisions(base_dir)
    status = "aligned" if checks and all(check.aligned for check in checks) else "drift"
    return {
        "schema_version": "jobpipe.companion-revision-check.v1",
        "status": status,
        "companions": [
            {
                "id": check.companion_id,
                "expected_path": check.expected_path,
                "resolved_path": check.resolved_path,
                "pinned_remote": check.pinned_remote,
                "pinned_branch": check.pinned_branch,
                "pinned_commit": check.pinned_commit,
                "sync_role": check.sync_role,
                "pin_status": check.pin_status,
                "exists": check.exists,
                "is_git_repo": check.is_git_repo,
                "actual_remote": check.actual_remote,
                "actual_branch": check.actual_branch,
                "actual_commit": check.actual_commit,
                "dirty": check.dirty,
                "status": check.status,
                "notes": check.notes,
            }
            for check in checks
        ],
    }
