# Contracts

An index of the testable claims the coordinator system makes, linking each
contract bullet to the hook, script, or doctrine section that enforces it.
This is not a restatement — read the linked source for the rule itself.

Layer taxonomy:
- `mechanical-blocker` — hook script that fails-closed (e.g. `block-off-daily-branch.sh`, `coordinator-safe-commit --expected-branch`).
- `mechanical-advisory` — hook script that warns / reminds without blocking (e.g. `coordinator-reminder.sh`, `context-pressure-advisory.sh`).
- `prompt-doctrine` — pointer to CLAUDE.md section / agent prompt / skill body.
- `workflow-check` — multi-step procedure where compliance depends on EM following sequence (e.g. integrator dispatch after review).

## Coordinator (EM) contract

- Doesn't write implementation code directly →
  [`plugins/coordinator/CLAUDE.md` § Plan-First Workflow](../plugins/coordinator/CLAUDE.md#plan-first-workflow) +
  `plugins/coordinator/hooks/scripts/coordinator-reminder.sh` (PreToolUse nudge when EM reaches for domain tools)
  *— mechanical-advisory via `coordinator-reminder.sh`; prompt-doctrine via CLAUDE.md § Plan-First Workflow*
- Preserves project state across sessions →
  [`plugins/coordinator/CLAUDE.md` § Handoff Lineage](../plugins/coordinator/CLAUDE.md#handoff-lineage--single-predecessor-no-adjacency-inference) +
  `/handoff` command (`plugins/coordinator/commands/handoff.md`)
  *— prompt-doctrine via CLAUDE.md § Handoff Lineage + `/handoff` command*
- Routes implementation to executor agents →
  [`plugins/coordinator/agents/executor.md`](../plugins/coordinator/agents/executor.md) +
  [`plugins/coordinator/CLAUDE.md` § Executor Dispatch Mode](../plugins/coordinator/CLAUDE.md#executor-dispatch-mode)
  *— prompt-doctrine via CLAUDE.md § Executor Dispatch Mode*
- Routes review to independent reviewers sequentially →
  [`plugins/coordinator/CLAUDE.md` § Review Sequencing](../plugins/coordinator/CLAUDE.md#review-sequencing)
  *— workflow-check via CLAUDE.md § Review Sequencing (sequential dispatch sequence)*
- Stages only in-scope files — never `git add -A` →
  [`plugins/coordinator/bin/coordinator-safe-commit`](../plugins/coordinator/bin/coordinator-safe-commit) +
  [`plugins/coordinator/CLAUDE.md` § Concurrent-EM Git Operations](../plugins/coordinator/CLAUDE.md#concurrent-em-git-operations)
  *— mechanical-blocker via `coordinator-safe-commit` (fails closed on scope violation)*
- Stays on the daily branch — no ad-hoc `feature/*` →
  [`plugins/coordinator/hooks/scripts/block-off-daily-branch.sh`](../plugins/coordinator/hooks/scripts/block-off-daily-branch.sh) +
  [`plugins/coordinator/CLAUDE.md` § Concurrent-EM Git Operations](../plugins/coordinator/CLAUDE.md#concurrent-em-git-operations)
  *— mechanical-blocker via `block-off-daily-branch.sh` (PreToolUse, fails closed)*
- Presents ship/no-ship verdicts with evidence before merging →
  [`plugins/coordinator/skills/merging-to-main/SKILL.md` § The Process](../plugins/coordinator/skills/merging-to-main/SKILL.md#the-process)
  *— workflow-check via `/merging-to-main` skill sequence*
- Trigger word "plan" mechanically invokes the plan super-skill — never `Write` direct to disk →
  [`plugins/coordinator/CLAUDE.md` § Plan-First Workflow](../plugins/coordinator/CLAUDE.md#plan-first-workflow) +
  [`plugins/coordinator/skills/plan/SKILL.md`](../plugins/coordinator/skills/plan/SKILL.md)
  *— prompt-doctrine via CLAUDE.md § Plan-First Workflow + `plan/SKILL.md`*
- Plans pass through prior-art recall before Opus review →
  [`plugins/coordinator/agents/prior-art-checker.md`](../plugins/coordinator/agents/prior-art-checker.md) +
  [`docs/wiki/prior-art-checker.md`](../docs/wiki/prior-art-checker.md)
  *— workflow-check via prior-art-checker dispatch in plan pipeline*

## Executor contract

- Follows the enriched plan exactly — no improvisation →
  [`plugins/coordinator/agents/executor.md` § Core Behavior](../plugins/coordinator/agents/executor.md#core-behavior)
  *— prompt-doctrine via executor.md § Core Behavior*
- Updates stub status before touching files (write-ahead) →
  [`plugins/coordinator/agents/executor.md` § Operating Protocols](../plugins/coordinator/agents/executor.md#operating-protocols)
  *— prompt-doctrine via executor.md § Operating Protocols*
- Stages only files it edited — never blanket-stage →
  [`plugins/coordinator/agents/executor.md` § Commit Discipline](../plugins/coordinator/agents/executor.md#commit-discipline--scoped-staging-never--a)
  *— prompt-doctrine via executor.md § Commit Discipline (backed by `coordinator-safe-commit` mechanical-blocker)*
- Escalates rather than guesses on ambiguous specs →
  [`plugins/coordinator/agents/executor.md` § Stop Conditions](../plugins/coordinator/agents/executor.md#stop-conditions--fixable-vs-structural)
  *— prompt-doctrine via executor.md § Stop Conditions*

## Reviewer contract

- Reviews against acceptance criteria and non-goals →
  [`plugins/coordinator/agents/staff-eng.md`](../plugins/coordinator/agents/staff-eng.md)
  *— prompt-doctrine via staff-eng.md agent prompt*
- Classifies findings as blocker / non-blocker / taste with confidence scores →
  `plugins/coordinator/snippets/reviewer-calibration.md` (synced into every reviewer prompt)
  *— prompt-doctrine via reviewer-calibration.md snippet (injected into all reviewer prompts)*
- Cites file:line evidence for every finding →
  [`plugins/coordinator/agents/staff-eng.md`](../plugins/coordinator/agents/staff-eng.md)
  *— prompt-doctrine via staff-eng.md agent prompt*
- Avoids opportunistic rewrites (assess, fill, frame — never re-author) →
  [`plugins/coordinator/CLAUDE.md` § Synthesis Discipline](../plugins/coordinator/CLAUDE.md#synthesis-discipline)
  *— prompt-doctrine via CLAUDE.md § Synthesis Discipline*
- Review findings are applied by the integrator, not manually by the EM →
  [`plugins/coordinator/agents/review-integrator.md`](../plugins/coordinator/agents/review-integrator.md) +
  [`plugins/coordinator/CLAUDE.md` § Review Sequencing](../plugins/coordinator/CLAUDE.md#review-sequencing)
  *— workflow-check via CLAUDE.md § Review Sequencing (integrator dispatch mandatory)*

## Hooks and scripts that detect contract violations

| Enforcer | What It Guards | Layer |
|----------|---------------|-------|
| `plugins/coordinator/hooks/scripts/block-off-daily-branch.sh` | Branch discipline — blocks create/switch/rename/commit off the daily branch | mechanical-blocker |
| `plugins/coordinator/bin/coordinator-safe-commit` | Scoped staging — fails closed when >1 live session and no explicit scope is declared | mechanical-blocker |
| `plugins/coordinator/hooks/scripts/validate-commit.sh` | Commit-content validation (Checks 1–5: message format, file-scope, signing) | mechanical-blocker |
| `plugins/coordinator/hooks/scripts/coordinator-reminder.sh` | EM discipline — nudges coordinator away from direct implementation work | mechanical-advisory |
| `plugins/coordinator/hooks/scripts/context-pressure-advisory.sh` | Session continuity — prompts handoff creation before compaction fires | mechanical-advisory |
| `plugins/coordinator/agents/review-integrator.md` | No manual review integration — routes findings through the integrator agent | workflow-check |
| `plugins/coordinator/hooks/scripts/plan-persistence-check.sh` | Plan-first discipline — checks plan content was written to disk, not held in context | mechanical-blocker |

## Further reading

- Full persona rationale: [`docs/evolution/03-personas-as-ergonomics.md`](evolution/03-personas-as-ergonomics.md)
- System architecture: [`docs/architecture.md`](architecture.md)
- Daily-branch doctrine: `docs/wiki/daily-branch-discipline.md`
- Scoped-staging guide: `docs/wiki/scoped-safety-commits.md`
