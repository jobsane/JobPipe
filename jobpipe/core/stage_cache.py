from __future__ import annotations

import hashlib
import json
import os
from typing import Any


def stable_payload_hash(payload: Any) -> str:
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def artifact_meta_path(artifact_path: str) -> str:
    return f"{artifact_path}.meta.json"


def read_artifact_cache_key(artifact_path: str) -> str | None:
    meta_path = artifact_meta_path(artifact_path)
    if not os.path.exists(meta_path):
        return None
    try:
        with open(meta_path, encoding="utf-8") as fh:
            payload = json.load(fh)
    except Exception:
        return None
    value = payload.get("cache_key")
    return value if isinstance(value, str) and value else None


def write_artifact_cache_key(artifact_path: str, cache_key: str) -> None:
    meta_path = artifact_meta_path(artifact_path)
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump({"cache_key": cache_key}, fh, ensure_ascii=False, indent=2)
