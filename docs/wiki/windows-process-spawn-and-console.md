# Windows Process Spawn and Console Popup

**Purpose.** Triage, canonical fix, and test-discipline rules for Windows hidden-window child-process spawning under the Claude Code headless-bash parent. Three sections consolidate queue entries 52, 65, and 66 (2026-06-08).

See also: `cross-platform-shell-portability.md` § Windows console-popup (the full layer-0/layer-1/reach doctrine); `coordinator-tripwires.md` § WINDOWS-CONSOLE-POPUP; `docs/plans/2026-06-19-windows-console-popup-coordinator-doctrine.md`.

## 1. Triage — audit session-lifecycle scripts first

**Windows console-popup complaints point at session-lifecycle scripts, not test runs.** When a user reports a flash-window or focus-steal in Claude Code on Windows, the first hypothesis is usually "something in my tests is spawning a console child." The correct first move is the opposite: audit the **shell/PS1 session-lifecycle surface**.

Session-lifecycle scripts that run on every Claude Code session start or tool call are the dominant popup source:

- `hooks/scripts/ensure-*.sh` / `ensure-*.ps1`
- `hooks/scripts/stop-*.sh` / `stop-*.ps1`
- `hooks/scripts/update-*.sh` / `update-*.ps1`
- Any SessionStart hook that spawns a background Python or PowerShell process

These scripts run under the Claude Code headless-bash parent on every hook invocation — a console-subsystem child spawned from a headless parent calls `AllocConsole()` and pops a window. A single misfiring ensure/update hook produces one popup per tool call, which looks like a test problem but isn't.

**Apply:** when triaging a popup complaint, run `grep -r 'subprocess\|Popen\|Start-Process\|powershell' hooks/scripts/` before looking at test code. Fix the session-lifecycle surface first; tests are lower-cadence and only fire on explicit test runs.

**Empirical source (queue line 52, 2026-06-08):** popup complaints were triaged at the test layer for several sessions before the audit landed on `ensure-lsp-proxy.ps1` running on every SessionStart hook.

## 2. Canonical spawn — `subprocess.Popen` with `CREATE_NO_WINDOW` + `stdin=DEVNULL`

**`Start-Process -WindowStyle Hidden + -RedirectStandard*` does not reliably suppress the console window for a Python child process.** `-WindowStyle Hidden` applies to the PowerShell window for the `Start-Process` call itself; it does not propagate `CREATE_NO_WINDOW` to the child process's own console allocation. Under some Windows build/version combinations, `python.exe` still calls `AllocConsole()` and a window appears.

**Canonical fix for hiding a Python child process window on Windows:**

```python
import subprocess
import os

proc = subprocess.Popen(
    ["python", "-m", "mymodule", ...],
    creationflags=subprocess.CREATE_NO_WINDOW,  # suppresses AllocConsole()
    stdin=subprocess.DEVNULL,                   # no controlling terminal
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)
```

For cross-platform code that also runs on macOS/Linux, use the `getattr` form so the integer is not evaluated on POSIX (where `CREATE_NO_WINDOW` does not exist as an attribute):

```python
creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
```

Or use the `no_console_creationflags()` helper if your codebase ships one (see `cross-platform-shell-portability.md` § Platform-conditional guard taxonomy § class 2 for the multi-site helper form).

**Do not use `Start-Process -WindowStyle Hidden` + `-RedirectStandard*` as the canonical cross-session solution.** It is unreliable for console-subsystem children (`python.exe`, `powershell.exe`, `netstat.exe`, `cmd.exe`). `git.exe` is GUI-subsystem and exempt — it does not call `AllocConsole()`.

**Empirical source (queue line 65, 2026-06-08):** a daemon launcher using `Start-Process -WindowStyle Hidden -RedirectStandardOutput ...` continued to flash a console window on Windows under the Claude Code parent. Replacing with `subprocess.Popen(creationflags=CREATE_NO_WINDOW, stdin=DEVNULL)` eliminated the popup unconditionally.

## 3. Test-env ≠ prod-env for child-spawn flags

**Windows daemon-spawn bugs that require `CREATE_NO_WINDOW` reproduce only under a no-controlling-terminal parent and will not reproduce under a foreground interactive bash session.** A developer who tests the spawn logic by running the launcher directly from a terminal gets a false clear: the terminal IS the console, so no `AllocConsole()` call is needed and no window pops. The same launcher under the Claude Code headless-bash parent (or `nohup`, or `Start-Process` without a terminal) has no console to inherit and will pop a window.

**Apply this test discipline:**

- **Diagnose and verify the fix under the actual no-terminal parent**, not in an interactive shell. For Claude Code bugs: disable and re-enable the hook while watching for popups. For production daemons: use `nohup ./launcher &` or `Start-Process -NoNewWindow launcher.exe` as the test harness, not `./launcher` from bash.
- **Foreground-bash test that passes does NOT clear a spawn-flag defect.** A test that only exercises the spawn path from a controlling terminal is a false negative for `AllocConsole()` behavior. Write a test fixture that mimics a no-terminal parent: `subprocess.Popen(['python', 'launcher.py'], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)` from Python, or `Start-Process python launcher.py -NoNewWindow` from PowerShell.
- **The bug is invisible in CI** on Linux/macOS runners — `CREATE_NO_WINDOW` is a Windows-only flag and the `AllocConsole()` codepath doesn't exist on POSIX. Windows-only popup bugs require a Windows runner or a Windows dev machine to reproduce.

**Empirical source (queue line 66, 2026-06-08):** a spawn-flag defect in a session-lifecycle script was diagnosed and declared fixed based on foreground-bash test runs that returned clean. The popup reappeared on the next Claude Code session (headless parent). The fix required both adding `CREATE_NO_WINDOW` AND writing a no-terminal test fixture that would have caught the regression.
