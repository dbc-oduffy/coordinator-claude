---
title: Bash on Windows Gotchas
status: active
kind: doctrine-wiki
created: 2026-05-18
---

# Bash on Windows Gotchas

## Overview

Git Bash for Windows is a Unix-shell veneer over a Win32 syscall layer; subtle behaviors leak through in the form of line endings, shebang resolution, and subprocess CR stripping. These compound when scripts cross interpreter boundaries — a Python subprocess writing to stdout, a Bash hook reading that output with `read -r`, a git hook invoking a script saved by a Windows editor, or a cross-platform CI runner executing a script with hardcoded paths. Each of the four gotchas below is independently detectable and independently fixable; collectively they cover the most common failure modes encountered in coordinator hook and build-script work on Windows hosts.

---

## 1. Python stdout via `read -r` carries CR on Git Bash

**Source:** 2026-05-17 self, `state/lessons.md` L3.

### Symptom

A pattern like:

```bash
read -r FILE_PATH TRANSCRIPT_PATH TOOL_NAME < <(python -c 'import sys; print("a", "b", "Write")')
```

silently captures `TOOL_NAME="Write\r"` on Git Bash. The trailing carriage-return comes from Python's `print()` using `os.linesep` (`\r\n`) when stdout is a pipe on Windows. The `read` builtin strips the newline but leaves the `\r`.

Downstream comparisons then fail silently:

```bash
[[ "$TOOL_NAME" != "Write" ]]   # unexpectedly true — "Write\r" != "Write"
```

A hook that is supposed to block exits 0 instead. The error is invisible in normal execution.

### Why `bash -x` misleads

`bash -x` traces both operands of `&&` inside `[[ ]]` when the overall expression short-circuits, which makes the short-circuit logic appear broken. The real defect is the value of `$TOOL_NAME`, not the conditional structure. Tracing `[[` output does not reveal embedded `\r`.

### Diagnostic

```bash
echo -n "$TOOL_NAME" | xxd | head -1
# 00000000: 5772 6974 650d  Write.
#                      ^^^ 0d = CR
```

The `0d` byte at the end proves the trailing CR.

### Fix

Pipe Python output through `tr -d '\r'` before the `read`:

```bash
read -r FILE_PATH TRANSCRIPT_PATH TOOL_NAME < <(python -c '...' | tr -d '\r')
```

### Greppable signature

```
read -r ... < <(... python ...)
```

without a `| tr -d '\r'` in the process substitution. Any hook matching this pattern on a Windows-hosted repo should be audited.

---

## 2. CRLF line endings in shell scripts

**Source:** 2026-05-06 example-game-workbench-repo, central queue L207.

### Symptom

Windows-default editors (Notepad, VS Code with default settings, some IDEs) save new files with CRLF (`\r\n`) line endings. When `bash` encounters a shell script with CRLF, the interpreter reads the shebang line as `#!/bin/bash\r` — the trailing `\r` causes the kernel exec path to fail with:

```
bash: /bin/bash\r: No such file or directory
```

or, if the script is sourced rather than executed directly, produces cryptic parse errors on every line.

### Fix

Add a `.gitattributes` rule at repo root:

```
*.sh    text eol=lf
```

After adding the rule, re-normalize existing files:

```bash
git add --renormalize .
git commit -m "normalize shell script line endings to LF"
```

Verify a specific script:

```bash
file hooks/pre-commit
# Good:    hooks/pre-commit: ASCII text
# Problem: hooks/pre-commit: ASCII text, with CRLF line terminators
```

**Establish at init, not after first symptom.** The rule must land before any `.sh` files are added. Retrofitting requires a `--renormalize` pass and risks a noisy diff. Add it alongside `.gitignore` in repo-onboarding.

### Greppable signature

Shell scripts in a repo with no `.gitattributes` rule for `*.sh`:

```bash
grep -c '\.sh.*eol=lf' .gitattributes 2>/dev/null || echo "MISSING"
```

