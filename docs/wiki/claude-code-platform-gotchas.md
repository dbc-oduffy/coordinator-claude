# Claude Code Platform Gotchas

**Provenance:** consolidated 2026-05-05 from `tasks/lesson-triage-2026-05-05/SYNTHESIS.md` §B11.

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

Source: `plugins/coordinator/hooks/scripts/context-pressure-advisory.sh`.

### PreCompact fires without real shrink on subagent-result integration

Claude Code triggers the `PreCompact` event for events that don't actually compress the parent transcript (notably integrating large subagent outputs back into the parent). A bridge that emits "COMPACTION OCCURRED" on every `PreCompact` will spam false alarms on 1M-context sessions.

**Defense:** gate the message on actual transcript-size shrink (≥15%) — record pre-size at `PreCompact`, compare against post-size at the next `PostToolUse`.

### `session_id` reaches hooks but NOT subprocesses

`session_id` arrives in hook stdin JSON but is never exported as `CLAUDE_SESSION_ID` to the EM's interactive Bash. CLI tools that need it (e.g. `coordinator-safe-commit`) must:

- Read a sentinel file written by a SessionStart hook, OR
- Accept it as an arg, OR
- Scan session-dir metadata.

Don't assume the env var exists.

### `CLAUDE_SESSION_ID` unavailable in subagent environments

Confirmed via probe (2026-05-05): `CLAUDE_SESSION_ID` is NOT present in subagent env. Subagent env contains: `AI_AGENT=claude-code_2-1-128_agent`, `CLAUDECODE=1`, `CLAUDE_CODE_ENTRYPOINT=cli`, `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`. No `CLAUDE_SESSION_ID`, no `CLAUDE_PARENT_SESSION_ID`.

`$PPID = 1` (Cygwin/MSYS shim — no real parent visible). `tty` returns "not a tty". Side-channel signals also dead. Session-ID-based cross-session linkage via env is infeasible.

**Defense:** Use on-disk state (sentinel files). `session-init.sh:77` writes the current `session_id` to `.git/coordinator-sessions/.current-session-id` on every SessionStart — read this sentinel from shell scripts that need it.

Source: `tasks/probes/2026-05-05-probe-0-1-results.md`.

## Git — Windows-Specific

### Mixed-case branch ref on Windows case-insensitive filesystem

On Windows, `.git/HEAD` can store a mixed-case ref name (`work/<MACHINE>/2026-05-07`) while the on-disk canonical ref is lowercase (`work/<machine>/2026-05-07`). `git branch --show-current` returns HEAD's stored case (uppercase). `git push origin <uppercase>` fails with "cannot be resolved to branch" because the remote resolves against the on-disk canonical.

**Root cause:** `lib/coordinator-daily-branch.sh:129` normalizes input to lowercase before the allow-list check (`cs_is_allowed_branch`), silently accepting non-canonical mixed-case branch creation.

**Defense-in-depth** (all four now in place):
1. Runtime fix: `coordinator-auto-push` is case-agnostic in branch ref handling
2. Creation-time tripwire: `cs_is_canonical_branch` in the hook rejects mixed-case at `git checkout -b` time
3. Migration helper: `bin/migrate-branch-canonical-case.sh` (idempotent rename: local + remote)
4. Doctrine: `daily-branch-discipline.md` updated with span-aware rename flow

Source: `archive/handoffs/2026-05-07_101517_https-autopush-credential-failure.md`, `archive/specs/2026-05-07-mixed-case-branch-creation-tripwire.md` (formerly `docs/plans/...` @ d0fcc842).

### `git push` from hook subprocess — Windows Credential Manager access

`git push` from a post-commit hook subprocess may fail to reach the Windows Credential Manager that the interactive session has populated. HTTPS remotes take the `git push` direct path in the same bash subprocess executing the hook. Failure is silent unless `.git/push-failures.log` is monitored.

**Workaround:** `coordinator-auto-push` routes through `powershell.exe -NonInteractive -NoProfile` for SSH remotes (where 1Password-agent is inaccessible from Git Bash OpenSSH). For HTTPS remotes, the same routing provides credential access via Windows OpenSSH.

Source: `archive/handoffs/2026-05-07_101517_https-autopush-credential-failure.md`.

### PreToolUse deny: use JSON output, not exit 2

The exit-1-vs-2 distinction is a footgun (exit 1 is non-blocking; only exit 2 blocks). Modern interface — emit on stdout with exit 0:

```json
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "..."}}
```

`permissionDecisionReason` surfaces verbatim to Claude. Source: https://code.claude.com/docs/en/hooks.

### `async: true` PostToolUse hooks race subsequent reads

