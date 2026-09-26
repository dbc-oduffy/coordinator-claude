
import os
import subprocess
import sys
from typing import Optional

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin", "lib")
_LIB_DIR = os.path.normpath(_LIB_DIR)
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

# CREATE_NO_WINDOW is Windows-only, so the ternary short-circuits.
_NO_CONSOLE_WINDOW = (
    {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
)


def _claude_klabauter_env() -> Optional[dict]:
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
    return subprocess.run(
        [sys.executable, "-m", "coordinator_core.session.js_bridge_cli", *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
        **_NO_CONSOLE_WINDOW,
    )


def resolve_live_session_ids() -> list:
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

    ``entry`` MUST be repo-relative. Since 2026-08-21 the CLI REFUSES an
    absolute entry (``claims.canonical_claim_entry`` returns None) rather than
    recording an unmatchable key, and says so on its own stderr — which this
    wrapper captures. Its stderr is therefore FORWARDED below whenever it is
    non-empty, at rc 0 as well as non-zero: the child exits 0 on a refusal by
    design (the "never throws" contract), so a returncode-only check would
    swallow the one line telling the operator their claim was dropped, and a
    dropped claim nobody sees is a path nobody is protecting.

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
        if result.stderr and result.stderr.strip():
            print(result.stderr.rstrip("\n"), file=sys.stderr)
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
