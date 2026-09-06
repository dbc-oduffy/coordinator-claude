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

**Source:** self, `state/lessons/` L3.

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

**Source:** example-game-workbench-repo, central queue L207.

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

**Source:** example-game-workbench-repo, central queue L209.

### Symptom

A script beginning with `#!/bin/bash` runs correctly on a standard Linux host where bash lives at `/bin/bash`, but fails on:

- **macOS with Homebrew bash** — Homebrew installs bash at `/opt/homebrew/bin/bash`; system bash at `/bin/bash` is v3 (GPL-2 restriction). Scripts requiring bash ≥ 4 features silently run under the wrong version.
- **Windows MSYS2 / Git Bash** — bash lives at `/usr/bin/bash` under the MSYS2 prefix (e.g., `C:\Program Files\Git\usr\bin\bash.exe`). `/bin/bash` either does not exist or is a symlink that breaks under certain MSYS2 configurations. <!-- foreign-path-ok: documents real MSYS2 install path shape, not a checkout location -->
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

**Discriminant — which shape is my entrypoint? Answer this before applying any rule below.** A `python3` shebang's safety on Windows depends entirely on how the file is invoked there, not on the shebang line in isolation. Two shapes exist for a `coordinator/bin` entrypoint:

- **Legacy `#!/bin/sh` polyglot** — the ~16 not-yet-migrated `coordinator/bin` CLIs. These retain operator/shell-invocation surfaces (bareword-through-git-bash, `bash <script>`) that the shebang is consulted for. This is legacy debt on a kill-bash-roadmap continuation being migrated away, not a permanent coequal class — the Windows exception and ban below apply to it in full until each CLI migrates.
- **Pure-Python-with-`.cmd`** — the migration target every `coordinator/bin` entrypoint converges on: the 109 W4a trampolines (commit `b5a4192c`) and any future pure-`.py` bin entrypoint with a generated `.cmd` launcher (the generator, C1/`gen-launcher-shim.py`, keeps `.cmd` and shebang symmetric). Here a `python3` shebang is **required and correct** — see the carve-out below the ban.

If your file is the legacy polyglot shape, the Windows exception and ban in the next two paragraphs apply as written. If it is pure-Python-with-`.cmd`, skip to the carve-out below "Still banned."

**Windows exception (legacy `#!/bin/sh` polyglot shape) — `python3` is not on PATH.** On standard Windows Python installs (python.org installer), only `python` and `py` are available; `python3` is not symlinked. Scripts using `#!/usr/bin/env python3` fail on Windows with exec-127, which may be misdiagnosed as a "key unset" or other upstream error. Use `#!/usr/bin/env python` for any legacy-polyglot script that must run on Windows operators (coordinator hook chains, MCP scripts, cross-repo tooling) as long as it retains a bareword/shell-invocation surface. If the script is Linux/macOS-only, `python3` remains correct.

**Diagnostic — `env: python: No such file or directory` is an invocation error, not a shebang bug.** On the legacy `#!/bin/sh` polyglot shape, line 1 is `#!/bin/sh` and line 2 is the trampoline `''''exec "$(command -v python3 || command -v python || command -v py)" "$0" "$@" #'''`, so direct `./script` invocation resolves correctly on macOS 12.3+ (which dropped `/usr/bin/python`): the kernel execs `/bin/sh`, which reads the trampoline and re-execs the correct Python. On that shape there is no "invocation method" vs "shebang" gap to navigate.

**That polyglot is the legacy shape, not the target.** It is bash, and this repo treats structural bash as debt to be removed — the canonical shape is a pure-Python entrypoint with a generated `.cmd` launcher (see the carve-out below, and § 9). Do not read this diagnostic as a reason to author a new polyglot; it explains the behaviour of the ~16 CLIs still awaiting migration.

**Invoking a script that carries no trampoline.** `python3 <script>` (or `bash <script>`) is the workaround for `env: python: No such file or directory` on a script with no trampoline of its own — `bash <script>` only ever helps a trampoline-bearer. Every `coordinator/bin` polyglot CLI carries one, so both direct `./script` and `bash <script>` work there; the prefix form remains necessary only for the four standalone-python3 scripts that carry no trampoline (`age-sweep-lessons.py`, `doctor-catalog-gen.py`, `doctor-probe-select.py`, `extract-lessons.py`).