---

## 3. Shell shebangs must respect environment locality

**Source:** 2026-05-06 example-game-workbench-repo, central queue L209.

### Symptom

A script beginning with `#!/bin/bash` runs correctly on a standard Linux host where bash lives at `/bin/bash`, but fails on:

- **macOS with Homebrew bash** — Homebrew installs bash at `/opt/homebrew/bin/bash`; system bash at `/bin/bash` is v3 (GPL-2 restriction). Scripts requiring bash ≥ 4 features silently run under the wrong version.
- **Windows MSYS2 / Git Bash** — bash lives at `/usr/bin/bash` under the MSYS2 prefix (e.g., `C:\Program Files\Git\usr\bin\bash.exe`). `/bin/bash` either does not exist or is a symlink that breaks under certain MSYS2 configurations.
- **CI containers** — minimal images frequently place bash outside `/bin`.

The failure mode is usually `exec format error` or a silent wrong-version execution, neither of which is easy to trace back to the shebang.

### Fix

Use `env`-based shebangs for all interpreted scripts:

| Interpreter | Portable shebang |
|---|---|
| Bash | `#!/usr/bin/env bash` |
| Python 3 (Linux/macOS) | `#!/usr/bin/env python3` |
| Python 3 (Windows-capable) | `#!/usr/bin/env python` |
| Node.js | `#!/usr/bin/env node` |

`/usr/bin/env` is present and stable on Linux, macOS, and Windows Git Bash / MSYS2. It resolves the interpreter through `$PATH`, picking up the environment-local version.

**Windows exception — `python3` is not on PATH.** On standard Windows Python installs (python.org installer), only `python` and `py` are available; `python3` is not symlinked. Scripts using `#!/usr/bin/env python3` fail on Windows with exec-127, which may be misdiagnosed as a "key unset" or other upstream error. Use `#!/usr/bin/env python` for any script that must run on Windows operators (coordinator hook chains, MCP scripts, cross-repo tooling). If the script is Linux/macOS-only, `python3` remains correct.

**Diagnostic — `env: python: No such file or directory` is an invocation error, not a shebang bug; the canonical fix is now the `#!/bin/sh` polyglot.** As of 2026-06-18 (bin-cli-sh-shebang-polyglot), all coordinator/bin Python CLIs ship as `#!/bin/sh` polyglots: line 1 is `#!/bin/sh` and line 2 is the trampoline `''''exec "$(command -v python3 || command -v python || command -v py)" "$0" "$@" #'''`. This means direct `./script` invocation works correctly on macOS 12.3+ (which dropped `/usr/bin/python`) — the kernel execs `/bin/sh`, which reads the trampoline and re-execs the correct Python. There is no longer an "invocation method" vs "shebang" gap to navigate: direct invocation Just Works.

**Legacy workaround (superseded).** Before the polyglot migration, the workaround for `env: python: No such file or directory` was to invoke as `python3 <script>` or `bash <script>` — and `bash <script>` only worked for the subset of scripts that already carried the trampoline. Post-migration (2026-06-18), all 16 coordinator/bin CLIs carry the trampoline, so `bash <script>` and direct `./script` invocation both work universally — the historical caveat that `bash <script>` only helped for trampoline-bearers no longer applies. This workaround is no longer necessary for polyglot CLIs; it remains correct only for the four standalone-python3 scripts that carry no trampoline (`age-sweep-lessons.py`, `doctor-catalog-gen.py`, `doctor-probe-select.py`, `extract-lessons.py`).
<!-- Review: code-reviewer — F4: clarify legacy workaround post-migration: bash <script> now works universally across all 16 CLIs; the historical per-trampoline caveat is gone. -->

