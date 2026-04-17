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


def run(cmd: list[str]) -> None:
    print("> " + " ".join(cmd))
    subprocess.run(cmd, check=True)


def _job_id_from_json(obj: dict[str, Any]) -> str:
    return stable_job_id(obj)


def load_processed_ids(sqlite_path: Path) -> set[str]:
    """
    Returns job_ids present in the ledger SQLite.
    If the DB doesn't exist yet, returns empty set.
    """
    if not sqlite_path.exists():
        return set()
    try:
        con = sqlite3.connect(str(sqlite_path))
        cur = con.cursor()
        # Ledger schema created by jobpipe.cli.sync_ledger
        cur.execute("SELECT job_id FROM ledger")
        rows = cur.fetchall()
        return {str(r[0]) for r in rows if r and r[0]}
    except Exception:
        # If table doesn't exist yet, treat as empty.
        return set()
    finally:
        try:
            con.close()
        except Exception:
            pass


def _ledger_summary(ledger_path: Path) -> str:
    """Return a one-line decision breakdown from ledger.sqlite, e.g. 'SKIP=480 | REVIEW_LOW=12 | APPLY=3'."""
    if not ledger_path.exists():
        return ""
    try:
        con = sqlite3.connect(str(ledger_path))
        cur = con.cursor()
        cur.execute(
            "SELECT final_decision, COUNT(*) AS n FROM ledger GROUP BY final_decision ORDER BY n DESC"
        )
        rows = cur.fetchall()
        con.close()
        if rows:
            return " | ".join(f"{(d or 'UNKNOWN')}={n}" for d, n in rows)
    except Exception:
        pass
    return ""


