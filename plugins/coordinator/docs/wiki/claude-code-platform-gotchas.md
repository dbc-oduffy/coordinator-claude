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

### `session_id` in subprocesses — `CLAUDE_CODE_SESSION_ID` (the var name matters)

**Update 2026-05-23 (Claude Code 2.1.150):** the platform now exports
`CLAUDE_CODE_SESSION_ID` into every tool subprocess. This supersedes the
"never exported / use a sentinel" guidance below — but note the **name**: the
platform sets `CLAUDE_CODE_SESSION_ID`, NOT `CLAUDE_SESSION_ID`. Coordinator
code that only checked `CLAUDE_SESSION_ID` (the name no platform version ever
set) silently fell through to the clobberable sentinel for months. Probe both
the EM's interactive Bash and a subagent's Bash and you get the **same** value:
the subagent inherits the *dispatching* EM's id — exactly the cross-session
linkage that the `.agents/<aid>/em-session-id.txt` back-pointer reconstructs the
hard way. Per-session and unclobberable by a sibling session's SessionStart.

Resolution precedence the helpers now use (`coordinator-safe-commit`,
`coordinator-write-review-trail.sh`, `coordinator-session-loe.sh`,
`cs_claim_handoff`):

1. `CLAUDE_SESSION_ID` — explicit override (manual / test harness).
2. `CLAUDE_CODE_SESSION_ID` — platform-injected, authoritative for the session.
3. `.git/coordinator-sessions/.current-session-id` sentinel — last-writer-wins
   fallback, only reached on old Claude Code (≤ 2.1.128 did not export the var).
4. PID scan of session-dir metadata.

**Historical (≤ 2.1.128):** `CLAUDE_SESSION_ID` was NOT present in any env —
EM Bash or subagent. Probe (2026-05-05): subagent env had `CLAUDECODE=1`,
`CLAUDE_CODE_ENTRYPOINT=cli`, `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`, no
session id; `$PPID = 1` (Cygwin/MSYS shim), `tty` "not a tty", side channels
dead. The sentinel (`session-init.sh` writes it on every SessionStart) was the
only mechanism. It remains the fallback for those versions.

Sources: `tasks/probes/2026-05-05-probe-0-1-results.md` (historical); live probe
2026-05-23 on 2.1.150 (env var present in EM + subagent, identical value).

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

### Windows bash / CRLF — `bash -n` false-positives on heredoc-heavy scripts

On a Windows working tree with `git config core.autocrlf=true`, `bash -n` false-positives on heredoc-heavy installers: CRLF makes the closer line (`DELIM\r`) not match the opener, so the heredoc swallows to EOF and bash reports a bogus "syntax error near unexpected `fi`". The committed LF blob is clean — `git show HEAD:<path>` has zero CRLF while the working tree has thousands. Before treating a `bash -n` heredoc/`fi` error on an installer as a real defect, check `git config core.autocrlf` + the committed blob's line endings (`git show HEAD:<path>` piped to a CR counter). **Use ShellCheck (the real lint, run in `/workweek-complete`) as the syntax gate on installers, not `bash -n`.** Source: 2026-05-24 project-rag `install-project-rag-plugin.sh` (SC1017 literal-CR rabbit hole; 0 CRLF in the committed blob, 3132 in the working tree).

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

**Prefer `py -3` over the command-v chain when the Python Launcher is available.** `py.exe` (the Python Launcher, bundled with the python.org installer) is more reliable on Windows than either `python3` (absent on many installs) or `python` (may resolve conda/embedded variants). Updated preference order for hook-chain scripts:

```bash
if command -v py &>/dev/null; then PYTHON_BIN="py -3"
elif command -v python &>/dev/null; then PYTHON_BIN=python
else echo "ERROR: no Python found" >&2; exit 1; fi
```

