"""coordinator_session.py — Python shim for coordinator session self-claim.

Purpose: Allow Python writers (embedded heredoc or standalone scripts) to register
touched paths with the active coordinator session's touched.txt without reimplementing
the atomic-dedup-append logic. Shells out to the claude-klabauter native session engine's CLI
bridge (`coordinator_core.session.js_bridge_cli`, invoked as a `sys.executable -m`
subprocess) for all session resolution and append operations — no bash anywhere in
this module. `js_bridge_cli` is the Python-native counterpart of the retired
sourced bash session lib (see that module's docstring — it was originally built to
serve the equivalent Node-side JS shim, `coordinator_session.js`, itself retired
2026-07-27, and is a 1:1 target for this Python shim's needs too).

Spec backlink: ~/.claude/plans/safe-commit-fixes.md § Phase 3b
Repoint spec: docs/plans/2026-07-16-bash-clean-slate-residual-migration.md

Self-claim contract (best-effort, never raises):
  - If no coordinator session is resolvable → emit stderr warning → return None.
  - If exactly one live session → claim the path.
  - If 2+ live sessions → emit stderr warning (ambiguous) → skip claim.
  - Any subprocess error → emit stderr warning → return None.
  - NEVER raises an exception or exits non-zero from claim_path().

Session resolution: subprocess call to `js_bridge_cli live-session-ids`, which prints
one sid per line with no headers or formatting (the Python-native counterpart of the
retired `cs_live_session_ids`).
"""

import os
import subprocess
import sys
from typing import Optional

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin", "lib")
_LIB_DIR = os.path.normpath(_LIB_DIR)
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

# Windows-only: suppress the console window that console-subsystem child
# processes flash when this process has no console to inherit (e.g. spawned
# by an MCP server or a GUI Claude Code host). POSIX: empty dict —
# CREATE_NO_WINDOW is Windows-only, so the ternary short-circuits.
_NO_CONSOLE_WINDOW = (
    {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
)


def _claude_klabauter_env() -> Optional[dict]:
    """Resolve CLAUDE_KLABAUTER_ROOT and build the js_bridge_cli subprocess env.

    Returns None if CLAUDE_KLABAUTER_ROOT is unresolvable — callers treat that as a
    best-effort skip, matching the old "lib not found" branch.
    """
    try:
        from cc_invoke import _resolve_claude_klabauter_root, _build_subprocess_env  # noqa: E402
    except ImportError:
        return None
    try:
        claude_klabauter_root = _resolve_claude_klabauter_root()
    except Exception:
        return None
    return _build_subprocess_env(claude_klabauter_root)


def _js_bridge_cli(args: list, env: dict) -> subprocess.CompletedProcess:
    """Run `python3 -m coordinator_core.session.js_bridge_cli <args>`."""
    return subprocess.run(
        [sys.executable, "-m", "coordinator_core.session.js_bridge_cli", *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
        **_NO_CONSOLE_WINDOW,
    )


def resolve_live_session_ids() -> list:
    """Return list of live session ids (may be empty).

    Shells out to `js_bridge_cli live-session-ids`. Returns [] on any error
    so callers can treat the result as a plain list without error handling.
    """
    env = _claude_klabauter_env()
    if env is None:
        return []
    try:
        result = _js_bridge_cli(["live-session-ids"], env)
        if result.returncode != 0:
            return []
        lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
        return lines
    except Exception:
        return []


def claim_path(touched_file: str, entry: str) -> None:
    """Append entry to touched_file for the active coordinator session.

    Best-effort: emits a warning to stderr and returns without raising on any
    failure (no session, ambiguous sessions, subprocess errors, unresolvable
    claude-klabauter engine).

    Args:
        touched_file: Absolute path to the session's touched.txt.
        entry: Repo-relative path to record (the file that was just written).
    """
    env = _claude_klabauter_env()
    if env is None:
        print(
            f"coordinator-session: claude-klabauter engine not resolvable — skipping self-claim for {entry}",
            file=sys.stderr,
        )
        return

    try:
        result = _js_bridge_cli(["claim-path", touched_file, entry], env)
        if result.returncode != 0:
            print(
                f"coordinator-session: claim-path failed (rc={result.returncode}) — "
                f"skipping self-claim for {entry}",
                file=sys.stderr,
            )
    except Exception as exc:
        print(
            f"coordinator-session: exception during self-claim for {entry}: {exc}",
            file=sys.stderr,
        )


def self_claim(written_path: str) -> None:
    """Convenience wrapper: resolve the active session and claim written_path.

    Delegates entirely to `js_bridge_cli self-claim`, which resolves the active
    session (platform session-id env vars first, falling back to live-session
    enumeration — exactly-one-live-session required) and claims written_path.
    Best-effort; never raises.

    Args:
        written_path: Absolute or repo-relative path that was just written.
    """
    env = _claude_klabauter_env()
    if env is None:
        print(
            f"coordinator-session: claude-klabauter engine not resolvable — skipping self-claim for {written_path}",
            file=sys.stderr,
        )
        return

    try:
        result = _js_bridge_cli(["self-claim", written_path], env)
        if result.returncode != 0:
            print(
                f"coordinator-session: self-claim failed (rc={result.returncode}) — "
                f"skipping self-claim for {written_path}",
                file=sys.stderr,
            )
        if result.stderr:
            sys.stderr.write(result.stderr)
    except Exception as exc:
        print(
            f"coordinator-session: exception during self-claim for {written_path}: {exc}",
            file=sys.stderr,
        )
