#!/usr/bin/env python3
"""PreToolUse hook (matchers: Agent, Workflow) -- Layer 2 of the DR-088
ladder (docs/plans/2026-07-23-dr-088-ladder-enforcement-layers.md § C8):
closes the "EM typed a suite command into a dispatch brief" gap that
layer 3 (PreToolUse(Bash), claude-klabauter-owned, c66e559d) cannot reach, because
layer 3 fires on the dispatched subagent's OWN Bash call, not on the
dispatching EM's Agent()/Workflow() call that hands the subagent its
prompt in the first place.

THIS IS A REGISTRATION HOOK, NOT A CLASSIFIER. All suite-shaped-command
judgement lives in claude-klabauter's
`coordinator_core.bash_guards.check_test_suite_invocation.classify_text`
(shipped `bfbe1625` + `18f8498e`, per the inbound memo
cross-repo/inbox/2026-07-23-claude-klabauter-em-dr088-layers-2-5-shipped.md
§ "Layer 2"). This file owns ZERO test-runner names, ZERO command
grammar, ZERO regex over suite invocations -- it calls `classify_text`,
reads the returned `SuiteMatch.position`, and decides deny-or-allow. A
second classifier grammar in this tree would drift from claude-klabauter's within
weeks, and the drift would be silent (both would look correct) -- that
is the boundary test this hook exists to hold.

Danger condition: the dispatching EM's Agent/Workflow prompt text
contains a suite-shaped command in IMPERATIVE position (a real
instruction to run it), which would hand a subagent a Tier-F/Tier-U test
command a fan-out wave should never carry.

`position` handling -- gate on "imperative" only. Claude-klabauter's classifier
reports `fenced_code` / `inline_code` / `negated` / `unknown` /
`imperative` as ADVISORY metadata; claude-klabauter classifies, this hook decides.
A brief that quotes a suite command inside a fence, inline code, or a
negation ("do NOT run `pytest -v`") is legitimate authoring content -- an
executor brief instructing a chunk to DELETE a deny-list table (this
plan's own C5/C6/C7 briefs) must quote the exact commands it prohibits.
Only `position == "imperative"` denies.

Deny shape: JSON on stdout + exit 0, per
coordinator/docs/pretooluse-deny-contract.md and hook-best-practices.md §
Multi-hook deny aggregation. exit 1 does NOT block -- the named footgun
this doc warns about.

Fail-open guards (in order, all silent exit 0 unless noted):
  - explicit override, payload-independent leg (env var or repo-root
    sentinel file) -- see _OVERRIDE_ENV / _OVERRIDE_SENTINEL_NAME below.
    Checked before tool_input is even parsed.
  - tool_name not in {"Agent", "Workflow"}.
  - subagent/nested call (payload carries "agent_id") -- this hook
    guards the dispatching EM's OWN Agent/Workflow call, mirroring
    block-workflow-unmodeled-agent.py's subagent exclusion. (In practice
    Agent/Workflow calls are always main-loop-issued, but the check is
    kept for parity and future-proofing.)
  - no dispatch prompt text extractable from tool_input (unknown tool_input
    shape, e.g. a Workflow `name:`-only launch with no script/prompt payload).
  - explicit override, payload-dependent leg (in-prompt marker) -- see
    _OVERRIDE_MARKER_PREFIX below. Runs here, after text extraction,
    since it needs the extracted dispatch text to check.
  - _engine_root.py unresolvable, or coordinator_core.bash_guards.
    check_test_suite_invocation unimportable, or classify_text raises --
    ANY infra failure fails OPEN (silent allow). A broken guard must
    never brick every dispatch in the fleet; fail CLOSED only on the
    authorization question itself (a confirmed imperative-position
    match).

Override -- THREE hatches, in ascending order of blast radius. Prefer
the first one that applies; the third is a named last resort, not a
routine option.

  1. In-prompt marker (`COORDINATOR-OVERRIDE-DISPATCH-SUITE-GUARD:
     <reason>`, own line, non-empty reason) -- the PREFERRED hatch,
     scoped to exactly the ONE dispatch carrying the marker. Honored
     ONLY in text the dispatching EM authored in this very tool call
     (Agent `prompt`, Workflow inline `script`) -- never in a
     `scriptPath` file read from disk, which is attacker-influenceable
     on a shared branch. See _has_override_marker() / _extract_dispatch_text()
     for the trust-scoping mechanics. Deliberately HYPHENATED, distinct
     from the underscored env-var name below, so prose merely discussing
     the env var cannot accidentally self-override. Known, accepted
     limitation: a brief whose prose quotes the marker verbatim at line
     start would self-override -- the hyphen/underscore split mitigates
     the common case (discussing the env var), this residue is accepted.
  2. COORDINATOR_OVERRIDE_DISPATCH_SUITE_GUARD=1, typed and EM-settable,
     same shape as COORDINATOR_OVERRIDE_WORKFLOW_MODEL_GUARD /
     COORDINATOR_OVERRIDE_NO_VERIFY / COORDINATOR_OVERRIDE_BLANKET_ADD /
     COORDINATOR_AGENT_FOREGROUND_OK. NOT reachable mid-session -- a
     shell `export` inside a Bash tool call does not mutate the running
     harness process's own env, so a live EM session cannot set this on
     itself after boot. Still valid for non-interactive/CI invocation
     (the process env is set before the harness launches), which is why
     the check remains in the code -- it is simply not offered as a
     live-session escape hatch in the deny text below.
  3. A repo-root `.coordinator-override-dispatch-suite-guard` sentinel
     file -- blast radius is the WHOLE REPO: it disarms this guard for
     EVERY dispatch while it exists, and on a shared `work/*` branch, for
     every concurrent peer session too. Named last resort only; two
     sibling repos (project-rag, claude-klabauter) have already field-
     reported reaching for this on a single false-positive dispatch
     because hatch 2 was unreachable and hatch 1 did not yet exist --
     that is precisely the live pressure toward a posture worse than the
     guard itself that motivated adding hatch 1.

Layer 3 (PreToolUse(Bash), agent_id present, subagent-targeted)
correctly has NO override of any of these three shapes -- the subagent
being guarded could set an env override or plant a marker on itself
inline. Layer 2 is different: this hook fires on the DISPATCHING EM's
own call, not the guarded subagent's, so the EM is the trusted
orchestrator and a deliberate, reason-bearing override it sets is the
correct escape hatch, not a hole -- a guard with no exception path that
vetoes the EM's own legitimate delegation is the DR-058 failure mode.
Residual traffic on all three overrides should be low: per the inbound
memo, gating on `position == "imperative"` already passes the concrete
false-positive case (a brief quoting a deny-list table in order to
delete it) without needing any override at all.

Registered BEFORE block-workflow-unmodeled-agent.py on the Workflow
matcher in hooks.json -- first-deny-wins in registration order
(hook-best-practices.md § Multi-hook deny aggregation) -- so a suite-
invocation deny is never shadowed by that hook's own (unrelated) verdict.

ADVISORY LEG -- the directory-breadth nudge (added 2026-07-28). Additive
over everything above, and it NEVER denies. Gap this closes: DR-088 R9
(claude-klabauter's PreToolUse(Bash) layer 3 precision leg) correctly refuses a
directory positional to a DISPATCHED agent -- Tier T is file-and-node-id
precision for a subagent -- but that refusal fires at the dispatched
agent's own Bash call, one hop downstream of the EM that wrote the brief.
An inbound memo (cross-repo/inbox/2026-07-28-example-market-data-repo-em-
dispatched-agent-scoped-test-breadth.md) reports the observed failure
mode: an EM briefed a directory-scoped verification run, R9 refused it,
the dispatched agent silently narrowed to the two files it had touched
(37 tests passed) against a briefed breadth of 434, and reported green.
Nothing told the dispatching EM at authoring time that its brief was
unrunnable as written.

This leg fires when the dispatch text names a pytest invocation carrying
a bare DIRECTORY positional in imperative position -- the same shape R9
will refuse downstream -- and, on stdout, offers the better alternative
(name node ids or explicit file paths) and states plainly that a
dispatched agent cannot run the directory form and will narrow, so
verifying the breadth the brief named is the EM's own job afterwards. A
directory-scoped brief is NOT wrong -- an EM intending to verify breadth
itself post-dispatch has every right to write one -- so this leg is
strictly a design-as-offers nudge, never a gate.

Precedence -- deny wins. This leg is only reached when the identity deny
leg above did NOT already fire (`matches`/`imperative` empty); a dispatch
that is ALSO suite-shaped-imperative gets the deny, not the advisory, and
the advisory is never emitted alongside a deny for the same tool call.

Classification is 100% claude-klabauter's, same boundary as the deny leg above:
`coordinator_core.bash_guards.check_test_suite_invocation.
classify_text_precision`, returning `PrecisionMatch` (`detected`,
`matched_text`, `span`, `position`, `directory_args`). This file adds
ZERO grammar of its own -- it reads `.position` and `.directory_args`
exactly as the deny leg reads `SuiteMatch.position`.

`position` handling -- gate on "imperative" only, identical rationale to
the deny leg: a brief quoting or negating a directory-scoped command in
its authoring prose is not an instruction to run one.

Fail-open, silently, on every one of: claude-klabauter unresolvable; the API not
yet importable (`classify_text_precision` may not have landed in the
sibling checkout yet -- an `ImportError`/`AttributeError` degrades to
silent allow, same as every other infra failure in this file, never a
crash); `classify_text_precision` itself raising; no directory_args on
the matched item. A broken/half-landed sibling API must never brick a
dispatch, exactly like the deny leg's own contract.

Override hatches -- reused, not reimplemented. All three existing
hatches (env var, sentinel file, in-prompt marker) are checked earlier in
`main()`, before dispatch text is even classified for either leg; a
dispatch that already carries one of them never reaches this leg either,
so there is no separate override surface to build here.

Envelope shape -- advisory, NOT deny: `{"hookSpecificOutput":
{"hookEventName": "PreToolUse", "additionalContext": "<msg>"}}` on
stdout, exit 0. Never `permissionDecision: "deny"`. Mirrors
`nudge-em-code-dispatch.py` / `nudge-multiwave-workflow.py`'s advisory
contract, per `coordinator/docs/pretooluse-deny-contract.md`.

Spec backlink: cross-repo/inbox/2026-07-28-example-market-data-repo-em-dispatched-agent-scoped-test-breadth.md
Spec backlink: docs/plans/2026-07-23-dr-088-ladder-enforcement-layers.md § C8
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, NamedTuple, Optional


_OVERRIDE_ENV = "COORDINATOR_OVERRIDE_DISPATCH_SUITE_GUARD"
_OVERRIDE_SENTINEL_NAME = ".coordinator-override-dispatch-suite-guard"

# Deliberately hyphenated -- see module docstring's "Override" section,
# hatch 1. Anchored to line start (allowing leading whitespace),
# case-sensitive, requires a non-empty (non-whitespace-only) reason.
_OVERRIDE_MARKER_PREFIX = "COORDINATOR-OVERRIDE-DISPATCH-SUITE-GUARD:"
_OVERRIDE_MARKER_RE = re.compile(
    r"^[ \t]*" + re.escape(_OVERRIDE_MARKER_PREFIX) + r"[ \t]*(\S.*)?$",
    re.MULTILINE,
)


class _DispatchText(NamedTuple):
    """Return shape for `_extract_dispatch_text` -- pairs the extracted
    text with whether it is text the DISPATCHING EM authored in this very
    tool call (Agent `prompt`, Workflow inline `script`) versus text read
    from a `scriptPath` file on disk. This flag is the ONLY thing that
    gates the in-prompt override marker (hatch 1) -- a file on a shared
    branch is attacker-influenceable by anyone with write access, so the
    marker must never be honored from `caller_authored=False` text. Kept
    as a distinct field (not folded into a merged string) specifically so
    a later refactor cannot silently lose the distinction -- see the
    module docstring's "Override" section, hatch 1.
    """

    text: str
    caller_authored: bool


_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from _message_envelope import compose, render  # noqa: E402

#: Wiki section carrying the relocated deny/advisory explanation -- the
#: three override hatches, the remediation-vs-reword distinction, and the
#: directory-breadth advisory rationale all live there now, not restated
#: in the deny/advisory prose. See docs/plans/2026-08-02-guard-message-
#: character-cap.md § C6.
_WIKI_ANCHOR = (
    "coordinator/docs/wiki/guard-message-concision.md"
    "#dispatch-suite-guard-overrides-and-directory-breadth-advisory"
)


def _git_root() -> "Optional[str]":
    """Best-effort repo-root resolution for the sentinel-file override,
    WITHOUT shelling out to git (this hook is zero-spawn on the hot path,
    same constraint as _engine_root.py). Walks upward from the session's
    cwd -- NOT this script's own on-disk location (that would resolve
    the coordinator *plugin source tree*, which is only the same repo as
    the session's working tree in the DoE-claude dogfood case; anywhere
    else it silently points the sentinel lookup at the wrong repo). This
    mirrors `_classify()`'s own `cwd=os.getcwd()` assumption two
    functions below. Any failure returns None -- the sentinel check is
    then skipped, never crashed on.
    """
    try:
        cur = Path(os.getcwd())
        for _ in range(8):
            if (cur / ".git").exists():
                return str(cur)
            if cur.parent == cur:
                break
            cur = cur.parent
    except Exception:
        return None
    return None


def _sentinel_override_active() -> bool:
    root = _git_root()
    if not root:
        return False
    try:
        return os.path.isfile(os.path.join(root, _OVERRIDE_SENTINEL_NAME))
    except Exception:
        return False


def _extract_dispatch_text(tool_name: str, tool_input: "dict[str, Any]") -> "_DispatchText":
    """Pull whatever text the dispatching call is handing the subagent,
    across the two matcher shapes this hook covers. Returns a
    `_DispatchText(text, caller_authored)` pair -- `caller_authored` is
    True only for text the dispatching EM typed directly into THIS tool
    call (Agent `prompt`, Workflow inline `script`), and False for text
    read from a `scriptPath` file on disk. `_classify()` is given `.text`
    either way (the classifier still sees the full text regardless of
    provenance); only the override-marker check at hatch 1 consults
    `.caller_authored`.

    Agent tool_input: `prompt` (the dispatch brief).
    Workflow tool_input: `script` (inline orchestration script -- its
    string/template literals carry per-agent prompts), falling back to a
    file read at `scriptPath` when `script` is empty (mirrors
    block-workflow-unmodeled-agent.py's own scriptPath handling). A
    `name:`-only saved-workflow launch carries no script contents in the
    payload and is out of scope here, same as that hook.

    Known limitation (narrow): `classify_text` was written for markdown
    inline-code spans and has no notion of JS template-literal syntax --
    a raw `script` string is JS, not markdown. A SINGLE-LINE JS template
    literal (`` agent({prompt: `Run: pytest -v`}) `` all on one line) gets
    its backtick-delimited span read as markdown `inline_code`, which
    never satisfies the `position == "imperative"` deny gate below, even
    when the quoted content is a genuinely imperative suite command.
    Multi-line template literals (the common shape for a real dispatch
    brief) are unaffected -- the inline-code regex excludes newlines, so
    multi-line content falls through to the bare-line imperative pass and
    IS still caught. Not fixed here: closing it needs either stripping/
    normalizing JS template-literal delimiters before this text reaches
    `classify_text`, or routing the Workflow `script` case through
    per-argument classification instead of prose-oriented `classify_text`
    -- both are extraction-side (this file's) concerns, not a reason to
    fork claude-klabauter's classifier grammar.
    """
    if tool_name == "Agent":
        prompt = tool_input.get("prompt", "") or ""
        text = prompt if isinstance(prompt, str) else ""
        return _DispatchText(text, caller_authored=True)

    # tool_name == "Workflow"
    script = tool_input.get("script", "") or ""
    if isinstance(script, str) and script:
        return _DispatchText(script, caller_authored=True)

    script_path = tool_input.get("scriptPath", "") or ""
    if not script_path or not isinstance(script_path, str):
        return _DispatchText("", caller_authored=False)
    try:
        if not os.path.isfile(script_path):
            return _DispatchText("", caller_authored=False)
        with open(script_path, "r", encoding="utf-8", errors="replace") as fh:
            return _DispatchText(fh.read(1_000_000), caller_authored=False)
    except Exception:
        return _DispatchText("", caller_authored=False)


def _has_override_marker(text: str) -> bool:
    """True iff `text` contains a `COORDINATOR-OVERRIDE-DISPATCH-SUITE-
    GUARD:` line (anchored to line start, leading whitespace allowed)
    carrying a non-empty, non-whitespace-only reason. Caller is
    responsible for only invoking this on `caller_authored=True` text --
    see `_DispatchText` and the module docstring's "Override" section,
    hatch 1.
    """
    for match in _OVERRIDE_MARKER_RE.finditer(text):
        reason = match.group(1)
        if reason and reason.strip():
            return True
    return False


def _classify(text: str) -> "list[Any]":
    """Resolve claude-klabauter root, import the shared classifier, call it.
    Returns [] (never raises) on any infra failure -- the caller treats
    an empty list identically to "no matches found" (silent allow),
    which is the correct fail-open behavior for this guard.
    """
    try:
        from _engine_root import resolve_claude_klabauter_root  # noqa: E402
    except Exception:
        return []

    try:
        claude_klabauter_root = resolve_claude_klabauter_root()
    except Exception:
        claude_klabauter_root = None

    if not claude_klabauter_root:
        return []

    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)

    try:
        from coordinator_core.bash_guards.check_test_suite_invocation import (  # noqa: E402
            classify_text,
        )
    except Exception:
        return []

    try:
        return list(classify_text(text, cwd=os.getcwd()))
    except Exception:
        return []


def _classify_precision(text: str) -> "list[Any]":
    """Resolve claude-klabauter root, import the shared PRECISION classifier, call it.
    Returns [] (never raises) on any infra failure, INCLUDING the sibling
    API not existing yet (`classify_text_precision` may not have landed in
    the sibling checkout) -- an empty list is treated identically to "no
    directory-scoped match found" by the caller, i.e. silent allow / no
    advisory. See the module docstring's "ADVISORY LEG" section.
    """
    try:
        from _engine_root import resolve_claude_klabauter_root  # noqa: E402
    except Exception:
        return []

    try:
        claude_klabauter_root = resolve_claude_klabauter_root()
    except Exception:
        claude_klabauter_root = None

    if not claude_klabauter_root:
        return []

    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)

    try:
        from coordinator_core.bash_guards.check_test_suite_invocation import (  # noqa: E402
            classify_text_precision,
        )
    except Exception:
        # Covers both "claude-klabauter's classify_text_precision module is missing"
        # and "the sibling checkout hasn't shipped the symbol yet" --
        # ImportError either way, fail open.
        return []

    try:
        return list(classify_text_precision(text, cwd=os.getcwd()))
    except Exception:
        return []


def _precision_advisory_envelope(text: str) -> "Optional[dict[str, Any]]":
    """Build the advisory `hookSpecificOutput` envelope for a directory-
    scoped imperative match, or None if there is nothing to advise on.
    Never raises -- any unexpected shape from `_classify_precision`'s
    return value (missing `.directory_args`, missing `.matched_text`, etc.)
    degrades to None (silent allow), same fail-open contract as the rest
    of this file.
    """
    try:
        precision_matches = _classify_precision(text)
        imperative = [
            m for m in precision_matches if getattr(m, "position", "") == "imperative"
        ]
        directory_hits = [m for m in imperative if getattr(m, "directory_args", None)]
        if not directory_hits:
            return None

        hit = directory_hits[0]
        detected = getattr(hit, "detected", "a test-runner invocation")
        directory_args = list(getattr(hit, "directory_args", []) or [])
        dirs_desc = ", ".join(repr(d) for d in directory_args) or "a directory"

        message = compose(
            f"{detected} targets directory {dirs_desc} -- DR-088 R9 "
            "refuses it downstream, so name file paths or node ids "
            "instead.",
            anchor=_WIKI_ANCHOR,
        )
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": render(message),
            }
        }
    except Exception:
        return None


def _compose_precision_deny_reason(
    tool_name: str, detected: str, tier: str, matched_text: str, remediation: str
) -> str:
    """Pure composer for the imperative-suite deny path, extracted from the
    inline f-string previously built directly in `main()`. Routes through
    `_message_envelope.compose` -- the prose it carries is deliberately
    short; the full three-hatch override rationale, the remediation-vs-
    reword distinction, and the classifier-defect note all relocated to
    `_WIKI_ANCHOR` (see the relocation fragment this hook's conversion
    produced)."""
    del matched_text, remediation  # now covered by the wiki anchor, not restated per-deny
    message = compose(
        f"{tool_name}: Tier-{tier} suite command ({detected}) -- add "
        f"{_OVERRIDE_MARKER_PREFIX} <reason> to override.",
        anchor=_WIKI_ANCHOR,
    )
    return render(message)


def main() -> int:
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""
    if not raw:
        return 0

    if os.environ.get(_OVERRIDE_ENV, "") == "1":
        return 0
    if _sentinel_override_active():
        return 0

    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    tool_name = payload.get("tool_name", "")
    if tool_name not in ("Agent", "Workflow"):
        return 0

    # Only the dispatching EM's own Agent/Workflow call is guarded, never
    # a subagent's nested dispatch (mirrors block-workflow-unmodeled-agent.py).
    if "agent_id" in payload:
        return 0

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}

    dispatch = _extract_dispatch_text(tool_name, tool_input)
    text = dispatch.text
    if not text:
        return 0

    # Hatch 1 (in-prompt marker) -- payload-dependent, so it runs here,
    # after tool_input parsing, unlike the payload-independent env-var
    # and sentinel checks above. Only honored in caller-authored text --
    # see _DispatchText / _has_override_marker docstrings.
    if dispatch.caller_authored and _has_override_marker(text):
        return 0

    matches = _classify(text)
    imperative = [m for m in matches if getattr(m, "position", "") == "imperative"] if matches else []
    if not imperative:
        # Deny leg didn't fire -- try the advisory leg (directory-breadth
        # nudge). Deny wins by construction: we only reach here once the
        # deny leg above has already declined to fire for this dispatch.
        envelope = _precision_advisory_envelope(text)
        if envelope is None:
            return 0
        sys.stdout.write(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")))
        sys.stdout.write("\n")
        return 0

    hit = imperative[0]
    detected = getattr(hit, "detected", "a test-suite command")
    tier = getattr(hit, "tier", "U")
    matched_text = getattr(hit, "matched_text", "")
    remediation = getattr(
        hit,
        "remediation",
        "Remove the suite invocation from this dispatch prompt, or path-scope it "
        "to a Tier-T subset before dispatching.",
    )

    reason = _compose_precision_deny_reason(tool_name, detected, tier, matched_text, remediation)

    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    sys.stdout.write(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
