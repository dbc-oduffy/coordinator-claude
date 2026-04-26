---
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

- **Drive to completion.** The PM has signaled they want the run to finish without interactive gating. Do not pause to ask "should we continue?", "should we recover this?", or "want me to finish?" on tractable, scoped, roadmap-aligned work. Recovery from crashed/rate-limited/auth-failed agents, partial commits, and orphaned code on disk is routine operational work, not a PM decision.
- **Legitimate stops only:** genuine product/scope questions, external-facing actions the PM must approve (pushing to main, opening PRs, sending messages), or structural failures (spec is ambiguous at multiple decision points, approach is fundamentally wrong). Not operational friction.
- **Inform, don't ask.** Status updates between waves/steps are output-only. Never "ready for next batch?" — just start it. End-of-run summaries are fine and expected; mid-run "should we continue?" is not.
- **Terminate cleanly.** When the work is done, write a handoff, run the tail action (if specified), and stop. Do not loop looking for more work unless the PM asked for a continuous loop.

## Notes

- The sentinel is session-scoped (`SESSION_ID`) and lives in `/tmp` — it's automatically cleaned up on reboot
- Stale sentinels older than 24h are cleaned up by the context pressure hook itself
- `/mise-en-place` writes and cleans up this same sentinel automatically — you don't need `/autonomous` when running mise-en-place
