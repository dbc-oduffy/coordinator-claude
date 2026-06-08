---
title: Python subprocess encoding patterns
description: Hardening subprocess.run/Popen calls against Windows locale-inherited UnicodeDecodeError.
---

# Python subprocess encoding patterns

> Source: `hl-031-wiki-only-python-subprocess-locale` — promoted from holodeck project lessons.

## Why it fails: parent locale inheritance

When Python spawns a subprocess, the child process inherits the parent's locale and therefore
its default text encoding. On Windows, the system locale defaults to a codepage such as
**cp1252** (Western Europe) or **cp932** (Japanese). Python's `subprocess.run()` uses
`locale.getpreferredencoding(False)` to determine the default text encoding when `encoding=`
is not explicitly passed.

If the child process emits any byte outside the active codepage — common with Unicode output
from tools like `npm`, `git`, compilers, or anything locale-aware — Python raises
`UnicodeDecodeError` while reading stdout/stderr.

POSIX systems (macOS, Linux) default the locale to UTF-8 in virtually all modern
distributions, so this failure mode is rare there. It is a **Windows-specific hazard**,
but the fix is portable and costs nothing to apply universally.

## Symptom signature

```
UnicodeDecodeError: 'charmap' codec can't decode byte 0xXX in position N: character maps to <undefined>
```

This surfaces mid-stream during subprocess output capture — either immediately or only when
the output happens to contain a Unicode character. It may appear only on certain developer
machines and not in CI (or vice versa, depending on system locale).

To diagnose the active encoding at runtime:

```python
import locale
print(locale.getpreferredencoding(False))  # e.g. "cp1252" on Windows without UTF-8 mode
```

## Fix pattern

Always pass `encoding='utf-8'` explicitly on subprocess calls that capture output:

```python
import subprocess

result = subprocess.run(
    ["tool", "--arg"],
    capture_output=True,
    encoding='utf-8',
    errors='replace',   # see below
)
print(result.stdout)
```

This overrides locale inheritance and guarantees consistent behavior across all platforms.

### `errors='replace'` vs `errors='strict'`

| Value | Behaviour | When to use |
|-------|-----------|-------------|
| `'strict'` | Raises `UnicodeDecodeError` on any undecodable byte | When garbled output is worse than a crash — e.g., security-sensitive parsing, structured data that must be correct |
| `'replace'` | Substitutes `U+FFFD` (replacement character) for undecodable bytes | When you need the command to succeed even if some diagnostic output is garbled — log scraping, build output display, progress messages |
| `'ignore'` | Silently drops undecodable bytes | Avoid unless you have a specific reason; data loss is silent |

**Default recommendation:** use `errors='replace'` in tooling / automation contexts. Use
`errors='strict'` when the output is machine-parsed and a mojibake result would propagate
silently into downstream data.

## Cross-platform note

On POSIX systems, `locale.getpreferredencoding(False)` returns `'UTF-8'` in most modern
environments, so `encoding='utf-8'` is effectively a no-op. The explicit argument is a
**Windows hardening pattern** that also serves as documentation of intent. Apply it
universally rather than guarding with `sys.platform` — the overhead is zero.

## Related: `PYTHONIOENCODING`

Setting the environment variable `PYTHONIOENCODING=utf-8` before launching Python affects
stdin/stdout/stderr for the Python process itself, but does **not** change the default
encoding used by `subprocess.run()` for child output capture. The subprocess encoding must
be set via the `encoding=` argument.

If you control the child process and it is also Python, passing `PYTHONIOENCODING=utf-8` in
the subprocess environment can help:

```python
import os
import subprocess

env = os.environ.copy()
env['PYTHONIOENCODING'] = 'utf-8'

result = subprocess.run(
    ["python", "child_script.py"],
    capture_output=True,
    encoding='utf-8',
    errors='replace',
    env=env,
)
```

## Windows headless spawn: CREATE_NO_WINDOW vs pythonw.exe

**CREATE_NO_WINDOW alone is unreliable for python.exe spawns on uv-managed venvs** (2026-05-17 project-rag). On uv-managed virtual environments, `python.exe` is a stub launcher compiled with the CONSOLE subsystem. Passing `creationflags=subprocess.CREATE_NO_WINDOW` to `subprocess.Popen` suppresses the console window for the parent-spawned process, but the stub launcher itself may briefly flash a console window before handing off to the real interpreter — because the stub's PE header declares CONSOLE subsystem, the OS creates a console for it regardless of the flag.

