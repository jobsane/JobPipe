from __future__ import annotations

from pathlib import Path

from jobpipe.core.paths import (
    JOBPIPE_DATA_ROOT_ENV,
    bootstrap_private_data,
    default_data_root,
    get_jobpipe_paths,
)


def test_default_data_root_respects_env_override(monkeypatch, tmp_path: Path) -> None:
    override = tmp_path / "jobpipe-home"
    monkeypatch.setenv(JOBPIPE_DATA_ROOT_ENV, str(override))

    assert default_data_root() == override


def test_bootstrap_private_data_copies_legacy_repo_state_into_data_root(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    data_root = tmp_path / "data"
    reports_dir = repo_root / "reports"
    out_runs_dir = repo_root / "out_runs" / "run_a" / "nav_001"
    reports_dir.mkdir(parents=True)
    out_runs_dir.mkdir(parents=True)

    (repo_root / ".env").write_text("OPENAI_API_KEY=test-key\n", encoding="utf-8")
    (repo_root / "profile_pack.md").write_text("# PROFILE\n", encoding="utf-8")
    (repo_root / "jobs_state.json").write_text('{"rows":{}}', encoding="utf-8")
    (repo_root / "jobs_delta.jsonl").write_text('{"job_id":"nav_001"}\n', encoding="utf-8")
    (reports_dir / "resume.json").write_text('{"basics":{"name":"Lars"}}', encoding="utf-8")
    (reports_dir / "application_state.json").write_text('{"applications":{}}', encoding="utf-8")
    (reports_dir / "dashboard.html").write_text("<html></html>", encoding="utf-8")
    (out_runs_dir / "00_input.json").write_text('{"job_id":"nav_001"}', encoding="utf-8")

    paths = get_jobpipe_paths(data_root=data_root, repo=repo_root)
    copied = bootstrap_private_data(paths, include_artifacts=True)

    copied_set = {path.resolve() for path in copied}
    assert paths.env_file.resolve() in copied_set
    assert paths.profile_pack_path.read_text(encoding="utf-8") == "# PROFILE\n"
    assert paths.resume_json_path.exists()
    assert paths.application_state_path.exists()
    assert paths.dashboard_export_path.exists()
    assert (paths.out_runs_dir / "run_a" / "nav_001" / "00_input.json").exists()


def test_bootstrap_private_data_never_overwrites_existing_user_files(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    data_root = tmp_path / "data"
    reports_dir = repo_root / "reports"
    reports_dir.mkdir(parents=True)

    (repo_root / ".env").write_text("OPENAI_API_KEY=repo-value\n", encoding="utf-8")
    paths = get_jobpipe_paths(data_root=data_root, repo=repo_root)
    paths.ensure_data_dirs()
    paths.env_file.write_text("OPENAI_API_KEY=user-value\n", encoding="utf-8")

    copied = bootstrap_private_data(paths, include_artifacts=False)

    assert paths.env_file.read_text(encoding="utf-8") == "OPENAI_API_KEY=user-value\n"
    assert paths.env_file not in copied
