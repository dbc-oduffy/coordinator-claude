# Windows Process Spawn and Console Popup

**Purpose.** Triage, canonical fix, and test-discipline rules for Windows hidden-window child-process spawning under the Claude Code headless-bash parent, plus the console-input-mode rule that governs launching an interactive TUI. Sections 1-3 consolidate queue entries 52, 65, and 66; § 4 governs the launch chain.

See also: `cross-platform-shell-portability.md` § Windows console-popup (the full layer doctrine); `coordinator/docs/wiki/coordinator-tripwires/` § WINDOWS-CONSOLE-POPUP; `docs/decisions/DR-054-*` (retirement of the execution-layer nag; creationflags-at-authoring is the canonical fix); `docs/plans/2026-06-19-windows-console-popup-coordinator-doctrine.md` (superseded in part by DR-054).

## 1. Triage — audit session-lifecycle scripts first

**Windows console-popup complaints point at session-lifecycle scripts, not test runs.** When a user reports a flash-window or focus-steal in Claude Code on Windows, the first hypothesis is usually "something in my tests is spawning a console child." The correct first move is the opposite: audit the **shell/PS1 session-lifecycle surface**.

Session-lifecycle scripts that run on every Claude Code session start or tool call are the dominant popup source:

- `hooks/scripts/ensure-*.sh` / `ensure-*.ps1`
- `hooks/scripts/stop-*.sh` / `stop-*.ps1`
- `hooks/scripts/update-*.sh` / `update-*.ps1`
- Any SessionStart hook that spawns a background Python or PowerShell process

These scripts run under the Claude Code headless-bash parent on every hook invocation — a console-subsystem child spawned from a headless parent calls `AllocConsole()` and pops a window. A single misfiring ensure/update hook produces one popup per tool call, which looks like a test problem but isn't.

**Apply:** when triaging a popup complaint, run `grep -r 'subprocess\|Popen\|Start-Process\|powershell' hooks/scripts/` before looking at test code. Fix the session-lifecycle surface first; tests are lower-cadence and only fire on explicit test runs.

**Empirical source (queue line 52):** popup complaints were triaged at the test layer for several sessions before the audit landed on `ensure-lsp-proxy.ps1` running on every SessionStart hook.

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

**Do not use `Start-Process -WindowStyle Hidden` + `-RedirectStandard*` as the canonical cross-session solution.** It is unreliable for console-subsystem children (`python.exe`, `powershell.exe`, `netstat.exe`, `cmd.exe`, `git.exe`).

**`git.exe` is not exempt.** Spawned with no `creationflags` from a console-less parent it allocates and shows a visible `ConsoleWindowClass` window in ~50ms, and redirecting the standard streams — the shape `capture_output=True` produces — does not suppress it. Measured across six cases with both controls discriminating: `claude-klabauter state/audits/2026-08-07-git-console-allocation-measurement.md` (claude-klabauter `03b12f87e`). The older "GUI-subsystem, exempt" claim traced to no observation at any link and is refuted; `git.exe` needs `CREATE_NO_WINDOW` like any other console child.

**Empirical source (queue line 65):** a daemon launcher using `Start-Process -WindowStyle Hidden -RedirectStandardOutput ...` continued to flash a console window on Windows under the Claude Code parent. Replacing with `subprocess.Popen(creationflags=CREATE_NO_WINDOW, stdin=DEVNULL)` eliminated the popup unconditionally.

## 3. Test-env ≠ prod-env for child-spawn flags

**Windows daemon-spawn bugs that require `CREATE_NO_WINDOW` reproduce only under a no-controlling-terminal parent and will not reproduce under a foreground interactive bash session.** A developer who tests the spawn logic by running the launcher directly from a terminal gets a false clear: the terminal IS the console, so no `AllocConsole()` call is needed and no window pops. The same launcher under the Claude Code headless-bash parent (or `nohup`, or `Start-Process` without a terminal) has no console to inherit and will pop a window.

**Apply this test discipline:**

- **Diagnose and verify the fix under the actual no-terminal parent**, not in an interactive shell. For Claude Code bugs: disable and re-enable the hook while watching for popups. For production daemons: use `nohup ./launcher &` or `Start-Process -NoNewWindow launcher.exe` as the test harness, not `./launcher` from bash.
- **Foreground-bash test that passes does NOT clear a spawn-flag defect.** A test that only exercises the spawn path from a controlling terminal is a false negative for `AllocConsole()` behavior. Write a test fixture that mimics a no-terminal parent: `subprocess.Popen(['python', 'launcher.py'], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)` from Python, or `Start-Process python launcher.py -NoNewWindow` from PowerShell.
- **The bug is invisible in CI** on Linux/macOS runners — `CREATE_NO_WINDOW` is a Windows-only flag and the `AllocConsole()` codepath doesn't exist on POSIX. Windows-only popup bugs require a Windows runner or a Windows dev machine to reproduce.

