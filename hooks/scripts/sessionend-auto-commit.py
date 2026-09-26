"""SessionEnd hook — DEREGISTERED. Kept on disk, unregistered, so re-arming is
one hooks.json entry rather than a rewrite.

DEREGISTERED 2026-08-27 per PM ruling relayed by claude-klabauter-em
(`cross-repo/inbox/2026-08-27-claude-klabauter-em-retire-sessionend-auto-commit.md`):
"commits are for EMs and when they choose to commit". This does NOT reverse the
2026-07-31 auto-commit pivot wholesale — that ruling still governs the CEREMONY
callers (`skills/quick-wrap/SKILL.md`, `skills/handoff/residue/040-dirty-tree.md`),
which dial the same `session.safe_commit_offer` engine op and are untouched,
because an EM ran the ceremony. It narrows the pivot to exclude THIS caller: `SessionEnd` means
`/clear`, `/quit`, logout, exit — no EM is present to choose, which is exactly why
this hook passed no `--message`/`--groups-json`. The data-loss case it was written
against is covered by `/workday-complete`'s dirty-tree sweep
(`coordinator_core/ops/workday_complete_step2_5_dirty_tree.py`, engine-side), an EM-run
daily ceremony. A future reader finding the deregistration in git history should
read the memo, not assume an oversight.

Everything below documents the mechanism as built, for the re-arming case.

WHY IT WAS BUILT: `/handoff`'s auto-commit step (`coordinator/skills/handoff/
SKILL.md` § Safe-Commit Auto-Commit) only fires when an EM remembers to run
`/handoff`. The PM's actual complaint was sessions that FORGOT — stranded
uncommitted paths from sessions that finished and never came back. A
mechanism that requires remembering does not address forgetting (this
repo's own discharge test: "the operator remembers" means the work is not
finished). `SessionEnd` fires exactly once, unconditionally, when a session
is genuinely over — the same reasoning `sessionend-archive-session.py`
already uses for its own best-effort teardown work, mirrored here.

ONE mechanism, two triggers: this hook (as built) called the SAME `auto_commit_session`
path the `/handoff` ceremony called (the `safe-commit-offer` CLI, mechanical-
grouping default — no `--message`/`--groups-json`, since there is no EM
present at session end to author one). Never a second, drifting
implementation of the compute-then-commit-then-push logic.

DELETED SPAWN TARGET (2026-08-27): `coordinator/bin/safe-commit-offer.py` (and its
`.cmd` sibling) was deleted from the engine plane, replaced by the registered engine
op `session.safe_commit_offer` (scope "none", MUTATING; dialed via
`coordinator-invoke session.safe_commit_offer '{"cwd": ..., "session_id": ..., "message":
...}'` -- one positional JSON string, both keys required: `cwd` picks the tree,
`session_id` establishes identity, and omitting the latter commits under whichever
session started the warm engine. Never a
bareword). This hook is unregistered and this module is intentionally NOT rewritten
to call the op — the spawn code below is left as historical documentation of the CLI
shape, per the DEREGISTERED note above. Re-arming this hook requires porting the
subprocess call below to dial `session.safe_commit_offer` instead of resurrecting the
deleted CLI path.

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

Push-failure framing: `auto_commit_session` commits FIRST, then pushes-with-retry — a push that
exhausts its bounded retry leaves the commit landed locally and reports
`push_state` accordingly; it does not roll the commit back. A commit that
landed but did not push is a GOOD outcome here (it survives on disk, it
will push on the next successful attempt by any mechanism); only the
unpushed-AND-uncommitted case is the data loss this whole mechanism exists
to prevent. This hook does not need to special-case a push failure — it is
already not a failure from this hook's point of view.

Why a subprocess shim rather than an in-process coordinator_core import
(same reasoning as `sessionend-archive-session.py`): the auto-commit logic,
as built, lived behind a CLI purpose-built for this exact call —
`coordinator/bin/safe-commit-offer.py` (engine plane; deleted, see the
DELETED SPAWN TARGET note above) — ported there specifically so `/handoff`
and this hook could share one non-fatal-by-design entrypoint rather than
duplicating the compute/group/commit/push sequence.

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

_HOOKS_JSON_REGISTERED_TIMEOUT_SECS = 30

_SUBPROCESS_TIMEOUT_SECS = 22

# Grace window between the soft terminate and the hard kill. NEGATIVE SPEC:
_TERMINATE_GRACE_SECS = 4

# Post-kill pipe-drain wait. Deliberately smaller than _TERMINATE_GRACE_SECS:
_POST_KILL_DRAIN_SECS = 2

# Worst case: _SUBPROCESS_TIMEOUT_SECS + _TERMINATE_GRACE_SECS +
# _POST_KILL_DRAIN_SECS == 22 + 4 + 2 == 28s, comfortably under the 30s


def _read_stdin(timeout: float = 2.0) -> str:
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
        _log_diagnostic(payload, "SessionEnd payload carried no usable session_id; auto-commit skipped.")
        return 0

    root = _resolve_claude_klabauter_root()
    if not root:
        return 0

    cli = Path(root) / "coordinator" / "bin" / "safe-commit-offer.py"
    if not cli.is_file():
        return 0

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

    # see the `_TERMINATE_GRACE_SECS` negative-spec block above for why.
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

    # (transport failure -- CLAUDE_KLABAUTER_ROOT resolvable here but not inside the
    if returncode not in (0, 1):
        _log_diagnostic(
            payload,
            f"safe-commit-offer exited {returncode} for session {session_id}: "
            f"{(stderr or '').strip()[:500]}",
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
