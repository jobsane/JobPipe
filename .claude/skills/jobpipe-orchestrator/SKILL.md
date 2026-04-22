---
name: jobpipe-orchestrator
description: >
  Session-start skill for the JobPipe orchestrator. Use this at the beginning
  of every JobPipe coordination session, or any time the user asks to "check
  state", "check git", "what's the status", "are tasks up to date", "check
  everything", "is stage clean", "bring me up to speed", or "sync up". Also
  use whenever handing off to Codex, reviewing a PR, or closing a sprint — any
  moment where you need a reliable picture of the current repo and project state
  before making a decision. Reads the canonical docs spine, checks all three git
  worktrees via PowerShell, checks open PRs, checks Project #6, and produces a
  structured status report with prioritised action items.
---

# JobPipe Orchestrator — Session Start

You are the coordinator/planner for JobPipe. Your role is to read, orient, route,
and review — not to implement code. All implementation goes to Codex.

## Step 1 — Read the canonical docs spine

Read these files in order before doing anything else. They are the source of truth
for product direction, workflow rules, and live task state.

```
1. CLAUDE.md                          (role + escalation gates)
2. MASTER_PLAN.md                     (canonical product thesis + invariants)
3. PRODUCT_VISION.md                  (product thesis + wedge framing)
4. ROADMAP.md                         (execution sequence)
5. OSS_SCOPE.md                       (public repo boundary)
6. DEPENDENCY_POLICY.md               (license + dependency rules)
7. docs/ai-playbook.md                (workflow rules, routing schema, approval gates)
8. docs/current-state.json            (live task state, branches, risks, blockers)
9. docs/execplans/<active>.md         (active sprint execplan — check current_slice in current-state.json)
```

If docs and code disagree, call out the mismatch rather than routing around it.

## Step 2 — Check git state across all three worktrees

Use Desktop Commander (`mcp__Desktop_Commander__start_process`) to run PowerShell.
Run all three worktree checks in a single command:

```powershell
git -C C:\Users\larsv\Jobpipe-orchestrator-v2 status --short
echo "---ORCH-BRANCH---"
git -C C:\Users\larsv\Jobpipe-orchestrator-v2 branch --show-current
echo "---CODEX---"
git -C C:\Users\larsv\Jobpipe-codex-v2 status --short
echo "---CODEX-BRANCH---"
git -C C:\Users\larsv\Jobpipe-codex-v2 branch --show-current
echo "---CLAUDE---"
git -C C:\Users\larsv\Jobpipe-claude-v2 status --short
echo "---CLAUDE-BRANCH---"
git -C C:\Users\larsv\Jobpipe-claude-v2 branch --show-current
```

**Interpret the output:**

| Symbol | Meaning |
|---|---|
| `M <file>` | Modified, not yet committed |
| `?? <file>` | Untracked — check if it belongs in git or is a stale helper |
| Clean output | Worktree is committed and up to date |

**What "clean" looks like per worktree:**
- **Orchestrator** (`ops/orchestrator-v2`): only `docs/` and `specs/` files; no `.bat`, `.py` helper scripts, no `*.json.restored`
- **Codex** (`codex/T002-*`): only the slice's implementation files; no diagnostic `.bat`, `smoke_*.py`, `check_*.bat`, or `get_*.bat` files
- **Claude** (`claude/T002-*` or idle): `.claude/settings.json` and `.mcp.example.json` changes are expected and can be committed or ignored depending on intent

**Common issues to flag:**
- `docs/current-state.json` modified but not committed → commit to orchestrator before handing off
- Codex branch doesn't match `implementation_branch` in `current-state.json` → note the mismatch
- Many `??` untracked helper scripts → stale diagnostics from prior sessions, safe to ignore but don't stage them
- `.pytest-tmp/` permission denied warnings → harmless, ignore

## Step 3 — Check open PRs and Project #6

Run via Desktop Commander:

```powershell
gh -R larsvaerland/Jobpipe pr list --state open
echo "---PROJECT---"
gh project item-list 6 --owner larsvaerland --limit 30
```

