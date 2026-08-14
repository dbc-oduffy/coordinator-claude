# guard-not-a-hook-entrypoint -- invoked via the in-process guard runner's
# REAL_GUARD_REGISTRY (coordinator/hooks/scripts/_guard_runner.py), which
# preuse-write-dispatch.py's own hooks.json PreToolUse(Write|Edit|MultiEdit)
# registration calls in-process (C4, docs/plans/2026-08-06-hook-spawn-fan-
# in-finish-and-extend.md). This basename is deliberately never referenced
# literally in hooks.json text -- that IS the mechanism, per D6.
"""PreToolUse hook (matcher: Write|Edit|MultiEdit): Layer 1 leg 1a of the
doctrinal surface weight ratchet -- prices a byte-adding write to a
doctrine surface against its D2 tier, ADVISORY ONLY on the ratio path.

Spec: docs/plans/2026-08-13-doctrinal-surface-weight-ratchet.md, chunk C8
(§ D1, D2, D6, D7).

Why this exists
----------------
D1: a per-commit net is the mechanism that changes authoring behaviour, but
a `PreToolUse` hook fires before any commit exists (D7) -- it sees one tool
call and cannot net across a commit's other edits. Leg 1a's whole job is
pricing: report what THIS edit will cost at commit time and where the cut
must land, before the paragraph is even finished, which is when folding is
still cheap. It never denies on the ratio path (`CHANNEL_ADDITIONAL_
CONTEXT` only) -- the enforcing net is leg 1b, a native git pre-commit hook
(C9b/C9c), out of this module's scope.

C8 shipped the guard body and its registration -- the algorithm skeleton
(five steps below) and the tier-plus-scope SELECTION. C9a (this chunk)
wires the single-edit advisory PRICE (the actual prose naming bytes owed
and the pool they must be paid from) and the 512 B silent floor into step
5. C9b wires per-commit netting, the reasoned-growth marker, the sub-floor
accumulator, and the enforcing leg 1b admission check on top of it --
still out of this module's scope. `is_sanctioned_split` (C10) is NOT
imported here -- split recognition needs two snapshots, which a
`PreToolUse` hook structurally does not have; see C10's own body and this
guard's `ALGORITHM SKETCH` docstring below.

Composes exactly the primitives D6 names -- no new byte-delta primitive,
no second population scoper, no second ratchet, no second tier owner:

  - Byte delta: `_sentinel_write_guard.reconstruct_after` (the engine
    re-export), same contract as `guard-doctrine-changelog-prose.py`.
  - Population scoping: `_doctrine_changelog_prose.surface_of` (added by
    this chunk, D7's resolved design), composing `DOCTRINE_MD_DIRS`
    internally -- reuse, not a second scoper.
  - Tier lookup: `doctrine_surface_tiers.tier_boundaries_for`, the ONE seam
    this guard reads Layer-2 ceiling data through. Never reads
    `coordinator/tests/baselines/doctrine-surface-weight.json` directly and
    never imports anything from `coordinator/tests/` -- either would be an
    undeclared hooks-plane -> test-plane coupling D6 forbids.
  - Verdict channel: `_message_envelope.compose`/`emit`.

Ratio pricing scope -- three surfaces, not five
-------------------------------------------------
`tier_boundaries_for` is called on the STEP 5 (existing-file ratio) path
for `wiki`, `commands`, and `snippets` only. `agents` and `skills` keep
their own existing, unreplaced ratchets (`test_agent_body_envelope.py`,
`test_skill_weight_budget.py`) -- the C2 baseline's own `ceiling_derivation`
field states this directly for both surfaces ("D2's tier table and C8's
ratio guard do not price this surface"), and C3b's own tier-boundary test
(`test_tier_boundaries_match_d2_table`) asserts the D2 table against
wiki/commands/snippets only, not all five. Step 5 is therefore a no-op
(silent allow) for `agents`/`skills`. Step 4 (new-file admission) is NOT
scoped this way -- D3's admission carve-out is priced by admission across
all five surfaces (see `_ADMISSION_PRICED_SURFACES` below).

New-file admission cap (step 4)
---------------------------------
A file with no history has nothing to cut against (D3), so a brand-new
file is priced by admission, not ratio, on ALL five surfaces:
`doctrine_surface_tiers.admission_cap_for(surface)` (C9a's owed export,
closing the C8-inherited duplication of Layer-2 ceiling data into this
guard) -- the wiki's own separate p90-derived `admission_cap` for `wiki`,
falling through to the surface's own `aspirational_ceiling` for every
other surface. This guard never reads either value from the baseline
JSON itself and never hardcodes either as a literal; both are read
through this one export, the same seam `tier_boundaries_for` is.

Advisory pricing and the 512 B floor (C9a, step 5)
----------------------------------------------------
On the ratio path, this leg reports what the edit will cost at commit AND
where the cut must land -- `CHANNEL_ADDITIONAL_CONTEXT` only, NEVER
`CHANNEL_DENY` (this leg has no enforcing authority). The price is C8's
step-5 tier-plus-scope selection's `ratio` times `delta_bytes` -- a
single-edit estimate, not a cross-invocation net; it does not attempt to
track other edits in the same uncommitted change (D7 -- that would be the
session-keyed accumulator D7 explicitly rejects). A single edit's
`delta_bytes` under 512 B (`_SUB_FLOOR_BYTES`) prices nothing: the guard
returns an EMPTY verdict, no `additionalContext` key at all -- silent, not
advisory (D3 carve-out 2). Deferred cross-commit billing of sub-floor
growth is leg 1b's (C9b) `sub_floor_accumulator`, out of this leg's scope.

ALGORITHM SKETCH (PreToolUse, target path resolved to one of the five
surfaces or no-op) -- see C8's own plan body for the canonical numbering:
  1. Resolve target path via `extract_target_path`; no-op if unresolvable
     or `surface_of()` returns `None`.
  2. `before` = on-disk bytes ("" if new); `after = reconstruct_after(...)`.
     No-op if `reconstruct_after` returns `None` (fail-open).
  3. `delta_bytes = len(after.encode()) - len(before.encode())`.
     `delta_bytes <= 0` never prices anything -- allow silently.
  4. New file (`before == ""`) -- admission-cap carve-out: deny if
     `len(after.encode())` exceeds the surface's admission value.
  5. Existing file, `delta_bytes > 0`, surface in
     `_RATIO_PRICED_SURFACES` -- select the D2 tier (2:1/5:1/10:1) and its
     paired `credit_scope` off the file's PRE-EDIT size (C8). Below the
     512 B floor, silent (C9a). At or above it, emit the single-edit
     advisory price naming the pool owed (C9a). C9b still owns per-commit
     netting, the reasoned-growth marker, and the sub-floor accumulator on
     top of this.

Fail-open guards (all exit 0 silent, in order): unreadable/unparseable
stdin payload; tool_name not in the guarded set; no target path in
tool_input; `surface_of()` is `None` (wrong tree/extension, a
`tests`/`fixtures` subdirectory); on-disk read failure for an existing
file; unreconstructable before/after; `delta_bytes <= 0`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

#: coordinator/lib/ holds doctrine_surface_tiers.py -- .../scripts -> hooks
#: -> coordinator -> lib.
_LIB_DIR = str(Path(__file__).resolve().parents[2] / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from _sentinel_write_guard import extract_target_path, reconstruct_after  # noqa: E402
from _doctrine_changelog_prose import surface_of  # noqa: E402
from _message_envelope import (  # noqa: E402
    CHANNEL_ADDITIONAL_CONTEXT,
    CHANNEL_DENY,
    Message,
    compose,
    emit,
)
from doctrine_surface_tiers import admission_cap_for, tier_boundaries_for  # noqa: E402

_GUARDED_TOOLS = ("Write", "Edit", "MultiEdit")

#: Surfaces D2's tier table (and this guard's step 5 ratio path) actually
#: prices. `agents`/`skills` keep their own existing, unreplaced ratchets
#: (see module docstring "Ratio pricing scope -- three surfaces, not
#: five") -- C3b's own `test_tier_boundaries_match_d2_table` asserts the
#: D2 table against exactly these three surfaces.
_RATIO_PRICED_SURFACES = frozenset({"wiki", "commands", "snippets"})

#: All five surfaces are admission-priced on arrival (D3) -- see module
#: docstring "New-file admission cap (step 4)".
_ADMISSION_PRICED_SURFACES = frozenset({"wiki", "commands", "snippets", "agents", "skills"})

#: A single edit's `delta_bytes` under this floor prices nothing -- the
#: guard returns an EMPTY verdict, silently (D3 carve-out 2, C9a). Below
#: the floor is not advisory, it is silent; deferred billing across
#: commits is leg 1b's (C9b) `sub_floor_accumulator`, out of this leg's
#: scope.
_SUB_FLOOR_BYTES = 512

#: Where the rule this guard enforces actually lives.
_RULE_ANCHOR = "the doctrinal surface weight ratchet (§ D1-D3, D6, D7)"


def _select_tier(surface: str, pre_edit_size: int) -> "dict | None":
    """Step 5: select the D2 tier (ratio + `credit_scope`) `pre_edit_size`
    falls into for `surface`, or `None` if `surface` is not one of
    `_RATIO_PRICED_SURFACES`. Half-open band selection on the file's size
    BEFORE the edit, per `tier_boundaries_for`'s own docstring."""
    if surface not in _RATIO_PRICED_SURFACES:
        return None
    boundaries = tier_boundaries_for(surface)
    for band in boundaries["tiers"]:
        if band["max"] is None or pre_edit_size < band["max"]:
            return band
    return boundaries["tiers"][-1]


