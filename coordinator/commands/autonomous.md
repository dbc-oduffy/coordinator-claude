---
name: autonomous
description: "Toggle autonomous execution mode — suppresses /handoff nudges from the context pressure hook when the PM wants the EM to continue through compaction"
allowed-tools: ["Bash"]
argument-hint: "[on|off]"
---

# Autonomous Mode Toggle

Writes or removes the autonomous-run sentinel file that the context pressure hook checks. When active, context pressure messages become informational-only (no `/handoff` recommendation).

## Usage

- `/autonomous` or `/autonomous on` — enable autonomous mode
- `/autonomous off` — disable autonomous mode

## Instructions

Parse `$ARGUMENTS`:
- If empty, "on", or "yes" → **enable**
- If "off", "no", or "stop" → **disable**

### Enable

```bash
echo "autonomous" > /tmp/autonomous-run-${SESSION_ID}
```

Confirm to the PM: "Autonomous mode enabled — context pressure hook will emit informational-only messages (no /handoff nudge). Use `/autonomous off` to restore normal behavior."

### Disable

```bash
rm -f /tmp/autonomous-run-${SESSION_ID}
```

Confirm to the PM: "Autonomous mode disabled — context pressure hook will resume normal /handoff nudges."

## Behavior While Active

Autonomous mode is more than a handoff-nudge suppressor — it's a posture change. When active:

- **Presume the PM is away from the keyboard.** Asking or pausing doesn't get a fast answer — it stalls the run until the PM physically returns. A pause is the *most expensive* action, not the safe default. The bar to stop is not "would input help?" but "is proceeding actually forbidden?"
- **Drive to completion under the First Officer Doctrine as the ONLY constraint.** Like Asimov's laws: proceed *unless and until* an action would conflict with the doctrine. Operational recovery (crashed/rate-limited agents, partial commits, orphaned code) is never a stop reason. Engineering calls (approach, structure, refactor mechanics, sequencing) are yours to make and act on.
- **Reach the goal even with debt — as long as you TRACK it.** A patch, hotfix, shim, or otherwise unsustainable path to a working result is fine; don't stop just because the clean fix is large. The hard requirement: every shortcut and deferred-proper-fix gets logged to `state/debt-backlog/` (or `improvement-queue/` / `bug-backlog/`) via `coordinator-queue-append` and named in the end-of-run summary. Untracked debt is the failure mode; tracked debt is acceptable cost of finishing.
- **Legitimate stops are doctrine conflicts only** — and most route around rather than halt:
  - **Non-pre-approved destructive/irreversible actions** (force-push, history rewrite, `rm -rf` of unrecoverable data, push to `origin/main`, PRs, external messages, DB drops). Pre-authorized → do it carefully; otherwise queue it and keep working everything else — don't block the run on one gated action.
  - **Genuine product/scope tradeoffs** the PM owns. A *broken thing* is never one of these — break-class findings are fix-by-default (`§ Flag Severity`).
  - **Structural dead-ends** — spec ambiguous at multiple load-bearing points, or the approach is fundamentally wrong. Capture the blocker, finish independent work, stop that thread only.
- **Inform, don't ask.** Status between steps is output-only — never "ready for next batch?". End-of-run summaries (with tracked debt + queued gated actions) are expected; mid-run "should we continue?" is not.
- **Terminate cleanly.** When done, write a handoff, run the tail action (if specified), and stop. Don't loop for more work unless the PM asked for a continuous loop.

## Notes

- The sentinel is session-scoped (`SESSION_ID`) and lives in `/tmp` — it's automatically cleaned up on reboot
- Stale sentinels older than 24h are cleaned up by the context pressure hook itself
- `/mise-en-place` writes and cleans up this same sentinel automatically — you don't need `/autonomous` when running mise-en-place
