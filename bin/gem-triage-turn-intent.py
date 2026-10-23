"""gem-triage-turn-intent -- the G-EM stamps its triage verdict onto a target EM's turn-intent.json.

Compare-and-swap on turn_ended_at: the merge lands only if the target's turn has not moved on.
Adds triaged_by/outcome/triaged_at/gem_session_id; never touches needs_pm, ask, source or schema.

Exit: 0 merged, 2 usage/unresolvable input, 4 sidecar absent, 5 turn moved on, 6 caller is not the G-EM.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time


def _place_engine_on_path() -> str:
    """Resolve the engine root through the claude-klabauter bin resolver and put it on `sys.path`."""
    lib = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
    if lib not in sys.path:
        sys.path.insert(0, lib)
    from engine_bootstrap import _resolve_engine_root

    root = _resolve_engine_root(os.path.abspath(__file__))
    if not root:
        raise RuntimeError("engine root unresolved")
    if root not in sys.path:
        sys.path.insert(0, root)
    return root


def main(argv: list[str] | None = None) -> int:
    try:
        _place_engine_on_path()
        from coordinator_core.group_em import gem_home as _gem_home
        from coordinator_core.hooks.support import git_common_dir as _git_common_dir
        from coordinator_core.hooks.support import turn_intent as _turn_intent
    except Exception as exc:
        print(f"gem-triage-turn-intent: engine turn_intent helper unresolvable: {exc}", file=sys.stderr)
        return 2

    p = argparse.ArgumentParser(prog="gem-triage-turn-intent", description=__doc__)
    p.add_argument("--session-id", required=True)
    p.add_argument("--repo-root", required=True)
    p.add_argument("--turn-ended-at", required=True)
    p.add_argument("--outcome", required=True, choices=("cleared", "escalated"))
    p.add_argument("--caller-session-id")
    args = p.parse_args(argv)
    if (
        args.session_id in (".", "..")
        or args.session_id.startswith(".")
        or any(sep in args.session_id for sep in ("/", "\\"))
    ):
        print("gem-triage-turn-intent: --session-id must be a bare id (no separators, no leading dot)", file=sys.stderr)
        return 2

    caller = (
        args.caller_session_id
        or os.environ.get("CLAUDE_CODE_SESSION_ID")
        or os.environ.get("CLAUDE_SESSION_ID")
    )
    if not caller:
        print("gem-triage-turn-intent: no caller session id (pass --caller-session-id)", file=sys.stderr)
        return 2
    try:
        expected = float(args.turn_ended_at)
    except ValueError:
        print("gem-triage-turn-intent: --turn-ended-at is not a float", file=sys.stderr)
        return 2

    holder = _gem_home.gem_holder()
    if not holder or str(holder.get("session_id") or "") != caller:
        print("gem-triage-turn-intent: caller is not the live G-EM holder", file=sys.stderr)
        return 6

    common = _git_common_dir.resolve_git_common_dir(args.repo_root)
    if not common:
        print("gem-triage-turn-intent: cannot resolve git-common-dir", file=sys.stderr)
        return 2
    directory = _turn_intent.session_dir(common, args.session_id)
    path = os.path.join(directory, _turn_intent.RECORD_NAME)
    try:
        with open(path, encoding="utf-8") as fh:
            record = json.load(fh)
    except FileNotFoundError:
        print(f"gem-triage-turn-intent: no sidecar at {path}", file=sys.stderr)
        return 4
    except (OSError, ValueError) as exc:
        print(f"gem-triage-turn-intent: unreadable sidecar: {exc}", file=sys.stderr)
        return 4
    if not isinstance(record, dict):
        print("gem-triage-turn-intent: sidecar is not an object", file=sys.stderr)
        return 4

    # Trap: read-compare-replace is not atomic; a turn-end write between here and os.replace is lost.
    current = record.get("turn_ended_at")
    if isinstance(current, bool) or not isinstance(current, (int, float)) or float(current) != expected:
        print("gem-triage-turn-intent: turn_ended_at differs; the turn moved on", file=sys.stderr)
        return 5

    record.update(
        {
            "triaged_by": "gem",
            "outcome": args.outcome,
            "triaged_at": time.time(),
            "gem_session_id": caller,
        }
    )
    if not _turn_intent._atomic_write(directory, _turn_intent.RECORD_NAME, json.dumps(record)):
        print("gem-triage-turn-intent: write failed", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
