from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _expand_path(raw: str | os.PathLike[str]) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(str(raw)))).resolve()


def data_root() -> Path | None:
    raw = (os.environ.get("JOBPIPE_DATA_DIR") or "").strip()
    if not raw:
        return None
    return _expand_path(raw)


def profile_pack_path() -> Path:
    raw = (os.environ.get("JOBPIPE_PROFILE_PATH") or "").strip()
    if raw:
        return _expand_path(raw)
    root = data_root()
    if root is not None:
        return root / "profile_pack.md"
    return repo_root() / "profile_pack.md"


def resume_json_path() -> Path:
    raw = (os.environ.get("JOBPIPE_RESUME_JSON") or "").strip()
    if raw:
        return _expand_path(raw)
    root = data_root()
    if root is not None:
        return root / "resume.json"
    return repo_root() / "reports" / "resume.json"


def application_state_path() -> Path:
    raw = (os.environ.get("JOBPIPE_APP_STATE_PATH") or "").strip()
    if raw:
        return _expand_path(raw)
    root = data_root()
    if root is not None:
        return root / "application_state.json"
    return repo_root() / "reports" / "application_state.json"


def gmail_token_path() -> Path:
    raw = (os.environ.get("JOBPIPE_GMAIL_TOKEN_PATH") or "").strip()
    if raw:
        return _expand_path(raw)
    root = data_root()
    if root is not None:
        return root / "gmail_token.json"
    return repo_root() / "reports" / "gmail_token.json"


def gmail_credentials_path() -> Path:
    raw = (os.environ.get("JOBPIPE_GMAIL_CREDENTIALS_PATH") or "").strip()
    if raw:
        return _expand_path(raw)
    root = data_root()
    if root is not None:
        return root / "gmail_credentials.json"
    return repo_root() / "reports" / "gmail_credentials.json"


def suggested_jobs_path() -> Path:
    raw = (os.environ.get("JOBPIPE_SUGGESTED_PATH") or "").strip()
    if raw:
        return _expand_path(raw)
    root = data_root()
    if root is not None:
        return root / "suggested_jobs.jsonl"
    return repo_root() / "reports" / "suggested_jobs.jsonl"


def profile_embedding_cache_path() -> Path:
    raw = (os.environ.get("JOBPIPE_PROFILE_EMBEDDING_PATH") or "").strip()
    if raw:
        return _expand_path(raw)
    root = data_root()
    if root is not None:
        return root / "profile_embedding.npy"
    return repo_root() / "reports" / "profile_embedding.npy"
