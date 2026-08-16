"""raw_cmdline_recovery — shared Windows raw-cmdline argv recovery.

Consumers: `coordinator/bin/coordinator-write-review-trail.py`,
`coordinator/bin/scoped-git-commit`, and `coordinator/bin/cross-repo-memo.py`
— the three entrypoints named in `gen-launcher-shim.py`'s
`_RAW_CMDLINE_ENTRYPOINTS` (mirrored, not imported, against
`coordinator_core/install/substrate.py`'s `_RAW_CMDLINE_TARGETS`).
`cross-repo-memo.py` is in both `_RAW_CMDLINE_ENTRYPOINTS` and
`_RAW_CMDLINE_TARGETS` and calls `recover_windows_argv` at its own
`sys.exit(main(...))` line, same as the other two. All three already insert
`coordinator/bin/lib` onto `sys.path` before importing their own siblings, so
no new bootstrap step is needed at any call site.

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
invoking Python, still carries the original, unmangled text ONLY when the
caller outer-quoted the whole post-``/c``/``/k`` string (measured: first and
last character of the remainder after the switch are both ``"``) —
PowerShell's ``cmd /c ""<exe>" <args>"`` form does this; git-bash/MSYS and
Python's own ``subprocess.run([...])`` list-form do not, and hand this
process a ``%CMDCMDLINE%`` capture from which the caret is ALREADY GONE by
the time this module ever reads it. On a non-outer-quoted spawn this
function is handed already-stripped text and cannot recover it — no parse
here can reconstruct bytes cmd.exe destroyed before this process started.
This module can only detect that condition and refuse to vouch for the
result; see ``UnsoundRawCmdlineTransport`` below.

**The outer-quote-pair test is a heuristic, not an exact classifier.** It
trades false-refusals against false-successes and gets some shapes wrong in
both directions: ``cmd /c "<exe>" --note "hello world"`` starts and ends
with a quote (looks SOUND) while still being lossy in general, because the
test only inspects the remainder's first/last character, not every
argument's internal quoting. Do not present this rule as precise; it is the
best boundary measurement supports, not a proof.

Best-effort and fail-safe: any parse mismatch (missing env var, non-Windows,
the recovered token count disagreeing with the mangled ``argv``) falls back
to ``argv`` unchanged — recovery must never crash, nor silently drop or
reorder an argument the caller actually passed. **This is a hard negative
spec, not an oversight:** the missing-env-var branch in particular must
NEVER become a refusal. It is the escape hatch that this transport's
remediation message points callers at ("invoke the extensionless entrypoint
directly through an interpreter") — a caller that took that advice will not
have `_LAUNCHER_RAW_CMDLINE_FILE` set at all, and if that branch started
refusing, the guard would block its own remediation path and every rung
would die. A future hardening pass must not "fix" this branch into a raise.

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


class UnsoundRawCmdlineTransport(Exception):
    """Raised when the captured ``%CMDCMDLINE%`` cannot vouch for argv fidelity.

    Two distinct causes collapse to this one exception, deliberately — a
    caller catching it does not need to distinguish them to respond
    correctly, and separate exception types would invite a caller to treat
    one as safer than the other, which it is not:

    - UNSOUND: a ``/c``/``/k`` switch was found, but the remainder is not
      wrapped in a single outer quote pair (first and last character both
      ``"``) — a transport shape measured to already have the caret (and
      potentially other metacharacters) stripped before this process ever
      started.
    - UNKNOWN: no ``/c``/``/k`` switch token was found at all — an
      unrecognised shape this module has no measured basis to vouch for.
      Silence on an unrecognised shape is the failure mode this exception
      exists to close; it does NOT fall back to the fail-safe branches
      below, which are reserved for conditions where non-recovery is known
      to be safe (e.g. no capture was ever made).

    Every entrypoint calling `recover_windows_argv` MUST catch this at its
    own ``sys.exit(main(...))`` line and respond per its own contract — an
    uncaught traceback here is a `docs/wiki/guard-messaging.md` § Register
    violation, not an acceptable failure mode.
    """


def _find_switch_end(raw: str) -> int | None:
    """Scan ``raw``'s leading tokens for a case-insensitive ``/c``/``/k``
    switch token and return the index immediately after it, or ``None`` if
    none is found.

    Anchors structurally, not lexically — does NOT search for the literal
    substring ``cmd.exe /c``, since ``/d``, ``/s``, an overridden
    ``COMSPEC``, or a quoted comspec token all vary the text ahead of the
    switch (e.g. ``cmd.exe /d /s /c "..."`` or ``"C:\\...\\cmd.exe" /c
    "..."`` — neither contains that substring). Skips a quoted comspec
    token, if present, and any unrecognised unquoted leading token.

    This deliberately scans past ANY leading token, not only a `/`-prefixed
    one -- the plan body's prose ("scan the leading tokens for a
    `/`-prefixed run terminated by ... `/c` or `/k`") reads narrower than
    AC1's own acceptance text ("tolerant of leading `/d`/`/s`"), and a bare
    (unquoted) comspec basename needs to be skippable too. Cross-referenced
    per review: coordinator:code-reviewer (9245562b, P3) -- the wording gap
    is between the plan's prose and its own AC1, not between the code and
    AC1.

    A quoted leading token's closing quote skip honours a backslash-escaped
    ``\\"`` inside it (e.g. an 8.3-shortened or COMSPEC-override path
    embedding one) — treating the first bare ``"`` as authoritative would
    close the token early and leave the scan resuming mid-string, at an
    offset with no relationship to where the real switch token starts.
    """
    pos = 0
    n = len(raw)
    while pos < n:
        while pos < n and raw[pos].isspace():
            pos += 1
        if pos >= n:
            break
        if raw[pos] == '"':
            end = pos + 1
            while end < n:
                if raw[end] == '"' and raw[end - 1] != "\\":
                    break
                end += 1
            pos = (end + 1) if end < n else n
            continue
        start = pos
        while pos < n and not raw[pos].isspace():
            pos += 1
        token = raw[start:pos]
        if token.lower() in ("/c", "/k"):
            return pos
        # Any other leading token — a bare (unquoted) comspec basename, or
        # an unrecognised switch — is skipped; scanning continues rather
        # than concluding UNKNOWN on the first non-switch token, since a
        # bare `cmd.exe` (no quotes) is itself a legitimate leading token.
    return None


def _classify_raw_cmdline_transport(raw: str) -> tuple[str, str | None]:
    """Classify a captured ``%CMDCMDLINE%`` string's spawn-transport soundness.

    Delegates the leading-token scan to `_find_switch_end` and classifies
    the remainder that follows the ``/c``/``/k`` switch it finds.

    Returns ``(status, remainder)``:
    - ``("SOUND", remainder)`` — switch found, remainder is outer-quoted
      (first and last character both ``"``).
    - ``("UNSOUND", remainder)`` — switch found, remainder is NOT
      outer-quoted. A legitimate argument may contain no metacharacter at
      all and still have arrived through this shape — soundness is a
      property of the TRANSPORT, never inferred from whether a caret is
      visible in the text.
    - ``("UNKNOWN", None)`` — no ``/c``/``/k`` switch token found.
    """
    switch_end = _find_switch_end(raw)
    if switch_end is None:
        return "UNKNOWN", None
    remainder = raw[switch_end:].strip()
    if len(remainder) >= 2 and remainder[0] == '"' and remainder[-1] == '"':
        return "SOUND", remainder
    return "UNSOUND", remainder


#: Cap on the leading-tokens prefix `spawn_shape_prefix` records for the
#: UNKNOWN case (no `/c`/`/k` switch found, so there is no structural
#: boundary between transport tokens and caller payload to anchor on).
#: Deliberately short — this is a spawn-shape fingerprint, not a payload
#: capture.
_UNKNOWN_SPAWN_SHAPE_CAP = 40


def spawn_shape_prefix(raw: str) -> str:
    """Return the leading transport tokens identifying ``raw``'s spawn
    shape — comspec path, `/d`/`/s`/etc., and the `/c`/`/k` switch itself —
    WITHOUT the remainder that follows it (the caller's actual command and
    argument payload, which is never returned here).

    This is what the C2b ledger persists in place of the raw capture: the
    ledger's purpose is to decide the documented flip-condition (a
    caller-shape distribution with zero unsound-or-unknown classifications
    among successful invocations), which only needs the SHAPE of the
    transport, never argument values, paths, or message text a caller
    supplied. When no switch is found (UNKNOWN) there is no structural
    boundary to anchor on, so the prefix is capped short rather than
    returning the raw text unbounded.
    """
    switch_end = _find_switch_end(raw)
    if switch_end is not None:
        return raw[:switch_end].strip()
    return raw[:_UNKNOWN_SPAWN_SHAPE_CAP].strip()


def recover_windows_argv(argv: list[str], launcher_cmd_name: str) -> list[str]:
    """Recover un-mangled argv from the raw invoking cmdline on Windows.

    ``launcher_cmd_name`` is the invoking .cmd launcher's own basename (e.g.
    ``"scoped-git-commit.cmd"`` or ``"coordinator-write-review-trail.cmd"``)
    — used to locate where this invocation's own arguments begin within the
    raw cmdline text, since ``%CMDCMDLINE%`` carries the whole invoking
    command line, launcher name included.

    See this module's docstring for the full recovery contract and its
    fail-safe guarantees.

    Raises `UnsoundRawCmdlineTransport` if the captured `%CMDCMDLINE%` text
    shows this invocation arrived through a transport known (or unknown-and-
    therefore-unvouchable) to have already stripped metacharacters before
    this process started — see `_classify_raw_cmdline_transport`. This is
    distinct from every fail-safe branch below, which returns `argv`
    unchanged for conditions where non-recovery is known to be safe.
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
    status, _remainder = _classify_raw_cmdline_transport(raw)
    if status != "SOUND":
        raise UnsoundRawCmdlineTransport(
            f"{status}: raw cmdline transport cannot vouch for argv fidelity"
        )
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