def update_agent_status(project_root: Path, ledger_path: Path, total_rows: int, loops: int) -> None:
    """Overwrite the '## Last pipeline run' block in AGENT_STATUS.md with fresh stats."""
    status_file = project_root / "AGENT_STATUS.md"
    if not status_file.exists():
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    ledger_line = _ledger_summary(ledger_path)

    run_block = (
        "\n\n---\n\n"
        "## Last pipeline run\n\n"
        f"**{now}** - {total_rows} jobs processed in {loops} loop(s)  \n"
        + (f"Ledger totals: {ledger_line}  \n" if ledger_line else "")
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
            "This version can skip jobs already present in the SQLite ledger (so you can reset state safely)."
        )
    )
    ap.add_argument("--csv-url", default="", help="Published CSV URL for the EXPORT sheet (optional if JOBPIPE_CSV_URL is set).")
    ap.add_argument("--sheet-url", default="", help="Google Sheets edit URL (optional alternative to --csv-url).")
    ap.add_argument("--env-file", default=".env", help="Optional .env file (default: .env).")
    ap.add_argument("--profile", required=True, help="Path to profile_pack.md")
    ap.add_argument("--config", default="", help="Path to pipeline YAML (optional).")
    ap.add_argument("--out", default="./out_runs", help="Output folder for runs (default: ./out_runs)")
    ap.add_argument("--reports", default="./reports", help="Reports folder (default: ./reports)")

    ap.add_argument("--state", default="./jobs_state.json", help="State JSON used by pull_sheets_csv (default: ./jobs_state.json)")
    ap.add_argument("--delta", default="./jobs_delta.jsonl", help="Delta JSONL path (default: ./jobs_delta.jsonl)")

    ap.add_argument("--batch-size", type=int, default=50, help="How many jobs to process per batch (default: 50)")
    ap.add_argument("--overwrite", action="store_true", help="Overwrite existing per-job stage JSONs if they exist.")
    ap.add_argument("--reset-state", action="store_true", help="Delete the state file before starting (forces a full first pass).")
    ap.add_argument("--no-only-changed", action="store_true", help="Pull ALL rows each loop (ignores delta; expensive).")
    ap.add_argument("--sleep", type=float, default=0.0, help="Sleep seconds between loops (default: 0).")
    ap.add_argument("--max-loops", type=int, default=200, help="Safety cap on loop count (default: 200).")

    # --- Pull filtering (passed through to pull_sheets_csv) ---
    ap.add_argument("--status-filter", default="ACTIVE", metavar="STATUS",
                    help="Only pull rows with this status column value (default: ACTIVE). Pass ALL to disable.")
    ap.add_argument("--no-skip-expired-deadline", action="store_true", default=False,
                    help="Include jobs with past applicationDue dates (default: skip them).")

    # --- Ledger filtering ---
    ap.add_argument("--skip-processed", action="store_true", default=True, help="Skip jobs already present in SQLite ledger (default: on).")
    ap.add_argument("--no-skip-processed", dest="skip_processed", action="store_false", help="Disable ledger filtering.")
    ap.add_argument("--ledger-sqlite", default="", help="SQLite ledger path (default: reports/ledger.sqlite or JOBPIPE_LEDGER_SQLITE).")
    ap.add_argument("--sync-ledger-before", action="store_true", default=True, help="Sync ledger from out_runs before pulling (default: on).")
    ap.add_argument("--no-sync-ledger-before", dest="sync_ledger_before", action="store_false", help="Disable ledger sync before pull.")
    ap.add_argument("--sync-ledger-after", action="store_true", default=True, help="Sync ledger from out_runs after processing (default: on).")
    ap.add_argument("--no-sync-ledger-after", dest="sync_ledger_after", action="store_false", help="Disable ledger sync after run.")

    args = ap.parse_args(argv)

    load_env_file(Path(args.env_file))

    csv_url = (args.csv_url or os.environ.get("JOBPIPE_CSV_URL", "")).strip()
    sheet_url = (args.sheet_url or os.environ.get("JOBPIPE_SHEET_URL", "")).strip()
    if not csv_url and not sheet_url:
        raise SystemExit("Provide --csv-url or --sheet-url, or set JOBPIPE_CSV_URL/JOBPIPE_SHEET_URL in .env")

    py = sys.executable
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    reports_dir = Path(args.reports)
    reports_dir.mkdir(parents=True, exist_ok=True)

    ledger_sqlite = (args.ledger_sqlite or os.environ.get("JOBPIPE_LEDGER_SQLITE", "")).strip()
    ledger_path = Path(ledger_sqlite) if ledger_sqlite else (reports_dir / "ledger.sqlite")

    state_path = Path(args.state)
    if args.reset_state and state_path.exists():
        state_path.unlink()

    delta_path = Path(args.delta)
    expired_path = delta_path.parent / "jobs_expired.jsonl"
    tmp_dir = Path(".jobpipe_tmp")
    tmp_dir.mkdir(exist_ok=True)

    # Optional: keep ledger up to date before we decide what's "processed"
    if args.sync_ledger_before:
        sync_cmd = [py, "-m", "jobpipe.cli.sync_ledger", "--out", str(out_dir), "--reports", str(reports_dir), "--sqlite", str(ledger_path)]
        if expired_path.exists():
            sync_cmd += ["--expired-file", str(expired_path)]
        run(sync_cmd)

    processed_ids = load_processed_ids(ledger_path) if args.skip_processed else set()
    if args.skip_processed:
        print(f"[drain_queue] ledger filter ON: {len(processed_ids)} job_ids already in {ledger_path}")

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

        # Ledger filter: remove already-processed job_ids
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
            print(f"[drain_queue] ledger filter: skipped={skipped}, remaining={len(lines)}")

        if not lines:
            print("[drain_queue] All pulled jobs already in ledger -> done.")
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
                "--profile",
                args.profile,
                "--out",
                str(out_dir),
                "--max",
                str(len(batch)),
            ]
            if args.config:
                run_cmd += ["--config", args.config]
            if args.overwrite:
                run_cmd += ["--overwrite"]

            run(run_cmd)

            total_batches += 1
            total_rows_processed += len(batch)

            # optional cleanup
            try:
                batch_file.unlink()
            except OSError:
                pass

        if args.sleep and args.sleep > 0:
            time.sleep(args.sleep)

    # Update ledger at the end (so the next run won't reprocess even after reset-state)
    if args.sync_ledger_after and total_rows_processed > 0:
        sync_cmd = [py, "-m", "jobpipe.cli.sync_ledger", "--out", str(out_dir), "--reports", str(reports_dir), "--sqlite", str(ledger_path)]
        if expired_path.exists():
            sync_cmd += ["--expired-file", str(expired_path)]
        run(sync_cmd)

    # Write run summary to AGENT_STATUS.md so any Cowork session sees current state immediately
    project_root = Path(__file__).resolve().parents[2]
    update_agent_status(project_root, ledger_path, total_rows_processed, loops)

    print(
        f"[drain_queue] Finished. loops={loops}, batches={total_batches}, rows_processed={total_rows_processed}, out={out_dir}, ledger={ledger_path}"
    )


if __name__ == "__main__":
    main()