Two reliable alternatives:

1. **Use `pythonw.exe` directly.** The sibling `pythonw.exe` is compiled with the GUI subsystem; the OS never creates a console for it. Resolve it from the venv's `Scripts/` directory alongside `python.exe`. This is the simplest fix when you control the interpreter path.

2. **Resolve via a `pythonw_executable()` helper.** Rather than hardcoding the filename, inspect the PE optional header's `Subsystem` field (value `2` = GUI, `3` = CONSOLE). Build a helper that locates the sibling with `Subsystem == 2` and falls back to `pythonw.exe` by name if the sibling check is unavailable. This is more robust across edge cases (conda envs, embedded distributions) where the sibling may be named differently.

```python
import os, struct

def pythonw_executable(python_exe: str) -> str:
    """Return a GUI-subsystem sibling of python_exe for windowless spawning."""
    candidate = os.path.join(os.path.dirname(python_exe), "pythonw.exe")
    return candidate if os.path.isfile(candidate) else python_exe

# Usage:
import sys
exe = pythonw_executable(sys.executable)
proc = subprocess.Popen([exe, "script.py"], ...)
```

On non-Windows platforms `pythonw.exe` does not exist; `pythonw_executable()` falls back to the original path transparently.

### uv-managed venvs and the stub-launcher flash (2026-05-16)

On **uv-managed virtual environments**, `python.exe` is not the real CPython binary — it is a stub launcher compiled with the **CONSOLE subsystem**. When a windowless parent spawns it, the OS sees the CONSOLE subsystem PE header and creates a console before the stub hands off to the real interpreter. `CREATE_NO_WINDOW` does not suppress this flash because the flag only affects the spawned process's console-creation step, not the OS's initial subsystem-driven allocation.

**Diagnosis heuristic:** any periodic console flash occurring on a predictable cadence while the parent is running windowlessly is a candidate for this root cause. The flash will be brief (stub hand-off latency) and repeat at the spawn interval (e.g. scheduler tick).

**Fix — centralise interpreter resolution:**

- Put a `pythonw_executable()`-style helper in a shared lib.
- The helper should: (a) detect uv-managed venv layout (`pyvenv.cfg` with `uv` provenance or the presence of a uv-specific stub), (b) prefer `pythonw.exe` from the same venv's `Scripts/` directory when present, (c) fall back to `python.exe + CREATE_NO_WINDOW` if `pythonw.exe` is absent.
- **Call-sites must never reach for `sys.executable` directly** for spawn decisions — route through the helper so the resolution logic lives in one place.

```python
import os, sys

# Python 3.10+; on 3.9 add `from __future__ import annotations` or use Optional[str]
def pythonw_executable(python_exe: str | None = None) -> str:
    """Return a GUI-subsystem sibling of python_exe for windowless spawning.

    Prefers pythonw.exe from the same venv Scripts/ directory.
    Falls back to the original path (caller should add CREATE_NO_WINDOW).
    """
    base = python_exe or sys.executable
    candidate = os.path.join(os.path.dirname(base), "pythonw.exe")
    return candidate if os.path.isfile(candidate) else base
```

If `pythonw_executable()` returns the original path (no sibling found), pass `creationflags=subprocess.CREATE_NO_WINDOW` as a belt-and-suspenders fallback — it will not eliminate the stub flash on uv venvs but is still the right default for non-uv paths.

## Shell-out callers must converge on the impl's exit-code contract

*2026-05-20, project-rag.* When several callers shell out to the same underlying tool, they must agree on what its exit codes *mean* — specifically, "key absent" (a legitimate empty result) versus "impl broke" (a real error) are different conditions that callers often conflate. If one caller treats non-zero-or-empty as an error and another treats it as absence, querying a genuinely-absent key produces false-positive WARNs in one path and silence in the other.

Defense: give the impl an explicit absence signal that is distinct from its error signal, and have every caller use it. The `--default ''` pattern is the canonical shape — the tool returns the supplied default (empty string) on key-absent with exit 0, and reserves non-zero exit for actual failure:

```bash
# absence → empty string, exit 0;  impl-broken → non-zero exit
value=$(mytool get "$key" --default '') || { echo "WARN: mytool failed" >&2; }
[ -n "$value" ] || : # key legitimately absent — not an error
```

