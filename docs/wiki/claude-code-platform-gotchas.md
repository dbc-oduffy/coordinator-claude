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

Source: `plugins/coordinator-claude/coordinator/hooks/scripts/context-pressure-advisory.sh`.

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

### `atexit.register(sys.exit, N)` does not set the process exit code on Python 3.13+ — use `os._exit(N)`

*2026-05-29, project-rag.* On Python 3.13+, an `atexit`-registered handler that calls `sys.exit(N)` does **not** propagate `N` as the process exit code — the `SystemExit` raised inside an atexit callback is caught/ignored by the interpreter's shutdown machinery, and the process exits 0 regardless. A launcher or test-harness that relies on `atexit.register(sys.exit, code)` to signal failure silently reports success. **Fix:** call `os._exit(N)` from the atexit handler (bypasses the normal shutdown path and sets the code directly), or set the exit code before shutdown begins rather than from within an atexit callback. Verify the actual `$?` / `%ERRORLEVEL%`, not just the handler's apparent intent.

## Git — Windows-Specific

### Mixed-case branch ref on Windows case-insensitive filesystem

On Windows, `.git/HEAD` can store a mixed-case ref name (`work/<MACHINE>/2026-05-07`) while the on-disk canonical ref is lowercase (`work/<machine>/2026-05-07`). `git branch --show-current` returns HEAD's stored case (uppercase). `git push origin <uppercase>` fails with "cannot be resolved to branch" because the remote resolves against the on-disk canonical.

**Root cause:** `lib/coordinator-daily-branch.sh:129` normalizes input to lowercase before the allow-list check (`cs_is_allowed_branch`), silently accepting non-canonical mixed-case branch creation.

**Defense-in-depth** (all four now in place):
1. Runtime fix: `coordinator-auto-push` is case-agnostic in branch ref handling
2. Creation-time tripwire: `cs_is_canonical_branch` in the hook rejects mixed-case at `git checkout -b` time
3. Migration helper: `migrate-branch-canonical-case.sh` (idempotent rename: local + remote)
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

### Coordinator scripts are on PATH — `bin/X` and bare `X` are both PATH-namespace, never cwd-relative

The Claude Code harness prepends every installed plugin's `bin/` dir to PATH for tool/hook execution (verify: `echo "$PATH" | tr ':' '\n' | grep -i claude` shows `~/.claude/bin` plus each `plugins/*/bin`). This is harness-provided, not shell-profile provisioned — so it reproduces on every machine running the plugin, the strongest install-surface guarantee we have. A coordinator script (`fan-out-dispatch.sh`, `coordinator-safe-commit`, `check-shipped-on-main.sh`, …) therefore resolves by **bare name from any cwd, in any repo**.

**The core invariant:** both `bin/X` and bare `X` are **PATH-namespace** references — they name "the coordinator bin tool X", which resolves the same from any cwd in any repo. Neither is cwd-relative. The failure to avoid is resolving `bin/X` against the *current repo's* `./bin/` — an EM standing in a consumer repo (`X:\project-rag`) that looks for `./bin/X`, finds nothing, and wrongly concludes the script "isn't mirrored here."

