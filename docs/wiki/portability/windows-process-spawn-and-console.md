# Windows Process Spawn and Console Popup

**Purpose.** Triage, canonical fix, and test-discipline rules for Windows hidden-window child-process spawning under the Claude Code headless-bash parent, plus the console-input-mode rule that governs launching an interactive TUI. Sections 1-3 consolidate queue entries 52, 65, and 66; § 4 governs the launch chain.

See also: `cross-platform-shell-portability.md` § Windows console-popup (the full layer doctrine); `coordinator/docs/wiki/coordinator-tripwires/` § WINDOWS-CONSOLE-POPUP; `docs/decisions/DR-054-*` (retirement of the execution-layer nag; creationflags-at-authoring is the canonical fix).

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

**`git.exe` is not exempt.** Spawned with no `creationflags` from a console-less parent it allocates and shows a visible `ConsoleWindowClass` window in ~50ms, and redirecting the standard streams — the shape `capture_output=True` produces — does not suppress it. Measured across six cases with both controls discriminating. The older "GUI-subsystem, exempt" claim traced to no observation at any link and is refuted; `git.exe` needs `CREATE_NO_WINDOW` like any other console child.

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

**Scope.** The `--doe-root` seam exists only in the dogfood shape (a doctrine-repo clone plus an
engine-repo clone, with the `claude` shim reading the `.doe-root` pointer). OSS
coordinator-claude and claude-klabauter installs never take this path, so the OSS install contract
cannot see this defect — coverage belongs on the surface that validates *our* shape.

**Surfaces.** Templates: `coordinator/templates/bin/claude-doe-launcher.{cmd,ps1}.tmpl`,
`coordinator/templates/shell/claude-doe-shim.ps1.tmpl`. Template guard:
`coordinator/tests/test_claude_doe_launcher_native_exec.py`. Rendered-install guard plus the
process-tree probe: `coordinator/tests/test_dogfood_launch_shape.py`. Tripwire:
`docs/wiki/coordinator-tripwires/tripwire-registry/windows-interactive-launch-must-be-a-direct-child.md`.

## 5. Resolver asymmetry — the checker and the executor use different resolvers

A Windows exec path can pass every check and still not run, because the surface that **verifies**
the call and the surface that **makes** the call resolve differently — the guard passes and the
execution fails, often silently:

- **`shutil.which()` honours `PATHEXT`; `CreateProcess` does not.** `CreateProcess` cannot run a
  shebang script (`WinError 193: %1 is not a valid Win32 application`) and does not consult
  `PATHEXT` (`WinError 2`), so a delivered `.cmd` is invisible to it — while a `which()`-style guard
  passes on a name that cannot actually be exec'd. The same asymmetry recurs outside Python:
  `.cmd`/`.ps1` resolve via `PATHEXT`/`ShellExecute` and so are invisible to any list-form caller
  (`subprocess.run(["python3", …])`, `hooks.json` exec-form) regardless of speed.
- **The bundled git shipped with GitHub Desktop has no `bash.exe`.** It bundles MinGit shipping
  `usr/bin/sh.exe` and `usr/bin/env.exe` but no `bash.exe`, and Git for Windows' own `usr\bin` is
  deliberately kept off the persisted PATH — so `env` cannot find bash either. A hook with
  `#!/usr/bin/env bash` or `#!/bin/bash` fails **every** GitHub Desktop commit. The fix costs
  nothing: that `sh.exe` *is* bash 5.2+ — arrays, `[[ ]]`, herestrings and `pipefail` all work under
  a `/bin/sh` shebang. Where a hook shells out to a bash script, invoke it as `sh <script>` and
  leave that script's own shebang alone; a git hook or hook generator on this fleet should never be
  authored with a bash shebang — `/bin/sh` is the only portable one.
- **Path separator and case defeat textual prefix matches.** Some values are written forward-slashed
  while others (e.g. `CLAUDE_PLUGIN_ROOT`) arrive backslashed, so a textual `startswith` prefix
  match never fires. The same asymmetry is a real security bypass in a traversal guard checking only
  `"/.." in path` — it misses `\..`. Normalize before any prefix or traversal comparison.

Test the exec path with the **executor**, not with a resolver: `cmd /c` the generated launcher, run
the hook under the bundled `sh.exe` directly, run the subprocess under the exact flags production
uses.

## 6. `CREATE_NO_WINDOW` silent-kills a child that still holds inherited console handles

