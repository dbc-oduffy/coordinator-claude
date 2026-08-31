#!/usr/bin/env python3
"""SessionEnd hook — best-effort archival of this session's bookkeeping dir.

WHY SessionEnd AND NOT the /workstream-complete ceremony: archival moves
`<git-common-dir>/coordinator-sessions/<sid>/` to `.archive/<sid>-<date>/`,
which resets every once-per-session guard the directory backs (nudge
sentinels, dispatch evidence, `started_at`, `meta.json`). `/workstream
-complete` fires MID-session — a session can close several workstreams
before it actually ends — so archiving there wipes state the *same still-
live* session still needs. SessionEnd fires exactly once, when the session
is genuinely over, which is the only point archival can happen without
self-sabotaging the session doing the archiving. (The engine's
workstream-complete ceremony no longer archives: its call site was removed
2026-07-31, leaving this hook as the session-end replacement rather than an
addition alongside it. Until then this docstring asserted a removal that had
not landed and BOTH paths fired -- a live session's own bookkeeping dir was
moved out from under it mid-ceremony, resetting eight fire-once sentinels.)

Contract:
  stdin   -- SessionEnd JSON payload (session_id, reason, cwd, ...)
  stdout  -- nothing (this hook has no context to inject; its only product
             is the archive side effect)
  exit 0  -- ALWAYS. Archival here is explicitly best-effort (the 24h
             reaper is the backstop for anything this hook misses) and must
             never block session teardown. Every failure mode -- unparsable
             stdin, absent session_id, unresolvable claude-klabauter root, a
             non-zero/timed-out archive-session-scope.py -- degrades to a silent no-op.

Why a subprocess shim rather than an in-process coordinator_core import
(unlike track-dispatched-agents.py / nudge-em-code-dispatch.py, which import
and call a claude-klabauter op directly): the archival logic already lives behind a
CLI surface purpose-built for this exact call --
`coordinator/bin/archive-session-scope.py archive-session --sid <sid>` (claude-klabauter,
see its own module docstring) -- ported there from this repo's
workstream-complete SKILL.md specifically so the tail-arg assembly and the
session-scope archive share one non-fatal-by-design entrypoint. Re-importing
`coordinator_core.session.scope.archive` here would duplicate the
`resolve_colocated_claude_klabauter_root` + non-fatal wrapping that CLI already does;
shelling out to the existing CLI is the one-implementation choice.

No `--sid`, no call: this hook never falls back to a pid-derived or
otherwise guessed session key -- an unresolvable session_id means there is
nothing to archive, not license to guess.

Spec backlink: docs/plans/2026-07-23-wsc-tail-slim-down.md (WSC-3 chunk --
the CLI this hook shells out to). SessionEnd wiring is this repo's half of
moving archival off the mid-session workstream-complete ceremony.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path


def _read_stdin(timeout: float = 2.0) -> str:
    """Bounded stdin read (Windows hang guard) -- same pattern as the other
    hooks in this directory (e.g. track-dispatched-agents.py._read_stdin)."""
    box = {"data": ""}

    def _read() -> None:
        try:
            box["data"] = sys.stdin.read()
        except Exception:
            box["data"] = ""

    t = threading.Thread(target=_read, daemon=True)
    t.start()
    t.join(timeout)
    return box["data"]


_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
try:
    from _engine_root import resolve_claude_klabauter_root as _resolve_claude_klabauter_root  # noqa: E402
except Exception:
    def _resolve_claude_klabauter_root() -> str | None:
        return None


def _note_degradation(payload: dict, note: str) -> None:
    """Append one line recording a condition under which this hook archived
    NOTHING, so the "this hook silently never ran" failure mode is
    discoverable by grep instead of being invisible.

    Two callers, both silent-no-op seams on the SOLE archival occasion for a
    session's claim directory (the 24h reap is a backstop, not a second
    occasion): a payload with no usable `session_id`, and an absent archival
    CLI. The second is the one the engine plane can cause -- the CLI path is
    hardcoded against the resolved engine root, so a rename on that side stops
    every session archiving on this host with nothing erroring and nothing
    logged. A line here is what turns that into something someone can find.

    Deliberately does NOT use the per-session dir (one caller has no session
    key -- that is its whole problem) and does NOT raise: a diagnostics write
    that could itself break session teardown would be worse than the blind
    spot it documents. Every failure here is swallowed.
    """
    try:
        cwd = payload.get("cwd")
        probe = Path(cwd).resolve() if isinstance(cwd, str) and cwd else Path.cwd()
        for candidate in (probe, *probe.parents):
            if (candidate / ".git").exists():
                out = subprocess.run(
                    ["git", "-C", str(candidate), "rev-parse",
                     "--path-format=absolute", "--git-common-dir"],
                    capture_output=True, text=True, timeout=5, check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if out.returncode != 0 or not out.stdout.strip():
                    return
                log_dir = Path(out.stdout.strip()) / "coordinator-sessions" / "logs"
                log_dir.mkdir(parents=True, exist_ok=True)
                keys = ",".join(sorted(k for k in payload if isinstance(k, str)))
                stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                with (log_dir / "sessionend-archive-diagnostics.log").open(
                    "a", encoding="utf-8"
                ) as fh:
                    fh.write(f"[{stamp}] {note} payload_keys=[{keys}]\n")
                return
    except Exception:
        return


def main() -> int:
    raw = _read_stdin()

    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        # Never guess a session key -- but do NOT vanish either. `session_id`
        # is documented as a common field present on every hook type rather
        # than shown in a SessionEnd-specific payload example, so its presence
        # here is inferred from the general contract, not observed. If that
        # inference is wrong this hook would no-op on EVERY session forever,
        # archival would silently never happen, and the only symptom would be
        # slow directory growth reaped 24h later -- a failure indistinguishable
        # from healthy operation. Leave a breadcrumb so that case is
        # discoverable instead of invisible.
        _note_degradation(
            payload,
            "SessionEnd payload carried no usable session_id; archival skipped.",
        )
        return 0

    root = _resolve_claude_klabauter_root()
    if not root:
        return 0  # fail-open -- claude-klabauter unresolvable on this machine

    archive_cli = Path(root) / "coordinator" / "bin" / "archive-session-scope.py"
    if not archive_cli.is_file():
        # Fail-open, but never silently. This path is hardcoded against a tree
        # this repo does not own, so a rename on that side degrades the sole
        # archival occasion in the system to a no-op with nothing erroring --
        # and the 24h reap hides the consequence, leaving slow directory growth
        # that looks exactly like health.
        _note_degradation(
            payload,
            f"archival CLI absent at {archive_cli}; claim dir NOT archived this "
            "session, 24h reap is the only remaining backstop. If the engine "
            "plane renamed it, repoint this hook.",
        )
        return 0

    try:
        subprocess.run(
            [sys.executable, str(archive_cli), "archive-session", "--sid", session_id],
            timeout=10,
            capture_output=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        pass  # any subprocess failure (missing interpreter, timeout, ...) -- fail-open

    return 0


if __name__ == "__main__":
    sys.exit(main())
