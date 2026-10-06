#!/usr/bin/env python3
"""statusline — render `<peer-name> · <model> · <effort> · <gauge>` and publish the context reading.

THE LABEL IS AN ADDRESS, NOT A DECORATION. The leading segment is the name this
session answers to over SendMessage, so an operator can read one terminal's
status line and tell another EM exactly who to message. It supersedes the plain
folder name rather than sitting beside it: the peer name already contains the
folder plus the discriminator that makes it unique, so rendering both would
repeat the folder to no benefit. The folder name remains the fallback for when
the registry cannot be read — a recognisable label with no routing power beats
no label at all.

TWO JOBS, ONE INVOCATION. The harness runs this on every assistant message with
session JSON on stdin. It prints one line for the operator, and it writes the
`context_window` block to a per-session sidecar for the context-pressure advisory
to read.

WHY THE SIDECAR EXISTS. The statusline's stdin is the ONLY surface on which the
harness exposes live context usage — no hook event payload carries a token or
context field (`coordinator/docs/wiki/claude-md-surfaces/anthropic-harness-capability-map.md`, the
`/usage` row). Consumers that need to know how full the window is cannot ask;
they can only read what this process leaves behind.

FAILURE MODE IS BLANK, NEVER LOUD. A non-zero exit or empty stdout blanks the
status line, which is the correct degradation — a broken statusline must never
be able to take a session's render with it. Every failure path here therefore
ends in "print less" rather than a traceback. The one thing this must not do is
print a confident wrong number: an absent percentage renders as `–`, not `0%`,
because a context gauge that reads 0% while the window is full is the exact
fail-quiet shape this mechanism exists to eliminate.

WHY THE SIDECAR WRITE IS ATOMIC. "If a new update triggers while your script is
still running, the in-flight script is cancelled" (`statusline.md`). A cancelled
in-place write leaves a torn file, and the consumer is a PostToolUse hook firing
on every tool call — it would eventually read half a JSON object. Write-temp
then `os.replace` makes the swap atomic, so a reader sees the old reading or the
new one and never a partial one.

ONE SPAWN, ONLY WHEN EARNED. This runs once per assistant message on a machine
shared with many concurrent sessions, so its cost is paid per turn per
session. When an operator has relocated their own `statusLine` command into
`<settings-home>/statusline-inner.json`, this script spawns it exactly once
per invocation and reproduces its output byte-for-byte; the operator already
paid that spawn cost before registering this script, so delegating to it adds
no new cost class. With no inner command configured, there is no spawn at
all.

Sidecars are not pruned here — a directory scan per assistant message costs more
than the stale files do. They are swept with the rest of session scratch. A
`.tmp` sibling orphaned by a cancellation between `mkstemp` and `os.replace` is
the same tradeoff, not a separate oversight: it too is a few stray bytes, and a
`glob` to reclaim it would add a directory scan to a path that runs on every
assistant message across every concurrent session on the machine.
"""
from __future__ import annotations

import json
import math
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path, PurePath

# Writes per-session context-level and registry-memo records under settings home, outside the tracked tree.
GENERATES = []

_BIN_LIB_DIR = Path(__file__).resolve().parent / "lib"
_COORDINATOR_LIB_DIR = Path(__file__).resolve().parents[1] / "lib"


def _on_path(directory: Path) -> None:
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))


def _group_em_helper(name: str):
    """`session_registry` / `atomic_record`, from `bin/lib` where the plugin tree carries them,
    else from the engine's `coordinator_core.group_em` (a published plugin root ships no copy).
    The lib dirs join `sys.path` on first use so a bare import of this module leaves it
    untouched. Raises ImportError when neither resolves; every caller degrades on it."""
    _on_path(_BIN_LIB_DIR)
    try:
        return __import__(name)
    except ImportError:
        pass
    import lib  # noqa: F401 -- the published bin/lib package bootstraps the engine resolver
    from cc_invoke import require_dispatch_engine_on_path

    require_dispatch_engine_on_path()
    import importlib

    return importlib.import_module(f"coordinator_core.group_em.{name}")