def _admission_deny_reason(target: str, surface: str, new_size: int, threshold: int) -> str:
    return (
        f"{target} arrives at {new_size} B, over {surface}'s {threshold} B "
        "new-file admission cap (D3). A file with no history has nothing "
        "to cut against -- split it before creating it, or start smaller."
    )


def _admission_deny_message(target: str, surface: str, new_size: int, threshold: int) -> Message:
    return compose(
        _admission_deny_reason(target, surface, new_size, threshold),
        alternative="python3 -m pytest coordinator/tests/test_guard_doctrine_surface_ratio.py -q",
        anchor=_RULE_ANCHOR,
    )


def _advisory_owed_bytes(delta_bytes: int, tier: dict) -> int:
    """Single-edit advisory price (C9a): this edit's `delta_bytes` times
    its selected tier's ratio -- a single-edit estimate, not a
    cross-invocation net (leg 1b, C9b, owns the enforcing per-commit
    net)."""
    return delta_bytes * tier["ratio"]


def _advisory_reason(target: str, surface: str, delta_bytes: int, tier: dict) -> str:
    owed = _advisory_owed_bytes(delta_bytes, tier)
    ratio = tier["ratio"]
    if tier["credit_scope"] == "file":
        pool = f"THIS FILE ({target})"
    else:
        pool = f"`{surface}`"
    return (
        f"+{delta_bytes} B to a {ratio}:1 file -- {owed} B of cuts owed on "
        f"{pool} this commit."
    )


