from __future__ import annotations

import argparse
import os
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Iterable

from jobpipe.core.io import read_jsonl_lines, write_jsonl_lines
from jobpipe.core.io import load_env_file
from jobpipe.runtime.paths import (
    artifacts_root,
    exports_root,
    jobs_delta_path,
    jobs_state_path,
    primary_db_path,
    repo_root,
)


DEFAULT_CONFIG_PATH = repo_root() / "configs" / "pipeline.v1.yaml"
DEFAULT_ENV_PATH = repo_root() / ".env"

MODULE_COMMANDS = {
    "bootstrap-state-db": "jobpipe.cli.bootstrap_state_db",
    "build-authoring-context": "jobpipe.authoring.smoke_cli",
    "drain-queue": "jobpipe.cli.drain_queue",
    "export-dashboard": "jobpipe.cli.export_dashboard",
    "export-jobsync": "jobpipe.cli.export_jobsync",
    "export-reactive-resume-plan": "jobpipe.cli.export_reactive_resume_plan",
    "gap-analysis": "jobpipe.cli.gap_analysis_report",
    "inspect-db": "jobpipe.cli.inspect_primary_db",
    "import-reactive-resume": "jobpipe.cli.import_reactive_resume",
    "mark-status": "jobpipe.cli.mark_status",
    "pull-finn-ext": "jobpipe.cli.pull_finn_ext",
    "pull-finn-search": "jobpipe.cli.pull_finn_search",
    "pull-sheets": "jobpipe.cli.pull_sheets_csv",
    "pull-suggested": "jobpipe.cli.pull_suggested",
    "record-feedback": "jobpipe.cli.record_feedback",
    "record-jobsync-event": "jobpipe.cli.record_jobsync_event",
    "record-reactive-resume-document": "jobpipe.cli.record_reactive_resume_document",
    "reset-runtime": "jobpipe.cli.reset_runtime",
    "scan-gmail": "jobpipe.cli.scan_gmail",
    "sync-evaluations": "jobpipe.cli.sync_evaluations",
}


def _run_module(module: str, argv: Iterable[str], *, allow_failure: bool = False) -> int:
    cmd = [sys.executable, "-m", module, *argv]
    print("> " + " ".join(cmd), flush=True)
    result = subprocess.run(cmd, cwd=str(repo_root()))
    if result.returncode and not allow_failure:
        raise SystemExit(result.returncode)
    return result.returncode


def _optional_step(label: str, module: str, argv: list[str]) -> None:
    print(label)
    code = _run_module(module, argv, allow_failure=True)
    if code:
        print(f"[warn] {module} failed (exit {code}). Continuing.")
    print()


def _process_delta_queue(
    label: str,
    delta_path: Path,
    *,
    candidate_id: str,
    artifacts_dir: Path,
    config_path: str,
    profile_path: str,
    batch_size: int,
) -> int:
    lines = read_jsonl_lines(delta_path)
    if not lines:
        print(f"[info] {label}: no queued jobs to process.")
        return 0

    tmp_dir = repo_root() / ".jobpipe_tmp"
    tmp_dir.mkdir(exist_ok=True)

    processed = 0
    for index in range(0, len(lines), batch_size):
        batch = lines[index:index + batch_size]
        batch_file = tmp_dir / f"{label}_{(index // batch_size) + 1:04d}.jsonl"
        write_jsonl_lines(batch_file, batch)
        argv = [
            "--jobs", str(batch_file),
            "--candidate-id", candidate_id,
            "--out", str(artifacts_dir),
            "--max", str(len(batch)),
            "--config", config_path,
            "--overwrite",
        ]
        if profile_path:
            argv += ["--profile", profile_path]
        _run_module("jobpipe.cli.run_feed", argv)
        processed += len(batch)
        try:
            batch_file.unlink()
        except OSError:
            pass

    try:
        delta_path.unlink()
    except OSError:
        pass

    print(f"[info] {label}: processed {processed} queued job(s).")
    print()
    return processed


def _default_candidate_id() -> str:
    return (os.environ.get("JOBPIPE_CANDIDATE_ID") or "default").strip() or "default"


def _preload_env_from_argv(raw_argv: list[str]) -> None:
    env_path = DEFAULT_ENV_PATH
    if raw_argv and raw_argv[0] == "run":
        for index, token in enumerate(raw_argv[:-1]):
            if token == "--env-file":
                env_path = Path(raw_argv[index + 1])
                break
    load_env_file(env_path)


