from __future__ import annotations

import argparse
import json
import os
import traceback
import uuid


def read_json_safe(path: str) -> dict | None:
    """Read a JSON file, returning None on any error."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def read_stage_json(job_dir: str, stage_name: str) -> dict | None:
    """Read a stage artifact by suffix so stage-number drift does not break recovery."""
    try:
        matches = sorted(
            name for name in os.listdir(job_dir)
            if name.endswith(f"_{stage_name}.json")
        )
    except Exception:
        return None
    if not matches:
        return None
    return read_json_safe(os.path.join(job_dir, matches[-1]))

from jobpipe.core.io import ensure_dir, iter_jobs, load_env_file, load_profile_pack, stable_job_id, now_iso, write_json
from jobpipe.core.paths import JOBPIPE_DATA_ROOT_ENV, bootstrap_private_data, get_jobpipe_paths
from jobpipe.core.profile_layer import build_triage_instruction_profile_summary, load_or_build_profile_layer_for_paths

from jobpipe.core.config import load_config
from jobpipe.core.schema import JobContext, RunMeta
from jobpipe.core.runner import PipelineRunner
from jobpipe.stages.pipeline import build_stages

_DEFAULT_PATHS = get_jobpipe_paths()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", required=True, help="Path to jobs .jsonl/.json/.csv")
    ap.add_argument(
        "--data-root",
        default="",
        help=f"JobPipe user data root (default: {_DEFAULT_PATHS.data_root})",
    )
    ap.add_argument(
        "--env-file",
        default="",
        help=f"Path to .env file (default: {_DEFAULT_PATHS.env_file})",
    )
    ap.add_argument(
        "--profile",
        default="",
        help=f"Path to profile_pack.md (default: {_DEFAULT_PATHS.profile_pack_path})",
    )
    ap.add_argument(
        "--out",
        default="",
        help=f"Output directory (default: {_DEFAULT_PATHS.out_runs_dir})",
    )
    ap.add_argument(
        "--config",
        default="",
        help=f"Pipeline config YAML (default: {_DEFAULT_PATHS.default_config_path})",
    )
    ap.add_argument("--config-overlay", action="append", default=[], help="Optional config overlay YAML. Can be passed multiple times.")
    ap.add_argument("--max", type=int, default=0, help="Max number of jobs (0 = all)")
    ap.add_argument("--overwrite", action="store_true", help="Overwrite per-stage artifacts")
    args = ap.parse_args()

    paths = get_jobpipe_paths(args.data_root or None)
    os.environ[JOBPIPE_DATA_ROOT_ENV] = str(paths.data_root)
    bootstrap_private_data(paths, include_artifacts=True)
    env_file = args.env_file or str(paths.env_file)
    profile_path = args.profile or str(paths.profile_pack_path)
    out_path = args.out or str(paths.out_runs_dir)
    config_path = args.config or str(paths.default_config_path)

    load_env_file(env_file)
    cfg = load_config(config_path, overlays=args.config_overlay)
    profile_pack = load_profile_pack(profile_path)
    profile_layer = load_or_build_profile_layer_for_paths(paths)

    run_id = f"{cfg.pipeline_name}_{uuid.uuid4().hex[:8]}"
    run_dir = os.path.join(out_path, run_id)
    ensure_dir(run_dir)

    runner = PipelineRunner(
        build_stages(
            cfg,
            profile_pack=profile_pack,
            triage_profile_summary=build_triage_instruction_profile_summary(profile_layer),
            targeting_title_patterns=list(profile_layer.targeting_profile.target_title_patterns),
        )
    )
    meta = RunMeta(run_id=run_id, pipeline_name=cfg.pipeline_name, created_at=now_iso())

    count = 0
    errors = 0
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
        index_path = os.path.join(run_dir, "index.jsonl")
        existing_ids: set = set()
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
            jid = entry.name
            if jid in existing_ids:
                continue
            # Reconstruct a minimal summary from artifacts
            try:
                inp = read_json_safe(os.path.join(entry.path, "00_input.json")) or {}
                triage = read_stage_json(entry.path, "triage") or {}
                profile = read_stage_json(entry.path, "profile_match") or {}
                pivot = read_stage_json(entry.path, "pivot") or {}
                triage_decision_v3 = read_stage_json(entry.path, "triage_decision_v3") or {}
                triage_ambiguity_v3 = read_stage_json(entry.path, "triage_ambiguity_v3") or {}
                advantage_assessment_v3 = read_stage_json(entry.path, "advantage_assessment_v3") or {}
                narrative_strategy_v3 = read_stage_json(entry.path, "narrative_strategy_v3") or {}
                mod = read_stage_json(entry.path, "moderator") or {}
                effective_triage_v3 = (
                    triage_ambiguity_v3.get("final_decision")
                    if isinstance(triage_ambiguity_v3.get("final_decision"), dict)
                    else triage_decision_v3
                )
                rec = {
                    "job_id": jid,
                    "title": inp.get("title", ""),
                    "employer": inp.get("employer_name", ""),
                    "triage_decision": triage.get("triage_decision", triage.get("decision", "")),
                    "triage_confidence": triage.get("confidence"),
                    "triage_signals": triage.get("signals", []),
                    "triage_v3_label": effective_triage_v3.get("label"),
                    "triage_v3_weighted_score": effective_triage_v3.get("weighted_score"),
                    "triage_v3_confidence": effective_triage_v3.get("confidence"),
                    "triage_v3_needs_ambiguity": effective_triage_v3.get("needs_ambiguity_pass"),
                    "triage_ambiguity_label": triage_ambiguity_v3.get("resolved_label"),
                    "advantage_type": advantage_assessment_v3.get("advantage_type"),
                    "advantage_review_priority": advantage_assessment_v3.get("review_priority"),
                    "narrative_positioning_angle": narrative_strategy_v3.get("positioning_angle"),
                    "narrative_brand_frame": narrative_strategy_v3.get("brand_frame"),
                    "final_decision": mod.get("final_decision", ""),
                    "fit_score": profile.get("fit_score"),
                    "pivot_score": pivot.get("pivot_score"),
                    "repaired": True,
                }
                with open(index_path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                repaired += 1
            except Exception as rep_exc:
                print(f"[WARN] repair failed for {jid}: {rep_exc}", flush=True)

        if repaired:
            print(f"[INFO] Repaired {repaired} missing index entries.", flush=True)
    except Exception as heal_exc:
        print(f"[WARN] Post-run index repair failed: {heal_exc}", flush=True)

    suffix = f" ({errors} errors)" if errors else ""
    print(f"Done. Run dir: {run_dir}{suffix}")


if __name__ == "__main__":
    main()
