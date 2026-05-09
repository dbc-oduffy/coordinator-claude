"""coordinator_session.py — Python shim for coordinator session self-claim.

Purpose: Allow Python writers (embedded heredoc or standalone scripts) to register
touched paths with the active coordinator session's touched.txt without reimplementing
the atomic-dedup-append logic. Shells out to the Bash lib for all session resolution
and append operations so there is one implementation per language and one source of
truth for the Windows + POSIX portability gotchas.

Spec backlink: ~/.claude/plans/safe-commit-fixes.md § Phase 3b

Self-claim contract (best-effort, never raises):
  - If no coordinator session is resolvable → emit stderr warning → return None.
  - If exactly one live session → claim the path.
  - If 2+ live sessions → emit stderr warning (ambiguous) → skip claim.
  - Any subprocess error → emit stderr warning → return None.
  - NEVER raises an exception or exits non-zero from claim_path().

Session resolution: shells out to cs_live_session_ids (lib line ~517) which returns
one sid per line with no headers or formatting. Do NOT use cs_active_sessions (returns
human-readable text including '(no active sessions)').
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

# Resolve Bash lib path: adjacent to this file inside lib/.
_LIB_PATH: Optional[str] = None


def _lib_path() -> Optional[str]:
    """Locate coordinator-session.sh relative to this module."""
    global _LIB_PATH
    if _LIB_PATH is not None:
        return _LIB_PATH
    candidate = Path(__file__).parent / "coordinator-session.sh"
    if candidate.is_file():
        _LIB_PATH = str(candidate)
        return _LIB_PATH
    # Fallback: absolute install path (matches known deployment layout).
    fallback = Path.home() / ".claude" / "plugins" / "coordinator-claude" / "coordinator" / "lib" / "coordinator-session.sh"
    if fallback.is_file():
        _LIB_PATH = str(fallback)
        return _LIB_PATH
    return None


def _bash_oneliner(script: str, env: Optional[dict] = None) -> subprocess.CompletedProcess:
    """Run a short Bash one-liner; inherit environment plus optional overrides."""
    merged = {**os.environ, **(env or {})}
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        env=merged,
        timeout=10,
    )


def resolve_live_session_ids() -> list:
    """Return list of live session ids (may be empty).

    Shells out to cs_live_session_ids from the Bash lib. Returns [] on any error
    so callers can treat the result as a plain list without error handling.
    """
    lib = _lib_path()
    if lib is None:
        return []
    try:
        result = _bash_oneliner(
            f'source "{lib}" && cs_live_session_ids'
        )
        if result.returncode != 0:
            return []
        lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
        return lines
    except Exception:
        return []


def claim_path(touched_file: str, entry: str) -> None:
    """Append entry to touched_file for the active coordinator session.

    Best-effort: emits a warning to stderr and returns without raising on any
    failure (no session, ambiguous sessions, subprocess errors, missing lib).

    Args:
        touched_file: Absolute path to the session's touched.txt.
        entry: Repo-relative path to record (the file that was just written).
    """
    lib = _lib_path()
    if lib is None:
        print(
            f"coordinator-session: lib not found — skipping self-claim for {entry}",
            file=sys.stderr,
        )
        return

    try:
        # Normalise paths for the shell invocation. On Windows+Git Bash, paths
        # may need to be POSIX-form; use cygpath when available, else pass as-is.
        tf_shell = _to_shell_path(touched_file)
        entry_shell = _to_shell_path(entry)

        result = _bash_oneliner(
            f'source "{lib}" && cs_atomic_dedup_append "{tf_shell}" "{entry_shell}"'
        )
        if result.returncode != 0:
            print(
                f"coordinator-session: cs_atomic_dedup_append failed (rc={result.returncode}) — "
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

    Resolves the active session via cs_live_session_ids, then calls claim_path
    with the appropriate touched.txt. Best-effort; never raises.

    Args:
        written_path: Absolute or repo-relative path that was just written.
                      Passed through to cs_atomic_dedup_append which handles
                      normalization on the Bash side.
    """
    lib = _lib_path()
    if lib is None:
        print(
            f"coordinator-session: lib not found — skipping self-claim for {written_path}",
            file=sys.stderr,
        )
        return

    try:
        sids = resolve_live_session_ids()
    except Exception:
        sids = []

    if len(sids) == 0:
        print(
            f"coordinator-session: no active session found — skipping self-claim for {written_path}",
            file=sys.stderr,
        )
        return

    if len(sids) > 1:
        print(
            f"coordinator-session: {len(sids)} live sessions (ambiguous) — "
            f"skipping self-claim for {written_path}",
            file=sys.stderr,
        )
        return

    sid = sids[0]
    try:
        # Build the touched.txt path via Bash to keep path resolution portable.
        result = _bash_oneliner(
            f'source "{lib}" && _cs_session_dir "{sid}"'
        )
        if result.returncode != 0 or not result.stdout.strip():
            print(
                f"coordinator-session: could not resolve session dir for {sid} — "
                f"skipping self-claim for {written_path}",
                file=sys.stderr,
            )
            return
        sdir = result.stdout.strip()
        touched_file = os.path.join(sdir, "touched.txt")
        claim_path(touched_file, written_path)
    except Exception as exc:
        print(
            f"coordinator-session: exception resolving session dir for {sid}: {exc}",
            file=sys.stderr,
        )


def _to_shell_path(p: str) -> str:
    """Convert a native path to a form safe for Bash string interpolation.

    On Windows + Git Bash, cygpath -u converts C:\\... → /c/... POSIX form.
    Falls back to the path as-is if cygpath is unavailable (POSIX hosts).
    Escapes single-quotes for safe use inside single-quoted shell strings by
    ending the quote, adding an escaped quote, and re-opening — but since we
    use double-quoted Bash strings, we instead escape double-quotes and
    backslashes only.
    """
    # Escape for Bash double-quoted string: backslash and double-quote.
    escaped = p.replace("\\", "/")  # Convert Windows backslashes to forward slashes.
    # cygpath conversion (best-effort, ignored if not available)
    try:
        result = subprocess.run(
            ["cygpath", "-u", p],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            escaped = result.stdout.strip()
    except (FileNotFoundError, Exception):
        pass
    return escaped
