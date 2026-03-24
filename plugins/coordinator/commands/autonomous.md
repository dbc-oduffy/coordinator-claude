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

## Notes

- The sentinel is session-scoped (`SESSION_ID`) and lives in `/tmp` — it's automatically cleaned up on reboot
- Stale sentinels older than 24h are cleaned up by the context pressure hook itself
- `/mise-en-place` writes and cleans up this same sentinel automatically — you don't need `/autonomous` when running mise-en-place