**Still banned: flipping the shebang to `#!/usr/bin/env python3`.** Even with the bin/sh polyglot in place, a `python3` shebang on line 1 overrides the polyglot and exec-127s on Windows (clean Windows installs ship only `python`/`py`, not `python3`). The trampoline resolves python3/python/py portably at runtime — the shebang must not pre-empt it. This misdiagnosis caused a 16-script regression on 2026-06-17; it is intercepted at edit-time by the `block-python3-shebang-flip.sh` PreToolUse hook (`WINDOWS-PYTHON-SHEBANG`), with `bin/check-windows-python-shebang.sh` as the static-grep backstop.

*Lesson origin:* 4 coordinator scripts (`cross-repo-memo`, `cross-repo-memo.test.py`, `_machine_local.py`, `publish_sync.py`) changed from `python3` to `python` shebang in commit 6fe5a986. The original lesson entry misdiagnosed exec-127 as a key-unset symptom and proposed a PowerShell workaround; the one-line shebang change is the actual fix.

### Exception

Scripts that are deliberately pinned to a specific interpreter version (e.g., a UE build script that requires exactly the Python bundled with UE) should document the explicit path and why portability is intentionally sacrificed — do not silently use a hardcoded path for convenience.

### Greppable signature

```bash
grep -rn '^#!/bin/bash' hooks/ bin/ scripts/
```

Any hit is a portability debt item.

---

## 4. `flock` is not on Git Bash for Windows — use `mkdir` for shell locks

**Source:** 2026-05-08 self, `state/lessons.md` ~L37.

### Symptom

Scripts that use `flock` for mutual exclusion silently break on Win11 Git Bash:

```bash
command -v flock   # returns empty — flock is not available
flock /tmp/my.lock -c "do_work"
# bash: flock: command not found
```

