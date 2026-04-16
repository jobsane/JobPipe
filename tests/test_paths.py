from __future__ import annotations

from pathlib import Path

from jobpipe.core.paths import (
    artifacts_root,
    data_root,
    db_root,
    documents_root,
    exports_root,
    primary_db_path,
    repo_root,
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
        "JOBPIPE_DOCUMENTS_DIR",
        "JOBPIPE_EXPORT_DIR",
    ):
        monkeypatch.delenv(key, raising=False)

    assert data_root() == tmp_path.resolve()
    assert db_root() == tmp_path / "db"
    assert primary_db_path() == tmp_path / "db" / "jobpipe.sqlite"
    assert artifacts_root() == tmp_path / "artifacts"
    assert documents_root() == tmp_path / "documents"
    assert exports_root() == tmp_path / "exports"


def test_explicit_overrides_win(monkeypatch, tmp_path):
    monkeypatch.setenv("JOBPIPE_DATA_DIR", str(tmp_path / "base"))
    monkeypatch.setenv("JOBPIPE_DB_DIR", str(tmp_path / "db-dir"))
    monkeypatch.setenv("JOBPIPE_DB_PATH", str(tmp_path / "db-file" / "custom.sqlite"))
    monkeypatch.setenv("JOBPIPE_ARTIFACT_DIR", str(tmp_path / "artifacts-dir"))
    monkeypatch.setenv("JOBPIPE_DOCUMENTS_DIR", str(tmp_path / "docs-dir"))
    monkeypatch.setenv("JOBPIPE_EXPORT_DIR", str(tmp_path / "exports-dir"))

    assert db_root() == (tmp_path / "db-dir").resolve()
    assert primary_db_path() == (tmp_path / "db-file" / "custom.sqlite").resolve()
    assert artifacts_root() == (tmp_path / "artifacts-dir").resolve()
    assert documents_root() == (tmp_path / "docs-dir").resolve()
    assert exports_root() == (tmp_path / "exports-dir").resolve()