Apply the `WindowsApps` exclusion if using `command -v python3`:
```bash
_path=$(command -v python3 2>/dev/null)
case "$_path" in */WindowsApps/*|*\\WindowsApps\\*) _path="" ;; esac
```

**Cross-repo resolver shape.** The correct propagation shape for this resolver is shape α: document the pattern in `docs/wiki/windows-cmd-shims.md`, vendor per-repo. Shape β (shared `~/.claude/lib/resolve-python.sh` runtime lib) is deferred until a third unique callsite needs the same fix. Shape γ (registry mutation to disable App Execution Aliases) is explicitly rejected — operator system-state mutation is out of our lane. → DR-059.

Source: `archive/completed/2026-05.md`.

### Windows Open-With picker flood — ShellExecute + AppX Execution Alias

**Root cause (2026-05-19, Striker empirical).** The Claude Code harness and MCP layer may call `ShellExecuteEx` (not `CreateProcess`) when launching hook scripts or Python MCP scripts — especially via Node's `child_process.exec` / `.NET Process.Start(UseShellExecute=true)`. Unlike `CreateProcess`, `ShellExecute` treats unresolvable names as documents and falls back to the file-association picker GUI. Two common Windows configurations trigger picker-flood across all concurrent sessions:

1. **Extensionless names** (e.g. bare `machine-local`) — `ShellExecute` walks `PATHEXT`, hits `.py` association, pops picker.
2. **`python3` with an orphan AppX stub** — `%LOCALAPPDATA%\Microsoft\WindowsApps\python3.exe` exists as a zero-byte reparse point after uninstalling the Store Python package. The AppX App-Execution-Alias subsystem is consulted **independently** of PATH; a broken stub opens the picker without ever reaching the PATHEXT fallthrough. Shell-level invocations (git-bash, PowerShell, cmd.exe) do NOT reproduce this — the flood originates from Windows API calls inside the harness.

**Fix:** `coordinator:setup` Step 3 installs `machine-local.cmd` and `python3.cmd` shims on the Windows user PATH, and Step 3c runs a health check (detect orphan reparse-point stubs, detect Store-alias-on-PATH, detect missing Python). The shims are found by `CreateProcess` before any `ShellExecute` fallback fires.

**Upstream:** Anthropic upstream filing explicitly deferred by PM — the harness-side ShellExecute-vs-CreateProcess behavior is the root cause we cannot fix from substrate.

→ Full detail: `docs/wiki/windows-cmd-shims.md`.

### Windows console window flash — process window flags

