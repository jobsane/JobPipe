"""Derived exports, dashboards, and other projection surfaces."""

from .dashboard import build_payload, export
from .jobsync import (
    build_jobsync_application_case_projection,
    build_jobsync_application_case_projections,
    build_jobsync_decision_brief,
    build_jobsync_document_refs,
    build_jobsync_job_summary,
)
from .reactive_resume import (
    build_resume_import_projection,
    build_tailored_cv_plan,
    build_tailored_cv_projection,
)
from .rr_patch import build_rr_patch

__all__ = [
    "build_payload",
    "build_jobsync_application_case_projection",
    "build_jobsync_application_case_projections",
    "build_jobsync_decision_brief",
    "build_jobsync_document_refs",
    "build_jobsync_job_summary",
    "build_resume_import_projection",
    "build_rr_patch",
    "build_tailored_cv_plan",
    "build_tailored_cv_projection",
    "export",
]
