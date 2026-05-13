from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from jobpipe.core.paths import JobPipePaths
from jobpipe.core.profile_layer import load_persisted_profile_layer

SETTINGS_SCHEMA_VERSION = "jobpipe.settings.v1"


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _clean_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "on"}


def _blank_state() -> Dict[str, Any]:
    return {
        "schema_version": SETTINGS_SCHEMA_VERSION,
        "updated_at": "",
        "targeting": {
            "primary_roles_text": "",
            "secondary_roles_text": "",
            "stepping_stone_roles_text": "",
            "geography_text": "",
            "domain_focus_text": "",
        },
        "integrations": {
            "reactive_resume": {
                "enabled": False,
                "base_url": "http://localhost:3000",
            },
            "document_workspace": {
                "enabled": False,
                "base_url": "",
            },
            "gmail": {
                "status_detection_enabled": False,
                "lead_intake_enabled": False,
            },
        },
    }


def _sanitize_state(raw: Dict[str, Any]) -> Dict[str, Any]:
    state = _blank_state()
    targeting = raw.get("targeting", {}) if isinstance(raw.get("targeting"), dict) else {}
    integrations = raw.get("integrations", {}) if isinstance(raw.get("integrations"), dict) else {}

    state["updated_at"] = _clean_text(raw.get("updated_at"))
    state["targeting"] = {
        "primary_roles_text": _clean_text(targeting.get("primary_roles_text")),
        "secondary_roles_text": _clean_text(targeting.get("secondary_roles_text")),
        "stepping_stone_roles_text": _clean_text(targeting.get("stepping_stone_roles_text")),
        "geography_text": _clean_text(targeting.get("geography_text")),
        "domain_focus_text": _clean_text(targeting.get("domain_focus_text")),
    }
    reactive_resume = integrations.get("reactive_resume", {}) if isinstance(integrations.get("reactive_resume"), dict) else {}
    document_workspace = integrations.get("document_workspace", {}) if isinstance(integrations.get("document_workspace"), dict) else {}
    gmail = integrations.get("gmail", {}) if isinstance(integrations.get("gmail"), dict) else {}
    state["integrations"] = {
        "reactive_resume": {
            "enabled": _clean_bool(reactive_resume.get("enabled")),
            "base_url": _clean_text(reactive_resume.get("base_url")) or "http://localhost:3000",
        },
        "document_workspace": {
            "enabled": _clean_bool(document_workspace.get("enabled")),
            "base_url": _clean_text(document_workspace.get("base_url")),
        },
        "gmail": {
            "status_detection_enabled": _clean_bool(gmail.get("status_detection_enabled")),
            "lead_intake_enabled": _clean_bool(gmail.get("lead_intake_enabled")),
        },
    }
    return state


def load_settings_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return _blank_state()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _blank_state()
    if not isinstance(raw, dict):
        return _blank_state()
    return _sanitize_state(raw)