def _advisory_message(target: str, surface: str, delta_bytes: int, tier: dict) -> Message:
    return compose(
        _advisory_reason(target, surface, delta_bytes, tier),
        alternative="python3 -m pytest coordinator/tests/test_guard_doctrine_surface_ratio.py -q",
        anchor=_RULE_ANCHOR,
    )


def evaluate(payload: dict) -> "Message | tuple[Message, str] | None":
    """Pure core: given a parsed PreToolUse payload, returns the
    `(Message, channel)` pair to emit, or `None` for a silent no-op.
    Separable from stdin/envelope plumbing so tests can drive it with
    synthesized payloads directly, same shape as the sibling guard's
    `_advisory_message`/`_deny_message` split."""
    if not isinstance(payload, dict):
        return None
    tool_name = payload.get("tool_name", "")
    if tool_name not in _GUARDED_TOOLS:
        return None

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None

    target_raw = extract_target_path(tool_input)
    if not target_raw:
        return None

    try:
        target = Path(target_raw).resolve()
    except Exception:
        return None

    surface = surface_of(target)
    if surface is None:
        return None

    try:
        before = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else ""
    except Exception:
        return None

    after = reconstruct_after(tool_name, tool_input, before)
    if after is None:
        return None

    delta_bytes = len(after.encode()) - len(before.encode())
    if delta_bytes <= 0:
        return None

    if before == "":
        if surface not in _ADMISSION_PRICED_SURFACES:
            return None
        new_size = len(after.encode())
        threshold = admission_cap_for(surface)
        if new_size > threshold:
            return _admission_deny_message(target_raw, surface, new_size, threshold), CHANNEL_DENY
        return None

    pre_edit_size = len(before.encode())
    tier = _select_tier(surface, pre_edit_size)
    if tier is None:
        return None

    # C9a's 512 B floor: a single edit's delta under the floor prices
    # nothing -- the guard is SILENT, not advisory (D3 carve-out 2).
    # Deferred cross-commit billing of sub-floor growth is leg 1b's
    # (C9b) sub_floor_accumulator, out of this leg's scope.
    if delta_bytes < _SUB_FLOOR_BYTES:
        return None

    # C9a's advisory pricing: names the price and the pool it must be
    # paid from, ADVISORY ONLY -- CHANNEL_ADDITIONAL_CONTEXT, never
    # CHANNEL_DENY. This leg has no enforcing authority; leg 1b (C9b) is
    # the enforcing net.
    return _advisory_message(target_raw, surface, delta_bytes, tier), CHANNEL_ADDITIONAL_CONTEXT


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

    result = evaluate(payload)
    if result is None:
        return 0

    message, channel = result
    emit(message, channel)
    return 0


if __name__ == "__main__":
    sys.exit(main())