**Still banned on the legacy `#!/bin/sh` polyglot shape: flipping the shebang to `#!/usr/bin/env python3`.** On a file that still carries the bin/sh polyglot trampoline, a `python3` shebang on line 1 overrides the polyglot and exec-127s on Windows (clean Windows installs ship only `python`/`py`, not `python3`). The trampoline resolves python3/python/py portably at runtime — the shebang must not pre-empt it. **There is no live PreToolUse hook enforcing this.** A `block-python3-shebang-flip.sh` hook and a `bin/check-windows-python-shebang.sh` static-grep backstop are both absent from this repo; do not assume edit-time interception. The real teeth are the **AC5 two-layer test gate** — layer (a) asserts entrypoint-invariant `.cmd`/shebang symmetry, layer (b) asserts no caller invokes a pure-`.py` entrypoint as a bareword through git-bash — not a hook.

**Carve-out — `python3` shebang is SAFE, and correct, on the pure-Python-with-`.cmd` shape, when BOTH invariants hold.** This does not weaken the ban above; the ban still governs the legacy `#!/bin/sh` polyglot shape (the ~16 CLIs awaiting migration) in full. For the pure-`.py` bin entrypoint shape instead (the 109 W4a trampolines, `b5a4192c`, and any future pure-`.py` bin entrypoint with a generated `.cmd`):

- **(a) Guaranteed `.cmd` launcher coverage.** On Windows, invoked as a bareword from `cmd.exe`, the co-located `.cmd` wins via `PATHEXT` and the shebang is never read there; on macOS/Linux, `python3` is the only interpreter present, so the shebang is exactly right. Enforced by AC5 layer (a). The generator (C1 / `gen-launcher-shim.py`) is the mechanism that keeps `.cmd` and shebang symmetric — a `.cmd`-less pure-`.py` entrypoint does not qualify for this carve-out.
- **(b) No caller invokes the entrypoint as a bareword `.py` through git-bash.** A git-bash-invoked bareword `.py` DOES read and honor the shebang on stock Windows — the `.cmd` does not rescue a `.py`-suffixed bareword from a bash context, so it exec-127s with no `python3` present. Every caller of a pure-`.py` bin entrypoint must use a resolved-interpreter prefix or the extensionless `.cmd`, never a bareword `.py`. Enforced by AC5 layer (b) (the caller-side gate).

Both invariants must hold; either one alone is not sufficient. Fold this same two-invariant framing into `cross-platform-invocation-parity.md` when reading that wiki — it restates the discriminant at CLAUDE.md altitude.

**The carve-out is unconditional.** There is no live guard gating a file's on-disk line 1 for `#!/bin/sh`; the `#!/bin/sh`-polyglot invariant such a guard would enforce is retired, and there is no live guard left to reconcile this carve-out against. The carve-out's underlying point still holds without it: the `#!/bin/sh` polyglot shape is legacy debt on a kill-bash-roadmap continuation, not a coexisting class preserved indefinitely.

### Exception

Scripts that are deliberately pinned to a specific interpreter version (e.g., a UE build script that requires exactly the Python bundled with UE) should document the explicit path and why portability is intentionally sacrificed — do not silently use a hardcoded path for convenience.

### Greppable signature

```bash
grep -rn '^#!/bin/bash' hooks/ bin/ scripts/
```

Any hit is a portability debt item.

---

## 4. `flock` is not on Git Bash for Windows — use `mkdir` for shell locks

**Source:** self, `state/lessons/` ~L37.

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

**Source:** eager-agent-calibration workstream.

### Symptom

`bin/claude-machine-local.ps1` sources `machine-local` by invoking `bash -c`. If `bash` is not on the Windows user PATH (rare but possible on minimal Windows installs) or if the bash subprocess receives a different `PATH` than the interactive PowerShell session, the helper silently fails — exports are missing, no error surfaced to the caller.

### Why it routes through bash

`machine-local` is a bash script. PowerShell cannot source or execute it directly as a native command. The `.ps1` helper therefore wraps: `$result = bash -c "source <settings-home>/bin/machine-local && ..."`. This is a latent-bug carve-out: on any machine where bash is unavailable to PowerShell, the helper is a no-op.

### Fix / Mitigation

- The `coordinator:install` Step 3 health check confirms `bash` is on PATH before declaring the shim install complete. If bash is absent, the `machine-local.cmd` shim still routes correctly for cmd.exe / PowerShell callers using PATHEXT lookup.
- Scripts that need registry values from PowerShell should prefer `bash -c "<settings-home>/bin/machine-local get <key>"` directly rather than dot-sourcing `claude-machine-local.ps1`.
- The latent-bug is documented in `bin/claude-machine-local.ps1` itself — do not remove this comment.

### Greppable signature

```
claude-machine-local.ps1
```

Any future refactor of this helper must preserve the `bash -c` routing and the latent-bug comment.

---

## 6. Interactive-Prompt Bypass for `/dev/tty`-less Environments