def persist_settings_state(path: Path, payload: Dict[str, Any]) -> Dict[str, Any]:
    current = load_settings_state(path)
    incoming_integrations = payload.get("integrations", {}) if isinstance(payload.get("integrations"), dict) else {}
    incoming_reactive = incoming_integrations.get("reactive_resume", {}) if isinstance(incoming_integrations.get("reactive_resume"), dict) else {}
    incoming_document_workspace = incoming_integrations.get("document_workspace", {}) if isinstance(incoming_integrations.get("document_workspace"), dict) else {}
    incoming_gmail = incoming_integrations.get("gmail", {}) if isinstance(incoming_integrations.get("gmail"), dict) else {}
    merged = {
        "schema_version": SETTINGS_SCHEMA_VERSION,
        "updated_at": _utc_now_z(),
        "targeting": {
            **current.get("targeting", {}),
            **(payload.get("targeting", {}) if isinstance(payload.get("targeting"), dict) else {}),
        },
        "integrations": {
            "reactive_resume": {
                **((current.get("integrations", {}) or {}).get("reactive_resume", {})),
                **incoming_reactive,
            },
            "document_workspace": {
                **((current.get("integrations", {}) or {}).get("document_workspace", {})),
                **incoming_document_workspace,
            },
            "gmail": {
                **((current.get("integrations", {}) or {}).get("gmail", {})),
                **incoming_gmail,
            },
        },
    }
    clean = _sanitize_state(merged)
    clean["updated_at"] = merged["updated_at"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    return clean


def read_env_map(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    values: Dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _status_label(*, enabled: bool, ready: bool, partial: bool) -> str:
    if not enabled:
        return "disabled"
    if ready:
        return "ready"
    if partial:
        return "partial"
    return "missing"


def _profile_defaults_from_projection(paths: JobPipePaths) -> Dict[str, Any]:
    layer = load_persisted_profile_layer(paths.profile_layer_state_path)
    if layer is None:
        return {}
    return {
        "primary_roles": list(layer.target_roles.get("primary", [])),
        "secondary_roles": list(layer.target_roles.get("secondary", [])),
        "stepping_stone_roles": list(layer.target_roles.get("stepping_stone", [])),
        "geography": list(layer.target_geography.get("locations", [])),
        "remote_policy": str(layer.target_geography.get("remote_policy") or ""),
        "preferred_domains": list(layer.targeting_profile.preferred_domains),
        "target_title_patterns": list(layer.targeting_profile.target_title_patterns),
        "connector_policies": dict(layer.targeting_profile.connector_policies),
        "profile_snapshot_id": layer.profile_snapshot.profile_snapshot_id,
        "profile_source_hash": layer.source_hash,
    }


def _profile_defaults_from_payload(profile: Dict[str, Any]) -> Dict[str, Any]:
    target_roles = profile.get("target_roles", {}) if isinstance(profile.get("target_roles"), dict) else {}
    target_geography = profile.get("target_geography", {}) if isinstance(profile.get("target_geography"), dict) else {}
    derived = profile.get("derived", {}) if isinstance(profile.get("derived"), dict) else {}
    targeting_profile = (
        derived.get("targeting_profile", {})
        if isinstance(derived.get("targeting_profile"), dict)
        else {}
    )
    profile_snapshot = (
        derived.get("profile_snapshot", {})
        if isinstance(derived.get("profile_snapshot"), dict)
        else {}
    )
    return {
        "primary_roles": target_roles.get("primary", []),
        "secondary_roles": target_roles.get("secondary", []),
        "stepping_stone_roles": target_roles.get("stepping_stone", []),
        "geography": target_geography.get("locations", []),
        "remote_policy": target_geography.get("remote_policy", ""),
        "preferred_domains": targeting_profile.get("preferred_domains", []),
        "target_title_patterns": targeting_profile.get("target_title_patterns", []),
        "connector_policies": targeting_profile.get("connector_policies", {}),
        "profile_snapshot_id": profile_snapshot.get("profile_snapshot_id", ""),
        "profile_source_hash": derived.get("source_hash", ""),
    }


def build_settings_payload(
    *,
    paths: JobPipePaths,
    profile: Dict[str, Any],
    settings_path: Path | None = None,
) -> Dict[str, Any]:
    state_path = settings_path or paths.settings_state_path
    state = load_settings_state(state_path)
    env = read_env_map(paths.env_file)

    gmail_credentials_present = paths.gmail_credentials_path.exists()
    gmail_token_present = paths.gmail_token_path.exists()
    openai_present = bool(env.get("OPENAI_API_KEY"))

    reactive_state = state["integrations"]["reactive_resume"]
    reactive_enabled = bool(reactive_state["enabled"])
    reactive_base_url = reactive_state["base_url"]
    reactive_ready = bool(reactive_enabled and reactive_base_url)
    reactive_partial = bool(reactive_enabled and reactive_base_url)

    document_workspace_state = state["integrations"]["document_workspace"]
    document_workspace_enabled = bool(document_workspace_state["enabled"])
    document_workspace_base_url = document_workspace_state["base_url"]
    document_workspace_ready = bool(document_workspace_enabled and document_workspace_base_url)
    document_workspace_partial = bool(document_workspace_enabled and document_workspace_base_url)

    gmail_state = state["integrations"]["gmail"]
    gmail_enabled = bool(gmail_state["status_detection_enabled"] or gmail_state["lead_intake_enabled"])
    gmail_ready = bool(gmail_enabled and gmail_credentials_present and gmail_token_present)
    gmail_partial = bool(gmail_enabled and (gmail_credentials_present or gmail_token_present))

    profile_defaults = _profile_defaults_from_projection(paths) or _profile_defaults_from_payload(profile)

    return {
        "schema_version": SETTINGS_SCHEMA_VERSION,
        "state_path": str(state_path),
        "updated_at": state.get("updated_at", ""),
        "targeting": {
            **state["targeting"],
            "profile_defaults": profile_defaults,
        },
        "integrations": {
            "reactive_resume": {
                "enabled": reactive_enabled,
                "base_url": reactive_base_url,
                "status": _status_label(enabled=reactive_enabled, ready=reactive_ready, partial=reactive_partial),
            },
            "document_workspace": {
                "enabled": document_workspace_enabled,
                "base_url": document_workspace_base_url,
                "status": _status_label(
                    enabled=document_workspace_enabled,
                    ready=document_workspace_ready,
                    partial=document_workspace_partial,
                ),
            },
            "gmail": {
                "status_detection_enabled": bool(gmail_state["status_detection_enabled"]),
                "lead_intake_enabled": bool(gmail_state["lead_intake_enabled"]),
                "credentials_present": gmail_credentials_present,
                "token_present": gmail_token_present,
                "credentials_path": str(paths.gmail_credentials_path),
                "token_path": str(paths.gmail_token_path),
                "status": _status_label(enabled=gmail_enabled, ready=gmail_ready, partial=gmail_partial),
                "lead_target_path": str(paths.jobs_delta_path),
                "status_target_path": str(paths.application_state_path),
                "lead_flow": "pre_triage_lead_connector",
                "status_flow": "application_state_updates",
            },
        },
        "secrets": {
            "openai_api_key_present": openai_present,
        },
        "paths": {
            "data_root": str(paths.data_root),
            "env_file": str(paths.env_file),
            "profile_pack": str(paths.profile_pack_path),
            "resume_json": str(paths.resume_json_path),
            "profile_layer_state": str(paths.profile_layer_state_path),
            "gmail_credentials": str(paths.gmail_credentials_path),
            "gmail_token": str(paths.gmail_token_path),
        },
    }
