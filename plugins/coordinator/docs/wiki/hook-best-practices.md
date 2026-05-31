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
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "<human-readable explanation>"
  }
}
```

The flat `{"permissionDecision":"deny"}` shape (no `hookSpecificOutput` wrapper) is an older API form that silently passes through. Always use the nested `hookSpecificOutput` wrapper — canonical examples: `block-off-daily-branch.sh:262-277` and `block-subagent-archive-write.sh:204-218`.

Exit codes do NOT block-with-a-clean-reason. **exit 1** is non-blocking — the tool call proceeds and stderr goes to the *user terminal* only (advisory; the model never sees it). **exit 2** at PreToolUse *does* block, but the reason is delivered as raw stderr into the model's turn, not surfaced in the Claude Code permission UI (and exit-2 semantics vary by hook event — see § Friction-as-warning for the full PreToolUse-vs-PostToolUse table). JSON deny (stdout + exit 0) is the protocol that blocks the call AND surfaces a structured reason in the Claude Code UI — prefer it for any PreToolUse block. (In-tree witness for exit-2-blocks: `check-claude-md-size.py:6`.)

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

## Transcript scrape: never `large-producer | grep -q` under `set -o pipefail`

A hook that scrapes the transcript — `if tail -N "$transcript" | grep -q PAT; then ...` — silently fails OPEN under `set -o pipefail` on any real-sized session. `grep -q` exits 0 on its first match and closes the pipe; `tail` (still writing the multi-MB transcript) takes SIGPIPE and dies with exit 141; `pipefail` then makes 141 the *pipeline's* status. The `if` evaluates FALSE **despite a match**, so the suppression/detection the scrape was supposed to drive never fires. It only manifests past the ~64KB pipe buffer, so small-fixture tests pass while the hook is dead in production (2026-05-30: both nudge hooks' skill-suppression branches were dead on every real-sized transcript — the `/handoff` nudge fired 100% of the time on the Skill-tool case).

**Fix — keep the early-exiting reader out of the pipeline.** Read into a variable, match via here-string:

```bash
RECENT_TAIL=$(tail -N "$transcript" 2>/dev/null || true)
if grep -qE PAT <<< "$RECENT_TAIL"; then ...
```

`tail` now runs standalone in command substitution (its SIGPIPE swallowed by `|| true`), and `grep` reads from the variable — no pipeline, no status to poison the `if`.

**Direction matters.** `grep PAT file | tail -1` is safe: `grep` is the producer and `tail` the consumer that reads to EOF, so `grep` never takes SIGPIPE. The trap is specifically the *early-exiting reader downstream of a large producer* (`grep -q`, `head`, `grep -m1`).

**Test it with a real-sized, deterministic fixture.** The repro is racy: a mid-stream match lets `grep` drain the pipe before `tail` blocks. To make a regression test that reliably fails against the bug, put the match EARLY in the byte stream (line 1) with ≫64KB queued behind it, all inside the `tail -N` window — mirroring how the real incident reproduced (an early match in a 1.4MB transcript). A 3-line fixture proves nothing.

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

## Disabled hook scripts: clean BOTH registration surfaces

Hook scripts have two registration surfaces: `hooks/hooks.json` (plugin-distributed, travels with the plugin) and `~/.claude/settings.json` (user-scope, machine-local). Removing or disabling a hook script on disk without cleaning BOTH surfaces is silent breakage:

- **Dangling `hooks/hooks.json` entry:** when the script (or a same-named file from a plugin reinstall) reappears, the hook re-activates — often at a much later date with no one remembering why it was disabled.
- **Dangling `settings.json` entry:** every PreToolUse/PostToolUse fire produces a `Hook error` until the entry is removed. Not a "harmless stale reference" — it fires on every tool call.

Doctrinal pair: disable in BOTH surfaces AND remove the script file in the same commit. If you remove the script first, the registration edits follow in the same commit. For temporary disable rather than permanent removal, comment out the entries rather than deleting the script.

## Friction-as-warning needs a typed override, not a toggle

When you want a hook to *change EM behavior* (not just leave a paper trail), block-with-typed-justification is the only shape that works. Warn-only fails silent — stderr at exit 0 goes to the user's terminal, not back into the model's context, so the EM never reads it.

The two effective shapes:

1. **Hard block + typed env-var override.** Hook emits a JSON deny (`{"permissionDecision":"deny", "permissionDecisionReason":"<four questions>"}`) unless `COORDINATOR_<SCOPE>_PUNT="<plain-English sentence>"` is set. Trivial overrides ("1", "ok", strings under ~12 chars) are rejected by the reason-parser — the cognitive load IS the design point. The EM must articulate *what is being punted* while the deny reason sits in context.

2. **Exit 2 with stderr.** The Claude Code runtime treats exit 2 as "feed stderr into the model's next turn." This reaches the model — but **whether it also blocks depends on the hook event:**
   - **PreToolUse `exit 2` BLOCKS** the tool call (stderr → model). Wrong altitude for a pure warn.
   - **PostToolUse `exit 2` does NOT block** — the tool already ran, the file is on disk, only the stderr reaches the model. This is the genuine warn-reaches-the-model-**without**-blocking channel.

   So a "warn, never block" hook whose audience is the EM must fire at **PostToolUse** and `exit 2`. Canonical example: `nudge-unauthorized-handoff.sh` (PostToolUse Write on `tasks/handoffs/`|`tasks/spinoffs/`) — see `coordinator-tripwires.md` § `NUDGE-UNAUTHORIZED-HANDOFF`.

Stderr at exit 0 is the failure mode — the message lands in the user terminal but never reaches the model that just made the decision. If the EM is the audience, the EM has to be forced to read it.

The cost isn't keystrokes — it's the moment of friction that surfaces the lazy-punt before it becomes a queue entry. If writing the override sentence feels harder than just fixing the underlying thing, the hook worked.

Pattern generalizes to any "don't reflexively reach for this surface" tripwire: `block-off-daily-branch.sh`, `nudge-improvement-queue-write.sh` — all use block-with-override or exit-2-with-stderr; none use stderr-at-exit-0.

### Reliability of the gating signal must match the cost of being wrong

A *block* (PreToolUse deny / `exit 2`) gated on an unreliable signal fails **CLOSED** — it denies authorized work and trains the EM to reflexively reach for the override, defeating the point. The same unreliable signal used to SUPPRESS a *non-blocking nudge* (PostToolUse `exit 2`) fails **OPEN** — at worst the EM reads one extra nudge and proceeds.

When the detection cannot be made reliable, don't harden the signal — lower the consequence of its being wrong (block → nudge). `block-unauthorized-handoff.sh` detected "is an authoring skill active" by scraping the transcript for `<command-name>` tags / `/spinoff` strings; the Skill tool emits no `<command-name>`, and large tool outputs bury the invocation past any grep window. Two patches tried to make the *scrape* window-independent and it still false-blocked a PM-authorized `/spinoff` (2026-05-28). The third rework left the scrape exactly as unreliable as before and instead moved it from gating-a-block to suppressing-a-nudge (`nudge-unauthorized-handoff.sh`). That is the design-as-offers principle applied to hook altitude: the signal didn't get better, the blast radius of its being wrong got cheap.

## Plugin-owned hooks belong in hooks/hooks.json, not user-scope settings

Hook entries placed in user-scope `settings.json` are invisible to other machines and break marketplace distribution. Plugin hooks must live at `hooks/hooks.json` inside the plugin directory — this is the path the plugin system reads on install and the path that travels with the plugin to new machines.

User-scope `settings.json` hooks are for machine-local overrides that intentionally should not distribute. If a hook is load-bearing for a plugin's behavior, it belongs in the plugin's `hooks/hooks.json`.

## Script names encode invariants — if the invariant inverts, retire don't rename

When a hook or validator script's name encodes a now-defunct invariant (e.g., `block-X-mirror`, `verify-Y-single-tree`), the right move is retirement, not repurposing. Changing a path constant or condition inside the script while leaving the filename intact produces a script whose name lies — it will false-positive-block legitimate writes in any session where the name is read without the body.

Retirement protocol: (1) read the spec backlink to confirm the invariant is genuinely defunct, not just locally disabled; (2) retire the script file; (3) delete the hook registration from `hooks/hooks.json` and any `settings.json` entries; (4) update doctrine references — all in one commit. Running the unupdated hook post-inversion is silent breakage: the block fires on correct writes with no error message pointing at the stale invariant.