**Source:** rag-ue-addon.

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

**Source:** rag-ue-addon.

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

**Source:** project-rag.

### Symptom

`bash -n <installer.sh>` reports a syntax error ("unexpected `fi`" or similar) on a heredoc-heavy installer even though the committed blob is clean. Root cause: `core.autocrlf=true` expands the LF-committed blob to CRLF in the working tree; the heredoc closer (`DELIM\r`) does not match the opener (`DELIM`), causing the heredoc to swallow to EOF and confuse the parser. SC1017 (literal CR) is the ShellCheck signal.

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

## 9. Extensionless Python CLIs break under a `bash <script>` prefix — demote the docstring

**Source:** self (`cross-repo-memo` papercut).

> **Do not apply the trampoline prescription below — it is retired.** The blessed shape is DR-076
> cross-platform-invocation-parity: a `#!/usr/bin/env python3` shebang plus a co-located `.cmd`
> launcher, no polyglot trampoline. Claude-klabauter's
> `coordinator/bin/tests/test_no_bin_polyglot_invariant.py` enforces it.
>
> The trampoline costs **~326ms per invocation on Windows** (1306ms through the sh-shim re-exec
> versus 980ms direct, byte-identical output — `state/audits/2026-07-20-sh-suffixed-python-trampolines.md`),
> paid on every call whether or not the hazard below is ever hit. It is also not what fixes the
> hang described below: **the docstring is the hazard, and demoting it to a `#` comment block is
> the fix** — comments are inert to bash, and the demotion costs nothing at runtime.
>
> Without a trampoline, a mistaken `bash <script>` fails fast with a syntax error instead of
> hanging. That is the intended outcome, not a regression: Windows callers use the `.cmd` sibling,
> which is why DR-076 requires the pairing. Fail-fast plus a working `.cmd` beats an unbounded
> hang plus a permanent tax.
>
> Enforcement for DoE's own templates:
> `coordinator/tests/test_bin_template_polyglot_trampoline.py` — asserts no trampoline, no prose
> docstring, and a `.cmd` sibling.
>
> The trampoline prose below is kept for provenance — it explains the three-way interpreter probe
> and the `from __future__` interaction, which stay instructive. **Do not apply it to new files.**

### Symptom

An extensionless Python CLI on PATH (e.g. `cross-repo-memo`, `install-sentinel-write`) is *designed* to be invoked directly — `cross-repo-memo draft … --to …` — relying on its `#!/usr/bin/env python` shebang. But the habitual reach for "run a script at a path" is `bash <path>`, and the agent (or a human) types:

```bash
bash ~/.claude/.../bin/cross-repo-memo draft <slug> --to project-rag-em …
```

`bash` then tries to interpret **Python** as shell. Best case it drops into the Python REPL banner and a traceback; worst case it executes stray lines (`from … import …` → `import: command not found`, then a `SyntaxError near unexpected token '('`). The CLI never runs, and the operator burns a round guessing whether the flags or the path were wrong — when neither was; only the `bash ` prefix was.

The script's own docstring warning ("do NOT invoke as `bash <script>`") does **not** prevent this: the docstring is only visible *after* the failed invocation. Documentation cannot fix a muscle-memory problem — the file has to absorb the habit.

### The failure is not always loud — a module docstring turns it into a silent hang

The symptom above describes the *no-docstring* case, and it undersells the
hazard: a docstring turns the same mistake into a silent hang.

A `#` comment is inert to bash. **A module docstring is not.** Bash reads `"""…"""` as quoted
words and interprets **backtick spans inside it as command substitution** — and our docstrings are
markdown prose, so they are full of `` `backticked` `` identifiers. If any backtick span happens to
contain something that reads stdin, bash runs it and blocks forever.

Worked example, `~/.claude/bin/resolve-coordinator-clone` before the fix. Its docstring contained
the prose *"the bash trampoline this shim used to `` `exec bash` `` against"*, and `bash -x` showed:

```
++ .claude
resolve-coordinator-clone: line 50: .claude: command not found
++ exec bash          <-- process replaced by a bash reading stdin. Hangs. Zero output.
```

The hang came out of a sentence *describing* the bug.

Three properties make this far worse than the traceback this section originally predicted:

- **It needs an open stdin.** Under `</dev/null` the same file exits fast. So it hides in exactly
  the contexts that matter — a `pythonw` parent, a PowerShell caller, an install script — and
  presents as a silent multi-minute wedge rather than an error.
- **It walks straight through every defence.** A hang is not a non-zero exit, so `try/except`,
  exit-code gating, `|| true` and `2>/dev/null` all pass it through untouched.
