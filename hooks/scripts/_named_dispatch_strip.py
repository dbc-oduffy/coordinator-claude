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

Only a dispatch whose `subagent_type` falls in the full 32-type reporting
roster (`_REPORTING_SUBAGENT_TYPES` below) is in scope, and only when `name`
is present on that dispatch's `tool_input` -- every other case returns `None`
(nothing to do), same shape as `_worktree_isolation_strip.compute_strip`.

DR-190 § 2 (2026-09-02): the former Class-1 carve-out (16 types that declare
`SendMessage` in their own `tools:` line, or are named-by-driver per the
namer census, on the theory that naming them does not silently void the
report) is RETIRED. The three-way choice between extending the strip to all
32, adding the delivery clause as text to the handful of definitions lacking
it, or accepting the gap was decided in favour of the strip: it is one
module, uniform, and needs no tool-surface change, where the clause branch
would have needed one (granting `SendMessage` to the 3 Class-3 types that
lack it) and left the clause as text drifting independently across ~32
files. Naming any of these types now strips `name` and proceeds unnamed --
including most of the former Class 1 -- so a driver that named one of them
on purpose for teammate messaging loses that route; DR-190 § 2 weighed
maintenance cost over what it recorded as a use case a driver *might* want.
TWO EXCEPTIONS survive the retirement, both concrete, tested,
currently-exercised dependencies the ruling's cost analysis did not have in
view, discovered executing this change and its follow-up:
`/staff-session`'s six debate personas (`_STAFF_SESSION_NAMING_CARVE_OUT`)
name each other on purpose so the synthesizer can address them, and the
nine deep-research teammate types (`_DEEP_RESEARCH_NAMING_CARVE_OUT`) that
four shipped ceremonies (the repo, web and structured deep-research drivers
under `pipelines/deep-research/`, plus `/notebooklm-research`) dispatch by
name so specialists can wake each other
via `SendMessage`/`ListAgents` -- see docs/plans/2026-09-12-restore-deep-
research-teammate-naming.md. Stripping either would silently break its
ceremony (an unaddressable teammate), not merely cost a maintenance
surface, so both stay carved out; see each constant's own docstring.

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

_WIKI_ANCHOR = "coordinator/docs/wiki/guards/guard-message-concision.md#named-dispatch-strip"

#: CONFINEMENT reason. Naming one of these discards a read-only tool
#: build faithfully fails CLOSED -- see `_DENY_MESSAGE` and the FAIL-CLOSED
_RESTRICTED_SUBAGENT_TYPES = ("Explore", "Plan")

#: DELIVERY reason. These are the agent definitions that report by returning
#: FORMER THREE-CLASS TAXONOMY, COLLAPSED (DR-190 § 2, 2026-09-02). Until
#: NEGATIVE SPEC: this tuple is not a hand-curated taste list. It is the
#: named-on-purpose debate personas (`_STAFF_SESSION_NAMING_CARVE_OUT`
_REPORTING_SUBAGENT_TYPES = (
    "coordinator:apm",
    "coordinator:atlas-clarity-reviewer",
    "coordinator:blitz-em",
    "coordinator:code-reviewer",
    "coordinator:code-reviewer-weekly",
    "coordinator:coverage-auditor",
    "coordinator:dep-cve-auditor",
    "coordinator:doc-link-checker",
    "coordinator:docs-checker",
    "coordinator:enricher",
    "coordinator:executor",
    "coordinator:external-pattern-checker",
    "coordinator:falsifier-integrity-reviewer",
    "coordinator:overengineering-reviewer",
    "coordinator:plan-author",
    "coordinator:parallel-review-synthesizer",
    "coordinator:plan-coverage-checker",
    "coordinator:premise-checker",
    "coordinator:prior-art-checker",
    "coordinator:security-audit-worker",
    "coordinator:subtractive-adjudicator",
    "coordinator:test-evidence-parser",
    "coordinator:test-runner",
    "coordinator:workflow-maker",
)

#: CARVE-OUT, not an oversight. `/staff-session`'s debate ceremony
#: naming dependency found) is folded into `_REPORTING_SUBAGENT_TYPES` above
_STAFF_SESSION_NAMING_CARVE_OUT = (
    "coordinator:staff-eng",
    "coordinator:eng-director",
    "coordinator:staff-ux",
    "coordinator:staff-data-sci",
    "coordinator:senior-front-end",
    "coordinator:vp-product",
)

