"""Record one rendered Reactive Resume document ref back into canonical JobPipe state."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import List, Optional

from jobpipe.model import ReactiveResumeRenderedDocumentRef
from jobpipe.runtime import record_reactive_resume_document_ref
from jobpipe.runtime.data_sources import resolve_profile_paths, runtime_profile_choices

_DEFAULT_CANDIDATE_ID = (os.environ.get("JOBPIPE_CANDIDATE_ID") or "default").strip() or "default"


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Record one rendered Reactive Resume document ref into canonical JobPipe state.")
    parser.add_argument("job_id", help="Canonical job_id")
    parser.add_argument("kind", help="Document kind, e.g. tailored_cv_docx")
    parser.add_argument("storage_path", help="Rendered document path")
    parser.add_argument("--document-id", default="", help="Optional stable document ID")
    parser.add_argument("--evaluation-id", default="", help="Optional evaluation/run context")
    parser.add_argument("--status", default="draft", help="Document status (default: draft)")
    parser.add_argument("--producer", default="reactive_resume", help="Producer label (default: reactive_resume)")
    parser.add_argument("--preview-text", default="", help="Optional preview text")
    parser.add_argument("--updated-at", default="", help="Optional updated timestamp")
    parser.add_argument("--document-json", default="", help="Optional document metadata JSON object")
    parser.add_argument("--candidate-id", default=_DEFAULT_CANDIDATE_ID, help=f"Candidate ID (default: {_DEFAULT_CANDIDATE_ID})")
    parser.add_argument("--db", default="", help="Path to primary jobpipe.sqlite override")
    parser.add_argument("--runtime-profile", choices=runtime_profile_choices(), default="default", help="Runtime profile to resolve DB path from")
    parser.add_argument("--data-root", default="", help="Runtime data root override for live_local profile")
    args = parser.parse_args(argv)
    runtime = resolve_profile_paths(
        args.runtime_profile,
        data_root_override=args.data_root,
        db_override=args.db,
    )

    document_json = {}
    if args.document_json:
        document_json = json.loads(args.document_json)
        if not isinstance(document_json, dict):
            raise SystemExit("--document-json must decode to an object")

    document_id = args.document_id or f"reactive_resume::{args.job_id}::{args.kind}"
    ref = ReactiveResumeRenderedDocumentRef(
        document_id=document_id,
        candidate_id=args.candidate_id,
        job_id=args.job_id,
        evaluation_id=args.evaluation_id,
        kind=args.kind,
        storage_path=args.storage_path,
        status=args.status,
        producer=args.producer,
        updated_at=args.updated_at,
        preview_text=args.preview_text,
        document_json=document_json,
    )
    recorded = record_reactive_resume_document_ref(runtime.primary_db_path, ref)
    print(json.dumps(recorded.model_dump(mode="json"), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
