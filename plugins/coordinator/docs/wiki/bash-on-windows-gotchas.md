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

**Source:** 2026-05-17 self, `tasks/lessons.md` L3.

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

**Source:** 2026-05-06 claude-unreal-holodeck, central queue L207.

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

**Source:** 2026-05-06 claude-unreal-holodeck, central queue L209.

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
| Python 3 | `#!/usr/bin/env python3` |
| Node.js | `#!/usr/bin/env node` |

`/usr/bin/env` is present and stable on Linux, macOS, and Windows Git Bash / MSYS2. It resolves the interpreter through `$PATH`, picking up the environment-local version.

### Exception

Scripts that are deliberately pinned to a specific interpreter version (e.g., a UE build script that requires exactly the Python bundled with UE) should document the explicit path and why portability is intentionally sacrificed — do not silently use a hardcoded path for convenience.

### Greppable signature

```bash
grep -rn '^#!/bin/bash' hooks/ bin/ scripts/
```

Any hit is a portability debt item.

---

## 4. `flock` is not on Git Bash for Windows — use `mkdir` for shell locks

**Source:** 2026-05-08 self, `tasks/lessons.md` ~L37.

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

## Detection signatures (greppable)

| Signature | Risk |
|---|---|
| `read -r ... < <(... python ...)` without `\| tr -d '\r'` | Trailing CR silently corrupts captured variable |
| Shell scripts in repo without `.gitattributes` rule for `*.sh` | CRLF breaks shebang resolution |
| `#!/bin/bash` (instead of `#!/usr/bin/env bash`) | Hardcoded path breaks on macOS Homebrew and MSYS2 |
| `flock` invocations in scripts targeting Windows runners | `flock` absent on Git Bash; locking silently skipped |

---

## Related

- → `docs/wiki/claude-code-platform-gotchas.md` — Windows subprocess pop-ups, MCP CRLF, process-group handling
- → `docs/wiki/python-subprocess-patterns.md` — `CREATE_NO_WINDOW` flag, `pythonw.exe` vs `python.exe`, stdout pipe encoding
- → `docs/wiki/implementation-standards-by-domain.md` § Shell — idempotency, concurrency, resume strategy requirements for load-bearing scripts
