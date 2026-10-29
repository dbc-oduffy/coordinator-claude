"""Schema-agnostic ratchet primitives -- load-baseline / refuse-to-loosen /
diff-shaped reporting -- extracted so `test_hook_message_budget.py` (C4)
does not duplicate `test_agent_body_envelope.py`'s `_over_limit` /
`_unbaselined_over` / `_regenerate` shape a third time.

Purpose: `test_boot_description_envelope.py` and `test_agent_body_envelope.py`
each independently grew a shrink-only, refuse-to-loosen ratchet against a
JSON baseline (`{total_bytes, over_limit}` and
`{agents:{limit}, fleet:{limit}}, NEW_AGENT_CAP` respectively). C4's own
chunk brief names this drift explicitly: citing only one of the two as
precedent would produce a THIRD bespoke variant. This module is the shared
core, operating on **plain `{name: measured}` / `{name: {"limit": ...}}`
dicts** rather than assuming either shipped test's exact top-level JSON
shape -- so either existing envelope test COULD adopt it later without this
module dictating their file's own schema.

Negative-spec: this module does NOT know what a "hook" or an "agent" is, and
never reads a baseline JSON file itself -- callers own their own file I/O
and their own baseline's top-level shape (`hooks`/`agents`/`fleet`/whatever
key names they choose). It only knows how to compare a measured-size dict
against a limits dict.

Ships beside the `_skill_weight_admission` hook, which imports it: percolate
does not publish `coordinator/tests/`, so this module must live under
`coordinator/hooks/scripts/`.

Spec: docs/plans/2026-08-02-guard-message-character-cap.md, chunk C4 (see
also chunk C3's body, which names this same extraction). Out of scope: this
plan does not migrate `test_boot_description_envelope.py` or
`test_agent_body_envelope.py` onto this module -- see the plan's "Out of
scope" section.
"""

from __future__ import annotations

from typing import Optional


def over_limit(sizes: dict[str, int], limits: dict[str, dict]) -> dict[str, tuple[int, int]]:
    """An entry in `sizes` with no corresponding `limits` entry is silently
    excluded -- that is `unbaselined_over`'s question, not this one."""
    return {
        name: (size, limits[name]["limit"])
        for name, size in sizes.items()
        if name in limits and size > limits[name]["limit"]
    }


def unbaselined_over(sizes: dict[str, int], limits: dict[str, dict], cap: int) -> dict[str, int]:
    """name -> measured for every entry present in `sizes` but absent from
    `limits`, whose measured size exceeds `cap`. This is the "a new item
    arrives capped" invariant (`NEW_AGENT_CAP` / `NEW_HOOK_CAP`)."""
    return {name: size for name, size in sizes.items() if name not in limits and size > cap}


def fleet_over(total: int, fleet_limit: int) -> bool:
    return total > fleet_limit


def over_floor(
    limits: dict[str, dict], *, limit_key: str = "limit", floor_key: str = "ratchet_floor"
) -> dict[str, tuple[int, int]]:
    """The floor is the lowest limit ever recorded for an entry. A limit with
    no floor raises rather than being skipped: that shape means malformed or
    tampered (floor deleted), and silently passing it would let a hand-raised
    limit look like a legitimate regeneration write."""
    over: dict[str, tuple[int, int]] = {}
    for name, entry in limits.items():
        limit = entry.get(limit_key)
        if limit is None:
            continue
        floor = entry.get(floor_key)
        if floor is None:
            raise AssertionError(
                f"entry {name!r} has a `{limit_key}` ({limit}) but no `{floor_key}` -- "
                f"baseline is malformed (or `{floor_key}` was deleted)."
            )
        if limit > floor:
            over[name] = (limit, floor)
    return over


#: Matched by suffix so a caller's own naming is covered without this module
#: learning that caller's schema. `measured` is deliberately absent -- a
#: measurement is supposed to move both directions, and flagging it would
#: train callers to suppress this check as noisy.
_BUDGET_KEY_SUFFIXES = ("limit", "ratchet_floor", "total_bytes", "cap")

OI_BANNER = (
    "\n"
    "  ┌──────────────────────────────────────────────────────────────────┐\n"
    "  │  OI. YOU ARE RAISING THE LIMIT.                                  │\n"
    "  └──────────────────────────────────────────────────────────────────┘\n"
    "\n"
    "  Every Claude who widened one of these numbers believed their case\n"
    "  was the special one. That belief is not evidence, and it is the\n"
    "  most common thing in these baselines' history.\n"
    "\n"
    "  You are almost certainly not the exception. The default is CUT:\n"
    "  restatement, rationale and worked examples belong in the wiki; the\n"
    "  measured surface carries the rule alone. Pay for what you added by\n"
    "  removing what you did not need, in the same edit.\n"
    "\n"
    "  docs/wiki/coordinator-tripwires/your-case-is-not-the-special-one.md\n"
)

