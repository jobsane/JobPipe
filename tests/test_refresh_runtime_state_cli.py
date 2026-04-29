from __future__ import annotations

from jobpipe.cli import refresh_runtime_state


def test_refresh_runtime_state_resets_and_bootstraps(tmp_path, monkeypatch) -> None:
    data_root = tmp_path / "JobpipeData"
    data_root.mkdir()
    (data_root / "profile").mkdir()

    calls: list[tuple[str, dict]] = []

    def _fake_reset_runtime_state(**kwargs):
        calls.append(("reset", kwargs))
        return {"archive_dir": str(tmp_path / "_archives" / "baseline_a")}

    def _fake_bootstrap_primary_db(**kwargs):
        calls.append(("bootstrap", kwargs))
        return {
            "db_path": kwargs["db_path"],
            "candidate_id": kwargs["candidate_id"],
            "profile_path": kwargs["profile_path"],
            "resume_path": kwargs["resume_path"],
            "app_state_path": kwargs["app_state_path"],
            "events_stored": 3,
            "jobs_tracked": 2,
        }

    monkeypatch.setenv("JOBPIPE_DATA_DIR", str(data_root))
    monkeypatch.setattr(refresh_runtime_state, "reset_runtime_state", _fake_reset_runtime_state)
    monkeypatch.setattr(refresh_runtime_state, "bootstrap_primary_db", _fake_bootstrap_primary_db)

    refresh_runtime_state.main(["--tag", "baseline_a", "--candidate-id", "candidate-a"])

    assert [name for name, _ in calls] == ["reset", "bootstrap"]
    reset_kwargs = calls[0][1]
    bootstrap_kwargs = calls[1][1]

    assert reset_kwargs["data_root_path"] == data_root.resolve()
    assert reset_kwargs["tag"] == "baseline_a"
    assert bootstrap_kwargs["db_path"] == data_root / "db" / "jobpipe.sqlite"
    assert bootstrap_kwargs["profile_path"] == data_root / "profile" / "profile_pack.md"
    assert bootstrap_kwargs["resume_path"] == data_root / "profile" / "resume.json"
    assert bootstrap_kwargs["app_state_path"] == data_root / "db" / "application_state.json"