def _process_local_delta_for_dry_run(
    delta_path: Path,
    *,
    candidate_id: str,
    artifacts_dir: Path,
    config_path: str,
    profile_path: str,
    max_jobs: int,
) -> int:
    lines = read_jsonl_lines(delta_path)
    if not lines:
        print("[info] dry_run_queue: no queued jobs to process.")
        print()
        return 0

    batch = lines[:max(1, max_jobs)]
    tmp_dir = repo_root() / ".jobpipe_tmp"
    tmp_dir.mkdir(exist_ok=True)
    batch_file = tmp_dir / "dry_run_queue.jsonl"
    write_jsonl_lines(batch_file, batch)

    argv = [
        "--jobs", str(batch_file),
        "--candidate-id", candidate_id,
        "--out", str(artifacts_dir),
        "--max", str(len(batch)),
        "--config", config_path,
        "--overwrite",
    ]
    if profile_path:
        argv += ["--profile", profile_path]

    try:
        _run_module("jobpipe.cli.run_feed", argv)
    finally:
        try:
            batch_file.unlink()
        except OSError:
            pass

    print(f"[info] dry_run_queue: processed {len(batch)} queued job(s) from local delta only.")
    print()
    return len(batch)


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="jobpipe",
        description="Canonical JobPipe CLI. Use this as the cross-platform interface; go.ps1 is a Windows convenience wrapper.",
    )
    sub = ap.add_subparsers(dest="command", required=True)

    run = sub.add_parser(
        "run",
        help="Run the normal JobPipe workflow: drain queue, sync evaluations, and export dashboard.",
    )
    run.add_argument("--env-file", default=str(DEFAULT_ENV_PATH), help=f"Path to .env file (default: {DEFAULT_ENV_PATH})")
    default_candidate_id = _default_candidate_id()
    run.add_argument("--candidate-id", default="", help=f"Candidate ID override (default: {default_candidate_id})")
    run.add_argument("--profile", default="", help="Optional profile_pack.md override")
    run.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help=f"Pipeline YAML path (default: {DEFAULT_CONFIG_PATH})")
    run.add_argument("--artifacts", "--out", dest="artifacts_dir", default=str(artifacts_root()), help=f"Artifacts root override (default: {artifacts_root()})")
    run.add_argument("--exports", "--reports", dest="exports_dir", default=str(exports_root()), help=f"Exports root override (default: {exports_root()})")
    run.add_argument("--state", default=str(jobs_state_path()), help=f"Jobs state path override (default: {jobs_state_path()})")
    run.add_argument("--db", default=str(primary_db_path()), help=f"Primary DB path override (default: {primary_db_path()})")
    run.add_argument("--max-jobs", type=int, default=100, help="Max jobs per run (default: 100; dry-run uses 2)")
    run.add_argument(
        "--dry-run",
        action="store_true",
        help="Use the bounded local smoke path: process at most two already-queued jobs, skip live sheet intake, and skip browser open by default",
    )
    run.add_argument("--no-open", action="store_true", help="Do not open the exported dashboard in a browser")
    run.add_argument("--with-suggestions", action="store_true", help="Run Gmail status/suggestion intake and FINN search before the main workflow")

    for name, module in MODULE_COMMANDS.items():
        proxy = sub.add_parser(name, add_help=False, help=f"Proxy to python -m {module}")
        proxy.add_argument("args", nargs=argparse.REMAINDER, help="Arguments passed through to the underlying module")

    return ap


