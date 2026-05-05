from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from jobpipe.core.io import load_env_file, read_jsonl_lines, write_jsonl_lines, stable_job_id
from jobpipe.runtime.paths import (
    exports_root,
    artifacts_root,
    jobs_delta_path,
    jobs_expired_path,
    jobs_state_path,
    primary_db_path,
)
from jobpipe.core.evaluation_state import load_processed_job_ids


def run(cmd: list[str]) -> None:
    print("> " + " ".join(cmd))
    subprocess.run(cmd, check=True)


def _job_id_from_json(obj: dict[str, Any]) -> str:
    return stable_job_id(obj)

def _evaluation_summary(db_path: Path, candidate_id: str) -> str:
    """Return a one-line decision breakdown from the primary DB."""
    if not db_path.exists():
        return ""
    try:
        con = sqlite3.connect(str(db_path))
        cur = con.cursor()
        cur.execute(
            """
            SELECT final_decision, COUNT(*) AS n
            FROM job_evaluations
            WHERE candidate_id = ?
            GROUP BY final_decision
            ORDER BY n DESC
            """,
            [candidate_id],
        )
        rows = cur.fetchall()
        con.close()
        if rows:
            return " | ".join(f"{(d or 'UNKNOWN')}={n}" for d, n in rows)
    except Exception:
        pass
    return ""


def update_agent_status(project_root: Path, db_path: Path, candidate_id: str, total_rows: int, loops: int) -> None:
    """Overwrite the '## Last pipeline run' block in AGENT_STATUS.md with fresh stats."""
    status_file = project_root / "AGENT_STATUS.md"
    if not status_file.exists():
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    evaluation_line = _evaluation_summary(db_path, candidate_id)

    run_block = (
        "\n\n---\n\n"
        "## Last pipeline run\n\n"
        f"**{now}** - {total_rows} jobs processed in {loops} loop(s)  \n"
        + (f"Evaluation totals: {evaluation_line}  \n" if evaluation_line else "")
    )

    try:
        content = status_file.read_text(encoding="utf-8")
        # Refresh the "Last updated:" timestamp at the top
        content = re.sub(r"Last updated:.*", f"Last updated: {now}", content)
        # Replace existing run block or append a new one
        pattern = r"\n\n---\n\n## Last pipeline run\n.*$"
        if re.search(pattern, content, re.DOTALL):
            content = re.sub(pattern, run_block.rstrip(), content, flags=re.DOTALL)
        else:
            content = content.rstrip() + run_block
        status_file.write_text(content, encoding="utf-8")
        print(f"[drain_queue] AGENT_STATUS.md updated ({now}).")
    except Exception as exc:
        print(f"[drain_queue] WARNING: could not update AGENT_STATUS.md: {exc}")


