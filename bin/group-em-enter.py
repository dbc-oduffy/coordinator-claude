"""
group-em-enter.py — CLI trampoline over the engine's registered op
"groupem.enter" (`coordinator_core.ops.group_em_enter`).

WHY THIS IS THIN, UNLIKE THE DoE REFERENCE. The DoE-plane script this file
replaces (`coordinator/bin/group-em-enter.py`, archived there) carried a
two-path shape — call the warm engine over `cc_invoke`, or fall back to an
in-tree `--local` assembly — because that CLI runs in a SEPARATE process
from the engine it calls. This file IS the engine: `groupem.enter` already
composes the nomination claim, the candidate roster, the send digest, the
peer-set baseline, the teammate-presence assertion and the watch-liveness
read in one call (`coordinator_core/ops/group_em_enter.py`'s own module
docstring), in-process, with zero spawns. There is no second, slower path
to fall back to here, and no `--local` flag — a fallback that routes
around the one true op is exactly the hazard DoE's `StaleEngineError`
existed to prevent; this file has nothing to fall back to instead.

Cold path — one process, one call. Direct in-process import + call
(`lib` bootstrap, `require_dispatch_engine_on_path`), same trampoline shape
`coordinator/bin/group-em-watch.py` uses.

Exit codes:
  0 — Group-EM claimed (fresh, refreshed, or auto-replacing a dead holder).
  2 — usage error (no session id resolvable).
  5 — Group-EM REFUSED (a live or unaccounted-for incumbent holds it); the
      op's own `nomination` leg carries the refusal detail.

Negative spec: no send, no nudge, no transport — this assembles the digest
and stops, exactly as the DoE reference's own negative spec states. No
re-implementation of the roster/digest/nomination/baseline/teammates/watch
logic — every leg is the engine op's own, read and rendered here, never
recomputed.

Spec backlink: docs/plans/2026-09-18-doe-holds-no-scripts.md, chunk W2-C7.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Optional


def _resolve_op():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    require_dispatch_engine_on_path()
    from coordinator_core.ipc import get_op_handler

    handler = get_op_handler("groupem.enter")
    if handler is None:
        raise ImportError("groupem.enter is not registered")
    return handler


def _render(payload: dict[str, Any]) -> str:
    nomination = payload.get("nomination") or {}
    lines: list[str] = []
    claimed = bool(nomination.get("claimed"))
    lines.append("standing: CLAIMED" if claimed else "standing: REFUSED")
    holder = nomination.get("holder") or "unknown"
    if not claimed:
        incumbent = nomination.get("superseded_incumbent") or {}
        lines.append(
            f"  refused: incumbent {incumbent.get('session_id', 'unknown')} "
            f"[{incumbent.get('live_reason', 'unknown')}] holds this repo's nomination"
        )
        return "\n".join(lines)
    if nomination.get("already_held"):
        lines.append(f"  {holder} already holds Group EM here (refreshed)")
    elif nomination.get("replaced_holder"):
        replaced = nomination["replaced_holder"]
        lines.append(
            f"  claimed by {holder}, replacing dead holder "
            f"{replaced.get('session_id')} (pid not running)"
        )
    else:
        lines.append(f"  nominated {holder} as Group EM")

    roster = payload.get("roster") or []
    considered = payload.get("roster_considered")
    candidates = sum(1 for peer in roster if peer.get("candidate"))
    considered_note = f" of {considered} considered" if considered is not None else ""
    lines.append(f"roster: {len(roster)} peer(s){considered_note}, {candidates} candidate(s)")
    for peer in roster:
        mark = "*" if peer.get("candidate") else " "
        lines.append(
            f"  {mark} {peer.get('session_id')}  {peer.get('state')}  "
            f"({peer.get('reason')}, via {peer.get('source')})"
        )

    digest = payload.get("digest") or {}
    entries = digest.get("entries") or []
    suppressed = digest.get("suppressed") or []
    truncated = ", TRUNCATED" if digest.get("truncated") else ""
    lines.append(f"digest: {len(entries)} entry(ies), {len(suppressed)} suppressed{truncated}")
    for entry in entries:
        lines.append(f"  - {entry.get('session_id')}  {entry.get('trigger')}")
    for held in suppressed:
        lines.append(f"  x {held.get('session_id')}  {held.get('why')}")

    teammates = payload.get("teammates")
    if teammates is not None:
        lines.append(f"teammates: {teammates}")
    watch_liveness = payload.get("watch_liveness")
    if watch_liveness is not None:
        lines.append(f"watch: {watch_liveness.get('verdict')}")

    lines.append(
        "gates: gate1/gate2 unset — declare both in prose per send; never loop over entries"
    )
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="group-em-enter",
        description="Assemble Group EM mode via the engine's groupem.enter op: claim the "
        "nomination, build the candidate roster and the send digest. Selects and throttles; "
        "never sends.",
    )
    parser.add_argument("--repo", help="repo root; default cwd")
    parser.add_argument("--session-id", help="entering session; default $CLAUDE_SESSION_ID")
    parser.add_argument("--json", action="store_true", help="emit the payload as JSON")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    repo_root = args.repo or os.getcwd()
    session_id = args.session_id or os.environ.get("CLAUDE_SESSION_ID")
    if not session_id:
        print(
            "group-em-enter: no session id (pass --session-id or set CLAUDE_SESSION_ID)",
            file=sys.stderr,
        )
        return 2

    try:
        handler = _resolve_op()
    except Exception as exc:  # noqa: BLE001
        print(f"group-em-enter: engine unresolvable — {exc}", file=sys.stderr)
        return 2

    payload = handler({"repo_root": repo_root, "caller_session_id": session_id})

    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(_render(payload))

    nomination = payload.get("nomination") or {}
    return 0 if nomination.get("claimed") else 5


if __name__ == "__main__":
    sys.exit(main())
