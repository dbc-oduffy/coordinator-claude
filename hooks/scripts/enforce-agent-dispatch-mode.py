#!/usr/bin/env python3
"""enforce-agent-dispatch-mode.py -- PreToolUse hook, matcher: Agent (naked-Python port).

Byte-faithful port of enforce-agent-dispatch-mode.sh. Read that file's header
comment for the full concern breakdown, DEC references, sequencing assumption,
and fail-open contract -- this port preserves every one of those conditions
verbatim; only the extraction/emission MECHANISM changed (in-process JSON
handling instead of jq/python subprocess fan-out per Agent-tool dispatch,
the Windows spawn-tax motivation for this whole naked-Python migration wave).

Concern A -- mode elevation: raise a dispatched child agent's permission mode
up to an autonomous parent's posture (auto/dontAsk/bypassPermissions), never
lower. Absent child mode is treated as acceptEdits (rank 2).

Concern B -- run-report sidecar notice (C3, DEC-4, DEC-5): for subagent_types on
the report_sidecar: eligibility list in coordinator/subagent-sandbox-policy.yaml,
invoke the engine repo's provision-report engine module as a subprocess (python -m
coordinator_core.subagent_sandbox.provision_report, fed the PreToolUse payload
on stdin, 2s timeout) and, on a well-formed {"report_sidecar": "<path>"} stdout
line, append an unconditional deliverable notice to tool_input.prompt --
DEC-4 governs the provisioning decision (a sidecar is prescaffolded only for
report_sidecar-eligible types, so we don't over-provision empty docs for
types that were never eligible in the first place), not whether filling an
already-provisioned sidecar is optional once eligibility is met (DR-091:
it isn't) -- carrying a machine-readable "sidecar_path: <path>" line
(Concern B.3, below).

Concern B is NOT a black-box passthrough of the raw PreToolUse payload: the
engine's resolve_effective_types() (coordinator_core/subagent_sandbox/
engine.py) resolves the spawned child's type from exactly two legs -- a
top-level payload "agent_type" field, or a back-pointer lookup keyed on a
top-level "agent_id" (populated only for an ALREADY-DISPATCHED, named
teammate). On a PreToolUse Agent spawn the child does not exist yet, so it
has no agent_id back-pointer -- the "agent_type" leg is the ONLY viable one,
and the raw payload never carries it (the child's type lives at
tool_input.subagent_type, one level down). This hook therefore builds its
own stdin payload -- same shape as the raw PreToolUse payload PLUS a
top-level "agent_type" set to the resolved child subagent_type -- rather
than piping the raw payload through unmodified. Fixed via a 2026-07-25
cross-repo memo (Concern B: most spawns silently provisioned nothing
because agent_type was never populated).

Concern B is also NOT reliant on an undeclared CLI-invocation-environment
dependency: the subprocess is invoked with an explicit "--policy
<policy_file>" flag (the same policy_file path this hook already computes
for its own eligibility/report-type/contract-block resolution) rather than
depending on CLAUDE_PLUGIN_ROOT being present and correctly resolved in the
subprocess env (Concern B, same memo above).

Concern B.1 -- identity-triggered template selection (docs/plans/2026-07-24-
agent-citizenship-identity-adapted-provisioning.md, chunk C3): when a spawned
subagent_type is both report_sidecar-eligible AND present in the
report_type_map: key of the same policy file, resolve it to a template type
(run-report / review-findings / assessment / staff-eng-review, per C1's
engine-side template registry) and pass "--type <template>" to
provision_report. report_type_map: is a dict (unlike report_sidecar:'s flat
list), read via a real yaml.safe_load -- not the block-scan regex Concern B's
eligibility check uses. An identity absent from report_type_map: gets no
--type flag at all, leaving provisioning's own default untouched. Executors
(coordinator:executor) MUST resolve to an explicit "run-report" here, never
a no-type call -- C1's design gates the enhanced template (carrying the
"## Divergence from plan" section) on an explicit run-report request; a
no-type payload yields the frozen legacy shape instead.

Concern B.2 -- W0 seam prompt-block injection (state/subagent-share/conductor/
seam-adjudication.md §2.4): for subagent_types with a non-empty entry in the
contract_blocks: key of subagent-sandbox-policy.yaml (data-driven eligibility,
no hardcoded consumer family in this hook), the resolved ordered block-name
list is passed to the engine on the same stdin payload under "contract_blocks".
The engine independently returns an "injected_prompt_blocks" string on the
same stdout JSON object as "report_sidecar" -- read independently, neither
key conditional on the other -- which this hook appends verbatim to the
child prompt, after the sidecar deliverable notice. This hook resolves
eligibility and list order only; it authors no block text of its own.

Concern B.3 -- machine-readable sidecar-path marker: the deliverable notice
appended on a successful provision is prose plus a literal
"\nsidecar_path: <path>" line (own line, newline-preceded). Consumer
agents (coordinator/agents/code-reviewer.md § HARD RULE step 1) key off
that exact "sidecar_path:" line, not off the surrounding prose, to locate
their own sidecar. This is the SAME marker shape the EN-1 dedup guard
below already scans the child prompt for ("\nsidecar_path: " substring) to
detect a fan-out-provisioned sidecar and skip re-provisioning -- making the
two provisioning routes (this hook's own Concern B leg, and an upstream
fan-out dispatch) emit an identical, uniformly-greppable marker rather than
two different shapes for the same fact.

Emit-gate (W0 seam, widened): (mode-elevation-needed) OR (sidecar-provisioned)
OR (contract-blocks-injected). None -> silent pass (exit 0, no stdout). Any ->
permissionDecision "allow" plus updatedInput carrying the FULL original
tool_input with whichever mutations apply (mode overwrite, prompt-append(s),
or all three) layered on.

Escape hatch: COORDINATOR_AGENT_MODE_OK set (any non-empty value) in env ->
silent pass. Applies to mode-elevation only, per the oracle (Concern B's
eligibility/provisioning is independent of this env var, matching the bash
oracle's guard placement BEFORE any Concern A/B computation -- i.e. the
escape hatch short-circuits the WHOLE hook, sidecar offer included, exactly
as the oracle's early-exit does).

Fail-open on: missing/unresolvable engine root, missing provision-report
engine module, empty-stdout/exit-nonzero/malformed-JSON from the engine, a
hung/timed-out engine subprocess (2s timeout, matching the oracle's
"timeout 2" value), malformed input JSON, absent fields, unreadable/
malformed policy file. Every fail-open leg on Concern B degrades to
"provision nothing, inject nothing" -- it NEVER blocks or denies the spawn.
This hook exits 0 unconditionally; allow/advisory is conveyed via stdout
only.

CRITICAL: updatedInput carries the FULL original tool_input with mode
overwritten and/or prompt appended -- never a partial object. See the
oracle's SEQUENCING ASSUMPTION: this remains the ONLY updatedInput emitter
on the Agent matcher for the concerns above (nudge-foreground-agent-
dispatch's deny still wins via deny-precedence over this hook's allow --
unaffected by this port).

Concern E -- worktree-isolation strip (single-emitter fix, 2026-07-31): this
hook used to race `strip-worktree-isolation.py` for `updatedInput` on any
Agent dispatch carrying BOTH `isolation: "worktree"` AND a mode-elevation/
sidecar/role-framing trigger -- Claude Code runs same-event PreToolUse hooks
in parallel with undefined completion order, and `updatedInput` is
last-writer-wins, so exactly one hook's rewrite silently clobbered the
other's (confirmed live on harness 2.1.220: either the worktree strip was
silently un-done, or the mode elevation / sidecar offer / injected contract
/ role framing were silently dropped). Fix: this hook now ALSO computes the
worktree-isolation strip itself, via `_worktree_isolation_strip.compute_strip`
(the same pure, shared computation `strip-worktree-isolation.py` uses for
`Workflow` -- neither call site re-implements the strip/override logic), and
layers it onto the SAME `merged` dict / SAME single emission as every other
concern here. `strip-worktree-isolation.py` is narrowed to `Workflow` only
(its `tool_input` has no `prompt` key, so it cannot fold into this hook's
Agent-only merge path and stays a standalone hook for that tool). This is
now the sole `updatedInput` emitter on the Agent matcher for mode-elevation,
sidecar-provisioning, contract-block-injection, role-framing, AND
worktree-isolation stripping.

Concern F -- named-dispatch (`name` key) strip (single-emitter fold-in,
2026-07-31, follow-up to Concern E): this hook used to race
`guard-named-dispatch-tool-restriction.py` for `updatedInput` on a named
Explore/Plan Agent dispatch that ALSO carried a mode-elevation/sidecar/
role-framing/worktree-isolation trigger -- the identical parallel-hook
clobber class Concern E closed for the worktree/mode-elevation pair, now
closed here too. Fix: this hook now ALSO computes the named-dispatch strip
itself, via `_named_dispatch_strip.compute_named_dispatch_result` (the same
pure computation `guard-named-dispatch-tool-restriction.py` used inline,
extracted so neither call site re-implements the restricted-type / unknown-
key / deny logic), and layers a "strip" result onto the SAME `merged` dict /
SAME single emission as every other concern here. A "deny" result (the
guard's own fail-closed leg for an unrecognised `tool_input` key or an
internal failure) short-circuits this hook's `main()` immediately, BEFORE
any other concern is merged in -- the guard's fail-closed contract must win
outright, not get silently folded into an "allow" that also happens to
strip `name`. `guard-named-dispatch-tool-restriction.py` is deregistered
from `hooks.json`'s `Agent` matcher entirely (it was its only matcher, so
unlike `strip-worktree-isolation.py` there is no distinct matcher left where
it is a legitimate standalone emitter); the script itself stays on disk,
still delegating to the same shared module, so its own dedicated test suite
(coordinator/tests/test_guard_named_dispatch_tool_restriction.py) keeps
exercising the real decision logic via direct subprocess invocation.

Concern G -- foreground-dispatch reroute (single-emitter fold-in, RE-LAND,
2026-07-31, follow-up to Concern F): `nudge-foreground-agent-dispatch.py`
used to independently relay the engine's `hooks.nudge_foreground_agent_
dispatch` REROUTE-gate result (`updatedInput` rewriting a foreground
`run_in_background: false` Agent dispatch to `true`) on this SAME Agent
matcher -- the identical parallel-hook clobber class Concern E/F already
closed, confirmed live on harness 2.1.220. A 2026-07-30 revert concluded,
wrongly, that `updatedInput` does not bind `run_in_background` for the
Agent tool; the real cause was this race, and a fresh live probe with the
reroute computed as a single-emitter fold-in (no competing emitter) showed
the EM regaining control 32.3s BEFORE the subagent finished -- genuinely
backgrounded. Fix: this hook now ALSO computes the foreground-reroute
decision itself, via `_foreground_dispatch_strip.compute_foreground_
reroute` (a byte-faithful pure-Python port of that op -- three-state
`run_in_background` handling, durable `.harness-bg-capable` calibration,
`.foreground-ok` escape hatch -- ported rather than called into in-process
specifically to avoid the ~18ms engine hooks-package import and the
sidecar-provisioning subprocess spawn on a path every Agent dispatch
already reaches via Concern D's unconditional role-framing leg), and layers
a "reroute" result (`run_in_background: true` plus an `additionalContext`
notice) onto the SAME `merged` dict / SAME single emission as every other
concern here. A "deny" result (no safely rewritable `tool_input` -- missing
or no `prompt` key) short-circuits `main()` immediately, same precedence
tier as Concern F's own deny -- never silently folded into an allow. The
notice fires on EVERY reroute, never bark-once: a suppressed once-per-
session notice is exactly how the 2026-07-30 non-binding race went a whole
session undetected, since the notice and the tool result were the only
feedback channels and both asserted success. `nudge-foreground-agent-
dispatch.py` is deregistered from `hooks.json`'s `Agent` matcher entirely
(same reasoning as Concern F); the script and the engine's own op stay on
disk as this algorithm's reference implementation, each still exercised by
its own dedicated test suite via direct invocation/subprocess. This hook is
now the sole `updatedInput` emitter on the Agent matcher for mode-elevation,
sidecar-provisioning, contract-block-injection, role-framing, worktree-
isolation stripping, named-dispatch stripping, AND foreground-dispatch
rerouting.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path, PureWindowsPath
from typing import Any, Optional

import yaml

# --- G2 plan-path extraction (state/plan-sidecars chain closure) ---
# The four G2 plan-pipeline sidecar-emitters (prior-art-checker,
# plan-coverage-checker, external-pattern-checker, docs-checker) get their
# report_sidecar routed to the plan-derivable `state/plan-sidecars/
# <plan-stem>.<lens>.md` home ONLY when the payload sent to
# provision_report carries a top-level "plan_path" (see the engine repo's
# provision_report.py, _provision(), the "Plan-derivable leg" branch --
# `payload.get("plan_path")`). An ad-hoc `Agent`-tool dispatch (as opposed
# to a pre-provisioned fan-out-dispatch.py invocation) never populates that
# key -- the raw PreToolUse payload has nowhere to carry it from, exactly
# like the pre-fix "agent_type" gap this hook already closes below. Without
# this leg, every ad-hoc dispatch of a plan-derivable lens silently falls
# through to the session-keyed `state/subagent-share/<session>/<key>.md`
# home instead -- two sidecar homes live at once and the plan-stem
# derivation chain (external-pattern-checker reading prior-art's sidecar)
# only "works" by accident of a stale leftover file from a prior run
# (recorded finding: state/subagent-share/conductor/phase-4/
# g2-c14-discharge.md, "the derivation chain passed on a stale artifact").
#
# Fix: scan the dispatch prompt for a plan-artifact path in one of the two
# canonical plan homes (`docs/plans/*.md` or `~/.claude/plans/*.md`) and, on
# a match, inject it as payload["plan_path"] -- same shape as the
# agent_type injection. First match wins (a dispatch brief that names the
# plan artifact once, early, is the overwhelmingly common shape; this is a
# best-effort extraction, not a parser -- a brief citing zero or multiple
# distinct plan paths degrades to "no plan_path" or "first path", never a
# crash). Fails open (returns None) on no match, exactly like every other
# leg in this hook.
#
# The leading char-class includes "/" so an ABSOLUTE brief path (e.g.
# "some-repo/docs/plans/2026-07-26-foo.md", the shape a dispatch
# brief actually used when it cited the plan under review by full path
# rather than repo-relative) still matches -- the "/" immediately preceding
# "docs/plans/" in that string is what a plain [\s(\[\"'`] class rejects,
# which is the confirmed root cause of the 2026-07-26 miss (empirical
# repro: session 3b97257e-7b1e-47a3-947c-8731e175ed3a, prior-art-checker +
# plan-coverage-checker both provisioned to the session-keyed fallback
# because their briefs named the plan in absolute form). The capture group
# itself only ever starts at "docs/plans/" or "~/.claude/plans/" -- any
# absolute prefix before that point is excluded from the match by
# construction, so a matched absolute brief path normalizes to the same
# repo-relative form CONTRACT.md's plan-derivable leg expects (it only
# ever consumes `Path(plan_path).stem`, but repo-relative is the form
# every other caller of this regex already emits, and keeps the sanitized
# stem identical regardless of which clone/drive the brief's absolute
# prefix names). Unrelated `.md` mentions (schemas, archived specs, sibling
# non-plan docs) never enter this regex's candidate set at all -- the
# prefix literals `docs/plans/`/`~/.claude/plans/` are the only entry
# points, so a brief mentioning other `.md` paths alongside exactly one
# real plan still resolves that one plan.
#
# Review: code-reviewer -- F1 (2026-07-26). The widened leading "/" in the
# char-class above also matches the "/" immediately preceding "docs/plans/"
# inside a URL path segment (e.g. a GitHub permalink
# "https://github.com/org/repo/blob/main/docs/plans/2026-07-01-foo.md"),
# which before this widening was correctly excluded. The regex alone can't
# distinguish "an absolute filesystem path's directory separator" from "a
# URL path separator" -- both are a bare "/" immediately before
# "docs/plans/". Disambiguated post-match in _extract_plan_path below by
# walking back from the match to the nearest whitespace-delimited token
# boundary and rejecting the match if that token's prefix contains "://"
# (scheme-relative and scheme-qualified URLs both carry it) -- this is
# scheme-agnostic (not a literal "http(s)://" check) so it holds for any
# URL scheme, not just the ones seen in practice so far.
#
# Both separators, per tripwire `GUARD-PATH-REGEX-SEPARATOR-BLINDNESS`: a
# Windows brief cites `docs\plans\<stem>.md` with a backslash separator, which a
# forward-slash-only prefix literal never matches. This detector's failure on
# a miss is SILENT -- no plan_path is injected and the G2 sidecar chain simply
# does not form -- which is the worse half of the separator-blindness class:
# a blind deny guard is loud and gets reported, a blind detector just stops
# seeing. The captured path is separator-normalized before injection (see
# `_extract_plan_path`) so downstream `Path(plan_path).stem` is host-stable,
# which is the same invariant the repo-relative note above is protecting.
_PLAN_PATH_RE = re.compile(
    r"(?:^|[\s(\[\"'`/\\])"
    r"((?:docs[/\\]plans[/\\]|~[/\\]\.claude[/\\]plans[/\\])[^\s()\[\]\"'`,;:]+\.md)"
)


def _extract_plan_path(prompt: str) -> Optional[str]:
    if not prompt:
        return None
    for match in _PLAN_PATH_RE.finditer(prompt):
        start = match.start(1)
        token_start = start
        while token_start > 0 and not prompt[token_start - 1].isspace():
            token_start -= 1
        token_prefix = prompt[token_start:start]
        if "://" in token_prefix:
            # URL-adjacency (F1): the widened "/" in the char-class above
            # matched a URL path separator, not an absolute filesystem
            # path's directory separator -- skip this candidate and keep
            # scanning for a genuine plan-path citation later in the prompt,
            # preserving first-match-wins on real ambiguity.
            continue
        # Normalize to the repo-relative forward-slash spelling downstream
        # already assumes: `Path(plan_path).stem` is correct either way on
        # Windows, but a backslash-spelled path handed to a POSIX reader
        # yields a stem of "docs\plans\<name>" rather than "<name>".
        #
        # Review: code-reviewer -- F1 (2026-08-07). An unconditional
        # `.replace("\\", "/")` over the WHOLE match corrupts a literal
        # backslash inside a POSIX filename (`\` is a legal filename char
        # there): `docs/plans/weird\name.md` would be silently rewritten to
        # `docs/plans/weird/name.md`. Split the normalization instead of
        # applying it wholesale: the separators inside the MATCHED PREFIX
        # (`docs\plans\` / `~\.claude\plans\`) are provably separators --
        # our own regex matched them as its separator class -- so those are
        # always safe to normalize. The REMAINDER (the filename portion
        # after the prefix) is not provably separator territory; only
        # normalize it on a host where `\` cannot be a filename character
        # (i.e. `sys.platform.startswith("win")`, a real Windows citation),
        # never on POSIX.
        matched = match.group(1)
        # Locate the boundary between the matched prefix literal
        # (docs[/\\]plans[/\\] or ~[/\\].claude[/\\]plans[/\\]) and the
        # filename remainder by re-finding the prefix via the same regex
        # the module-level pattern already encodes.
        prefix_match = re.match(
            r"(docs[/\\]plans[/\\]|~[/\\]\.claude[/\\]plans[/\\])", matched
        )
        if prefix_match:
            boundary = prefix_match.end()
            # The matched prefix always ends in exactly one separator char
            # (the regex's trailing `[/\\]`); `PureWindowsPath(...).as_posix()`
            # strips that trailing separator, so it is restored explicitly
            # rather than trusting a bare replace of the separator pair.
            prefix = PureWindowsPath(matched[:boundary]).as_posix() + "/"
            remainder = matched[boundary:]
            if sys.platform.startswith("win"):
                # `\` cannot be a filename character on this host, so
                # `PureWindowsPath` (the sanctioned separator-normalization
                # tool, see the module docstring on `_extract_plan_path`)
                # is safe here -- unlike the POSIX leg this branch never
                # runs on, where a literal backslash in `remainder` would
                # be a legal filename char, not a separator.
                remainder = PureWindowsPath(remainder).as_posix()
            return prefix + remainder
        # Defensive fallback -- should be unreachable given the enclosing
        # regex already matched this string, but never crash on a
        # pathological input.
        return matched
    return None


# --- Autonomy rank table (least -> most) ---
# plan=0 < default=manual=1 < acceptEdits=2 < auto=3 < dontAsk=4 < bypassPermissions=5
_MODE_RANK = {
    "plan": 0,
    "default": 1,
    "manual": 1,
    "acceptEdits": 2,
    "auto": 3,
    "dontAsk": 4,
    "bypassPermissions": 5,
}


def _mode_rank(mode: str) -> int:
    return _MODE_RANK.get(mode, -1)


# --- report_sidecar: eligibility list -- flat block scan, mirrors the bash
# oracle's per-key scan (no full YAML parse). Fail-open on absent file,
# absent key, or no match.
_TOP_LEVEL_KEY_RE = re.compile(r"^[A-Za-z_][^\n]*:")
_REPORT_SIDECAR_KEY_RE = re.compile(r"^report_sidecar:")


def _is_report_sidecar_eligible(policy_file: Path, child_subagent_type: str) -> bool:
    if not child_subagent_type or not policy_file.is_file():
        return False
    try:
        lines = policy_file.read_text(encoding="utf-8").splitlines()
    except Exception:
        return False

    in_block = False
    for line in lines:
        if _REPORT_SIDECAR_KEY_RE.match(line):
            in_block = True
            continue
        if _TOP_LEVEL_KEY_RE.match(line):
            in_block = False
            continue
        if in_block:
            trimmed = line.lstrip()
            if trimmed.startswith("- "):
                trimmed = trimmed[2:]
            if trimmed == child_subagent_type:
                return True
    return False


_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
try:
    from _engine_root import resolve_claude_klabauter_root as _resolve_claude_klabauter_root  # noqa: E402
except Exception:
    # Defensive fallback -- a hook script copied/deployed WITHOUT its
    # sibling _engine_root.py (e.g. an isolated test harness, or a
    # partial deploy) must still fail-open rather than crash on import.
    def _resolve_claude_klabauter_root() -> str | None:
        return None

# Reuse the existing root-resolution PRIMITIVE (`_engine_root._session_repo_root`
# -- CLAUDE_PROJECT_DIR when set and real, else a zero-spawn upward walk for a
# `.git` entry) rather than writing a fourth copy of that walk. This is NOT
# the families-spanning shared READER/TRANSPORT module DR-047/DR-118 decline
# (see `_find_repo_root_for_trace`'s own docstring below, kept verbatim) --
# that ruling is about collapsing the three coordinator.local.md READERS
# into one shared transport, not about sharing the tiny root-finding
# primitive beneath them. Same `_engine_root` module this hook already
# imports one line above, for an unrelated (claude-klabauter-root) purpose.
try:
    from _engine_root import _session_repo_root as _resolve_consuming_repo_root  # noqa: E402
except Exception:
    # Same defensive fallback as _resolve_claude_klabauter_root above.
    def _resolve_consuming_repo_root() -> "Path | None":  # type: ignore[no-redef]
        return None

try:
    from _worktree_isolation_strip import compute_strip as _compute_worktree_strip  # noqa: E402
except Exception:
    # Same defensive fallback as _engine_root above -- a copied/deployed
    # hook without its sibling _worktree_isolation_strip.py must still
    # fail-open (Concern E simply never fires) rather than crash on import.
    def _compute_worktree_strip(tool_input: dict):  # type: ignore[no-redef]
        return None

try:
    from _named_dispatch_strip import (  # noqa: E402
        compute_named_dispatch_result as _compute_named_dispatch,
    )
except Exception:
    # Same defensive fallback as above -- a copied/deployed hook without its
    # sibling _named_dispatch_strip.py must still fail-open (Concern F
    # simply never fires) rather than crash on import. NOTE: this is a
    # fail-open for THIS hook's own missing-sibling deploy failure, distinct
    # from the module's own internal fail-closed contract (an unrecognised
    # tool_input key on a real named Explore/Plan dispatch) which only
    # applies once the module is actually importable and running.
    def _compute_named_dispatch(tool_input: dict):  # type: ignore[no-redef]
        return None

try:
    from _foreground_dispatch_strip import (  # noqa: E402
        compute_foreground_reroute as _compute_foreground_reroute,
    )
except Exception:
    # Same defensive fallback as above -- a copied/deployed hook without its
    # sibling _foreground_dispatch_strip.py must still fail-open (Concern G
    # simply never fires) rather than crash on import.
    def _compute_foreground_reroute(run_in_background, session_id, tool_input, cwd):  # type: ignore[no-redef]
        return None

def resolve_roster(*, doe_root: Any = None, home: Any = None):
    """Lazy proxy for `coordinator_core.hooks.block_unenumerated_agent_type
    .resolve_roster` -- the engine plane is reached on CALL, never at module
    import.

    The three sibling imports above are module-level because they are tiny
    local files in this same directory. This one is not: it crosses into the
    engine plane and pulls that module's own dependency tree with it, and
    THIS hook runs on every single Agent dispatch. Hoisting it to module
    scope costs that import unconditionally -- measured at ~52ms median in a
    fresh interpreter -- on every dispatch including a fully-catered one that
    resolves no roster at all, which is the cost A6 says such a dispatch must
    not pay. It also lands on the wrong side of the Agent matcher's
    PreToolUse cost budget that
    docs/plans/2026-08-06-hook-spawn-fan-in-finish-and-extend.md is actively
    reducing.

    Returns the same fail-CLOSED-shaped 2-tuple the real function returns --
    `(roster, None)` or `(None, reason)`, never a bare frozenset/False -- so
    an unimportable engine plane is indistinguishable, to the caller, from a
    roster that would not load. The call site maps that arm to
    `on_roster: null`, NEVER to `on_roster: false` (A2).
    """
    try:
        claude_klabauter_root = _resolve_claude_klabauter_root()
        if claude_klabauter_root and claude_klabauter_root not in sys.path:
            sys.path.insert(0, claude_klabauter_root)
        from coordinator_core.hooks.block_unenumerated_agent_type import (
            resolve_roster as _engine_resolve_roster,
        )
    except Exception as exc:  # noqa: BLE001 -- fail-open, same as every leg here
        return None, (
            "coordinator_core.hooks.block_unenumerated_agent_type is "
            f"unimportable (engine root unresolved or module missing): {exc}"
        )
    return _engine_resolve_roster(doe_root=doe_root, home=home)


from _message_envelope import compose, render  # noqa: E402

#: Wiki section carrying the relocated DR-091/Concern-B.3 explanation (why
#: the notice is unconditional, not an offer; what the deliverable is; how
#: the "sidecar_path:" marker line is consumed downstream) -- see this
#: hook's conversion relocation fragment at state/relocations/guard-message-
#: cap/enforce-agent-dispatch-mode.py.md.
_WIKI_ANCHOR = (
    "coordinator/docs/wiki/guard-message-concision.md#sidecar-deliverable-notice"
)


def _resolve_report_type(policy_file: Path, child_subagent_type: str) -> str:
    """C3 (identity-triggered template selection): resolve subagent_type ->
    template type via the report_type_map: key in subagent-sandbox-policy.yaml.

    Unlike _is_report_sidecar_eligible's flat block-scan (report_sidecar: is
    a plain list, cheap to line-scan), report_type_map: is a dict and needs a
    real structural read -- a real YAML parse, not a regex extension (F5).
    Fail-open on any parse error, absent file, absent key, or a subagent_type
    with no mapping: return "" and the caller leaves provisioning's own
    default (currently run-report) untouched -- never a crash, never a forced
    type for an unmapped identity.
    """
    if not child_subagent_type or not policy_file.is_file():
        return ""
    try:
        policy = yaml.safe_load(policy_file.read_text(encoding="utf-8"))
    except Exception:
        return ""
    if not isinstance(policy, dict):
        return ""
    report_type_map = policy.get("report_type_map")
    if not isinstance(report_type_map, dict):
        return ""
    report_type = report_type_map.get(child_subagent_type)
    return report_type if isinstance(report_type, str) else ""


def _resolve_contract_blocks(policy_file: Path, child_subagent_type: str) -> list[str]:
    """W0 seam (canonical spec `state/subagent-share/conductor/seam-adjudication.md`
    §2.4.1): resolve subagent_type -> ordered block-name list via the
    contract_blocks: key in subagent-sandbox-policy.yaml.

    Eligibility is DATA, not a hardcoded consumer family: any subagent_type
    with a non-empty list here is eligible for prompt-block injection. There
    is no reviewer-persona set and no emitter set baked into this hook --
    adding a new consumer family later is a policy-data edit only. Real
    yaml.safe_load, same shape as _resolve_report_type (contract_blocks: is a
    dict, not a flat list -- not the block-scan regex). Fail-open on any
    parse error, absent file, absent key, or an unmapped/empty-list
    subagent_type: return [] and the caller injects nothing.
    """
    if not child_subagent_type or not policy_file.is_file():
        return []
    try:
        policy = yaml.safe_load(policy_file.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(policy, dict):
        return []
    contract_blocks_map = policy.get("contract_blocks")
    if not isinstance(contract_blocks_map, dict):
        return []
    block_names = contract_blocks_map.get(child_subagent_type)
    if not isinstance(block_names, list):
        return []
    return [name for name in block_names if isinstance(name, str)]


def _find_repo_root_for_trace() -> Optional[Path]:
    """Anchor at the CONSUMING repo root: `CLAUDE_PROJECT_DIR` when set and a
    real directory, else a zero-spawn pure-Python upward walk for a `.git`
    entry (directory for a normal clone, file for a worktree). Independent
    copy of the same anchoring `_next_move_ledger._find_repo_root` uses for
    its own per-session file under `state/subagent-share/<session_id>/`
    (DR-047/DR-118 decline a families-spanning shared-transport module for
    this class of tiny, independently-failing-open helper -- see that
    module's own docstring).

    Delegates to `_engine_root._session_repo_root` for the actual walk (see
    the module-level import above) -- reusing that shared root-resolution
    primitive is explicitly NOT the shared-transport merge DR-047/DR-118
    decline; only the READER stays a separate copy per those DRs.

    Previously walked upward from THIS FILE's own `__file__` looking for a
    directory containing `coordinator.local.md`, which only ever resolves
    this plugin's own checkout -- correct by accident in a dev repo where
    `--plugin-dir` points the plugin at the working tree itself, and a
    silent miss on a marketplace install where the plugin lives under
    `~/.claude/plugins/` and the consumer's `state/subagent-share/` tree
    lives somewhere `__file__` can never reach."""
    try:
        root = _resolve_consuming_repo_root()
        return Path(root) if root else None
    except Exception:
        return None


_CATERING_TRACE_FILENAME = "catering-miss-trace.jsonl"


def _emit_catering_trace(
    session_id: str,
    child_subagent_type: str,
    sidecar_eligible: bool,
    report_type: str,
    contract_blocks: list[str],
) -> None:
    """Plan 2026-08-10-catering-miss-signal.md (C1) -- append one JSON
    record observing what Concern B actually resolved for this dispatch,
    roster-discriminated (A1). Pure observation: never mutates the
    dispatch, never touches stdout (A3) -- the caller wraps this whole
    call in a try/except so ANY failure here is swallowed (A4); this
    function additionally never raises past its own body for the same
    reason, defense in depth.

    Roster resolution is LAZY (A6): `resolve_roster()` is only called when
    catering resolved empty (neither sidecar-eligible nor carrying
    contract blocks) -- a fully-catered dispatch never touches the
    roster. `resolve_roster()`'s `(None, reason)` fail-CLOSED arm (meant
    for its home caller, a deny guard) maps here to `on_roster: null` +
    `roster_error: <reason>` -- NEVER to `on_roster: false` (A2); a bare
    membership test against a None roster would silently misclassify
    every roster-load failure as "invented", which is the exact trap the
    plan's anti-scope section names.

    `on_roster: null` is ambiguous on its own -- it means EITHER "roster
    resolution was skipped because catering already succeeded" OR
    "roster resolution was attempted and failed". The always-present
    boolean field `roster_checked` disambiguates the two: `False` when
    the laziness gate skipped resolution entirely (no `roster_error`),
    `True` when `resolve_roster()` was actually called (whether it
    succeeded, giving `on_roster` true/false, or failed, giving
    `on_roster: null` + `roster_error`).
    """
    if not session_id:
        return
    repo_root = _find_repo_root_for_trace()
    if repo_root is None:
        return

    on_roster: Optional[bool] = None
    roster_error: Optional[str] = None
    roster_checked = False
    if not sidecar_eligible and not contract_blocks:
        roster_checked = True
        roster, reason = resolve_roster()
        if reason is not None:
            on_roster = None
            roster_error = reason
        else:
            on_roster = child_subagent_type in (roster or frozenset())

    record: dict[str, Any] = {
        "subagent_type": child_subagent_type,
        "on_roster": on_roster,
        "roster_checked": roster_checked,
        "sidecar_eligible": bool(sidecar_eligible),
        "report_type": report_type,
        "contract_blocks": list(contract_blocks),
    }
    if roster_error is not None:
        record["roster_error"] = roster_error

    trace_dir = repo_root / "state" / "subagent-share" / session_id
    trace_dir.mkdir(parents=True, exist_ok=True)
    trace_path = trace_dir / _CATERING_TRACE_FILENAME
    with open(trace_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


_ROLE_APPEND_SNIPPET = Path(__file__).resolve().parents[2] / "snippets" / "agent-role-dispatched.md"


def _load_role_append() -> str:
    """Concern D (role framing) -- the single source of truth for the
    dispatched-worker role text is `snippets/agent-role-dispatched.md`;
    this reads it verbatim (no retyping/paraphrase) and fails open to ""
    on any read error, matching every other leg in this hook. Resolved
    from this script's own location (Path(__file__)), never cwd, never a
    hardcoded path -- must work on a machine this was never authored on.
    """
    try:
        return _ROLE_APPEND_SNIPPET.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _provision_sidecar(
    raw_input: str,
    child_subagent_type: str,
    policy_file: Path,
    report_type: str = "",
    contract_blocks: Optional[list[str]] = None,
) -> tuple[str, str]:
    """Invoke the engine repo's provision-report engine, timeout-wrapped at 2s (matches
    the oracle's timeout-2 value). Any failure leg returns ("", "") (fail-open).

    Oracle parity (A-F6): the bash oracle invokes provision_report
    unconditionally, regardless of whether it can resolve CLAUDE_KLABAUTER_ROOT --
    PYTHONPATH injection is best-effort there too. Mirror that here: attempt
    the subprocess even when _resolve_claude_klabauter_root() fails, only injecting
    PYTHONPATH when a root IS resolved. This restores the sidecar offer on
    installs where coordinator_core is importable without a resolved
    CLAUDE_KLABAUTER_ROOT (e.g. already on sys.path / PYTHONPATH via some other means).

    report_type (C3): when non-empty, resolved from report_type_map: via
    _resolve_report_type and appended as "--type <report_type>" -- selects
    which of provision_report's C1 templates (run-report / review-findings /
    assessment / staff-eng-review) the engine scaffolds. Empty (unmapped
    identity) means no --type flag at all -- provisioning's own default
    applies, never a forced type.

    contract_blocks (W0 seam): when non-empty, the resolved block-name list
    is merged into the stdin payload under a "contract_blocks" key -- this
    hook resolves ELIGIBILITY and the ORDERED LIST doctrine-plane-side but authors no
    block text; the engine reads the list, extracts + assembles the blocks
    from disk, and returns a pre-joined "injected_prompt_blocks" string on
    the SAME stdout JSON object as "report_sidecar". The two output keys are
    read independently -- neither is conditional on the other succeeding.

    child_subagent_type / policy_file (Concern B fix): the raw PreToolUse
    payload never carries a top-level "agent_type" -- the engine's
    resolve_effective_types() only resolves from a top-level "agent_type"
    field or an agent_id back-pointer, and a PreToolUse spawn has neither
    populated on the raw payload (the type lives one level down, at
    tool_input.subagent_type). This function injects
    payload["agent_type"] = child_subagent_type into a SINGLE parse-mutate-
    reserialize pass (unified with the pre-existing contract_blocks merge
    below -- one payload build, not two independent re-serializations) and
    passes "--policy <policy_file>" explicitly rather than depending on an
    undeclared CLAUDE_PLUGIN_ROOT-in-env leg. If the raw payload does not
    parse as a JSON object, this leg is skipped and the raw payload is sent
    through unmodified -- that fail-open shape is unchanged from before this
    fix (it was already how the contract_blocks merge failed open).

    plan_path (G2 plan-derivable sidecar chain, see `_extract_plan_path`
    above): the same parse-mutate-reserialize pass also best-effort-extracts
    a `docs/plans/*.md` or `~/.claude/plans/*.md` path out of the child
    prompt and injects it as payload["plan_path"] when found. This is what
    lets provision_report.py's plan-derivable leg fire for an ad-hoc `Agent`
    dispatch of one of the four G2 lenses (prior-art-checker,
    plan-coverage-checker, external-pattern-checker, docs-checker) -- absent
    it, those dispatches silently fall through to the session-keyed
    `state/subagent-share/` home instead of `state/plan-sidecars/`, breaking
    the cross-lens plan-stem derivation chain. No match -> no key added ->
    same fall-through as before this fix (fail-open, not fail-loud).
    """
    root = _resolve_claude_klabauter_root()

    env = dict(os.environ)
    if root:
        existing_pp = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = root if not existing_pp else (root + os.pathsep + existing_pp)

    argv = [
        sys.executable,
        "-m",
        "coordinator_core.subagent_sandbox.provision_report",
        "--policy",
        str(policy_file),
    ]
    if report_type:
        argv += ["--type", report_type]

    stdin_payload = raw_input
    try:
        payload_obj: Any = json.loads(raw_input)
    except Exception:
        payload_obj = None
    if isinstance(payload_obj, dict):
        if child_subagent_type:
            payload_obj["agent_type"] = child_subagent_type
        if contract_blocks:
            payload_obj["contract_blocks"] = contract_blocks
        tool_input_obj = payload_obj.get("tool_input")
        if isinstance(tool_input_obj, dict):
            plan_path = _extract_plan_path(str(tool_input_obj.get("prompt") or ""))
            if plan_path:
                payload_obj["plan_path"] = plan_path
        stdin_payload = json.dumps(payload_obj)

    try:
        # Windows: suppress the console-popup flash on this python.exe spawn.
        # Every console child needs this, git.exe included — the "git.exe is
        # GUI-subsystem and exempt" premise was refuted by measurement.
        proc = subprocess.run(
            argv,
            input=stdin_payload,
            capture_output=True,
            text=True,
            timeout=2,
            env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return "", ""

    out = (proc.stdout or "").strip()
    if not out:
        return "", ""

    try:
        data = json.loads(out)
    except Exception:
        return "", ""
    if not isinstance(data, dict):
        return "", ""

    sidecar = data.get("report_sidecar")
    sidecar = sidecar if isinstance(sidecar, str) else ""

    injected = data.get("injected_prompt_blocks")
    injected = injected if isinstance(injected, str) else ""

    return sidecar, injected


# Machine-readable structural marker appended by _compose_teammate_clause(),
# same convention as the "\nsidecar_path: <path>" line Concern B.3 already
# appends. Single source of truth -- the docstring below and the composer
# both reference this constant rather than duplicating the literal string,
# so a later concision pass can reword the prose without silently drifting
# the marker out of sync (Review: code-reviewer -- Finding 3, coordinatorcode-reviewer-b37492a7).
TEAMMATE_CLAUSE_MARKER = "teammate_delivery_channel: sidecar-write-required"


def _compose_teammate_clause() -> str:
    """Named-teammate sidecar-fill clause (docs/plans/2026-08-10-named-
    teammate-sidecar-fill.md, C1): a dispatch that is BOTH named (Agent-
    teams teammate, `tool_input.name` set) AND sidecar-provisioned by this
    SAME hook reaches the dispatcher only via SendMessage("main") -- that
    message is the pointer line, never the sidecar write, which stays
    unconditional (DR-091). Keyed on STRUCTURE (name present AND
    sidecar_path just provisioned), never on the brief's prose -- mirroring
    the engine's own SendMessage/"main" suppression heuristic is the exact
    defect this closes (see plan Sec Problem, finding 1). Fail-open: the
    caller wraps this in try/except, matching the Concern E/F call-site
    discipline (this hook's own docstring, :786-789, :802-805) -- never
    block a dispatch to deliver an advisory.

    The trailing "\\n" + TEAMMATE_CLAUSE_MARKER line is the module-level
    structural marker constant defined just above this docstring -- a later
    concision pass may reword the prose but should preserve this token."""
    message = compose(
        "Named teammate: SendMessage to \"main\" is your only return "
        "channel, and it carries the pointer line ONLY. It does not "
        "discharge the sidecar write -- still required, or the scaffold "
        "is refused.",
        anchor=_WIKI_ANCHOR,
    )
    return "\n\n" + render(message) + "\n" + TEAMMATE_CLAUSE_MARKER


def _compose_sidecar_offer_text(sidecar_path: str) -> str:
    """Pure composer for the DR-091 sidecar deliverable notice (Concern B.3)
    -- separated from `main()` so C1b's in-process measurement harness can
    call it directly per emission site, per the plan's Measurement
    mechanism section. The two DENY-branch messages (Concerns F/G) and the
    worktree/named-dispatch/foreground additionalContext notes are already
    composed by separate pure functions this module imports
    (`_compute_named_dispatch`, `_compute_foreground_reroute`,
    `_compute_worktree_strip`) -- this is the one remaining inline-composed
    string `main()` built itself. Behaviour-preserving extraction.

    Routes the human-readable diagnosis through `_message_envelope.compose`
    (the DR-091/Concern-B.3 "why this is unconditional, not an offer"
    explanation relocated to `_WIKI_ANCHOR` -- see this hook's relocation
    fragment). The trailing "\\nsidecar_path: <path>" line is a
    machine-readable marker, not prose (Concern B.3: consumer agents key
    off that exact line, per `coordinator/agents/code-reviewer.md` § HARD
    RULE step 1, and the EN-1 dedup guard above scans for the same
    shape) -- appended verbatim after the rendered message, never folded
    into the capped `prose` field or the structurally-validated
    `alternative` block (its trailing colon fails
    `validate_alternative_shape`'s command/path shape check by design)."""
    message = compose(
        "You have a run-report sidecar for this dispatch -- capture run "
        "notes and any divergence there; filling it in is expected, not "
        "optional.",
        anchor=_WIKI_ANCHOR,
    )
    return "\n\n" + render(message) + "\nsidecar_path: " + sidecar_path


def main() -> int:
    raw = sys.stdin.read()

    # --- Concern D (role framing): a FOURTH INDEPENDENT LEG of the emit-gate,
    # computed unconditionally, before and outside every guard below --
    # the fanout_already_present dedup guard, the subagent_type policy
    # lookup (Concern B/B.2's eligibility gate), and the escape hatch just
    # below. This is deliberate, not an oversight: Concerns B/B.2 are gated
    # on an exact-string policy lookup that enumerates only
    # `coordinator:`-prefixed plugin agents -- `Explore`, `Plan`,
    # `general-purpose`, and `claude` appear in neither eligibility list, so
    # a role-framing append riding either of those legs would never reach
    # exactly the population it exists for (state/audits/
    # 2026-07-27-explore-plan-hook-reach.md). It is also unconditional
    # across subagent_type by construction -- there is no allowlist here to
    # extend, because a policy lookup gating this population closed is the
    # defect this leg fixes.
    role_append = _load_role_append()

    try:
        data: Any = json.loads(raw)
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}

    tool_input = data.get("tool_input")
    tool_input_dict = tool_input if isinstance(tool_input, dict) else {}

    # --- Escape hatch: deliberate down-scope dispatch (e.g. read-only scout
    # from YOLO session). Short-circuits Concern A/B computation only,
    # matching the oracle's early-exit placement for THOSE concerns (before
    # any Concern A/B computation). It deliberately does NOT short-circuit
    # Concern D above: COORDINATOR_AGENT_MODE_OK is a permission-mode escape
    # hatch, not a doctrine one, and letting it suppress role framing would
    # silently unframe every session that sets it.
    mode_ok_escape = bool(os.environ.get("COORDINATOR_AGENT_MODE_OK"))

    parent_mode = data.get("permission_mode") or ""
    child_mode = tool_input_dict.get("mode") or ""

    need_mode_elevation = False
    sidecar_path = ""
    injected_blocks = ""
    teammate_clause = ""

    if not mode_ok_escape:
        # --- Concern A gate: mode-elevation-needed ---
        if parent_mode:
            parent_rank = _mode_rank(parent_mode)
            child_effective = child_mode or "acceptEdits"
            child_rank = _mode_rank(child_effective)
            if parent_rank >= 0 and child_rank >= 0 and parent_rank >= 3 and child_rank < parent_rank:
                need_mode_elevation = True

        # --- Concern B: run-report sidecar eligibility + provisioning ---
        child_prompt = tool_input_dict.get("prompt") or ""
        # EN-1: skip if fan-out already provisioned a deterministic sidecar
        # (present "sidecar_path: " line in prompt) -- avoid double-provision.
        # Anchored to the actual injected line shape (newline-preceded,
        # space-suffixed), not a bare substring -- see oracle comment. This
        # guard is scoped to Concern B/B.2 only -- it never gates role_append.
        fanout_already_present = "\nsidecar_path: " in child_prompt

        if not fanout_already_present:
            child_subagent_type = tool_input_dict.get("subagent_type") or ""
            if child_subagent_type:
                # __file__ parents: [0]=scripts [1]=hooks [2]=coordinator(plugin root)
                policy_file = Path(__file__).resolve().parents[2] / "subagent-sandbox-policy.yaml"
                # contract_blocks: is DECOUPLED from report_sidecar: by policy
                # (subagent-sandbox-policy.yaml, contract_blocks: header): a key
                # there "is NOT required to be report_sidecar-eligible", because a
                # block like quota-self-detect-preamble teaches an agent about its
                # own quota regardless of tier. Resolving it INSIDE the eligibility
                # branch collapsed that decoupling back to lockstep and silently
                # stripped the blocks from every exploration-tier key. The engine
                # half already supports the split -- provision_report emits
                # report_sidecar and injected_prompt_blocks independently, either
                # one alone -- so eligibility OR a non-empty block list is enough
                # to make the call worth its spawn. Both empty still spawns
                # nothing, which is what keeps an unenumerated type free.
                contract_blocks = _resolve_contract_blocks(policy_file, child_subagent_type)
                sidecar_eligible = _is_report_sidecar_eligible(policy_file, child_subagent_type)
                report_type = ""
                if sidecar_eligible or contract_blocks:
                    report_type = _resolve_report_type(policy_file, child_subagent_type)
                    sidecar_path, injected_blocks = _provision_sidecar(
                        raw, child_subagent_type, policy_file, report_type, contract_blocks
                    )

                # --- Catering miss-signal trace (plan 2026-08-10-catering-
                # miss-signal.md, C1) -- pure observation, never feeds back
                # into the dispatch. The whole leg is wrapped so ANY failure
                # (unresolvable engine root, import error, unwritable trace
                # path, full disk) is swallowed and the dispatch proceeds
                # unchanged (A4) -- this hook's own discipline for every
                # optional leg, matching the module docstring's uncaught-
                # exception-is-fail-CLOSED-on-a-fail-open-hook rule.
                try:
                    _emit_catering_trace(
                        data.get("session_id") or "",
                        child_subagent_type,
                        sidecar_eligible,
                        report_type,
                        contract_blocks,
                    )
                except Exception:
                    pass

        # --- Named-teammate sidecar-fill clause (plan 2026-08-10-named-
        # teammate-sidecar-fill.md, C1): keyed on STRUCTURE ONLY -- a
        # sidecar was just provisioned above AND tool_input carries a
        # non-empty `name` (the Agent-teams named-dispatch marker Concern F
        # strips later, off the SAME unmutated tool_input_dict read here --
        # the strip itself only ever mutates `merged`, a `dict(tool_input)`
        # copy built later, never `tool_input_dict`).
        # Fail-open, matching the Concern E/F call-site discipline: never
        # block a dispatch to deliver this advisory.
        try:
            if sidecar_path and tool_input_dict.get("name"):
                teammate_clause = _compose_teammate_clause()
        except Exception:
            teammate_clause = ""

    # --- Concern E: worktree-isolation strip (single-emitter fix, see module
    # docstring). Computed unconditionally, like role_append -- it is not a
    # mode-elevation concern and must not be gated by the
    # COORDINATOR_AGENT_MODE_OK escape hatch. Pure computation; None when
    # there is nothing to strip (isolation absent, any non-"worktree" value,
    # or the override sentinel is active).
    # Review: code-reviewer -- the three _compute_* call sites relied entirely
    # on callee-internal fail-open discipline with no defensive try/except at
    # the call site; an uncaught exception here would produce no valid JSON
    # on stdout (fail-CLOSED on a hook whose whole design is fail-open).
    # Degrade to None on any exception, matching the ImportError fallback's
    # own contract.
    try:
        worktree_strip_result = _compute_worktree_strip(tool_input_dict)
    except Exception:
        worktree_strip_result = None

    # --- Concern F: named-dispatch (`name` key) strip (single-emitter
    # fold-in, see module docstring). Computed unconditionally, like Concern
    # E -- it is not a mode-elevation concern and must not be gated by the
    # COORDINATOR_AGENT_MODE_OK escape hatch. A "deny" result is this
    # module's own fail-closed leg (unrecognised tool_input key, or an
    # internal failure, on a genuinely named Explore/Plan dispatch) and MUST
    # win outright over every other concern -- short-circuit immediately,
    # before folding anything else into `merged`, exactly as the standalone
    # guard used to (its deny was never conditional on the other concerns'
    # state).
    try:
        named_dispatch_result = _compute_named_dispatch(tool_input_dict)
    except Exception:
        named_dispatch_result = None

    # --- Concern G: foreground-dispatch reroute (single-emitter fold-in,
    # RE-LAND, see module docstring). Computed unconditionally, like Concern
    # E/F -- it is not a mode-elevation concern and must not be gated by the
    # COORDINATOR_AGENT_MODE_OK escape hatch (its own, distinct escape hatch
    # is the `.foreground-ok` sentinel, checked inside the pure computation).
    # A "deny" result (no safely rewritable tool_input) MUST win outright
    # over every other concern, same precedence tier as Concern F's own
    # fail-closed leg.
    try:
        foreground_result = _compute_foreground_reroute(
            tool_input_dict.get("run_in_background"),
            data.get("session_id"),
            tool_input_dict,
            data.get("cwd"),
        )
    except Exception:
        foreground_result = None

    # --- Single-emitter invariant: exactly ONE hookSpecificOutput object is
    # ever built and written, at the single write call site at the bottom of
    # this function -- a "deny" (Concern F's or Concern G's own
    # fail-closed leg) and an "allow" (every other concern) are mutually
    # exclusive outcomes of the SAME decision, computed into `out` below,
    # never two independent write sites racing to be the last one out.
    out: Optional[dict[str, Any]] = None

    if named_dispatch_result is not None and named_dispatch_result[0] == "deny":
        # A "deny" result is this module's own fail-closed leg (unrecognised
        # tool_input key, or an internal failure, on a genuinely named
        # Explore/Plan dispatch) and MUST win outright over every other
        # concern -- built here, before anything else is folded into a
        # merged `tool_input`, exactly as the standalone guard used to (its
        # deny was never conditional on the other concerns' state).
        _, _, deny_message = named_dispatch_result
        out = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": deny_message,
            }
        }
    elif foreground_result is not None and foreground_result[0] == "deny":
        # Concern G's own fail-closed leg (a provably-foreground dispatch
        # with no safely rewritable tool_input) -- same precedence tier as
        # Concern F's deny above: built before anything else is folded into
        # `merged`, never silently absorbed into an allow.
        _, _, deny_message = foreground_result
        out = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": deny_message,
            }
        }
    elif (
        need_mode_elevation
        or sidecar_path
        or injected_blocks
        or teammate_clause
        or role_append
        or worktree_strip_result is not None
        or named_dispatch_result is not None
        or foreground_result is not None
    ):
        # --- Combined emit-gate (W0 seam, widened to SEVEN independent
        # legs): mode-elevation-needed OR sidecar-provisioned OR
        # contract-blocks-injected OR role-framing-append OR
        # worktree-isolation-stripped OR named-dispatch-stripped OR
        # foreground-dispatch-rerouted. Each leg is independent -- a
        # consumer with a resolved contract_blocks list but a failed sidecar
        # provision must still get its injected contract, not silently
        # nothing; likewise role_append must fire even when the other legs
        # are all closed (Explore/Plan/general-purpose/claude, the exact
        # population Concern D exists for), the worktree strip must fire
        # even when none of Concerns A-D apply (an ordinary dispatch that
        # only happens to carry isolation: "worktree"), the named-dispatch
        # strip must fire even when none of Concerns A-E apply (an ordinary
        # named Explore/Plan dispatch with no other trigger), and the
        # foreground reroute must fire even when none of Concerns A-F apply
        # (an ordinary foreground Agent dispatch with no other trigger).

        # --- Sidecar deliverable notice (DR-091: unconditional, not an
        # offer) --- Concern B.3: the prose notice carries an ADDITIVE
        # machine-readable "\nsidecar_path: <path>" line -- the same marker
        # shape the EN-1 guard above scans for -- so a consuming agent
        # (coordinator/agents/code-reviewer.md § HARD RULE step 1) can key
        # off an exact line rather than parsing prose. DEC-4 (2026-07-13)
        # gated whether a sidecar gets provisioned at all (only
        # report_sidecar-eligible types get one, so ineligible types aren't
        # over-provisioned with empty docs); it never licensed skipping a
        # sidecar that WAS provisioned. DR-091 (2026-07-24) settled that
        # explicitly: the sidecar is prescaffolded before the agent's first
        # tool call and required frontmatter fields (divergence, etc.) are a
        # deliverable, not optional prose -- so this notice reads as a task,
        # not a maybe.
        offer_text = _compose_sidecar_offer_text(sidecar_path) if sidecar_path else ""

        # --- Emit: permissionDecision "allow" + updatedInput (full merge,
        # whichever mutations apply). Type guard mirrors the oracle's jq path
        # ("object" type check only -- an empty {} tool_input still
        # qualifies) rather than the oracle's stricter python-fallback
        # truthy check, since jq is the oracle's PREFERRED path.
        if not isinstance(tool_input, dict):
            return 0

        merged = dict(tool_input)
        if need_mode_elevation:
            merged["mode"] = parent_mode
        if offer_text:
            merged["prompt"] = (merged.get("prompt") or "") + offer_text
        # Named-teammate clause lands directly after the sidecar offer --
        # same channel (tool_input.prompt), same ordering rule as every
        # other prompt-append leg below (original brief -> sidecar offer ->
        # teammate clause -> injected contract -> role framing).
        if teammate_clause:
            merged["prompt"] = (merged.get("prompt") or "") + teammate_clause
        # W0 seam (§2.4.4): append the engine-assembled contract verbatim,
        # AFTER the DEC-4 sidecar offer, so ordering is deterministic --
        # original brief -> sidecar offer -> injected contract. This hook
        # authors no text of its own around the injected payload.
        if injected_blocks:
            merged["prompt"] = (merged.get("prompt") or "") + "\n\n" + injected_blocks
        # Concern D: role framing lands LAST, after any sidecar offer /
        # injected contract -- original brief -> sidecar offer -> injected
        # contract -> role framing. Unconditional across subagent_type; this
        # is the leg that reaches Explore/Plan/general-purpose/claude.
        if role_append:
            merged["prompt"] = (merged.get("prompt") or "") + "\n\n" + role_append

        # Concern E: worktree-isolation strip lands on the SAME merged dict
        # as every other concern above -- single object, single emission.
        # Surfaced via a sibling additionalContext string (the same shape
        # strip-worktree-isolation.py uses for Workflow) rather than
        # appended into tool_input.prompt, so it composes independently of
        # whether a sidecar/contract/role-framing prompt append also fired
        # on this call.
        #
        # Concern F: named-dispatch strip lands on the SAME merged dict too
        # -- `name` removal, plus its own additionalContext note. Concern G:
        # foreground reroute lands on the SAME merged dict too -- sets
        # `run_in_background: true`, plus its own additionalContext note.
        # All three notes are additionalContext strings (never
        # tool_input.prompt, which is Concerns B/B.2/D's channel); when
        # several fire on the same dispatch they are concatenated in a fixed
        # order -- worktree, named-dispatch, foreground-reroute --
        # deterministic, never a last-writer-wins clobber, since this is one
        # hook building one string, not several hooks racing.
        additional_context_parts: list[str] = []
        if worktree_strip_result is not None:
            _, worktree_note = worktree_strip_result
            if "isolation" in merged:
                del merged["isolation"]
            additional_context_parts.append(worktree_note)
        if named_dispatch_result is not None:
            _, _named_merged, name_offer = named_dispatch_result
            if "name" in merged:
                del merged["name"]
            additional_context_parts.append(name_offer)
        if foreground_result is not None and foreground_result[0] == "reroute":
            # Review: code-reviewer -- consume the callee's returned value
            # rather than re-hardcoding the literal it stands for.
            merged["run_in_background"] = foreground_result[1]
            additional_context_parts.append(foreground_result[2])
        additional_context = "\n\n".join(additional_context_parts) if additional_context_parts else None

        out = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "updatedInput": merged,
            }
        }
        if additional_context:
            out["hookSpecificOutput"]["additionalContext"] = additional_context

    if out is None:
        return 0

    sys.stdout.write(json.dumps(out))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