- **Fail-fast is an accident, not a guarantee.** At the time of writing, 290 of the 293
  extensionless Python entrypoints under `~/.claude/bin` fail fast purely because the generator
  template happens to use `#` comments rather than a docstring. Only 3 carry a real module
  docstring, and 2 of those 3 hang. Every one of the other 291 is one backticked `` `cat …` `` in a
  docstring away from joining them.

This is the mechanism the trampoline actually defends against, and it is why demoting the docstring
to a `#` block (below) is **load-bearing, not cosmetic** — it is what makes the prose inert to bash.

### Historical fix (retired — see notice above) — sh/python polyglot trampoline

Add one inert-to-Python, executable-to-sh line directly below the shebang. Under sh/bash it resolves the interpreter via `command -v python3 || command -v python || command -v py`, captures its path through `$()`, and re-execs under it. Under Python the same line is a no-op string literal:

```python
#!/usr/bin/env python
''''exec "$(command -v python3 || command -v python || command -v py)" "$0" "$@" #'''
"""Real module docstring continues here…"""  # see `from __future__` interaction below before adding one
```

Now `bash <script>`, `python <script>`, and direct shebang invocation all re-exec under whichever Python interpreter the platform actually ships — the `bash` prefix is *forgiven*, not punished. Recovery improves too: `bash <script> --help` prints the argparse help instead of a traceback.

**Why the three-way probe.** macOS 12.3+ removed the `/usr/bin/python` symlink (Apple ships `python3` only); modern Linux distros likewise ship only `python3`; standard Windows python.org installs ship `python` and the `py` launcher but no `python3` symlink. A trampoline that hard-codes any single name exec-127s on the other platforms, and our EMs reach for `bash <script>` from all three. `command -v python3 || command -v python || command -v py` picks whichever exists. Keep all three — single-interpreter forms have regressed before (see `cross-repo-memo` commit history: `6fe5a986` flipped to `python` for Windows and silently broke Mac/Linux EMs until the three-way probe landed).

**Why command-substitution, not `&& exec foo || exec bar`.** A chained `exec X || exec Y` form looks symmetric but isn't: in sh, a failed `exec` is fatal and does NOT fall through to the `||` branch. The `||` only fires if the preceding command (e.g. `command -v X`) returns non-zero before `exec` runs. Command-substitution collapses the probe to one resolved path and a single `exec` — no chained-`exec`-fallback footgun, and it's the form already used by claude-klabauter `coordinator/bin/install-sentinel-write`. Stay aligned with that sibling.

**`from __future__` interaction (gotcha-within-the-gotcha).** A `from __future__ import …` statement must be the file's first statement, and the *only* string literal permitted before it is the module docstring. The trampoline line is a string literal — so it occupies that single slot. A file that has *both* a trampoline **and** a `"""docstring"""` before `from __future__` raises `SyntaxError: from __future__ imports must occur at the beginning of the file`. Resolution: let the trampoline be the sole leading string and demote the human docstring to a `#` comment block (CLIs carry their `--help` text in argparse's `description=`, so nothing reads `__doc__`). See claude-klabauter `coordinator/bin/install-sentinel-write` for the worked example.

### Why this over a separate `.sh` wrapper

A sibling `cross-repo-memo.sh` that execs the python would also make `bash …` work, but it doubles the surface (two files per tool, flag/help drift, two PATH entries) and the operator may still call the bare name. The polyglot keeps it **one file**. (claude-klabauter `coordinator/bin/machine-local` uses the separate-wrapper form for historical reasons and works fine — but new extensionless Python CLIs should prefer the trampoline.)

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

**Source:** example-game-repo-em (cross-repo memo — phantom-dirty-index investigation).

### Symptom

A Python `subprocess.run(["git", "-C", "/x/repo", "status", "--porcelain"])` returns **empty stdout with a non-zero returncode** — which *reads exactly like* "0 modified / clean tree." An enumeration built on that output (e.g. a phantom-dirty file list, a drift check, a "which files changed" sweep) silently produces an **empty set that masks the real state**. The author iterates against a clean-looking nothing while the tree is actually dirty.

### Why

A `/x/...` (or `/c/...`) path is an **MSYS/Git-Bash mount-table POSIX path**, not a real filesystem path. When you run `git` *inside* bash, bash's MSYS layer translates `/x/repo` → `X:\repo` before the `git.exe` exec. A Python `subprocess`, by contrast, invokes **Windows-native `git.exe` directly** with no MSYS translation — so git.exe is handed a literal `/x/repo` it cannot resolve, errors out, and returns empty. The empty stdout is an *error channel*, not an *answer channel* — but a caller that only inspects stdout cannot tell the difference. <!-- foreign-path-ok: illustrates MSYS mount-path translation mechanism, not a checkout location -->

