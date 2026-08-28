#!/usr/bin/env python3
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
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

_BIN_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BIN_DIR.parent.parent  # coordinator/bin -> coordinator -> repo root

_SETTINGS_PATH = _REPO_ROOT / "coordinator" / "settings.json"
_DEBUG_ENV_VAR = "COORDINATOR_STATUSLINE_DEBUG"

_BOOTSTRAP_DONE = False


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


def _own_status_line(raw_stdin: bytes) -> str:
    """The minimal line this script emits when no inner statusline is
    configured. Never fabricates a context reading — that is the sidecar
    consumer's job (C4), not this script's."""
    try:
        payload = json.loads(raw_stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        payload = {}

    model = ""
    if isinstance(payload, dict):
        model_block = payload.get("model")
        if isinstance(model_block, dict):
            model = model_block.get("display_name") or model_block.get("id") or ""

    return f"[{model}] coordinator" if model else "coordinator"


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
