"""bounded-intake — run the full intake pipeline on a local corpus file.

Bypasses the Sheets pull entirely. Runs run_feed on a local JSONL, then
syncs evaluations. Use this for operational smoke testing without touching
the live queue.

Usage:
    jobpipe bounded-intake --corpus tests/fixtures/smoke_corpus_input.jsonl
    jobpipe bounded-intake --corpus <path> --max 5 --no-sync --out out_runs/smoke/
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from jobpipe.core.io import load_env_file
from jobpipe.runtime.paths import artifacts_root, primary_db_path, repo_root
from jobpipe.core.candidate_data import default_candidate_id


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        description=(
            "Run the intake pipeline on a local corpus JSONL without pulling from Sheets. "
            "Faster and cheaper than drain-queue for operational smoke testing."
        )
    )
    ap.add_argument("--corpus", required=True, help="Path to raw jobs JSONL file.")
    ap.add_argument(
        "--out",
        default=str(repo_root() / "out_runs" / "bounded-intake"),
        help="Artifact output directory (default: out_runs/bounded-intake/).",
    )
    ap.add_argument("--max", type=int, default=0, help="Stop after N jobs (0 = all).")
    ap.add_argument(
        "--candidate-id",
        default="",
        help=f"Candidate ID (default: JOBPIPE_CANDIDATE_ID env or '{default_candidate_id()}').",
    )
    ap.add_argument(
        "--db",
        default=str(primary_db_path()),
        help=f"Primary jobpipe.sqlite path (default: {primary_db_path()}).",
    )
    ap.add_argument(
        "--no-sync",
        action="store_true",
        help="Skip sync-evaluations step after run-feed.",
    )
    ap.add_argument("--env-file", default=".env", help="Optional .env file (default: .env).")
    args = ap.parse_args(argv)

    load_env_file(Path(args.env_file))
    candidate_id = (
        args.candidate_id or os.environ.get("JOBPIPE_CANDIDATE_ID") or default_candidate_id()
    ).strip()

    corpus_path = Path(args.corpus)
    if not corpus_path.exists():
        print(f"[bounded-intake] ERROR: corpus file not found: {corpus_path}", file=sys.stderr)
        raise SystemExit(1)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = Path(args.db)
    py = sys.executable

    print(f"[bounded-intake] corpus={corpus_path}  max={args.max or 'all'}  out={out_dir}")

    feed_cmd = [
        py, "-m", "jobpipe.cli.run_feed",
        "--jobs", str(corpus_path),
        "--out", str(out_dir),
        "--candidate-id", candidate_id,
    ]
    if args.max:
        feed_cmd += ["--max", str(args.max)]

    print("> " + " ".join(feed_cmd))
    result = subprocess.run(feed_cmd)
    if result.returncode:
        print(f"[bounded-intake] run-feed exited {result.returncode}.", file=sys.stderr)
        raise SystemExit(result.returncode)

    if args.no_sync:
        print("[bounded-intake] --no-sync: skipping sync-evaluations.")
    else:
        sync_cmd = [
            py, "-m", "jobpipe.cli.sync_evaluations",
            "--out", str(out_dir),
            "--db", str(db_path),
            "--candidate-id", candidate_id,
        ]
        print("> " + " ".join(sync_cmd))
        subprocess.run(sync_cmd, check=True)

    print(f"[bounded-intake] Done. out={out_dir}")


if __name__ == "__main__":
    main()
