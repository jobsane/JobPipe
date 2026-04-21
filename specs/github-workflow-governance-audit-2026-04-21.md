# GitHub Workflow Governance Audit

Date: 2026-04-21

## Purpose

This audit records how JobPipe should improve GitHub-based planning, delegation, and agent execution without replacing the canonical product roadmap or drifting into another parallel planning system.

The goal is to make work easier to delegate, review, and finish while preserving the current JobPipe rules:

- GitHub Project #6 is the execution board.
- `MASTER_PLAN.md`, `PRODUCT_VISION.md`, and `ROADMAP.md` remain the planning truth.
- Issues and pull requests carry executable task truth.
- Agents may help execute bounded work, but humans keep product, security, and merge authority.

## Sources Reviewed

- GitHub Project #6 current field and issue structure.
- Root planning docs: `MASTER_PLAN.md`, `PRODUCT_VISION.md`, `ROADMAP.md`, `OSS_SCOPE.md`, `DEPENDENCY_POLICY.md`, `TESTING.md`.
- Current runtime and architecture docs under `docs/`.
- Active and transitional specs under `specs/`.
- CCPM: https://github.com/automazeio/ccpm
- Simone: https://github.com/Helmi/claude-simone
- GitHub Copilot coding agent docs: https://docs.github.com/en/copilot/using-github-copilot/coding-agent/about-assigning-tasks-to-copilot
- GitHub issue template docs: https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/configuring-issue-templates-for-your-repository
- GitHub Projects automation docs: https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/using-the-built-in-automations
- GitHub Actions security hardening docs: https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions
- Recent AI workflow/project-management roundups were treated as trend input only, not as authoritative architecture.

## Current JobPipe Fit

JobPipe already has the right planning center:

- `MASTER_PLAN.md` defines product truth and planning hierarchy.
- `ROADMAP.md` intentionally stays high level.
- GitHub Project #6 owns backlog placement, hierarchy, milestones, sprint selection, and execution tracking.
- `DEPENDENCY_POLICY.md` already says agent runtimes and workflow engines should be wrapped behind JobPipe-owned boundaries when used.
- `TESTING.md` already defines the validation discipline that agent-created pull requests must satisfy.

The main gap is not another planning framework. The gap is execution ergonomics:

- issues are not yet explicitly marked by delegation suitability;
- issue intake is not yet structured by issue forms;
- agent-created work does not yet have a dedicated readiness/review policy;
- GitHub project automation is not yet used to reduce manual triage;
- background AI agents have no safe lane for small, reviewable implementation tasks.

## External Patterns Worth Borrowing

### CCPM

Useful pattern:

- PRD -> epic -> task decomposition.
- GitHub Issues as the auditable execution layer.
- Parallel agent execution only after decomposition is concrete.
- Worktree isolation for concurrent implementation.

JobPipe adaptation:

- Do not import CCPM as a new source of truth.
- Borrow the decomposition discipline for larger epics.
- Keep GitHub Project #6 as the canonical board and use specs only as supporting artifacts.

### Simone

Useful pattern:

- Durable task/project context for AI-assisted sessions.
- Explicit activity tracking and handoff/state preservation.
- MCP/server direction as an optional future integration pattern.

JobPipe adaptation:

- Do not install Simone as a parallel local planning system now.
- Borrow the idea of explicit handoff/state templates where JobPipe agents repeatedly lose context.
- Keep `AGENT_STATUS.md`, `AUDIT.md`, issues, and PRs as the real handoff surfaces.

### GitHub-Native AI Agents

Useful pattern:

- Assign bounded issues to an agent.
- Let the agent work in GitHub's pull-request flow.
- Human review remains the merge gate.
- Review comments can drive agent iteration.

JobPipe adaptation:

- Use this first for docs, tests, small refactors, issue-template work, and narrow bug fixes.
- Do not use it first for product-semantics changes, sensitive data handling, scoring thresholds, or DB migrations.
- Require a validation section in the issue and PR.

### Trending AI Workflow Tools

Common useful theme:

- modular agents;
- persistent context;
- task decomposition;
- self-hostable or GitHub-integrated execution;
- explicit guardrails around code review, security, and dependency changes.

JobPipe adaptation:

- Treat these as research subjects, not dependencies.
- Prefer GitHub-native and local-first workflow improvements before introducing new agent platforms.
- Any third-party agent runtime must pass `DEPENDENCY_POLICY.md` and security review before becoming tooling.

## Recommended Operating Model

1. Product truth stays in docs.
2. Execution truth stays in GitHub Project #6.
3. Complex work gets decomposed into epic, feature, story, task, and spike issues.
4. Each issue gets a delegation classification:
   - `Human-led`: needs product judgment or sensitive changes.
   - `Agent-ready`: bounded, testable, low product ambiguity.
   - `Needs decision`: blocked on user/product choice.
   - `Research only`: collect evidence and propose options.
5. Agent-ready issues must include:
   - bounded scope;
   - allowed files or package slice;
   - acceptance criteria;
   - exact validation command expectations;
   - explicit non-goals.
6. Agent pull requests must not merge without human review and local validation evidence.

## Project Topics Registered

The following topics should exist in GitHub Project #6 under planning/infrastructure governance rather than remaining as loose notes:

- GitHub-native agent delegation lane.
- Issue forms for epics, stories, tasks, bugs, spikes, and sprint closure.
- Project automation for adding issues, default status, labels, and PR linkage.
- Agent PR validation and security gate.
- CCPM-style epic decomposition research.
- Simone-style context/handoff research.
- Third-party agent/runtime evaluation policy.
- Worktree-backed parallel agent execution spike.
- Project board health check/report automation.

## Ready-Now Recommendation

This audit has already added the GitHub Project `Delegation` field and registered the setup/research topics. The next concrete setup slice should be:

1. create issue templates/forms;
2. define the first `agent-ready` issue policy;
3. add one lightweight project-health script/report or GitHub Actions workflow;
4. trial one low-risk `agent-ready` issue through the PR flow.

This should happen before assigning product-semantic work to background agents.

## Do Not Do Now

- Do not replace GitHub Project #6 with CCPM, Simone, Jira, Linear, or another planner.
- Do not install broad workflow/orchestration platforms into the repo to manage normal development.
- Do not let agent-generated PRs change scoring, filtering, private data handling, or DB schemas without explicit human review.
- Do not expose a third-party agent framework as JobPipe's public architecture.
- Do not make background agents work against `main` directly.

## Security and Dependency Rules

Any third-party agent, MCP server, workflow runtime, or GitHub automation must be treated as a tooling dependency and reviewed against:

- license;
- maintenance state;
- permission scope;
- secret exposure risk;
- ability to run with least privilege;
- whether it is direct tooling, wrapped tooling, or not appropriate for this repo.

Agent tooling should default to read-only or PR-only permissions until a specific stronger permission is justified.

## Practical Conclusion

JobPipe does not need another project-management system. It needs a clearer GitHub-native operating layer that separates:

- product decisions;
- planning decomposition;
- human-led implementation;
- agent-ready implementation;
- research-only exploration;
- validation and merge gates.

The cleanest path is to keep the current docs and GitHub Project #6, add delegation metadata, add issue forms, automate board hygiene, and use background agents only on bounded work with explicit validation.
