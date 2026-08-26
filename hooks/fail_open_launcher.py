"""Fail-open launcher for hook registrations — keeps a missing hook script from bricking
every tool call in every running session.

THE PROBLEM THIS SOLVES. A hook registration names a file. The harness must find that file
before any coordinator code runs, so if the path does not resolve the tool call itself
errors — and because `PreToolUse` covers `Write`, `Edit` and `Bash`, an unresolvable hook
path takes away the tools needed to repair it. Sessions snapshot their registrations at
startup, so a script removed mid-session keeps being invoked by every process that booted
earlier, while every on-disk check reports the tree as perfectly consistent.

Two distinct triggers have produced exactly this outcome: a path that does not exist on the
host (a sync race writing another machine's paths into shared config), and a script deleted
from the working tree while the registration still pointed at it. Fixing either trigger
individually leaves the other live, because the fragility is not in the triggers — it is in
requiring a file to resolve before anything of ours can run.

THE MECHANISM. Register an inline loader instead of a bare path: the command becomes
``python3 -c <LOADER> <script> [args...] <injector> <bootstrap>``. ``LOADER`` is inside the
command string, so there is no file the harness itself must resolve before any of our code
runs — that is the property this whole module exists to hold, and it is unchanged by the
trampoline body living in ``_hook_boot.py``: a missing bootstrap file is OUR failure to
handle, on a soft-fail path we control, never the harness's failure to launch. The loaded
bootstrap then decides what to do about the target, in our code rather than the harness's:

- target present  -> run it, unchanged: same ``__main__`` semantics, same ``sys.argv``, same
  stdin, same exit code (so a guard's ``exit 2`` deny still denies).
- target absent or unresolvable -> write a loud banner to stderr and exit 0, letting the tool
  call proceed. A guard that cannot run must not be indistinguishable from a guard that
  passed, so the banner says plainly that this is a defect and names the path.
- target present but broken -> the error propagates untouched. Failing open is for a script
  that is *not there*, never for one that is there and raising.

SINGLE LINE, DELIBERATELY. ``LOADER`` must contain no raw newline. A newline inside the
payload's string literal is a syntax error under ``python -c``, and a multi-line payload does
not survive being stored as a JSON string and handed to a shell. Both failure modes are real
and both are covered by the tests; keep the payload single-line and keep the escape hatch of
``chr(10)`` if a newline is ever genuinely needed inside it. The trampoline logic this used to
bind no longer lives here at all — it moved verbatim to ``coordinator/hooks/scripts/
_hook_boot.py`` as ordinary multi-line Python, which is exactly what retires this constraint
for that body; ``LOADER`` itself is the only payload left that still has to survive ``python
-c`` and a JSON round-trip.

THE PAYLOAD IS TWO PIECES NOW, ONE INLINE AND ONE ON DISK. ``LOADER`` (~159 bytes) is the
only text that still travels inside the ``-c`` argument, and by construction is also the only
text the harness ever echoes ahead of a guard's own message on a hook error — the eight
display lines of trampoline source a hook error used to carry ahead of every guard message are
gone because that source is no longer part of the argv at all. The trampoline logic itself
(the venv-injector shim call and the ``runpy`` hand-off to the target script) lives in
``_hook_boot.py``, named as the last element of ``args`` and loaded by ``LOADER`` at runtime
via ``exec(open(b).read())`` — never re-embedded inline. ACCEPTED REGRESSION, NAMED NOT
BURIED: because the trampoline is now one shared file rather than one inline payload per
registration, a missing ``_hook_boot.py`` fails EVERY hook open at once, where before only the
individually-missing target script did. Taken deliberately — ``LOADER``'s own
``os.path.isfile`` guard still banners loudly (``"bootstrap missing, hooks fail OPEN: "+b``)
rather than degrading silently, ``_hook_boot.py`` is regenerated alongside every registration
rather than being a per-guard edit surface, and the trade buys back roughly eight display
lines on every guard fire in every session. See ``_hook_boot.py``'s own module docstring for
the same trade recorded on the file it names.

WHAT THIS DOES NOT DO. It does not make a missing guard safe — it makes a missing guard
*visible and survivable* instead of fatal. Restoring the guard is still the fix.
"""
from __future__ import annotations

