from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from jobpipe.core.io import load_env_file, now_iso
from jobpipe.runtime.data_sources import resolve_runtime_profile, runtime_profile_choices


ARCHIVE_RELATIVE_PATHS = (
    Path(".jobpipe_tmp"),
    Path("artifacts"),
    Path("cache"),
    Path("db"),
    Path("exports"),
    Path("out_runs"),
    Path("reports"),
    Path("jobs_delta.jsonl"),
    Path("jobs_expired.jsonl"),
    Path("jobs_state.json"),
    Path("profile_embedding.npy"),
    Path("suggested_jobs.jsonl"),
)


def _default_tag() -> str:
    stamp = now_iso().replace(":", "").replace("-", "").replace("T", "_").replace("Z", "")
    return f"post_refactor_baseline_{stamp}"


def _resolve_data_root(profile_name: str, raw: str) -> Path:
    profile = resolve_runtime_profile(profile_name, data_root_override=raw)
    if profile.data_root is None:
        raise SystemExit("reset-runtime requires an external runtime data root. Use --runtime-profile live_local or --data-root.")
    return profile.data_root


def _inside_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _archive_item(root: Path, archive_dir: Path, rel_path: Path) -> bool:
    source = root / rel_path
    if not source.exists():
        return False
    target = archive_dir / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))
    return True


def _application_state_source(root: Path) -> Path | None:
    candidates = (
        root / "db" / "application_state.json",
        root / "application_state.json",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def reset_runtime_state(
    *,
    data_root_path: Path,
    archive_root_path: Path,
    tag: str,
    restore_app_state: bool = True,
) -> dict[str, Any]:
    root = data_root_path.resolve()
    archive_dir = archive_root_path.resolve() / tag
    archive_dir.mkdir(parents=True, exist_ok=False)

    app_state_snapshot: bytes | None = None
    app_state_relative: str | None = None
    active_app_state = _application_state_source(root)
    if restore_app_state and active_app_state is not None and _inside_root(active_app_state, root):
        app_state_snapshot = active_app_state.read_bytes()
        app_state_relative = "db/application_state.json"

    archived: list[str] = []
    for rel_path in ARCHIVE_RELATIVE_PATHS:
        if _archive_item(root, archive_dir, rel_path):
            archived.append(str(rel_path))

    for fresh_dir in (root / "db", root / "artifacts", root / "exports", root / "cache"):
        fresh_dir.mkdir(parents=True, exist_ok=True)

    restored: list[str] = []
    if app_state_snapshot is not None and app_state_relative is not None:
        restored_path = root / app_state_relative
        restored_path.parent.mkdir(parents=True, exist_ok=True)
        restored_path.write_bytes(app_state_snapshot)
        restored.append(app_state_relative)

    manifest = {
        "created_at": now_iso(),
        "data_root": str(root),
        "archive_dir": str(archive_dir),
        "archive_tag": tag,
        "archived_paths": archived,
        "restored_paths": restored,
        "notes": [
            "Generated runtime state was archived under archive_dir.",
            "Candidate inputs, secrets, and audit outputs outside the archived path set were left in place.",
        ],
    }
    (archive_dir / "reset_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    load_env_file(".env")

    ap = argparse.ArgumentParser(
        description="Archive generated runtime state under JOBPIPE_DATA_DIR and create a fresh baseline root without deleting candidate inputs or secrets."
    )
    ap.add_argument("--runtime-profile", choices=runtime_profile_choices(), default="live_local", help="Runtime profile to reset")
    ap.add_argument("--data-root", default="", help="Runtime root override (default: JOBPIPE_DATA_DIR)")
    ap.add_argument(
        "--archive-root",
        default="",
        help="Archive root override (default: <data-root>/_archives)",
    )
    ap.add_argument("--tag", default="", help="Archive tag override")
    ap.add_argument(
        "--no-restore-app-state",
        action="store_true",
        help="Do not copy the active application_state.json back into the fresh baseline",
    )
    args = ap.parse_args()

    root = _resolve_data_root(args.runtime_profile, args.data_root)
    archive_root_path = Path(args.archive_root).expanduser().resolve() if args.archive_root else root / "_archives"
    tag = args.tag.strip() or _default_tag()

    summary = reset_runtime_state(
        data_root_path=root,
        archive_root_path=archive_root_path,
        tag=tag,
        restore_app_state=not args.no_restore_app_state,
    )

    print("=== JobPipe Runtime Reset ===")
    print(f"Data root:    {summary['data_root']}")
    print(f"Archive dir:  {summary['archive_dir']}")
    print(f"Archive tag:  {summary['archive_tag']}")
    print(f"Archived:     {len(summary['archived_paths'])} path(s)")
    print(f"Restored:     {', '.join(summary['restored_paths']) or '(none)'}")


if __name__ == "__main__":
    main()