def _session_registry_dir(*args, **kwargs):
    return _group_em_helper("session_registry").registry_dir(*args, **kwargs)


def _load_by_path(*args, **kwargs):
    return _group_em_helper("atomic_record").load_by_path(*args, **kwargs)


def no_console_creationflags() -> dict:
    _on_path(_COORDINATOR_LIB_DIR)
    from win_portability import no_console_creationflags as _impl

    return _impl()


def _compaction_defaults():
    _on_path(_COORDINATOR_LIB_DIR)
    import compaction_defaults

    return compaction_defaults

#: The harness cancels an in-flight statusline run on the next update (see the
#: module docstring's WHY THE SIDECAR WRITE IS ATOMIC section), so a genuinely
#: hung inner command is already survivable from the harness's side -- this
#: timeout exists only so a hung inner command does not hold this process
#: open for the whole cancellation window while starving the sidecar publish
#: on the NEXT invocation of a fresh process to run in.
_DELEGATE_TIMEOUT_SEC = 10

#: Bands for the default gauge, in percent of the PRE-COMPACTION budget (100 = compaction fires).
_ORANGE_AT = 75
_RED_AT = 90
#: Bands for the operator's percent-of-total-window gauge (`COORDINATOR_STATUSLINE_GAUGE=total`).
_TOTAL_ORANGE_AT = 40
_TOTAL_RED_AT = 47
_GAUGE_ENV = "COORDINATOR_STATUSLINE_GAUGE"
_BAR_CELLS = 5
_BAR_FULL = "\u25b0"
_BAR_EMPTY = "\u25b1"

_ORANGE = "\033[38;5;208m"
_RED = "\033[31m"
_GOLD = "\033[38;5;220m"
_SCARLET = "\033[38;5;196m"
_DIM = "\033[2m"
_RESET = "\033[0m"

_GROUP_EM_GLYPH = "\U0001F9ED"
_UHURA_GLYPH = "\U0001F4DE"  # one codepoint, no variation selector, like the Group EM glyph

_UNKNOWN_PCT = "–"

_PEER_RESCAN_AFTER_SEC = 30


def _settings_home() -> Path:
    override = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if override:
        return Path(override)
    return Path.home() / ".coordinator-claude-settings"


def _safe_stem(session_id: str) -> str:
    return "".join(c for c in session_id if c.isalnum() or c in "-_")


def _sidecar_path(session_id: str) -> Path:
    """FROZEN CROSS-PLANE CONTRACT (DR-190 § 10, 2026-09-02). The path shape
    `<settings-home>/state/context-window/<session_id>.json` and, in the
    written record, the keys `captured_at` and `context_window` are consumed
    by claude-klabauter's context-pressure advisory. Renaming either the path
    shape or those two keys breaks that advisory silently -- it has no other
    consumer today, so nothing on this side would notice the break.
    `$comment`: do not rename `_sidecar_path`'s output location or the
    `captured_at`/`context_window` keys in `_publish` without a coordinated
    change on claude-klabauter's side."""
    return _settings_home() / "state" / "context-window" / f"{_safe_stem(session_id)}.json"


def _effort_path(session_id: str) -> Path:
    return _settings_home() / "state" / "session-effort" / _safe_stem(session_id)


def _record_effort(payload: dict, session_id: str) -> str | None:
    """The session's live effort level; persisted so `subagent-statusline.py` can show the
    inherited effort on rows whose own `effort` field the harness omits."""
    block = payload.get("effort")
    level = block.get("level") if isinstance(block, dict) else None
    if not isinstance(level, str) or not level.strip():
        return None
    level = level.strip()
    if session_id:
        target = _effort_path(session_id)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            handle, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(level)
            os.replace(tmp, target)
        except OSError:
            pass
    return level


