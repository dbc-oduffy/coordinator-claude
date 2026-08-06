---
name: autonomous
description: "Toggle autonomous mode — suppresses handoff nudges near compaction."
allowed-tools: ["Bash"]
argument-hint: "[on|off]"
---

# Autonomous Mode Toggle

Writes or removes the autonomous-run sentinel file that the context pressure hook checks. When active, context pressure messages become informational-only (no `/handoff` recommendation).

## Usage

- `/autonomous` or `/autonomous on` — enable autonomous mode
- `/autonomous off` — disable autonomous mode

## Instructions

Pass `$ARGUMENTS` through verbatim to the shared autonomous-toggle verb
(`coordinator_core.workday_complete.autonomous_verb` — the ONE toggle both
this command and any future workday-assembler step resolve to). It owns the
token mapping (empty/`on`/`yes` → enable, `off`/`no`/`stop` → disable), the
session-id resolution (`coordinator_core.session.core.resolve_session_id` —
the same resolver the consumer hooks key off of via the harness-injected
`session_id`), and the sentinel write/removal itself (wrapping
`misc-session-and-guards autonomous-sentinel enable|disable` — never
reimplemented here).

`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/autonomous-verb" $ARGUMENTS`

Relay the CLI's own stdout confirmation line to the PM — it already prints
the enabled/disabled message; don't re-author it.

## Behavior While Active

Autonomous mode is a posture change, not just a nudge suppressor. Presume the
PM is away from the keyboard — pausing to ask doesn't get a fast answer, it
stalls the run, so the bar to stop is "is proceeding actually forbidden?", not
"would input help?". Drive to completion, taking on debt rather than
stalling: a patch, hotfix, or shim is fine as long as every shortcut is logged
to `state/debt-backlog/` (or `improvement-queue/` / `bug-backlog/`) and named
in the end-of-run summary — untracked debt is the failure mode, tracked debt
is an acceptable cost of finishing. Legitimate stops are doctrine conflicts
only: non-pre-approved destructive/irreversible actions (force-push, history
rewrite, `rm -rf` of unrecoverable data, push to `origin/main`, PRs, external
messages, DB drops) get queued rather than halting the whole run; genuine
product/scope tradeoffs the PM owns (a broken thing is never one of these —
break-class findings are fix-by-default); and structural dead-ends (spec
ambiguous at a load-bearing point, or the approach is fundamentally wrong) —
capture the blocker, finish independent work, stop only that thread.
`AskUserQuestion` is prohibited for break-class and engineering-approach
decisions in this mode — it halts the run until the away PM returns. The only
legitimate pauses are a genuinely-irreversible external action with no
pre-authorization, or a true no-correct-answer product-direction fork the PM
owns, and even those should route around (queue the action, do independent
work) rather than halt. Status between steps is output-only — never "ready
for next batch?"; end-of-run summaries are expected, mid-run "should we
continue?" is not.

## Notes

- The sentinel is session-scoped, keyed by the id `coordinator_core.session.core.resolve_session_id` resolves (matching the hook's `session_id`, not a bare `${SESSION_ID}` env var), and lives in `/tmp` — it's automatically cleaned up on reboot
- Stale sentinels older than 24h are cleaned up by the context pressure hook itself
- `/mise-en-place` and `/autonomous` are INDEPENDENT and COMPOSABLE at the posture layer, not coupled. `/mise-en-place` writes and cleans up this same sentinel path automatically (with `--mode mise-en-place`), but sentinel presence alone no longer implies autonomous posture — the sentinel's `mode` content is what distinguishes them. A bare `/mise-en-place` run hands off at context pressure via its CONTINUANCE terminal (hand-off-at-pressure posture); it does NOT ride compaction. `/autonomous` + `/mise-en-place` together is the PM's opt-in to power through compaction to backlog exhaustion instead of taking the CONTINUANCE terminal — invoke both explicitly when that's wanted.