When `track-touched-files.sh` is async, the next Bash tool call (e.g. `coordinator-safe-commit` from `/handoff`) can read `touched.txt` before the hook has appended — same-session files get misclassified as orphans and rejected with "No staged scope detected."

**Rule:** for any hook whose output is consumed by the very next tool call, keep the matcher synchronous. The script is ~70ms; the 5s timeout is plenty.

### `track-touched-files.sh` PostToolUse hook must be synchronous

If `track-touched-files.sh` runs with `async: true`, it races against `coordinator-safe-commit`'s reads of `touched.txt`. This causes same-session files to be misclassified as orphans ("owned by another session"), leading to scope-sweep failures where the commit absorbs files from concurrent sessions. Fix: set `async: false` (default) on this hook.

Source: `archive/completed/2026-04.md` (2026-04-28 entries).

### "LSP/watcher reverts my writes" is a TEXT-ONLY hallucination variant

No PostToolUse hook can revert a write — by the time it fires the file is already on disk. When executors in parallel dispatch report "the watcher is reverting writes," verify with `ls -la <path>` (almost always the file is fine) and treat as the hallucination class. Inline the anti-hallucination preamble at agent identity AND in dispatch prompts; verify on disk, not via DONE replies.

## MCP

### Variable substitution — `{token}` placeholders are NOT expanded in launch args

Claude Code does NOT substitute `{token}` curly-brace placeholders in MCP server launch args — they pass through literally to the server's CLI. Use absolute paths or env-var expansion (`$VAR` at the harness shell layer) instead. (See also `## Misc` § curly-brace tokens for the failure shape.)

### Scope precedence — user-scope entries silently shadow plugin entries

MCP server precedence: user-scope (`~/.claude.json` mcpServers block) > project-scope (`<project>/.mcp.json`) > plugin-scope (`plugins/<name>/.mcp.json`). User-scope entries silently shadow plugin entries with the same server name — debugging this requires `claude mcp list` to see the resolved set.

### User-scope MCP entries silently override plugin `.mcp.json` of the same name

Scope precedence is **Local > Project > User > Plugin.** A leftover user-scope `mcpServers.<name>` in `~/.claude.json` (often from pre-plugin manual setup) wins over an identical plugin entry — the plugin's copy is dropped with a "skipped — same command/URL" warning, and the MCP no longer toggles with plugin enable/disable.

**Audit and clean up:**

```bash
claude mcp remove <name> --scope user
```

when adopting plugin-managed MCPs.

### Source-path MCP registrations make "install vN" a near-no-op

When a consumer's MCP entry in `~/.claude.json` points at a source tree (`X:/<your-rag-indexer>/mcp/server.py`) rather than a pip-installed wheel, the source tree's current HEAD is what executes — `pip show <pkg>` reports a separate, possibly stale wheel. Installer re-runs refresh registration + editable wheel, but the version that *actually runs* is whichever branch is checked out.

Before running an installer for "version N" against a consumer, inspect whether the MCP entry is source-path or wheel-import. If source-path, surface that the actual version gate is the checked-out branch — don't conflate `pip show` output with what the MCP harness boots.

### User-scope MCP entry overrides plugin-scope entry silently

If `~/.claude.json` has a user-scope `mcpServers.<name>` entry AND a plugin provides the same name (same command/URL), the user-scope entry wins. The plugin's copy is dropped with "skipped — same command/URL" warning, and the 35 tools load regardless of plugin enable/disable state (because the user-scope entry is always active). Plugin lifecycle no longer controls tool loading.

**Fix:** `claude mcp remove <name> --scope user`. Scope precedence: Local > Project > User > Plugin.

Source: `archive/completed/2026-04.md` (2026-04-28).

### PostToolUse JSON does not carry parent-session pointer

PostToolUse hook JSON does not carry a parent-session pointer. Session isolation between EM and dispatched agents is complete at both the env and hook levels. Cross-session tracking must use on-disk state, not process-level signals.

Source: `tasks/probes/2026-05-05-probe-0-2-results.md`.

## Python / Windows Tooling

### `python3` may not be on PATH on Windows hosts

On many Windows hosts, `python3` is NOT on PATH. Only `python` (e.g. Python 3.13) and `py` (launcher) are available. Scripts gating on `command -v python3` exit silently. `jq` is also frequently absent on Windows.

**PYTHON_BIN resolver pattern:**
```bash
if command -v python3 &>/dev/null; then PYTHON_BIN=python3
elif command -v python &>/dev/null; then PYTHON_BIN=python
elif command -v py &>/dev/null; then PYTHON_BIN=py
else echo "ERROR: no Python found" >&2; exit 1; fi
```

