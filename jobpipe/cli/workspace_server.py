from __future__ import annotations

import argparse
import json
import socket
import sys
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, unquote, urlparse

from jobpipe.workspace import ArtifactRunSource, ArtifactWorkspaceHub
from jobpipe.workspace.contracts import (
    ApplicationCaseReadModel,
    CaseListItem,
    WorkspaceContractError,
)

from jobpipe.workspace.supabase_cases import hub_from_env as _supabase_hub_from_env
from jobpipe.workspace.supabase_applications import from_env as _supabase_applications_from_env
from jobpipe.workspace.supabase_cover_letters import from_env as _supabase_cover_letters_from_env


# Canonical-migration: workspace_server always reads cases from Supabase
# (jobs ⨝ triage_decisions). The legacy artifact-backed code path remains
# in the repo for debug-dump consumers but is never selected at runtime.
# Run-id pinning is gone — there's only "current state".
_SUPABASE_VIRTUAL_RUN_ID = "supabase"


LIST_SCHEMA_VERSION = "jobpipe.workspace.cases.list.v1"
GET_SCHEMA_VERSION = "jobpipe.workspace.cases.get.v1"
MATERIALS_SCHEMA_VERSION = "jobpipe.workspace.materials.v1"
HEALTH_SCHEMA_VERSION = "jobpipe.workspace.health.v1"
STATE_SCHEMA_VERSION = "jobpipe.workspace.case_state.v1"
TAILORING_PLAN_SCHEMA_VERSION = "jobpipe.workspace.tailoring_plan.v1"

# Cap the write-back payload — a tailoring plan with cover letter + bullets
# fits comfortably under 64KB. Reject anything larger as a malformed request.
_TAILORING_PLAN_MAX_BYTES = 64_000

VALID_DECISION_STATUSES = frozenset(
    {"to_review", "decided_apply", "decided_skip"}
)
VALID_APPLICATION_STATUSES = frozenset(
    {
        "drafting",
        "ready",
        "applied",
        "interviewing",
        "offered",
        "accepted",
        "rejected",
        "withdrawn",
        "ghosted",
    }
)


@dataclass(frozen=True)
class WorkspaceServerConfig:
    out_root: Path
    default_run_id: str = ""
    state_root: Path | None = None


class _ExclusiveBindThreadingHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer that refuses to share its port with another process.

    By default Python's ``socketserver`` does NOT set ``SO_REUSEADDR``, but
    Windows' default socket behavior still allows a second process to bind
    to the same ``host:port`` in some configurations. The result we saw in
    Phase 5: starting a second hub on :8765 succeeded silently, both
    processes received traffic in round-robin fashion, and stale code in
    the older process produced confusing 404s.

    On Windows, ``SO_EXCLUSIVEADDRUSE`` makes the second bind fail with
    ``WinError 10048`` instead, which is the behavior we want — a second
    hub on the same port should refuse to start so the operator notices.
    On non-Windows platforms ``SO_REUSEADDR`` is left at its default
    (``False`` per Python's TCPServer), which already gives "address in
    use" for an active listener.
    """

    allow_reuse_address = False

    def server_bind(self) -> None:
        if sys.platform == "win32":
            exclusive_opt = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
            if exclusive_opt is not None:
                self.socket.setsockopt(socket.SOL_SOCKET, exclusive_opt, 1)
        super().server_bind()


def build_server(
    *,
    out_root: str | Path,
    run_id: str = "",
    host: str = "127.0.0.1",
    port: int = 8765,
    state_root: str | Path | None = None,
) -> ThreadingHTTPServer:
    """Create a local workspace cases HTTP server.

    Read-only for case artifacts (under ``out_root``). Read+write for user
    decision state (under ``state_root``), with per-case JSON records keyed
    by case id. State is global to the user — independent of which pipeline
    run surfaced the case.

    The returned server refuses to share its port with another process
    (see ``_ExclusiveBindThreadingHTTPServer``); starting a second hub on
    the same port fails fast with a clear OSError instead of silently
    racing with the existing listener.
    """

    config = WorkspaceServerConfig(
        out_root=Path(out_root),
        default_run_id=run_id,
        state_root=Path(state_root) if state_root else None,
    )

    class WorkspaceCasesHandler(BaseHTTPRequestHandler):
        server_version = "JobPipeWorkspaceCases/0.2"

        def do_GET(self) -> None:  # noqa: N802
            _handle_get(self, config)

        def do_POST(self) -> None:  # noqa: N802
            _handle_post(self, config)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            sys.stderr.write("%s - - [%s] %s\n" % (self.client_address[0], self.log_date_time_string(), format % args))

    return _ExclusiveBindThreadingHTTPServer((host, port), WorkspaceCasesHandler)


def _handle_get(handler: BaseHTTPRequestHandler, config: WorkspaceServerConfig) -> None:
    parsed = urlparse(handler.path)
    try:
        if parsed.path == "/healthz":
            _write_json(handler, HTTPStatus.OK, {"schemaVersion": HEALTH_SCHEMA_VERSION, "status": "ok"})
            return

        if parsed.path == "/cases":
            run_id, hub = _resolve_hub(config, parse_qs(parsed.query))
            cases = [_case_summary(item, hub.cases.get(item.id)) for item in hub.cases.list()]
            _write_json(
                handler,
                HTTPStatus.OK,
                {"schemaVersion": LIST_SCHEMA_VERSION, "runId": run_id, "cases": cases},
            )
            return

        if parsed.path == "/case_state":
            state = _load_state(config)
            _write_json(
                handler,
                HTTPStatus.OK,
                {
                    "schemaVersion": STATE_SCHEMA_VERSION,
                    "state": state,
                    "count": len(state),
                },
            )
            return

        if parsed.path.startswith("/cases/") and parsed.path.endswith("/tailoring_plan"):
            raw_case_id = parsed.path.removeprefix("/cases/").removesuffix("/tailoring_plan")
            case_id = unquote(raw_case_id).strip().strip("/")
            if not case_id or "/" in case_id:
                _write_error(handler, HTTPStatus.NOT_FOUND, "case_not_found", "Case not found.")
                return
            run_id, hub = _resolve_hub(config, parse_qs(parsed.query))
            plan_payload = _resolve_tailoring_plan(config, hub, case_id)
            _write_json(
                handler,
                HTTPStatus.OK,
                {
                    "schemaVersion": TAILORING_PLAN_SCHEMA_VERSION,
                    "runId": run_id,
                    "caseId": case_id,
                    "plan": plan_payload,
                },
            )
            return

        if parsed.path.startswith("/cases/") and parsed.path.endswith("/materials"):
            raw_case_id = parsed.path.removeprefix("/cases/").removesuffix("/materials")
            case_id = unquote(raw_case_id).strip().strip("/")
            if not case_id or "/" in case_id:
                _write_error(handler, HTTPStatus.NOT_FOUND, "case_not_found", "Case not found.")
                return
            run_id, hub = _resolve_hub(config, parse_qs(parsed.query))
            case = hub.cases.get(case_id)
            if case is None:
                _write_error(handler, HTTPStatus.NOT_FOUND, "case_not_found", "Case not found.")
                return
            _write_json(
                handler,
                HTTPStatus.OK,
                {
                    "schemaVersion": MATERIALS_SCHEMA_VERSION,
                    "runId": run_id,
                    "caseId": case.id,
                    **_case_materials(case),
                },
            )
            return

        if parsed.path.startswith("/cases/"):
            case_id = unquote(parsed.path.removeprefix("/cases/")).strip()
            if not case_id or "/" in case_id:
                _write_error(handler, HTTPStatus.NOT_FOUND, "case_not_found", "Case not found.")
                return
            run_id, hub = _resolve_hub(config, parse_qs(parsed.query))
            case = hub.cases.get(case_id)
            if case is None:
                _write_error(handler, HTTPStatus.NOT_FOUND, "case_not_found", "Case not found.")
                return
            _write_json(
                handler,
                HTTPStatus.OK,
                {"schemaVersion": GET_SCHEMA_VERSION, "runId": run_id, "case": _case_detail(case)},
            )
            return

        _write_error(handler, HTTPStatus.NOT_FOUND, "artifact_unavailable", "Endpoint not found.")
    except WorkspaceContractError:
        _write_error(handler, HTTPStatus.INTERNAL_SERVER_ERROR, "contract_violation", "Workspace contract violation.")
    except ValueError as exc:
        _write_error(handler, HTTPStatus.BAD_REQUEST, "invalid_config", str(exc))
    except RunNotFoundError:
        _write_error(handler, HTTPStatus.NOT_FOUND, "run_not_found", "No valid artifact run found.")
    except OSError:
        _write_error(handler, HTTPStatus.INTERNAL_SERVER_ERROR, "artifact_unavailable", "Artifact unavailable.")
    except Exception:  # pragma: no cover - defensive boundary for the local wrapper
        _write_error(handler, HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", "Internal server error.")


def _resolve_hub(
    config: WorkspaceServerConfig,
    query: dict[str, list[str]],
) -> tuple[str, Any]:
    # Canonical path: Supabase. When JOBPIPE_SUPABASE_URL/KEY are set (the
    # production default), every read goes to v_actionable_cases — current
    # state for current user. No run_id pinning, no per-request file walks.
    hub = _supabase_hub_from_env()
    if hub is not None:
        return _SUPABASE_VIRTUAL_RUN_ID, hub

    # Fallback: artifact-backed path. Kept for tests, debug runs, and any
    # pre-migration environment where Supabase env vars aren't configured.
    # Will be removed once the canonical migration has lived in production
    # for a release cycle (tracked in Phase 4 of the stitch plan —
    # docs/canonical-state-stitch-plan.md in JobDesk).
    if not config.out_root.exists() or not config.out_root.is_dir():
        raise ValueError("Configured out_root is not a directory.")

    source = ArtifactRunSource(config.out_root)
    requested_run_id = _first_query_value(query, "run_id") or config.default_run_id
    if requested_run_id:
        run_dir = source.resolve(requested_run_id)
        if run_dir is None:
            raise RunNotFoundError
        return requested_run_id, ArtifactWorkspaceHub(run_dir)

    latest = source.latest_run()
    if latest is None:
        raise RunNotFoundError
    run_dir = source.resolve(latest.id)
    if run_dir is None:
        raise RunNotFoundError
    return latest.id, ArtifactWorkspaceHub(run_dir)


class RunNotFoundError(Exception):
    pass


def _case_summary(item: CaseListItem, case: ApplicationCaseReadModel | None = None) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": item.id,
        "company": item.company,
        "role": item.role,
        "location": item.location,
        "workMode": item.work_mode.value,
        "deadline": item.deadline,
        "score": item.score,
        "recommendation": item.recommendation.value,
        "applicationStatus": item.application_status.value,
        "mainStrength": _truncate(item.main_strength),
        "mainGap": _truncate(item.main_gap),
        "tailoringEffort": item.tailoring_effort.value,
        "nextAction": item.next_action,
        "decidedAt": item.decided_at,
        "jobUpdatedAt": item.job_updated_at,
        "jobPostedAt": item.job_posted_at,
        "sourceUrl": case.source_url if case else "",
        "applicationUrl": case.application_url if case else "",
        "decisionSignalKeys": [signal.key.value for signal in case.decision_signals] if case else [],
        "artifactRefCount": len(case.artifacts) if case else 0,
    }
    if case is not None:
        # Ship rich fields in the list response too — the shortlist drawer
        # opens from list data and needs dimensions/strengths/gaps/atsKeywords/
        # summary without a second round-trip. Cost: ~3KB extra per row, ~130KB
        # total at 44 cases — fine.
        base.update({
            "summary": _truncate(case.summary, limit=500),
            "atsKeywords": case.ats_keywords,
            "decisionSignals": [
                {
                    "key": signal.key.value,
                    "label": signal.label,
                    "score": signal.score,
                    "band": signal.band,
                    "rationale": _truncate(signal.rationale, limit=240),
                    "confidence": signal.confidence,
                    "evidenceIds": signal.evidence_ids,
                    "supportingPoints": [_truncate(value) for value in signal.supporting_points[:4]],
                    "riskPoints": [_truncate(value) for value in signal.risk_points[:4]],
                }
                for signal in case.decision_signals
            ],
            "strengths": [_truncate(value) for value in case.strengths[:6]],
            "gaps": [_truncate(value) for value in case.gaps[:6]],
            "evidence": [
                {
                    "id": ref.id,
                    "label": ref.label,
                    "source": ref.source,
                    "quote": _truncate(ref.quote),
                    "confidence": ref.confidence,
                }
                for ref in case.evidence
            ],
        })
    return base


def _case_detail(case: ApplicationCaseReadModel) -> dict[str, Any]:
    return {
        "id": case.id,
        "company": case.company,
        "role": case.role,
        "location": case.location,
        "workMode": case.work_mode.value,
        "deadline": case.deadline,
        "summary": _truncate(case.summary, limit=500),
        "atsKeywords": case.ats_keywords,
        "score": case.score,
        "recommendation": case.recommendation.value,
        "applicationStatus": case.application_status.value,
        "tailoringEffort": case.tailoring_effort.value,
        "nextAction": case.next_action,
        "decidedAt": case.decided_at,
        "jobUpdatedAt": case.job_updated_at,
        "jobPostedAt": case.job_posted_at,
        "sourceUrl": case.source_url,
        "applicationUrl": case.application_url,
        "decisionSignals": [
            {
                "key": signal.key.value,
                "label": signal.label,
                "score": signal.score,
                "band": signal.band,
                "rationale": _truncate(signal.rationale, limit=240),
                "confidence": signal.confidence,
                "evidenceIds": signal.evidence_ids,
                "supportingPoints": [_truncate(value) for value in signal.supporting_points[:4]],
                "riskPoints": [_truncate(value) for value in signal.risk_points[:4]],
            }
            for signal in case.decision_signals
        ],
        "strengths": [_truncate(value) for value in case.strengths[:6]],
        "gaps": [_truncate(value) for value in case.gaps[:6]],
        "evidence": [
            {
                "id": ref.id,
                "label": ref.label,
                "source": ref.source,
                "quote": _truncate(ref.quote),
                "confidence": ref.confidence,
            }
            for ref in case.evidence
        ],
        "artifacts": [
            {
                "id": artifact.id,
                "kind": artifact.kind,
                "status": artifact.status,
                "label": artifact.label,
                "preview": _truncate(artifact.preview),
                "updatedAt": artifact.updated_at,
            }
            for artifact in case.artifacts
        ],
    }


def _case_materials(case: ApplicationCaseReadModel) -> dict[str, Any]:
    resume_refs = _matching_artifacts(
        case,
        ("resume", "cv", "reactive_resume", "pdf", "screenshot"),
    )
    value_refs = _matching_artifacts(
        case,
        ("value", "proposition", "cover_letter", "application_message"),
    )
    final_source_refs = _matching_artifacts(
        case,
        ("10_moderator", "bridge_triage_decision_v3", "bridge_triage_features"),
    )

    blockers: list[str] = []
    if not resume_refs:
        blockers.append("Resume variant artifact is not available in this run.")
    if not value_refs:
        blockers.append("Value proposition draft artifact is not available in this run.")
    if case.gaps:
        blockers.append("Open risk points should be reviewed before marking ready.")

    return {
        "resume": {
            "status": "available" if resume_refs else "missing",
            "summary": "Resume artifact is available." if resume_refs else "Resume variant is not prepared yet.",
            "artifactRefs": [_artifact_payload(ref) for ref in resume_refs],
        },
        "valueDraft": {
            "status": "available" if value_refs else "missing",
            "summary": "Value proposition draft is available."
            if value_refs
            else "Value proposition draft is not prepared yet.",
            "artifactRefs": [_artifact_payload(ref) for ref in value_refs],
        },
        "finalReadiness": {
            "status": "available" if not blockers else "blocked",
            "summary": "Ready for final review." if not blockers else "Readiness is blocked by missing downstream materials.",
            "blockers": blockers,
            "artifactRefs": [_artifact_payload(ref) for ref in final_source_refs],
        },
    }


def _matching_artifacts(
    case: ApplicationCaseReadModel,
    needles: tuple[str, ...],
) -> list[Any]:
    matches = []
    for artifact in case.artifacts:
        haystack = " ".join(
            [
                artifact.id,
                artifact.kind,
                artifact.label,
            ]
        ).lower()
        if any(needle in haystack for needle in needles):
            matches.append(artifact)
    return matches


def _artifact_payload(artifact: Any) -> dict[str, Any]:
    return {
        "id": artifact.id,
        "kind": artifact.kind,
        "status": artifact.status,
        "label": artifact.label,
    }


def _first_query_value(query: dict[str, list[str]], key: str) -> str:
    values = query.get(key) or []
    return str(values[0] if values else "").strip()


def _truncate(value: str, *, limit: int = 160) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def _handle_post(handler: BaseHTTPRequestHandler, config: WorkspaceServerConfig) -> None:
    parsed = urlparse(handler.path)
    try:
        if parsed.path.startswith("/cases/") and parsed.path.endswith("/tailoring_plan"):
            raw_case_id = parsed.path.removeprefix("/cases/").removesuffix("/tailoring_plan")
            case_id = unquote(raw_case_id).strip().strip("/")
            if not case_id or "/" in case_id:
                _write_error(handler, HTTPStatus.BAD_REQUEST, "invalid_case_id", "Case id missing or invalid.")
                return

            body = _read_post_body(handler, max_bytes=_TAILORING_PLAN_MAX_BYTES)
            if body is None:
                return

            action = body.get("action", "set")
            if action == "clear":
                _clear_tailoring_override(config, case_id)
                # After clearing, re-derive from pipeline so the caller sees what
                # JobDesk will see on its next read.
                run_id, hub = _resolve_hub(config, parse_qs(parsed.query))
                plan_payload = _resolve_tailoring_plan(config, hub, case_id)
                _write_json(
                    handler,
                    HTTPStatus.OK,
                    {
                        "schemaVersion": TAILORING_PLAN_SCHEMA_VERSION,
                        "runId": run_id,
                        "caseId": case_id,
                        "cleared": True,
                        "plan": plan_payload,
                    },
                )
                return

            try:
                _validate_tailoring_override(body)
            except ValueError as exc:
                _write_error(handler, HTTPStatus.BAD_REQUEST, "invalid_plan", str(exc))
                return

            _save_tailoring_override(config, case_id, body)
            run_id, hub = _resolve_hub(config, parse_qs(parsed.query))
            plan_payload = _resolve_tailoring_plan(config, hub, case_id)
            _write_json(
                handler,
                HTTPStatus.OK,
                {
                    "schemaVersion": TAILORING_PLAN_SCHEMA_VERSION,
                    "runId": run_id,
                    "caseId": case_id,
                    "plan": plan_payload,
                },
            )
            return

        if parsed.path.startswith("/case_state/"):
            raw_case_id = parsed.path.removeprefix("/case_state/")
            case_id = unquote(raw_case_id).strip().strip("/")
            if not case_id or "/" in case_id:
                _write_error(handler, HTTPStatus.BAD_REQUEST, "invalid_case_id", "Case id missing or invalid.")
                return

            body = _read_post_body(handler, max_bytes=64_000)
            if body is None:
                return

            action = body.get("action", "set")
            if action == "clear":
                _clear_case_state(config, case_id)
                _write_json(
                    handler,
                    HTTPStatus.OK,
                    {"schemaVersion": STATE_SCHEMA_VERSION, "caseId": case_id, "cleared": True},
                )
                return

            decision_status = body.get("decisionStatus")
            if decision_status not in VALID_DECISION_STATUSES:
                _write_error(
                    handler,
                    HTTPStatus.BAD_REQUEST,
                    "invalid_decision",
                    f"decisionStatus must be one of {sorted(VALID_DECISION_STATUSES)}.",
                )
                return

            application_status = body.get("applicationStatus")
            if application_status is not None and application_status not in VALID_APPLICATION_STATUSES:
                _write_error(
                    handler,
                    HTTPStatus.BAD_REQUEST,
                    "invalid_application_status",
                    f"applicationStatus must be one of {sorted(VALID_APPLICATION_STATUSES)} or null.",
                )
                return

            skip_reason = body.get("skipReason")
            if skip_reason is not None and not isinstance(skip_reason, str):
                _write_error(handler, HTTPStatus.BAD_REQUEST, "invalid_skip_reason", "skipReason must be a string or null.")
                return

            from datetime import datetime, timezone
            effective_app_status = (
                application_status if decision_status == "decided_apply" else None
            )
            effective_skip_reason = (
                skip_reason if decision_status == "decided_skip" else None
            )
            _persist_case_state(
                config,
                case_id,
                decision_status=decision_status,
                application_status=effective_app_status,
                skip_reason=effective_skip_reason,
            )
            entry = {
                "caseId": case_id,
                "decisionStatus": decision_status,
                "applicationStatus": effective_app_status,
                "skipReason": effective_skip_reason,
                "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            }
            _write_json(
                handler,
                HTTPStatus.OK,
                {"schemaVersion": STATE_SCHEMA_VERSION, "caseId": case_id, "entry": entry},
            )
            return

        _write_error(handler, HTTPStatus.NOT_FOUND, "endpoint_unknown", "POST endpoint not found.")
    except OSError:
        _write_error(handler, HTTPStatus.INTERNAL_SERVER_ERROR, "storage_unavailable", "State storage unavailable.")
    except Exception:  # pragma: no cover
        _write_error(handler, HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", "Internal server error.")


def _read_post_body(
    handler: BaseHTTPRequestHandler, *, max_bytes: int
) -> dict[str, Any] | None:
    """Read + parse a JSON request body, writing an error and returning ``None`` on failure.

    Shared between ``/case_state`` and ``/cases/.../tailoring_plan`` POSTs so
    body-size + JSON validation logic stays in one place.
    """

    try:
        length = int(handler.headers.get("Content-Length", "0"))
    except ValueError:
        length = 0
    if length <= 0 or length > max_bytes:
        _write_error(
            handler,
            HTTPStatus.BAD_REQUEST,
            "invalid_body",
            f"Body required and must be < {max_bytes // 1000}KB.",
        )
        return None
    try:
        raw = handler.rfile.read(length).decode("utf-8")
        body = json.loads(raw) if raw else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        _write_error(handler, HTTPStatus.BAD_REQUEST, "invalid_json", "Request body must be valid JSON.")
        return None
    if not isinstance(body, dict):
        _write_error(handler, HTTPStatus.BAD_REQUEST, "invalid_body", "Request body must be a JSON object.")
        return None
    return body


# ----- tailoring plan storage + projection ---------------------------------


def _resolve_tailoring_plan(
    config: WorkspaceServerConfig,
    hub: "ArtifactWorkspaceHub",
    case_id: str,
) -> dict[str, Any] | None:
    """Return the merged tailoring-plan payload for ``case_id``.

    Pipeline projection forms the base; a JobSane-written override (if any)
    is merged on top via shallow-merge so partial refinements work. Returns
    ``None`` when neither layer has content (i.e. case has no application_pack
    AND no JobSane write-back yet).
    """

    pipeline = hub.tailoring.get(case_id)
    pipeline_dict = pipeline.to_dict() if pipeline is not None else None
    override = _load_tailoring_override(config, case_id)

    if pipeline_dict is None and override is None:
        return None
    if override is None:
        # Pipeline-only — pipeline_dict is snake_case from to_dict(), camelize.
        return _wire_format(pipeline_dict or {})
    if pipeline_dict is None:
        # JobSane wrote a plan for a case that doesn't have a pipeline pack
        # — surface it as-is (override is already camelCase wire-shape).
        merged = dict(override)
        merged.setdefault("caseId", case_id)
        merged["source"] = "jobsane"
        return merged

    # Merge: override fields (already camelCase) win over pipeline (snake_case
    # → camelize first) where present.
    base = _wire_format(pipeline_dict)
    merged = dict(base)
    merged.update({k: v for k, v in override.items() if v is not None})
    # Source becomes "merged" when both layers contributed.
    merged["source"] = "merged"
    return merged


def _wire_format(payload: dict[str, Any]) -> dict[str, Any]:
    """Convert snake_case dataclass output to camelCase wire format.

    Mirrors the convention used by ``_case_summary`` and ``_case_detail`` so
    JobDesk consumes one consistent style across all endpoints.
    """

    return _camelize(payload)


def _camelize(value: Any) -> Any:
    if isinstance(value, dict):
        return {_to_camel(key): _camelize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_camelize(item) for item in value]
    return value


def _to_camel(key: str) -> str:
    parts = str(key).split("_")
    if len(parts) == 1:
        return parts[0]
    return parts[0] + "".join(part.title() for part in parts[1:])


def _validate_tailoring_override(body: dict[str, Any]) -> None:
    """Validate a JobSane write-back payload.

    Accepts the camelCase wire shape we emit on GET; rejects unknown top-level
    keys to keep the contract narrow. Raises ``ValueError`` on rejection.
    """

    allowed_keys = {
        "caseId",
        "source",
        "positioningAngle",
        "sectionStrategy",
        "bulletChanges",
        "keywordCoverage",
        "claimWarnings",
        "valueProposition",
        "coverLetter",
        "reactiveResumeUrl",
        "updatedAt",
        "provenance",
    }
    unknown = set(body.keys()) - allowed_keys - {"action"}
    if unknown:
        raise ValueError(f"Unknown fields in tailoring plan body: {sorted(unknown)}")

    for list_field in ("sectionStrategy", "bulletChanges", "keywordCoverage", "claimWarnings"):
        if list_field in body and not isinstance(body[list_field], list):
            raise ValueError(f"{list_field} must be a list")

    for str_field in ("positioningAngle", "reactiveResumeUrl"):
        if str_field in body and not isinstance(body[str_field], str):
            raise ValueError(f"{str_field} must be a string")

    if "valueProposition" in body and not isinstance(body["valueProposition"], (dict, type(None))):
        raise ValueError("valueProposition must be an object or null")
    if "coverLetter" in body and not isinstance(body["coverLetter"], (dict, type(None))):
        raise ValueError("coverLetter must be an object or null")


def _tailoring_dir(config: WorkspaceServerConfig) -> Path:
    """Return the per-case tailoring override directory, creating it lazily."""

    root = config.state_root or (config.out_root.parent / "case_state")
    target = root / "case_tailoring"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _tailoring_path(config: WorkspaceServerConfig, case_id: str) -> Path:
    safe = "".join(ch for ch in case_id if ch.isalnum() or ch in {"-", "_"})
    if not safe:
        raise ValueError("case_id must contain at least one alphanumeric character")
    return _tailoring_dir(config) / f"{safe}.json"


def _load_tailoring_override(
    config: WorkspaceServerConfig, case_id: str
) -> dict[str, Any] | None:
    try:
        path = _tailoring_path(config, case_id)
    except ValueError:
        return None
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _save_tailoring_override(
    config: WorkspaceServerConfig, case_id: str, body: dict[str, Any]
) -> None:
    path = _tailoring_path(config, case_id)
    # Stamp the write so consumers can tell pipeline-projected (from artifact
    # mtime) apart from JobSane-written. We don't trust client-supplied
    # updatedAt — server time is authoritative.
    from datetime import datetime, timezone

    payload = dict(body)
    payload.pop("action", None)
    payload["updatedAt"] = (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    payload.setdefault("caseId", case_id)
    payload.setdefault("source", "jobsane")

    # Canonical write: when the override includes a coverLetter, persist its
    # content to Supabase `cover_letters` table. This is the durable record
    # JobDesk's tracker reads. The file write below is kept as a debug copy
    # and as the disk fallback when Supabase isn't configured.
    cover_letter = payload.get("coverLetter")
    if isinstance(cover_letter, dict) and isinstance(cover_letter.get("text"), str):
        clcap = _supabase_cover_letters_from_env()
        if clcap is not None:
            clcap.upsert_content(
                case_id,
                content=cover_letter["text"],
                language=cover_letter.get("language") if isinstance(cover_letter.get("language"), str) else None,
                angle=cover_letter.get("angle") if isinstance(cover_letter.get("angle"), str) else None,
            )

    tmp = path.with_suffix(".json.tmp")
    blob = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
    with tmp.open("wb") as fh:
        fh.write(blob)
    tmp.replace(path)


def _clear_tailoring_override(config: WorkspaceServerConfig, case_id: str) -> None:
    try:
        path = _tailoring_path(config, case_id)
    except ValueError:
        return
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass


def _state_path(config: WorkspaceServerConfig) -> Path:
    root = config.state_root or (config.out_root.parent / "case_state")
    root.mkdir(parents=True, exist_ok=True)
    return root / "case_state.json"


def _load_state(config: WorkspaceServerConfig) -> dict[str, dict[str, Any]]:
    # Canonical: Supabase applications table. Disk fallback for tests / pre-
    # migration. See docs/canonical-state-stitch-plan.md in JobDesk.
    apps = _supabase_applications_from_env()
    if apps is not None:
        return apps.list_state()

    path = _state_path(config)
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        return {}
    return {}


def _save_state(config: WorkspaceServerConfig, state: dict[str, dict[str, Any]]) -> None:
    # File-write path. Kept as a fallback when Supabase isn't configured.
    # When Supabase IS configured, callers should use _persist_case_state
    # for per-case upserts instead — _save_state is only invoked by the
    # bulk-clear branch which is fine to keep file-only for now since
    # full-state clears are operational/debug-only.
    path = _state_path(config)
    tmp = path.with_suffix(".json.tmp")
    blob = json.dumps(state, indent=2, ensure_ascii=False).encode("utf-8")
    with tmp.open("wb") as fh:
        fh.write(blob)
    tmp.replace(path)


def _persist_case_state(
    config: WorkspaceServerConfig,
    case_id: str,
    *,
    decision_status: str,
    application_status: Optional[str],
    skip_reason: Optional[str] = None,
) -> None:
    """Upsert one case's state.

    Canonical: writes to Supabase `applications` when env is set; falls
    back to merging into the disk state JSON when not. Each branch keeps
    the same external behavior — GET /case_state returns the same shape.
    """
    apps = _supabase_applications_from_env()
    if apps is not None:
        apps.upsert_state(
            case_id,
            decision_status=decision_status,
            application_status=application_status,
            notes=skip_reason if decision_status == "decided_skip" else None,
        )
        return

    # Disk fallback (tests / pre-migration ops).
    state = _load_state(config)
    entry: dict[str, Any] = {"decisionStatus": decision_status}
    if application_status is not None:
        entry["applicationStatus"] = application_status
    if skip_reason is not None and decision_status == "decided_skip":
        entry["skipReason"] = skip_reason
    state[case_id] = entry
    _save_state(config, state)


def _clear_case_state(config: WorkspaceServerConfig, case_id: str) -> None:
    apps = _supabase_applications_from_env()
    if apps is not None:
        apps.clear_state(case_id)
        return
    state = _load_state(config)
    if case_id in state:
        del state[case_id]
        _save_state(config, state)


def _write_json(handler: BaseHTTPRequestHandler, status: HTTPStatus, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status.value)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _write_error(handler: BaseHTTPRequestHandler, status: HTTPStatus, code: str, message: str) -> None:
    try:
        _write_json(handler, status, {"error": {"code": code, "message": message}})
    except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError):
        # Client already gave up (e.g. Next.js fetch cancelled). Don't take
        # the server down for a corpse client — just drop the response.
        pass


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve ApplicationWorkspaceHub cases and case-decision state over local HTTP.")
    parser.add_argument("--out-root", required=True, help="Root containing JobPipe run directories. Used for case_state file path and as the artifact-backed fallback when JOBPIPE_SUPABASE_URL/KEY are not set (e.g. tests).")
    parser.add_argument("--run-id", default="", help="Default opaque run directory ID for the artifact-backed fallback. Ignored when Supabase env is configured (cases then come from current Supabase state, not a pinned run).")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1).")
    parser.add_argument("--port", type=int, default=8765, help="Port to bind (default: 8765).")
    parser.add_argument(
        "--state-root",
        default="",
        help="Directory for user decision state (case_state.json). Defaults to <out-root>/../case_state.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)

    # Auto-load JobPipe env so JOBPIPE_SUPABASE_URL/KEY are set even when the
    # workspace_server is spawned by an orchestrator that doesn't pre-populate
    # env. After the canonical migration these are required for /cases.
    try:
        from jobpipe.core.io import load_env_file
        # Derive from --out-root: env file sits beside the data root that
        # contains out_runs/. Resilient to whatever JOBPIPE_DATA_DIR is set to.
        env_file = Path(args.out_root).resolve().parent / ".env"
        if env_file.exists():
            load_env_file(str(env_file))
    except Exception:
        pass  # best-effort; env may already be set externally

    try:
        server = build_server(
            out_root=args.out_root,
            run_id=args.run_id,
            host=args.host,
            port=args.port,
            state_root=args.state_root or None,
        )
    except OSError as exc:
        # Most commonly: port already bound by another hub. With Phase 5's
        # SO_EXCLUSIVEADDRUSE fix the second bind fails fast — surface it
        # readably so the operator doesn't chase phantom routing bugs.
        if getattr(exc, "errno", None) in (10048, 10013, 98) or "address" in str(exc).lower():
            print(
                f"[error] Cannot bind {args.host}:{args.port} — another "
                f"workspace_server is already running on this port. Stop "
                f"it before starting a new one (or pass --port).",
                file=sys.stderr,
                flush=True,
            )
            raise SystemExit(2) from exc
        raise
    host, port = server.server_address[:2]
    print(f"Serving workspace cases on http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping workspace cases server.", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main(sys.argv[1:])
