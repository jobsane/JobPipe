from __future__ import annotations

import argparse
import json
import os
import uuid

import traceback


def read_json_safe(path: str) -> dict | None:
    """Read a JSON file, returning None on any error."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None

from jobpipe.core.io import ensure_dir, iter_jobs, load_env_file, stable_job_id, now_iso, write_json

# Load .env (OPENAI_API_KEY, etc.) before importing/initializing anything that might rely on env
load_env_file(".env")

from jobpipe.core.candidate_data import default_candidate_id, load_candidate_profile_pack
from jobpipe.core.config import load_config
from jobpipe.runtime.paths import artifacts_root, primary_db_path, repo_root
from jobpipe.runtime.pipeline import build_stages
from jobpipe.core.primary_db import (
    connect_primary_db,
    ensure_candidate,
    mark_pipeline_run_finished,
    upsert_pipeline_run,
)
from jobpipe.model.schema import JobContext, RunMeta
from jobpipe.core.runner import PipelineRunner


def _open_pipeline_run(db_conn, *, run_id: str, candidate_id: str, cfg, args, started_at: str) -> None:
    profile_row = db_conn.execute(
        """
        SELECT profile_version_id
        FROM candidate_profiles
        WHERE candidate_id = ? AND is_active = 1
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        [candidate_id],
    ).fetchone()
    upsert_pipeline_run(
        db_conn,
        {
            "run_id": run_id,
            "candidate_id": candidate_id,
            "profile_version_id": profile_row[0] if profile_row else "",
            "config_version": cfg.pipeline_name,
            "jobs_path": args.jobs,
            "max_jobs": args.max,
            "status": "running",
            "started_at": started_at,
            "finished_at": "",
            "jobs_seen": 0,
            "jobs_failed": 0,
            "source_batch_json": {
                "jobs_path": args.jobs,
                "out_dir": args.out,
                "config_path": args.config,
                "overwrite": bool(args.overwrite),
            },
            "updated_at": started_at,
        },
    )
    db_conn.commit()


def _build_repaired_index_record(job_dir: str, job_id: str) -> dict:
    inp = read_json_safe(os.path.join(job_dir, "00_input.json")) or {}
    triage = read_json_safe(os.path.join(job_dir, "01_triage.json")) or {}
    mod = read_json_safe(os.path.join(job_dir, "05_moderator.json")) or {}
    return {
        "job_id": job_id,
        "title": inp.get("title", ""),
        "employer": inp.get("employer_name", ""),
        "triage_decision": triage.get("decision", ""),
        "triage_confidence": triage.get("confidence"),
        "triage_signals": triage.get("signals", []),
        "final_decision": mod.get("final_decision", ""),
        "fit_score": mod.get("fit_score"),
        "pivot_score": mod.get("pivot_score"),
        "repaired": True,
    }


