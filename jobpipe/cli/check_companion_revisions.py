from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List

from jobpipe.core.companion_revisions import build_companion_revision_report


def _render_human_report(report: dict) -> str:
    lines: List[str] = []
    overall = str(report.get("status") or "unknown").upper()
    lines.append(f"Companion revision status: {overall}")
    for item in report.get("companions", []):
        lines.append("")
        lines.append(f"[{item.get('status', 'unknown').upper()}] {item.get('id', '<unknown>')}")
        lines.append(f"  path: {item.get('resolved_path', '')}")
        lines.append(
            f"  pinned: {item.get('pinned_branch', '')} @ {str(item.get('pinned_commit', ''))[:12]}"
        )
        actual_branch = str(item.get("actual_branch") or "")
        actual_commit = str(item.get("actual_commit") or "")
        if actual_branch or actual_commit:
            lines.append(f"  actual: {actual_branch or '<detached>'} @ {actual_commit[:12]}")
        if item.get("dirty"):
            lines.append("  dirty: yes")
        notes = item.get("notes") or []
        for note in notes:
            lines.append(f"  note: {note}")
    return "\n".join(lines)


def main(argv: List[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Check local companion repos against COMPANION_REVISIONS.json.")
    ap.add_argument(
        "--repo-root",
        default="",
        help="Override the JobPipe repo root that contains COMPANION_REVISIONS.json",
    )
    ap.add_argument("--json", action="store_true", help="Emit the report as JSON.")
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any companion is missing, dirty, or off the pinned revision.",
    )
    args = ap.parse_args(argv)

    report = build_companion_revision_report(Path(args.repo_root).resolve() if args.repo_root else None)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(_render_human_report(report))

    if args.strict and report.get("status") != "aligned":
        sys.exit(1)


if __name__ == "__main__":
    main()
