# Windows `.cmd` Shims for Extensionless Bash Scripts and `python3`

> Why `bin/machine-local.cmd` exists, and what failure mode it prevents. `bin/python3.cmd` is
> retired — see "The three `python3`-resolution paths" below for its replacement.

## The three `python3`-resolution paths (additive, all three kept)

On Windows, `python3` gets resolved through **three separate lookup mechanisms**, each hit by a
different class of caller. Two of the three — cmd.exe-side and CreateProcess-side — now share one
fix, the `python3.exe` PE; bash-side remains its own mechanism. None replaces another — all three
caller classes are covered simultaneously:

| Path | Caller class | Fix | Lands via |
|---|---|---|---|
| **bash-side** | `bash` scripts doing `command -v python3` / PATH lookup | `COORDINATOR_PYTHON`/registry/PATH resolution contract (successor to the retired `lib/resolve-python.sh` — see `machine-local-registry.md § coordinator.python resolution contract`; WindowsApps-stub exclusion needs re-verification against the successor, see `claude-code-platform-gotchas.md`) | applied directly by callers, no lib to source |
| **cmd.exe-side** | `cmd.exe` / PowerShell `ShellExecute` fallback, PATHEXT-aware lookup | the same `python3.exe` PE as the CreateProcess-side row below — a real `.exe` satisfies a PATHEXT-aware lookup too | see CreateProcess-side row |
| **CreateProcess-side** | Python `subprocess.run(["python3", …])` (list form) / any Win32 `CreateProcess` caller, including `hooks.json` exec-form registrations | a real `python3.exe` PE (hardlink/copy of the python.org `python.exe`), placed ahead of `%LOCALAPPDATA%\Microsoft\WindowsApps` on PATH | claude-klabauter `coordinator_core/ops/ensure_python3_exe_shim.py`, picked up by the `coordinator/bin/install-health-run.py` drop-in orchestrator (Phase 3 Step 1b) |

`python3.cmd` is retired — it is not the cmd.exe-side fix any more. A reader who does not know
that will restore it to fix the `CreateProcess`/`PATHEXT` problem, which is real; the correct
answer is a real `python3.exe` PE (hardlink/copy of the python.org `python.exe`) placed beside the
real interpreter, in a directory ahead of `%LOCALAPPDATA%\Microsoft\WindowsApps` on PATH — it
cannot live in `~/.coordinator-claude-settings/bin/` (a shim directory): the loader searches an
executable's own folder for its DLLs ahead of PATH, and `getpath` locates the stdlib by searching
up from the executable's directory for `Lib/os.py`, so a `python3.exe` dropped in a shim dir would
find neither. This is a PATH-ordering fix at the real interpreter's install location, not a
restored shim. The absence of `python3.cmd` is the operative rule, not an oversight.