def _repair_missing_index_entries(run_dir: str) -> int:
    index_path = os.path.join(run_dir, "index.jsonl")
    existing_ids: set[str] = set()
    if os.path.exists(index_path):
        with open(index_path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                    if rec.get("job_id"):
                        existing_ids.add(rec["job_id"])
                except Exception:
                    pass

    repaired = 0
    for entry in sorted(os.scandir(run_dir), key=lambda e: e.name):
        if not entry.is_dir():
            continue
        job_id = entry.name
        if job_id in existing_ids:
            continue
        try:
            rec = _build_repaired_index_record(entry.path, job_id)
            with open(index_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            repaired += 1
        except Exception as rep_exc:
            print(f"[WARN] repair failed for {job_id}: {rep_exc}", flush=True)
    return repaired


def _close_pipeline_run(db_conn, *, run_id: str, run_status: str, count: int, max_jobs: int, errors: int) -> None:
    finished_at = now_iso()
    jobs_seen = min(count, max_jobs) if max_jobs else count
    mark_pipeline_run_finished(
        db_conn,
        run_id=run_id,
        status=run_status,
        finished_at=finished_at,
        jobs_seen=jobs_seen,
        jobs_failed=errors,
    )
    db_conn.commit()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", required=True, help="Path to jobs .jsonl/.json/.csv")
    ap.add_argument("--profile", default="", help="Optional path to profile_pack.md override")
    ap.add_argument("--db", default=str(primary_db_path()), help="Path to primary jobpipe.sqlite")
    ap.add_argument(
        "--candidate-id",
        default=default_candidate_id(),
        help=f"Candidate ID for primary DB profile reads (default: {default_candidate_id()})",
    )
    ap.add_argument("--out", default=str(artifacts_root()), help=f"Artifacts output directory (default: {artifacts_root()})")
    ap.add_argument("--config", default=str(repo_root() / "configs" / "pipeline.v1.yaml"), help="Pipeline config YAML")
    ap.add_argument("--max", type=int, default=0, help="Max number of jobs (0 = all)")
    ap.add_argument("--overwrite", action="store_true", help="Overwrite per-stage artifacts")
    args = ap.parse_args()

    cfg = load_config(args.config)
    profile_pack = load_candidate_profile_pack(
        args.profile or None,
        candidate_id=args.candidate_id,
        db_path=args.db,
    )

    run_id = f"{cfg.pipeline_name}_{uuid.uuid4().hex[:8]}"
    run_dir = os.path.join(args.out, run_id)
    ensure_dir(run_dir)

    runner = PipelineRunner(build_stages(cfg, profile_pack=profile_pack))
    meta = RunMeta(run_id=run_id, pipeline_name=cfg.pipeline_name, created_at=now_iso())
    started_at = meta.created_at

    count = 0
    errors = 0
    run_status = "completed"
    db_conn = None
    try:
        db_conn = connect_primary_db(args.db)
        ensure_candidate(db_conn, candidate_id=args.candidate_id)
        _open_pipeline_run(
            db_conn,
            run_id=run_id,
            candidate_id=args.candidate_id,
            cfg=cfg,
            args=args,
            started_at=started_at,
        )

        for job in iter_jobs(args.jobs):
            count += 1
            if args.max and count > args.max:
                break

            job_id = stable_job_id(job)
            job_dir = os.path.join(run_dir, job_id)
            ctx = JobContext(meta=meta, job_id=job_id, job=job, profile_pack=profile_pack)

            try:
                ctx = runner.run_job(ctx, job_dir=job_dir, overwrite=args.overwrite)
            except Exception as exc:
                errors += 1
                ensure_dir(job_dir)
                write_json(
                    os.path.join(job_dir, "pipeline_error.json"),
                    {"job_id": job_id, "error": str(exc), "traceback": traceback.format_exc()},
                )
                print(f"[ERROR] job {job_id} failed: {exc}", flush=True)

            try:
                runner.append_index(run_dir, ctx)
            except Exception as idx_exc:
                print(f"[WARN] index write failed for {job_id}: {idx_exc}", flush=True)

        # ── Post-run self-heal: repair any missing index entries ──────────────────
        # Catches cases where append_index silently failed mid-run (e.g. file lock,
        # exception after run_job completed successfully).
        try:
            repaired = _repair_missing_index_entries(run_dir)
            if repaired:
                print(f"[INFO] Repaired {repaired} missing index entries.", flush=True)
        except Exception as heal_exc:
            print(f"[WARN] Post-run index repair failed: {heal_exc}", flush=True)
    except Exception:
        run_status = "failed"
        raise
    finally:
        if db_conn is not None:
            _close_pipeline_run(
                db_conn,
                run_id=run_id,
                run_status=run_status,
                count=count,
                max_jobs=args.max,
                errors=errors,
            )
            db_conn.close()

    suffix = f" ({errors} errors)" if errors else ""
    print(f"Done. Run dir: {run_dir}{suffix}")


if __name__ == "__main__":
    main()
