from __future__ import annotations

import json
from pathlib import Path

from crewai.flow.flow import Flow, listen, or_, router, start

from jobpipe_crewai.crew import build_authoring_crew
from jobpipe_crewai.state import JobPipeState


def get_primary_db_conn():
    from jobpipe.core.primary_db import connect_primary_db
    from jobpipe.runtime.paths import primary_db_path

    return connect_primary_db(primary_db_path())


class JobPipeAuthoringFlow(Flow[JobPipeState]):
    """
    Post-triage authoring flow. Assumes jobpipe run (triage pipeline) has
    already executed and written artifacts for the given job_id.
    Scope: decision routing -> context loading -> Author+Critic crew -> persist.
    Full pipeline integration (triage -> authoring) is Sprint 4.
    """

    def __init__(self, job_id: str, model: str = "gpt-4o-mini"):
        super().__init__()
        self.state.job_id = job_id
        self._model = model

    @start()
    def load_decision_step(self):
        """Load job record and triage decision from primary DB."""
        conn = get_primary_db_conn()
        row = conn.execute(
            "SELECT * FROM jobs WHERE job_id = ?", (self.state.job_id,)
        ).fetchone()
        conn.close()
        if not row:
            self.state.errors.append(f"job_id {self.state.job_id} not found in DB")
            return
        self.state.job_data = dict(row)
        self.state.decision = str(self.state.job_data.get("decision") or "")
        self.state.suggested_by_platform = bool(
            self.state.job_data.get("suggested_by_platform", False)
        )

    @router(load_decision_step)
    def route_decision(self):
        if self.state.errors:
            return "done"
        if self.state.decision in ("APPLY_STRONGLY", "APPLY"):
            return "apply"
        if self.state.decision == "REVIEW":
            return "queue"
        return "done"

    @listen("apply")
    def build_context_step(self):
        """
        Load AuthoringCaseContext from triage artifacts.
        Uses the existing build_context_for_job helper which knows the
        artifact directory layout and constructs the full context object.
        """
        from jobpipe.authoring.smoke_cli import build_context_for_job

        ctx = build_context_for_job(
            artifacts_root=Path("artifacts"),
            run_id=None,
            job_id=self.state.job_id,
            candidate_id=None,
        )
        try:
            self.state.authoring_context = ctx.model_dump()
        except AttributeError:
            import dataclasses

            self.state.authoring_context = dataclasses.asdict(ctx)

    @listen("apply")
    def author_crew_step(self):
        """Author + Critic crew - the one step that earns autonomous collaboration."""
        crew = build_authoring_crew(self.state.authoring_context, self._model)
        result = crew.kickoff()
        raw = str(result) if result else ""
        try:
            self.state.package = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            self.state.package = {"cover_letter_draft": raw}
            self.state.errors.append("author crew output was not valid JSON")

    @listen("apply")
    def persist_step(self):
        from jobpipe.authoring.output_models import GeneratedApplicationPackage
        from jobpipe.authoring.persist import persist_generated_package

        pkg = GeneratedApplicationPackage(
            job_id=self.state.job_id,
            cover_letter_draft=self.state.package.get("cover_letter_draft", ""),
            tailored_cv_projection=self.state.package.get("tailored_cv_projection", {}),
            evidence_refs=self.state.package.get("evidence_refs", []),
            gap_notes=self.state.package.get("gap_notes", []),
        )
        conn = get_primary_db_conn()
        self.state.document_id = persist_generated_package(
            conn,
            pkg,
            candidate_id=self.state.authoring_context.get("candidate_id", "default"),
        )
        conn.commit()
        conn.close()

    @listen(or_("queue", "done"))
    def finalize_step(self):
        pass


def run_authoring_flow(job_id: str, model: str = "gpt-4o-mini") -> JobPipeState:
    flow = JobPipeAuthoringFlow(job_id=job_id, model=model)
    flow.kickoff()
    return JobPipeState.model_validate(flow.state.model_dump())
