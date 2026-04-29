from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .paths import repo_root


def _expand_path(raw: str | os.PathLike[str]) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(str(raw)))).resolve()


def _clean(value: str | None) -> str:
    return (value or "").strip()


@dataclass(frozen=True)
class RuntimeProfile:
    name: str
    repo_root: Path
    data_root: Path | None
    db_root: Path
    primary_db_path: Path
    artifacts_root: Path
    exports_root: Path
    documents_root: Path
    cache_root: Path
    secrets_root: Path
    profile_dir: Path
    profile_pack_path: Path
    resume_json_path: Path
    application_state_path: Path
    suggested_jobs_path: Path
    jobs_state_path: Path
    jobs_delta_path: Path
    jobs_expired_path: Path


def _resolve_optional(raw: str) -> Path | None:
    value = _clean(raw)
    if not value:
        return None
    return _expand_path(value)


def _repo_profile(root: Path) -> RuntimeProfile:
    reports_root = root / "reports"
    profile_root = root / "profile"
    return RuntimeProfile(
        name="repo_smoke",
        repo_root=root,
        data_root=None,
        db_root=reports_root,
        primary_db_path=reports_root / "jobpipe.sqlite",
        artifacts_root=root / "out_runs",
        exports_root=reports_root,
        documents_root=reports_root / "documents",
        cache_root=reports_root,
        secrets_root=reports_root,
        profile_dir=profile_root,
        profile_pack_path=root / "profile_pack.md",
        resume_json_path=reports_root / "resume.json",
        application_state_path=reports_root / "application_state.json",
        suggested_jobs_path=reports_root / "suggested_jobs.jsonl",
        jobs_state_path=root / "jobs_state.json",
        jobs_delta_path=root / "jobs_delta.jsonl",
        jobs_expired_path=root / "jobs_expired.jsonl",
    )


def _data_root_profile(root: Path, *, name: str) -> RuntimeProfile:
    profile_root = root / "profile"
    profile_pack = profile_root / "profile_pack.md"
    if not profile_pack.exists():
        for candidate in (root / "documents" / "profile_pack.md", root / "profile_pack.md"):
            if candidate.exists():
                profile_pack = candidate
                break

    resume_json = profile_root / "resume.json"
    if not resume_json.exists():
        for candidate in (root / "documents" / "resume.json", root / "resume.json"):
            if candidate.exists():
                resume_json = candidate
                break

    return RuntimeProfile(
        name=name,
        repo_root=repo_root(),
        data_root=root,
        db_root=root / "db",
        primary_db_path=root / "db" / "jobpipe.sqlite",
        artifacts_root=root / "artifacts",
        exports_root=root / "exports",
        documents_root=root / "documents",
        cache_root=root / "cache",
        secrets_root=root / "secrets",
        profile_dir=profile_root,
        profile_pack_path=profile_pack,
        resume_json_path=resume_json,
        application_state_path=root / "db" / "application_state.json",
        suggested_jobs_path=root / "db" / "suggested_jobs.jsonl",
        jobs_state_path=root / "db" / "jobs_state.json",
        jobs_delta_path=root / "db" / "jobs_delta.jsonl",
        jobs_expired_path=root / "db" / "jobs_expired.jsonl",
    )


def resolve_runtime_profile(
    profile_name: str | None = None,
    *,
    data_root_override: str = "",
) -> RuntimeProfile:
    name = _clean(profile_name).lower() or "default"
    root = repo_root()

    if name == "repo_smoke":
        return _repo_profile(root)

    if name in {"default", "live_local"}:
        data_root_raw = _clean(data_root_override) or _clean(os.environ.get("JOBPIPE_DATA_DIR"))
        if data_root_raw:
            return _data_root_profile(_expand_path(data_root_raw), name="live_local")
        if name == "live_local":
            raise SystemExit("runtime profile 'live_local' requires JOBPIPE_DATA_DIR or --data-root")
        return _repo_profile(root)

    raise SystemExit(f"unknown runtime profile: {profile_name}")


def runtime_profile_choices() -> tuple[str, ...]:
    return ("default", "live_local", "repo_smoke")


def resolve_profile_path(override: str, profile_path: Path) -> Path:
    return _resolve_optional(override) or profile_path


def resolve_profile_paths(
    profile_name: str | None = None,
    *,
    data_root_override: str = "",
    db_override: str = "",
    artifacts_override: str = "",
    exports_override: str = "",
    documents_override: str = "",
    profile_override: str = "",
    resume_override: str = "",
    app_state_override: str = "",
    jobs_state_override: str = "",
    jobs_delta_override: str = "",
) -> RuntimeProfile:
    profile = resolve_runtime_profile(profile_name, data_root_override=data_root_override)
    resolved_db_path = resolve_profile_path(db_override, profile.primary_db_path)
    return RuntimeProfile(
        name=profile.name,
        repo_root=profile.repo_root,
        data_root=profile.data_root,
        db_root=resolved_db_path.parent if db_override else profile.db_root,
        primary_db_path=resolved_db_path,
        artifacts_root=resolve_profile_path(artifacts_override, profile.artifacts_root),
        exports_root=resolve_profile_path(exports_override, profile.exports_root),
        documents_root=resolve_profile_path(documents_override, profile.documents_root),
        cache_root=profile.cache_root,
        secrets_root=profile.secrets_root,
        profile_dir=profile.profile_dir,
        profile_pack_path=resolve_profile_path(profile_override, profile.profile_pack_path),
        resume_json_path=resolve_profile_path(resume_override, profile.resume_json_path),
        application_state_path=resolve_profile_path(app_state_override, profile.application_state_path),
        suggested_jobs_path=profile.suggested_jobs_path,
        jobs_state_path=resolve_profile_path(jobs_state_override, profile.jobs_state_path),
        jobs_delta_path=resolve_profile_path(jobs_delta_override, profile.jobs_delta_path),
        jobs_expired_path=profile.jobs_expired_path,
    )


__all__ = [
    "RuntimeProfile",
    "resolve_profile_path",
    "resolve_profile_paths",
    "resolve_runtime_profile",
    "runtime_profile_choices",
]
