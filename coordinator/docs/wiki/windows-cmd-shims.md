# Windows `.cmd` Shims for Extensionless Bash Scripts and `python3`

> Why `bin/machine-local.cmd` and `bin/python3.cmd` exist, and what failure mode they prevent.

## The failure mode

On Windows, certain process-launch paths fall back to `ShellExecute`/`ShellExecuteEx` when `CreateProcess` cannot resolve a name to a runnable image. `ShellExecute` then treats the name as a *document* and consults file associations — for unknown names this opens the "Select an app to open 'X'" GUI picker instead of returning `ERROR_FILE_NOT_FOUND`.

Two specific names hit this on a typical operator's Windows install:

- **`machine-local`** — extensionless bash script at `~/.claude/bin/machine-local`. `CreateProcess` cannot execute it (not a PE). `ShellExecute` fallback walks `PATHEXT`, hits the `.py` association (often without a `UserChoice` key set), pops the picker.
- **`python3`** — no `python3.exe` on a vanilla Windows Python install (only `python.exe` and `py.exe`). `ShellExecute` falls through to the Microsoft Store App Execution Alias for `python3.exe`, which either silently routes to the Store Python REPL (blocks the caller) or pops the "Install Python" page or the Open-With picker.

In a multi-session Claude Code workflow with MCP servers, hooks, and frequent subprocess invocations across multiple repos, the picker storm becomes a UX-blocker — dozens of modal dialogs piled across the taskbar.

## What the shims do

`bin/machine-local.cmd` and `bin/python3.cmd` are tiny `.cmd` files that:

- Are found by `cmd.exe` / `PowerShell` / any caller doing `PATHEXT`-aware command resolution **before** `ShellExecute` fallback fires.
- Route the call to the right interpreter: `bash` (for `machine-local`) or `python.exe` (for `python3`).
- Exit with the wrapped command's exit code.

## Shim is necessary but not sufficient

Empirical testing on 2026-05-19 showed:

- **cmd.exe / PowerShell callers** — fully fixed by the `.cmd` shim if it's on the Windows user PATH. `Get-Command machine-local` resolves to the shim.
- **Python `subprocess.run([name], shell=False)` (list form)** — Python passes the name directly to `CreateProcess` as `lpApplicationName`, bypassing `PATHEXT`. The shim does NOT help here; `subprocess` throws clean `FileNotFoundError`. The `try/except OSError` in the addon's caller already catches this — no picker fires from the list form. **If a Python caller uses the string form** `subprocess.run(name, ...)` (or `shell=True`), `PATHEXT` IS consulted and the `.cmd` shim DOES help.
- **Python `subprocess.run([full_path_to_extensionless_script], ...)`** — `CreateProcess` reads the file, finds it's not a valid PE, throws `OSError [WinError 193] %1 is not a valid Win32 application`. No picker. The caller must prepend `["bash", ...]` to actually execute the script.
- **Node `child_process.spawn(name, args, { shell: false })`** — same shape as Python subprocess list form; clean ENOENT, no picker.
- **`Process.Start(UseShellExecute=true)` from .NET / Node `child_process.exec` / PowerShell `& $extensionlessName`** — these go through `ShellExecute`; the picker fires unless the name resolves via PATH first. The `.cmd` shim DOES help here.

The shim is a structural fix for the dominant path (shell callers). Python/Node subprocess callers that invoke extensionless scripts must be fixed at the caller (use `bash + path` explicitly).

## Install path

`coordinator:install` Step 3 copies both `.cmd` files from `templates/bin/` to `~/.claude/bin/`. Step 3b (Windows-only conditional) adds `~/.claude/bin` to the Windows user `PATH` if not already present. Both are idempotent.

On non-Windows operators, the `.cmd` files sit unused in `~/.claude/bin/` — harmless.

## Maintenance