**Citation rule for doctrine prose (CLAUDE.md, wikis, skills, commands):**
- **Invokable scripts** — executable `.sh` and extensionless-executable commands (`fan-out-dispatch.sh`, `check-plugin-drift.sh`, `machine-local`, `cross-repo-memo`) → **cite by bare name**. They resolve on PATH exactly as written; the script's own `Usage:` line is the source of truth and already uses bare name. (2026-05-29: the invokable-script citations across coordinator doctrine were swept from `bin/X` to bare `X`.)
- **Non-bare-invokable tools** — interpreter scripts run via a launcher (`bin/render-handoff-tracker.js` → `node …`, `bin/extract-lessons.py` → `python …`), data files (`bin/doctor-probes.toml`), and tools cited without a uniquely-resolvable name (`bin/query-records` ships both `.sh` and `.js`) → **the `bin/X` shorthand stays only as a prose label, never in a runnable block.** Distinguish two usages:
  - **Label usage** (prose: "prefer `bin/query-records` over static lists", a Tier-2 table cell, a "this is the query engine" reference) → `bin/X` shorthand is correct. It names the namespace tool, not a file; bare `X` would not run, so `bin/X` is the readable label. Still PATH-namespace, still never cwd-relative.
  - **Executable usage** (inside a ```bash block, or any inline command an EM will copy-paste-run verbatim) → **cite the full launcher path: `"$HOME/.claude/plugins/coordinator-claude/coordinator/bin/query-records.sh"`** (matching how every other coordinator bin tool is cited in runnable blocks — `render-template.sh`, `coordinator-auto-push`, etc.). The bare `bin/query-records` shorthand **fails `command not found`** even though `bin/` *is* on PATH (harness-provided, per the invariant above — verified 2026-05-30: `command -v query-records.sh` and `command -v fan-out-dispatch.sh` both resolve). The reason is the **extensionless citation**: `query-records` ships only as `query-records.sh` and `query-records.js`, so there is no file named `query-records` for the bare name to resolve to — `command -v query-records` returns MISSING with `bin/` fully on PATH. (This is the trap in the earlier "bin not on PATH" diagnosis: `command -v query-records` empty does **not** prove `bin/` is off PATH; it proves only that no *extensionless* `query-records` exists. The right probe is `command -v query-records.sh`.) The failure is silent because callers wrap the call in `2>/dev/null`, so command-not-found stderr is swallowed and empty stdout reads as "no records" — a false-negative that masked 5 `ready_to_fire` handoffs in a project-rag workday-start briefing (2026-05-30). A runnable bare-`bin/query-records` (or bare extensionless `query-completions`) block is the bug; reach for the full launcher path. The bare-`.sh` form (`query-records.sh`) also resolves on PATH and is equally correct — option B (full launcher path) is the chosen citation because it carries zero PATH dependency.
- **Filesystem location** ("the hook lives at X", a path you'd `cat`/edit) → full repo-relative path from the plugin root: `plugins/coordinator-claude/coordinator/bin/X`, or the `~/.claude/plugins/.../bin/X` absolute form. Here the prefix is correct because you're naming a file, not a command.

**Windows caveat (extensionless scripts).** Bare-name citation is safe for `.sh`-suffixed scripts. Extensionless coordinator commands (`machine-local`, `cross-repo-memo`) can trip the ShellExecute Open-With picker when launched via Windows API rather than a shell — their `.cmd` shim story (above, and `windows-cmd-shims.md`) is what makes bare invocation safe; don't drop it.

Source: 2026-05-29 — `fan-out-dispatch.sh` doctrine citations read as repo-relative and misled the EM in a consumer repo. Root cause: `bin/X` is PATH-namespace shorthand, not a real path (the script lives under `plugins/.../coordinator/bin/`, never `~/.claude/bin/`). Resolved by sweeping invokable-script citations to bare name and documenting the namespace invariant for the rest.

### `os.kill(pid, 0)` is a Windows suite-killer, not a POSIX liveness probe

*2026-05-30, sibling-repo universal.* The POSIX idiom `os.kill(pid, 0)` ("send signal 0 to test whether the process exists") **does not port to Windows**. On win32, Python maps signal `0` to `CTRL_C_EVENT` and routes it through `GenerateConsoleCtrlEvent`, which delivers a Ctrl-C to the **process GROUP** — so "liveness-checking" your own PID (or a recycled PID that now belongs to the test runner) sends Ctrl-C to the caller. In a test suite this is a deterministic suite-killer: the liveness probe terminates the harness that issued it.

**Rule:** on Windows, never use `os.kill(pid, 0)` for a liveness check. Use `psutil.pid_exists(pid)` (cross-platform, side-effect-free). Guard any remaining `os.kill(pid, 0)` behind `if os.name != "nt"`. (NB: this is the general platform rule; a project-scoped instance with a named locus — project-rag's `embed_sidecar` — is tracked separately in that repo and is not superseded by this entry.)

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

### Accepting bypass-permissions mode clobbers `settings.json` down to a 3-line stub

**Symptoms:** all coordinator slash commands vanish mid-session or at next launch. Plugin agents missing. `enabledPlugins` empty. `/help` shows only built-in skills. Hook registrations gone. The marketplace registry, model pin, env vars, permission allow-list, and skill overrides are all gone too.

**Diagnosis (run first):**

```bash
git diff settings.json
```

A clobbered file looks like this — three lines, single key:

```json
{ "skipDangerousModePermissionPrompt": true }
```

The HEAD version is the full coordinator install (typically 60–100 lines: `enabledPlugins`, `extraKnownMarketplaces`, `model`, `env`, `permissions`, `skillOverrides`, `hooks`). Bypass-mode acceptance writes a stub containing **only** the `skipDangerousModePermissionPrompt: true` flag — and that flag is already present in the full HEAD version, so the clobber drops everything novel.

**Recovery:**

```bash
git checkout HEAD -- settings.json
```

If `package.json` and other coordinator-infra files were also nuked in the same write, restore them too (`git checkout HEAD -- package.json`). The bypass flag survives the restore (it's in HEAD). MCP auth caches (`mcp-needs-auth-cache.json`) are regenerable — leave them deleted if you don't need the affected MCP.

**Critical caveat — restart required.** `enabledPlugins` changes only take effect at Claude Code start. The plugins lost from session-state will **not** reappear in the current session after `git checkout`; coordinator commands return at next `/exit` + relaunch.

**SessionStart-hook self-heal is impossible (chicken-egg).** A SessionStart hook that diffs settings.json and auto-restores would seem like the right defense, but it can't run: a gutted `enabledPlugins` means the coordinator plugin doesn't load, which means its hooks don't register, which means the self-heal never fires. The defense must be either pre-launch (external script) or post-launch-with-manual-restart.

**Recurrence pattern.** Recurred twice within ~24h (2026-05-27, 2026-05-28) on the same machine. Trigger appears to be accepting the bypass-mode permission dialog at certain harness moments — exact reproducer not yet isolated. Each recurrence requires the same `git checkout HEAD -- settings.json` + restart cycle. If you've been clobbered, expect it may happen again — keep the recovery command handy.

**Grep keywords (for future-you finding this):** `coordinator commands vanished`, `coordinator commands missing`, `plugins disappeared`, `enabledPlugins empty`, `enabledPlugins clobbered`, `settings.json shrunk`, `settings.json 3 lines`, `skipDangerousModePermissionPrompt only`, `bypass mode clobber`, `dangerous mode wrote settings.json`.

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

`Agent(...)` calls without a `subagent_type` default to `Plan`, which excludes Write/Edit/NotebookEdit — planners return plan text for the EM to write out instead of persisting it. Override at `~/.claude/agents/Plan.md` with Write/Edit added to enable disk persistence. The coordinator plugin ships its own `code-architect` agent at `plugins/coordinator-claude/coordinator/agents/code-architect.md` with Write/Edit enabled.

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

### Hot-path PowerShell invocations must include `-WindowStyle Hidden` (but that alone does not prevent the flash)

**CORRECTION (docs-checker 2026-05-29):** `-WindowStyle Hidden` is **create-then-hide** — the console window is allocated first, then hidden.  The brief blue flash *is* the allocation; `-WindowStyle Hidden` does not prevent it.  It is the **minimum baseline** (better than nothing — the window is hidden before the user sees it for more than a frame), but it is not true suppression.

**True suppression** requires setting `CREATE_NO_WINDOW` (Win32 `dwCreationFlags=0x08000000`) at the spawning parent's `CreateProcess` call.  From a shell (bash/mintty) context this bit cannot be set — only a native Win32 parent (a compiled shim, or a Node/Python parent using `windowsHide:true` / `creationflags=CREATE_NO_WINDOW` on its own child-spawning call) can set it.

Any `powershell.exe` or `pwsh` call that fires on every hook event (e.g. `coordinator-auto-push` on every PostToolUse commit, or `hooks.json` SessionStart on every boot/compact) must still include `-WindowStyle Hidden` as the required baseline.

**Launcher for python/node spawns we own:** `lib/spawn-hidden.sh` (new, 2026-05-29).  For python spawns where stdin is caller-controlled (heredoc, /dev/null), it resolves to `pythonw.exe` (SUBSYSTEM:WINDOWS) — that IS genuine suppression.  For node and for harness-piped-stdin python, it passes through transparently and documents the gap.  See `lib/spawn-hidden.sh` header for the full mechanism breakdown and `lib/resolve-python.sh` for the stdin-safety caveat.

**The dominant blue `powershell.exe` flash is the PowerShell *tool* backing process — fixed by an explicit settings flag, NOT by removing an env var (2026-05-31 correction).** Claude Code stands up a persistent Windows PowerShell 5.1 backing process whenever the **PowerShell tool** is enabled — that process (re)spawning is the recurring blue flash. Per CC changelog v2.1.143 / v2.1.142 / v2.1.120 the PowerShell tool is now **enabled by default on Windows**, so the 2026-05-29 fix that merely *removed* `CLAUDE_CODE_USE_POWERSHELL_TOOL` silently rotted: with the new default, "absent" means **on**. **Correct fix: set `"CLAUDE_CODE_USE_POWERSHELL_TOOL": "0"` explicitly in `settings.json` → `env` (session restart required — the tool roster is fixed at startup).** The flash persists even when the agent only ever calls the Bash tool, because the *tool being enabled* is what stands up the backing process — preferring bash does not disable it. The agent's toolset does not need PowerShell (everything routes through git-bash), so `"0"` costs nothing.

**ConPTY machine-belt: ABANDONED (2026-05-31, PM call).** An earlier plan proposed making Windows Terminal the default terminal app (`HKCU\Console\%%Startup\Delegation`) so ConPTY suppresses console allocations machine-wide. That was speculative belt-and-suspenders for a flash whose real cause was the PowerShell-tool setting above; the belt experiment + its `console-flash-repro.sh` harness were retired. Do not reintroduce a ConPTY-delegation approach.

**node/python PreToolUse hook flashes (separate from the blue tool flash):** spawned by Claude Code's harness on Write/Edit/MultiEdit, not by our scripts. We cannot set `CREATE_NO_WINDOW` on them from a shell. The only real suppression levers are (a) a compiled no-window launcher shim, or (b) eliminating the console-interpreter spawn (reimplement the hook in the already-running shell). Whether these *visibly* flash — distinct from the now-fixed blue tool flash — was never empirically confirmed (the measuring spike was the abandoned ConPTY belt). Verify by direct observation after the settings fix lands before investing in a shim.

**Child-of-a-child flashes (the class the shell/`hooks.json` grep can't see):** the loudest, hardest-to-diagnose source is a console exe (`powershell.exe`, `git.exe`, `nvidia-smi.exe`, `uv.exe`, `node.exe`) spawned by `subprocess.run`/`Popen` *inside a `.py` module* that itself runs as a child of a console-less parent (an MCP server, a scheduled task, a GUI Claude Code host).  A conftest/main-process monkeypatch that ORs `CREATE_NO_WINDOW` into `subprocess` only patches the process it runs in — a freshly-imported child gets a clean `subprocess` module and flashes.  project-rag chased this for weeks before isolating it (`cross-repo/archive/2026-05-30-windows-popup-child-process-hypothesis.md`).  `verify-no-console-flash.sh` greps shell scripts + `hooks.json` and is structurally blind to this class.  Coordinator's fix: every spawn in a production `.py` module splats a module-local `_NO_CONSOLE_WINDOW = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}`, enforced by `tests/test_no_console_window_guard.py` (tripwire `CONSOLE-FLASH-GUARD-PY`).  Confirmation method when a popup persists: spawn a child `-c` snippet that prints `GetConsoleWindow()` / `IsWindowVisible()` — `HWND=0` means that link in the chain is clean; keep walking outward.

**Rule:** `-NonInteractive -NoProfile -WindowStyle Hidden` remains the required preamble for all coordinator `powershell`/`pwsh` invocations on Windows.  The tripwire `verify-no-powershell-flash.sh` greps shell scripts and `hooks.json` to catch bare invocations in coordinator and sibling plugins.

**Empirical source:** `tasks/lessons.md:171` — original fix in commits 2b762da (install side) + 45fbf63 (coordinator-claude), 2026-05-07.  Mechanism correction verified 2026-05-29 against Node/Python/Win32 docs (issue #15572).

### Git Bash on Windows cannot reach 1Password's SSH agent

The agent lives on the Windows-only pipe `\\.\pipe\openssh-ssh-agent`; Git Bash's bundled OpenSSH cannot read it, so `git push` to SSH remotes fails with "Permission denied (publickey)" from Claude Code's Bash tool — even when the same key works in PowerShell.

**Workaround:** route SSH pushes through `powershell.exe -NonInteractive -NoProfile -WindowStyle Hidden -Command "git ... push ..."`. HTTPS remotes are unaffected (Windows Credential Manager works in either shell). Canonical helper: `coordinator/bin/coordinator-auto-push`.

## Bash Tool

### `cd` persists across Bash tool calls

The Bash tool keeps working-directory state across calls. Convenient when intentional; surprising when not. Prefer absolute paths in long sessions; reserve `cd` for explicit scope changes.

### `run_in_background` kills children on timeout

A backgrounded process killed by the harness's timeout takes its child processes with it. For long-running pipelines that spawn workers, monitor and re-launch rather than relying on the harness to keep the children alive.

### `Edit(replace_all=true)` matches leading whitespace — indent-twins are silently skipped

*2026-05-30, project-rag.* The `Edit` tool matches the exact `old_string` substring **including leading whitespace** — so an `old_string` copied at one indent level silently skips identically-named twins sitting at a different indent (a method body vs. a top-level statement, a nested block vs. an outer one). `replace_all=true` rewrites only the matched-indent subset and reports success, leaving the other occurrences stale — a partial sweep that reads as complete. **Defense:** grep the bare token for its occurrence count *before* the edit, then grep again after and assert the count dropped to the expected residual. Don't trust the `replace_all` success report as proof every occurrence was rewritten.

### Grep look-around patterns silently return "No matches found" — ripgrep has no look-around

*2026-05-30, sibling-repo universal.* The `Grep` tool is ripgrep (Rust `regex` crate), which has **no look-around support** — `(?<!…)`, `(?<=…)`, `(?=…)`, `(?!…)` are unimplemented. The tool does not error on them; it degrades to **"No matches found."** So a sweep built on a lookbehind "guard" reads as *complete-and-clean* when in fact it found nothing — a silent false-negative that masks every real hit the guard was meant to exclude.

**Rule:** never put `(?<!…)` / `(?<=…)` / `(?=…)` / `(?!…)` in a `Grep` pattern. Use a plain pattern and filter the results manually (or pipe through a second `Grep`). When a `Grep` returns zero where you expected at least one match, **suspect a look-around construct in the pattern before concluding absence** — re-run with the bare token and inspect. This is the `Grep`-tool analog of "do not infer from absence" (`tool-output-flakiness-protocol.md`): a zero-result from an unsupported regex feature is *unknown*, not *empty*.

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

### PowerShell here-string syntax (`@'…'@`) silently corrupts Bash tool git messages

PowerShell here-strings (`@'…'@` or `@"…"@`) are a PowerShell-only construct. When a heredoc is authored using this syntax inside a **Bash tool** call, Git Bash interprets the `@'` literal as a positional argument — the string is not expanded as a heredoc, and git receives a malformed message. The resulting commit subject may be truncated, contain literal `@'` characters, or fail entirely.

**Rule:** Build git commit messages in the Bash tool using a POSIX quoted heredoc:

```bash
git commit -m "$(cat <<'EOF'
subject line here