### Fix

- **Enumerate in bash, not Python, for any `git -C /x/...`.** Bash resolves the mount path; the command actually runs. This is the simplest fix and the one the memo validated.
- If Python *must* drive git, pass a **Windows-native path** (`X:/repo` or `X:\\repo`, or translate via `cygpath -w "$p"`), AND **check `returncode` explicitly** — never treat empty stdout as "clean." `result.check_returncode()` or an explicit `if result.returncode != 0: raise` converts the silent mask into a loud failure. <!-- foreign-path-ok: illustrative Windows-native path shape, not a checkout location -->

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

**Source:** example-game-repo-em (same memo).

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

**Source:** project-rag. [universal]

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

## 13. `cc_invoke` passes op params on argv — large round-tripped payloads overflow Windows ARG_MAX

**Source:** self, `state/lessons/`. [universal]

### Symptom

`coordinator/bin/lib/cc_invoke.py`'s `cc_invoke` calls `python3 -m coordinator_core.invoke <op> <params_json> --repo <repo>` with `params_json` as an **argv** argument. Any op whose params round-trip a non-trivial payload — notably `ceremony.wsc_commit`, which must pass back the full resolved_state PipelineContext (~51 KB in a modest single-session close) — overflows Windows/msys `ARG_MAX` (~32 KB) and dies:

```
python3: Argument list too long   # exit 126
```

`cc_invoke` surfaces this as rc 2 with a non-ImportError stderr, so `/workstream-complete`'s three-state contract classifies it as case (b) HALT — and its "re-run" recovery is futile, because the overflow is deterministic. The primary (pipeline-inverted) `/workstream-complete` path therefore **cannot complete on Windows** for any session large enough that resolved_state exceeds ARG_MAX.

### Fix

Pass params via **stdin or a temp file** rather than argv — the invoke already reads stdin in its envelope-parse leg. Alternatively, `wsc_commit` should not require the caller to round-trip the whole resolved_state on argv. This is an engine-tier surface — the real fix lands in claude-klabauter's `coordinator_core`, not a DoE bash patch.

### Greppable signature

```bash
grep -rn 'coordinator_core.invoke' bin/ lib/ | grep -v '<<\|--stdin\|/tmp\|stdin'
```

Any argv-passed `<params_json>` that can carry a resolved_state round-trip is a Windows ARG_MAX overflow waiting to happen.

---

## 14. Emit forward-slash/POSIX paths at any CLI seam a shell will consume — backslash drive-paths brick bash

**Source:** self, `state/lessons/` (F4 headline of the Windows cold install). [universal]

### Symptom

A CLI that prints a filesystem path a shell will later execute must normalize to forward-slash/POSIX **at the emit seam** on Windows. `machine-local get repos.*` printed `str(Path)` → the native backslash-drive form `X:\DoE-claude`. Baked into a bash-executed hook command string, the leading backslash of a segment is an escape: `\D` → `X:DoE-claude` (drive-relative), the path doubles against cwd → `ENOENT` → **every PreToolUse hook fails → all Write/Edit blocked.** A single un-normalized path emit at one `get` seam bricked the entire cold install. <!-- foreign-path-ok: reproduces a real observed backslash-drive bug string, not a location claim -->

### Why

