#!/usr/bin/env python3
"""PreToolUse(Agent|Workflow) naked-Python advisory-nudge hook.

Self-contained port of nudge-multiwave-workflow.sh -- W5 straggler port
(no reusable claude-klabauter op exists for this logic yet; grepped
coordinator_core/hooks and coordinator_core/ops for "multiwave"/"nudge"
and found no match, so the decision logic is ported directly here rather
than split into an engine op + thin stub). ONE python3 hook entry -- zero
Git-Bash cold-start per Agent/Workflow dispatch on Windows (each bash.exe
spawn costs 200-500ms; this is the whole point).

Offer-shape (never blocks): this hook ALWAYS exits 0. On the nudge path it
emits {"hookSpecificOutput":{"hookEventName":"PreToolUse",
"additionalContext":"<message>"}} on stdout -- an advisory suggestion
surfaced to the EM, never a deny. It never sets "decision":"block" and
never returns a non-zero exit code on the nudge path.

Branches on tool_name (byte-faithful port of the bash oracle's decision
tree):
  - "Workflow" -> records a session sentinel (workflow-launched) and exits
    0 silently. Once a Workflow has been launched this session, the nudge
    never fires again (Agent branch condition 4 below).
  - "Agent"    -> runs the nudge logic (conditions 1-6 below); fires at
    most once per session (condition 5), and only once the dispatch is the
    Nth write-capable EM-originated Agent dispatch within a rolling
    W-second window (condition 6, burst-threshold below).
  - anything else -> exits 0 silently.

Burst threshold: a single hand-dispatch (e.g. a lone review-integrator, or
a review->integrate pair) no longer trips this nudge. It fires only when
the CURRENT dispatch is the Nth qualifying dispatch within the last W
seconds, tracked via a per-session rolling log at
${SESSION_DIR}/multiwave-dispatch-log (one epoch-seconds line per
qualifying dispatch, pruned to the window on each invocation).
  N defaults to 4, overridable via COORDINATOR_MULTIWAVE_NUDGE_THRESHOLD.
  W defaults to 30, overridable via COORDINATOR_MULTIWAVE_NUDGE_WINDOW_SECS.

Override (ESCAPE HATCH -- preserve exactly): set
COORDINATOR_OVERRIDE_MULTIWAVE_WORKFLOW=1 to suppress the nudge entirely
(condition 1). Read from os.environ at call time, mirroring the bash
oracle's process-env read (no re-plumb to a sentinel file -- this hook is
a plain script invocation each time, not a resident engine call, so the
env var IS reachable at hook-call time, unlike the resident-engine
env-hatch re-plumb precedent in nudge-foreground-agent-dispatch.py).

DENY-CONDITION CARE (there is no deny path here -- this hook is advisory
only -- but the conditions that gate the ADVISORY firing must be preserved
exactly, since a wrongly-loosened gate turns an occasional nudge into a
per-dispatch nag, and a wrongly-tightened gate silently drops the offer):
  1. COORDINATOR_OVERRIDE_MULTIWAVE_WORKFLOW=="1" -> never fire.
  2. Raw payload contains the substring '"agent_id"' ANYWHERE (not just a
     parsed top-level key -- the bash oracle greps the whole raw JSON text,
     so a nested tool_response.agent_id, if it ever appeared on a
     PreToolUse payload, would also suppress; ported as a raw-substring
     check on the original stdin bytes for byte-fidelity, not a
     payload.get("agent_id") key lookup) -> subagent-originated dispatch,
     never nudge.
  3. subagent_type must be present under tool_input and must match the
     write-capable roster (*executor* substring, or an exact
     review-integrator/enricher name, case-insensitive) -- everything else
     (including empty/missing) never fires.
  4. No Workflow launched this session (workflow-launched sentinel absent).
  5. Fires at most once per session (multiwave-workflow-nudged sentinel).
  6. Burst threshold: rolling-window dispatch count (post-prune, INCLUDING
     the current dispatch just appended) must be >= THRESHOLD.

Spec backlink: coordinator/docs/wiki/coordinator-tripwires.md
§ NUDGE-MULTIWAVE-WORKFLOW

Contract (mirrors the bash hook it replaces):
  stdin   -- PreToolUse JSON (tool_name, tool_input with subagent_type,
             session_id, agent_id (subagent-originated only), ...)
  stdout  -- one hookSpecificOutput JSON envelope (additionalContext) on a
             qualifying burst-threshold-tripping Agent dispatch; NOTHING
             otherwise (silent pass)
  exit 0  -- always (advisory only; never blocks/denies)

Graceful degradation -- REQUIRED: any failure to parse stdin, resolve the
git root, or read/write session-scoped sentinel/log files falls through to
a silent pass (exit 0, no stdout). A filesystem hiccup must never brick an
Agent/Workflow dispatch.

NOTE: cutover is complete -- hooks.json registers only this Python hook now.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
try:
    import _message_envelope as _envelope  # noqa: E402
except Exception:
    # Defensive fallback -- an isolated copy-only deploy without its
    # sibling _message_envelope.py must still compose and emit the nudge
    # rather than crash on import (mirrors the same fallback already
    # established in nudge-initiative-goals-ladder.py).
    from dataclasses import dataclass as _dataclass
    from typing import Optional as _Optional

    @_dataclass(frozen=True)
    class _FallbackMessage:
        prose: str
        alternative: "_Optional[str]" = None
        anchor: "_Optional[str]" = None

    class _FallbackEnvelope:
        CHANNEL_ADDITIONAL_CONTEXT = "additional_context"
        Message = _FallbackMessage

        @staticmethod
        def compose(prose, alternative=None, anchor=None):
            return _FallbackMessage(prose=prose.strip(), alternative=alternative, anchor=anchor)

        @staticmethod
        def emit(message, channel):  # noqa: ARG004 -- single-channel fallback
            parts = [message.prose]
            if message.alternative:
                parts.append("")
                parts.append("```\n" + message.alternative.rstrip("\n") + "\n```")
            if message.anchor:
                parts.append("")
                parts.append("See {}.".format(message.anchor))
            envelope = {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "additionalContext": "\n".join(parts),
                }
            }
            sys.stdout.write(json.dumps(envelope, separators=(",", ":")))
            return 0

    _envelope = _FallbackEnvelope()

from _win_portability import no_console_creationflags  # noqa: E402
try:
    from _git_common_dir import resolve_git_common_dir as _resolve_git_common_dir  # noqa: E402
except Exception:
    # Defensive fallback -- a deploy missing its sibling _git_common_dir.py
    # must still fail open (empty common dir -> callers skip) rather than
    # crash on import.
    def _resolve_git_common_dir(git_root: str) -> str:
        return ""
try:
    from _session_hub import session_id_is_real, ensure_session_dir  # noqa: E402
except Exception:
    # Defensive fallback -- a deploy missing its sibling _session_hub.py must
    # still fail open to the pre-gate behaviour, not crash on import.
    def session_id_is_real(session_id: object) -> bool:
        return bool(session_id)

    def ensure_session_dir(session_dir: "str | os.PathLike[str]", session_id: object) -> bool:
        try:
            os.makedirs(os.fspath(session_dir), exist_ok=True)
        except (OSError, TypeError, ValueError):
            return False
        return True
try:
    from _git_root_walk import git_root_walk as _git_root_walk  # noqa: E402
except Exception:
    # Defensive fallback -- a deploy missing its sibling _git_root_walk.py
    # must still fail open to the subprocess rung below, not crash on import.
    def _git_root_walk() -> str | None:
        return None

#: See state/relocations/guard-message-cap/nudge-multiwave-workflow.py.md
#: for the full explanation this hook's message used to spell out inline
#: (docs/plans/2026-08-02-guard-message-character-cap.md § C6).
_WIKI_ANCHOR = (
    # Review: code-reviewer -- bare fragment produced an unresolvable
    # `render()` citation. Full path matches every other converted hook.
    "coordinator/docs/wiki/guard-message-concision.md"
    "#workflow-offer-nudge"
)

# session_id format guard -- mirrors the bash oracle's guard (which itself
# mirrors the AGENT_ID format guard in track-dispatched-agents.py / the
# SESSION_ID guard in nudge-foreground-agent-dispatch.py). Nulls garbage
# session_id so a malformed value can't produce a bogus SESSION_DIR path.
_SESSION_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{4,}$")

# Write-capable roster (case-insensitive). Keep in sync with the bash
# oracle's `case` block and CLAUDE.md § Roster Doctrine / § Adding a
# Convention -- a future write-capable worker type that doesn't match
# *executor* and isn't named review-integrator/enricher will silently miss
# this nudge, same caveat as the bash original.
_EXACT_WRITE_CAPABLE = {
    "review-integrator",
    "coordinator:review-integrator",
    "enricher",
    "coordinator:enricher",
}


def _is_write_capable(subagent_type_lc: str) -> bool:
    if "executor" in subagent_type_lc:
        return True
    return subagent_type_lc in _EXACT_WRITE_CAPABLE


def _git_root() -> str | None:
    """Repo root as `git rev-parse --show-toplevel` would report it, fail-open to None.

    Resolved by an in-process parent walk (`_git_root_walk`) first -- no subprocess spawn on
    the routine path; ~0.065ms against ~25ms + one process for the subprocess form. The
    `git rev-parse --show-toplevel` subprocess below is now a FALLBACK for the case the walk
    cannot resolve (a bare repo, or a `GIT_DIR`-driven invocation with no `.git` above cwd), not
    the default -- do not reintroduce it as a routine path.

    Suppressed via `no_console_creationflags()` for structural parity with
    the other `_git_root()` copies in this tree (`test_no_bare_python_spawn.py`
    scope), even though git.exe itself does not AllocConsole().
    """
    walked = _git_root_walk()
    if walked:
        return walked
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=1,
            **no_console_creationflags(),
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    root = result.stdout.strip()
    return root or None


def _read_int_lines(path: Path) -> list[int]:
    """Best-effort int-per-line read; non-numeric/blank lines are dropped
    (mirrors awk's numeric-comparison behavior on a malformed field, which
    treats it as 0 and therefore prunes it out under any sane cutoff)."""
    out: list[int] = []
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(int(line))
            except ValueError:
                continue
    except Exception:
        pass
    return out


def _compose_workflow_offer(in_window_count: int) -> "_envelope.Message":
    """Pure message composer, routed through `_message_envelope.compose`
    (docs/plans/2026-08-02-guard-message-character-cap.md § C6). The
    relocated explanation of what a background Workflow buys and when
    hand-dispatch is still the right call moves to `_WIKI_ANCHOR` -- see
    state/relocations/guard-message-cap/nudge-multiwave-workflow.py.md --
    dropped from the message, not from the system."""
    prose = (
        f"[workflow offer] {in_window_count} hand-dispatched executors in a "
        "row - a Workflow survives compaction, encodes wave gates. Ad-hoc "
        "is fine; your call."
    )
    return _envelope.compose(prose, anchor=_WIKI_ANCHOR)


def _compose_workflow_offer_message(in_window_count: int) -> str:
    """Back-compat shim for `message_measurement_harness.
    _adapt_nudge_multiwave_workflow`, which calls this exact name and
    measures its raw string return directly (not via the shared harness's
    `_capture_envelope_messages` context) -- so it must keep returning a
    plain string. Returns `_compose_workflow_offer(...).prose`: the
    counted diagnosis only, the same value the ceiling/median/p90 legs
    measure. `main()` calls `_compose_workflow_offer` directly and emits
    the fuller Message (prose + anchor) via `_message_envelope.emit`."""
    return _compose_workflow_offer(in_window_count).prose


def main() -> int:
    raw = sys.stdin.read()
    if not raw:
        return 0

    # Extract tool_name (top-level field). Bash oracle does a raw-substring
    # presence check before extraction; json.loads subsumes that (a missing
    # key after a successful parse is the same "absent" outcome).
    try:
        payload = json.loads(raw)
    except Exception:
        return 0
    if not isinstance(payload, dict):
        return 0

    tool_name = payload.get("tool_name")
    if not isinstance(tool_name, str) or not tool_name:
        return 0

    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return 0
    if not _SESSION_ID_RE.match(session_id):
        return 0
    # Every path below persists this hook's dedup state under
    # `<hub>/<session_id>/`, so a session id the hub gate will not accept has
    # no place to dedup from and must not mint a directory trying (see
    # `_session_hub`). Skipping outright is the honest behaviour: the nudge
    # is advisory, and only a benchmark or probe supplies such an id.
    if not session_id_is_real(session_id):
        return 0

    git_root = _git_root()
    if not git_root:
        return 0

    # Rooted at the git COMMON dir (see `_resolve_git_common_dir`'s
    # docstring), never `<git_root>/.git` -- that path is a FILE in a
    # worktree, so the pre-fix join silently never persisted this session's
    # sentinels/log, and the nudges re-fired forever. Fail-open: an
    # unresolvable common dir is treated the same as an unresolvable
    # git_root above -- silent pass, never build a path from "".
    common_dir = _resolve_git_common_dir(git_root)
    if not common_dir:
        return 0

    session_dir = Path(common_dir) / "coordinator-sessions" / session_id

    if tool_name == "Workflow":
        try:
            if ensure_session_dir(session_dir, session_id):
                (session_dir / "workflow-launched").touch()
        except Exception:
            pass
        return 0

    if tool_name != "Agent":
        return 0

    # Condition 1: explicit override.
    if os.environ.get("COORDINATOR_OVERRIDE_MULTIWAVE_WORKFLOW", "") == "1":
        return 0

    # Condition 2: subagent-originated dispatch (payload carries agent_id
    # ANYWHERE in the raw text) -> this is an executor dispatching further,
    # not the main EM. Never nudge. Raw-substring check for byte-fidelity
    # with the bash oracle (not a parsed top-level key lookup).
    if '"agent_id"' in raw:
        return 0

    # Condition 3: extract subagent_type from tool_input; only fire for
    # write-capable executors/workers.
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    subagent_type = tool_input.get("subagent_type")
    if not isinstance(subagent_type, str) or not subagent_type:
        return 0

    subagent_type_lc = subagent_type.lower()
    if not _is_write_capable(subagent_type_lc):
        return 0

    # Condition 4: no Workflow launched this session.
    if (session_dir / "workflow-launched").is_file():
        return 0

    # Condition 5: fire at most once per session.
    nudged_sentinel = session_dir / "multiwave-workflow-nudged"
    if nudged_sentinel.is_file():
        return 0

    # Condition 6: burst threshold. Only a run of N qualifying dispatches
    # within the last W seconds trips the nudge -- a single hand-dispatch
    # (or a review->integrate pair) is legitimate and must not fire.
    try:
        threshold = int(os.environ.get("COORDINATOR_MULTIWAVE_NUDGE_THRESHOLD", "4"))
    except ValueError:
        threshold = 4
    try:
        window_secs = int(os.environ.get("COORDINATOR_MULTIWAVE_NUDGE_WINDOW_SECS", "30"))
    except ValueError:
        window_secs = 30
    dispatch_log = session_dir / "multiwave-dispatch-log"

    try:
        ensure_session_dir(session_dir, session_id)
    except Exception:
        pass

    now = int(time.time())
    try:
        with dispatch_log.open("a", encoding="utf-8") as fh:
            fh.write(f"{now}\n")
    except Exception:
        pass

    # Prune to the rolling window: filtered read into a temp file, then
    # atomic replace (os.replace is atomic on both POSIX and Windows NTFS/
    # ReFS, mirroring the bash oracle's filtered-read-then-mv approach). A
    # concurrent hook invocation racing this prune is benign advisory-tooling
    # drift, not a correctness hazard -- no locking, same as the bash oracle.
    cutoff = now - window_secs
    lines = _read_int_lines(dispatch_log)
    pruned = [n for n in lines if n >= cutoff]
    tmp_path = dispatch_log.with_name(f"{dispatch_log.name}.tmp.{os.getpid()}")
    try:
        tmp_path.write_text("".join(f"{n}\n" for n in pruned), encoding="utf-8")
        os.replace(tmp_path, dispatch_log)
    except Exception:
        try:
            tmp_path.unlink()
        except Exception:
            pass

    in_window_count = len(pruned)

    if in_window_count < threshold:
        return 0

    try:
        nudged_sentinel.touch()
    except Exception:
        pass

    # Fire, routed through the shared envelope seam (see
    # docs/plans/2026-08-02-guard-message-character-cap.md § C6).
    message = _compose_workflow_offer(in_window_count)
    _envelope.emit(message, _envelope.CHANNEL_ADDITIONAL_CONTEXT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
