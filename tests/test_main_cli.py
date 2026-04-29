from __future__ import annotations

import json
import pytest

from jobpipe.cli import main as cli_main


def test_run_dry_run_uses_local_delta_and_skips_drain_queue(tmp_path, monkeypatch) -> None:
    """Canonical bounded smoke path: local delta only, no drain_queue, max two jobs."""
    delta_path = tmp_path / "jobs_delta.jsonl"
    delta_path.write_text(
        "\n".join(
            [
                json.dumps({"job_id": "job-1", "title": "One"}),
                json.dumps({"job_id": "job-2", "title": "Two"}),
                json.dumps({"job_id": "job-3", "title": "Three"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    calls: list[tuple[str, list[str]]] = []

    def _fake_run_module(module: str, argv: list[str], *, allow_failure: bool = False) -> int:
        calls.append((module, list(argv)))
        return 0

    monkeypatch.setattr(cli_main, "_run_module", _fake_run_module)
    monkeypatch.setattr(cli_main, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(cli_main, "jobs_delta_path", lambda: delta_path)

    cli_main.main(
        [
            "run",
            "--dry-run",
            "--no-open",
            "--env-file",
            str(tmp_path / ".env"),
            "--artifacts",
            str(tmp_path / "artifacts"),
            "--exports",
            str(tmp_path / "exports"),
            "--state",
            str(tmp_path / "jobs_state.json"),
            "--db",
            str(tmp_path / "jobpipe.sqlite"),
        ]
    )

    modules = [module for module, _ in calls]
    assert "jobpipe.cli.drain_queue" not in modules
    assert modules == [
        "jobpipe.cli.run_feed",
        "jobpipe.cli.sync_evaluations",
        "jobpipe.cli.export_dashboard",
    ]

    run_feed_argv = calls[0][1]
    assert "--jobs" in run_feed_argv
    assert "--max" in run_feed_argv
    assert run_feed_argv[run_feed_argv.index("--max") + 1] == "2"


def test_run_non_dry_run_keeps_drain_queue_flow(tmp_path, monkeypatch) -> None:
    calls: list[tuple[str, list[str]]] = []

    def _fake_run_module(module: str, argv: list[str], *, allow_failure: bool = False) -> int:
        calls.append((module, list(argv)))
        return 0

    monkeypatch.setattr(cli_main, "_run_module", _fake_run_module)
    monkeypatch.setattr(cli_main, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(cli_main, "jobs_delta_path", lambda: tmp_path / "jobs_delta.jsonl")

    cli_main.main(
        [
            "run",
            "--no-open",
            "--env-file",
            str(tmp_path / ".env"),
            "--artifacts",
            str(tmp_path / "artifacts"),
            "--exports",
            str(tmp_path / "exports"),
            "--state",
            str(tmp_path / "jobs_state.json"),
            "--db",
            str(tmp_path / "jobpipe.sqlite"),
            "--max-jobs",
            "5",
        ]
    )

    modules = [module for module, _ in calls]
    assert modules == [
        "jobpipe.cli.drain_queue",
        "jobpipe.cli.sync_evaluations",
        "jobpipe.cli.export_dashboard",
    ]


def test_run_defaults_honor_env_file_data_root(tmp_path, monkeypatch) -> None:
    data_root = tmp_path / "JobpipeData"
    env_file = tmp_path / ".env"
    env_file.write_text(f"JOBPIPE_DATA_DIR={data_root}\n", encoding="utf-8")

    calls: list[tuple[str, list[str]]] = []

    def _fake_run_module(module: str, argv: list[str], *, allow_failure: bool = False) -> int:
        calls.append((module, list(argv)))
        return 0

    monkeypatch.delenv("JOBPIPE_DATA_DIR", raising=False)
    monkeypatch.setattr(cli_main, "_run_module", _fake_run_module)
    monkeypatch.setattr(cli_main, "repo_root", lambda: tmp_path)

    cli_main.main(["run", "--dry-run", "--no-open", "--env-file", str(env_file)])

    sync_argv = next(argv for module, argv in calls if module == "jobpipe.cli.sync_evaluations")
    export_argv = next(argv for module, argv in calls if module == "jobpipe.cli.export_dashboard")

    assert str(data_root / "artifacts") in sync_argv
    assert str(data_root / "exports") in sync_argv
    assert str(data_root / "db" / "jobpipe.sqlite") in sync_argv
    assert str(data_root / "exports" / "dashboard.html") in export_argv


def test_reset_runtime_proxies_module(monkeypatch) -> None:
    calls: list[tuple[str, list[str]]] = []

    def _fake_run_module(module: str, argv: list[str], *, allow_failure: bool = False) -> int:
        calls.append((module, list(argv)))
        return 0

    monkeypatch.setattr(cli_main, "_run_module", _fake_run_module)

    with pytest.raises(SystemExit) as exc:
        cli_main.main(["reset-runtime", "--", "--tag", "baseline_a"])

    assert exc.value.code == 0
    assert calls == [("jobpipe.cli.reset_runtime", ["--tag", "baseline_a"])]
