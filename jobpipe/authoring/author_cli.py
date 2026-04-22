from __future__ import annotations

import argparse
import sys
from pathlib import Path

from jobpipe.authoring.case_context import AuthoringCaseContext
from jobpipe.authoring.persist import persist_generated_package
from jobpipe.authoring.simple_agent_author import SimpleAgentAuthor
from jobpipe.authoring.smoke_cli import build_context_for_job
from jobpipe.authoring.validation import validate_authoring_context
from jobpipe.core.primary_db import connect_primary_db
from jobpipe.runtime.paths import primary_db_path


def add_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("--job", required=True, help="job_id to author package for")
    p.add_argument("--model", default="gpt-4o-mini", help="Model passed to SimpleAgentAuthor")
    p.add_argument("--no-persist", action="store_true", default=False, help="Skip DB write and print JSON only")
    p.add_argument(
        "--validate",
        action="store_true",
        default=False,
        help="Validate the AuthoringCaseContext before generation",
    )
    p.add_argument(
        "--author",
        default="simple",
        choices=["simple", "crew" + "ai"],
        help="Author implementation (default: simple)",
    )


def _load_context_for_job(job_id: str) -> AuthoringCaseContext:
    return build_context_for_job(
        artifacts_root=Path("artifacts"),
        run_id=None,
        job_id=job_id,
        candidate_id=None,
    )


def _print_validation_result(result) -> None:
    summary = (
        f"[validate] passed={result.passed}"
        f"  score={result.score:.2f}"
        f"  failures={len(result.failures)}"
        f"  warnings={len(result.warnings)}"
    )
    print(summary, file=sys.stderr)
    for failure in result.failures:
        print(f"  FAIL: {failure}", file=sys.stderr)
    for warning in result.warnings:
        print(f"  WARN: {warning}", file=sys.stderr)


def _run(args: argparse.Namespace) -> int:
    ctx = _load_context_for_job(args.job)
    if args.validate:
        validation = validate_authoring_context(ctx)
        _print_validation_result(validation)
        if not validation.passed:
            return 2

    from jobpipe.authoring.author_factory import build_author
    author = build_author(name=getattr(args, "author", "simple"), model=args.model)
    package = author.generate(ctx)

    should_persist = not args.no_persist
    if should_persist:
        conn = connect_primary_db(primary_db_path())
        try:
            persist_generated_package(
                conn,
                package,
                candidate_id=ctx.candidate_id,
                evaluation_id=ctx.evaluation_id,
            )
            conn.commit()
        finally:
            conn.close()

    print(
        f"[author-package] job_id={package.job_id} "
        f"cover_letter_len={len(package.cover_letter_draft)} "
        f"persist={should_persist}",
        file=sys.stderr,
    )
    sys.stdout.write(package.model_dump_json(indent=2))
    sys.stdout.write("\n")
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="jobpipe author-package",
        description="Generate an application authoring package for one job.",
    )
    add_arguments(parser)
    args = parser.parse_args(argv)
    raise SystemExit(_run(args))


if __name__ == "__main__":
    main()
