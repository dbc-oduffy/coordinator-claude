---
title: Hook best practices
created: 2026-05-17
type: doctrine
related:
  - plugins/coordinator/docs/wiki/daily-branch-discipline.md
  - plugins/coordinator/docs/wiki/claude-code-platform-gotchas.md
---

# Hook Best Practices

Working notes on Claude Code hook mechanics — the platform behaviors that are non-obvious and have caused silent failures.

## PreToolUse deny: JSON output, not exit 2

When a PreToolUse hook needs to block a tool call, emit JSON to stdout — not a non-zero exit code.

```json
{
  "permissionDecision": "deny",
  "permissionDecisionReason": "<human-readable explanation>"
}
```

Exit code 2 is silently swallowed by the hook runtime. The tool call proceeds as if the hook never fired, with no error surfaced. JSON deny is the only protocol that actually blocks the call and surfaces the reason in the Claude Code UI.

The `permissionDecisionReason` field is required — hooks that omit it produce a terse "denied" with no context, which is harder to diagnose when an agent hits the block.

→ `docs/wiki/daily-branch-discipline.md` § Enforcement surfaces shows a working example of the JSON deny shape.

## `async: true` on touched-files hooks races safe-commit reads

PostToolUse hooks that produce state consumed by `coordinator-safe-commit` (touched-file lists, session-scope records) must run synchronously. Setting `async: true` means the hook process is still writing when the safe-commit helper reads — files are missed from scope detection and land outside the commit scope silently.

The 70ms synchronous cost is irrelevant at the cadence commits fire. Default to `async: false` for any hook whose output feeds an adjacent operation in the same session. Use `async: true` only for fire-and-forget telemetry hooks whose output no other tool reads.

## session_id reaches hooks but NOT hook-spawned subprocesses

Claude Code injects `CLAUDE_SESSION_ID` into the hook's own environment, but that variable is not inherited by subprocesses the hook spawns via `bash -c`, Python subprocess, or similar. A hook that forks a worker expecting to read `CLAUDE_SESSION_ID` from its environment will silently get an empty string.

Two remediation patterns:

1. **Explicit arg.** Pass `$CLAUDE_SESSION_ID` as a positional argument when launching the subprocess: `python worker.py "$CLAUDE_SESSION_ID"`.
2. **Sentinel file.** Have the hook write the session_id to a known path (e.g., `.git/coordinator-sessions/current-session-id`) before launching the subprocess; the subprocess reads from disk instead of env.

Pattern 1 is simpler for single-child spawns. Pattern 2 is better when the subprocess is a long-lived daemon that outlives the hook invocation.

## PreCompact false alarms: gate on ≥15% transcript size shrink

`PreCompact` fires on every event that may trigger context management — including subagent-result integration events that do not actually shrink the transcript. Emitting "context compacted" unconditionally on every `PreCompact` fire produces spurious advisory noise during normal heavy-use sessions.

Gate the message on measured shrink: compare the transcript token count before and after. Only emit if the shrink is ≥15% of pre-event size. Below that threshold the event was a housekeeping fire, not a compaction.

## Model-version gating: family fallbacks, not pinned arms

Hook scripts that branch on model name should match family prefixes, not pinned version strings.

Good:
```bash
if [[ "$CLAUDE_MODEL" == *opus* ]]; then ...
if [[ "$CLAUDE_MODEL" == *sonnet* ]]; then ...
```

Bad:
```bash
if [[ "$CLAUDE_MODEL" == *opus*4*6* ]]; then ...  # breaks on next minor release
```

Pinned arms like `opus*4*6*` break silently on the next version bump — the branch falls through to the else case with no error and wrong behavior. Family fallbacks (`*opus*`, `*sonnet*`, `*haiku*`) survive minor version bumps and new model releases.

## Disabled hook scripts must be removed from hooks.json

Removing a hook script from disk without removing its entry from `hooks/hooks.json` (or `settings.json`, for user-scope hooks) leaves a dangling reference. When the script is restored or a file with the same name appears (e.g., from a plugin reinstall), the hook re-activates — often at a much later date with no one remembering why it was disabled.

Two-place cleanup is the rule: remove the script AND remove its entry from the hooks config in the same commit. If the intent is temporary disable rather than permanent removal, comment out the entry in the config rather than deleting the script.

## Plugin-owned hooks belong in hooks/hooks.json, not user-scope settings

Hook entries placed in user-scope `settings.json` are invisible to other machines and break marketplace distribution. Plugin hooks must live at `hooks/hooks.json` inside the plugin directory — this is the path the plugin system reads on install and the path that travels with the plugin to new machines.

User-scope `settings.json` hooks are for machine-local overrides that intentionally should not distribute. If a hook is load-bearing for a plugin's behavior, it belongs in the plugin's `hooks/hooks.json`.