def _peer_memo_path(session_id: str) -> Path:
    return _settings_home() / "state" / "peer-name" / f"{_safe_stem(session_id)}.json"


def _write_json_atomic(target: Path, record: dict) -> None:
    """Swap a small JSON file in one step. Best-effort, never raises.

    In-place writes are unsafe here: the harness cancels an in-flight
    statusline when a new update triggers, and a cancelled write leaves a
    torn file for a consumer reading on every tool call. Write-temp then
    `os.replace` means a reader sees the old record or the new one, never a
    partial one."""
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        handle, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(record, fh)
        os.replace(tmp, target)
    except OSError:
        pass


def _publish(payload: dict, session_id: str) -> None:
    """Write the context reading where the advisory can find it. Best-effort.

    FROZEN (DR-190 § 10): the written record's `captured_at` and
    `context_window` keys are a cross-plane contract consumed by
    claude-klabauter's context-pressure advisory -- see `_sidecar_path`'s
    docstring. Do not rename them."""
    context = payload.get("context_window")
    if not isinstance(context, dict) or not session_id:
        return
    _write_json_atomic(
        _sidecar_path(session_id),
        {
            "session_id": session_id,
            "captured_at": time.time(),
            "source": "statusline",
            "context_window": context,
            "model": _model_block(payload).get("id"),
            "harness_version": payload.get("version"),
            "exceeds_200k_tokens": payload.get("exceeds_200k_tokens"),
        },
    )


def _inner_command() -> str | None:
    """The operator's own, relocated `statusLine` command, or `None`.

    Reads `<settings-home>/statusline-inner.json` verbatim -- the file holds
    the relocated `statusLine` object exactly as it stood in
    `~/.claude/settings.json` before relocation. Returns `None` in five
    cases: the file is absent, unreadable, not valid JSON, `command` is not a
    non-empty string, or the command names this very script (the recursion
    guard below) -- each is a "no delegate" answer, never an error.

    RECURSION GUARD MATCHES THE BREADCRUMB/PLUGIN PATH, NOT THE BARE
    BASENAME. An operator who already registered this script would otherwise
    relocate it onto itself, spawning itself forever; matching only on the
    bare basename `statusline.py` would ALSO rule out an operator's own,
    unrelated script that merely happens to share that name. Matching on
    `.coordinator-plugin-root`, or a `/bin/statusline.py` under a coordinator path (which
    also catches an older install's plugin-cache glob), targets the one thing that is
    actually recursive.
    """
    try:
        text = (_settings_home() / "statusline-inner.json").read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        obj = json.loads(text)
    except ValueError:
        return None
    if not isinstance(obj, dict):
        return None
    command = obj.get("command")
    if not isinstance(command, str) or not command.strip():
        return None
    normalized = command.replace("\\", "/")
    if ".coordinator-plugin-root" in normalized or (
        "coordinator" in normalized and "/bin/statusline.py" in normalized
    ):
        return None
    return command


#: Unquoted characters only a shell interprets (pipes, chaining, redirects, substitution). A
#: command carrying one cannot be honoured as an argv list, so it degrades to "print less"
#: rather than being handed to a shell.
_SHELL_OPERATORS = set("|&;<>`")


def _needs_shell(command: str) -> bool:
    quote = None
    for ch in command:
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch in _SHELL_OPERATORS:
            return True
    return False