On Linux, `flock` is a `util-linux` binary. Git Bash ships a subset of GNU tools; `flock` is not among them. Scripts that assume `flock` availability will either fail loudly (if they check) or skip locking entirely (if they don't), producing race conditions that are hard to reproduce outside Windows.

### Fix

Default to `mkdir`-as-lock — a POSIX-portable atomic primitive. `mkdir` succeeds atomically; `EEXIST` signals the lock is held. Write `$$` into `$LOCK_DIR/pid`, reap on dead-PID with `kill -0`, remove on release:

```bash
LOCK_DIR="/tmp/my-script.lock"
acquire_lock() {
    mkdir "$LOCK_DIR" 2>/dev/null && { echo $$ > "$LOCK_DIR/pid"; return 0; }
    local pid; pid=$(cat "$LOCK_DIR/pid" 2>/dev/null)
    [[ -n "$pid" ]] && ! kill -0 "$pid" 2>/dev/null && rm -rf "$LOCK_DIR" \
        && mkdir "$LOCK_DIR" && echo $$ > "$LOCK_DIR/pid" && return 0
    return 1
}
release_lock() { rm -rf "$LOCK_DIR"; }
```

Works on Linux, macOS, and Git Bash without modification.

### Availability check before planning

If `flock` usage is under consideration for a new script that must target Windows runners, verify first:

```bash
command -v flock || echo "flock unavailable — use mkdir-lock"
```

Bake the detection into the plan-time substrate check, not the runtime script. Fail loud if the required primitive is absent rather than degrading silently.

### Greppable signature

```bash
grep -rn '\bflock\b' hooks/ bin/ scripts/
```

Any hit in a script that may run on Windows is a portability risk requiring the `mkdir`-lock substitution.

---

## 5. PowerShell `machine-local` helper routes through `bash -c`

**Source:** 2026-05-20, eager-agent-calibration workstream.

### Symptom

`bin/claude-machine-local.ps1` sources `machine-local` by invoking `bash -c`. If `bash` is not on the Windows user PATH (rare but possible on minimal Windows installs) or if the bash subprocess receives a different `PATH` than the interactive PowerShell session, the helper silently fails — exports are missing, no error surfaced to the caller.

### Why it routes through bash

`machine-local` is a bash script. PowerShell cannot source or execute it directly as a native command. The `.ps1` helper therefore wraps: `$result = bash -c "source ~/.claude/bin/machine-local && ..."`. This is a latent-bug carve-out: on any machine where bash is unavailable to PowerShell, the helper is a no-op.

### Fix / Mitigation

- The `coordinator:install` Step 3 health check confirms `bash` is on PATH before declaring the shim install complete. If bash is absent, the `machine-local.cmd` shim still routes correctly for cmd.exe / PowerShell callers using PATHEXT lookup.
- Scripts that need registry values from PowerShell should prefer `bash -c "~/.claude/bin/machine-local get <key>"` directly rather than dot-sourcing `claude-machine-local.ps1`.
- The latent-bug is documented in `bin/claude-machine-local.ps1` itself — do not remove this comment.

### Greppable signature

```
claude-machine-local.ps1
```

Any future refactor of this helper must preserve the `bash -c` routing and the latent-bug comment.

---

## 6. Interactive-Prompt Bypass for `/dev/tty`-less Environments

**Source:** rag-ue-addon 2026-05-28.

### Symptom

A publish or release script that uses `read -p "Confirm? [y/N]: "` to gate an externally-visible action hard-requires `/dev/tty` for keyboard input. In a Claude Code Bash-tool-driven session on Windows Git Bash (no `/dev/tty`) or in some CI runners, the script hangs or fails — blocking automated or agent-driven publish flows even when the PM has authorized the action.

### Why interactive-prompt bypass differs from safety override

`_OVERRIDE` env vars (e.g., `COORDINATOR_OVERRIDE_NO_VERIFY=1`) are for bypassing *safety checks*. An interactive-prompt block is an *environmental constraint*, not a safety concern — the PM has already authorized the action; the issue is that `/dev/tty` is absent. Conflating the two by reusing the same env var mixes authorization semantics.

### Fix

Add a third `elif` branch to the confirmation gate:

```bash
if [ -t 0 ]; then
    read -p "Confirm? [y/N]: " answer
    [[ "$answer" =~ ^[Yy] ]] || exit 1
elif [ -n "${SCRIPT_CONFIRM:-}" ]; then
    echo "Non-interactive: SCRIPT_CONFIRM set — proceeding"
else
    echo "Non-interactive and SCRIPT_CONFIRM not set — aborting" >&2; exit 1
fi
```

The `_CONFIRM` suffix signals "I am explicitly bypassing the interactive prompt" (not a safety bypass). Default unset preserves human-at-keyboard as the gate; explicit value (`SCRIPT_CONFIRM=yes`) is the documented escape hatch for agent-driven and CI contexts.

---

## 7. PowerShell Here-String Syntax Corrupts Commit Subjects in the Bash Tool

**Source:** rag-ue-addon 2026-05-23.

### Symptom

A multi-line `git commit -m` message authored via PowerShell here-string syntax (`@'…'@`) in the **Bash tool** produces a commit where the subject is the literal `@` character and the intended subject is demoted to the body.

### Why

PowerShell here-string syntax (`@'…'@`) is valid PowerShell only — it is interpreted by the PowerShell engine before reaching the command. In the **Bash tool** it is not interpreted; bash treats the raw `@` + newline as the start of the message, making the first real line the body, not the subject.

### Fix

In the Bash tool, always pass git commit messages via:

```bash
git commit -m "$(cat <<'EOF'
Subject line here

Body here.
EOF
)"
```

or a single `-m "..."`. Reserve `@'…'@` for the **PowerShell tool** only. If a concurrent EM stacks a commit on top of a malformed one on a shared branch, the subject cannot be cleanly amended — use the H8 plumbing-reword procedure.

---

## 8. `bash -n` False Positives on CRLF Working Trees

**Source:** project-rag 2026-05-24.

### Symptom

`bash -n <installer.sh>` reports a syntax error ("unexpected `fi`" or similar) on a heredoc-heavy installer even though the committed blob is clean. Root cause: `core.autocrlf=true` expands the LF-committed blob to CRLF in the working tree; the heredoc closer (`DELIM\r`) no longer matches the opener (`DELIM`), causing the heredoc to swallow to EOF and confuse the parser. SC1017 (literal CR) is the ShellCheck signal.

### Diagnostic

```bash
git config core.autocrlf   # should be true on Windows
git show HEAD:<path> | python -c "import sys; print('CRLF' if b'\r\n' in sys.stdin.buffer.read() else 'LF')"
# LF → committed blob is clean; the working-tree checkout is the problem
```

### Fix

Use ShellCheck (the real lint) rather than `bash -n` as the syntax gate on installers in this repo. ShellCheck is aware of CRLF (SC1017) and correctly isolates the line-ending issue. `bash -n` is not an appropriate syntax-validity gate on a Windows working tree with `core.autocrlf=true`.

`/workweek-complete` already runs ShellCheck — do not add `bash -n` as a parallel gate.

---

## 9. Extensionless Python CLIs break under a `bash <script>` prefix — add a polyglot trampoline

**Source:** 2026-05-30 self (`cross-repo-memo` papercut).

### Symptom

An extensionless Python CLI on PATH (e.g. `cross-repo-memo`, `install-sentinel-write`) is *designed* to be invoked directly — `cross-repo-memo --to … --topic …` — relying on its `#!/usr/bin/env python` shebang. But the habitual reach for "run a script at a path" is `bash <path>`, and the agent (or a human) types:

```bash
bash ~/.claude/.../bin/cross-repo-memo --to project-rag-em --topic …
```

`bash` then tries to interpret **Python** as shell. Best case it drops into the Python REPL banner and a traceback; worst case it executes stray lines (`from … import …` → `import: command not found`, then a `SyntaxError near unexpected token '('`). The CLI never runs, and the operator burns a round guessing whether the flags or the path were wrong — when neither was; only the `bash ` prefix was.

The script's own docstring warning ("do NOT invoke as `bash <script>`") does **not** prevent this: the docstring is only visible *after* the failed invocation. Documentation cannot fix a muscle-memory problem — the file has to absorb the habit.

### Fix — sh/python polyglot trampoline

Add one inert-to-Python, executable-to-sh line directly below the shebang. Under sh/bash it resolves the interpreter via `command -v python3 || command -v python || command -v py`, captures its path through `$()`, and re-execs under it. Under Python the same line is a no-op string literal:

```python
#!/usr/bin/env python
''''exec "$(command -v python3 || command -v python || command -v py)" "$0" "$@" #'''
"""Real module docstring continues here…"""  # see `from __future__` interaction below before adding one
```

Now `bash <script>`, `python <script>`, and direct shebang invocation all re-exec under whichever Python interpreter the platform actually ships — the `bash` prefix is *forgiven*, not punished. Recovery improves too: `bash <script> --help` prints the argparse help instead of a traceback.

**Why the three-way probe.** macOS 12.3+ removed the `/usr/bin/python` symlink (Apple ships `python3` only); modern Linux distros likewise ship only `python3`; standard Windows python.org installs ship `python` and the `py` launcher but no `python3` symlink. A trampoline that hard-codes any single name exec-127s on the other platforms, and our EMs reach for `bash <script>` from all three. `command -v python3 || command -v python || command -v py` picks whichever exists. Keep all three — single-interpreter forms have regressed before (see `cross-repo-memo` commit history: `6fe5a986` flipped to `python` for Windows and silently broke Mac/Linux EMs until the three-way probe landed).

**Why command-substitution, not `&& exec foo || exec bar`.** A chained `exec X || exec Y` form looks symmetric but isn't: in sh, a failed `exec` is fatal and does NOT fall through to the `||` branch. The `||` only fires if the preceding command (e.g. `command -v X`) returns non-zero before `exec` runs. Command-substitution collapses the probe to one resolved path and a single `exec` — no chained-`exec`-fallback footgun, and it's the form already used by `bin/install-sentinel-write`. Stay aligned with that sibling.

**`from __future__` interaction (gotcha-within-the-gotcha).** A `from __future__ import …` statement must be the file's first statement, and the *only* string literal permitted before it is the module docstring. The trampoline line is a string literal — so it occupies that single slot. A file that has *both* a trampoline **and** a `"""docstring"""` before `from __future__` raises `SyntaxError: from __future__ imports must occur at the beginning of the file`. Resolution: let the trampoline be the sole leading string and demote the human docstring to a `#` comment block (CLIs carry their `--help` text in argparse's `description=`, so nothing reads `__doc__`). See `bin/install-sentinel-write` for the worked example.

