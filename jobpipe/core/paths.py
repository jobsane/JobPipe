from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Tuple

JOBPIPE_DATA_ROOT_ENV = "JOBPIPE_DATA_ROOT"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_data_root() -> Path:
    override = os.environ.get(JOBPIPE_DATA_ROOT_ENV, "").strip()
    if override:
        return Path(override).expanduser()

    home = Path.home()
    if os.name == "nt":
        return home / "JobpipeData"
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "JobPipe"

    xdg_data_home = os.environ.get("XDG_DATA_HOME", "").strip()
    if xdg_data_home:
        return Path(xdg_data_home).expanduser() / "jobpipe"
    return home / ".local" / "share" / "jobpipe"


@dataclass(frozen=True)
class JobPipePaths:
    repo_root: Path
    data_root: Path

    @property
    def repo_reports_dir(self) -> Path:
        return self.repo_root / "reports"

    @property
    def repo_configs_dir(self) -> Path:
        return self.repo_root / "configs"

    @property
    def reports_dir(self) -> Path:
        return self.data_root / "reports"

    @property
    def exports_dir(self) -> Path:
        return self.data_root / "exports"

    @property
    def cache_dir(self) -> Path:
        return self.data_root / "cache"

    @property
    def tmp_dir(self) -> Path:
        return self.data_root / ".jobpipe_tmp"

    @property
    def out_runs_dir(self) -> Path:
        return self.data_root / "out_runs"

    @property
    def env_file(self) -> Path:
        return self.data_root / ".env"

    @property
    def jobs_state_path(self) -> Path:
        return self.data_root / "jobs_state.json"

    @property
    def jobs_delta_path(self) -> Path:
        return self.data_root / "jobs_delta.jsonl"

    @property
    def jobs_expired_path(self) -> Path:
        return self.data_root / "jobs_expired.jsonl"

    @property
    def profile_pack_path(self) -> Path:
        return self.data_root / "profile_pack.md"

    @property
    def resume_json_path(self) -> Path:
        return self.reports_dir / "resume.json"

    @property
    def resume_fixed_json_path(self) -> Path:
        return self.reports_dir / "resume_fixed.json"

    @property
    def application_state_path(self) -> Path:
        return self.reports_dir / "application_state.json"

    @property
    def ledger_sqlite_path(self) -> Path:
        return self.reports_dir / "ledger.sqlite"

    @property
    def ledger_csv_path(self) -> Path:
        return self.reports_dir / "ledger_latest.csv"

    @property
    def gmail_credentials_path(self) -> Path:
        return self.reports_dir / "gmail_credentials.json"

    @property
    def gmail_token_path(self) -> Path:
        return self.reports_dir / "gmail_token.json"

    @property
    def suggested_jobs_path(self) -> Path:
        return self.reports_dir / "suggested_jobs.jsonl"

    @property
    def profile_builder_state_path(self) -> Path:
        return self.reports_dir / "profile_builder_state.json"

    @property
    def profile_embedding_path(self) -> Path:
        return self.cache_dir / "profile_embedding.npy"

    @property
    def dashboard_export_path(self) -> Path:
        return self.exports_dir / "dashboard.html"

    @property
    def dashboard_template_path(self) -> Path:
        return self.repo_reports_dir / "dashboard_template.html"

    @property
    def apply_template_path(self) -> Path:
        return self.repo_reports_dir / "apply_template.html"

    @property
    def default_config_path(self) -> Path:
        return self.repo_configs_dir / "pipeline.v1.yaml"

    def ensure_data_dirs(self) -> None:
        for path in (self.data_root, self.reports_dir, self.exports_dir, self.cache_dir, self.tmp_dir):
            path.mkdir(parents=True, exist_ok=True)


def get_jobpipe_paths(data_root: str | Path | None = None, repo: str | Path | None = None) -> JobPipePaths:
    return JobPipePaths(
        repo_root=Path(repo).resolve() if repo else repo_root(),
        data_root=Path(data_root).expanduser().resolve() if data_root else default_data_root().resolve(),
    )


def _legacy_copy_plan(paths: JobPipePaths, include_artifacts: bool) -> Iterable[Tuple[Path, Path, bool]]:
    entries: List[Tuple[Path, Path, bool]] = [
        (paths.repo_root / ".env", paths.env_file, False),
        (paths.repo_root / "profile_pack.md", paths.profile_pack_path, False),
        (paths.repo_reports_dir / "resume.json", paths.resume_json_path, False),
        (paths.repo_reports_dir / "resume_fixed.json", paths.resume_fixed_json_path, False),
        (paths.repo_reports_dir / "application_state.json", paths.application_state_path, False),
        (paths.repo_reports_dir / "ledger.sqlite", paths.ledger_sqlite_path, False),
        (paths.repo_reports_dir / "ledger.sqlite-shm", paths.ledger_sqlite_path.with_name("ledger.sqlite-shm"), False),
        (paths.repo_reports_dir / "ledger.sqlite-wal", paths.ledger_sqlite_path.with_name("ledger.sqlite-wal"), False),
        (paths.repo_reports_dir / "ledger_latest.csv", paths.ledger_csv_path, False),
        (paths.repo_reports_dir / "gmail_credentials.json", paths.gmail_credentials_path, False),
        (paths.repo_reports_dir / "gmail_token.json", paths.gmail_token_path, False),
        (paths.repo_reports_dir / "suggested_jobs.jsonl", paths.suggested_jobs_path, False),
        (paths.repo_reports_dir / "profile_builder_state.json", paths.profile_builder_state_path, False),
        (paths.repo_reports_dir / "profile_embedding.npy", paths.profile_embedding_path, False),
        (paths.repo_root / "jobs_state.json", paths.jobs_state_path, False),
        (paths.repo_root / "jobs_delta.jsonl", paths.jobs_delta_path, False),
        (paths.repo_root / "jobs_expired.jsonl", paths.jobs_expired_path, False),
        (paths.repo_reports_dir / "dashboard.html", paths.dashboard_export_path, False),
    ]
    if include_artifacts:
        entries.append((paths.repo_root / "out_runs", paths.out_runs_dir, True))
    return entries


def bootstrap_private_data(paths: JobPipePaths, *, include_artifacts: bool = True) -> List[Path]:
    paths.ensure_data_dirs()
    copied: List[Path] = []

    for src, dst, is_dir in _legacy_copy_plan(paths, include_artifacts):
        if dst.exists() or not src.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if is_dir:
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        copied.append(dst)

    return copied