def _argv_for(command: str) -> list:
    """`command` as a resolved argv list: tokens split with shell-style quoting (backslash literal
    on NT), `~` and `%VAR%`/`$VAR` expanded per token, the executable resolved on PATH. A `.sh` script on Windows runs
    under Git Bash directly. Raises OSError when the command needs a shell or names nothing
    runnable -- `_delegate` turns that into empty output."""
    if _needs_shell(command):
        raise OSError("statusLine command needs a shell; not delegated")
    lexer = shlex.shlex(command, posix=True)
    lexer.whitespace_split = True
    if os.name == "nt":
        lexer.escape = ""  # backslash is a path separator, not an escape, on Windows
    try:
        tokens = [os.path.expandvars(os.path.expanduser(t)) for t in lexer]
    except ValueError as exc:
        raise OSError(f"unparseable statusLine command: {exc}") from None
    if not tokens:
        raise OSError("empty statusLine command")
    exe = shutil.which(tokens[0]) or (tokens[0] if os.path.isfile(tokens[0]) else None)
    if exe is None:
        raise OSError(f"statusLine executable not found: {tokens[0]}")
    if os.name == "nt" and exe.lower().endswith((".cmd", ".bat")):
        # CreateProcess runs a batch file through cmd.exe -- a shell, which delegation never uses.
        raise OSError(f"statusLine batch-file executable needs cmd.exe; not delegated: {exe}")
    if os.name == "nt" and exe.lower().endswith(".sh"):
        bash = shutil.which("bash")
        if bash is None:
            raise OSError("statusLine .sh script needs bash, none on PATH")
        return [bash, exe, *tokens[1:]]
    return [exe, *tokens[1:]]


def _run_inner(command: str, raw: bytes) -> subprocess.CompletedProcess:
    """Spawn the operator's statusLine `command` as an argv list (no shell), feeding it `raw` on
    stdin and capturing its output unparsed.

    Injectable -- `_delegate` takes this as a parameter, so a test can stub
    it and never actually spawn a process (this module's own test file is
    zero-spawn by design). `no_console_creationflags()` suppresses the console-popup window.
    """
    return subprocess.run(
        _argv_for(command),
        input=raw,
        capture_output=True,
        timeout=_DELEGATE_TIMEOUT_SEC,
        **no_console_creationflags(),
    )


def _delegate(raw: bytes, command: str, runner=None) -> int:
    """Run the operator's own statusline on the exact raw stdin bytes, and
    reproduce its stdout and exit code unchanged.

    FAILURE MODE IS "PRINT LESS", NEVER A TRACEBACK -- matching this file's
    house rule (see module docstring). A spawn error (`OSError`) or a timeout
    (`subprocess.TimeoutExpired`, which `subprocess.run` raises only after
    already killing the child) both end in empty stdout and exit 0.
    """
    try:
        result = (runner or _run_inner)(command, raw)
    except (OSError, subprocess.TimeoutExpired):
        return 0
    sys.stdout.buffer.write(result.stdout)
    return result.returncode


_SELFTEST_SESSION_ID = "statusline-selftest-fixture"
_SELFTEST_FIXTURE = {
    "session_id": _SELFTEST_SESSION_ID,
    "context_window": {"used_percentage": 1},
}


def _selftest() -> int:
    """`statusline.py --selftest` -- proves the sidecar lands where the
    context-pressure advisory reads it, before an operator registers this
    script.

    Reads mock stdin; an empty or unparseable stdin falls back to a built-in
    fixture payload carrying `session_id` and `context_window`. Unlinks any
    pre-existing sidecar for that session_id FIRST -- a stale file left over
    from an earlier run must never let a no-op `_publish` (e.g. stubbed in a
    test) pass the exit oracle below by coincidence. Runs no inner command;
    it only reports which one WOULD run.
    """
    raw = _read_raw_stdin()
    payload = None
    if raw.strip():
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            payload = None
    if not isinstance(payload, dict):
        payload = dict(_SELFTEST_FIXTURE)

    session_id = str(payload.get("session_id") or _SELFTEST_SESSION_ID)
    sidecar = _sidecar_path(session_id)
    try:
        sidecar.unlink()
    except OSError:
        pass

    _publish(payload, session_id)
    command = _inner_command()
    print(f"sidecar: {sidecar}")
    print(f"inner: {command or 'none'}")
    threshold, why = _compaction_defaults().threshold_tokens(
        (payload.get("context_window") or {}).get("context_window_size")
    )
    print(f"compaction threshold: {int(threshold) if threshold else 'unknown'} ({why})")
    return 0 if sidecar.exists() else 1