def main(argv: Optional[list[str]] = None) -> None:
    ap = argparse.ArgumentParser(
        description=(
            "Drain JobPipe queue: pull delta from Sheets and run the pipeline in batches until there are no new/changed rows.\n"
            "This version can skip jobs already present in the primary DB."
        )
    )
    ap.add_argument("--csv-url", default="", help="Published CSV URL for the EXPORT sheet (optional if JOBPIPE_CSV_URL is set).")
    ap.add_argument("--sheet-url", default="", help="Google Sheets edit URL (optional alternative to --csv-url).")
    ap.add_argument("--env-file", default=".env", help="Optional .env file (default: .env).")
    ap.add_argument("--profile", default="", help="Optional path to profile_pack.md override")
    ap.add_argument(
        "--candidate-id",
        default="",
        help="Candidate ID for DB-backed profile reads",
    )
    ap.add_argument("--config", default="", help="Path to pipeline YAML (optional).")
    ap.add_argument("--out", default=str(artifacts_root()), help=f"Artifact output folder (default: {artifacts_root()})")
    ap.add_argument("--reports", default=str(exports_root()), help=f"Exports folder (default: {exports_root()})")

    ap.add_argument("--state", default=str(jobs_state_path()), help=f"State JSON used by pull_sheets_csv (default: {jobs_state_path()})")
    ap.add_argument("--delta", default=str(jobs_delta_path()), help=f"Delta JSONL path (default: {jobs_delta_path()})")

    ap.add_argument("--batch-size", type=int, default=50, help="How many jobs to process per batch (default: 50)")
    ap.add_argument("--overwrite", action="store_true", help="Overwrite existing per-job stage JSONs if they exist.")
    ap.add_argument("--reset-state", action="store_true", help="Delete the state file before starting (forces a full first pass).")
    ap.add_argument("--no-only-changed", action="store_true", help="Pull ALL rows each loop (ignores delta; expensive).")
    ap.add_argument("--sleep", type=float, default=0.0, help="Sleep seconds between loops (default: 0).")
    ap.add_argument("--max-loops", type=int, default=200, help="Safety cap on loop count (default: 200).")
    ap.add_argument("--max-jobs", type=int, default=0, help="Stop after processing this many jobs total (0 = unlimited).")

    # --- Pull filtering (passed through to pull_sheets_csv) ---
    ap.add_argument("--status-filter", default="ACTIVE", metavar="STATUS",
                    help="Only pull rows with this status column value (default: ACTIVE). Pass ALL to disable.")
    ap.add_argument("--no-skip-expired-deadline", action="store_true", default=False,
                    help="Include jobs with past applicationDue dates (default: skip them).")

    # --- Processed-job filtering ---
    ap.add_argument("--skip-processed", action="store_true", default=True, help="Skip jobs already present in primary DB (default: on).")
    ap.add_argument("--no-skip-processed", dest="skip_processed", action="store_false", help="Disable processed-job filtering.")
    ap.add_argument("--db", default=str(primary_db_path()), help="Primary jobpipe.sqlite path for processed-job filtering")
    ap.add_argument("--sync-evaluations-before", action="store_true", default=True, help="Sync evaluation state from artifacts before pulling (default: on).")
    ap.add_argument("--no-sync-evaluations-before", dest="sync_evaluations_before", action="store_false", help="Disable evaluation sync before pull.")
    ap.add_argument("--sync-evaluations-after", action="store_true", default=True, help="Sync evaluation state from artifacts after processing (default: on).")
    ap.add_argument("--no-sync-evaluations-after", dest="sync_evaluations_after", action="store_false", help="Disable evaluation sync after run.")

    args = ap.parse_args(argv)

    load_env_file(Path(args.env_file))
    candidate_id = (args.candidate_id or os.environ.get("JOBPIPE_CANDIDATE_ID") or "default").strip() or "default"

    csv_url = (args.csv_url or os.environ.get("JOBPIPE_CSV_URL", "")).strip()
    sheet_url = (args.sheet_url or os.environ.get("JOBPIPE_SHEET_URL", "")).strip()
    if not csv_url and not sheet_url:
        raise SystemExit("Provide --csv-url or --sheet-url, or set JOBPIPE_CSV_URL/JOBPIPE_SHEET_URL in .env")

    py = sys.executable
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    reports_dir = Path(args.reports)
    reports_dir.mkdir(parents=True, exist_ok=True)

    db_path = Path(args.db)

    state_path = Path(args.state)
    if args.reset_state and state_path.exists():
        state_path.unlink()

    delta_path = Path(args.delta)
    expired_path = jobs_expired_path()
    tmp_dir = Path(".jobpipe_tmp")
    tmp_dir.mkdir(exist_ok=True)

    # Optional: keep evaluation state up to date before we decide what's "processed"
    if args.sync_evaluations_before:
        sync_cmd = [py, "-m", "jobpipe.cli.sync_evaluations", "--out", str(out_dir), "--reports", str(reports_dir), "--db", str(db_path), "--candidate-id", candidate_id]
        if expired_path.exists():
            sync_cmd += ["--expired-file", str(expired_path)]
        run(sync_cmd)

    processed_ids = load_processed_job_ids(
        primary_db_path=db_path,
        candidate_id=candidate_id,
    ) if args.skip_processed else set()
    if args.skip_processed:
        print(f"[drain_queue] processed-job filter ON: {len(processed_ids)} job_ids already evaluated in {db_path}")

    loops = 0
    total_rows_processed = 0
    total_batches = 0

    while True:
        loops += 1
        if loops > args.max_loops:
            print(f"[drain_queue] max_loops reached ({args.max_loops}). Stopping.")
            break

        pull_cmd = [py, "-m", "jobpipe.cli.pull_sheets_csv"]
        if csv_url:
            pull_cmd += ["--csv-url", csv_url]
        else:
            pull_cmd += ["--sheet-url", sheet_url]
        pull_cmd += ["--out", str(delta_path), "--state", str(state_path)]
        pull_cmd += ["--expired-out", str(expired_path)]
        pull_cmd += ["--db", str(db_path)]
        if not args.no_only_changed:
            pull_cmd += ["--only-changed"]
        if args.status_filter and args.status_filter.upper() != "ALL":
            pull_cmd += ["--status-filter", args.status_filter]
        if args.no_skip_expired_deadline:
            pull_cmd += ["--no-skip-expired-deadline"]

        run(pull_cmd)

        lines = read_jsonl_lines(delta_path)
        if not lines:
            print("[drain_queue] No changes -> done.")
            break

        # Processed-job filter: remove already-processed job_ids
        if args.skip_processed:
            kept: list[str] = []
            skipped = 0
            for s in lines:
                try:
                    obj = json.loads(s)
                except Exception:
                    kept.append(s)
                    continue
                jid = _job_id_from_json(obj)
                if jid and jid in processed_ids:
                    skipped += 1
                    continue
                kept.append(s)
                if jid:
                    # Also dedupe within this run (helps if the sheet contains dupes)
                    processed_ids.add(jid)
            lines = kept
            print(f"[drain_queue] processed-job filter: skipped={skipped}, remaining={len(lines)}")

        if not lines:
            print("[drain_queue] All pulled jobs already known -> done.")
            break

        # Process the pulled delta fully, even if it contains more than batch-size rows.
        bs = max(1, int(args.batch_size))
        for i in range(0, len(lines), bs):
            batch = lines[i : i + bs]
            batch_file = tmp_dir / f"jobs_batch_{loops:03d}_{(i//bs)+1:04d}.jsonl"
            write_jsonl_lines(batch_file, batch)

            run_cmd = [
                py,
                "-m",
                "jobpipe.cli.run_feed",
                "--jobs",
                str(batch_file),
                "--candidate-id",
                candidate_id,
                "--out",
                str(out_dir),
                "--max",
                str(len(batch)),
            ]
            # Always forward the DB path so run_feed can load the candidate profile
            run_cmd += ["--db", str(db_path)]
            if args.profile:
                run_cmd += ["--profile", args.profile]
            if args.config:
                run_cmd += ["--config", args.config]
            if args.overwrite:
                run_cmd += ["--overwrite"]

            run(run_cmd)

            total_batches += 1
            total_rows_processed += len(batch)

            if args.max_jobs > 0 and total_rows_processed >= args.max_jobs:
                print(f"[drain_queue] max-jobs {args.max_jobs} reached. Stopping.")
                break

            # optional cleanup
            try:
                batch_file.unlink()
            except OSError:
                pass

        if args.sleep and args.sleep > 0:
            time.sleep(args.sleep)

    # Update evaluation state at the end (so the next run won't reprocess even after reset-state)
    if args.sync_evaluations_after and total_rows_processed > 0:
        sync_cmd = [py, "-m", "jobpipe.cli.sync_evaluations", "--out", str(out_dir), "--reports", str(reports_dir), "--db", str(db_path), "--candidate-id", candidate_id]
        if expired_path.exists():
            sync_cmd += ["--expired-file", str(expired_path)]
        run(sync_cmd)

    # Write run summary to AGENT_STATUS.md so any Cowork session sees current state immediately
    project_root = Path(__file__).resolve().parents[2]
    update_agent_status(project_root, db_path, candidate_id, total_rows_processed, loops)

    print(
        f"[drain_queue] Finished. loops={loops}, batches={total_batches}, rows_processed={total_rows_processed}, out={out_dir}, db={db_path}"
    )


if __name__ == "__main__":
    main()