### Why this over a separate `.sh` wrapper

A sibling `cross-repo-memo.sh` that execs the python would also make `bash …` work, but it doubles the surface (two files per tool, flag/help drift, two PATH entries) and the operator may still call the bare name. The polyglot keeps it **one file**. (`bin/machine-local` uses the separate-wrapper form for historical reasons and works fine — but new extensionless Python CLIs should prefer the trampoline.)

### Greppable signature

```bash
# Extensionless Python CLIs in bin/ that lack the trampoline. The `.py`
# extension is itself a "this is Python" signal, so `*.py` files are exempt —
# the trap is specific to extensionless names that read like commands.
# Match by the invariant marker `''''exec` (the polyglot opener followed by the
# sh `exec` keyword) rather than by the interpreter name — that way the check
# catches both the canonical command-substitution form and any legacy
# `''''exec python "$0"` survivors, without false-negatives on a CLI that
# trims the probe (e.g. drops `py` on a macOS/Linux-only tool).
for f in bin/*; do
  case "$(basename "$f")" in *.*) continue;; esac     # skip files with an extension
  [ -f "$f" ] && head -1 "$f" | grep -q python \
    && ! grep -qF "''''exec" "$f" && echo "no trampoline: $f"
done
```

Any hit is a `bash <script>` papercut waiting to happen.

---

## 10. `git -C /x/...` via a Python `subprocess` silently fails — Windows-native git can't resolve MSYS paths

**Source:** 2026-06-01 example-game-repo-em (cross-repo memo — phantom-dirty-index investigation).

### Symptom

A Python `subprocess.run(["git", "-C", "/x/repo", "status", "--porcelain"])` returns **empty stdout with a non-zero returncode** — which *reads exactly like* "0 modified / clean tree." An enumeration built on that output (e.g. a phantom-dirty file list, a drift check, a "which files changed" sweep) silently produces an **empty set that masks the real state**. The author iterates against a clean-looking nothing while the tree is actually dirty.

### Why

A `/x/...` (or `/c/...`) path is an **MSYS/Git-Bash mount-table POSIX path**, not a real filesystem path. When you run `git` *inside* bash, bash's MSYS layer translates `/x/repo` → `X:\repo` before the `git.exe` exec. A Python `subprocess`, by contrast, invokes **Windows-native `git.exe` directly** with no MSYS translation — so git.exe is handed a literal `/x/repo` it cannot resolve, errors out, and returns empty. The empty stdout is an *error channel*, not an *answer channel* — but a caller that only inspects stdout cannot tell the difference.

### Fix

- **Enumerate in bash, not Python, for any `git -C /x/...`.** Bash resolves the mount path; the command actually runs. This is the simplest fix and the one the memo validated.
- If Python *must* drive git, pass a **Windows-native path** (`X:/repo` or `X:\\repo`, or translate via `cygpath -w "$p"`), AND **check `returncode` explicitly** — never treat empty stdout as "clean." `result.check_returncode()` or an explicit `if result.returncode != 0: raise` converts the silent mask into a loud failure.

This is arguably the higher-value universal in the source memo: it silently corrupts **any** Python-driven git enumeration on Windows, well beyond the phantom-dirty case that surfaced it.

### Greppable signature

```bash
# Python subprocess invoking git -C with an MSYS mount path (/x/, /c/, …).
# These run Windows-native git.exe, which cannot resolve the POSIX path.
grep -rn 'subprocess.*git.*-C.*["'\'']/[a-z]/' --include='*.py' . \
  | grep -v 'cygpath\|check_returncode\|returncode'
```

---

## 11. `GIT_OPTIONAL_LOCKS=0` makes `git status` refresh in memory but never persist — flaky contradictory reads

**Source:** 2026-06-01 example-game-repo-em (same memo).

### Symptom

`git status --porcelain` reads **0** while `git status --short` reads **thousands** — in the same second, on the same tree. Repeated reads disagree with each other. The phantom-dirty count appears to flap rather than hold steady.

### Why

Agent Bash harnesses commonly run with `GIT_OPTIONAL_LOCKS=0` (it avoids taking the `index.lock` so concurrent git invocations don't contend). But persisting a stat-cache refresh to the index **requires** taking that lock. So git computes the clean refresh **in memory**, uses it for *that* invocation's output, and then discards it — the next invocation recomputes from the still-stale on-disk index. Two reads in the same second legitimately disagree because one persisted nothing for the other to read.

### Fix

- **Trust the stable repeated reading; never act on a single flaky read.** This composes directly with `tool-output-flakiness-protocol.md` (§ "two reads disagree → read a third way; never act on one flaky read before an irreversible op").
- To actually *clear* the phantom state, the index lock has to be taken — either let the `coordinator-renormalize-index` SessionStart hook do its real `git add` (which persists), or run the hygiene op in a shell where `GIT_OPTIONAL_LOCKS` is unset. A read-only `git status` under `OPTIONAL_LOCKS=0` will never make the phantoms go away no matter how many times you run it.

### Greppable signature

```bash
# Disagreement between two status reads, or OPTIONAL_LOCKS in the env of a
# script that then acts on a status count.
grep -rn 'GIT_OPTIONAL_LOCKS' . --include='*.sh'
# Behavioral tell: --porcelain and --short counts diverge in the same second.
```

---

## 12. Windows PID recycling makes bare `Get-Process -Id <pid>` a false-positive liveness probe

**Source:** project-rag, 2026-06-09. [universal]

### Symptom

A supervisor-alive check using bare `Get-Process -Id $supPid` (PowerShell) or `kill -0 $supPid` (Git Bash) returns true for a recorded PID, but the actual supervisor process has long since exited. Windows recycles PIDs aggressively — the kernel has reissued the PID to an unrelated process that happens to inherit the recycled number. Stale lockfiles are treated as live; the supervisor is "running" according to the probe but doing no work.

### Why

Liveness ≠ identity. A live process at PID N tells you the kernel has a process there, not that it's *your* process. POSIX has the same risk in principle but Linux/macOS recycle PIDs slowly enough that the failure is rare in practice; Windows recycles fast enough that the false positive is routine.

### Fix

Liveness checks on a recorded PID must verify identity by matching the process's `CommandLine` against a known sentinel string:

**PowerShell:**
```powershell
Get-CimInstance Win32_Process -Filter "ProcessId = $pid" |
    Where-Object CommandLine -like '*known-identifier*'
```

**POSIX:**
```bash
ps -p "$pid" -o args= | grep -q 'known-identifier'
```

The same hazard exists everywhere a PID is persisted across the dead-recycle boundary — lockfiles, supervisor metadata, session-tracker dirs. Bare `kill -0` / `Get-Process -Id` is a tripwire on any such surface.

### Greppable signature

```bash
grep -rn 'Get-Process -Id\|kill -0' bin/ hooks/ scripts/ --include='*.sh' --include='*.ps1' \
    | grep -v 'CommandLine\|args=\|-o args'
```

Any hit on a PID-from-file probe without an identity verification step is the bug.

---

## Detection signatures (greppable)

| Signature | Risk |
|---|---|
| `read -r ... < <(... python ...)` without `\| tr -d '\r'` | Trailing CR silently corrupts captured variable |
| Shell scripts in repo without `.gitattributes` rule for `*.sh` | CRLF breaks shebang resolution |
| `#!/bin/bash` (instead of `#!/usr/bin/env bash`) | Hardcoded path breaks on macOS Homebrew and MSYS2 |
| `flock` invocations in scripts targeting Windows runners | `flock` absent on Git Bash; locking silently skipped |
| `#!/usr/bin/env python3` in coordinator or MCP scripts | exec-127 on Windows; misdiagnosed as upstream error; change to `python` |
| `read -p "..."` in publish/release scripts with no `_CONFIRM` bypass | Hangs in Bash-tool / CI sessions with no `/dev/tty`; use the `_CONFIRM` env-var escape hatch |
| `git commit -m @'…'@` in the Bash tool | PowerShell here-string syntax; subject becomes `@`, body shifts down; use heredoc or `-m "..."` |
| `bash -n` used as syntax gate on installers in Windows working tree | False positives under `core.autocrlf=true` (SC1017 literal CR); use ShellCheck instead |
| Cross-shell line-count comparison (`bash wc -l` vs PowerShell `Measure-Object -Line`) | CRLF/final-newline handling differs; mismatches misread as concurrent-EM edits; use `git status` + `git log -- <file>` as the ONLY drift oracle — never cross-shell counts |
| Extensionless Python CLI in `bin/` (shebang `python`, no `''''exec python "$0"` line) | `bash <script>` feeds Python to bash → traceback; add the §9 polyglot trampoline |
| Trampolined file with BOTH a `''''exec…'''` line AND a `"""docstring"""` before `from __future__` | Two leading string literals → `SyntaxError: from __future__ … must occur at the beginning`; let the trampoline be the sole leading string (§9), demote the docstring to a `#` comment block |
| Python `subprocess` calling `git -C /x/...` (or `/c/...`) without `cygpath -w` / explicit `returncode` check | Windows-native git.exe can't resolve the MSYS path → empty stdout masquerades as a clean tree (§10); enumerate in bash, or pass a Windows path and check returncode |
| Script reads a `git status` count under `GIT_OPTIONAL_LOCKS=0` and acts on it | Refresh computed in memory but never persisted → `--porcelain` and `--short` disagree second-to-second (§11); trust the stable repeated read, persist via a real `git add` |

---

## Related

## heredoc + herestring on fd 0 silently discards one stream

In bash, `python - <<HEREDOC ... HEREDOC <<< "$payload"` silently empties stdin — you cannot feed both a heredoc and a herestring to fd 0 in the same command. Only the last redirect wins; the script sees an empty input. Audit rule: grep any script that combines `<<` and `<<<` on the same command for this footgun. Fix: write the payload to a temp file, or pass it via an env var and have the Python script read `os.environ`.

- → `docs/wiki/concurrent-em-hazards.md` § H23 — the EOL phantom-dirty index (stale line-ending blob size flags content-equal files) and the `coordinator-renormalize-index` automatic fix. §10 and §11 here are the two Windows gotchas that ambush an EM *diagnosing* a phantom-dirty tree before they find H23's fix.
- → `docs/wiki/claude-code-platform-gotchas.md` — Windows subprocess pop-ups, MCP CRLF, process-group handling
- → `docs/wiki/python-subprocess-patterns.md` — `CREATE_NO_WINDOW` flag, `pythonw.exe` vs `python.exe`, stdout pipe encoding
- → `docs/wiki/implementation-standards-by-domain.md` § Shell — idempotency, concurrency, resume strategy requirements for load-bearing scripts