**Empirical source (queue line 66):** a spawn-flag defect in a session-lifecycle script was diagnosed and declared fixed based on foreground-bash test runs that returned clean. The popup reappeared on the next Claude Code session (headless parent). The fix required both adding `CREATE_NO_WINDOW` AND writing a no-terminal test fixture that would have caught the regression.

## 4. Interactive launch — `claude.exe` must be a DIRECT child of the invoking shell

Sections 1-3 govern a child process the operator must not *see*. This one governs the child the
operator *types into*, and it is the opposite constraint: not "hide the console" but "do not put
anything between the shell and the process that owns it."

**The rule.** On Windows the interactive `claude.exe` is spawned by the operator's shell and by
nothing else. Any intermediate process — `cmd.exe`, `python.exe`, a `bash -c` hop — corrupts the
console input mode of the operator's terminal. Not "eventually reached": directly spawned.

**The failure signature**, so an agent recognises it in one look: literal `[I` and `[O` text
filling the terminal, keystrokes misrouting to a phantom row, and the host shell's own prompt left
corrupted (`PS[O[I...>`) after exit. Those are xterm focus-report sequences (`ESC[I` focus gained,
`ESC[O` focus lost — DECSET mode 1004). They are a **symptom, not the disease**: they leak into
the input stream only because the TUI's console input mode is already corrupted, so the terminal's
focus events stop being consumed. Chasing mode 1004 chases the symptom.

**The isolation table** — same `claude.exe`, same args in every row; only the nesting differs:

| Invocation | Launch shape | Result |
|---|---|---|
| `claude.exe` | pwsh → claude.exe (direct child) | works |
| `claude.exe --plugin-dir <dir>` | pwsh → claude.exe (direct child) | works |
| `claude` (the coordinator shim) | pwsh → cmd.exe → python.exe → claude.exe | corrupt |

Three wrong hypotheses were tested and discarded before the table settled it: resetting mode 1004
in `$PROFILE` (Claude re-enables it on startup, and it is the symptom), the Git-for-Windows MSYS
`PATH` prepend (dead code on this path), and `os.execv` versus `subprocess.run` in the launch
wrapper (patched; corruption unchanged). The nesting is the cause. Reproduce the discriminator
directly rather than re-deriving it: walk the real process tree from a stub `claude`, which is
what `coordinator/tests/test_dogfood_launch_shape.py` does.

**The discriminator that this rule turns on — self-terminating flags vs resolution-input flags.**
A launcher may safely delegate its *whole* invocation to a helper process only for flags the
helper answers and exits on. Conflating the two classes is what caused the outage:

- **Self-terminating** — `--dry-run`, `--print-plugin-dir`, `--help`, `-h`. The `claude-doe`
  Python wrapper answers these itself and exits; no TUI is ever rendered, so no console input mode
  exists to corrupt. Delegating them wholesale is safe, and necessary — `claude` rejects them
  outright.
- **Resolution input** — `--doe-root <path>` / `--doe-root=<path>`. Different in kind: an input to
  an otherwise ordinary **interactive** launch. Delegating it hands the TUI to the wrapper. It
  must be consumed by the launcher, folded into the non-interactive `--print-plugin-dir`
  resolution, and stripped from the argv that reaches `claude`.

`--doe-root` sat in the launchers' self-terminating set, and the PowerShell `claude` shim passes
it on **every** launch — so the operator's hottest path always ran the TUI under `python.exe`
under `cmd.exe`.

**One further trap, PowerShell-side.** `& claude-doe` resolves through `PATHEXT` to
`claude-doe.CMD` and spawns a `cmd.exe`. Invoking `claude-doe.ps1` **by path** runs it in the
caller's own pwsh process, interposing nothing. A shim that "simplifies" back to the bare command
name reintroduces the defect silently.

**Blast radius — why this is not a cosmetic bug.** The only workable mitigation while the defect
is live is disabling the shim, which leaves every session on the box running vanilla `claude.exe`
with no coordinator plugin at all. One bad launch shape strips the whole operating system from
every session.

**Scope.** The `--doe-root` seam exists only in the dogfood shape (a DoE-claude clone plus a
Claude-klabauter clone, with the `claude` shim reading the `.doe-root` pointer). OSS
coordinator-claude and claude-klabauter installs never take this path, so the OSS install contract
cannot see this defect — coverage belongs on the surface that validates *our* shape.

**Surfaces.** Templates: `coordinator/templates/bin/claude-doe-launcher.{cmd,ps1}.tmpl`,
`coordinator/templates/shell/claude-doe-shim.ps1.tmpl`. Template guard:
`coordinator/tests/test_claude_doe_launcher_native_exec.py`. Rendered-install guard plus the
process-tree probe: `coordinator/tests/test_dogfood_launch_shape.py`. Tripwire:
`docs/wiki/coordinator-tripwires/tripwire-registry/windows-interactive-launch-must-be-a-direct-child.md`.
