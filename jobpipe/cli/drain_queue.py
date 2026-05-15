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

from jobpipe.core.intake_pipe import prune_connector_records, rebuild_intake_queue
from jobpipe.core.io import load_env_file, read_jsonl_lines, write_jsonl_lines, stable_job_id
from jobpipe.core.paths import bootstrap_private_data, get_jobpipe_paths

_DEFAULT_PATHS = get_jobpipe_paths()


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
    ap.add_argument(
        "--data-root",
        default="",
        help=f"JobPipe user data root (default: {_DEFAULT_PATHS.data_root})",
    )
    ap.add_argument(
        "--env-file",
        default="",
        help=f"Optional .env file (default: {_DEFAULT_PATHS.env_file}).",
    )
    ap.add_argument(
        "--profile",
        default="",
        help=f"Path to profile_pack.md (default: {_DEFAULT_PATHS.profile_pack_path})",
    )
    ap.add_argument(
        "--config",
        default="",
        help=f"Path to pipeline YAML (default: {_DEFAULT_PATHS.default_config_path}).",
    )
    ap.add_argument("--config-overlay", action="append", default=[], help="Optional config overlay YAML. Can be passed multiple times.")
    ap.add_argument(
        "--out",
        default="",
        help=f"Output folder for runs (default: {_DEFAULT_PATHS.out_runs_dir})",
    )
    ap.add_argument(
        "--reports",
        default="",
        help=f"Reports folder (default: {_DEFAULT_PATHS.reports_dir})",
    )

    ap.add_argument(
        "--state",
        default="",
        help=f"State JSON used by pull_sheets_csv (default: {_DEFAULT_PATHS.jobs_state_path})",
    )
    ap.add_argument(
        "--delta",
        default="",
        help=f"Delta JSONL path (default: {_DEFAULT_PATHS.jobs_delta_path})",
    )
    ap.add_argument(
        "--nav-connector",
        default="",
        help=f"NAV connector JSONL path (default: {_DEFAULT_PATHS.nav_connector_path})",
    )
    ap.add_argument(
        "--leads-connector",
        default="",
        help=f"Lead connector JSONL path (default: {_DEFAULT_PATHS.leads_connector_path})",
    )
    ap.add_argument(
        "--merge-only",
        action="store_true",
        help="Merge connector staging into --delta and exit before pulling, ledger sync, or run-feed.",
    )

    ap.add_argument("--batch-size", type=int, default=50, help="How many jobs to process per batch (default: 50)")
    ap.add_argument("--max-total-jobs", type=int, default=0, help="Stop after processing this many jobs in total (0 = no cap).")
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
    ap.add_argument(
        "--ledger-sqlite",
        default="",
        help=f"SQLite ledger path (default: {_DEFAULT_PATHS.ledger_sqlite_path} or JOBPIPE_LEDGER_SQLITE).",
    )
    ap.add_argument("--sync-ledger-before", action="store_true", default=True, help="Sync ledger from out_runs before pulling (default: on).")
    ap.add_argument("--no-sync-ledger-before", dest="sync_ledger_before", action="store_false", help="Disable ledger sync before pull.")
    ap.add_argument("--sync-ledger-after", action="store_true", default=True, help="Sync ledger from out_runs after processing (default: on).")
    ap.add_argument("--no-sync-ledger-after", dest="sync_ledger_after", action="store_false", help="Disable ledger sync after run.")
    ap.add_argument("--sync-primary-db-after", action="store_true", default=True, help="Sync primary jobpipe.sqlite (job_evaluations) after processing (default: on).")
    ap.add_argument("--no-sync-primary-db-after", dest="sync_primary_db_after", action="store_false", help="Disable primary DB sync after run.")

    args = ap.parse_args(argv)
    paths = get_jobpipe_paths(args.data_root or None)

    env_file = Path(args.env_file) if args.env_file else paths.env_file
    profile_path = Path(args.profile) if args.profile else paths.profile_pack_path
    config_path = Path(args.config) if args.config else paths.default_config_path
    out_dir = Path(args.out) if args.out else paths.out_runs_dir
    reports_dir = Path(args.reports) if args.reports else paths.reports_dir
    state_path = Path(args.state) if args.state else paths.jobs_state_path
    delta_path = Path(args.delta) if args.delta else paths.jobs_delta_path
    nav_connector_path = Path(args.nav_connector) if args.nav_connector else paths.nav_connector_path
    leads_connector_path = Path(args.leads_connector) if args.leads_connector else paths.leads_connector_path

    if args.merge_only:
        merge_summary = rebuild_intake_queue(
            nav_path=nav_connector_path,
            leads_path=leads_connector_path,
            out_path=delta_path,
        )
        print(
            "[drain_queue] merge-only: "
            f"nav={merge_summary['nav_records']} "
            f"leads={merge_summary['lead_records']} "
            f"merged={merge_summary['merged_records']} "
            f"out={delta_path}"
        )
        print("[drain_queue] merge-only: run_feed skipped.")
        return

    bootstrap_private_data(paths, include_artifacts=True)
    load_env_file(env_file)

    csv_url = (args.csv_url or os.environ.get("JOBPIPE_CSV_URL", "")).strip()
    sheet_url = (args.sheet_url or os.environ.get("JOBPIPE_SHEET_URL", "")).strip()
    supabase_url = os.environ.get("JOBPIPE_SUPABASE_URL", "").strip()
    supabase_key = os.environ.get("JOBPIPE_SUPABASE_KEY", "").strip()
    use_supabase = bool(supabase_url and supabase_key)
    if not use_supabase and not csv_url and not sheet_url:
        raise SystemExit("Provide --csv-url or --sheet-url, or set JOBPIPE_CSV_URL/JOBPIPE_SHEET_URL in .env, "
                         "or set JOBPIPE_SUPABASE_URL + JOBPIPE_SUPABASE_KEY for Supabase intake.")

    py = sys.executable
    out_dir.mkdir(parents=True, exist_ok=True)

    reports_dir.mkdir(parents=True, exist_ok=True)

    ledger_sqlite = (args.ledger_sqlite or os.environ.get("JOBPIPE_LEDGER_SQLITE", "")).strip()
    ledger_path = Path(ledger_sqlite) if ledger_sqlite else (reports_dir / "ledger.sqlite")

    if args.reset_state and state_path.exists():
        state_path.unlink()

    expired_path = delta_path.parent / "jobs_expired.jsonl"
    tmp_dir = paths.tmp_dir
    tmp_dir.mkdir(exist_ok=True)

    # Optional: keep ledger up to date before we decide what's "processed"
    if args.sync_ledger_before:
        sync_cmd = [
            py,
            "-m",
            "jobpipe.cli.sync_ledger",
            "--data-root",
            str(paths.data_root),
            "--out",
            str(out_dir),
            "--reports",
            str(reports_dir),
            "--sqlite",
            str(ledger_path),
        ]
        if expired_path.exists():
            sync_cmd += ["--expired-file", str(expired_path)]
        run(sync_cmd)

    processed_ids = load_processed_ids(ledger_path) if args.skip_processed else set()
    if args.skip_processed:
        print(f"[drain_queue] ledger filter ON: {len(processed_ids)} job_ids already in {ledger_path}")

        # Canonical-migration: also skip jobs already decided in Supabase under the
        # current profile_version. Stale decisions (older profile) are NOT in this
        # set so they get re-triaged. Best-effort: missing config = no-op.
        try:
            from jobpipe.core.decision_sink import get_profile_version, load_decided_job_ids
            profile_version = get_profile_version(paths.profile_pack_path)
            supabase_decided = load_decided_job_ids(profile_version=profile_version)
            new_ids = supabase_decided - processed_ids
            processed_ids |= supabase_decided
            print(
                f"[drain_queue] supabase decisions filter: +{len(new_ids)} new "
                f"({len(supabase_decided)} total) under profile_version={profile_version}"
            )
        except Exception as exc:
            print(f"[drain_queue] supabase decisions query skipped: {exc}")

    loops = 0
    total_rows_processed = 0
    total_batches = 0

    while True:
        if args.max_total_jobs and total_rows_processed >= args.max_total_jobs:
            print(f"[drain_queue] max_total_jobs reached ({args.max_total_jobs}). Stopping.")
            break

        loops += 1
        if loops > args.max_loops:
            print(f"[drain_queue] max_loops reached ({args.max_loops}). Stopping.")
            break

        if use_supabase:
            pull_cmd = [py, "-m", "jobpipe.cli.pull_supabase_jobs", "--data-root", str(paths.data_root)]
            pull_cmd += ["--out", str(nav_connector_path), "--state", str(state_path)]
            if not args.no_only_changed:
                pull_cmd += ["--only-changed"]
        else:
            pull_cmd = [py, "-m", "jobpipe.cli.pull_sheets_csv", "--data-root", str(paths.data_root)]
            if csv_url:
                pull_cmd += ["--csv-url", csv_url]
            else:
                pull_cmd += ["--sheet-url", sheet_url]
            pull_cmd += ["--out", str(nav_connector_path), "--state", str(state_path)]
            pull_cmd += ["--expired-out", str(expired_path)]
            if not args.no_only_changed:
                pull_cmd += ["--only-changed"]
        if args.status_filter and args.status_filter.upper() != "ALL":
            pull_cmd += ["--status-filter", args.status_filter]
        if args.no_skip_expired_deadline:
            pull_cmd += ["--no-skip-expired-deadline"]

        run(pull_cmd)

        merge_summary = rebuild_intake_queue(
            nav_path=nav_connector_path,
            leads_path=leads_connector_path,
            out_path=delta_path,
        )
        print(
            "[drain_queue] intake merge: "
            f"nav={merge_summary['nav_records']} "
            f"leads={merge_summary['lead_records']} "
            f"merged={merge_summary['merged_records']}"
        )

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

        if args.max_total_jobs:
            remaining = args.max_total_jobs - total_rows_processed
            if remaining <= 0:
                print(f"[drain_queue] max_total_jobs reached ({args.max_total_jobs}). Stopping.")
                break
            if len(lines) > remaining:
                print(f"[drain_queue] trimming pulled rows from {len(lines)} to {remaining} due to max_total_jobs")
                lines = lines[:remaining]

        # Process the pulled delta fully, even if it contains more than batch-size rows.
        bs = max(1, int(args.batch_size))
        processed_keys: list[str] = []
        for i in range(0, len(lines), bs):
            batch = lines[i : i + bs]
            for raw in batch:
                try:
                    processed_keys.append(json.loads(raw).get("intake_dedupe_key", ""))
                except Exception:
                    continue
            batch_file = tmp_dir / f"jobs_batch_{loops:03d}_{(i//bs)+1:04d}.jsonl"
            write_jsonl_lines(batch_file, batch)

            run_cmd = [
                py,
                "-m",
                "jobpipe.cli.run_feed",
                "--data-root",
                str(paths.data_root),
                "--env-file",
                str(env_file),
                "--jobs",
                str(batch_file),
                "--profile",
                str(profile_path),
                "--out",
                str(out_dir),
                "--max",
                str(len(batch)),
            ]
            if config_path:
                run_cmd += ["--config", str(config_path)]
            for overlay in args.config_overlay:
                run_cmd += ["--config-overlay", overlay]
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

        processed_keys = [key for key in processed_keys if key]
        if processed_keys:
            pruned_nav = prune_connector_records(nav_connector_path, processed_keys)
            pruned_leads = prune_connector_records(leads_connector_path, processed_keys)
            print(
                f"[drain_queue] pruned connector staging: nav={pruned_nav}, leads={pruned_leads}"
            )

        if args.sleep and args.sleep > 0:
            time.sleep(args.sleep)

    # Update ledger at the end (so the next run won't reprocess even after reset-state)
    if args.sync_ledger_after and total_rows_processed > 0:
        sync_cmd = [
            py,
            "-m",
            "jobpipe.cli.sync_ledger",
            "--data-root",
            str(paths.data_root),
            "--out",
            str(out_dir),
            "--reports",
            str(reports_dir),
            "--sqlite",
            str(ledger_path),
        ]
        if expired_path.exists():
            sync_cmd += ["--expired-file", str(expired_path)]
        run(sync_cmd)

    # Sync primary jobpipe.sqlite (job_evaluations) so prepare_application can find new jobs
    if args.sync_primary_db_after and total_rows_processed > 0 and paths.data_root:
        primary_db = paths.data_root / "db" / "jobpipe.sqlite"
        sync_eval_cmd = [
            py,
            "-m",
            "jobpipe.cli.sync_evaluations",
            "--out",
            str(out_dir),
            "--reports",
            str(reports_dir),
            "--db",
            str(primary_db),
            "--include-description",
        ]
        if expired_path.exists():
            sync_eval_cmd += ["--expired-file", str(expired_path)]
        run(sync_eval_cmd)

    # Write run summary to AGENT_STATUS.md so any Cowork session sees current state immediately
    project_root = Path(__file__).resolve().parents[2]
    update_agent_status(project_root, ledger_path, total_rows_processed, loops)

    print(
        f"[drain_queue] Finished. loops={loops}, batches={total_batches}, rows_processed={total_rows_processed}, out={out_dir}, ledger={ledger_path}"
    )


if __name__ == "__main__":
    main()
