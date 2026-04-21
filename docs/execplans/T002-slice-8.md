# T002 Slice 8 — persist_generated_package + author-package CLI

**Written:** 2026-04-22  
**Issues:** #64 (persist_generated_package), #75 (author-package CLI), #77 (end-to-end smoke test)  
**Branch:** `codex/T002-authoring-mvp`  
**Base:** `origin/main` (post-PR-#100, commit e73b001)  
**Governing spec:** `specs/ai-document-authoring-mvp-workflow-2026-04-21.md`

---

## Goal

Add persistence for `GeneratedApplicationPackage` to the primary DB, and a
`jobpipe author-package --job <id>` CLI command that calls
`SimpleAgentAuthor.generate()` end-to-end and saves the result. This is the
Sprint 2 exit slice. After this, `jobpipe author-package --job <id>` runs
against a real job and produces a structurally valid `GeneratedApplicationPackage`
stored in the DB.

No crewAI. No changes to existing models.

---

## Files to create / touch

| Path | Action |
|---|---|
| `jobpipe/authoring/persist.py` | CREATE — `persist_generated_package()` |
| `jobpipe/authoring/author_cli.py` | CREATE — `author-package` CLI handler |
| `jobpipe/cli/main.py` | MODIFY — register `author-package` subcommand |
| `tests/test_author_persist.py` | CREATE — persist tests (in-memory SQLite) |
| `tests/test_author_cli.py` | CREATE — CLI tests (monkeypatched) |

No other files may be touched.

---

## Signatures Block (verified against `origin/main` @ `e73b001`)

```python
# jobpipe/authoring/output_models.py
class GeneratedApplicationPackage(BaseModel):
    job_id: str
    cover_letter_draft: str
    tailored_cv_projection: dict
    evidence_refs: list[dict]
    gap_notes: list[str]
    validation: dict | None = None

# jobpipe/authoring/adapter.py
class AuthorAdapter(Protocol):
    def generate(self, ctx: AuthoringCaseContext) -> GeneratedApplicationPackage: ...

# jobpipe/authoring/simple_agent_author.py
class SimpleAgentAuthor:
    def __init__(self, model: str = "gpt-4o-mini") -> None: ...
    def generate(self, ctx: AuthoringCaseContext) -> GeneratedApplicationPackage: ...

# jobpipe/core/primary_db.py — existing insert helper
def insert_generated_document(conn, row: dict) -> None: ...

# jobpipe/cli/main.py — existing pattern (from Slice 4 / smoke_cli)
# subcommands are registered via subparsers.add_parser() + set_defaults(func=...)
# look at the existing build-authoring-context registration for the exact pattern

# jobpipe/authoring/smoke_cli.py — existing pattern
def add_arguments(p: argparse.ArgumentParser) -> None: ...
def _run(args: argparse.Namespace) -> int: ...
```

**Step 0 check:** before writing any code, grep `origin/main` for:
- `insert_generated_document` in `jobpipe/core/primary_db.py` — confirm signature
- `add_parser` calls in `jobpipe/cli/main.py` — confirm registration pattern
- `build-authoring-context` registration in `jobpipe/cli/main.py` — copy pattern exactly

---

## Implementation spec

### `jobpipe/authoring/persist.py`

```python
def persist_generated_package(
    conn,                              # sqlite3 connection (caller opens/closes)
    package: GeneratedApplicationPackage,
    *,
    candidate_id: str,
    evaluation_id: str | None = None,
    producer: str = "simple_agent_author",
) -> str:                              # returns document_id
```

- Calls `insert_generated_document(conn, row)` with kind `"author_package_json"`.
- `document_id`: `"apkg_" + sha1(f"{candidate_id}|{package.job_id}|author_package_json")[:20]`
- `preview_text`: first 400 chars of `package.cover_letter_draft`
- `document_json`: `package.model_dump(mode="json")`
- `status`: `"draft"`
- `created_at` / `updated_at`: `now_iso()` from `jobpipe.core.io`
- Returns `document_id`.

### `jobpipe/authoring/author_cli.py`

CLI entry point for `jobpipe author-package --job <id>`.

Arguments:
- `--job` (required) — job_id string
- `--model` (default `"gpt-4o-mini"`) — model passed to SimpleAgentAuthor
- `--no-persist` (store_true, default False) — skip DB write, print JSON only
- `--validate` (store_true, default False) — run validate_authoring_context on ctx before generation; exit 2 if not passed

Flow:
1. Load `AuthoringCaseContext` for the given job_id using the same helper as smoke_cli (`_build_application_pack_contexts` + `build_authoring_case_context`).
2. If `--validate`: call `validate_authoring_context(ctx)`; print result to stderr; exit 2 if not passed.
3. Instantiate `SimpleAgentAuthor(model=args.model)`.
4. Call `author.generate(ctx)` → `package`.
5. If not `--no-persist`: open primary DB, call `persist_generated_package(conn, package, candidate_id=..., evaluation_id=...)`, commit, close.
6. Print `package.model_dump_json(indent=2)` to stdout.
7. Return 0 on success.

Print a one-line summary to stderr: `[author-package] job_id=<id> cover_letter_len=<n> persist=<True|False>`

### `jobpipe/cli/main.py` modification

Register `author-package` subcommand using the same pattern as `build-authoring-context`. Import from `jobpipe.authoring.author_cli` and call `add_arguments` / set `_run` as the handler.

---

## Validation commands

```
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_author_persist.py tests/test_author_cli.py -v -p no:debugging -p no:cacheprovider --basetemp .pytest-tmp
python compile_check.py
python -c "from jobpipe.authoring.persist import persist_generated_package; from jobpipe.authoring.author_cli import add_arguments; print('import ok')"
python -m jobpipe author-package --help
```

All tests must pass. compile_check must pass. `--help` must show `--job`, `--model`, `--no-persist`, `--validate`.

---

## Test spec

### `tests/test_author_persist.py` (5 tests, in-memory SQLite)

Use `sqlite3.connect(":memory:")` and apply schema migration for `generated_documents` table (look at how `test_authoring_smoke_cli.py` or `test_inspect_primary_db_claims.py` set up test DBs — copy that pattern).

1. `test_persist_returns_document_id` — persist a package, assert doc_id starts with "apkg_"
2. `test_persist_inserts_row` — after persist, SELECT from generated_documents by job_id, assert 1 row
3. `test_persist_kind_is_author_package_json` — row kind == "author_package_json"
4. `test_persist_document_json_roundtrip` — row document_json contains cover_letter_draft matching input
5. `test_persist_no_crewai` — scan persist.py for "crewai"; assert not found

### `tests/test_author_cli.py` (5 tests, monkeypatched)

Monkeypatch targets: `jobpipe.authoring.author_cli.SimpleAgentAuthor`, `jobpipe.authoring.author_cli.persist_generated_package`, `jobpipe.authoring.author_cli._load_context_for_job` (or whichever internal loader is used).

1. `test_author_cli_help` — `python -m jobpipe author-package --help` exits 0
2. `test_author_cli_no_persist_prints_json` — monkeypatch generate, run with --no-persist, assert stdout is valid JSON with job_id
3. `test_author_cli_persist_called` — monkeypatch persist, assert it is called once without --no-persist
4. `test_author_cli_validate_fails_exits_2` — monkeypatch validate to return failed result, assert exit code 2
5. `test_author_cli_no_crewai` — scan author_cli.py for "crewai"; assert not found

---

## Sprint 2 exit criteria (check all before handing back)

After this slice merges, the full Sprint 2 exit test is:

```
python -m jobpipe author-package --job <any_valid_job_id> --no-persist
```

Must produce valid JSON with `job_id`, `cover_letter_draft` (non-empty string), `tailored_cv_projection` (dict), `evidence_refs` (list), `gap_notes` (list). Report whether this ran successfully.

---

## Acceptance criteria (13 items)

1. `persist.py` exists with `persist_generated_package(conn, package, *, candidate_id, evaluation_id, producer)`.
2. `persist_generated_package` calls `insert_generated_document` with kind `"author_package_json"`.
3. `persist_generated_package` returns a `document_id` string prefixed `"apkg_"`.
4. `author_cli.py` exists with `add_arguments(p)` and `_run(args) -> int`.
5. `author-package` subcommand registered in `jobpipe/cli/main.py`.
6. `--job`, `--model`, `--no-persist`, `--validate` flags present; `--help` shows all four.
7. `--validate` exits 2 when `validate_authoring_context` returns `passed=False`.
8. `--no-persist` skips DB write and prints JSON to stdout.
9. All 5 tests in `test_author_persist.py` pass.
10. All 5 tests in `test_author_cli.py` pass.
11. `compile_check.py` passes (no syntax errors).
12. No `crewai`, `autogen`, or `langchain` import in any new file or test.
13. Sprint 2 exit test (`author-package --job <id> --no-persist`) runs and prints valid JSON.

---

## No-go list

- Do not import crewai, autogen, or langchain anywhere.
- Do not edit files outside the five listed above.
- Do not add new fields to `GeneratedApplicationPackage` or `AuthoringCaseContext`.
- Do not change `SimpleAgentAuthor` or `AuthorAdapter` (those are Slice 7).
- Do not add Supabase, hosted shell, or remote persistence (#82–#89 are parked).

---

## Escalation gates

Stop and ask the coordinator before:
- Any crewai/autogen/langchain import.
- Any signature mismatch at Step 0 (insert_generated_document or main.py pattern).
- Any file touch outside the five listed files.
- Any change to Sprint 1 contract models.