body paragraph.
EOF
)"
```

Reserve `@'…'@` for the PowerShell tool (`pwsh`/`powershell.exe`) where it is correct syntax. The two tools have different shell semantics; heredoc idioms do not cross the boundary. (Source: 2026-05-24 project-rag-ue-addon)

### Embedded double-quote JSON must not be passed as a native-command argument on Windows

PowerShell 5.1 strips embedded double-quotes at the native-command boundary. A string like `'{"key":"value"}'` passed directly as an argument to a native command (node, python, curl) arrives with the inner quotes stripped — the command receives `{key:value}`, which is invalid JSON. This does not affect PowerShell-to-PowerShell cmdlet calls, only PowerShell-to-native-command calls.

**Rule:** Write the JSON to a temp file and pass the path:

```powershell
$json = '{"key":"value"}'
$tmp = [System.IO.Path]::GetTempFileName() + ".json"
$json | Set-Content $tmp -Encoding UTF8
& native-command --json-file $tmp
Remove-Item $tmp
```

Alternatively, switch to the Bash tool for the call and use a POSIX heredoc. (Source: 2026-05-24 claude-unreal-holodeck)

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

## PowerShell Script Discipline

### `[CmdletBinding()]`-less PS scripts silently discard unknown named params

*2026-05-19, project-rag-ue-addon.* A PowerShell script without `[CmdletBinding()]` (or a typed `param(...)` block) silently discards named parameters it doesn't declare — no error, no warning. Silent-default-fallback launchers then run with the *default* arg value, making a mis-passed argument look like a downstream regression rather than a launcher-contract bug. Defense: declare `[CmdletBinding()]` on any script that accepts named params so unknown params fail loud at bind time, and verify the launcher's arg-resolution path before attributing a value mismatch to the impl it wraps.

### PowerShell `& $py - @"…"@` reads from STDIN, not the here-string — use `-c` instead

*Windows/PowerShell.* The invocation `& $py - @"…"@` passes `-` as the script argument, which tells Python to read its program from **stdin** — the here-string becomes positional argv, not the script body. On an interactive terminal this produces an infinite `_pyrepl` loop; when stdout is redirected (the common case in Claude Code's Bash tool), it is a silent no-op that returns exit 0 and does nothing.

**Fix:** use `-c` to pass an inline script:

```powershell
& $py -c @"
import sys, json
# ... your script here
"@
```

`-c @"…"@` passes the here-string as the script body. `-  @"…"@` does not. The two forms look identical at a glance — the `-` vs `-c` difference is the entire bug. (Source: 2026-05-27 claude-central)

### PS→Python heredoc bool interpolation needs literal `True`/`False`, not `true`/`false`

*2026-05-20, project-rag.* When a PowerShell (or shell) script interpolates a value into a Python heredoc, Python booleans must be the literal capitalized tokens `True` / `False` — lowercase `true` / `false` are undefined names and raise `NameError` at exec time. Same hazard for `None` (not `null`/`nil`) and for strings (must be quoted on the Python side). Defense: mock-interpolate and run the heredoc body through Python once before shipping — the failure is invisible until the interpolated branch actually executes.

## Bash / Shell-Script Discipline

### `diff … | wc -l` under `set -e -o pipefail` silently aborts on any difference

*2026-05-18, claude-unreal-holodeck.* `diff` exits non-zero **by design** when files differ (1 = differences, 2 = error). Under `set -e -o pipefail`, `diff a b | wc -l` aborts the whole script the moment the files differ — exactly the case the count was meant to measure. The script dies before `wc` runs, and the failure reads as a mysterious early exit. Fix: neutralize the expected non-zero with a subshell-guard:

```bash
{ diff a b || true; } | wc -l
```

Applies to any pipeline component whose non-zero exit is expected (`grep` with no match, `cmp`, etc.) under `pipefail`.

### Bash reading Python-emitted TSV on Windows — last column carries a trailing CR

*2026-05-23, claude-central.* Python text-mode stdout writes `\r\n` line endings on Windows, but bash `read` strips only the trailing `\n` — so the **last** field of each TSV line arrives with a trailing `\r` attached. Interior fields are clean (split cleanly on `IFS=$'\t'`); only the final field is contaminated, which silently breaks arithmetic (`$((last + 1))` → error) or string comparisons against the last column. Fix: strip the CR via ANSI-C quoted parameter expansion after the read, on the last column only:

```bash
while IFS=$'\t' read -r col1 col2 last; do
  last=${last%$'\r'}   # strip trailing CR from the final field
  ...
