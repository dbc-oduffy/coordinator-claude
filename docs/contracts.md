# Contracts

An index of the testable claims the coordinator system makes, linking each
contract bullet to the hook, script, or doctrine section that enforces it.
This is not a restatement — read the linked source for the rule itself.

## Coordinator (EM) contract

- Doesn't write implementation code directly →
  [`plugins/coordinator/CLAUDE.md` § Plan-First Workflow](../plugins/coordinator/CLAUDE.md#plan-first-workflow) +
  `plugins/coordinator/hooks/scripts/coordinator-reminder.sh` (PreToolUse nudge when EM reaches for domain tools)
- Preserves project state across sessions →
  [`plugins/coordinator/CLAUDE.md` § Handoff Lineage](../plugins/coordinator/CLAUDE.md#handoff-lineage--single-predecessor-no-adjacency-inference) +
  `/handoff` command (`plugins/coordinator/commands/handoff.md`)
- Routes implementation to executor agents →
  [`plugins/coordinator/agents/executor.md`](../plugins/coordinator/agents/executor.md) +
  [`plugins/coordinator/CLAUDE.md` § Executor Dispatch Mode](../plugins/coordinator/CLAUDE.md#executor-dispatch-mode)
- Routes review to independent reviewers sequentially →
  [`plugins/coordinator/CLAUDE.md` § Review Sequencing](../plugins/coordinator/CLAUDE.md#review-sequencing)
- Stages only in-scope files — never `git add -A` →
  [`plugins/coordinator/bin/coordinator-safe-commit`](../plugins/coordinator/bin/coordinator-safe-commit) +
  [`plugins/coordinator/CLAUDE.md` § Concurrent-EM Git Operations](../plugins/coordinator/CLAUDE.md#concurrent-em-git-operations)
- Stays on the daily branch — no ad-hoc `feature/*` →
  [`plugins/coordinator/hooks/scripts/block-off-daily-branch.sh`](../plugins/coordinator/hooks/scripts/block-off-daily-branch.sh) +
  [`plugins/coordinator/CLAUDE.md` § Concurrent-EM Git Operations](../plugins/coordinator/CLAUDE.md#concurrent-em-git-operations)
- Presents ship/no-ship verdicts with evidence before merging →
  [`plugins/coordinator/skills/merging-to-main/SKILL.md` § The Process](../plugins/coordinator/skills/merging-to-main/SKILL.md#the-process)

## Executor contract

- Follows the enriched plan exactly — no improvisation →
  [`plugins/coordinator/agents/executor.md` § Core Behavior](../plugins/coordinator/agents/executor.md#core-behavior)
- Updates stub status before touching files (write-ahead) →
  [`plugins/coordinator/agents/executor.md` § Operating Protocols](../plugins/coordinator/agents/executor.md#operating-protocols)
- Stages only files it edited — never blanket-stage →
  [`plugins/coordinator/agents/executor.md` § Commit Discipline](../plugins/coordinator/agents/executor.md#commit-discipline--scoped-staging-never--a)
- Escalates rather than guesses on ambiguous specs →
  [`plugins/coordinator/agents/executor.md` § Stop Conditions](../plugins/coordinator/agents/executor.md#stop-conditions--fixable-vs-structural)

## Reviewer contract

- Reviews against acceptance criteria and non-goals →
  [`plugins/coordinator/agents/staff-eng.md`](../plugins/coordinator/agents/staff-eng.md)
- Classifies findings as blocker / non-blocker / taste with confidence scores →
  `plugins/coordinator/snippets/reviewer-calibration.md` (synced into every reviewer prompt)
- Cites file:line evidence for every finding →
  [`plugins/coordinator/agents/staff-eng.md`](../plugins/coordinator/agents/staff-eng.md)
- Avoids opportunistic rewrites (assess, fill, frame — never re-author) →
  [`plugins/coordinator/CLAUDE.md` § Synthesis Discipline](../plugins/coordinator/CLAUDE.md#synthesis-discipline)
- Review findings are applied by the integrator, not manually by the EM →
  [`plugins/coordinator/agents/review-integrator.md`](../plugins/coordinator/agents/review-integrator.md) +
  [`plugins/coordinator/CLAUDE.md` § Review Sequencing](../plugins/coordinator/CLAUDE.md#review-sequencing)

## Hooks and scripts that detect contract violations

| Enforcer | What It Guards |
|----------|---------------|
| `plugins/coordinator/hooks/scripts/block-off-daily-branch.sh` | Branch discipline — blocks create/switch/rename/commit off the daily branch |
| `plugins/coordinator/bin/coordinator-safe-commit` | Scoped staging — fails closed when >1 live session and no explicit scope is declared |
| `plugins/coordinator/hooks/scripts/validate-commit.sh` | Commit-content validation (Checks 1–5: message format, file-scope, signing) |
| `plugins/coordinator/hooks/scripts/coordinator-reminder.sh` | EM discipline — nudges coordinator away from direct implementation work |
| `plugins/coordinator/hooks/scripts/context-pressure-advisory.sh` | Session continuity — prompts handoff creation before compaction fires |
| `plugins/coordinator/agents/review-integrator.md` | No manual review integration — routes findings through the integrator agent |
| `plugins/coordinator/hooks/scripts/plan-persistence-check.sh` | Plan-first discipline — checks plan content was written to disk, not held in context |

## Further reading

- Full persona rationale: [`docs/evolution/03-personas-as-ergonomics.md`](evolution/03-personas-as-ergonomics.md)
- System architecture: [`docs/architecture.md`](architecture.md)
- Daily-branch doctrine: `plugins/coordinator/docs/wiki/daily-branch-discipline.md`
- Scoped-staging guide: `plugins/coordinator/docs/wiki/scoped-safety-commits.md`