def _run_main_flow(args: argparse.Namespace) -> None:
    env_file = Path(args.env_file)
    if env_file.exists():
        load_env_file(env_file)

    default_candidate_id = _default_candidate_id()
    candidate_id = (args.candidate_id or os.environ.get("JOBPIPE_CANDIDATE_ID") or default_candidate_id).strip() or default_candidate_id
    max_jobs = 2 if args.dry_run else max(1, int(args.max_jobs))
    artifacts_dir = Path(args.artifacts_dir)
    reports_dir = Path(args.exports_dir)
    state_path = Path(args.state)
    delta_path = jobs_delta_path()
    db_path = Path(args.db)
    dashboard_path = reports_dir / "dashboard.html"

    artifacts_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    print()
    print("=== JobPipe ===")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'FULL RUN'}")
    print(f"Candidate: {candidate_id}")
    print(f"Artifacts: {artifacts_dir}")
    print(f"Exports: {reports_dir}")
    print(f"Primary DB: {db_path}")
    if args.with_suggestions:
        print("Suggestions: ON")
    print()

    if args.with_suggestions:
        _optional_step(
            "[0a/5] scan-gmail (status) ...",
            "jobpipe.cli.scan_gmail",
            ["--days", "90", "--candidate-id", candidate_id, "--db", str(db_path)],
        )
        _optional_step(
            "[0b/5] scan-gmail --scan-suggestions ...",
            "jobpipe.cli.scan_gmail",
            ["--scan-suggestions", "--days", "30", "--candidate-id", candidate_id, "--db", str(db_path)],
        )
        tmp_dir = repo_root() / ".jobpipe_tmp"
        tmp_dir.mkdir(exist_ok=True)
        suggested_delta = tmp_dir / "suggested_jobs.jsonl"
        finn_search_delta = tmp_dir / "finn_search_jobs.jsonl"

        for temp_delta in (suggested_delta, finn_search_delta):
            try:
                temp_delta.unlink()
            except OSError:
                pass

        print("[0c/5] pull-suggested ...")
        code = _run_module(
            "jobpipe.cli.pull_suggested",
            ["--max", "20", "--candidate-id", candidate_id, "--db", str(db_path), "--out", str(suggested_delta)],
            allow_failure=True,
        )
        if code:
            print(f"[warn] jobpipe.cli.pull_suggested failed (exit {code}). Continuing.")
        _process_delta_queue(
            "suggested_intake",
            suggested_delta,
            candidate_id=candidate_id,
            artifacts_dir=artifacts_dir,
            config_path=args.config,
            profile_path=args.profile,
            batch_size=max_jobs,
        )

        print("[0d/5] pull-finn-search ...")
        code = _run_module(
            "jobpipe.cli.pull_finn_search",
            ["--config", args.config, "--max", "40", "--candidate-id", candidate_id, "--db", str(db_path), "--out", str(finn_search_delta)],
            allow_failure=True,
        )
        if code:
            print(f"[warn] jobpipe.cli.pull_finn_search failed (exit {code}). Continuing.")
        _process_delta_queue(
            "finn_search_intake",
            finn_search_delta,
            candidate_id=candidate_id,
            artifacts_dir=artifacts_dir,
            config_path=args.config,
            profile_path=args.profile,
            batch_size=max_jobs,
        )

    if args.dry_run:
        print("[1/3] local dry-run queue ...")
        _process_local_delta_for_dry_run(
            delta_path,
            candidate_id=candidate_id,
            artifacts_dir=artifacts_dir,
            config_path=args.config,
            profile_path=args.profile,
            max_jobs=max_jobs,
        )
    else:
        print("[1/3] drain-queue ...")
        drain_argv = [
            "--env-file", str(env_file),
            "--candidate-id", candidate_id,
            "--config", args.config,
            "--out", str(artifacts_dir),
            "--reports", str(reports_dir),
            "--state", str(state_path),
            "--batch-size", str(max_jobs),
            "--overwrite",
            "--db", str(db_path),
        ]
        if args.profile:
            drain_argv += ["--profile", args.profile]
        _run_module("jobpipe.cli.drain_queue", drain_argv)

    print()
    print("[2/3] sync-evaluations ...")
    _run_module(
        "jobpipe.cli.sync_evaluations",
        [
            "--out", str(artifacts_dir),
            "--reports", str(reports_dir),
            "--csv", str(reports_dir / "evaluations_latest.csv"),
            "--db", str(db_path),
            "--candidate-id", candidate_id,
        ],
    )

    print()
    print("[3/3] export-dashboard ...")
    _run_module(
        "jobpipe.cli.export_dashboard",
        [
            "--out-runs", str(artifacts_dir),
            "--out", str(dashboard_path),
            "--db", str(db_path),
            "--candidate-id", candidate_id,
        ],
    )

    print()
    print("=== Done ===")
    if not args.no_open and not args.dry_run and dashboard_path.exists():
        webbrowser.open(dashboard_path.resolve().as_uri())


def main(argv: list[str] | None = None) -> None:
    raw_argv = list(argv if argv is not None else sys.argv[1:])
    if raw_argv and raw_argv[0] in MODULE_COMMANDS:
        module = MODULE_COMMANDS[raw_argv[0]]
        forwarded = raw_argv[1:]
        if forwarded and forwarded[0] == "--":
            forwarded = forwarded[1:]
        raise SystemExit(_run_module(module, forwarded))

    _preload_env_from_argv(raw_argv)
    ap = _build_parser()
    args = ap.parse_args(raw_argv)

    if args.command == "run":
        _run_main_flow(args)
        return

    module = MODULE_COMMANDS[args.command]
    forwarded = list(args.args)
    if forwarded and forwarded[0] == "--":
        forwarded = forwarded[1:]
    raise SystemExit(_run_module(module, forwarded))


if __name__ == "__main__":
    main()