Use `$PYTHON_BIN` everywhere instead of hardcoding `python3`. For JSON: prefer Python-with-fallback-resolver over `jq` since jq is not guaranteed.

Source: `tasks/tier-usage-telemetry-fix/spec.md`, `archive/completed/2026-05.md`.

### Windows console window flash — process window flags

Processes spawned from hooks (post-commit, SessionStart) may open console windows on Windows when the parent has no console (e.g. spawned under `pythonw.exe` or from Claude's windowless process). Each child that inherits no console gets a fresh one allocated.

**Fix pattern:**
- Shell: `powershell.exe -NonInteractive -NoProfile -WindowStyle Hidden`
- Python subprocess: `creationflags=subprocess.CREATE_NO_WINDOW`
- Registry: `HKCU\Console\%%Startup\Delegation{Console,Terminal}` — switch from Windows Terminal to Console Host so allocations don't open focus-stealing WT tabs

Source: `archive/completed/2026-05.md` (2026-05-07 PowerShell flash fix).

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

### Disabling a hook means removing the settings.json reference, not just renaming the script

When a hook script is disabled or removed, prune its registration from `settings.json` (and any plugin `hooks/hooks.json`) in the same commit. Leaving the registration in place with the script renamed/removed leads to silent invocation failures on future sessions and noisy "command not found" entries in hook logs. The reverse direction — the registration is the source of truth, the script is what the registration calls.

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

### Agent Teams — billing/auth gate recovery differs by scope

Recovery from a billing/auth gate differs by scope — a SINGLE agent's gate (1M-context billing on one Sonnet teammate) is resumed via `SendMessage` to that agent after the gate clears; a GLOBAL gate (account-wide auth expiry) requires fresh redispatch because all transcripts may be stale. Probe scope with `claude api ping` before deciding. (Refines the doctrine in CLAUDE.md § Agent Teams.)

### Subagents lack the `Agent` tool — multi-phase fan-out must originate from EM

A dispatched subagent does NOT have `Agent` in its tool surface; it cannot spawn other subagents. Multi-phase pipelines (scout → specialists → synthesizer, or fan-out + fan-in) must therefore originate from the EM session — each phase boundary is a Tool surface the subagent doesn't have. Authors who write "the scout dispatches the specialists" in a skill body are describing a shape the platform doesn't support; the EM must hold the wave map and re-dispatch at each phase.

**Workaround for genuine teammate-to-teammate coordination:** Agent Teams (`TeamCreate` / `SendMessage` / shared `TaskList`) — that's the platform's answer for multi-agent coordination without going back through the EM. Use Teams for blocking chains (scout → specialists → synthesizer); use EM-driven re-dispatch for serial fan-out where the EM owns the wave decisions.

### MCP tool names in Agent Teams teammates may differ from parent

Deferred tool names can vary by prefix convention (`mcp__notebooklm__*` vs `mcp__plugin_notebooklm_notebooklm__*`). Always use graduated `ToolSearch`: exact `select:` → keyword `+prefix` fallback → graceful failure. Never hardcode a single naming pattern.

## OS Quirks

### Hot-path PowerShell invocations must include `-WindowStyle Hidden`

Any `powershell.exe` or `pwsh` call that fires on every hook event (e.g. `coordinator-auto-push` on every PostToolUse commit, or `hooks.json` SessionStart on every boot/compact) must include `-WindowStyle Hidden` to suppress the brief blue console flash that appears on Windows even for sub-second invocations.

**Rule:** `-NonInteractive -NoProfile -WindowStyle Hidden` is the standard preamble for all coordinator shell invocations on Windows. The tripwire `bin/verify-no-powershell-flash.sh` greps shell scripts and `hooks.json` to catch bare invocations in coordinator and sibling plugins (game-dev, holodeck).

**Empirical source:** `tasks/lessons.md:171` — fixed in commits 2b762da (install side) + 45fbf63 (coordinator-claude), 2026-05-07.

### Git Bash on Windows cannot reach 1Password's SSH agent

The agent lives on the Windows-only pipe `\\.\pipe\openssh-ssh-agent`; Git Bash's bundled OpenSSH cannot read it, so `git push` to SSH remotes fails with "Permission denied (publickey)" from Claude Code's Bash tool — even when the same key works in PowerShell.

**Workaround:** route SSH pushes through `powershell.exe -NonInteractive -NoProfile -WindowStyle Hidden -Command "git ... push ..."`. HTTPS remotes are unaffected (Windows Credential Manager works in either shell). Canonical helper: `coordinator/bin/coordinator-auto-push`.

## Bash Tool

### `cd` persists across Bash tool calls

The Bash tool keeps working-directory state across calls. Convenient when intentional; surprising when not. Prefer absolute paths in long sessions; reserve `cd` for explicit scope changes.

### `run_in_background` kills children on timeout

A backgrounded process killed by the harness's timeout takes its child processes with it. For long-running pipelines that spawn workers, monitor and re-launch rather than relying on the harness to keep the children alive.

## Misc

### Curly-brace tokens in MCP launch args are NOT substituted by Claude Code

If an MCP launcher arg contains `{session_id}` or similar curly-brace placeholders, Claude Code passes them through literally. Substitution is the launcher's responsibility, not the harness's.

### PowerShell `@`-splat does not preserve `[switch]` semantics through string arrays

Wrapper scripts forwarding flags via `& downstream.ps1 @PassThrough` where `PassThrough` is `[string[]]` silently drop `[switch]` flags downstream — the downstream parameter binds to `$false` rather than receiving the switch. Translate switches to env vars (or explicit `-Switch:$true` calls) at the wrapper-to-downstream seam. Bash positional pass-through (`"$@"`) does not have this gap.

### HTML-encoded BOM (`&#xFEFF;`) is a real PS1 failure mode

A PowerShell script with an HTML-encoded BOM at the start fails with cryptic parse errors. When PS1 scripts emitted by tools fail to run, check the first few bytes for encoding artifacts before debugging script logic.

### `pythonw.exe` swallows stdout/stderr — diagnostic output disappears

Scripts launched via `pythonw.exe` (windowless Python on Windows) have no attached console, so `print()`/`sys.stderr.write()` go to `os.devnull`. Logging that "works" under `python.exe` produces zero diagnostic output under `pythonw.exe` — typical failure shape is "script ran, no output, no error, no idea why it didn't do the thing." Defense: route diagnostics to a file via `logging.FileHandler` (not `StreamHandler`); never assume stdout is captured.

### PE subsystem flag determines whether a Windows binary gets a console

A Python launcher (or any Windows binary) compiled with the GUI subsystem (`/SUBSYSTEM:WINDOWS`) has no console attached at startup; a binary compiled with the CONSOLE subsystem (`/SUBSYSTEM:CONSOLE`) always allocates one. The `.exe` name (`python.exe` vs `pythonw.exe`) is a hint, not a contract — inspect the PE header (`dumpbin /headers <exe>` or `pwsh: (Get-Item exe).VersionInfo`) to confirm subsystem before debugging "why did/didn't a console window appear." This is the layer underneath the `creationflags=CREATE_NO_WINDOW` workaround.

### `asyncio.wait_for(coro, timeout=0)` raises `TimeoutError` immediately, never awaits the coro

`timeout=0` is not "no timeout" — it's "expire immediately." The coroutine is scheduled but cancelled on the next loop tick before any work runs. Anyone reading the call site expects either "fire-and-forget" or "no timeout"; both are wrong. Use `None` for no timeout or a positive float for an actual budget.

### MSYS/Git-Bash auto-translates POSIX-looking paths in argv

When a Bash script passes `/foo/bar` as an argument to a non-MSYS binary (e.g. `node`, `python`, `claude`), MSYS/Git-Bash silently rewrites it to a Windows path (`C:\Program Files\Git\foo\bar`) — sometimes prepending the Git install dir. Defense: prefix with `//` (`//foo/bar`) to disable translation, or set `MSYS_NO_PATHCONV=1` for the invocation. Symptom: a flag whose value is a literal POSIX-shaped string (URL paths, JSON pointers, regex patterns) arrives mangled at the receiving binary.

### Stale `node` / `python` / TS-build processes survive session boundaries

Killing the Claude Code session does NOT kill backgrounded `node`/`python` workers or watch-mode TS builds that the session spawned. They keep holding file locks, port bindings, and stale compiled `.js` output until the host OS reaps them or the user kills them by hand. The next session sees "files updated but behavior unchanged" — that's the prior session's daemon still serving from memory. Defense: `taskkill /F /IM node.exe` (Windows) or `pkill -f node` (POSIX) at session boundaries when long-running watchers were in play; never trust "I rebuilt the TS" if the watch-mode build from the prior session is still resident.

### Cross-platform script portability — `#!/usr/bin/env bash` is necessary but not sufficient

A shell script that uses `realpath`, `readlink -f`, GNU-extension flags (`sed -i ''` vs `sed -i`), `mktemp` without `-d`, or assumes `/dev/stdin` works the same way on every platform will fail loudly on macOS or Windows Git-Bash even with a portable shebang. Defense: pin to documented-portable subset, or detect host (`uname -s`) at top and dispatch. Treat "works on Linux CI" as a non-claim about author/consumer machines.