done < <(python emit_tsv.py)
```

Either emit with `\n` line endings from the Python side (open stdout in binary or set `newline=''`), or strip CR at the bash read site. Don't strip interior fields — they're already clean.

### Bash heredoc-internal syntax errors hide until EOF — gate with `bash -n`

*2026-05-20, project-rag.* A syntax error *inside* a Bash heredoc body is not reported when the heredoc is parsed — it only surfaces when the interpreting shell reaches it, which for an install script can be long after ship (this defect rode an installer for ~18h). A `bash -n` (no-exec syntax check) in pre-commit catches these in under a second. Caveat: on a Windows working tree with `core.autocrlf=true`, `bash -n` *false-positives* on heredoc-heavy scripts (CRLF breaks closer-line matching) — see § Python / Windows Tooling "Windows bash / CRLF" above; use ShellCheck as the authoritative syntax gate on installers in that case.

### `subprocess.run(['.ps1-path'])` is a Windows footgun — centralize the launcher prefix

*2026-05-20, claude-unreal-holodeck.* Passing a bare `.ps1` path as the first element of a `subprocess.run([...])` argv on Windows does not launch it — `.ps1` files are not directly executable; they must be invoked through `powershell.exe -File <path>` (or `pwsh -File`). Scripts that hand a `.ps1` path straight to `subprocess.run`/`Popen` fail with an exec error or silently shell-resolve to the wrong handler. Defense: centralize the launcher prefix (`powershell.exe -NonInteractive -NoProfile -File`) in a cross-platform script-dispatch helper rather than scattering raw `.ps1` paths through call sites; the helper also carries the `-WindowStyle Hidden` and headless-spawn flags the platform needs.

### GitHub raw-API fetch is LF; a Windows working tree is CRLF — naive diff reports 100%-changed

*2026-05-30, claude-unreal-holodeck.* A file fetched via the GitHub raw API (`raw.githubusercontent.com`, `gh api .../contents`) arrives with LF line endings, but a Windows working tree checked out under `core.autocrlf=true` holds the same content as CRLF. Diffing the fetched copy against the working-tree copy line-by-line (or byte-comparing) reports **every line changed** — a false 100%-drift signal that reads as "the remote and local have completely diverged." Before claiming drift between a raw-API fetch and a local file, strip trailing CR from both sides (`tr -d '\r'`, or `sed 's/\r$//'`) and re-compare; the real diff is almost always empty or small. Same root as the `bash -n` heredoc and TSV-last-column CRLF gotchas above — Windows line-ending normalization contaminating a byte-level comparison.

## Diagnosis Heuristics

### Tiny "corrupt" binary (~130–200B) is usually a git-lfs pointer — `xxd` before assuming corruption

*2026-05-20, project-rag.* A 135-byte (or roughly 130–200B) SQLite or other binary file that reads as "corrupt" at a git-tracked path is almost always a **git-lfs pointer**, not a damaged file — the pointer text was checked out instead of the real blob because `git lfs pull` never ran. Before reaching for data-recovery: `xxd <file> | head -2`. An LFS pointer begins with `version https://git-lfs.github.com/spec/v1`. Fix is `git lfs pull`, not recovery tooling.