**Interpret PRs:**
- Any PR on `codex/*` branch that is OPEN → likely ready for review or merge
- Any PR on `ops/orchestrator-v2` → orchestrator housekeeping, check if stale
- PR older than 2 days with no activity → flag as potentially forgotten

**Interpret Project #6:**
- The list shows Initiative → Epic → Feature → Story → Task hierarchy
- Sprint execution items (e.g., `T002 S4-A`) appear as DraftIssues near the end of the list — use `--limit 50` if they're not visible
- Items the orchestrator creates during session should be marked Done after the corresponding PR merges

## Step 4 — Produce the status report

Synthesise everything into this structure:

```
## JobPipe State — <date>

### Docs spine
<one line per file: Current | Stale | Missing — note anything surprising>

### Open PRs
<table: PR # | Title | Branch | Status | Age | Action needed>

### Git stage
<table: Worktree | Branch | Status | Issues>

### Project #6
<note any items that are In Progress or stale — don't enumerate the whole backlog>

### Active sprint
<current_slice from current-state.json, what's blocked, what's next>

### Action items (prioritised)
1. <highest-urgency action>
2. ...
```

Keep the report tight. One paragraph of context at the top if something non-obvious is happening.

## Step 5 — Identify the next coordinator action

After the report, state one of:

- **Hand to Codex** — paste the Codex prompt (already in execplan) and note pre-stage commands
- **Merge a PR** — tell Lars which PR and why now
- **Commit orchestrator state** — give the exact `git add` + `git commit` command
- **Escalate** — something needs a founder decision before proceeding
- **No action needed** — everything is clean and in progress

Use the coordinator output schema from `docs/ai-playbook.md` for any routing turn:

```
TASK CLASSIFICATION:
GITHUB PROJECT ITEM STATUS:
CHOSEN WORKER:
BRANCH NAME:
ONE-STEP OBJECTIVE:
APPROVAL STATUS:
EXACT WORKER PROMPT:  (or "see execplan <path>")
```

## Architecture invariants — never violate

These are hard constraints to check against before routing any work:

- `import crewai` / `from crewai` must never appear inside `jobpipe/` — only inside `jobpipe_crewai/`
- Two Python environments: `jobpipe/` → Python 3.14 main venv; `jobpipe_crewai/` → `C:\Users\larsv\envs\crewai-env` (Python 3.12)
- DB API: `connect_primary_db(path)` from `jobpipe.core.primary_db` — `get_primary_db_conn()` does not exist
- PRs target `main` — never `codex/job-catalog-foundation*` (retired)
- `scripts/flow_author.py` must never be imported from `jobpipe/` or added to `MODULE_COMMANDS`

## Escalation gates — always stop and ask Lars before

- DB schema migration (current version: check `docs/current-state.json`)
- Auth, billing, deployment, secrets
- Changes to `GeneratedApplicationPackage`, `AuthoringCaseContext`, or `AuthorAdapter` contracts
- Any crewai/autogen/langchain import entering `jobpipe/`
- Destructive git ops on `main`
- OSS/Workbench boundary changes

## Worktree paths (reference)

| Worktree | Path | Branch pattern | Role |
|---|---|---|---|
| Orchestrator | `C:\Users\larsv\Jobpipe-orchestrator-v2` | `ops/orchestrator-v2` | Plans, specs, state |
| Codex | `C:\Users\larsv\Jobpipe-codex-v2` | `codex/T00X-<slug>` | Implementation |
| Claude | `C:\Users\larsv\Jobpipe-claude-v2` | `claude/T00X-<slug>` | Planner (idle) |

## Pre-staging Codex before every handoff

Before pasting any Codex prompt, ensure the target branch is clean:

```powershell
# From orchestrator side — reset Codex worktree to current main
git -C C:\Users\larsv\Jobpipe-codex-v2 fetch origin
git -C C:\Users\larsv\Jobpipe-codex-v2 checkout -b codex/<new-branch> origin/main
# OR if branch already exists:
git -C C:\Users\larsv\Jobpipe-codex-v2 reset --hard origin/main
```

Include `git fetch origin && git reset --hard origin/<branch>` at the top of every Codex prompt itself — never trust worktree state.