#: CARVE-OUT, not an oversight. Four shipped deep-research ceremonies
#: NEGATIVE SPEC: membership is earned by a driver dispatching that type BY
#: `_STAFF_SESSION_NAMING_CARVE_OUT` (a different ceremony's exemption). A
#: `_REPORTING_SUBAGENT_TYPES`.
_DEEP_RESEARCH_NAMING_CARVE_OUT = (
    "coordinator:repo-scout",
    "coordinator:repo-specialist",
    "coordinator:research-scout",
    "coordinator:research-specialist",
    "coordinator:research-synthesizer",
    "coordinator:research-sweep",
    "coordinator:research-worker",
    "coordinator:structured-synthesizer",
    "coordinator:notebooklm-research-scout",
)

# NEGATIVE SPEC: this set is reconciled against the LIVE Agent tool schema,
_KNOWN_AGENT_TOOL_INPUT_KEYS = frozenset(
    {
        "subagent_type",
        "prompt",
        "name",
        "description",
        "run_in_background",
        "isolation",
        "model",
        "mode",
        "team_name",
    }
)


#: Why a given type is in scope. `_REASON_CONFINEMENT` fails CLOSED on a
#: allowing it through unchecked is the worse outcome). `_REASON_DELIVERY`
_REASON_CONFINEMENT = "confinement"
_REASON_DELIVERY = "delivery"


def _reason_for(subagent_type: Any) -> Optional[str]:
    if subagent_type in _RESTRICTED_SUBAGENT_TYPES:
        return _REASON_CONFINEMENT
    if subagent_type in _REPORTING_SUBAGENT_TYPES:
        return _REASON_DELIVERY
    return None


def _compose_offer_message(subagent_type: str, reason: str) -> str:
    """Pure composer for the `strip` offer (docs/plans/2026-08-02-guard-
    message-character-cap.md § C6). The full rationale (read-only
    restriction, system prompt, and omitClaudeMd loss; the ~31k-token cost
    breakdown) relocates to `_WIKI_ANCHOR` -- see this module's own
    relocation fragment. Returns the flattened `render()` text (not a
    `Message`) since both callers (`enforce-agent-dispatch-mode.py`,
    `guard-named-dispatch-tool-restriction.py`) treat this as a plain
    `additionalContext` string, not a `Message` they render themselves."""
    if reason == _REASON_DELIVERY:
        prose = (
            "[named-dispatch guard] `name:` stripped from {} -- naming it "
            "makes it a teammate, whose report never reaches you; proceeds "
            "unnamed so it arrives. Its sidecar is the durable copy either "
            "way. (Some other reporting-typed agents declare `SendMessage` "
            "or are named-by-driver and keep reaching you when named -- this "
            "one does not.)"
        ).format(subagent_type)
    else:
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

    Returns `None` when there is nothing to do: `subagent_type` is in
    neither `_RESTRICTED_SUBAGENT_TYPES` nor `_REPORTING_SUBAGENT_TYPES`, or
    `name` is absent from `tool_input` -- an ordinary pass, not a failure.

    THE TWO LEGS ARE DELIBERATELY ASYMMETRIC ON FAILURE, and this is the
    whole reason `_reason_for` exists rather than one flat tuple.
    `_REASON_CONFINEMENT` fails CLOSED: naming Explore/Plan discards a real
    read-only restriction, so a rewrite this module cannot build faithfully
    must deny rather than risk allowing an unconfined agent through.
    `_REASON_DELIVERY` fails OPEN (returns `None`, dispatch proceeds named):
    naming a reporting agent discards nothing -- it costs a report that may
    be lost, which is exactly today's behaviour, so denying would trade a
    sometimes-lost report for a certainly-dead dispatch. Symmetry here would
    be a defect: claude-klabauter-em measured 410 report-eligible named
    dispatches in two weeks, peak 103/day, so a fail-closed delivery leg
    turns one unreconciled `tool_input` key into ~100 hard-denied dispatches
    in a day. Deny where confinement is at stake; pass where it is not.

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
    reason = _reason_for(subagent_type)
    if reason is None:
        return None
    if "name" not in tool_input:
        return None

    subagent_type_str = str(subagent_type)
    try:
        unknown_keys = set(tool_input.keys()) - _KNOWN_AGENT_TOOL_INPUT_KEYS
        if unknown_keys:
            if reason == _REASON_DELIVERY:
                return None
            return ("deny", None, _DENY_MESSAGE.format(subagent_type=subagent_type_str))
        merged = dict(tool_input)
        del merged["name"]
        return ("strip", merged, _compose_offer_message(subagent_type_str, reason))
    except Exception:
        if reason == _REASON_DELIVERY:
            return None
        return ("deny", None, _DENY_MESSAGE.format(subagent_type=subagent_type_str))
