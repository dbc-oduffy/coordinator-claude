# pytest-xdist No-Console Pattern (Windows)

**Purpose.** Canonical recipe for suppressing focus-stealing console windows when running
`pytest -n <N>` (pytest-xdist) on Windows under a headless parent (Git Bash / mintty without
a ConPTY). Documents the working approach and the two dead ends that break worker reaping.

<!-- spec-backlink: archive/specs/2026-05/2026-05-30-windows-console-popup-child-process-audit.md
     That audit hardened CODE-UNDER-TEST spawn sites and explicitly scoped the test-RUNNER
     layer OUT. This doc closes the runner-layer gap for the xdist case. -->

See also: `windows-process-spawn-and-console.md` (production subprocess spawn patterns);
`python-subprocess-patterns.md` (cross-platform creationflags).

## The problem

`python.exe` is a `/SUBSYSTEM:CONSOLE` binary. Under pytest-xdist `-n auto` the xdist
controller spawns N worker processes via execnet. Each worker pops a NEW console window only
when its parent (the controller) is attached to **no console** for it to inherit. Under a
truly console-less parent (Git Bash / mintty **without** a ConPTY) every worker calls
`AllocConsole()` → N focus-stealing windows. Under a ConPTY parent (modern Windows Terminal,
the Claude Code Bash tool) the controller already owns a windowless console, so workers
inherit it — the bug never manifests there.

## Dead ends — DO NOT reach for these

Both were tried empirically and break xdist worker reaping:

1. **`pythonw.exe` controller** — `bin/python-quiet.sh`/`spawn-hidden.sh`'s `/SUBSYSTEM:WINDOWS`
   approach works for standalone scripts but is **incompatible with xdist**. execnet spawns
   workers via `sys.executable` (now `pythonw`); a `pythonw` worker cannot read its
   stdin-pipe bootstrap line → the run **DEADLOCKS**. The controller also hits
   `OSError [WinError 6]` on the inherited (invalid) stderr handle.

2. **`CREATE_NO_WINDOW` flag on the execnet worker `Popen`** — when a worker is spawned
   with `CREATE_NO_WINDOW` it is detached from any console. Its own nested
   `platform.win32_ver()` → `cmd /c ver` call then dies with
   `Windows fatal exception 0x8007000e`, tearing the worker down
   (controller sees `EOFError: expected 1 bytes, got 0`). Even when the execnet patch is
   narrowed to `Popen2IOMaster` only (not the global `subprocess.Popen`), the crash
   persists — the root cause is the worker being console-less, not the scope of the patch.

   The earlier approach of globally subclassing `subprocess.Popen` was separately
   problematic (global replacement; affected all controller subprocesses, not just
   execnet's worker spawn), but the narrower patch fails for the same fundamental reason.

## Working approach — AllocConsole + hide (controller-only, console-less gate)

**In the xdist CONTROLLER, allocate ONE hidden console for a truly-console-less process.
Workers then inherit that hidden console instead of each allocating their own.**

Key properties:
- Workers spawn **exactly as in a known-good run** — no creationflags changes, no pythonw.
  xdist parallelism + stdout/stderr capture are untouched.
- `GetConsoleProcessList` is the non-destructive attachment probe (returns 0 ONLY when
  truly console-less). A ConPTY or real terminal returns >0 → the hook is a strict no-op
  there, so it is safe to leave in always.
- `AllocConsole` rebinds the process std handles to the new console; saved+restored so the
  controller's existing output-pipe to the shell is preserved.
- Fail-safe: any exception in the hook is swallowed — worst case is the pre-fix behaviour
  (per-worker windows), never a broken test run.

### Reference implementation

`project-rag-ue-addon/conftest.py:_install_xdist_worker_no_console_patch` (committed
`24feff18c`, 2026-06-29). Canonical port for any repo:

```python
# conftest.py — root of the pytest project
import sys
import ctypes

_SW_HIDE = 0
_STD_HANDLES = (-10, -11, -12)  # STD_INPUT_HANDLE, STD_OUTPUT_HANDLE, STD_ERROR_HANDLE


def _install_xdist_worker_no_console_patch(config) -> None:
    """In the xdist CONTROLLER, give a truly-console-less process a hidden console.

    Purpose: suppress per-worker AllocConsole() focus-steal on Windows under a
    console-less parent (Git Bash/mintty without ConPTY). Workers inherit the
    hidden console; no CREATE_NO_WINDOW on workers (which breaks xdist).

    Spec-backlink: archive/specs/2026-05/2026-05-30-windows-console-popup-child-process-audit.md
    — that audit scoped the runner layer OUT; this closes the gap.
    Dead ends: pythonw (DEADLOCK) and CREATE_NO_WINDOW on execnet Popen
    (platform.win32_ver cmd /c ver fatal exception 0x8007000e) — do NOT retry.
    """
    if sys.platform != "win32":
        return
    if hasattr(config, "workerinput"):
        return  # this process IS an xdist worker — do not touch.

    try:
        k32 = ctypes.windll.kernel32

        # Non-destructive probe: 0 only when truly console-less.
        # ConPTY / real terminal both return >0 — no-op there.
        _buf = (ctypes.c_uint * 4)()
        if k32.GetConsoleProcessList(_buf, 4) != 0:
            return

        saved = [k32.GetStdHandle(s) for s in _STD_HANDLES]
        if not k32.AllocConsole():
            return  # fall back to pre-fix behaviour
        for std, handle in zip(_STD_HANDLES, saved):
            k32.SetStdHandle(std, handle)
        hwnd = k32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, _SW_HIDE)
    except Exception:  # noqa: BLE001 — console suppression is best-effort, never fatal
        return


def pytest_configure(config):
    _install_xdist_worker_no_console_patch(config)
```

### Verification (mandatory before declaring the fix safe)

Run a bounded worker count on a light test file. Never use `-n auto` for the reaping check:

```bash
# Record before
python_before=$(powershell.exe -NoProfile -Command \
  "(Get-Process python -ErrorAction SilentlyContinue).Count" 2>/dev/null || echo 0)

# Bounded run — must terminate on its own (hang IS the failure mode)
python -m pytest tests/test_schema_compat.py -o addopts="" -n 2 -q \
  # popup-intentional-last-resort

# Record after — must match before (zero orphaned workers)
python_after=$(powershell.exe -NoProfile -Command \
  "(Get-Process python -ErrorAction SilentlyContinue).Count" 2>/dev/null || echo 0)
echo "Before: $python_before  After: $python_after"
```

If any workers orphan (after > before AND the orphans are python.exe processes), the fix is
wrong. `taskkill //F //IM python.exe` to clean up orphans before re-trying.

## Integration with `bin/python-quiet.sh`

`bin/python-quiet.sh` (the `/SUBSYSTEM:WINDOWS` pythonw wrapper for standalone scripts)
and this pattern serve **different contexts**:

| Context | Correct tool |
|---|---|
| Ad-hoc `python -m mymodule`, `python -c '...'` | `bin/python-quiet.sh <interp> [args]` |
| pytest-xdist gate (`-n <N>`) | conftest.py AllocConsole+hide (automatic) |

**Never route `pytest -n <N>` through `python-quiet.sh`.** pythonw breaks xdist (dead end #1 above).
The `bin/run-fast-tests.{sh,ps1}` wrappers call the interpreter directly and rely on conftest
for the popup suppression — that is the correct wiring.