**Why the `.exe` covers two caller classes, not just one:** `CreateProcess` (the Win32 API behind
Python's list-form `subprocess.run`, and behind `hooks.json` exec-form registrations) does **not**
honor `PATHEXT` and only resolves actual `.exe` files — it never sees a `.cmd` shim or the bash
resolver. A real `.exe`, unlike a `.cmd` shim, also satisfies a PATHEXT-aware `ShellExecute` lookup
— `.EXE` is in the default `PATHEXT` list — so the same artifact answers both the cmd.exe-side and
CreateProcess-side rows. It does not help a bash `command -v python3` lookup, which stays on its
own resolution contract. See
`docs/research/2026-07-14-windows-first-class-coordinator/09-python3-shim-fix-recipe.md` Q3 for
the original wiring confirmation and Q1/Q2 for how
the ensure-python3-exe-shim logic (now claude-klabauter `coordinator_core/ops/ensure_python3_exe_shim.py`)
is wired into install, run by the claude-klabauter `coordinator/bin/install-health-run.py` orchestrator
— no direct call site needed or added.

**Measured cost of each path** (this machine, native `CreateProcess` launch from PowerShell — see
`docs/research/2026-07-14-windows-first-class-coordinator/00-EMPIRICAL-spawn-benchmark.md`
"Indirection-layer probe" table):

| path to run python | median | overhead vs native |
|---|---:|---|
| **native `python3.exe`** (the cmd.exe-side and CreateProcess-side fix) | **~35 ms** | — |
| `py -3` launcher | ~156 ms | +121 ms |
| `python3.cmd` (retired cmd.exe-side shim, historical) | ~184 ms | +149 ms |
| bash-shim `python3` (bash-side, `#!/usr/bin/env bash; exec python`) | ~202 ms | +167 ms |

The native `python3.exe` is a real PE with no interpreter indirection — it is the fast path for any
caller that resolves via `CreateProcess` or PATHEXT-aware `ShellExecute`. The bash-resolver path
remains necessary for its own caller class (`command -v` callers) — it is not superseded by the
`.exe`, only complemented by it.

## The failure mode

On Windows, certain process-launch paths fall back to `ShellExecute`/`ShellExecuteEx` when `CreateProcess` cannot resolve a name to a runnable image. `ShellExecute` then treats the name as a *document* and consults file associations — for unknown names this opens the "Select an app to open 'X'" GUI picker instead of returning `ERROR_FILE_NOT_FOUND`.

Several extensionless names hit this on a typical operator's Windows install:

- **`machine-local`** — extensionless bash script at `<settings-home>/bin/machine-local`. `CreateProcess` cannot execute it (not a PE). `ShellExecute` fallback walks `PATHEXT`, hits the `.py` association (often without a `UserChoice` key set), pops the picker.
- **`coordinator-settings-home`** — extensionless bash forwarder at `<settings-home>/bin/coordinator-settings-home`. Same mechanism as `machine-local` — its `.cmd` shim was omitted at introduction and re-added after it popped the picker at every boot on a hook-wired Windows install.
- **`claude-home`** — extensionless bash script; shipped with `claude-home.cmd` from the start.
- **`python3`** — no `python3.exe` on a vanilla Windows Python install (only `python.exe` and `py.exe`). `ShellExecute` falls through to the Microsoft Store App Execution Alias for `python3.exe`, which either silently routes to the Store Python REPL (blocks the caller) or pops the "Install Python" page or the Open-With picker.

**Rule when adding a new extensionless PATH-injected command:** ship a `.cmd` sibling in `templates/bin/` AND install it in *both* `install-substrate.py` bin loops (primary `_bin_dst` + compat `_compat_bin_dst`), same as its extensionless partner. The `.cmd` MUST be CRLF (pinned via `coordinator/.gitattributes` `*.cmd text eol=crlf`) — `cmd.exe` mis-parses LF-only batch files and executes `REM` lines as commands. Gap closed 2026-07-19: `resolve-coordinator-clone.cmd` now ships in `templates/bin/` — BLOCKED-class (bash-routing), since `resolve-coordinator-clone` is a pure `#!/usr/bin/env bash` script, not a python/sh polyglot; see § "python-direct shims" below.

In a multi-session Claude Code workflow with MCP servers, hooks, and frequent subprocess invocations across multiple repos, the picker storm becomes a UX-blocker — dozens of modal dialogs piled across the taskbar.

## What the shim does

`bin/machine-local.cmd` is a tiny `.cmd` file that:

- Is found by `cmd.exe` / `PowerShell` / any caller doing `PATHEXT`-aware command resolution **before** `ShellExecute` fallback fires.
- Was rewired python-direct in the 2026-07-19 de-bash campaign (Wave 0) — see the next section; it
  does not route through `bash`, and `py -3` is demoted to the ladder's last-resort tier rather
  than being the primary route.
- Exits with the wrapped command's exit code.

**`python3.cmd` is retired**, not merely superseded — `templates/bin/python3.cmd` contained `py -3
%*`, a double indirection (cmd.exe resolves the shim, hands off to the `py` launcher, which then
execs the actual interpreter; measured ~184 ms end-to-end vs. ~35 ms for the native `python3.exe`
PE — see "Measured cost of each path" above and
`docs/research/2026-07-14-windows-first-class-coordinator/00-EMPIRICAL-spawn-benchmark.md`). The
`python3.exe` PE placed beside the real interpreter, ahead of `%LOCALAPPDATA%\Microsoft\WindowsApps`
on PATH, is the correct answer to the same `CreateProcess`/`PATHEXT` problem now — see "The three
`python3`-resolution paths" above. A reader restoring `python3.cmd` to fix a picker or a
hook-quoting issue is solving an already-solved problem with a retired mechanism.

## python-direct shims

Wave 0 of the Windows de-bash campaign (`docs/plans/2026-07-19-debash-coordinator-windows.md`)
rewrote the `.cmd`/`.ps1` shims for every `bin/*` entrypoint that is a pure `.py` file or an
sh/python polyglot to be **python-direct**: they resolve an interpreter and run the entrypoint
directly, with `py -3` demoted to a last-resort tier instead of being the primary route the older
"What the shims do" section above describes. `gen-launcher-shim.py` is the generator for this
shape; hand-authored shims in the same wave mirror its contract by hand.

**The 3-tier ladder** (identical across the generator and every hand-authored python-direct shim,
modeled on the retired `python3.cmd`'s fast-path rationale — see "What the shim does" above):

1. **`__PYTHON_BIN__`** — an absolute interpreter path baked in at install time by
   **claude-klabauter**'s `coordinator/lib/install-substrate.py` (engine plane — it is not in this
   repo, and a search here for the bare filename finds nothing), or the empty string on a
   no-Python install. The literal token is
   guarded against surviving un-substituted (`if "%_py%"=="__PYTHON_BIN__" set "_py="` / the
   delayed-expansion `!_py!` equivalent in generated shims / the PowerShell
   `if ($_pybin -eq '__PYTHON_BIN__') { $_pybin = '' }` equivalent) — without this guard, an
   unsubstituted launcher (fresh checkout, from-source dev-tree, or a partially-failed install)
   treats the literal token string as a non-empty path, fails, and terminates without falling
   through to tier 2.
2. **`where python.exe` / PowerShell `Get-Command python.exe`** — first `python.exe` on PATH,
   **with WindowsApps App-Execution-Alias stubs filtered out** (`*\WindowsApps\*` hits skipped
   before accepting a candidate). This is the same mitigation § "AppX App-Execution-Alias
   precedence over PATH" below prescribes for bash-side resolution, applied to the `.cmd`/`.ps1`
   side: on a fresh or no-Python-installed Windows machine, `%LOCALAPPDATA%\Microsoft\WindowsApps`
   is on the default user PATH and its `python.exe`/`python3.exe` App Execution Alias stubs either
   silently redirect to the Microsoft Store or hang — the exact failure class this whole campaign
   exists to prevent, so every tier-2 lookup in this shape MUST filter it.
3. **`py -3`** — the Python Launcher, last resort (carries the Store-alias risk the baked path and
   the filtered PATH lookup exist to avoid).
4. **none found** — exit 127 with a remediation pointer to the python.org Windows installer.

**Shims converted to this shape (Wave 0):** `claude-home.cmd`/`.ps1` (generator-produced),
`coordinator-lesson-add.cmd`, `coordinator-doc-new.cmd`, `mint-deliverable-id.cmd`,
`coordinator-queue-append.cmd`, `cross-repo-memo.cmd` (all seven now share the same 3-tier ladder;
twin filenames never carry the target's language extension — claude-klabauter erratum, landed
`b4707679` — the installed forwarder twin in the settings-home `bin/` dir is `mint-deliverable-id.sh.cmd`,
keeping `.sh` in the installed name for caller-path stability, a known parked PATHEXT quirk).
`templates/bin/machine-local.cmd` also converted — its bash target's only value was locating
`_machine_local.py` via the settings-home seam and picking an interpreter, so that path-resolution
logic was promoted directly into the `.cmd` (env-var precedence, not `%~dp0`-relative, since the
compat-forwarder install location isn't co-located with `_machine_local.py`) ahead of the same
3-tier interpreter ladder; failure exit codes stayed `2` (matching the bash original's
operational-failure contract) rather than adopting this shape's usual `127`.

**Bare-name resolution prefers `.ps1` over `.cmd`.** For any command name with both a `.cmd` and a
`.ps1` sibling on PATH (the shape this section's Wave 0 conversions produced), PowerShell resolves
the bare name to the `.ps1` twin ahead of the `.cmd` twin — on both pwsh 7 and Windows PowerShell
5.1, despite `.PS1` being absent from `PATHEXT`. This is **observed and pinned by a claude-klabauter
regression test, not a documented Microsoft guarantee** — treat it as empirical behavior to keep
verifying, not settled vendor contract. Verified on pwsh 7.6.4 and Windows PowerShell
5.1.26100.8875. Source: § 6(i) of
`cross-repo/archive/2026-08-07-claude-klabauter-em-cmd-forwarder-newline-truncation-fix.md`.

**An execution-policy-blocked `.ps1` hard-fails rather than falling back to its `.cmd` sibling** —
PowerShell refuses to run a `.ps1` under a `Restricted`-class policy, and nothing downstream
recovers the call once that refusal fires; bare-name resolution having already picked `.ps1` (see
above) means the `.cmd` twin is never tried. This hazard is now closed at install time:
Claude-klabauter's fail-closed policy gate (`coordinator_core/install/policy_gate.py`, wired into
`substrate.py`'s `.ps1`-emission path, landed `2b9e319aa`) probes both PowerShell hosts before
emitting `.ps1` launchers and skips `.ps1` emission entirely on a RED verdict, leaving only the
`.cmd` twin installed — so a `Restricted`-policy host never receives a `.ps1` it can't run. The
residual: execution policy is mutable *after* install (the gate's own AC10), so a host that goes
`Restricted` post-install can still hit the hard-fail until the next install pass re-runs the gate.

**No `.cmd` in either tree still bash-routes.** `coordinator-initiative.cmd` and
`coordinator-safe-commit.cmd` (claude-klabauter `coordinator/bin/`) and `resolve-coordinator-clone.cmd`
(`templates/bin/`) were the last BLOCKED-class holdouts; their targets are now Python and all three
are `gen-launcher-shim.py` output carrying a "NO bash re-exec" header. The blocker that held them —
a pure-bash target `python <target>` could not run — is discharged.

## Shim is necessary but not sufficient

Empirical testing on 2026-05-19 showed:

- **cmd.exe / PowerShell callers** — fully fixed by the `.cmd` shim if it's on the Windows user PATH. `Get-Command machine-local` resolves to the shim.
- **Python `subprocess.run([name], shell=False)` (list form)** — Python passes the name directly to `CreateProcess` as `lpApplicationName`, bypassing `PATHEXT`. The shim does NOT help here; `subprocess` throws clean `FileNotFoundError`. The `try/except OSError` in the addon's caller already catches this — no picker fires from the list form. **If a Python caller uses the string form** `subprocess.run(name, ...)` (or `shell=True`), `PATHEXT` IS consulted and the `.cmd` shim DOES help.
- **Python `subprocess.run([full_path_to_extensionless_script], ...)`** — `CreateProcess` reads the file, finds it's not a valid PE, throws `OSError [WinError 193] %1 is not a valid Win32 application`. No picker. The caller must prepend `["bash", ...]` to actually execute the script.
- **Node `child_process.spawn(name, args, { shell: false })`** — same shape as Python subprocess list form; clean ENOENT, no picker.
- **`Process.Start(UseShellExecute=true)` from .NET / Node `child_process.exec` / PowerShell `& $extensionlessName`** — these go through `ShellExecute`; the picker fires unless the name resolves via PATH first. The `.cmd` shim DOES help here.

The shim is a structural fix for the dominant path (shell callers). Python/Node subprocess callers that invoke extensionless scripts must be fixed at the caller (use `bash + path` explicitly).

## Install path

`coordinator:install` Step 3 copies `machine-local.cmd` from `templates/bin/` to the settings-home
bin dir (`bin_dst` — POSIX-host form `${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin`,
the same directory rung 0 / Shape W in `coordinator/snippets/resolve-coordinator-bin.md` resolves
on a PowerShell host), not
`~/.claude/bin/` — the compat-mirror producer that once wrote a second copy there
(`substrate.py`'s Step 3c-compat) was deleted as part of the owns-zero-`~/.claude/bin` retirement
(`docs/plans/2026-07-24-coordinator-owns-zero-claude-bin.md`, Gate 6; a live `CHECK_ONLY=1`
sweep confirmed zero `~/.claude/bin` writes, AC6). Step 3b (Windows-only conditional) adds the
settings-home bin dir to the Windows user `PATH` if not already present. Both are idempotent.
`python3.exe` lands beside the real interpreter (never the settings-home bin dir — the loader
resolves DLLs and the stdlib relative to the executable's own folder, so a shim dir won't work)
via a separate, claude-klabauter-owned install leg (`coordinator_core/ops/ensure_python3_exe_shim.py`)
— not `coordinator:install` Step 3.
<!-- Review: code-reviewer — Finding 1: this sentence still claimed the `.cmd` twins land in
     `~/.claude/bin/`, contradicting the sibling "sit unused in the settings-home bin/" sentence
     below (already repointed by C8) and AC6's verified zero-writes evidence. -->

On non-Windows operators, the `.cmd` file sits unused in the settings-home `bin/` — harmless.

## Maintenance

- The shims are pure ASCII (no BOM) — Windows `cmd.exe` parser breaks on UTF-8 BOM in the first bytes.
- Line endings MUST be `CRLF`, pinned via `coordinator/.gitattributes` `*.cmd text eol=crlf` — see § "The failure mode" above: `cmd.exe` mis-parses LF-only batch files and executes `REM` lines as commands.
- Do not introduce bash-syntax constructs (`/dev/null`, `&>`, etc.) into `.cmd` files — `cmd.exe` syntax only (`nul`, `>nul 2>&1`).
- A linter that "corrects" cmd syntax to bash will break the shim — keep `.cmd` files outside shellcheck/shfmt scope.

## Python resolution on Windows operators

The `python3.exe` PE covers the PATH-lookup case for `python3` (see "The three `python3`-resolution paths" above). The picker can still fire on Windows operators if a different lookup path resolves `python3` first. Three failure modes worth knowing:

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

**Scope note — a `hooks.json` exec-form `command` field is outside this ban's subject class.**
This is a scope clarification, not an exception or carve-out: the ban was never softened, and its
subject was never this caller.

- The ban's subject is our own runtime **scripts**. A `hooks.json` `command` field is harness
  config resolved to an executable via `CreateProcess` before any coordinator code runs, let alone
  the target script — it is not a script itself, so it was never in scope.
- A resolver pattern is structurally unavailable to a `command` field: the documented path
  placeholders are a closed set (`${CLAUDE_PROJECT_DIR}`, `${CLAUDE_PLUGIN_ROOT}`,
  `${CLAUDE_PLUGIN_DATA}`), and env-var interpolation is documented only for HTTP hook headers —
  there is no seam to name a registry-pinned or environment-resolved interpreter, let alone run a
  resolver ahead of the spawn.
- For hooks specifically, whichever real interpreter bare `python3` resolves to at `CreateProcess`
  time IS the resolver, by construction of there being no other seam — and that is fine because the
  fail-open `BOOTSTRAP` injects the coordinator venv's `site-packages` into `sys.path` before the
  target script imports anything, so it does not matter which real interpreter answers.
- The WindowsApps App Execution Alias hazard this doctrine exists to prevent remains live for
  hooks and is closed by a mechanical assertion that a real interpreter (not a stub) resolves ahead
  of `%LOCALAPPDATA%\Microsoft\WindowsApps` on PATH — not by this scope note.

Full mechanism and the DR-044 disambiguation: `cross-platform-shell-portability.md § Hook
registration exec form — bare python3 is safe there (DR-044)`. Tripwire:
`coordinator-tripwires.md § HOOK-EXEC-FORM-BARE-PYTHON3-SAFE`.

## Non-goals (explicitly rejected shapes)

- **Shape β — shared runtime resolver lib at `~/.claude/lib/resolve-python.sh`**: REJECTED for now. Inverts Central's authoring-time direction and creates a runtime dep for every consumer repo. Promote only if a third unique callsite needs the same resolver bug fix, or if a fifth repo joins the cleanup wave (instance-#3 rule). Until then: vendor the resolver pattern per repo (shape α with propagation discipline). (The coordinator's own vendored copy, `coordinator/lib/resolve-python.sh`, has since been retired entirely per the bash-kill campaign — not merely un-shared — in favor of the `COORDINATOR_PYTHON`/registry/PATH resolution contract; "vendor the resolver pattern per repo" as a live recommendation applies to consumer repos that still need a bash-side resolver, not to the coordinator itself.)
- **Shape γ — registry mutation to disable App Execution Aliases**: REJECTED. Operator system-state mutation is out of our lane. Operators who want this can self-service via Settings → Apps → Advanced app settings → App execution aliases → toggle off `python.exe` / `python3.exe`. The wiki documents the option; the setup skill does NOT perform it.

## Related fix sites (per-repo durable fixes)

The shim is the universal structural fix; per-repo code that names `python3` or extensionless `machine-local` in shell heredocs should also be hardened:

- Shell scripts: source `scripts/lib/select-python.sh` (project-rag) or, for the coordinator itself, apply the `COORDINATOR_PYTHON`/registry/PATH resolution contract directly (`coordinator/lib/resolve-python.sh` is retired, not a lib to source — see `machine-local-registry.md § coordinator.python resolution contract`) and use the resolved interpreter, not bare `python3`. Apply WindowsApps exclusion if the resolution path does not already.
- CreateProcess-side (Python `subprocess`/Win32 launch) callers: rely on the native `python3.exe`
  created by claude-klabauter `coordinator_core/ops/ensure_python3_exe_shim.py` (see "The three
  `python3`-resolution paths" above) — do not add a bash or `.cmd` workaround for this caller
  class, neither is reachable from `CreateProcess`.
- Python callers: invoke `[bash, str(reader)]` rather than `[str(reader)]` for extensionless bash scripts. **For `.cmd`/`.exe`/`.bat`/`.com` targets, use bare invocation (natively executable). For everything else (extensionless, `.sh`, `.ps1`), prepend `bash`.** This whitelist-natively-executable inversion is fail-closed vs. the fail-open `suffix == ""` check.
- PowerShell callers: invoke `& bash $script` rather than `& $script` for extensionless bash scripts.

## Quote the `--` Separator When Invoking a Launcher From PowerShell

**Write `'--'`, not a bare `--`, when calling a `.cmd`/`.ps1` launcher from PowerShell.** The
PowerShell binder consumes a bare `--` while parsing the call to the launcher itself, before any
construct inside the launcher's own body can see it — nothing downstream recovers it once that
happens. Quoting it as a string literal (`'--'`) passes it through as an ordinary argument instead.
Source: § 6(ii) of
`cross-repo/archive/2026-08-07-claude-klabauter-em-cmd-forwarder-newline-truncation-fix.md`.

## PowerShell Python Inline Invocation — Use `-c`, Not Bare `-`

**`& $py - @"…"@` passes the here-string as an argv and makes Python read its program from STDIN — use `-c @"…"@` instead.**

This entire hazard class — and the sibling PowerShell `-Command` parser bug that strips embedded
double-quoted literals from an inline Python payload (`claude-code-platform-gotchas.md`) — exists
because a shell transits the payload between the caller and the interpreter. It does not apply to
`hooks.json` exec-form registrations: `type: "command"` plus an `args` array is a list-form spawn
with no shell in the path, so each argument reaches the interpreter verbatim and there is no
quoting apparatus to get right or wrong. The guidance below remains necessary for PowerShell
installer scripts and any other caller that still shells out to invoke Python inline.

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

`Start-Process -WindowStyle Hidden` combined with `-RedirectStandardOutput`/`-RedirectStandardError` on a console-subsystem `python.exe` does NOT reliably hide the window — it allocates a persistent console. The distinction is `SW_HIDE` (hides after creation) vs. `CREATE_NO_WINDOW` (never creates). For reliable headless spawning, use `pythonw.exe` (GUI subsystem) or pass `creationflags=CREATE_NO_WINDOW` (0x08000000) in Python's `subprocess.Popen`. Defense-in-depth audit: grep for `Start-Process.*-WindowStyle Hidden` across all scripts — second occurrence (project-rag-L42): found 10+ sites in the example-game-repo/project-rag install surface.

## console-popup triage — lifecycle scripts dominate, not tests

Console-popup complaints on Windows usually originate in session-lifecycle scripts (startup, health-check, install runners), not the test runner itself. Triage heuristic: audit parallel-launch lifecycle scripts (e.g., session-init hooks, `coordinator-auto-push`, MCP start scripts) before chasing pytest internals. Apply: reproduce by running the lifecycle script path in isolation before adding `CREATE_NO_WINDOW` flags inside tests.

## PowerShell 5.1 ConvertTo-Json empty array serializes as null

PowerShell 5.1 `ConvertTo-Json` serializes an empty `@()` value inside a hashtable as `null`, not `[]`. This breaks any downstream consumer that distinguishes null from empty array. Fix: use `@(,@())` for a forced-array or `[System.Collections.Generic.List[object]]::new()`, then pipe through `ConvertTo-Json`; or post-process with `-replace '"value": null', '"value": []'` where field semantics are known. Audit: any PS5.1 script serializing potentially-empty arrays to JSON needs this guard.

## Why we can't have integration tests for picker-fire

The picker is a GUI dialog. There is no programmatic signal that an assertion can read (no stderr, no exit code, no log entry). The closest we can do is assert at `/setup` time that the orphan-stub and Store-alias-on-PATH configurations are absent after the health check runs — that's an acceptance test on the health check, not on the runtime scripts. Document this expectation rather than chase a test we can't write.
