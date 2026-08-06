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

THE MECHANISM. Register an inline bootstrap instead of a bare path: the command becomes
``python3 -c <BOOTSTRAP> <script> [args...]``. The payload is inside the command string, so
there is no file for the harness to fail to find. The bootstrap then decides what to do
about the target itself, in our code rather than the harness's:

- target present  -> run it, unchanged: same ``__main__`` semantics, same ``sys.argv``, same
  stdin, same exit code (so a guard's ``exit 2`` deny still denies).
- target absent or unresolvable -> write a loud banner to stderr and exit 0, letting the tool
  call proceed. A guard that cannot run must not be indistinguishable from a guard that
  passed, so the banner says plainly that this is a defect and names the path.
- target present but broken -> the error propagates untouched. Failing open is for a script
  that is *not there*, never for one that is there and raising.

SINGLE LINE, DELIBERATELY. ``BOOTSTRAP`` must contain no raw newline. A newline inside the
payload's string literal is a syntax error under ``python -c``, and a multi-line payload does
not survive being stored as a JSON string and handed to a shell. Both failure modes are real
and both are covered by the tests; keep the payload single-line and keep the escape hatch of
``chr(10)`` if a newline is ever genuinely needed inside it.

WHAT THIS DOES NOT DO. It does not make a missing guard safe — it makes a missing guard
*visible and survivable* instead of fatal. Restoring the guard is still the fix.
"""
from __future__ import annotations

# Double-quoted string literals throughout, never single: the whole payload is wrapped in
# single quotes for the shell, so a single quote inside it would terminate the argument
# early. `_sq` enforces this rather than trusting it.
BOOTSTRAP = (
    "import os,runpy,sys;"
    "p=sys.argv[1];"
    "sys.argv=sys.argv[1:];"
    'runpy.run_path(p,run_name="__main__") if os.path.isfile(p) else '
    'sys.stderr.write("COORDINATOR HOOK SEAM: registered hook script unreachable -- "'
    '"failing OPEN so tool calls keep working. missing: "+p+" | This is a defect, not a "'
    '"normal state: the registration and the script have drifted apart (deleted script, "'
    '"or a path that does not resolve on this host).")'
)

_MARKER = "COORDINATOR HOOK SEAM"


def is_wrapped(command: str) -> bool:
    """True when ``command`` already routes through the fail-open bootstrap."""
    return _MARKER in command


def wrap_command(command: str) -> str:
    """Rewrite ``python3 <script> [args]`` into its fail-open equivalent.

    Idempotent: an already-wrapped command is returned unchanged, so the rewriter can be
    re-run over a partially-converted file without double-wrapping.
    """
    if is_wrapped(command):
        return command

    parts = command.split()
    if len(parts) < 2 or parts[0] != "python3":
        raise ValueError(
            "unsupported hook command shape; expected 'python3 <script> [args...]', got: "
            + command
        )

    script, args = parts[1], parts[2:]
    # shlex.quote is deliberately not used on the payload here: it targets POSIX sh, and the
    # payload is quoted once at write time by the rewriter that owns the file format.
    return " ".join(["python3", "-c", _sq(BOOTSTRAP), script, *args])


def _sq(text: str) -> str:
    """Single-quote for a POSIX shell. The payload contains no single quotes by
    construction — it uses only double-quoted Python string literals — so this stays a
    simple wrap rather than the general escape dance."""
    if "'" in text:
        raise ValueError("bootstrap payload must not contain a single quote")
    return "'" + text + "'"