### cProfile cumtime can name a background-thread *symptom* as the *cause*

*2026-05-20, project-rag.* When a foreground operation holds a shared lock, `cProfile` cumulative-time can attribute the wall-clock cost to whatever background thread is blocked *waiting* on that lock — presenting the symptom (e.g. chromadb's posthog telemetry call) as the apparent cause when the real cause is the foreground work holding the lock (a slow `collection.get`). Tell: disabling the named "cause" (telemetry) does not clear the wedge. Before acting on a cProfile cumtime ranking in a multi-threaded process, confirm the high-cumtime frame is doing work, not waiting on a lock held elsewhere.

### Dead MCP server in a subagent allowlist breaks ALL its MCP tool resolution — diff LIVE install against source first

*2026-05-26, claude-unreal-holodeck.* A peer session reported Sid (`game-dev:staff-game-dev`) getting zero project-rag tools as a subagent ("banner present, tools absent"), even for validly-granted `project_semantic_search`. Hypotheses ranged over allowlist-vs-wildcard and platform/Agent-Teams plumbing. Real root: the **live install** carried a stale `holodeck-docs`-era definition with the retired `mcp__holodeck-docs__*` (dead server) in its allowlist; the **source** was already clean. A dead MCP server in a subagent allowlist breaks resolution of every MCP tool in that session.

**How to apply:** when a subagent can't see MCP tools its source frontmatter grants, FIRST diff the live install (`~/.claude/plugins/.../agents/<agent>.md`) against source and check for dead/retired `mcp__<server>__*` entries — don't reach for platform/dispatch-mode hypotheses until the live copy is confirmed in-sync. `refresh-plugin-live-install.sh` (clears the dead ref + stale plugin cache) is the fix. This is source↔install drift; the forward-SHA drift check (`version.txt`) + refresh discipline is the prevention.

### WMI hangs on a thrashed Windows host — use kernel APIs for crash forensics

*2026-05-27, claude-unreal-holodeck.* On a memory-thrashed or otherwise distressed Windows host, WMI queries (`Get-WmiObject`, `Get-CimInstance`, anything routing through `platform.system()` that touches WMI on py3.13) **hang indefinitely** — the very condition you are trying to diagnose is what wedges the diagnostic. For crash/OOM forensics, read kernel APIs directly instead: `GlobalMemoryStatusEx` (via P/Invoke or `[System.GC]`-adjacent calls) for memory pressure and `Get-Process` for per-process RSS. These return promptly even when WMI is unresponsive. (Test-code corollary — hermetic probe-aggregator tests must stub `platform.*`/native-lib probes under a hard `--timeout` — lives in `test-design-discipline.md` §50.)