- The shims are pure ASCII (no BOM) — Windows `cmd.exe` parser breaks on UTF-8 BOM in the first bytes.
- Use `CRLF` line endings or `LF` — modern `cmd.exe` accepts both.
- Do not introduce bash-syntax constructs (`/dev/null`, `&>`, etc.) into `.cmd` files — `cmd.exe` syntax only (`nul`, `>nul 2>&1`).
- A linter that "corrects" cmd syntax to bash will break the shim — keep `.cmd` files outside shellcheck/shfmt scope.

## Python resolution on Windows operators

The shim covers the `python3.cmd` case at the **PATH-lookup layer**. The picker can still fire on Windows operators if a different lookup path resolves `python3` first. Three failure modes worth knowing:

### 1. AppX App-Execution-Alias precedence over PATH

When a caller invokes `python3` via `ShellExecute` (Node `child_process.exec`, .NET `Process.Start(UseShellExecute=true)`, PowerShell `& python3` in some contexts), Windows consults the AppX App-Execution-Alias subsystem **independently** of PATH lookup — the two are separate subsystems, not a fallthrough chain. If a `%LOCALAPPDATA%\Microsoft\WindowsApps\python3.exe` stub exists (reparse point registered by an AppX package such as PythonSoftwareFoundation.PythonManager / Python.3.x), the AppX path wins. If the stub's target AppX package is uninstalled or its alias is broken, Windows falls back to "how do you want to open this?" — the picker fires **without** falling through to PATH. The shim on PATH is never reached.

**Detection on operator's box:**
```powershell
Get-Item "$env:LOCALAPPDATA\Microsoft\WindowsApps\python3.exe" -Force -ErrorAction SilentlyContinue | Select-Object Name, Length, Target, LinkType
```
Length 0 + LinkType ReparsePoint + no Target ⇒ orphan stub. Delete with `Remove-Item -Force`. If you reinstall Store Python the stub regenerates — re-clean. The `/setup` Step 3c health check encodes this same three-condition detection.

### 2. Store-alias on `command -v` resolution

A subset of operators have `%LOCALAPPDATA%\Microsoft\WindowsApps` on the **MSYS PATH** (git-bash inheritance from Windows PATH ordering). In that case `command -v python3` from bash returns the stub path — non-empty, so any `command -v python3 || command -v python || echo python` guard "succeeds" with the stub. The stub then gets invoked → picker.

**Mitigation in runtime scripts:** filter PATH results against `WindowsApps`:
```bash
case "$_path" in
    */WindowsApps/*|*\\WindowsApps\\*) continue ;;
esac
```
**Prefer:** detect `py.exe` (the Python Launcher bundled with python.org installer) first; only fall through to filtered `command -v` lookup.

### 3. The bare-`python3` doctrine

In any runtime script that fires from a hook chain or MCP probe on Windows, do NOT write bare `python3 -c "..."`. Use a resolver pattern with the WindowsApps exclusion, or invoke via `py -3` if you can assume the Python Launcher is present. Document the assumption.

## Non-goals (explicitly rejected shapes)

- **Shape β — shared runtime resolver lib at `~/.claude/lib/resolve-python.sh`**: REJECTED for now. Inverts Central's authoring-time direction and creates a runtime dep for every consumer repo. Promote only if a third unique callsite needs the same resolver bug fix, or if a fifth repo joins the cleanup wave (instance-#3 rule). Until then: vendor the resolver pattern per repo (shape α with propagation discipline).
- **Shape γ — registry mutation to disable App Execution Aliases**: REJECTED. Operator system-state mutation is out of our lane. Operators who want this can self-service via Settings → Apps → Advanced app settings → App execution aliases → toggle off `python.exe` / `python3.exe`. The wiki documents the option; the setup skill does NOT perform it.

## Related fix sites (per-repo durable fixes)

The shim is the universal structural fix; per-repo code that names `python3` or extensionless `machine-local` in shell heredocs should also be hardened:

- Shell scripts: source `scripts/lib/select-python.sh` (project-rag) or `lib/resolve-python.sh` (coordinator) and use the resolved interpreter, not bare `python3`. Apply WindowsApps exclusion if the lib does not already.
- Python callers: invoke `[bash, str(reader)]` rather than `[str(reader)]` for extensionless bash scripts. **For `.cmd`/`.exe`/`.bat`/`.com` targets, use bare invocation (natively executable). For everything else (extensionless, `.sh`, `.ps1`), prepend `bash`.** This whitelist-natively-executable inversion is fail-closed vs. the fail-open `suffix == ""` check.
- PowerShell callers: invoke `& bash $script` rather than `& $script` for extensionless bash scripts.

## PowerShell Python Inline Invocation — Use `-c`, Not Bare `-`

**`& $py - @"…"@` passes the here-string as an argv and makes Python read its program from STDIN — use `-c @"…"@` instead.**

### Symptom

An installer's `& $PythonAbs - @"<script>"@` runs as a silent no-op non-interactively. Interactively (when stdout is redirected but stdin is a tty), it triggers an infinite Python 3.13 `_pyrepl` loop — pegged CPU and 2.5 GB of stderr — because Python waits for STDIN program text and `getheightwidth` has no console to query.

### Why

PowerShell `& $py - @"…"@` passes the here-string as an *argument* (argv[1]), not as STDIN. Python's `-` flag means "read program from STDIN"; combined with an argv, Python reads stdin (blocking or looping) and ignores the here-string entirely.

### Fix

| Goal | Correct form |
|---|---|
| Pass script inline as a string argument | `& $py -c @"<script>"@` |
| Feed script via STDIN | `@"<script>"@ \| & $py -` |
| The bare `& $py - @"…"@` form | **Always wrong — never use** |

`-c @"…"@` treats the here-string as the program text (positional arg to `-c`). `-` with pipe feeds via STDIN as intended. The bare `- <here-string>` form combines both flags in an ambiguous way that always resolves to STDIN-read.

### Greppable signature

```
& $.*python.* - @"
```

Any PowerShell script matching this pattern should be audited.

## Start-Process -WindowStyle Hidden with redirect silently allocates console

`Start-Process -WindowStyle Hidden` combined with `-RedirectStandardOutput`/`-RedirectStandardError` on a console-subsystem `python.exe` does NOT reliably hide the window — it allocates a persistent console. The distinction is `SW_HIDE` (hides after creation) vs. `CREATE_NO_WINDOW` (never creates). For reliable headless spawning, use `pythonw.exe` (GUI subsystem) or pass `creationflags=CREATE_NO_WINDOW` (0x08000000) in Python's `subprocess.Popen`. Defense-in-depth audit: grep for `Start-Process.*-WindowStyle Hidden` across all scripts — second occurrence (project-rag-L42): found 10+ sites in the holodeck/project-rag install surface.

## console-popup triage — lifecycle scripts dominate, not tests

Console-popup complaints on Windows usually originate in session-lifecycle scripts (startup, health-check, install runners), not the test runner itself. Triage heuristic: audit parallel-launch lifecycle scripts (e.g., `session-init.sh`, `coordinator-auto-push`, MCP start scripts) before chasing pytest internals. Apply: reproduce by running the lifecycle script path in isolation before adding `CREATE_NO_WINDOW` flags inside tests.

## PowerShell 5.1 ConvertTo-Json empty array serializes as null

PowerShell 5.1 `ConvertTo-Json` serializes an empty `@()` value inside a hashtable as `null`, not `[]`. This breaks any downstream consumer that distinguishes null from empty array. Fix: use `@(,@())` for a forced-array or `[System.Collections.Generic.List[object]]::new()`, then pipe through `ConvertTo-Json`; or post-process with `-replace '"value": null', '"value": []'` where field semantics are known. Audit: any PS5.1 script serializing potentially-empty arrays to JSON needs this guard.

## Why we can't have integration tests for picker-fire

The picker is a GUI dialog. There is no programmatic signal that an assertion can read (no stderr, no exit code, no log entry). The closest we can do is assert at `/setup` time that the orphan-stub and Store-alias-on-PATH configurations are absent after the health check runs — that's an acceptance test on the health check, not on the runtime scripts. Document this expectation rather than chase a test we can't write.
