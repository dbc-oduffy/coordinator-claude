# Claude Code Platform Gotchas

**Provenance:** consolidated 2026-05-05 from `tasks/lesson-triage-2026-05-05/SYNTHESIS.md` §B11. Source extracts: coord E6–E15, project-rag E29/E30/E31, holodeck Cand1.

Reference catalog of platform-level Claude Code behaviors that have bitten us — hooks, MCP, plugins, subprocesses, OS quirks. None of these are documentation gaps in our doctrine; they're things the platform does (or doesn't do) that surprise authors writing against it. Greppable single-page reference; link from `~/.claude/CLAUDE.md`.

## Hooks

### Model-version gating must use family fallbacks, not pinned version arms

A `case` matching only `*opus*4*6*` / `*sonnet*4*6*` silently falls through for next-version IDs (e.g. `claude-opus-4-7[1m]`) to a conservative default — manifesting as undersized context windows and premature handoff nudges.

Prefer family-level fallback with override arms above for known exceptions:

```bash
case "$model" in
  *opus*) WINDOW=1000000 ;;
  *sonnet*|*haiku*) WINDOW=200000 ;;
  *) WINDOW=200000 ;;
esac
```

Source: `plugins/coordinator-claude/coordinator/hooks/scripts/context-pressure-advisory.sh`.

### PreCompact fires without real shrink on subagent-result integration

Claude Code triggers the `PreCompact` event for events that don't actually compress the parent transcript (notably integrating large subagent outputs back into the parent). A bridge that emits "COMPACTION OCCURRED" on every `PreCompact` will spam false alarms on 1M-context sessions.

**Defense:** gate the message on actual transcript-size shrink (≥15%) — record pre-size at `PreCompact`, compare against post-size at the next `PostToolUse`.

### `session_id` reaches hooks but NOT subprocesses

`session_id` arrives in hook stdin JSON but is never exported as `CLAUDE_SESSION_ID` to the EM's interactive Bash. CLI tools that need it (e.g. `coordinator-safe-commit`) must:

- Read a sentinel file written by a SessionStart hook, OR
- Accept it as an arg, OR
- Scan session-dir metadata.

Don't assume the env var exists.

### PreToolUse deny: use JSON output, not exit 2

The exit-1-vs-2 distinction is a footgun (exit 1 is non-blocking; only exit 2 blocks). Modern interface — emit on stdout with exit 0:

```json
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "..."}}
```

`permissionDecisionReason` surfaces verbatim to Claude. Source: https://code.claude.com/docs/en/hooks.

### `async: true` PostToolUse hooks race subsequent reads

When `track-touched-files.sh` is async, the next Bash tool call (e.g. `coordinator-safe-commit` from `/handoff`) can read `touched.txt` before the hook has appended — same-session files get misclassified as orphans and rejected with "No staged scope detected."

**Rule:** for any hook whose output is consumed by the very next tool call, keep the matcher synchronous. The script is ~70ms; the 5s timeout is plenty.

### "LSP/watcher reverts my writes" is a TEXT-ONLY hallucination variant

No PostToolUse hook can revert a write — by the time it fires the file is already on disk. When executors in parallel dispatch report "the watcher is reverting writes," verify with `ls -la <path>` (almost always the file is fine) and treat as the hallucination class. Inline the anti-hallucination preamble at agent identity AND in dispatch prompts; verify on disk, not via DONE replies.

## MCP

### User-scope MCP entries silently override plugin `.mcp.json` of the same name

Scope precedence is **Local > Project > User > Plugin.** A leftover user-scope `mcpServers.<name>` in `~/.claude.json` (often from pre-plugin manual setup) wins over an identical plugin entry — the plugin's copy is dropped with a "skipped — same command/URL" warning, and the MCP no longer toggles with plugin enable/disable.

**Audit and clean up:**

```bash
claude mcp remove <name> --scope user
```

when adopting plugin-managed MCPs.

### Source-path MCP registrations make "install vN" a near-no-op

When a consumer's MCP entry in `~/.claude.json` points at a source tree (`X:/project-rag/mcp/server.py`) rather than a pip-installed wheel, the source tree's current HEAD is what executes — `pip show <pkg>` reports a separate, possibly stale wheel. Installer re-runs refresh registration + editable wheel, but the version that *actually runs* is whichever branch is checked out.

Before running an installer for "version N" against a consumer, inspect whether the MCP entry is source-path or wheel-import. If source-path, surface that the actual version gate is the checked-out branch — don't conflate `pip show` output with what the MCP harness boots.

## Plugins

### Plugin enablement is per-project, not user-global