# EXEC FORM RETIRES THE SHELL-QUOTING HAZARD (C1/A1/A4). Registrations built via
# `wrap_command_exec()` hand the harness a `{command, args}` mapping -- BOOTSTRAP travels as
# one `args` element, passed to the child process verbatim with no shell in the path. The
# no-double-quote / no-`$` / no-backtick / no-backslash invariants this module used to enforce
# (`_dq`, now deleted) existed ONLY because the string form transited a shell; exec form
# retires the whole hazard class by construction, not by continuing to police it. Double
# quotes and backslashes are legal in BOOTSTRAP now -- see the payload below, which uses a
# double-quoted `exec("...")` string with `\n` escapes instead of the old `chr(39)`-soup single-
# quote assembly. The single-line constraint on BOOTSTRAP is NOT retired by this: it comes from
# `python -c` and JSON (see SINGLE LINE, DELIBERATELY above), not from the shell. The legacy
# string emitter `wrap_command()` (and its `_shell_quote` helper) is deleted (C2): all 43
# `hooks.json` registrations moved to exec form, leaving it with no remaining caller.
# NO SITE-PACKAGES INJECTION, BY CONSTRUCTION. Registrations carry one trailing token
# (BOOTSTRAP_PATH), not two. The three-rung site-packages ladder, its pyvenv.cfg ABI gate and its
# sys.path promotion step are retired along with the coordinator venv they resolved; hook-path
# third-party imports resolve from whichever interpreter bare `python3` lands on. Re-adding a
# path-mutating token here would reintroduce a seam whose only supported target is a venv --
# `_find_venv_root` gated every rung on a `pyvenv.cfg`, which a machine interpreter does not have.
LOADER = (
    "import os,sys;b=sys.argv.pop();exec(open(b,encoding='utf-8').read()) if os.path.isfile(b) "
    "else sys.stderr.write(\"COORDINATOR HOOK SEAM: bootstrap missing, hooks fail OPEN: \"+b)"
)

_MARKER = "COORDINATOR HOOK SEAM"


def is_wrapped(command) -> bool:
    """True when ``command`` already routes through the fail-open bootstrap.

    Accepts both shapes this module emits: the legacy string form (``wrap_command``), where
    the marker is a substring of the whole command, and the exec form
    (``wrap_command_exec``), a ``{"command": ..., "args": [...]}`` mapping where the marker
    lives inside ``args[1]`` (the ``-c`` payload, i.e. ``LOADER`` itself -- its own inline
    fallback banner carries the marker text even though the trampoline body it may go on to
    ``exec()`` no longer lives inline).
    """
    if isinstance(command, dict):
        args = command.get("args") or []
        return len(args) > 1 and _MARKER in args[1]
    return _MARKER in command


def _split_python3_command(command: str):
    """Shared parse for both emitters: ``python3 <script> [args...]`` -> ``(script, args)``.
    Raises ``ValueError`` on any other shape."""
    parts = command.split()
    if len(parts) < 2 or parts[0] != "python3":
        raise ValueError(
            "unsupported hook command shape; expected 'python3 <script> [args...]', got: "
            + command
        )
    return parts[1], parts[2:]


BOOTSTRAP_PATH = "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/_hook_boot.py"


def wrap_command_exec(command: str) -> dict:
    """Rewrite ``python3 <script> [args]`` into its fail-open exec-form registration.

    Returns ``{"command": "python3", "args": ["-c", LOADER, script, *args, BOOTSTRAP_PATH]}``
    -- the shape `hooks.json` exec-form registrations consume. The target script stays at
    `args` index 2, the only index with production evidence of `${CLAUDE_PLUGIN_ROOT}`
    expansion (AC3); the trampoline's own path is appended as the last element, where `LOADER`
    pops it and `exec()`s it before the remaining `sys.argv` reaches the target. No shell is
    ever in the path: each element is passed to the child process verbatim, which is what
    retires the `_dq` quoting-invariant hazard class this module used to police.

    One trailing token, not two: the site-packages injector that used to occupy the
    second-to-last slot is retired, and hook-path third-party imports now resolve from the
    interpreter `python3` lands on. `_hook_boot.py` drains a stale injector element off the
    tail so a registration snapshotted by a still-running pre-retirement session does not hand
    the target script a spurious argument.
    """
    script, args = _split_python3_command(command)
    return {
        "command": "python3",
        "args": ["-c", LOADER, script, *args, BOOTSTRAP_PATH],
    }