#: `authorized_by` is the load-bearing field -- every other field can be
#: satisfied by the person who wants the raise.
RAISE_JUSTIFICATION_FIELDS = ("rule", "why_not_shorter", "authorized_by")


def _is_budget_key(key: str) -> bool:
    return any(key == suffix or key.endswith("_" + suffix) for suffix in _BUDGET_KEY_SUFFIXES)


def raised_against(current, committed, _path: tuple = ()) -> dict:
    """The only check in the family with a memory -- every other assertion
    reads one revision of a baseline, and a raise is invisible within one
    revision. `committed` of `None` (no prior revision) yields `{}`: no prior
    state means no finding, never "proven clean"."""
    if not isinstance(current, dict) or not isinstance(committed, dict):
        return {}
    found: dict = {}
    moves: list[str] = []
    for key, cur_val in current.items():
        old_val = committed.get(key)
        if isinstance(cur_val, bool) or isinstance(old_val, bool):
            continue
        if isinstance(cur_val, int) and isinstance(old_val, int):
            if _is_budget_key(key) and cur_val > old_val:
                moves.append(f"{key} {old_val} -> {cur_val} (+{cur_val - old_val})")
        elif isinstance(cur_val, dict):
            found.update(raised_against(cur_val, old_val, _path + (key,)))
    if moves:
        found[_path] = moves
    return found


def entry_at(baseline: dict, path: tuple) -> dict:
    """Takes `path` as a tuple of keys, never a joined-and-resplit string --
    entries in these baselines are named after files, and a dotted filename
    segment resolves against nothing. An unresolvable path yields `{}`, which
    carries no justification, so an unlocatable raise still fails closed."""
    node = baseline
    for part in path:
        if not isinstance(node, dict) or part not in node:
            return {}
        node = node[part]
    return node if isinstance(node, dict) else {}


def path_label(path: tuple) -> str:
    return ".".join(path) if path else "<root>"


def raise_justification_defects(entry: dict) -> list[str]:
    block = entry.get("raised") if isinstance(entry, dict) else None
    if not isinstance(block, dict):
        return ["no `raised:` block"]
    return [
        f"`raised.{field}` missing or empty"
        for field in RAISE_JUSTIFICATION_FIELDS
        if not str(block.get(field) or "").strip()
    ]


def raise_remedy_text() -> str:
    return (
        "\n\n  A budget that genuinely cannot be met is not blocked, it is "
        "argued. Add to\n  the entry:\n\n"
        '      "raised": {\n'
        '        "rule": "<the rule that could not be stated shorter>",\n'
        '        "why_not_shorter": "<what you cut first, and what broke>",\n'
        '        "authorized_by": "<who agreed — not you>"\n'
        "      }\n\n"
        "  `authorized_by` is the point. If you cannot name someone, you are "
        "not raising\n  a budget; you are approving your own diff."
    )


def missing_reason(limits: dict[str, dict]) -> list[str]:
    return sorted(name for name, entry in limits.items() if not str(entry.get("reason", "")).strip())


def compute_regenerated_limit(
    measured: int, prior_limit: Optional[int], *, headroom: int
) -> tuple[Optional[int], Optional[str]]:
    """`new_limit` is `None` iff regeneration is refused (measured now
    exceeds the previously recorded limit) -- only a deliberate hand-edit,
    never `--regenerate`, may raise the limit."""
    if prior_limit is not None and measured > prior_limit:
        return None, (
            f"measured {measured} > recorded limit {prior_limit} -- "
            "regeneration will not raise a limit. Cut the message, or "
            "hand-edit the baseline in the same commit so the growth is "
            "reviewed."
        )
    proposed = measured + headroom
    if prior_limit is not None:
        proposed = min(proposed, prior_limit)
    return proposed, None


def compute_regenerated_limit_and_floor(
    measured: int,
    prior_limit: Optional[int],
    prior_floor: Optional[int],
    *,
    headroom: int,
) -> tuple[Optional[int], Optional[int], Optional[str]]:
    """A prior limit with no prior floor is refused rather than treated as a
    new entry: taking the new-entry path would derive a fresh floor and
    launder a hand-raised limit into a self-consistent, indistinguishable-
    from-honest write. The floor never rises -- regeneration may only lower
    it or leave it, mirroring the scalar refusal above."""
    if prior_limit is not None and prior_floor is None:
        return None, None, (
            f"has a `limit` ({prior_limit}) but no `ratchet_floor` -- baseline entry is "
            "malformed (or `ratchet_floor` was deleted). Regeneration will not "
            "re-baseline a floor for an existing entry; restore `ratchet_floor` by hand "
            "so the value is reviewed."
        )
    proposed, reason = compute_regenerated_limit(measured, prior_limit, headroom=headroom)
    if reason is not None:
        return None, None, reason
    floor = proposed if prior_floor is None else min(prior_floor, proposed)
    return proposed, floor, None