def _model_block(payload: dict) -> dict:
    """The ``model`` field, isinstance-guarded like every other stdin field.

    ``payload.get("model") or {}`` alone only falls back on a falsy value --
    a truthy non-dict (e.g. a bare string) would short-circuit past the
    ``or`` and raise on the caller's ``.get(...)``."""
    block = payload.get("model")
    return block if isinstance(block, dict) else {}


def _folder(payload: dict) -> str | None:
    """The session's home folder name.

    Taken from ``workspace.project_dir`` -- where Claude Code was launched --
    rather than ``cwd``, so the label identifies the session for its whole
    life instead of following a mid-session directory change. Falls back to
    ``cwd`` when the workspace block is absent.

    Deliberately not ``workspace.repo.name``: that is parsed from the
    ``origin`` remote, so it is absent outside a git repo and can disagree
    with the folder on a clone whose directory was renamed."""
    workspace = payload.get("workspace")
    candidate = None
    if isinstance(workspace, dict):
        candidate = workspace.get("project_dir") or workspace.get("current_dir")
    candidate = candidate or payload.get("cwd")
    if not isinstance(candidate, str) or not candidate.strip():
        return None
    name = PurePath(candidate.rstrip("/\\")).name
    return name or None


def _name_in(entry: Path, session_id: str) -> str | None:
    """This session's peer name from one registry file, or None if it isn't ours."""
    try:
        record = json.loads(entry.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(record, dict) or record.get("sessionId") != session_id:
        return None
    name = record.get("name")
    return name.strip() if isinstance(name, str) and name.strip() else None


def _peer_name(session_id: str) -> str | None:
    """The address this session is reachable at over SendMessage.

    The harness publishes it as ``name`` in ``~/.claude/sessions/<pid>.json``,
    keyed by ``sessionId``. It is the only operator-visible handle for routing a
    message to a specific peer, so surfacing it here is what lets one EM be told
    to message another by name instead of by guesswork.

    RESOLVED ONCE, RE-READ CHEAPLY. Finding the right registry file means
    scanning a directory holding one entry per live session on the machine —
    affordable once, not on every assistant message across every concurrent
    session. The memo therefore caches the resolved *path*, and each subsequent
    invocation reads that single file and re-confirms the ``sessionId`` still
    matches.

    NEGATIVE SPEC — the memo deliberately does NOT cache the name itself. A
    session can be renamed mid-life, and a cached name would then render an
    address that no longer reaches this session. A wrong address is worse than
    no address: it sends the operator's message into a void while looking
    authoritative. Caching only the path keeps the read cheap and the value live.

    A miss is re-scanned no more than once per retry window — the registry entry
    may simply not be written yet at session start, and that is a wait, not a
    permanent absence.
    """
    if not session_id:
        return None
    memo_path = _peer_memo_path(session_id)
    try:
        memo = json.loads(memo_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        memo = None
    if isinstance(memo, dict):
        hint = memo.get("registry_path")
        if isinstance(hint, str) and hint:
            name = _name_in(Path(hint), session_id)
            if name:
                return name
        else:
            checked = memo.get("checked_at")
            if isinstance(checked, (int, float)) and not isinstance(checked, bool):
                if 0 <= time.time() - checked < _PEER_RESCAN_AFTER_SEC:
                    return None
    try:
        entries = list(_session_registry_dir().iterdir())
    except Exception:  # noqa: BLE001 -- an unresolvable registry is a fallback label, not a blank line
        entries = []
    for entry in entries:
        name = _name_in(entry, session_id)
        if name:
            _write_json_atomic(
                memo_path, {"registry_path": str(entry), "checked_at": time.time()}
            )
            return name
    _write_json_atomic(memo_path, {"registry_path": "", "checked_at": time.time()})
    return None


def _percentage(context: object) -> int | None:
    """The window's used percentage, or None when it cannot be trusted.

    Clamping is deliberately ASYMMETRIC. An over-100 reading clamps down to 100
    — it overstates nothing and a full window shown as full is correct. A
    NEGATIVE reading does not clamp up to 0: that would render an emphatic "this
    session is empty" out of input the harness should never have produced, and
    understating pressure is the one direction this whole mechanism exists to
    never fail in. Out-of-range-low is unknown, not zero.
    """
    if not isinstance(context, dict):
        return None
    raw = context.get("used_percentage")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    if not math.isfinite(raw) or raw < 0:
        return None
    return min(100, round(raw))


def _gauge_value(context: object) -> int | None:
    """The one context figure shown. Default: percent of the pre-compaction budget, so the
    auto-compact threshold reads 100. With `COORDINATOR_STATUSLINE_GAUGE=total` it is instead the
    percent of the whole window, and only that figure is shown.

    The threshold is derived in `compaction_defaults.threshold_tokens` (the payload carries none).
    When it cannot be derived the gauge is unknown (`_UNKNOWN_PCT`), never a guessed number.
    """
    total = _percentage(context)
    if total is None:
        return None
    if os.environ.get(_GAUGE_ENV, "").strip().lower() == "total":
        return total
    raw = context.get("used_percentage")
    window = context.get("context_window_size")
    threshold, _why = _compaction_defaults().threshold_tokens(window)
    if threshold:
        used_tokens = raw / 100.0 * _compaction_defaults()._number(window)
        return min(100, round(used_tokens / threshold * 100))
    return None


def _gauge_text(value: int | None) -> str:
    """A five-cell bar that fills toward compaction,
    then the figure -- `▰▰▱▱▱ 40%`. 100% means the harness compacts."""
    if value is None:
        return f"{_BAR_EMPTY * _BAR_CELLS} {_UNKNOWN_PCT}"
    if os.environ.get(_GAUGE_ENV, "").strip().lower() == "total":
        return f"{value}%"
    filled = min(_BAR_CELLS, round(value / 100 * _BAR_CELLS))
    return f"{_BAR_FULL * filled}{_BAR_EMPTY * (_BAR_CELLS - filled)} {value}%"


def _workspace_root(payload: dict) -> str | None:
    """The repo root this session is working in, for the Group EM join.

    Same source order as ``_folder`` (``workspace.project_dir`` then
    ``cwd``), but returns the full path rather than just the trailing folder
    name -- the nomination record is keyed on the full, normalised repo root,
    not on a display name that two different repos could share."""
    workspace = payload.get("workspace")
    candidate = None
    if isinstance(workspace, dict):
        candidate = workspace.get("project_dir") or workspace.get("current_dir")
    candidate = candidate or payload.get("cwd")
    if not isinstance(candidate, str) or not candidate.strip():
        return None
    return candidate


def _tree_carries_helpers() -> bool:
    """True in the authoring tree, whose `bin/lib` carries the group-em helpers and whose
    sibling CLIs read records by `repo_root` alone. A published plugin root carries neither:
    its sibling CLIs take the engine's `atomic_record` as a leading argument."""
    return (_BIN_LIB_DIR / "atomic_record.py").is_file()


def _nomination_record(repo_root: str):
    """The verified standing only (`read_authoritative`); `group-em-nomination.py` is a CLI
    trampoline with no module-level readers, so the engine module is the one source."""
    return _group_em_helper("nomination").read_authoritative(repo_root)


def _uhura_record(repo_root: str):
    uhura = _uhura_module()
    if uhura is None:
        return None
    if _tree_carries_helpers():
        return uhura.read_record(repo_root)
    return uhura.read_record(_group_em_helper("atomic_record"), repo_root)


def _group_em(payload: dict, session_id: str) -> str | None:
    """The gold Group-EM glyph, rendered iff THIS session currently holds the Group EM nomination
    for this repo — never for any other reason.

    RESOLUTION IS A SESSION-ID JOIN, NEVER A STORED PID AND NEVER THE PEER NAME. The nomination
    record's ``session_id`` is compared directly against the ``session_id`` already on stdin for
    this invocation — the same field every other segment in this file already trusts, not a pid
    read off a registry row and not the record's advisory ``peer_name`` snapshot.

    LIVENESS IS FREE HERE, DELIBERATELY NOT RE-DERIVED. ``group_em_nomination.is_live()`` exists
    to answer "is the recorded holder's session still running" for a THIRD PARTY asking about some
    OTHER session. This call is answering it about the session currently executing this very
    statusline invocation — if this code is running, this session is, by construction, alive.
    Re-scanning the harness registry to prove a session live to itself would be pure overhead on a
    hot path (every assistant message, ~25 concurrent sessions) for a fact already established by
    the fact of execution.

    CACHING DISCIPLINE, COPIED IN SPIRIT FROM ``_peer_name`` AND NARROWED WHERE IT DOES NOT APPLY.
    ``_peer_name`` caches the resolved registry *file path* (never the name) because finding it
    means scanning a directory of one-file-per-live-session. The nomination record's path has no
    equivalent scan to cache: ``group-em-nomination.py``'s own module docstring establishes its
    path is O(1)-deterministic from the repo root, with nothing to memoize. So there is nothing
    to path-cache here without inventing a cache with no scan behind it — the negative spec that
    DOES carry over unchanged is the value side: the Group EM's answer (does this session hold the
    role, right now) is resolved fresh on every call, never persisted across invocations. A cached
    "yes" that outlives a stand-down is a false standing looking authoritative, which is worse than a
    missing one.

    NEVER RAISES. A missing settings-home tree, an unreadable or absent nomination record, or a
    failed import of the nomination module all resolve to "no standing," matching this file's
    house rule that a broken statusline must degrade to less output, never a traceback.
    """
    if not session_id:
        return None
    repo_root = _workspace_root(payload)
    if not repo_root:
        return None
    try:
        record = _nomination_record(repo_root)
    except Exception:
        return None
    if not isinstance(record, dict):
        return None
    if str(record.get("session_id") or "") != session_id:
        return None
    return _colorize_gold(_GROUP_EM_GLYPH)


def _uhura_module():
    """Load ``uhura-mode.py`` by path -- its filename is not import-safe as a
    package name."""
    try:
        return _load_by_path("_statusline_uhura", Path(__file__).with_name("uhura-mode.py"))
    except Exception:
        return None


def _holds_uhura(payload: dict, session_id: str) -> bool:
    """Whether THIS session currently holds this repo's Uhura comms channel.

    Same session-id join and liveness reasoning as ``_group_em`` above. The
    never-raises rule is enforced locally here too, even though
    ``uhura-mode.py::read_record`` documents its own never-raises contract --
    that is an external contract, not a local guarantee, and this path runs
    once per assistant message across every concurrent session. The Group EM
    says who coordinates; this says which window a PM message will come
    from -- a stale "yes" here is the expensive direction, so the record is
    read fresh every call, never cached."""
    if not session_id:
        return False
    repo_root = _workspace_root(payload)
    if not repo_root:
        return False
    try:
        record = _uhura_record(repo_root)
    except Exception:
        return False
    if not isinstance(record, dict):
        return False
    return str(record.get("session_id") or "") == session_id


def _colorize_256(text: str, code: str) -> str:
    """Wrap ``text`` in a 256-colour escape ``code``, honouring ``NO_COLOR`` like ``_colorize``.

    Callers pass the escape constant.
    """
    if os.environ.get("NO_COLOR"):
        return text
    return f"{code}{text}{_RESET}"


def _colorize_scarlet(text: str) -> str:
    return _colorize_256(text, _SCARLET)


def _colorize_gold(text: str) -> str:
    return _colorize_256(text, _GOLD)


def _colorize(pct: int | None, text: str) -> str:
    """Tone by pressure band.

    Deliberately NOT gated on ``sys.stdout.isatty()``. The harness captures this
    process's stdout through a pipe and renders the result itself, so stdout is
    never a tty here and an isatty guard would suppress colour unconditionally.
    ``NO_COLOR`` remains honoured.
    """
    if os.environ.get("NO_COLOR"):
        return text
    if pct is None:
        return f"{_DIM}{text}{_RESET}"
    total = os.environ.get(_GAUGE_ENV, "").strip().lower() == "total"
    red_at, orange_at = (_TOTAL_RED_AT, _TOTAL_ORANGE_AT) if total else (_RED_AT, _ORANGE_AT)
    if pct >= red_at:
        tone = _RED
    elif pct >= orange_at:
        tone = _ORANGE
    else:
        return text
    return f"{tone}{text}{_RESET}"


def _read_raw_stdin() -> bytes:
    """The exact bytes on stdin, byte-fidelity preserved.

    `sys.stdin.buffer` is present on a real harness invocation (a genuine
    text-mode stream wraps an underlying binary buffer), so the production
    path reads bytes directly and never round-trips through str decoding.
    The existing statusline test suite (frozen, out of this row's scope)
    stubs `sys.stdin` with a text-only object exposing only `.read()` -- the
    fallback there re-encodes as utf-8, which is exact for anything that
    fixture can produce (plain JSON text).
    """
    buffer = getattr(sys.stdin, "buffer", None)
    if buffer is not None:
        return buffer.read()
    return sys.stdin.read().encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    """`argv` defaults to `sys.argv[1:]`; the warm door calls `main(argv)` uniformly across
    every `coordinator/bin/` entrypoint (`coordinator_core.warm.serve_classifier`)."""
    args = sys.argv[1:] if argv is None else argv
    if args[:1] == ["--selftest"]:
        return _selftest()

    raw = _read_raw_stdin()
    try:
        payload = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        payload = None
    if not isinstance(payload, dict):
        payload = None

    session_id = str(payload.get("session_id") or "") if payload is not None else ""
    if payload is not None:
        _publish(payload, session_id)

    command = _inner_command()
    if command is not None:
        # The user's own statusline decides what to do with malformed stdin
        # too (AC6) -- delegation runs on the raw bytes regardless of whether
        # this process could parse them as JSON.
        return _delegate(raw, command)

    if payload is None:
        return 0

    model = _model_block(payload).get("display_name")
    pct = _gauge_value(payload.get("context_window"))
    effort = _record_effort(payload, session_id)

    if not model and pct is None:
        return 0

    label = _peer_name(session_id) or _folder(payload)
    standing = _group_em(payload, session_id)
    # Uhura outranks the Group EM ON THE LABEL ONLY, and the Group EM glyph
    # is unaffected: a session can hold both, and scarlet answers "will a PM
    # message come from this window" -- the scarcer fact a reader scans for.
    holds_uhura = _holds_uhura(payload, session_id)
    if label and holds_uhura:
        label = _colorize_scarlet(label)
    elif standing and label:
        label = _colorize_gold(label)
    # The receiver leads the line, ahead of the standing, for the same reason.
    # The two glyphs coexist rather than displacing each other -- each keeps
    # its own colour so neither reads as the other.
    receiver = _colorize_scarlet(_UHURA_GLYPH) if holds_uhura else None
    segments = [s for s in (receiver, standing, label, model, effort) if s]
    segments.append(_colorize(pct, _gauge_text(pct)))
    sys.stdout.write(_colorize(None, " · ").join(segments) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