Plugin enablement (`enabledPlugins["<name>@<marketplace>"]`) belongs in `<project>/.claude/settings.local.json`, not `~/.claude/settings.json`. The marketplace and install record stay user-global; the install record uses `scope:"project"` with `projectPath`. See `docs/wiki/plugin-extraction-and-distribution.md` §7 for the full rule.

### Disabling a plugin doesn't uninstall it — cache + entries both need clearing

Setting `enabledPlugins.foo: false` leaves the cache intact (`~/.claude/plugins/cache/<marketplace>/<plugin>/`) and a re-enable instantly resurrects the plugin. For a true uninstall when `claude plugin uninstall` reports "not found in installed plugins" (cache-only loads):

```bash
rm -rf ~/.claude/plugins/cache/<marketplace>/<plugin>/
```

AND delete the `enabledPlugins` key from every project's settings.json — not just flip it false.

### Plugin hooks belong in `hooks/hooks.json`, not user-scope `settings.json`

A SessionStart/PreToolUse/etc. hook registered in `~/.claude/settings.json` works on the author's machine but doesn't follow the plugin to marketplace consumers — install lays down the script but never registers the event. Always ship `hooks/hooks.json` alongside the script in the plugin tree so install auto-wires it.

### Plugin installers must register enablement, not just MCP wiring

Three files need to be touched for slash commands and agents to surface:

- `~/.claude/settings.json` (or `<project>/.claude/settings.local.json`) — `enabledPlugins`
- `~/.claude/plugins/known_marketplaces.json`
- `~/.claude/plugins/installed_plugins.json`

Test installs from a profile that has never run `/plugin install`. See `docs/wiki/plugin-extraction-and-distribution.md` §8.

## Agents and Subagents

### Agent prompt is the only channel that reaches a dispatched agent

Instructions in the EM's CLAUDE.md are invisible to subagents — they only read their own prompt. Any constraint on a dispatched agent's behavior must appear verbatim in the prompt sent to it. (This is doctrine in coord/CLAUDE.md "Agent Prompts Are Self-Contained" — repeated here as a reference for hook/skill authors.)

### Built-in `Plan` and `feature-dev:code-architect` ship read-only

`Agent(...)` calls without a `subagent_type` default to `Plan`, which excludes Write/Edit/NotebookEdit — planners return plan text for the EM to write out instead of persisting it. Override at `~/.claude/agents/Plan.md` and `~/.claude/agents/code-architect.md` with Write/Edit added to enable disk persistence.

### Agent Teams 7-teammate limit requires phased spawning for extra pipeline steps

When adding a step between existing team phases (e.g., atlas sketch between scouts and specialists), dispatch it as a regular subagent — not a teammate. Create tasks upfront with blockers, but delay spawning dependent agents until the subagent completes. The EM isn't freed during this window but the overhead is small (~2-5 min for Haiku work).

### MCP tool names in Agent Teams teammates may differ from parent

Deferred tool names can vary by prefix convention (`mcp__notebooklm__*` vs `mcp__plugin_notebooklm_notebooklm__*`). Always use graduated `ToolSearch`: exact `select:` → keyword `+prefix` fallback → graceful failure. Never hardcode a single naming pattern.

## OS Quirks

### Git Bash on Windows cannot reach 1Password's SSH agent

The agent lives on the Windows-only pipe `\\.\pipe\openssh-ssh-agent`; Git Bash's bundled OpenSSH cannot read it, so `git push` to SSH remotes fails with "Permission denied (publickey)" from Claude Code's Bash tool — even when the same key works in PowerShell.

**Workaround:** route SSH pushes through `powershell.exe -NonInteractive -NoProfile -Command "git ... push ..."`. HTTPS remotes are unaffected (Windows Credential Manager works in either shell). Canonical helper: `coordinator/bin/coordinator-auto-push`.

## Bash Tool

### `cd` persists across Bash tool calls

The Bash tool keeps working-directory state across calls. Convenient when intentional; surprising when not. Prefer absolute paths in long sessions; reserve `cd` for explicit scope changes.

### `run_in_background` kills children on timeout

A backgrounded process killed by the harness's timeout takes its child processes with it. For long-running pipelines that spawn workers, monitor and re-launch rather than relying on the harness to keep the children alive.

## Misc

### Curly-brace tokens in MCP launch args are NOT substituted by Claude Code

If an MCP launcher arg contains `{session_id}` or similar curly-brace placeholders, Claude Code passes them through literally. Substitution is the launcher's responsibility, not the harness's.

### HTML-encoded BOM (`&#xFEFF;`) is a real PS1 failure mode

A PowerShell script with an HTML-encoded BOM at the start fails with cryptic parse errors. When PS1 scripts emitted by tools fail to run, check the first few bytes for encoding artifacts before debugging script logic.
