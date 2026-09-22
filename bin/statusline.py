"""
statusline.py — pass-through statusline that writes the context-usage
sidecar and preserves any user-configured inner statusline.

Claude Code renders this script's stdout as the interactive status line,
handing it the harness JSON (including ``context_window`` and
``session_id``) on stdin. This script has two jobs, in this order, with the
first never able to break the second:

1. Extract ``context_window`` and ``session_id`` from stdin and hand them to
   ``coordinator_core.session.context_usage_sidecar.write_usage`` — the
   producer half of the sidecar contract C1 built
   (``coordinator_core/session/context_usage_sidecar.py``). Any failure here
   (malformed JSON, missing fields, a write error) is swallowed: a broken
   sidecar write must never blank the user's status line. The failure is
   already observable as an absent sidecar, which the PostToolUse
   context-pressure advisory's UNKNOWN branch reports by design (C4) — this
   script does not also announce it on every render, since it runs on every
   render, and an unconditional stderr write on a persistent failure would
   produce noise proportional to render frequency under this repo's 50-70
   concurrent-session load norm (``docs/wiki/machine-load-norm.md``). Set
   ``COORDINATOR_STATUSLINE_DEBUG=1`` to see the swallowed exception on
   stderr.
2. Produce the visible status line. When ``coordinator/settings.json``'s
   ``statusLineCommand`` key names an inner statusline command, run it,
   forward the SAME stdin bytes this script received, reproduce its stdout
   byte-for-byte, and exit with its exit code. When no such key is
   configured, emit a minimal line of our own and exit 0.

Deliberately NOT read: ``~/.claude/settings.json``'s ``statusLine`` key. By
the time this script runs, that key points at this script — reading it back
would be a self-reference and an infinite-recursion hazard. The inner
command is instead named by this repo's own ``coordinator/settings.json``
(``statusLineCommand``), a file this chunk creates; no other file owns that
key.

Spec backlink: C3 of the 2026-08-17 "the advisory reads the harness" plan
(``docs/plans/2026-08-17-the-advisory-reads-the-harness.md``). The sidecar
contract is ``coordinator_core/session/context_usage_sidecar.py`` (C1); the
consumer is ``coordinator_core/hooks/postuse_advisory_dispatch.py`` (C4).

Negative-spec:
    - No re-implemented tail-scan fallback, ever. If the sidecar write
      fails, the failure is swallowed and reported nowhere but stderr behind
      a debug flag — never worked around with a guessed reading.
    - No fallback command guess when ``statusLineCommand`` is absent or its
      command fails to resolve: an unconfigured or misconfigured inner
      statusline means this script emits its own minimal line, never a
      silently-different substitute command.
    - Still never fabricates a context percentage in the OWN line below —
      that stays C4's job (the sidecar consumer), unchanged by the addition
      below.

PEER LABEL / GROUP EM / UHURA STANDING (W3-C5, reconciled from the DoE-plane
fork of this file). ``uhura-mode.py``'s own docstring names this script as
its consumer ("the statusline reads this on a hot path"), and
``group-em-nomination.py`` exists for the same "operator can see who they are
talking to" reason -- both landed in this repo (W2-C7) with no renderer yet
reading them. The DoE fork's own-line rendering (peer name label, gold Group
EM glyph, scarlet Uhura glyph) is ported into ``_own_status_line`` below,
reusing this repo's already-ported primitives (``coordinator_core.group_em
.session_registry.find_registry_row``, ``.nomination.read_record``,
``.atomic_record.load_by_path`` for the hyphenated ``uhura-mode.py`` sibling)
rather than DoE's own separate ``bin/lib`` copies or its file-backed peer-name
memo cache -- ``session_registry``'s own docstring names its directory scan as
affordable per call and its negative spec as deliberately cache-free, so no
second cache is built on top of it here. What did NOT port: DoE's inline
percentage/colour-by-pressure rendering. This script's own negative spec above
already assigns that job to C4's sidecar consumer, on purpose -- porting it
would re-open the exact fail-quiet risk that assignment exists to close, not
satisfy an unmet requirement.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path, PurePath

_BIN_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BIN_DIR.parent.parent  # coordinator/bin -> coordinator -> repo root

_SETTINGS_PATH = _REPO_ROOT / "coordinator" / "settings.json"
_DEBUG_ENV_VAR = "COORDINATOR_STATUSLINE_DEBUG"

_BOOTSTRAP_DONE = False

_GROUP_EM_GLYPH = "\U0001F9ED"  # 🧭 -- ported from the DoE fork, unchanged.
_UHURA_GLYPH = "\U0001F4DE"  # 📞 -- one codepoint, no variation selector, like the glyph above.
_GOLD = "\033[38;5;220m"
_SCARLET = "\033[38;5;196m"
_RESET = "\033[0m"


def _bootstrap_engine() -> None:
    """Put `_REPO_ROOT` on `sys.path` so the deferred `coordinator_core.*`
    imports scattered through this file resolve. Idempotent.

    What moved, and what did NOT: this single-line mutation used to run at
    MODULE scope, which made every import of this file — including on every
    interactive statusline render — mutate the `sys.path` of a warm server
    ~50 sessions share. The line is preserved exactly; only the trigger
    moved. No name is bound as a global here, so there is nothing to publish
    and no `__getattr__` hook is needed.
    """
    global _BOOTSTRAP_DONE
    if _BOOTSTRAP_DONE:
        return
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    _BOOTSTRAP_DONE = True


def _debug(message: str) -> None:
    """Write ``message`` to stderr only when the debug env var is set.

    Gated because this script runs on every statusline render; an
    unconditional stderr write on a persistent failure produces noise
    proportional to render frequency, and the failure is already observable
    as an absent sidecar.
    """
    if os.environ.get(_DEBUG_ENV_VAR):
        print(f"statusline.py: {message}", file=sys.stderr)


def _write_sidecar_from_payload(raw_stdin: bytes) -> None:
    """Extract ``context_window``/``session_id`` from ``raw_stdin`` and hand
    them to ``write_usage``. Any failure — malformed JSON, missing or
    wrong-shaped fields, a write error — is swallowed via ``except
    Exception:`` (never a bare ``except:``, which would also swallow
    ``KeyboardInterrupt``/``SystemExit``): a broken sidecar write must never
    blank the user's status line.
    """
    try:
        _bootstrap_engine()
        from coordinator_core.session.context_usage_sidecar import write_usage

        payload = json.loads(raw_stdin)
        session_id = payload["session_id"]
        context_window = payload["context_window"]
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("session_id missing or not a non-empty string")
        if not isinstance(context_window, dict):
            raise ValueError("context_window missing or not an object")
        write_usage(session_id, context_window, now=time.time())
    except Exception as exc:  # noqa: BLE001 - deliberate catch-all, see docstring
        _debug(f"sidecar write skipped: {exc!r}")


def _resolve_inner_command() -> list[str] | None:
    """Read ``coordinator/settings.json``'s ``statusLineCommand`` key and
    return it as an argv list, or ``None`` when unset/unreadable/malformed.

    Accepts either a JSON array of argv tokens or a single string (split via
    ``shlex.split``, POSIX rules — this repo's runtime convention is naked
    Python, not shell, but the *inner* command is operator-supplied and may
    itself be a shell one-liner).
    """
    try:
        raw = _SETTINGS_PATH.read_bytes()
    except OSError:
        return None

    try:
        settings = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

    if not isinstance(settings, dict):
        return None

    command = settings.get("statusLineCommand")
    if isinstance(command, list) and command and all(isinstance(tok, str) for tok in command):
        return command
    if isinstance(command, str) and command.strip():
        return shlex.split(command)
    return None


def _colorize_256(text: str, code: str) -> str:
    """Wrap ``text`` in a 256-colour escape ``code``, honouring ``NO_COLOR``."""
    if os.environ.get("NO_COLOR"):
        return text
    return f"{code}{text}{_RESET}"


def _colorize_gold(text: str) -> str:
    return _colorize_256(text, _GOLD)


def _colorize_scarlet(text: str) -> str:
    return _colorize_256(text, _SCARLET)


def _workspace_root(payload: dict) -> str | None:
    """The repo root this session is working in, for the Group EM / Uhura join.

    Same source order as ``_folder`` below (``workspace.project_dir`` then
    ``workspace.current_dir`` then ``cwd``), but returns the full path rather
    than just the trailing folder name — the holder records this joins
    against are keyed on the full, normalised repo root
    (``coordinator_core.group_em.atomic_record.repo_key``), never on a
    display name two different repos could share.
    """
    workspace = payload.get("workspace")
    candidate = None
    if isinstance(workspace, dict):
        candidate = workspace.get("project_dir") or workspace.get("current_dir")
    candidate = candidate or payload.get("cwd")
    if not isinstance(candidate, str) or not candidate.strip():
        return None
    return candidate


def _folder(payload: dict) -> str | None:
    """The session's home folder name — the label's fallback when no live
    registry row names this session (see ``_peer_label``)."""
    candidate = _workspace_root(payload)
    if not candidate:
        return None
    name = PurePath(candidate.rstrip("/\\")).name
    return name or None


def _peer_label(payload: dict, session_id: str) -> str | None:
    """The address this session is reachable at over SendMessage, or the
    session's folder name if no live registry row names it. Never raises.

    Resolved via ``coordinator_core.group_em.session_registry
    .find_registry_row`` — the primitive already ported into this engine at
    W2-C1 for exactly this join (harness session id -> registry row), scanned
    fresh on every call per that module's own negative spec (no caching layer
    added on top here; see this file's module docstring).
    """
    if session_id:
        try:
            _bootstrap_engine()
            from coordinator_core.group_em.session_registry import find_registry_row

            row = find_registry_row(session_id)
            if row is not None and row.name:
                return row.name
        except Exception as exc:  # noqa: BLE001 - never let a lookup failure blank the line
            _debug(f"peer label lookup failed: {exc!r}")
    return _folder(payload)


def _group_em_glyph(payload: dict, session_id: str) -> str | None:
    """The gold Group-EM glyph, iff THIS session currently holds the Group EM
    nomination for this repo — never for any other reason. Never raises."""
    if not session_id:
        return None
    repo_root = _workspace_root(payload)
    if not repo_root:
        return None
    try:
        _bootstrap_engine()
        from coordinator_core.group_em import nomination

        record = nomination.read_record(repo_root)
    except Exception as exc:  # noqa: BLE001
        _debug(f"group-em standing lookup failed: {exc!r}")
        return None
    if not isinstance(record, dict):
        return None
    if str(record.get("session_id") or "") != session_id:
        return None
    return _colorize_gold(_GROUP_EM_GLYPH)


def _uhura_module():
    """Load ``uhura-mode.py`` by path — its hyphenated filename is not
    import-safe as a package module, same as every other trampoline CLI in
    this directory. Best-effort: any failure here means no standing, never a
    raise."""
    try:
        _bootstrap_engine()
        from coordinator_core.group_em.atomic_record import load_by_path

        return load_by_path("_statusline_uhura", _BIN_DIR / "uhura-mode.py")
    except Exception:
        return None


def _holds_uhura(payload: dict, session_id: str) -> bool:
    """Whether THIS session currently holds this repo's Uhura comms channel.
    Same session-id join as ``_group_em_glyph``; never raises."""
    if not session_id:
        return False
    repo_root = _workspace_root(payload)
    if not repo_root:
        return False
    try:
        _bootstrap_engine()
        from coordinator_core.group_em import atomic_record

        uhura = _uhura_module()
        if uhura is None:
            return False
        record = uhura.read_record(atomic_record, repo_root)
    except Exception as exc:  # noqa: BLE001
        _debug(f"uhura standing lookup failed: {exc!r}")
        return False
    if not isinstance(record, dict):
        return False
    return str(record.get("session_id") or "") == session_id


def _own_status_line(raw_stdin: bytes) -> str:
    """The minimal line this script emits when no inner statusline is
    configured. Never fabricates a context reading — that is the sidecar
    consumer's job (C4), not this script's.

    Prefixed with the session's peer-name label (or folder name), and the
    gold Group-EM / scarlet Uhura glyphs when this session holds either
    standing — see this file's module docstring, "PEER LABEL / GROUP EM /
    UHURA STANDING". A lookup failure at any stage degrades to the plain
    ``[model] coordinator`` / ``coordinator`` line, never a crash or a blank
    line.
    """
    try:
        payload = json.loads(raw_stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    model = ""
    model_block = payload.get("model")
    if isinstance(model_block, dict):
        model = model_block.get("display_name") or model_block.get("id") or ""

    base = f"[{model}] coordinator" if model else "coordinator"

    session_id = str(payload.get("session_id") or "")
    label = _peer_label(payload, session_id)
    if not label:
        return base

    standing = _group_em_glyph(payload, session_id)
    holds_uhura = _holds_uhura(payload, session_id)
    # Uhura outranks the Group EM ON THE LABEL ONLY, matching the DoE fork's
    # own reasoning: a session can hold both, and scarlet answers "will a PM
    # message come from this window", the scarcer fact a reader scans for.
    if holds_uhura:
        colored_label = _colorize_scarlet(label)
    elif standing:
        colored_label = _colorize_gold(label)
    else:
        colored_label = label
    receiver = _colorize_scarlet(_UHURA_GLYPH) if holds_uhura else None
    segments = [s for s in (receiver, standing, colored_label) if s]
    prefix = " · ".join(segments)
    return f"{prefix} · {base}" if prefix else base


def _run_inner(command: list[str], raw_stdin: bytes) -> int:
    """Run the configured inner statusline command, forwarding ``raw_stdin``
    verbatim and reproducing its stdout byte-for-byte. Returns the exit code
    to adopt. A failure to launch or run the inner command (missing binary,
    non-zero exit, exception) falls back to this script's own line rather
    than propagating a blank status line."""
    try:
        _bootstrap_engine()
        from coordinator_core.win_portability import no_console_creationflags

        result = subprocess.run(
            command,
            input=raw_stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            **no_console_creationflags(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        _debug(f"inner statusline command failed to run: {exc!r}")
        sys.stdout.write(_own_status_line(raw_stdin))
        return 0

    sys.stdout.buffer.write(result.stdout)
    return result.returncode


def _selftest(raw_stdin: bytes) -> int:
    """``--selftest``: accept mock stdin, write the sidecar exactly as the
    real render path would, and print the resolved sidecar path — so AC3 is
    checkable without a live session."""
    try:
        payload = json.loads(raw_stdin)
        session_id = payload["session_id"]
    except Exception as exc:  # noqa: BLE001 - selftest reports, never crashes
        print(f"statusline.py --selftest: could not resolve session_id: {exc!r}", file=sys.stderr)
        return 1

    _bootstrap_engine()
    from coordinator_core.session.context_usage_sidecar import sidecar_path

    _write_sidecar_from_payload(raw_stdin)
    print(str(sidecar_path(session_id)))
    return 0


def main(argv: list[str] | None = None) -> int:
    _bootstrap_engine()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[2] if __doc__ else "")
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="Accept mock stdin, write the sidecar, and print the resolved sidecar path.",
    )
    args = parser.parse_args(argv)

    raw_stdin = sys.stdin.buffer.read()

    if args.selftest:
        return _selftest(raw_stdin)

    _write_sidecar_from_payload(raw_stdin)

    command = _resolve_inner_command()
    if command is not None:
        return _run_inner(command, raw_stdin)

    sys.stdout.write(_own_status_line(raw_stdin))
    return 0


if __name__ == "__main__":
    sys.exit(main())
