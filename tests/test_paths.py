from __future__ import annotations

from pathlib import Path

from jobpipe.core.paths import (
    application_state_path as compat_application_state_path,
    artifacts_root,
    cache_root as compat_cache_root,
    data_root,
    db_root,
    documents_root,
    exports_root,
    gmail_credentials_path as compat_gmail_credentials_path,
    gmail_token_path as compat_gmail_token_path,
    primary_db_path,
    profile_embedding_cache_path as compat_profile_embedding_cache_path,
    repo_root as compat_repo_root,
    suggested_jobs_path as compat_suggested_jobs_path,
    resume_json_path as compat_resume_json_path,
    repo_root,
    secrets_root as compat_secrets_root,
)
from jobpipe.runtime.data_sources import resolve_profile_paths, resolve_runtime_profile
from jobpipe.runtime.paths import (
    application_state_path,
    cache_root,
    gmail_credentials_path,
    gmail_token_path,
    profile_pack_path,
    profile_embedding_cache_path,
    repo_root as runtime_repo_root,
    resume_json_path,
    secrets_root,
    suggested_jobs_path,
)


def test_data_root_defaults_to_none(monkeypatch):
    monkeypatch.delenv("JOBPIPE_DATA_DIR", raising=False)
    assert data_root() is None


def test_roots_default_to_repo_layout(monkeypatch):
    for key in (
        "JOBPIPE_DATA_DIR",
        "JOBPIPE_DB_DIR",
        "JOBPIPE_DB_PATH",
        "JOBPIPE_ARTIFACT_DIR",
        "JOBPIPE_DOCUMENTS_DIR",
        "JOBPIPE_EXPORT_DIR",
    ):
        monkeypatch.delenv(key, raising=False)

    root = repo_root()

    assert db_root() == root / "reports"
    assert primary_db_path() == root / "reports" / "jobpipe.sqlite"
    assert artifacts_root() == root / "out_runs"
    assert documents_root() == root / "reports" / "documents"
    assert exports_root() == root / "reports"


def test_roots_follow_jobpipe_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("JOBPIPE_DATA_DIR", str(tmp_path))
    for key in (
        "JOBPIPE_DB_DIR",
        "JOBPIPE_DB_PATH",
        "JOBPIPE_ARTIFACT_DIR",
        "JOBPIPE_CACHE_DIR",
        "JOBPIPE_DOCUMENTS_DIR",
        "JOBPIPE_EXPORT_DIR",
        "JOBPIPE_SECRETS_DIR",
    ):
        monkeypatch.delenv(key, raising=False)

    assert data_root() == tmp_path.resolve()
    assert db_root() == tmp_path / "db"
    assert primary_db_path() == tmp_path / "db" / "jobpipe.sqlite"
    assert artifacts_root() == tmp_path / "artifacts"
    assert cache_root() == tmp_path / "cache"
    assert documents_root() == tmp_path / "documents"
    assert exports_root() == tmp_path / "exports"
    assert secrets_root() == tmp_path / "secrets"
    assert application_state_path() == tmp_path / "db" / "application_state.json"
    assert suggested_jobs_path() == tmp_path / "db" / "suggested_jobs.jsonl"
    assert profile_embedding_cache_path() == tmp_path / "cache" / "profile_embedding.npy"
    assert gmail_token_path() == tmp_path / "secrets" / "gmail_token.json"
    assert gmail_credentials_path() == tmp_path / "secrets" / "gmail_credentials.json"
    assert resume_json_path() == tmp_path / "documents" / "resume.json"


def test_data_root_prefers_existing_flat_legacy_candidate_and_secret_files(monkeypatch, tmp_path):
    monkeypatch.setenv("JOBPIPE_DATA_DIR", str(tmp_path))
    for key in (
        "JOBPIPE_PROFILE_PATH",
        "JOBPIPE_RESUME_JSON",
        "JOBPIPE_GMAIL_TOKEN_PATH",
        "JOBPIPE_GMAIL_CREDENTIALS_PATH",
    ):
        monkeypatch.delenv(key, raising=False)

    legacy_profile = tmp_path / "profile_pack.md"
    legacy_resume = tmp_path / "resume.json"
    legacy_token = tmp_path / "gmail_token.json"
    legacy_credentials = tmp_path / "gmail_credentials.json"

    legacy_profile.write_text("# PROFILE\nlegacy", encoding="utf-8")
    legacy_resume.write_text("{}", encoding="utf-8")
    legacy_token.write_text("{}", encoding="utf-8")
    legacy_credentials.write_text("{}", encoding="utf-8")

    assert profile_pack_path() == legacy_profile
    assert resume_json_path() == legacy_resume
    assert gmail_token_path() == legacy_token
    assert gmail_credentials_path() == legacy_credentials