Audit cross-caller exit-code handling whenever a second consumer of the same impl appears; divergence is the recurring smell.

## Related: bare-namespace package collisions across sibling repos

When subprocesses or in-process imports pull two sibling repos into one interpreter, bare-namespace top-level packages (`scripts/`, `utils/`, `lib/`) collide in `sys.modules` because Python keys on import name, not path — an order-dependent, non-deterministic failure. Bilateral rename is the fix; defensive eviction is a workaround. → [`dual-identity-module-hazard.md`](./dual-identity-module-hazard.md) § Bare-namespace top-level packages collide across sibling repos.

## `communicate(timeout=)` does NOT bound the reader-thread join — grandchildren wedge it forever

`subprocess.communicate(timeout=N)` sends SIGTERM/TerminateProcess to the **child** and starts a join on the internal reader threads when the timeout expires. However, the join itself has **no deadline** — if the child's stdout/stderr pipes are still open (because a grandchild process inherited and is still holding them), the reader threads block forever. On Windows, `taskkill /F /IM child.exe` closes the child's handle but grandchildren that inherited the pipe descriptors keep the pipes open; the `communicate()` call then hangs after timeout.

**When the subprocess may spawn grandchildren that outlive it, do not use `communicate()` with captured PIPEs.** Use file-based redirection instead:

```python
import subprocess, tempfile, os

with tempfile.TemporaryFile() as out_f, tempfile.TemporaryFile() as err_f:
    proc = subprocess.Popen(
        cmd,
        stdout=out_f,
        stderr=err_f,
    )
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        # Windows: kill entire process tree, not just the child
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                       capture_output=True)
        proc.wait()
    out_f.seek(0); err_f.seek(0)
    stdout = out_f.read().decode("utf-8", errors="replace")
    stderr = err_f.read().decode("utf-8", errors="replace")
```

The `/T` flag to `taskkill` terminates the entire child process tree, closing all inherited pipe handles and unblocking any pending reads. On POSIX, `os.killpg(os.getpgid(proc.pid), signal.SIGKILL)` is the equivalent.

Add this to the Summary checklist: when grandchildren may outlive the child, redirect stdout/stderr to temp files + `proc.wait(timeout)` + `/T` tree-kill, instead of `communicate(timeout=)`.

## Windows pytest Runner — pythonw Breaks stdin-Inheriting Subprocesses

**Never run `pytest` through `pythonw` (python-quiet) — `pythonw` has no stdin HANDLE, so stdin-inheriting subprocess tests fail with WinError 6/50; popup suppression belongs in `conftest.py`, not the runner.**

`pythonw` is safe for one-shot `python -c` diagnostics (no child spawns), but pytest orchestrates subprocesses that need a real stdin. When spawning headless, the two popup paths are different: `python -c` has no child spawns so `pythonw` is safe; pytest's children need a valid `DuplicateHandle`-able stdin.

**How to apply:** route popup suppression through `tests/conftest.py` (Fortran env vars + `CREATE_NO_WINDOW` monkeypatch) and run pytest under a normal console python. `python-quiet` / `pythonw` is for `-c`/scratch-script diagnostics ONLY. Corollary: when a "test-ordering" failure reproduces only under one runner, suspect the runner before bisecting tests. Source: 2026-05-27 project-rag.

## Windows Console Popup Suppression — CREATE_NO_WINDOW + DEVNULL Reconciles Popup and stdin

**Windows console popup: console-python + `CREATE_NO_WINDOW` + `DEVNULL` stdin reconciles "no popup" with "valid stdin" for pytest runs.**

`pythonw` fixes the popup but has no stdin handle (stdin-inheriting children die `WinError 6/50`). Console python avoids the broken-stdin issue but creates a window under headless execution. The two constraints look mutually exclusive but aren't:

- Keep the process on `python.exe` (console subsystem).
- Add `creationflags=CREATE_NO_WINDOW` — suppresses the window.
- Add `stdin=subprocess.DEVNULL` — a valid NUL handle that children can `DuplicateHandle`.
- Launch the outer runner itself under GUI `pythonw` so the runner process has no window of its own.

Also: a doctrine bullet stating an unverified *conclusion* can mislead for weeks — verify pytest runner behavior against live process state, not the bullet. Source: 2026-05-28 project-rag.

## `Path.write_text` on Windows Emits CRLF — Pass `newline='\n'` for Unix Consumers