Processes spawned from hooks (post-commit, SessionStart) may open console windows on Windows when the parent has no console (e.g. spawned under `pythonw.exe` or from Claude's windowless process). Each child that inherits no console gets a fresh one allocated.

**Fix pattern:**
- Shell: `powershell.exe -NonInteractive -NoProfile -WindowStyle Hidden`
- Python subprocess: `creationflags=subprocess.CREATE_NO_WINDOW`
- Registry: `HKCU\Console\%%Startup\Delegation{Console,Terminal}` — switch from Windows Terminal to Console Host so allocations don't open focus-stealing WT tabs

Source: `archive/completed/2026-05.md` (2026-05-07 PowerShell flash fix).

### Windows bootstrap test harnesses must set `windowsHide` / `CREATE_NO_WINDOW` explicitly

Bootstrap test harnesses on Windows (e.g., Python `subprocess.Popen`, Node `child_process.spawn`) must set `windowsHide=True` or the `CREATE_NO_WINDOW` creation flag explicitly — changing the Windows Terminal default profile does NOT suppress console windows for spawned processes. The registry key that controls actual delegation behavior is `HKCU\Console\%%Startup\Delegation` (both `DelegationConsole` and `DelegationTerminal`); flipping it from Windows Terminal to Console Host prevents focus-stealing WT tabs from appearing on every subprocess spawn.

**Rule:** never assume a WT profile change has made subprocess windows invisible. Flag `windowsHide` / `CREATE_NO_WINDOW` is the only reliable per-process suppression.

Source: central improvement queue (2026-05-06).

## Plugins

### `CLAUDE_PLUGIN_ROOT` resolves to the plugin install dir (marketplace source subdir), not the repo root

For a marketplace plugin whose `marketplace.json` sets `source: "./plugin"`, `${CLAUDE_PLUGIN_ROOT}` resolves to the **plugin install dir = that subdir** (`<repo>/plugin`), NOT the repo / marketplace-checkout root. Consequences for path references in command/lib files:

- `${CLAUDE_PLUGIN_ROOT}/commands/lib/...` — correct.
- `${CLAUDE_PLUGIN_ROOT}/plugin/commands/...` — DOUBLES to `…/plugin/plugin/…` (wrong).
- `${CLAUDE_PLUGIN_ROOT}/../project_scripts/...` — correct for a repo-root sibling (the `../` climbs out of `plugin/`).

**Mechanical agent extraction of command bodies is a known source of wrong-prefix path bugs** — agents invent variables (`$PLUGIN_ROOT` for the canonical `${CLAUDE_PLUGIN_ROOT}`) and propagate wrong prefixes that existence/inventory tripwires don't catch (every wrong path is non-empty, it just points at nothing). **Smoke-test resolved paths with the correct root:** `export CLAUDE_PLUGIN_ROOT=<repo>/plugin && ls "${CLAUDE_PLUGIN_ROOT}/<resolved-rel-path>"` for one helper per call shape. Authority for the contract is an executable test that hardcodes the root (e.g. `tests/install/test_claude_plugin_root_resolution.py`). Source: 2026-05-21/23 project-rag `doctor.md` extraction (118 doubled-prefix + 72 missing-`../` fixes).

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

`Agent(...)` calls without a `subagent_type` default to `Plan`, which excludes Write/Edit/NotebookEdit — planners return plan text for the EM to write out instead of persisting it. Override at `~/.claude/agents/Plan.md` with Write/Edit added to enable disk persistence. The coordinator plugin ships its own `code-architect` agent at `plugins/coordinator/agents/code-architect.md` with Write/Edit enabled.

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

### Auto-discovery globs sweep stale backups in "env var → glob fallback" config layers

Config loaders that resolve via `env var → fallback to glob` (e.g., path discovery for plugin roots, project config) will match `*backup*`, `*.bak*`, `*-bak*`, and `*.partial` files alongside live config — stale backups silently shadow the canonical config and produce hard-to-diagnose misbehavior.

**Mitigation:** either exclude backup-pattern suffixes explicitly in the glob, OR require explicit registration (no glob-based auto-discovery at all). Applies to any layered config system where a glob serves as last-resort discovery.

Source: central improvement queue (2026-04-29, claude-unreal-holodeck).

### Externally-visible action scripts need an env-var bypass for /dev/tty-less environments

*2026-05-17, project-rag-ue-addon.* Scripts that gate destructive or irreversible actions on an interactive `read` from `/dev/tty` (e.g. "Are you sure? [y/N]") fail loudly when run from Claude Code's Bash tool, CI runners, headless workers, or any environment where `/dev/tty` is not available — `read` errors immediately and the script aborts before the confirmation can be supplied.

**Defense:** action scripts that ship as part of a plugin or operator-facing tool must accept an env-var bypass (e.g. `CONFIRM_DESTRUCTIVE=1`, `ALLOW_NO_TTY=1`, or a script-specific name). The bypass replaces the `/dev/tty read` step; the env-var presence serves as affirmative confirmation. Document the bypass in the script's `--help` and any operator-facing docs.

```bash
if [[ -z "${CONFIRM_DESTRUCTIVE:-}" ]]; then
  read -p "Confirm destructive action [y/N] " ans </dev/tty
  [[ "$ans" =~ ^[Yy]$ ]] || { echo "aborted"; exit 1; }
fi
```

Same pattern for `gum confirm`, `whiptail`, `dialog`, and any other TTY-bound primitive.

### Cross-platform script portability — `#!/usr/bin/env bash` is necessary but not sufficient

A shell script that uses `realpath`, `readlink -f`, GNU-extension flags (`sed -i ''` vs `sed -i`), `mktemp` without `-d`, or assumes `/dev/stdin` works the same way on every platform will fail loudly on macOS or Windows Git-Bash even with a portable shebang. Defense: pin to documented-portable subset, or detect host (`uname -s`) at top and dispatch. Treat "works on Linux CI" as a non-claim about author/consumer machines.

### `gh release upload` aborts the entire batch on a 0-byte asset

*2026-05-17, project-rag-ue-addon.* When `gh release upload <tag> file1 file2 ...` receives any zero-byte file in the argument list, the GitHub API rejects that asset with a 422 and `gh` exits non-zero — every remaining asset in the batch is dropped, not just the empty one. Defense: filter `-size +0c` (or `find ... -not -empty`) before the call, or run one-asset-per-call with `|| true` and a tally at the end. Surfaces empirically when a release-builder writes placeholder files for "no work this round" cases.

### Self-rewriting tools need a self-validation guard, not just a filename-exclusion

*2026-05-17, claude-central.* Sanitizers, sed-fleet linters, and codegen passes that process their own source need TWO defenses against self-corruption, not one. Filename-exclusion (`case "$base" in *<self>*) return 0 ;;`) prevents NEW corruption from this point forward but cannot detect EXISTING corruption from before the exclusion was added — and the script's "rewrote N file(s)" log typically fires unconditionally after the I/O block, hiding the no-op. Defense:

1. **Self-exclusion** to prevent future corruption.
2. **Self-validation guard at script start** that detects already-substituted state (e.g. canonical key fingerprint missing, or substitution targets present where keys should be) and exits loud with `"restore <self> from <upstream-source> before re-running"`.
3. **Conditional success log** — `cmp` before/after the I/O block and report `"rewrote: N file(s) (M unchanged)"`, not unconditional `"rewrote: <count>"`.

Two-phase failure shape: corruption happens once, then becomes invisible. "Rewrote" log fired = file touched, not = file changed.

### PowerShell 5.1 strips embedded double-quotes in native-command args — use temp file for JSON

*2026-05-24, claude-unreal-holodeck.* PowerShell 5.1's native-command invocation strips embedded double-quote characters when passing a string argument to an external executable. A JSON payload passed inline as a native-command argument (e.g. `my-tool --config '{"key":"value"}'`) arrives at the process with the double-quotes stripped, producing malformed JSON. Defense: write the JSON payload to a temp file and pass `--config-file <path>` (or equivalent file-path argument) instead. This affects any tool invoked from a PowerShell 5.1 context (including Claude Code's Bash tool on Windows when the shell is PowerShell), any JSON argument with non-trivial structure. PowerShell 7.x improves this, but the fix via temp file is portable across both versions. (Source: 2026-05-24 claude-unreal-holodeck)

### PowerShell here-string `@'…'@` silently corrupts commit subjects in Bash tool

*2026-05-24, project-rag-ue-addon.* When a Bash tool invocation uses a PowerShell here-string (`@'…'@`) to supply a multi-line git commit message, the resulting commit subject may be corrupted — the here-string is interpreted by PowerShell before being passed to Bash, and the line-ending handling differs. The commit subject arrives as an empty string, or the first line of the here-string body is swallowed. Defense: use a POSIX Bash heredoc inside the Bash tool invocation for git commit messages:

```bash
git commit -m "$(cat <<'EOF'
Subject line here

Body line here
EOF
)"
```

PowerShell here-strings are not a safe vehicle for multi-line string literals in Bash tool calls — use Bash heredocs exclusively. (Source: 2026-05-24 project-rag-ue-addon)
