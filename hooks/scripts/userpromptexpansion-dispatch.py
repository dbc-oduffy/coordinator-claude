"""UserPromptExpansion fan-in dispatcher -- the four typed-verb legs, one
interpreter, matched legs run CONCURRENTLY.

Fold set (REGISTRY rows -- leg id, script filename, verb set):
  - pickup-autofire        `_PICKUP_COMMAND_NAMES | _BATON_GRAB_COMMAND_NAMES`
  - mise-autofire          `_MISE_COMMAND_NAMES`
  - handoff-segment-inject `_HANDOFF_COMMAND_NAMES`
  - group-em-autofire      `_GROUP_EM_COMMAND_NAMES`
The verb sets are declared here as named constants; a test pins each to EQUAL
its leg's own constant, so a verb renamed in a leg fails loudly rather than
silently unwiring it.

Typed-verb-only: `UserPromptExpansion` fires only when the operator TYPES a
slash command; a model-invoked `Skill` call never reaches it. That is the PM
gate `group-em-autofire.py` depends on (it claims a group-em nomination), so
it may live in this fan-in and nowhere a model `Skill` call can reach.

Verb disjointness: `_GROUP_EM_COMMAND_NAMES` shares no verb with any other
leg, so the mutating group-em leg always runs ALONE. Its in-process forwarder
call rewrites `sys.path`/`sys.argv` and redirects stdout process-wide, which is
only safe with no sibling thread running beside it. Overlapping `pickup` and
`mise-en-place` (both read-mostly, both match `mise-en-place`) may share a run.

Each matched leg is imported lazily by path and run through its own
`compute_context(stdin_text) -> str | None`. A leg lacking that entry point (or
raising, or running past the deadline) is skipped, fail-open for that leg
only. Matched legs run on daemon threads under one shared deadline --
daemon, not `ThreadPoolExecutor`, so a hung leg cannot block interpreter exit
through the stdlib's atexit pool join.

Timeouts: internal deadline 40 s (`_INTERNAL_DEADLINE_SECONDS`), strictly
below the 45 s hooks.json registration timeout.

Emission: ONE `hookSpecificOutput` envelope (`hookEventName`
`UserPromptExpansion`), leg contexts joined in REGISTRY order with a blank
line; no stdout when nothing matched or nothing was said. The envelope and the
skip breadcrumb go through `sys.__stdout__`/`sys.__stderr__`: a group-em leg
still running past the deadline holds `sys.stdout`/`sys.stderr` swapped to its
capture, and a write through the swapped name would be lost.

Negative spec: never add a leg reachable from PreToolUse(Skill); never add a
non-disjoint verb to group-em.

Contract:
  stdin   -- UserPromptExpansion JSON (command_name, command_args, ...)
  stdout  -- one envelope, or nothing
  exit 0  -- always.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, FrozenSet, List, Optional, Tuple

_HOOKS_DIR = Path(__file__).resolve().parent
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

from _skill_invocation import context_envelope  # noqa: E402

# Strictly below the 45 s registration timeout.
_INTERNAL_DEADLINE_SECONDS = 40.0

_PICKUP_AUTOFIRE_VERBS: FrozenSet[str] = frozenset({"pickup", "mise-en-place"})
_MISE_AUTOFIRE_VERBS: FrozenSet[str] = frozenset({"mise-en-place"})
_HANDOFF_SEGMENT_INJECT_VERBS: FrozenSet[str] = frozenset({"handoff"})
_GROUP_EM_AUTOFIRE_VERBS: FrozenSet[str] = frozenset({"group-em"})


@dataclass(frozen=True)
class UpeLeg:
    leg_id: str
    module_key: str
    filename: str
    verbs: FrozenSet[str]


REGISTRY: Tuple[UpeLeg, ...] = (
    UpeLeg("pickup-autofire", "pickup_autofire", "pickup-autofire.py",
           _PICKUP_AUTOFIRE_VERBS),
    UpeLeg("mise-autofire", "mise_autofire", "mise-autofire.py",
           _MISE_AUTOFIRE_VERBS),
    UpeLeg("handoff-segment-inject", "handoff_segment_inject",
           "handoff-segment-inject.py", _HANDOFF_SEGMENT_INJECT_VERBS),
    UpeLeg("group-em-autofire", "group_em_autofire", "group-em-autofire.py",
           _GROUP_EM_AUTOFIRE_VERBS),
)


def _normalize_command_name(name: Any) -> str:
    """Bare verb: any `<namespace>:` prefix and leading `/` stripped."""
    if not isinstance(name, str):
        return ""
    return name.lstrip("/").rsplit(":", 1)[-1]


def _import_leg(leg: UpeLeg) -> Any:
    if leg.module_key in sys.modules:
        return sys.modules[leg.module_key]
    spec = importlib.util.spec_from_file_location(
        leg.module_key, str(_HOOKS_DIR / leg.filename)
    )
    if spec is None or spec.loader is None:
        raise ImportError(leg.filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[leg.module_key] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop(leg.module_key, None)
        raise
    return mod


def _run_leg(leg: UpeLeg, stdin_text: str) -> Optional[str]:
    """Run one leg's `compute_context`; a missing entry point raises
    AttributeError, which skips only this leg."""
    mod = _import_leg(leg)
    compute_context = getattr(mod, "compute_context")
    raw = compute_context(stdin_text)
    if not raw or not raw.strip():
        return None
    return raw.strip()


def _run_legs_concurrently(
    matched: List[UpeLeg], stdin_text: str
) -> Tuple[dict, List[str]]:
    """Run every matched leg on its own daemon thread under one deadline.
    Returns `({leg_id: text_or_None}, [skipped descriptions])`."""
    results: dict = {}
    failed: List[str] = []

    def _runner(leg: UpeLeg) -> None:
        try:
            results[leg.leg_id] = _run_leg(leg, stdin_text)
        except BaseException:
            failed.append(leg.leg_id)

    threads = [
        (leg, threading.Thread(target=_runner, args=(leg,),
                               name="upe-leg-" + leg.leg_id, daemon=True))
        for leg in matched
    ]
    for _leg, thread in threads:
        thread.start()

    deadline = time.monotonic() + _INTERNAL_DEADLINE_SECONDS
    for _leg, thread in threads:
        thread.join(max(0.0, deadline - time.monotonic()))

    skipped = list(failed)
    for leg, thread in threads:
        if thread.is_alive():
            skipped.append(leg.leg_id + " (past internal deadline)")
    return results, skipped


def _write_stdout(text: str) -> None:
    out = sys.__stdout__
    buf = getattr(out, "buffer", None)
    if buf is not None:
        buf.write(text.encode("utf-8"))
        buf.flush()
    else:
        out.write(text)
        out.flush()


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw else {}
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    verb = _normalize_command_name(payload.get("command_name"))
    matched = [leg for leg in REGISTRY if verb in leg.verbs]
    if not matched:
        return 0

    results, skipped = _run_legs_concurrently(matched, raw)

    if skipped:
        try:
            sys.__stderr__.write(
                "[userpromptexpansion-dispatch] leg(s) skipped (fail-open for "
                "those only): " + ", ".join(skipped) + "\n"
            )
        except Exception:
            pass

    parts = [results[leg.leg_id] for leg in matched if results.get(leg.leg_id)]
    if not parts:
        return 0

    try:
        _write_stdout(context_envelope("UserPromptExpansion", "\n\n".join(parts)) + "\n")
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
