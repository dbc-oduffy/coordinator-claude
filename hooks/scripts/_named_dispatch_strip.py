"""_named_dispatch_strip.py -- shared library, NOT a registered hook.

Single-emitter fix (2026-07-31, follow-up to the worktree/mode-elevation
fold-in): `guard-named-dispatch-tool-restriction.py` used to independently
build its own `hookSpecificOutput.updatedInput` (a `name` key strip) on the
`Agent` matcher, racing `enforce-agent-dispatch-mode.py`'s own single merged
`updatedInput` emission on the SAME matcher -- Claude Code runs same-event
PreToolUse hooks in parallel with undefined completion order, and
`updatedInput` is last-writer-wins, so on an Agent dispatch carrying BOTH a
`name` key on a restricted subagent_type AND a mode-elevation/sidecar/
role-framing/worktree-isolation trigger, exactly one hook's rewrite silently
clobbered the other's. This is the same parallel-hook clobber class
`_worktree_isolation_strip.py` closed for the worktree/mode-elevation pair;
this module closes it for the `name`-strip too, using that fix as its
precedent shape.

Fix shape: the named-dispatch-strip COMPUTATION (this module) is now shared,
pure, and side-effect-free (no stdout, no sys.exit). The only caller that may
EMIT `updatedInput` for `Agent` is `enforce-agent-dispatch-mode.py` -- it
folds this module's result into its own single merged `updatedInput` (mode
elevation + sidecar + contract-blocks + role-framing + worktree-strip +
named-dispatch-strip, all layered onto ONE `merged` dict, ONE emission site).

`guard-named-dispatch-tool-restriction.py` still imports and calls this
module for its OWN standalone `main()` (its dedicated test suite,
`coordinator/tests/test_guard_named_dispatch_tool_restriction.py`, drives
that script directly via subprocess and must keep passing unmodified in
intent), but it is deregistered from `hooks.json`'s `Agent` matcher entirely
-- `Agent` was its only matcher, so once its computation is folded into
`enforce-agent-dispatch-mode.py`'s single-emitter path there is no live
matcher left where it is the sole emitter (unlike
`_worktree_isolation_strip.py`'s `strip-worktree-isolation.py` caller, which
stays registered on `Workflow` because `Workflow`'s `tool_input` has no
`prompt` key and cannot fold into the Agent-only merge path). Neither caller
re-implements the restricted-type / unknown-key / deny logic -- both import
`compute_named_dispatch_result` from here.

Only `Explore` and `Plan` are in scope, and only when `name` is present on
that dispatch's `tool_input` -- every other case returns `None` (nothing to
do), same shape as `_worktree_isolation_strip.compute_strip`.

Fail-closed for THIS module's own detection failure (not the caller's):
once `tool_input` is established as a named Explore/Plan dispatch, an
unrecognised `tool_input` key (outside `_KNOWN_AGENT_TOOL_INPUT_KEYS`) or any
other internal failure while constructing the rewrite returns a `"deny"`
result rather than `None` -- `None` is reserved for genuine "nothing to do"
cases, never for "this module failed to decide". See
`guard-named-dispatch-tool-restriction.py`'s original module docstring
(preserved there) for the full FAIL-CLOSED rationale; this module implements
that same contract, just as a pure function instead of a stdout emitter.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

from _message_envelope import compose, render  # noqa: E402

#: Wiki section carrying the relocated full rationale for the `strip`
#: offer (why naming Explore/Plan loses its read-only restriction, system
#: prompt, and omitClaudeMd; the ~31k-token cost breakdown) -- see this
#: module's own relocation fragment at state/relocations/guard-message-cap/
#: enforce-agent-dispatch-mode.py.md (the site is measured via
#: `enforce-agent-dispatch-mode.py`'s imported `_compute_named_dispatch`
#: alias, per docs/plans/2026-08-02-guard-message-character-cap.md § C6).
_WIKI_ANCHOR = "coordinator/docs/wiki/guard-message-concision.md#named-dispatch-strip"

_RESTRICTED_SUBAGENT_TYPES = ("Explore", "Plan")

# The complete set of keys this module knows how to carry forward into a
# stripped `tool_input`. A key outside this set is a schema drift neither
# caller has been taught about -- see the fail-closed discussion above.
_KNOWN_AGENT_TOOL_INPUT_KEYS = frozenset(
    {
        "subagent_type",
        "prompt",
        "name",
        "description",
        "run_in_background",
        "isolation",
        "model",
    }
)


def _compose_offer_message(subagent_type: str) -> str:
    """Pure composer for the `strip` offer (docs/plans/2026-08-02-guard-
    message-character-cap.md § C6). The full rationale (read-only
    restriction, system prompt, and omitClaudeMd loss; the ~31k-token cost
    breakdown) relocates to `_WIKI_ANCHOR` -- see this module's own
    relocation fragment. Returns the flattened `render()` text (not a
    `Message`) since both callers (`enforce-agent-dispatch-mode.py`,
    `guard-named-dispatch-tool-restriction.py`) treat this as a plain
    `additionalContext` string, not a `Message` they render themselves."""
    prose = (
        "[named-dispatch guard] `name:` stripped from {} -- naming "
        "Explore/Plan loses read-only + costs ~31k tokens; proceeds "
        "unnamed. Use a non-plugin subagent_type for teammate messaging."
    ).format(subagent_type)
    return render(compose(prose, anchor=_WIKI_ANCHOR))

_DENY_MESSAGE = (
    "[named-dispatch guard] denied: this dispatch names {subagent_type} "
    "with `name:` set, and the guard could not safely construct a "
    "restricted rewrite for it (unrecognised tool_input key or an internal "
    "failure). Naming Explore or Plan discards its read-only tool "
    "restriction (tools falls back to \"*\"), so this guard fails closed "
    "rather than risk silently allowing that through. Retry the dispatch "
    "without `name:` -- Explore/Plan are read-only and cheaper unnamed. If "
    "you genuinely need teammate messaging, pick a subagent_type whose "
    "definition survives naming (non-built-in, non-plugin) instead."
)


def compute_named_dispatch_result(tool_input: dict) -> Optional[tuple[str, Any, str]]:
    """Pure computation, no I/O.

    Returns `None` when there is nothing to do: `subagent_type` is not
    `Explore`/`Plan`, or `name` is absent from `tool_input` -- an ordinary
    pass, not a failure.

    Returns `("strip", merged_tool_input, offer_message)` when this IS a
    named Explore/Plan dispatch and a faithful rewrite could be built --
    `merged_tool_input` is a FULL COPY of `tool_input` with `name` removed
    (never a partial object), and `offer_message` is the fixed advisory
    string every caller surfaces (as `additionalContext` on an allow).

    Returns `("deny", None, deny_message)` when this IS a named Explore/Plan
    dispatch but a complete, faithful rewrite could NOT safely be
    constructed (an unrecognised `tool_input` key, or any other exception
    while building the rewrite) -- fail-closed, per the module's FAIL-CLOSED
    contract above. A caller that only knows how to emit "allow" (never
    "deny") must treat this return value as "deny the whole tool call", not
    silently drop it and fall through to allow.
    """
    subagent_type = tool_input.get("subagent_type")
    if subagent_type not in _RESTRICTED_SUBAGENT_TYPES:
        return None
    if "name" not in tool_input:
        return None

    subagent_type_str = str(subagent_type)
    try:
        unknown_keys = set(tool_input.keys()) - _KNOWN_AGENT_TOOL_INPUT_KEYS
        if unknown_keys:
            return ("deny", None, _DENY_MESSAGE.format(subagent_type=subagent_type_str))
        merged = dict(tool_input)
        del merged["name"]
        return ("strip", merged, _compose_offer_message(subagent_type_str))
    except Exception:
        return ("deny", None, _DENY_MESSAGE.format(subagent_type=subagent_type_str))
