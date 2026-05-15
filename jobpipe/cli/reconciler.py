"""Background reconciler loop for the JobPipe canonical state migration.

Replaces run_scheduled_flow as the operator-facing entry point. Runs the
drain pipeline on a configurable cadence; relies on Supabase decision
filtering (load_decided_job_ids) to keep each tick cheap when nothing's
changed.

Self-correcting: no manual reset, no run-id pinning, no flag juggling.
The rig walks the data and reconciles current Supabase state against the
current profile_version. Operator's only job is to run this process —
typically via systemd, Docker compose entry, or a process supervisor.

Usage:
  python -m jobpipe.cli.reconciler                       # default 5-min interval
  python -m jobpipe.cli.reconciler --interval-seconds 60 # tighter cadence
  python -m jobpipe.cli.reconciler --once                # single tick (debug)

Any args after a `--` are forwarded to drain_queue.main verbatim:
  python -m jobpipe.cli.reconciler --interval-seconds 60 -- --max-loops 1
"""
from __future__ import annotations

import argparse
import signal
import sys
import time
from typing import List, Optional

from jobpipe.cli import drain_queue


_shutdown = False


def _handle_signal(signum, _frame) -> None:
    global _shutdown
    _shutdown = True
    print(
        f"[reconciler] received signal {signum}, finishing current tick then exiting...",
        flush=True,
    )


def main(argv: Optional[List[str]] = None) -> int:
    raw = sys.argv[1:] if argv is None else argv

    # Split our args from drain_queue passthrough at the first `--`.
    if "--" in raw:
        idx = raw.index("--")
        own_args = raw[:idx]
        drain_args = raw[idx + 1:]
    else:
        own_args = raw
        drain_args = []

    ap = argparse.ArgumentParser(
        description="Background reconciler loop for JobPipe (canonical state migration).",
    )
    ap.add_argument(
        "--interval-seconds",
        type=int,
        default=300,
        help="Seconds to sleep between ticks (default: 300 = 5 minutes).",
    )
    ap.add_argument(
        "--once",
        action="store_true",
        help="Run a single tick and exit (useful for debugging or cron-driven mode).",
    )
    args = ap.parse_args(own_args)

    signal.signal(signal.SIGINT, _handle_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_signal)

    tick = 0
    while not _shutdown:
        tick += 1
        print(f"\n=== reconciler tick {tick} ===", flush=True)
        try:
            drain_queue.main(drain_args)
        except SystemExit as exc:
            if exc.code not in (None, 0):
                print(
                    f"[reconciler] drain_queue tick {tick} failed exit={exc.code}, continuing",
                    flush=True,
                )
        except Exception as exc:  # noqa: BLE001 — never let one tick kill the loop
            print(
                f"[reconciler] drain_queue tick {tick} raised: {exc!r}, continuing",
                flush=True,
            )

        if args.once or _shutdown:
            break

        # Sleep in 1s steps so a SIGTERM during sleep exits within ~1s.
        remaining = args.interval_seconds
        print(f"[reconciler] sleeping {remaining}s until next tick", flush=True)
        for _ in range(remaining):
            if _shutdown:
                break
            time.sleep(1)

    print("[reconciler] exited cleanly.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
