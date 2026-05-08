"""ApplicationWorkspaceHub capability protocols."""

from __future__ import annotations

from typing import Protocol

from .contracts import ApplicationCaseReadModel, CaseListItem


class CasesCapability(Protocol):
    """Read-only JobDesk-facing case capability."""

    def list(self, candidate_id: str = "default") -> list[CaseListItem]:
        """Return the case queue for one candidate."""

    def get(self, case_id: str, candidate_id: str = "default") -> ApplicationCaseReadModel | None:
        """Return one case, or None when the case is not available."""


class ApplicationWorkspaceHub(Protocol):
    """Backend hub contract exposed to future API/MCP wrappers."""

    @property
    def cases(self) -> CasesCapability:
        """Read-only case capability."""


__all__ = ["ApplicationWorkspaceHub", "CasesCapability"]