`pathlib.Path.__str__()` emits the OS-native separator (`\` on Windows). Bash treats `\` as an escape inside a double-quoted command string, so `X:\DoE-claude` collapses to `X:DoE-claude`. Every downstream consumer that `eval`s or execs the string sees a broken drive-relative path. <!-- foreign-path-ok: reproduces a real observed backslash-drive bug string, not a location claim -->

### Fix

Normalize at the **single get seam** with `resolved.as_posix()` — bash, `py.exe`, `node`, `claude.exe`, and the Windows path APIs all accept forward slashes, so POSIX-normalized is universally safe. Fix it once at the emitter, not at each of the N consumers (`install-surface-completeness.md § Install-surface bugs must be fixed at the emitter`). This is the mirror image of §10: §10 is a shell POSIX path handed to a Windows-native consumer; this is a Windows-native path handed to a shell consumer — both fail at the shell↔native seam, and the fix is to normalize *at* the seam.

### Greppable signature

```bash
# Path printed straight from str(Path) at a CLI seam a shell will consume.
grep -rn 'print(.*str(.*[Pp]ath\|print(.*resolved\b' --include='*.py' bin/ lib/ \
  | grep -v 'as_posix'
```

---

## 15. Native-Python `git push` reaches the Windows SSH agent with no PowerShell detour — the real dependency is ssh-binary selection

**Source:** claude-klabauter-em spike (`cross-repo/inbox/2026-07-20-claude-klabauter-em-auto-push-naked-python-doe-cutover.md` § "Spike verdict: Windows SSH-agent reachability — VIABLE"; full verdict record `claude-klabauter:state/handoffs/2026-07-20_103000_spike-result-windows-ssh-agent-auto-push.md`).

### Finding

Native Windows Python spawning native `git push` reaches the 1Password SSH agent with **no PowerShell detour**, even with `SSH_AUTH_SOCK` unset. Verified empirically (Win11, Git 2.55, CPython 3.13, 1Password agent live, real SSH remote): `ssh-add -l`, `git ls-remote`, `git push --dry-run`, and `ssh -T git@github.com` all pass from a native-Python parent. Live process-tree sampling of a real post-commit push showed **zero `bash.exe` and zero `powershell.exe`** — the only shell present was the sanctioned POSIX-`sh` hook shim, which `exec`s straight into Python:

```
git commit → sh.exe (hook shim) → python3 auto_push.py        [exec, abspath]
                                   └→ python3 auto_push.py     [detached respawn]
                                       └→ git push origin work/…
                                           └→ C:/Windows/System32/OpenSSH/ssh.exe  <!-- foreign-path-ok: fixed Windows system path, identical on every Windows machine -->
                                              git@github.com "git-receive-pack …"
```

### Why (mechanism)

Win32-OpenSSH falls back to the hardcoded named pipe `\\.\pipe\openssh-ssh-agent` when `SSH_AUTH_SOCK` is unset. MSYS/Cygwin `ssh.exe` emulates AF_UNIX over loopback TCP and structurally **cannot** reach a Win32 named pipe — that, not PowerShell, is what the bash-era PowerShell detour was actually working around. The widely-cited "PowerShell works, Git Bash doesn't" folk report resolves to **which `ssh` binary git executed**, not to the parent shell.

### The load-bearing caveat — do not skip

**The real dependency is ssh-binary selection, not the parent shell.** Any Python/hook that shells out to `git push` inherits whatever `ssh` git resolves. On a box with a bundled MSYS `ssh.exe` on PATH and no `core.sshCommand` pin, git can select that MSYS `ssh.exe` instead of Win32-OpenSSH, and the push fails auth — a PowerShell parent offers no remedy here, because the failure is in binary selection, not shell. The correct fix is 1Password's documented pin, not a shell change:

```
git config --global core.sshCommand "C:/Windows/System32/OpenSSH/ssh.exe"  <!-- foreign-path-ok: fixed Windows system path, identical on every Windows machine -->
```

**The pin is required, not recommended.** This is a demonstrated hazard, not a theoretical one — see the reproduced control below. Any fleet box where git resolves an MSYS `ssh` (a GitHub Desktop user, a VS Team Explorer shell, anyone who installed Git with bundled OpenSSH) will fail auth on `work/*` pushes, and because the post-commit hook exits 0 regardless, `.git/push-failures.log` is the ONLY signal that it happened.

### The negative control — reproduced, and it holds

Two-armed control, same box / same user / same parent process (native Python) / `SSH_AUTH_SOCK` unset in both arms. **Sole variable: which `ssh` binary git executes.** Target: a real `git@github.com:` remote.

| ssh binary | `git ls-remote --heads origin` | result |
|---|---|---|
| `C:/Windows/System32/OpenSSH/ssh.exe` | `rc=0`, refs returned | **PASS** | <!-- foreign-path-ok: fixed Windows system path, identical on every Windows machine -->
| GitHub Desktop MinGit `usr/bin/ssh.exe` | `rc=128`, `git@github.com: Permission denied (publickey)` | **FAIL** |

Corroborating from the MSYS side: `MinGit ssh-add -l` → `rc=2`, *"Could not open a connection to your authentication agent."* The MSYS client cannot see the agent at all — exactly what the pipe-vs-socket mechanism above predicts.

Run independently on two occasions (claude-klabauter; re-run in DoE-claude against a separate SSH remote, same result). The VIABLE verdict therefore rests on a reproduced two-armed control, not on mechanism-plus-positive-legs.

**Why the happy path passes on a dev box at all:** because the box already has the pin set globally. Remove the pin and the same box fails. Do not read a passing push as evidence the pin is unnecessary — it is evidence the pin is working.

### Honest limitations on this verification

This finding is **not** "Windows SSH just works" unqualified. One gap remains:

1. **Single-machine scope.** Both the original verification and the re-run were executed on the same physical machine. Two sessions on one box is not two data points; the control varies the ssh binary rigorously, but not the host. A second-machine confirmation is still outstanding.
2. **Remote-transport scope.** The verifying repo's own `origin` is HTTPS; the SSH leg was verified specifically against a separate SSH remote, not against the verifying repo's own push path.

> **Method lesson: a couple of failed hardcoded-path probes do not prove a binary is absent from a
> machine.** This machine carries five MSYS `ssh.exe` binaries (two GitHub Desktop app-versions,
> two VS Team Explorer installs, one UE cwrsync) — the GitHub Desktop one is not a curiosity, it is
> the bash-less MinGit that CLAUDE.md names as the break-class environment for this exact hook.
> **The rule already exists and applies here too:** a single failed `ls` is not "substrate absent"
> (see `skills/pickup` § premise verification). For the general rule this instantiates, see
> `multi-channel-claim-discipline.md` § Generalization.

### Consequence for coordinator

Claude-klabauter's `coordinator_core/hooks/auto_push.py` keeps `WINDOWS_SSH_POWERSHELL_FALLBACK = False` — the PowerShell branch is permanently-dead documented fallback, not a live code path. PowerShell was never the fix for a binary-selection problem; `core.sshCommand` is.

### Greppable signature

```bash
grep -rn 'SSH_AUTH_SOCK\|ssh-agent\|core.sshCommand' bin/ hooks/ scripts/ --include='*.py' --include='*.sh'
```

A hook/script that shells out to `git push` over SSH on Windows without an explicit `core.sshCommand` pin (or a documented reliance on it being set elsewhere) is exposed to the MSYS-`ssh.exe`-selection failure mode described above.

---

## 16. On a Windows host the Bash tool is not this fleet's shell

Use PowerShell, Python, or a dedicated tool. Fan-out shapes — `find -exec`, `for`/`while` over
paths, `xargs` — are banned outright, not discouraged: one measured `find -exec` ran 293 spawns
and exceeded three minutes where a single `python -c` returned instantly.

Settings-home forwarders (`$COORDINATOR_SETTINGS_HOME/bin/<name>`) are extensionless, and
PowerShell cannot execute them. The failure surfaces as *nothing* — no output, no error — so an
empty registry read is indistinguishable from an absent key. Call the `.cmd` twin.

The harness's bypass-permissions preamble instructs the opposite ("do your work through the Bash
tool wherever it can accomplish the job"). That is generic harness boilerplate injected into every
bypass-mode session, not a PM instruction. Expect the pull and ignore it.

§5 and §7 cover bash *invocation mechanics*; this covers which tool to reach for at all.

---

## 17. The Bash tool pays for a login shell it never uses

The tool invokes `bash -c -l`; `-l` sources Git-for-Windows' stock `/etc/profile` (~450ms
process time, ~800ms wall clock here — quote both with their shapes; under load wall swings
~5.8x stock, ~8.1x block) and the tool's contract discards shell state after every call. Run
`coordinator/templates/bin/install-git-bash-fast-profile.py` (idempotent; `--check`,
`--uninstall`) — it prepends a block reproducing the environment with one retained spawn
(`locale -uU` for `LANG`, which no inherited variable can supply), gated on a non-interactive
shell carrying `CLAUDECODE`, so interactive Git Bash is untouched. Needs an elevated shell,
and a Git-for-Windows update silently reverts it. **Measuring — or guarding — this from
inside a Bash tool call gives a false negative:** the parent is already a login shell, so
`/etc/profile:38` preserves `ORIGINAL_PATH` and the `PATH` recompute looks like a no-op, and
`LANG`/`LC_*` look set when at profile time they are not — a guard keyed on them never fires.
Both traps were hit here, on different variables. Measure from PowerShell.
→ `state/2026-08-23-the-login-shell-tax-on-this-host.md` for measurements and the
verified-equivalence diff.

---

## Detection signatures (greppable)

| Signature | Risk |
|---|---|
| `read -r ... < <(... python ...)` without `\| tr -d '\r'` | Trailing CR silently corrupts captured variable |
| Shell scripts in repo without `.gitattributes` rule for `*.sh` | CRLF breaks shebang resolution |
| `#!/bin/bash` (instead of `#!/usr/bin/env bash`) | Hardcoded path breaks on macOS Homebrew and MSYS2 |
| `flock` invocations in scripts targeting Windows runners | `flock` absent on Git Bash; locking silently skipped |
| `#!/usr/bin/env python3` on a legacy `#!/bin/sh`-polyglot `coordinator/bin` script (still has an operator/shell-invocation surface) | exec-127 on Windows; misdiagnosed as upstream error; change to `python`, or migrate to the pure-Python-with-`.cmd` shape (§3 carve-out) |
| `#!/usr/bin/env python3` on a pure-`.py` bin entrypoint with a co-located `.cmd` launcher, invoked ONLY via the `.cmd` or a resolved-interpreter prefix | Safe and correct — no risk, this is the migration target shape (§3 carve-out); risk returns only if a caller invokes it as a bareword `.py` through git-bash |
| `read -p "..."` in publish/release scripts with no `_CONFIRM` bypass | Hangs in Bash-tool / CI sessions with no `/dev/tty`; use the `_CONFIRM` env-var escape hatch |
| `git commit -m @'…'@` in the Bash tool | PowerShell here-string syntax; subject becomes `@`, body shifts down; use heredoc or `-m "..."` |
| `bash -n` used as syntax gate on installers in Windows working tree | False positives under `core.autocrlf=true` (SC1017 literal CR); use ShellCheck instead |
| Cross-shell line-count comparison (`bash wc -l` vs PowerShell `Measure-Object -Line`) | CRLF/final-newline handling differs; mismatches misread as concurrent-EM edits; use `git status` + `git log -- <file>` as the ONLY drift oracle — never cross-shell counts |
| Extensionless Python CLI in `bin/` (shebang `python`, no `''''exec python "$0"` line) | `bash <script>` feeds Python to bash → traceback; the §9 polyglot trampoline is retired — see §9 notice — demote any module docstring to a `#` comment block and pair with a `.cmd` launcher (DR-076) instead |
| Trampolined file with BOTH a `''''exec…'''` line AND a `"""docstring"""` before `from __future__` | Two leading string literals → `SyntaxError: from __future__ … must occur at the beginning`; retired shape — see §9 notice — demote the docstring to a `#` comment block; do not add a new trampoline to resolve this |
| Python `subprocess` calling `git -C /x/...` (or `/c/...`) without `cygpath -w` / explicit `returncode` check | Windows-native git.exe can't resolve the MSYS path → empty stdout masquerades as a clean tree (§10); enumerate in bash, or pass a Windows path and check returncode |
| Script reads a `git status` count under `GIT_OPTIONAL_LOCKS=0` and acts on it | Refresh computed in memory but never persisted → `--porcelain` and `--short` disagree second-to-second (§11); trust the stable repeated read, persist via a real `git add` |
| `coordinator_core.invoke <op> <params_json>` with a large round-tripped `params_json` on argv | Windows/msys ARG_MAX (~32 KB) overflow → `Argument list too long` exit 126, deterministic (§13); pass params via stdin/temp file |
| CLI prints `str(Path)` at a seam a shell later execs, no `.as_posix()` | Native `X:\...` backslash-drive form → `\D` escape collapses the path → ENOENT bricks every consumer (§14); normalize at the emit seam with `resolved.as_posix()` | <!-- foreign-path-ok: illustrative backslash-drive form, not a location claim -->
| Hook/script shells out to `git push` over SSH on Windows with no `core.sshCommand` pin | Git can select a bundled MSYS `ssh.exe` instead of Win32-OpenSSH → agent unreachable, push fails auth (**reproduced**, not theoretical — §15 control table); PowerShell parent is not the fix — the pin to `C:/Windows/System32/OpenSSH/ssh.exe` is **required, not recommended**, and the hook exits 0 either way so `push-failures.log` is the only signal | <!-- foreign-path-ok: fixed Windows system path, identical on every Windows machine -->

---

## Related

## heredoc + herestring on fd 0 silently discards one stream

In bash, `python - <<HEREDOC ... HEREDOC <<< "$payload"` silently empties stdin — you cannot feed both a heredoc and a herestring to fd 0 in the same command. Only the last redirect wins; the script sees an empty input. Audit rule: grep any script that combines `<<` and `<<<` on the same command for this footgun. Fix: write the payload to a temp file, or pass it via an env var and have the Python script read `os.environ`.

- → `docs/wiki/concurrent-em-hazards.md` § H23 — the EOL phantom-dirty index (stale line-ending blob size flags content-equal files) and the `coordinator-renormalize-index` automatic fix. §10 and §11 here are the two Windows gotchas that ambush an EM *diagnosing* a phantom-dirty tree before they find H23's fix.
- → `docs/wiki/claude-code-platform-gotchas.md` — Windows subprocess pop-ups, MCP CRLF, process-group handling
- → `docs/wiki/python-subprocess-patterns.md` — `CREATE_NO_WINDOW` flag, `pythonw.exe` vs `python.exe`, stdout pipe encoding
- → `docs/wiki/implementation-standards-by-domain.md` § Shell — idempotency, concurrency, resume strategy requirements for load-bearing scripts
