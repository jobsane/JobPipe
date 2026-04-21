from __future__ import annotations

import hashlib

from jobpipe.authoring.output_models import GeneratedApplicationPackage
from jobpipe.core.io import now_iso
from jobpipe.core.primary_db import insert_generated_document


def persist_generated_package(
    conn,
    package: GeneratedApplicationPackage,
    *,
    candidate_id: str,
    evaluation_id: str | None = None,
    producer: str = "simple_agent_author",
) -> str:
    document_id = "apkg_" + hashlib.sha1(
        f"{candidate_id}|{package.job_id}|author_package_json".encode("utf-8")
    ).hexdigest()[:20]
    now = now_iso()
    insert_generated_document(
        conn,
        {
            "document_id": document_id,
            "candidate_id": candidate_id,
            "job_id": package.job_id,
            "evaluation_id": evaluation_id or "",
            "kind": "author_package_json",
            "producer": producer,
            "status": "draft",
            "storage_path": "",
            "preview_text": package.cover_letter_draft[:400],
            "document_json": package.model_dump(mode="json"),
            "created_at": now,
            "updated_at": now,
        },
    )
    return document_id
