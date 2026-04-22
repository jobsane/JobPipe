from __future__ import annotations

from pydantic import BaseModel, Field


class JobPipeState(BaseModel):
    # Input
    job_id: str = ""
    job_data: dict = Field(default_factory=dict)
    suggested_by_platform: bool = False

    # Triage
    semantic_score: float = 0.0
    decision: str = ""
    score: float = 0.0
    decision_brief: dict = Field(default_factory=dict)

    # Authoring
    authoring_context: dict = Field(default_factory=dict)
    package: dict = Field(default_factory=dict)

    # Persistence
    document_id: str = ""
    exported: bool = False

    # Audit
    errors: list[str] = Field(default_factory=list)