def test_explicit_overrides_win(monkeypatch, tmp_path):
    monkeypatch.setenv("JOBPIPE_DATA_DIR", str(tmp_path / "base"))
    monkeypatch.setenv("JOBPIPE_DB_DIR", str(tmp_path / "db-dir"))
    monkeypatch.setenv("JOBPIPE_DB_PATH", str(tmp_path / "db-file" / "custom.sqlite"))
    monkeypatch.setenv("JOBPIPE_ARTIFACT_DIR", str(tmp_path / "artifacts-dir"))
    monkeypatch.setenv("JOBPIPE_CACHE_DIR", str(tmp_path / "cache-dir"))
    monkeypatch.setenv("JOBPIPE_DOCUMENTS_DIR", str(tmp_path / "docs-dir"))
    monkeypatch.setenv("JOBPIPE_EXPORT_DIR", str(tmp_path / "exports-dir"))
    monkeypatch.setenv("JOBPIPE_SECRETS_DIR", str(tmp_path / "secrets-dir"))

    assert db_root() == (tmp_path / "db-dir").resolve()
    assert primary_db_path() == (tmp_path / "db-file" / "custom.sqlite").resolve()
    assert artifacts_root() == (tmp_path / "artifacts-dir").resolve()
    assert cache_root() == (tmp_path / "cache-dir").resolve()
    assert documents_root() == (tmp_path / "docs-dir").resolve()
    assert exports_root() == (tmp_path / "exports-dir").resolve()
    assert secrets_root() == (tmp_path / "secrets-dir").resolve()


def test_runtime_paths_is_canonical_and_core_paths_stays_compatible(monkeypatch, tmp_path):
    monkeypatch.setenv("JOBPIPE_DATA_DIR", str(tmp_path))

    assert runtime_repo_root() == compat_repo_root()
    assert resume_json_path() == compat_resume_json_path()
    assert application_state_path() == compat_application_state_path()
    assert cache_root() == compat_cache_root()
    assert secrets_root() == compat_secrets_root()
    assert suggested_jobs_path() == compat_suggested_jobs_path()
    assert profile_embedding_cache_path() == compat_profile_embedding_cache_path()
    assert gmail_token_path() == compat_gmail_token_path()
    assert gmail_credentials_path() == compat_gmail_credentials_path()


def test_runtime_profile_repo_smoke_ignores_external_data_root(monkeypatch, tmp_path):
    monkeypatch.setenv("JOBPIPE_DATA_DIR", str(tmp_path / "external"))

    profile = resolve_runtime_profile("repo_smoke")

    assert profile.name == "repo_smoke"
    assert profile.data_root is None
    assert profile.primary_db_path == repo_root() / "reports" / "jobpipe.sqlite"
    assert profile.artifacts_root == repo_root() / "out_runs"


def test_runtime_profile_live_local_follows_external_data_root(monkeypatch, tmp_path):
    monkeypatch.setenv("JOBPIPE_DATA_DIR", str(tmp_path))

    profile = resolve_runtime_profile("live_local")

    assert profile.name == "live_local"
    assert profile.data_root == tmp_path.resolve()
    assert profile.primary_db_path == tmp_path / "db" / "jobpipe.sqlite"
    assert profile.profile_pack_path == tmp_path / "profile" / "profile_pack.md"
    assert profile.resume_json_path == tmp_path / "profile" / "resume.json"


def test_runtime_profile_path_overrides_win(monkeypatch, tmp_path):
    monkeypatch.setenv("JOBPIPE_DATA_DIR", str(tmp_path / "data"))
    custom_db = tmp_path / "custom" / "jobpipe.sqlite"
    custom_profile = tmp_path / "profile_pack.md"

    profile = resolve_profile_paths(
        "live_local",
        db_override=str(custom_db),
        profile_override=str(custom_profile),
    )

    assert profile.primary_db_path == custom_db.resolve()
    assert profile.db_root == custom_db.resolve().parent
    assert profile.profile_pack_path == custom_profile.resolve()
