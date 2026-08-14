"""SessionEnd hook — unattended rescue-commit+push for whatever this session
left uncommitted, fired without any invocation.

WHY THIS EXISTS: `/handoff`'s auto-commit step (`coordinator/skills/handoff/
SKILL.md` § Safe-Commit Auto-Commit) only fires when an EM remembers to run
`/handoff`. The PM's actual complaint was sessions that FORGOT — stranded
uncommitted paths from sessions that finished and never came back. A
mechanism that requires remembering does not address forgetting (this
repo's own discharge test: "the operator remembers" means the work is not
finished). `SessionEnd` fires exactly once, unconditionally, when a session
is genuinely over — the same reasoning `sessionend-archive-session.py`
already uses for its own best-effort teardown work, mirrored here.

ONE mechanism, two triggers: this hook calls the SAME `auto_commit_session`
path the `/handoff` ceremony calls (the `safe-commit-offer` CLI, mechanical-
grouping default — no `--message`/`--groups-json`, since there is no EM
present at session end to author one). Never a second, drifting
implementation of the compute-then-commit-then-push logic.

Contract:
  stdin   -- SessionEnd JSON payload (session_id, reason, cwd, ...).
  stdout  -- nothing (no context to inject; the only product is the
             commit+push side effect, plus a best-effort diagnostic log on
             a genuinely unexpected failure).
  exit 0  -- ALWAYS, unconditionally. A session ending is the worst possible
             moment to raise: no human is watching, and an exception here
             could break session teardown for every session on the machine.
             "Nothing to commit", a dirty index the CLI declines to touch,
             an unresolvable session id, a push that exhausted retry, a
             subprocess timeout, an unreadable payload -- every one of
             these degrades to a silent (or best-effort-logged) no-op, same
             posture as `sessionend-archive-session.py`.

Push-failure framing: `ceremony.scoped_git_commit` (composed inside
`auto_commit_session`) commits FIRST, then pushes-with-retry — a push that
exhausts its bounded retry leaves the commit landed locally and reports
`push_state` accordingly; it does not roll the commit back. A commit that
landed but did not push is a GOOD outcome here (it survives on disk, it
will push on the next successful attempt by any mechanism); only the
unpushed-AND-uncommitted case is the data loss this whole mechanism exists
to prevent. This hook does not need to special-case a push failure — it is
already not a failure from this hook's point of view.

Why a subprocess shim rather than an in-process coordinator_core import
(same reasoning as `sessionend-archive-session.py`): the auto-commit logic
already lives behind a CLI purpose-built for this exact call —
`coordinator/bin/safe-commit-offer.py` (engine plane) — ported there
specifically so `/handoff` and this hook share one non-fatal-by-design
entrypoint rather than duplicating the compute/group/commit/push sequence.

No `--sid`/session_id resolved here from `CLAUDE_SESSION_ID`/pid-guessing --
this hook never falls back to a guessed session key. No usable
`session_id` in the payload means there is nothing to rescue, not license
to guess whose dirty tree it is.

Spec backlink: state/sizings/2026-07-31-safe-commit-offer-at-
session-stop-events.yaml (this repo).
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

# Mirror of the "timeout" registered for this exact script's SessionEnd entry
# in coordinator/hooks/hooks.json (the authoritative value lives there, NOT
# here -- this is a comment-only mirror for humans tracing the budget, and is
# NOT read at runtime). Review: coordinator:code-reviewer 604caa04 -- the
# internal terminate/grace/kill budget below must stay comfortably under this
# ceiling, or the harness kills the hook process itself before the soft-
# terminate/hard-kill sequence can finish, reproducing one layer up the exact
# "cleanup never ran" failure this sequence exists to prevent.
_HOOKS_JSON_REGISTERED_TIMEOUT_SECS = 30

_SUBPROCESS_TIMEOUT_SECS = 22

# Grace window between the soft terminate and the hard kill. NEGATIVE SPEC:
# `subprocess.run(timeout=)` hard-kills (SIGKILL / TerminateProcess) the moment
# the bound expires, so no frame in the child ever runs -- including the
# `try/finally` in `run_commit_pipeline` whose whole job is to unstage the
# residue it staged. Staged-and-abandoned is the worst of the three possible
# states on a shared `work/*` branch: the next bare `git commit` from any
# concurrent session absorbs those paths into an unrelated commit. Untracked
# would be inert; committed would be a paper trail. Hence terminate-then-wait-
# then-kill rather than a bare `run(timeout=)`.
_TERMINATE_GRACE_SECS = 4

# Post-kill pipe-drain wait. Deliberately smaller than _TERMINATE_GRACE_SECS:
# after a hard kill() the child is gone and its pipes close immediately, so
# this only needs to cover the OS's own teardown latency, not the grace period
# a still-alive child gets to actually run its cleanup.
_POST_KILL_DRAIN_SECS = 2

# Worst case: _SUBPROCESS_TIMEOUT_SECS + _TERMINATE_GRACE_SECS +
# _POST_KILL_DRAIN_SECS == 22 + 4 + 2 == 28s, comfortably under the 30s
# ceiling mirrored above.


def _read_stdin(timeout: float = 2.0) -> str:
    """Bounded stdin read (Windows hang guard) -- same pattern as the other
    hooks in this directory (e.g. sessionend-archive-session.py._read_stdin)."""
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


def _log_diagnostic(payload: dict, note: str) -> None:
    """Append one best-effort line so a genuinely unexpected failure mode
    (not "nothing to commit", not "no session_id", not a push-retry
    exhaustion — those are all expected outcomes) is discoverable by grep
    instead of invisible. Never raises; a diagnostics-write failure must not
    itself break session teardown. Mirrors
    `sessionend-archive-session.py._note_missing_session_id`.
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
                stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                with (log_dir / "sessionend-auto-commit-diagnostics.log").open(
                    "a", encoding="utf-8"
                ) as fh:
                    fh.write(f"[{stamp}] {note}\n")
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
        # Never guess a session key -- silent no-op is the correct
        # disposition (no session_id means nothing to rescue), but leave a
        # breadcrumb the same way sessionend-archive-session.py does for
        # its own identical situation, in case this payload shape is wrong
        # on this Claude Code version.
        _log_diagnostic(payload, "SessionEnd payload carried no usable session_id; auto-commit skipped.")
        return 0

    root = _resolve_claude_klabauter_root()
    if not root:
        return 0  # fail-open -- engine plane unresolvable on this machine

    cli = Path(root) / "coordinator" / "bin" / "safe-commit-offer.py"
    if not cli.is_file():
        return 0  # fail-open -- CLI not present on this checkout

    try:
        proc = subprocess.Popen(
            [sys.executable, str(cli), "--session", session_id],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as exc:
        _log_diagnostic(payload, f"safe-commit-offer subprocess failed to spawn: {exc}")
        return 0

    # Popen + communicate(timeout=) rather than subprocess.run(timeout=) --
    # see the `_TERMINATE_GRACE_SECS` negative-spec block above for why.
    # NOTE (Windows): `Popen.terminate()` IS `TerminateProcess` on Windows --
    # there is no softer signal to send, so the soft-terminate path degrades
    # to the same hard-kill behaviour there. That is a platform limit, not a
    # bug this hook can work around.
    try:
        _stdout, stderr = proc.communicate(timeout=_SUBPROCESS_TIMEOUT_SECS)
        returncode = proc.returncode
    except subprocess.TimeoutExpired:
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.communicate(timeout=_TERMINATE_GRACE_SECS)
            _log_diagnostic(
                payload,
                f"safe-commit-offer exceeded {_SUBPROCESS_TIMEOUT_SECS}s for session "
                f"{session_id} but exited within the {_TERMINATE_GRACE_SECS}s "
                "soft-terminate grace window -- cleanup (unstaging any residue it "
                "staged) had a chance to run.",
            )
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except Exception:
                pass
            try:
                proc.communicate(timeout=_POST_KILL_DRAIN_SECS)
            except Exception:
                # Draining the pipes is best-effort here -- the child is
                # already killed; a still-blocked pipe read must not itself
                # raise out of a SessionEnd hook.
                pass
            _log_diagnostic(
                payload,
                f"safe-commit-offer ignored the soft terminate and required a hard "
                f"kill after {_SUBPROCESS_TIMEOUT_SECS + _TERMINATE_GRACE_SECS}s "
                f"total for session {session_id}; cleanup did NOT run -- staged "
                "residue may survive on disk.",
            )
        except Exception as exc:
            _log_diagnostic(payload, f"safe-commit-offer soft-terminate wait failed: {exc}")
        return 0
    except Exception as exc:
        _log_diagnostic(payload, f"safe-commit-offer subprocess failed: {exc}")
        return 0

    # Exit 0 (ran, nothing-to-commit-is-a-valid-outcome included) and exit 1
    # (session id unresolvable -- shouldn't happen here since we pass
    # --session explicitly, but the CLI degrades to it rather than raising)
    # are both expected outcomes, never worth a diagnostic. Exit 2 (usage
    # error -- would indicate a bug in THIS hook's own invocation) and exit 3
    # (transport failure -- CLAUDE_KLABAUTER_ROOT resolvable here but not inside the
    # trampoline, or the engine import failed) are genuinely unexpected.
    if returncode not in (0, 1):
        _log_diagnostic(
            payload,
            f"safe-commit-offer exited {returncode} for session {session_id}: "
            f"{(stderr or '').strip()[:500]}",
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
