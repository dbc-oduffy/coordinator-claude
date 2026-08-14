"""raw_cmdline_recovery — shared Windows raw-cmdline argv recovery.

Consumers: `coordinator/bin/coordinator-write-review-trail.py` and
`coordinator/bin/scoped-git-commit` — the two entrypoints named in
`gen-launcher-shim.py`'s `_RAW_CMDLINE_ENTRYPOINTS` (mirrored, not imported,
against `coordinator_core/install/substrate.py`'s `_RAW_CMDLINE_TARGETS`).
Both already insert `coordinator/bin/lib` onto `sys.path` before importing
their own siblings, so no new bootstrap step is needed at either call site.

Why this exists as a standalone module rather than being copied a second
time: the recovery logic (read the `%CMDCMDLINE%` capture file, locate this
invocation's own launcher name inside it, tokenize the tail with
Windows-flavoured `shlex`, and fall back to the untouched, possibly
caret-mangled `argv` on ANY mismatch) is identical between the two call
sites — the only thing that differs is which launcher basename to search
for, so that is the one parameter this module takes.

cmd.exe silently strips any literal ``^`` from an argument while populating
a .cmd launcher's ``%1..%9``/``%*`` batch parameters — this happens during
cmd.exe's OWN command-line parse, before the launcher body (or the Python
entrypoint) ever runs, and is lost regardless of caller (PowerShell, a
Python ``subprocess.run`` list-form call, or cmd.exe itself — measured, not
a caller-side quoting bug). ``%CMDCMDLINE%``, captured verbatim by the
launcher into a temp file named by ``_LAUNCHER_RAW_CMDLINE_FILE`` before
invoking Python, still carries the original, unmangled text (measured) —
this recovers argv from THAT text instead of trusting the already-mangled
``sys.argv`` the interpreter received.

Best-effort and fail-safe: any parse mismatch (missing env var, non-Windows,
the recovered token count disagreeing with the mangled ``argv``) falls back
to ``argv`` unchanged — recovery must never crash, nor silently drop or
reorder an argument the caller actually passed.

2026-08-14: the capture file now lives inside a per-invocation `mkdir`-ed
directory, not directly under `%TEMP%` (see `gen-launcher-shim.py::
_cmd_raw_cmdline_block`'s docstring for the collision this fixes — a bare
`%RANDOM%%RANDOM%.tmp` name was NOT collision-safe across concurrent
sessions started in the same second). Cleanup here best-effort-removes that
directory too, alongside the file, so this fix does not just relocate the
leak this module's callers exist to close.

Spec backlink: state/bug-backlog/2026-08-08-cmd-exe-shim-eats-the-caret-in-
a-git-rev-6679bf76eb8a.yaml
"""
from __future__ import annotations

import os
from pathlib import Path

#: Env var the .cmd launcher exports (gen-launcher-shim.py's
#: `_RAW_CMDLINE_ENTRYPOINTS`, opt-in per state/bug-backlog/2026-08-08-cmd-
#: exe-shim-eats-the-caret-in-a-git-rev-6679bf76eb8a.yaml) — names a temp
#: FILE holding the raw, un-mangled `%CMDCMDLINE%` text captured BEFORE
#: cmd.exe's own %* population strips any literal `^` from this process's
#: actual `sys.argv`. A file, not the text directly in an env var: measured,
#: `set "_X=%CMDCMDLINE%"` ALSO strips the caret (a second, independent
#: instance of the same cmd.exe defect) — only `echo %CMDCMDLINE%>file`
#: preserves it, so the launcher redirects to a file and hands us the path
#: (itself caret-free, safe for an ordinary `set`) instead.
RAW_CMDLINE_FILE_ENV = "_LAUNCHER_RAW_CMDLINE_FILE"


def recover_windows_argv(argv: list[str], launcher_cmd_name: str) -> list[str]:
    """Recover un-mangled argv from the raw invoking cmdline on Windows.

    ``launcher_cmd_name`` is the invoking .cmd launcher's own basename (e.g.
    ``"scoped-git-commit.cmd"`` or ``"coordinator-write-review-trail.cmd"``)
    — used to locate where this invocation's own arguments begin within the
    raw cmdline text, since ``%CMDCMDLINE%`` carries the whole invoking
    command line, launcher name included.

    See this module's docstring for the full recovery contract and its
    fail-safe guarantees.
    """
    if os.name != "nt":
        return argv
    raw_file = os.environ.get(RAW_CMDLINE_FILE_ENV)
    if not raw_file:
        return argv
    try:
        raw = Path(raw_file).read_text(encoding="utf-8", errors="replace").rstrip("\r\n")
    except OSError:
        return argv
    finally:
        try:
            os.remove(raw_file)
        except OSError:
            pass  # best-effort cleanup — a leaked temp file is not fatal
        # Review: staff-eng (Finding 3) — only rmdir a directory THIS
        # mechanism created (named "_coordinator_launcher_<...>" by
        # gen-launcher-shim.py::_cmd_raw_cmdline_block /
        # substrate.py::_agent_cmd_raw_cmdline_block). An unguarded rmdir of
        # os.path.dirname(raw_file) blind-trusts an environment variable —
        # a malformed/adversarial RAW_CMDLINE_FILE_ENV value naming, say, a
        # test's own tmp_path (measured: this module's own caret-recovery
        # test constructs raw_file directly under tmp_path) would silently
        # delete a directory this mechanism never made.
        parent = os.path.dirname(raw_file)
        if os.path.basename(parent).startswith("_coordinator_launcher_"):
            try:
                os.rmdir(parent)
            except OSError:
                pass  # best-effort — non-empty (a peer's dir, unlikely) or gone
    if not raw:
        return argv
    idx = raw.lower().find(launcher_cmd_name.lower())
    if idx == -1:
        return argv
    tail = raw[idx + len(launcher_cmd_name):]
    if tail.startswith('"'):
        tail = tail[1:]
    tail = tail.strip()
    # The whole %CMDCMDLINE% text is itself one outer-quoted `cmd /c "..."`
    # blob (Windows' own .cmd CreateProcess convention) — strip the single
    # trailing quote that closes it, if present and unbalanced within tail.
    if tail.endswith('"') and tail.count('"') % 2 == 1:
        tail = tail[:-1].strip()
    try:
        import shlex

        recovered = shlex.split(tail, posix=False)
    except ValueError:
        return argv
    cleaned = [
        tok[1:-1] if len(tok) >= 2 and tok[0] == tok[-1] == '"' else tok
        for tok in recovered
    ]
    if len(cleaned) != len(argv):
        # Token-count disagreement means our text-slicing assumption about
        # where the launcher name ends and args begin didn't hold for this
        # invocation — bail to the safe, known (if caret-mangled) argv
        # rather than risk silently misaligning arguments.
        return argv
    return cleaned