*Source: project-rag state/lessons.md:35, 2026-05-29. [universal]*

`pathlib.Path.write_text()` (and `open(..., 'w')` without `newline=`) uses the platform's native line ending. On Windows that is `\r\n` (CRLF). Files consumed by bash scripts (`[ -f ]` path lists, `git rm --pathspec-from-file`, `xargs`), by `git`, or by any POSIX tool will mis-parse CRLF-terminated lines: the carriage return appears as part of the last token on the line, turning `path/to/file` into `path/to/file\r` and silently failing every downstream match.

**Fix:** always pass `newline='\n'` when writing files intended for bash/git/POSIX consumption:

```python
path.write_text(content, encoding='utf-8', newline='\n')
# or
with open(path, 'w', encoding='utf-8', newline='\n') as f:
    f.write(content)
```

Alternatively, strip carriage returns at the reader side before passing lines to `git rm`/`xargs`:

```bash
git rm --pathspec-from-file=<(tr -d '\r' < file_list.txt)
```

The `newline='\n'` approach is preferable — it is unambiguous and locates the fix at the producer, not scattered across every consumer.

## Conftest Spawn-Flag Monkeypatch Does Not Reach Production Child-Spawn Sites

*Source: project-rag L5 + claude-unreal-holodeck L13, 2026-05-30.*

**A `CREATE_NO_WINDOW` (or any spawn-flag) monkeypatch installed in `conftest.py` suppresses popups only for processes the *test process itself* spawns — it does NOT propagate into production child-spawn sites, nor into grandchildren the tests spawn.** A conftest fixture monkeypatches `subprocess.Popen`/`subprocess.run` in the test interpreter's address space; a production code path that spawns a child carries whatever flags *its own* call site passes. Auditing only `tests/` for popup-safety therefore misses every production spawn site — the flag belongs **at the production spawn site**, not bolted on in test infra.

This is the spawn-flag analog of the network-mock leak (`test-design-discipline.md` §10, "network-layer mocks leak through real subprocess spawns"): the patch applies to the parent's address space only; the child reads its own creation flags.

**Console-popup suppression is orthogonal to the bounded-Popen lifecycle gate.** Two distinct invariants ride the same `Popen` call and must be audited separately: (1) *popup suppression* (`CREATE_NO_WINDOW` / `pythonw.exe` / `stdin=DEVNULL`) governs whether a window flashes; (2) *bounded lifecycle* (timeout + tree-kill, see `communicate(timeout=)` section above) governs whether the child can wedge or leak. A spawn site can satisfy one and violate the other. When auditing spawn paths, enumerate **every** production spawn site (grep `Popen` / `subprocess.run` / `os.spawn*` across the source tree, not just the headless-runner entry point) and check both invariants at each — a single bypass spawn path re-introduces the popup or the wedge.

## Summary checklist

- Always pass `encoding='utf-8'` on any `subprocess.run()` or `Popen()` call that captures output.
- Default to `errors='replace'` for tooling; use `errors='strict'` for machine-parsed output.
- Use `locale.getpreferredencoding(False)` to diagnose the active encoding on a suspect machine.
- Do not rely on `PYTHONIOENCODING` alone — it does not cover subprocess capture.
- On Windows, prefer `pythonw.exe` (GUI subsystem) over `python.exe` + `CREATE_NO_WINDOW` for truly headless spawns from uv-managed venvs — use a `pythonw_executable()` helper to locate it.
- When grandchildren may outlive the child: redirect to temp files + `proc.wait(timeout)` + tree-kill (`taskkill /T /F` on Windows, `killpg` on POSIX) — do NOT use `communicate(timeout=)` with captured PIPEs.
- Never run `pytest` through `pythonw` — use console python + `CREATE_NO_WINDOW` + `stdin=DEVNULL` instead; put popup suppression in `conftest.py`.
- For headless pytest: `creationflags=CREATE_NO_WINDOW` + `stdin=DEVNULL` on console python reconciles "no window" with "valid stdin for child processes."
- A conftest spawn-flag monkeypatch reaches only the test process's own spawns — put popup suppression at every **production** child-spawn site; auditing only `tests/` misses the leak.
- Audit popup-suppression and bounded-Popen lifecycle as **separate** invariants at every spawn site (grep all `Popen`/`subprocess.run`, not just the runner entry point) — one bypass spawn path re-introduces the popup or the wedge.