`CREATE_NO_WINDOW` plus **inherited** stdio kills the child outright — return code 1, no output —
rather than merely hiding its window: the flag detaches the child from the console while it still
holds console handles it cannot use anymore. Safe only when stdio is explicitly redirected. Isolate
the three cases before assuming a logic bug: bare run → exit 0; `+creationflags=CREATE_NO_WINDOW`
with inherited stdio → exit 1; `+creationflags=CREATE_NO_WINDOW` with `capture_output` → exit 0.
Because the non-capturing call fails with no diagnostic output at all, it masquerades as a logic bug
in the caller rather than a stdio-handle conflict — redirect stdio wherever `CREATE_NO_WINDOW` is
set.

**Why local testing and review never catch this.** `getattr(subprocess, "CREATE_NO_WINDOW", 0)`
resolves to `0` on macOS/Linux, so the flag is a literal no-op on the machine doing the authoring
and the reviewing — the code is genuinely correct there. One case: a repo's dev-tooling entrypoint
passed `CREATE_NO_WINDOW` to every subprocess it spawned, including its own **foreground** runner
calls (test, run, extract, schema, plus the pip install inside its install step) whose output the
operator is meant to see. The first-ever Windows execution ran the test target for over two
minutes — the suite genuinely executed — and emitted zero output before exiting 1, versus hundreds
of log lines for the same suite on Linux. A green local suite, several adversarial review passes,
and a scout sweep specifically hunting POSIX assumptions all missed it, because it is invisible
until executed on Windows and its symptom there is silence, not an error.

**The fix is surgical, not a blanket removal.** The flag only breaks a call whose stdio is
*inherited*; a call already passing `capture_output=True` or redirecting to `DEVNULL` is
unaffected, because its output already goes to a pipe the parent owns (the three-way isolation
above). So the rule is not "never use `CREATE_NO_WINDOW`" — it is "never set it on a call whose
output the operator is meant to see inherited." Strip it from foreground/streaming calls
(interactive-tool entrypoints, streaming install steps) while retaining it on every
capture/`DEVNULL` call.

**Generalization.** A platform-conditional no-op (any `getattr(module, "WINDOWS_ONLY_ATTR", 0)`
guard) is the most dangerous shape a cross-platform defect can take, because the platform that
would reveal it is precisely the one nobody authoring or reviewing the change is running on. Treat
any such guarded platform flag as untested-by-default rather than as safe-because-it-degrades.

## 7. A fix at the diagnosed line can reopen the same hazard one stack frame up

A careful, correctly-understood fix can still leave the bug live if the hazard is restated only at
the line the finding named, rather than as an invariant the whole call chain must honour. Two
independent cases surfaced the same shape in one review pass, both authored by people who
understood the bug they were fixing:

- A TOCTOU was correctly closed at its diagnosed site — one `read_bytes()`, hash those bytes — but
  the *same commit's* cross-check one frame up added an independent second read of the same file
  (`json.loads(path.read_text())`), so the file was still read twice per call and the cross-check
  could validate one version while a different version was hashed. That second read also dropped
  `encoding=`, silently reintroducing the classic **cp1252-vs-UTF-8-on-Windows** read bug the fix
  had just removed — in a repo whose reason for existing is Windows correctness.
- A reviewer finding that a field carried no join key was "fixed" by threading an id from the
  nearest-to-hand row — moving the field from honestly-null to confidently-wrong. A referential
  validator certified it, because a wrong-lane id still resolves; it was not a one-to-one join, so
  no correct id existed to thread and null had been the right answer.

**Why it recurs.** A fix is scoped to the line the finding names, and the finding names a
*symptom location*, not the invariant. The author holds the invariant in their head while editing
that line and does not re-apply it to code added alongside it in the same commit — and a reviewer
reading the diff sees a correct fix, because it is one.

**Rules.**
1. State a resource-access invariant as a **signature**, not a comment: have one function own the
   read (with its explicit `encoding=`) and hand the decoded bytes/text down, so a second read
   anywhere downstream is a signature change, not a quiet addition — "be careful here" is not a
   control.
2. Re-audit a fix that *adds* code against the very invariant it is restoring, including code
   added in the same commit.
3. Filling a previously-null field is not automatically an improvement: honestly-null beats
   confidently-wrong, and a validator that only checks resolvability will certify a wrong value.
   Verify the join is one-to-one before threading an identifier.
4. Reviewers: read what a fix commit *adds*, not only what it changes.
