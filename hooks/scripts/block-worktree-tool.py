#!/usr/bin/env python3
"""PreToolUse hook (matcher: `EnterWorktree|ExitWorktree`): structurally bans
the harness worktree-lifecycle tools from every session in this fleet.

Why this exists
----------------
Worktrees degrade on Windows (the primary machine and audience for this
fleet — see `CLAUDE.md § Runtime conventions`) and do not scale to the
concurrent-agent shape this coordinator system runs: multiple sessions
sharing one working tree with scoped, disjoint file paths is the load-
bearing pattern (`docs/wiki/fanout-shape-scoped-parallel-not-sequential-not-
worktree.md` in spirit — see also this repo's own memory note "Fan-out
shape: scoped parallel edit-only + EM-serial-commit"). A worktree per
dispatched agent reintroduces exactly the sequential-grind /
worktree-per-item shape that pattern exists to rule out.

Block predicate
----------------
DENY `EnterWorktree` unconditionally (subject to the sentinel override
below). ALLOW `ExitWorktree` unconditionally — leaving a worktree is
cleanup, never the thing this guard exists to stop; blocking an exit path
would trap an agent that is already inside a worktree (from before this
guard existed, or from an override-gated entry) with no way out.

Override — repo-root sentinel file ONLY, no env-var leg
---------------------------------------------------------
`<repo-root>/.coordinator-override-worktree-guard` suppresses the DENY on
`EnterWorktree`. There is deliberately NO environment-variable override
leg, unlike most other guards in this tree. A dispatched subagent can set
an env var on itself before a tool call — an env-var override is
self-defeating for a guard that must bind subagents exactly as it binds
the main session. Precedent: `coordinator_core.bash_guards.
block_subagent_destructive_action` (claude-klabauter) deliberately withholds
an env-var override for the identical reason.

Deny message discipline — the sentinel name is NEVER printed
---------------------------------------------------------------
The deny reason does not name the sentinel file, and does not print any
override incantation. Precedent: `block-home-dir-memo-delivery.py`
withholds its own override env-var name for a documented reason — a deny
message that prints the exact bypass command reads to an eager agent as a
sanctioned next step, not a boundary (see that file's docstring and
`coordinator/hooks/tests/block-destructive-rm.security-review.md:39` for
the incident this pattern exists to prevent: a destructive-rm guard once
printed `export COORDINATOR_ALLOW_RM=1` in its deny text and an agent used
it to destroy a peer's untracked work). The message here instead leads
with the sanctioned alternative (design-as-offers): dispatch into the same
tree with scoped, disjoint paths, and escalate to the EM (PM permission
required) if branch-level isolation is genuinely needed.

Fail-open guards (all exit 0 silent, in order):
  - unreadable/unparseable stdin payload.
  - tool_name is not EnterWorktree or ExitWorktree.
  - sentinel-file override active for EnterWorktree.
  - any exception during git-root resolution or sentinel-file check.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

_HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

from _message_envelope import CHANNEL_DENY, compose, emit  # noqa: E402
from _win_portability import no_console_creationflags  # noqa: E402
try:
    from _git_root_walk import git_root_walk as _git_root_walk  # noqa: E402
except Exception:
    # Defensive fallback -- a deploy missing its sibling _git_root_walk.py
    # must still fail open to the subprocess rung below, not crash on import.
    def _git_root_walk() -> str | None:
        return None

_OVERRIDE_SENTINEL_NAME = ".coordinator-override-worktree-guard"

_WIKI_ANCHOR = "coordinator/docs/wiki/guard-message-concision.md#worktree-ban-rationale"

_DENY_PROSE = (
    "Worktrees banned (break Windows, don't scale to concurrent dispatch). "
    "Use scoped, disjoint paths here; escalate to the EM (PM-approved) for "
    "branch isolation."
)


def _deny_message():
    """Pure composer for the deny message -- kept separate from `main()` so
    it can be measured / unit-exercised without stdin plumbing (mirrors the
    shape used by the other Category-A hooks in this tree)."""
    return compose(_DENY_PROSE, anchor=_WIKI_ANCHOR)


def _git_root() -> "str | None":
    """Repo root as `git rev-parse --show-toplevel` would report it — same idiom as
    block-workflow-unmodeled-agent.py's `_git_root()`: an in-process parent walk
    (`_git_root_walk`) first, no subprocess on the routine path, with the 1s-timeout
    `git rev-parse --show-toplevel` subprocess below kept only as a fallback for the case the
    walk cannot resolve. Any failure (not a git repo, git missing, timeout) returns None and
    the sentinel check is skipped — fails toward "no override", never toward a crash.
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


def _sentinel_override_active() -> bool:
    """Repo-root sentinel FILE override, reachable from inside a live
    session (`touch <repo-root>/.coordinator-override-worktree-guard`) —
    unlike an env var, which a running hook process cannot have injected
    into it mid-session. Fails toward "no override" (returns False) on any
    resolution failure, consistent with every other detection-failure
    guard in this hook tree.
    """
    root = _git_root()
    if not root:
        return False
    try:
        import os

        return os.path.isfile(os.path.join(root, _OVERRIDE_SENTINEL_NAME))
    except Exception:
        return False


def main() -> int:
    try:
        raw = sys.stdin.read()
    except Exception:
        return 0
    if not raw:
        return 0

    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return 0
    except Exception:
        return 0

    tool_name = payload.get("tool_name", "")

    if tool_name == "ExitWorktree":
        return 0

    if tool_name != "EnterWorktree":
        return 0

    try:
        if _sentinel_override_active():
            return 0
    except Exception:
        pass

    emit(_deny_message(), CHANNEL_DENY)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
