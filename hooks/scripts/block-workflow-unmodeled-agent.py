#!/usr/bin/env python3
"""PreToolUse hook (matcher: Workflow): closes the un-modeled agent() cost trap
documented in coordinator/docs/wiki/em-operating-model/workflow-orchestration.md § "Model
selection: Sonnet by default, Opus is PM-gated". That doc's own
negative-spec says: "an un-modeled agent() in an Opus session is a defect,
not a shortcut... there is no warning, no gate, and no retry." This hook
is the gate.

Originally ported naked-Python (W5 straggler port from a now-retired bash
oracle) -- no reusable engine-repo op exists for this hook's per-call-site
agent()/model: string-aware parse, so this is a SELF-CONTAINED hook, not a
thin engine-repo stub -- zero Git-Bash cold-start per Workflow launch on Windows).

Danger condition (deliberately narrow -- an offer, not a nag): the EM's main
loop is running on an OPUS-tier model AND launches an inline-script
Workflow whose agent() calls carry no model: override. Every un-modeled
agent() then silently inherits Opus, running every worker at ~4x cost with
zero visible signal in the script or the tool output.

Behavior:
  - AGENT_N agent( call sites; MODELED_N is the subset of those call sites
    whose OWN balanced argument list contains a model: key (per-call-site
    attribution, not a whole-script model: substring count -- see Known
    limitations below), in the effective script (inline tool_input.script,
    or the file at tool_input.scriptPath when script is empty).
  - AGENT_N >= 1 AND MODELED_N == 0 (no call site carries a model: key):
    each such call site's OWN agentType: (if any) is resolved against its
    agent definition (coordinator/agents/<name>.md, coordinator: namespace
    stripped) and rung on THAT definition's frontmatter model:, never on
    whether a key was merely present at the call site -- see
    `_resolve_call_site_tier()`. If every call site resolves this way
    (whether to sonnet or opus -- an asserted agentType is self-enforcing,
    so a resolved-opus call site is a declared cost, not a silent one):
    silent allow, and no agent-definition file is read for any OTHER path
    through this hook. If any call site's agentType is absent, non-literal,
    or names no resolvable definition: DENY (Form A
    permissionDecision:"deny"), message leads with the fix (add model:
    'sonnet', or a defined agentType:, to each call) before naming the
    violation, and names the override + PM-gate escape hatches.
  - AGENT_N >= 1 AND 0 < MODELED_N < AGENT_N (partial/mixed coverage -- some
    call sites modeled, some not, could be intentional per-agent tiering):
    WARN via additionalContext advisory only, never a deny.
  - Otherwise (MODELED_N >= AGENT_N, i.e. every call site modeled, or no
    agent( calls at all): silent allow.

Fail-open guards (all exit 0 silent, in order):
  - COORDINATOR_OVERRIDE_WORKFLOW_MODEL_GUARD=1 set, OR a repo-root sentinel
    file `.coordinator-override-workflow-model-guard` exists (2026-07-23 F2
    fix -- the env var is set once at process-launch time and a hook
    inherits the harness's env, so a live session cannot set it into its
    own already-running hook; `touch <repo-root>/.coordinator-override-
    workflow-model-guard` is the session-reachable equivalent). See
    `_sentinel_override_active()`.
  - tool_name != "Workflow".
  - subagent/nested call (payload carries "agent_id") -- only the main-loop
    EM's own Workflow launches are guarded, never a subagent's.
  - Session model is undetectable, or detectable but not Opus-tier. This
    hook fires ONLY in the exact danger condition; any detection failure
    fails OPEN rather than risk wedging a legitimate Sonnet-session launch.
  - The Workflow call uses `name:` (saved-workflow launch by name) -- the
    payload carries no script contents in that shape, so it's unparseable
    here and remains out of scope for this hook. `scriptPath` launches ARE
    now validated (the file at that path is read and run through the same
    count/deny logic as an inline script) -- a missing/unreadable file at
    that path fails OPEN (silent allow), consistent with every other
    detection-failure guard below.

Model detection mirrors the folded-in context-pressure advisory's approach
(now part of postuse-advisory-dispatch.py): read
transcript_path from the PreToolUse payload, find the first literal
"model":"claude-..." occurrence, and match against *opus*. Unlike
that advisory's soft-threshold use (a wrong match just
mis-sizes a byte threshold, low consequence), a wrong-here result changes
DENY vs allow -- the detection failure mode is deliberately fail-open
(undetected/non-opus -> silent allow), which biases toward false-negatives
over false-positives; this is a deliberate tradeoff (never wedge a
legitimate launch), documented at the fail-open guards list above.

Known limitations (v2) -- string-literal-aware as of the 2026-07-21 fix:
  - `agent(` occurrences and the paren/brace depth walk are now
    string-literal-aware (see `_string_mask()`): single-quote,
    double-quote, and backtick template-literal spans (with `${...}`
    interpolation tracked back to real, structural code, including
    strings/templates nested inside the interpolation) are excluded from
    depth/brace counting and from `agent(` matching. A real-world Workflow
    script whose multi-line backtick prompts contain unbalanced `(`/`)`,
    fenced code examples, or the literal substring `agent(` in prose no
    longer desyncs the per-call-site parse -- this was the confirmed
    defect (a reported 11-vs-9 count against a ground truth of 14-vs-14,
    and false WARNs that trained operators to ignore the guard on the run
    where it mattered). `sub_agent(`/`myagent(`-style compound identifiers
    (which, unlike capitalized `subAgent(`/`myAgent(`, DO contain the
    literal lowercase substring `agent(` and would otherwise be
    miscounted) are also no longer miscounted as `agent(` call sites:
    the character immediately preceding a candidate `agent(` match must
    not be an identifier character (letter, digit, `_`, `$`).
  - Comment-stripping (`_strip_comments()`) shares the same string mask:
    a `//` or `/*` occurring inside a string literal (a URL, a regex-like
    substring, etc.) is no longer treated as a comment start.
  - `model:` attribution remains PER-CALL-SITE: for each real (non-string,
    non-identifier-suffixed) `agent(` occurrence, the hook extracts that
    call's own balanced argument list (tracking paren depth from the
    opening `(` to its matching `)`, now skipping string-literal spans)
    and only counts a `model:` found INSIDE that call's own arguments, at
    brace depth == 1 relative to the call's own top-level paren depth
    (i.e. a direct key of the options object passed to agent(), not
    nested one level deeper inside a schema/meta/opts sub-object). An
    options object passed through a helper call after the prompt argument
    (`agent(p, withRole(r, { model: 'opus' }))`) counts the same way: a
    direct key of an object literal at brace depth 1 in its own paren frame.
  - Residual limitation: this is a string-aware depth-counting pass, not
    a full JS parser. JS regex literals (`/.../flags`) are recognized by
    the previous significant token and masked like strings (see
    `_scan_masks()`); the regex-vs-division call uses that token only, so
    exotic cases (`}` followed by division) can misread. Any residual
    desync still fails toward the documented
    unbalanced-script fail-safe (attribute nothing for that call site,
    guaranteed forward progress) rather than a crash or hang.
  - AGENT_N counting advances the top-level scan past an entire outer
    call's balanced region once processed -- an `agent(` occurrence
    nested as an argument to another `agent()` call (e.g.
    `agent(subAgent(...))`) is implicitly consumed by the outer call's
    scan and never independently counted. Low practical risk since
    agent() calls are dispatch calls, not typically values passed to
    other agent() calls.

Ternary-undefined fix (2026-07-22): a call site whose `model:` key is
present but whose VALUE resolves to `undefined`/`null` (e.g.
`model: COND.includes(x) ? undefined : 'sonnet'`) previously counted as
modeled purely because the literal token `model:` was found -- the
value was never inspected. At runtime that ternary can hand back
`undefined`, and an `undefined` `model:` in the Workflow tool's own
options object is equivalent to omitting `model:` entirely: the agent
silently inherits the session model. `_extract_model_value()` now reads
forward from the matched `model:` to the end of its value expression
(the next top-level `,`/`}`/`)`, tracking local paren/brace depth so a
ternary's own `(`/`{` don't truncate it early) and a bare `undefined` or
`null` token (word-boundary, so `undefinedThing`/`nullable` don't
false-positive) in that value un-credits the call site -- it is treated
identically to a call with no `model:` key at all. A plain identifier
value (`model: myModelVar`) is untouched by this fix and remains
credited as modeled -- unknown-but-set is the pre-existing
mixed-coverage advisory territory, not newly denied.

Spec backlink: cross-repo/inbox/2026-07-13-example-store-repo-em-workflow-sonnet-default-guard.md
Source: naked-Python original -- no bash oracle exists for this hook (the
W5-straggler-port docstring above refers to the initial 2026-07-13 port;
there is no `block-workflow-unmodeled-agent.sh` in this repo to diff
against for subsequent fixes).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
_LIB_DIR = _SCRIPTS_DIR.parents[1] / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from _message_envelope import compose, render  # noqa: E402
from frontmatter_scan import read_text, scan_frontmatter  # noqa: E402
from _win_portability import (  # noqa: E402
    no_console_spawn_kwargs,
    noninteractive_git_env,
)
try:
    from _git_root_walk import git_root_walk as _git_root_walk  # noqa: E402
except Exception:
    # Defensive fallback -- a deploy missing its sibling _git_root_walk.py
    # must still fail open to the subprocess rung below, not crash on import.
    def _git_root_walk() -> str | None:
        return None

#: Wiki section carrying the relocated override-hatch explanation (env var,
#: sentinel file, PM-gate) -- see this hook's conversion relocation fragment
#: at state/relocations/guard-message-cap/block-workflow-unmodeled-agent.py.md.
_WIKI_ANCHOR = (
    "coordinator/docs/wiki/guards/guard-message-concision.md"
    "#workflow-model-guard-override-hatches-and-pm-gate"
)


_IDENTIFIER_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$"
)


_REGEX_PRECEDING_KEYWORDS = frozenset(
    {"return", "typeof", "case", "in", "of", "delete", "void", "throw",
     "new", "else", "do", "instanceof", "yield", "await"}
)


def _regex_allowed(last_sig: str, last_word: str) -> bool:
    """True when a `/` after the previous significant token opens a regex
    literal rather than a division. `last_sig` is the previous token's last
    char ("" at start, "a" for an identifier/number, "'" for a closed
    string/regex)."""
    if last_sig == "":
        return True
    if last_sig == "a":
        return last_word in _REGEX_PRECEDING_KEYWORDS
    return last_sig not in (")", "]", "'")


def _regex_literal_end(script: str, start: int) -> int:
    """Index just past the regex literal (body + flags) opening at
    `script[start] == '/'`, or -1 when the line ends before a closing `/`."""
    n = len(script)
    i = start + 1
    in_class = False
    while i < n:
        ch = script[i]
        if ch == "\n":
            return -1
        if ch == "\\":
            i += 2
            continue
        if in_class:
            if ch == "]":
                in_class = False
        elif ch == "[":
            in_class = True
        elif ch == "/":
            i += 1
            while i < n and script[i] in _IDENTIFIER_CHARS:
                i += 1
            return i
        i += 1
    return -1


def _scan_masks(script: str) -> "tuple[bytearray, bytearray]":
    """Single-pass, string-AND-comment-aware JS scanner -- returns
    `(string_mask, comment_mask)`, one bit per character of `script`.

    `string_mask[i]` is 1 where the char at index `i` is part of a
    string-literal payload (delimiter, content, or escape): single-quote
    `'...'`, double-quote `"..."`, or backtick template-literal
    `` `...` `` forms, with backslash-escaped delimiters (`\\'`, `\\"`,
    `` \\` ``, `\\\\`) never prematurely ending a string. Backtick
    `${...}` interpolation is tracked back to real code: parens and
    braces inside an interpolation are structural (mask 0), and an
    interpolation can itself contain nested strings/templates, masked
    recursively via the context stack.

    `comment_mask[i]` is 1 where the char is part of a `//` line comment
    or `/* */` block comment.

    THE FIX (2026-07-23): comment recognition and string recognition run
    in ONE pass sharing ONE stack, rather than as two independently-run
    scans (`_strip_comments()` calling a string-only `_string_mask()` to
    decide where `//`/`/*` may start). The two-pass form desynced on
    ordinary English-prose apostrophes inside a `//` comment (e.g. "this
    script's twin", "don't crash") -- the string-only scan has no notion
    of "inside a comment", so it read that apostrophe as opening a real
    single-quoted string, which then ran on (consuming subsequent `//`
    comment starts, real code, and even real `agent(` call sites) until
    it happened to hit some later matching quote character elsewhere in
    the file. Confirmed against `distill-harvest.workflow.js`: a JSDoc
    block containing "script's twin" and "don't crash" upstream of both
    real `agent()` call sites drove the string-only pre-scan into a
    runaway single-quote span that swallowed both calls, reporting
    (AGENT_N=1, MODELED_N=0) against a ground truth of (2, 2). A `//`/`/*`
    can only start while genuinely in `code`/`interp` state (never inside
    a string), and a quote character encountered while already inside a
    comment never opens a string -- the single shared stack makes both
    facts true by construction instead of by two scans agreeing by luck.

    Regex literals: a `/` met in code state where the previous significant
    token permits a regex (start, an operator/punctuator other than `)`/`]`,
    or a keyword such as `return`/`typeof`) opens a regex literal. Its body
    (honoring `\\` escapes and `[...]` classes) and flags are masked as
    string payload, so quotes and brackets inside it never open string
    spans or move paren depth. A `/` after an operand (identifier, number,
    `)`, `]`, a closed string) is division. A candidate regex that reaches
    a newline unclosed is treated as division instead.

    Not a full JS parser -- the regex/division call uses the previous
    token only (`}` is read as permitting a regex).
    """
    n = len(script)
    string_mask = bytearray(n)
    comment_mask = bytearray(n)
    stack = [("code", 0)]
    i = 0
    last_sig = ""
    last_word = ""
    prev_len = 1
    while i < n:
        kind, depth = stack[-1]
        if len(stack) < prev_len:
            last_sig, last_word = "'", ""
        prev_len = len(stack)

        if kind in ("code", "interp"):
            two = script[i:i + 2]
            if two == "//":
                comment_mask[i] = 1
                i += 1
                while i < n and script[i] != "\n":
                    comment_mask[i] = 1
                    i += 1
                continue
            if two == "/*":
                comment_mask[i] = 1
                comment_mask[i + 1] = 1
                end_idx = script.find("*/", i + 2)
                end = end_idx + 2 if end_idx != -1 else n
                for k in range(i + 2, end):
                    comment_mask[k] = 1
                i = end
                continue

            ch = script[i]
            if ch == "'":
                string_mask[i] = 1
                stack.append(("squote", 0))
                i += 1
                continue
            if ch == '"':
                string_mask[i] = 1
                stack.append(("dquote", 0))
                i += 1
                continue
            if ch == "`":
                string_mask[i] = 1
                stack.append(("template", 0))
                i += 1
                continue
            if ch == "/" and _regex_allowed(last_sig, last_word):
                end = _regex_literal_end(script, i)
                if end != -1:
                    for k in range(i, end):
                        string_mask[k] = 1
                    i = end
                    last_sig, last_word = "'", ""
                    continue
            if ch in _IDENTIFIER_CHARS:
                j = i + 1
                while j < n and script[j] in _IDENTIFIER_CHARS:
                    j += 1
                last_sig, last_word = "a", script[i:j]
                i = j
                continue
            if kind == "interp":
                if ch == "{":
                    stack[-1] = ("interp", depth + 1)
                elif ch == "}":
                    if depth == 0:
                        stack.pop()
                    else:
                        stack[-1] = ("interp", depth - 1)
            if not ch.isspace():
                last_sig, last_word = ch, ""
            i += 1
            continue

        if kind in ("squote", "dquote"):
            quote_char = "'" if kind == "squote" else '"'
            ch = script[i]
            string_mask[i] = 1
            if ch == "\\" and i + 1 < n:
                string_mask[i + 1] = 1
                i += 2
                continue
            if ch == quote_char:
                stack.pop()
            i += 1
            continue

        # kind == "template"
        ch = script[i]
        if ch == "\\" and i + 1 < n:
            string_mask[i] = 1
            string_mask[i + 1] = 1
            i += 2
            continue
        if ch == "`":
            string_mask[i] = 1
            stack.pop()
            i += 1
            continue
        if ch == "$" and i + 1 < n and script[i + 1] == "{":
            string_mask[i] = 1
            stack.append(("interp", 0))
            i += 2
            continue
        string_mask[i] = 1
        i += 1

    return string_mask, comment_mask


def _string_mask(script: str) -> bytearray:
    """Per-character JS string-literal mask -- 1 where the char at that
    index is part of a string-literal payload (delimiter, content, or
    escape), 0 where it is real structural code. See `_scan_masks()` for
    the shared scanner; this wrapper is retained as the standalone entry
    point `_count_agent_modeled()` calls on the already-comment-stripped
    buffer (no comment content survives at that point, so the
    string-only view is sufficient there).
    """
    return _scan_masks(script)[0]


def _strip_comments(script: str) -> str:
    """String-AND-comment-aware // and /* */ stripper.

    Uses `_scan_masks()` so a `//` or `/*` occurring inside a string
    literal (a URL, a regex-like substring, etc.) is never treated as a
    comment start, AND a quote character occurring inside a real comment
    (an English-prose apostrophe) is never treated as a string opener --
    see `_scan_masks()`'s docstring for the desync this single shared
    scan closes. Newlines consumed by a stripped block comment are
    preserved so line count is unaffected -- the stripped copy is used
    only for counting agent(/model:, never for execution.
    """
    _, comment_mask = _scan_masks(script)
    n = len(script)
    out = []
    for i in range(n):
        if comment_mask[i]:
            if script[i] == "\n":
                out.append("\n")
            continue
        out.append(script[i])
    return "".join(out)


# Call names counted as agent() call sites: the runtime hook, plus a workflow's pass-through counting
# wrapper (distill-harvest's countedAgent, which tallies calls against the runtime's 1000-agent cap).
# A wrapper's call sites carry the model: keys, so they are the sites the guard must see.
_AGENT_CALL_RE = re.compile(r"(?:countedAgent|agent)\(")
# A wrapper's own declaration (`function countedAgent(prompt, opts)`) is not a call site.
_FUNCTION_DECL_BEFORE = re.compile(r"\bfunction\s+$")


def _walk_agent_calls(buf: str, mask: "bytearray") -> "list[tuple[bool, str | None]]":
    """Per-call-site agent(/model:/agentType: attribution -- string-aware
    paren/brace depth walk (see module docstring "Known limitations" for
    the documented residual edges). Shared by `_count_agent_modeled()`
    (the pre-existing agent_n/modeled_n contract every caller and test
    already relies on) and `_count_agent_modeled_with_types()` (the
    agentType-resolution entry point `main()` uses), so both read the
    identical string-mask and identifier-boundary discipline off one walk
    rather than two independently-maintained copies.

    Returns one `(has_direct_model, agent_type)` tuple per real,
    successfully-balanced `agent(` call site, in source order.
    `agent_type` is the call's own captured `agentType:` value (already
    unwrapped from its quoting -- see `_extract_string_literal()`), or
    `None` when the call carries no `agentType:` key, a masked/decoy one,
    or a value that is not a plain string literal. An unbalanced call
    site (truncated/malformed script) contributes no tuple at all --
    matching `_count_agent_modeled()`'s pre-existing treatment of that
    case as a detection failure, not a call site.
    """
    n = len(buf)
    i = 0
    calls: "list[tuple[bool, str | None]]" = []

    while i < n:
        m = _AGENT_CALL_RE.search(buf, i)
        if m is None:
            break
        pos = m.start()
        if (mask[pos] or (pos > 0 and buf[pos - 1] in _IDENTIFIER_CHARS)
                or _FUNCTION_DECL_BEFORE.search(buf[max(0, pos - 24):pos])):
            i = pos + 1
            continue
        call_start = pos
        paren_open = m.end() - 1  # index of the "(" character

        depth = 0
        brace_depth = 0
        # Brace depth per paren frame, and whether the prompt argument is behind us. An options
        # object handed through a helper -- `agent(prompt, withRole(r, { model: 'opus' }))` --
        # carries its `model:` as a direct key one paren frame deeper; crediting only frame 1
        # denied every plan-blitz fire that pins a model on each call.
        frame_braces = {1: 0}
        past_prompt = False
        j = paren_open
        close_idx = -1
        has_direct_model = False
        agent_type: "str | None" = None
        while j < n:
            if mask[j]:
                j += 1
                continue
            ch = buf[j]
            if ch == "(":
                depth += 1
                frame_braces[depth] = 0
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    close_idx = j
                    break
            elif ch == "{":
                frame_braces[depth] = frame_braces.get(depth, 0) + 1
                if depth == 1:
                    brace_depth += 1
            elif ch == "}":
                frame_braces[depth] = frame_braces.get(depth, 0) - 1
                if depth == 1:
                    brace_depth -= 1
            elif ch == "," and depth == 1 and brace_depth == 0:
                past_prompt = True
            elif (
                ch == "m"
                and depth >= 2
                and past_prompt
                and frame_braces.get(depth) == 1
                and buf[j:j + 6] == "model:"
                and not any(mask[j:j + 6])
                and not (j > 0 and not mask[j - 1] and buf[j - 1] in _IDENTIFIER_CHARS)
            ):
                value = _extract_model_value(buf, mask, j + 6, n)
                masked_value = "".join(
                    ch2 if not mask[j + 6 + idx] else " " for idx, ch2 in enumerate(value)
                )
                if not _UNDEFINED_NULL_RE.search(masked_value):
                    has_direct_model = True
            elif ch == "m" and depth == 1 and brace_depth == 1:
                # Identifier-boundary guard,
                # symmetric with the `agent(` match above (line 277), so a key
                # ending in the literal substring "model:" (base_model:,
                # submodel:, usemodel:) is not miscredited as a real `model:`
                # key.
                if (
                    buf[j:j + 6] == "model:"
                    and not any(mask[j:j + 6])
                    and not (j > 0 and not mask[j - 1] and buf[j - 1] in _IDENTIFIER_CHARS)
                ):
                    value = _extract_model_value(buf, mask, j + 6, n)
                    # Blank out masked
                    # (string-literal) characters before matching, so a
                    # literal string value containing the standalone word
                    # "undefined"/"null" (e.g. model: 'undefined-mode') is
                    # not mistaken for an actual undefined/null value.
                    masked_value = "".join(
                        ch2 if not mask[j + 6 + idx] else " "
                        for idx, ch2 in enumerate(value)
                    )
                    if not _UNDEFINED_NULL_RE.search(masked_value):
                        has_direct_model = True
            elif ch == "a" and depth == 1 and brace_depth == 1:
                # Same string-mask + identifier-boundary discipline as the
                # `model:` capture above -- a key merely ENDING in the
                # literal substring "agentType:" (baseAgentType:,
                # subAgentType:) must not be miscredited, and a masked
                # (string-literal) occurrence must not match either.
                if (
                    buf[j:j + 10] == "agentType:"
                    and not any(mask[j:j + 10])
                    and not (j > 0 and not mask[j - 1] and buf[j - 1] in _IDENTIFIER_CHARS)
                ):
                    raw_value = _extract_model_value(buf, mask, j + 10, n)
                    literal = _extract_string_literal(raw_value)
                    if literal is not None:
                        agent_type = literal
            j += 1

        if close_idx == -1:
            # Unbalanced (truncated/malformed script) -- attribute
            # nothing for this call, INCLUDING agent_n itself: an
            # unparseable call site is a detection failure, not a
            # confirmed violation, and must fail toward silent-allow
            # like every other detection-failure guard in this file --
            # never toward the DENY path (modeled_n == 0). The inner
            # scan above already ran from paren_open to n without
            # finding a close, so the remainder of the buffer holds no
            # further balanced content to rescan; jump straight to n
            # (guarantees forward progress in O(1) rather than
            # re-scanning the same unclosed tail on every subsequent
            # "agent(" match, which would be O(n^2) on pathological
            # input).
            i = n
            continue

        calls.append((has_direct_model, agent_type))
        i = close_idx + 1

    return calls


def _count_agent_modeled(buf: str) -> "tuple[int, int]":
    """Per-call-site agent(/model: attribution -- the pre-existing,
    agentType-blind contract every caller and test outside `main()` uses.
    Thin wrapper over `_walk_agent_calls()`; unchanged in effect from
    before that walk was extracted."""
    mask = _string_mask(buf)
    calls = _walk_agent_calls(buf, mask)
    agent_n = len(calls)
    modeled_n = sum(1 for has_model, _ in calls if has_model)
    return agent_n, modeled_n


def _count_agent_modeled_with_types(buf: str) -> "tuple[int, int, list[str | None]]":
    """`main()`'s own entry point: identical agent_n/modeled_n as
    `_count_agent_modeled()`, plus each call site's captured `agentType:`
    literal (or `None`) in source order. Capturing the literal costs no
    filesystem access -- it is a pure string extraction off the same walk
    -- so it is safe to always compute; only *resolving* a captured value
    against its agent definition (`_resolve_call_site_tier()`) is deferred
    to the branch in `main()` that would otherwise DENY.
    """
    mask = _string_mask(buf)
    calls = _walk_agent_calls(buf, mask)
    agent_n = len(calls)
    modeled_n = sum(1 for has_model, _ in calls if has_model)
    agent_types = [agent_type for _, agent_type in calls]
    return agent_n, modeled_n, agent_types


_UNDEFINED_NULL_RE = re.compile(r"\b(?:undefined|null)\b")


def _extract_model_value(buf: str, mask: "bytearray", start: int, n: int) -> str:
    """Read the value expression following a matched `model:` key, from
    `start` (immediately after the colon) to the end of that value -- the
    next top-level `,`, or the `}`/`)` that closes the enclosing
    object/call, whichever comes first. Tracks LOCAL paren/brace depth
    (relative to `start`, not the outer call's depth) so a ternary's own
    `(...)` (e.g. `COND.includes(x) ? undefined : 'sonnet'`) does not
    truncate the value early, and string-literal spans (per `mask`) never
    contribute to depth or terminator matching.
    """
    local_paren = 0
    local_brace = 0
    k = start
    while k < n:
        if mask[k]:
            k += 1
            continue
        ch = buf[k]
        if ch == "(":
            local_paren += 1
        elif ch == ")":
            if local_paren == 0:
                break
            local_paren -= 1
        elif ch == "{":
            local_brace += 1
        elif ch == "}":
            if local_brace == 0:
                break
            local_brace -= 1
        elif ch == "," and local_paren == 0 and local_brace == 0:
            break
        k += 1
    return buf[start:k]


def _extract_string_literal(value: str) -> "str | None":
    """Unwrap a plain single/double/backtick-quoted string literal
    captured as an `agentType:` value (e.g. `'coordinator:staff-eng'` ->
    `coordinator:staff-eng`). Returns `None` for anything that is not
    exactly a quoted literal -- a computed expression, a bare identifier,
    a ternary, an interpolated template -- since none of those can be
    resolved without executing the script. A `None` here is treated
    identically to "no agentType captured at all" by every caller: this
    hook never guesses at a value it cannot read statically.
    """
    trimmed = value.strip()
    if len(trimmed) < 2:
        return None
    quote = trimmed[0]
    if quote not in ("'", '"', "`") or trimmed[-1] != quote:
        return None
    inner = trimmed[1:-1]
    if "${" in inner:
        return None
    return inner


_COORDINATOR_AGENT_TYPE_PREFIX = "coordinator:"
_AGENTS_DIR = _SCRIPTS_DIR.parent.parent / "agents"
_ROSTER_FRAGMENT = _SCRIPTS_DIR.parent.parent / "contract" / "review-roster-fragment.json"
_REVIEW_SIGNALS = _SCRIPTS_DIR.parent.parent / "contract" / "review-signals.json"


def _tier_walked_agent_types() -> "frozenset[str]":
    """Every `agentType` the published review roster dispatches via the
    tier walk (`fragment['tiers'] -> tier['stages'] -> stage['agents']`).
    Fails CLOSED to the empty set on a missing or malformed fragment: an
    unreadable/malformed contract exempts nobody, denying a legitimate
    review workflow rather than admitting an arbitrary Opus fleet -- see
    `_signal_selected_agent_types()`, which shares this posture."""
    try:
        with open(_ROSTER_FRAGMENT, "r", encoding="utf-8") as fh:
            fragment = json.load(fh)
        tiers = fragment.get("tiers")
        if not isinstance(tiers, dict):
            return frozenset()
        names = set()
        for tier in tiers.values():
            if not isinstance(tier, dict):
                continue
            for stage in tier.get("stages") or []:
                if isinstance(stage, dict):
                    names.update(a for a in stage.get("agents") or [] if isinstance(a, str))
        return frozenset(names)
    except Exception:
        return frozenset()


def _signal_selected_agent_types() -> "frozenset[str]":
    """Every `selects` value in `contract/review-signals.json`'s `signals`
    map -- a signal-selectable agent has no tier membership of its own but
    is still dispatched by the review workflow when its signal fires, so it
    belongs in the same roster this guard exempts.

    Same fail-CLOSED-to-empty-set posture as `_tier_walked_agent_types()`,
    for the same reason: an unreadable/malformed contract exempts nobody,
    denying a legitimate review workflow rather than admitting an arbitrary
    Opus fleet."""
    try:
        with open(_REVIEW_SIGNALS, "r", encoding="utf-8") as fh:
            contract = json.load(fh)
        signals = contract.get("signals")
        if not isinstance(signals, dict):
            return frozenset()
        names = set()
        for signal in signals.values():
            if not isinstance(signal, dict):
                continue
            selects = signal.get("selects")
            if isinstance(selects, str):
                names.add(selects)
        return frozenset(names)
    except Exception:
        return frozenset()


def _rostered_agent_types() -> "frozenset[str]":
    """Every `agentType` the published review roster dispatches -- the
    union of the tier walk (`_tier_walked_agent_types()`) and every
    signal-selectable agent (`_signal_selected_agent_types()`).

    This is the review-workflow discriminator. It is not self-asserted: an
    agent is rostered by appearing in a version-controlled contract file
    that a reviewed commit had to change (either the tier fragment or
    `review-signals.json`), so a hand-written workflow cannot add itself by
    typing. `review-signals.json` is equally such a contract -- widening
    this union does not weaken that property.

    Each half fails CLOSED to the empty set independently on its own
    missing or malformed contract file -- a broken tier fragment does not
    also blank out a healthy signals contract, and vice versa.
    """
    return _tier_walked_agent_types() | _signal_selected_agent_types()


def _resolve_call_site_tier(agent_type: "str | None") -> "str | None":
    """Resolve one call site's captured `agentType:` literal to the model
    tier its OWN agent definition declares -- `coordinator/agents/
    <name>.md`'s frontmatter `model:` key, after stripping the
    `coordinator:` namespace. This is the sole filesystem read this
    hook's agentType path performs, and `main()` reaches it only from the
    branch that would otherwise DENY (a fully- or partially-modeled
    script never calls this).

    Returns the resolved tier, lowercased, or `None` on ANY resolution
    failure: no agentType captured, a name resolving to no file, or a
    definition with no frontmatter `model:` key. Every failure collapses
    to the same `None` the caller treats identically to "no tier
    declared at all" -- never a crash, never a silent pass.
    """
    if not agent_type:
        return None
    name = agent_type
    if name.startswith(_COORDINATOR_AGENT_TYPE_PREFIX):
        name = name[len(_COORDINATOR_AGENT_TYPE_PREFIX):]
    if not name:
        return None
    path = _AGENTS_DIR / f"{name}.md"
    model = scan_frontmatter(read_text(path)).get("model")
    if not isinstance(model, str) or not model:
        return None
    return model.lower()


_MODEL_LINE_RE = re.compile(r'"model"\s*:\s*"(claude-[^"]*)"')


def _detect_opus(transcript_path: str) -> bool:
    """Grep the first literal "model":"claude-..." occurrence -- same
    detection idiom as the context-pressure advisory folded into
    postuse-advisory-dispatch.py. Empirically verified
    against a real multi-subagent Opus-session transcript: subagent model
    IDs surface ONLY as "resolvedModel":"..." (a different key) or
    backslash-escaped \\"model\\":\\"...\\" inside echoed prompt text
    (nested JSON is always escaped) -- neither matches this unescaped
    "model":"claude-..." pattern, so the first match is reliably the
    main-loop EM's own model, never a subagent's.

    A-F7 (P2 perf): stream line-by-line and break on the first match
    (grep -m1 parity) instead of reading the ENTIRE transcript into memory
    -- this hook fires on every Workflow call, and transcripts can run to
    tens of MB. The model line appears very early in the transcript, so
    this is a small-prefix read in practice, not a full-file scan.
    """
    if not transcript_path or not os.path.isfile(transcript_path):
        return False
    try:
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m = _MODEL_LINE_RE.search(line)
                if m:
                    return "opus" in m.group(1).lower()
    except Exception:
        return False
    return False


def _fold_session_roster(transcript_path: str) -> "frozenset[str] | None":
    """Agent types the session can dispatch, folded from the transcript's
    `agent_listing_delta` attachments: `builtInTypes`, `builtInPluginTypes`
    and `addedTypes` join the roster, `removedTypes` leave it, and an
    `isInitial` delta restarts the fold. Returns None when the transcript is
    unreadable or carries no delta -- the caller treats that as "check did
    not run", never as an empty roster."""
    if not transcript_path or not os.path.isfile(transcript_path):
        return None
    roster: "set[str]" = set()
    seen = False
    try:
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if "agent_listing_delta" not in line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                att = obj.get("attachment") if isinstance(obj, dict) else None
                if not isinstance(att, dict) or att.get("type") != "agent_listing_delta":
                    continue
                seen = True
                if att.get("isInitial"):
                    roster.clear()
                for key in ("builtInTypes", "builtInPluginTypes", "addedTypes"):
                    vals = att.get(key)
                    if isinstance(vals, list):
                        roster.update(v for v in vals if isinstance(v, str))
                removed = att.get("removedTypes")
                if isinstance(removed, list):
                    roster.difference_update(v for v in removed if isinstance(v, str))
    except Exception:
        return None
    return frozenset(roster) if seen else None


def _required_agent_types(
    tool_input: dict, agent_types: "list[str | None]"
) -> "tuple[list[str], bool]":
    """`(types, declared)`: the types a launch needs -- `args.prepared.
    requiredAgentTypes` (inline, or in the stub's `argsFile` when the
    args-inline pre-stage left it unresolved) plus every literal call-site
    `agentType:` -- and whether the args declared any. Unreadable args
    contribute nothing."""
    args = tool_input.get("args")
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except Exception:
            args = None
    if isinstance(args, dict) and "prepared" not in args and isinstance(args.get("argsFile"), str):
        try:
            with open(args["argsFile"], "r", encoding="utf-8", errors="replace") as fh:
                args = json.load(fh)
        except Exception:
            args = None
    required: "list[str]" = []
    prepared = args.get("prepared") if isinstance(args, dict) else None
    listed = prepared.get("requiredAgentTypes") if isinstance(prepared, dict) else None
    if isinstance(listed, list):
        required.extend(t for t in listed if isinstance(t, str) and t)
    declared = bool(required)
    required.extend(t for t in agent_types if t)
    return sorted(set(required)), declared


def _compose_absent_roster_deny_reason(missing: "list[str]") -> str:
    """Deny composer for a launch naming agent types the session roster
    lacks -- the types are frozen at session start, so the fix is a fresh
    session."""
    message = compose(
        f"{', '.join(missing[:5])} not in this session's agent roster -- the "
        "launch would fail at its first agent() call. Start a fresh session "
        "so the roster loads them.",
        anchor=_WIKI_ANCHOR,
    )
    return render(message)


_ROSTER_UNCHECKED_NOTE = (
    "Agent-roster check did not run (transcript unreadable or no "
    "agent_listing_delta); the launch's agent types were not verified. "
    "Start a fresh session if a missing type fails the run."
)


_OVERRIDE_SENTINEL_NAME = ".coordinator-override-workflow-model-guard"


def _git_root() -> "str | None":
    """Repo root as `git rev-parse --show-toplevel` would report it -- same idiom as
    nudge-multiwave-workflow.py's `_git_root()`: an in-process parent walk (`_git_root_walk`)
    first, no subprocess on the routine path, with the 1s-timeout `git rev-parse --show-toplevel`
    subprocess below kept only as a fallback for the case the walk cannot resolve. Any failure
    (not a git repo, git missing, timeout) returns None and the sentinel check below is skipped
    -- fails toward the env-var-only guard, never toward a crash.
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
            env=noninteractive_git_env(),
            **no_console_spawn_kwargs(),
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    root = result.stdout.strip()
    return root or None


def _sentinel_override_active() -> bool:
    """Sentinel-file override parity with the env var below (F2 fix,
    2026-07-23): `COORDINATOR_OVERRIDE_WORKFLOW_MODEL_GUARD=1` is
    env-only, and a live session cannot set an env var into its own
    already-running hook process -- hooks inherit the harness's
    environment, not whatever the session sets mid-run. A repo-root
    sentinel FILE is settable from inside a live session (`touch
    <repo-root>/.coordinator-override-workflow-model-guard`), giving the
    same override reachable from both a pre-launch shell (env var) and a
    running session (sentinel file). Fails toward "no override" (returns
    False) on any resolution failure -- consistent with every other
    detection-failure guard in this hook, which fail OPEN toward the
    non-blocking path, not toward silently suppressing the guard.
    """
    root = _git_root()
    if not root:
        return False
    try:
        return os.path.isfile(os.path.join(root, _OVERRIDE_SENTINEL_NAME))
    except Exception:
        return False


def _compose_zero_modeled_deny_reason(agent_n: int) -> str:
    """Pure composer for the "no agent() call has model:" deny branch --
    separated from `main()` so C1b's in-process measurement harness can call
    it directly, per the plan's Measurement mechanism section.
    Behaviour-preserving extraction.

    Routes through `_message_envelope.compose` -- the full three-hatch
    override rationale (env var, sentinel file, PM-gate) and the
    ternary-undefined/known-limitations detail relocated to `_WIKI_ANCHOR`
    (see this hook's relocation fragment)."""
    message = compose(
        f"{agent_n} agent() call(s) have no model: -- inherits Opus this "
        "session (~4x cost). Add model: 'sonnet', or a defined agentType:, "
        "to each.",
        alternative=f"touch {_OVERRIDE_SENTINEL_NAME}",
        anchor=_WIKI_ANCHOR,
    )
    return render(message)


def _compose_unrostered_opus_deny_reason(agent_types: "list[str | None]") -> str:
    """Pure composer for the "Opus persona fleet outside the review roster"
    deny branch. Same separation rationale as
    `_compose_zero_modeled_deny_reason`.

    Names the boundary -- Opus is dispatchable in a workflow for review,
    and the published roster is what review dispatches -- and routes to the
    wiki for why. Deliberately says nothing about an override: this hook's
    escape hatch is withheld from the message by design and addressed to
    the operator at a terminal (`guard-unlock-channel.md`), because a
    message that advertises its own unlock teaches routing around it."""
    named = ", ".join(sorted({a for a in agent_types if a})[:3]) or "an agentType"
    message = compose(
        f"{named} resolves to Opus and is not on the review roster -- Opus in "
        "a workflow is for review (~4x cost). Use a rostered reviewer, or "
        "model: 'sonnet'.",
        anchor=_WIKI_ANCHOR,
    )
    return render(message)


def _compose_partial_modeled_context(agent_n: int, modeled_n: int) -> str:
    """Pure composer for the "some but not all agent() calls have model:"
    additionalContext branch -- same separation rationale as
    `_compose_zero_modeled_deny_reason`."""
    message = compose(
        f"{agent_n} agent() calls, only {modeled_n} set model: -- rest may "
        "inherit Opus (~4x cost) unless intended, with PM approval.",
        anchor=_WIKI_ANCHOR,
    )
    return render(message)


def main() -> int:
    # --- Safe stdin read ---
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""
    if not raw:
        return 0

    # --- Guard: explicit override (env var, or repo-root sentinel file) ---
    if os.environ.get("COORDINATOR_OVERRIDE_WORKFLOW_MODEL_GUARD", "") == "1":
        return 0
    if _sentinel_override_active():
        return 0

    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    # --- tool_name gate ---
    if payload.get("tool_name", "") != "Workflow":
        return 0

    # --- Guard: subagent/nested call -- only guard the main-loop EM's launches ---
    if "agent_id" in payload:
        return 0

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}

    # --- Extract tool_input.script (inline script; `name:` launches skip) ---
    script = tool_input.get("script", "") or ""

    # --- Hole 1 fix: tool_input.script empty but scriptPath present -> read
    # the file at that path and validate its contents through the same logic.
    # `name:` (saved-workflow-by-name launch) exposes no script contents in
    # the payload and remains genuinely out of scope; only scriptPath is
    # closed here.
    if not script:
        script_path = tool_input.get("scriptPath", "") or ""
        # Fail OPEN on a missing/unreadable file -- never wedge a launch on
        # a detection failure, consistent with every other guard.
        try:
            if script_path and os.path.isfile(script_path):
                with open(script_path, "r", encoding="utf-8", errors="replace") as fh:
                    script = fh.read(1_000_000)
        except Exception:
            script = ""

    transcript_path = payload.get("transcript_path", "") or ""

    # --- Roster check: runs before, and independently of, the model check ---
    stripped = _strip_comments(script) if script else ""
    agent_n, modeled_n, agent_types = (
        _count_agent_modeled_with_types(stripped) if stripped else (0, 0, [])
    )
    required, declared = _required_agent_types(tool_input, agent_types)
    roster_note = ""
    if required:
        roster = _fold_session_roster(transcript_path)
        if roster is None:
            # A literal-only launch with no roster stays silent; the loud
            # note is for launches whose args declared required types.
            roster_note = _ROSTER_UNCHECKED_NOTE if declared else ""
        else:
            missing = [t for t in required if t not in roster]
            if missing:
                _write_hook_output(
                    {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": _compose_absent_roster_deny_reason(missing),
                    }
                )
                return 0

    model_out = _model_guard(transcript_path, stripped, agent_n, modeled_n, agent_types)
    if model_out is not None and model_out.get("permissionDecision") == "deny":
        _write_hook_output(model_out)
        return 0
    if roster_note:
        prior = (model_out or {}).get("additionalContext")
        model_out = {
            "hookEventName": "PreToolUse",
            "additionalContext": f"{prior}\n{roster_note}" if prior else roster_note,
        }
    if model_out is not None:
        _write_hook_output(model_out)
    return 0


def _write_hook_output(specific: dict) -> None:
    """Emit one PreToolUse `hookSpecificOutput` envelope on stdout."""
    sys.stdout.write(
        json.dumps({"hookSpecificOutput": specific}, ensure_ascii=False, separators=(",", ":"))
    )
    sys.stdout.write("\n")


def _model_guard(
    transcript_path: str,
    stripped: str,
    agent_n: int,
    modeled_n: int,
    agent_types: "list[str | None]",
) -> "dict | None":
    """The Opus-session un-modeled agent() guard: returns the
    `hookSpecificOutput` body to emit (a deny, or a partial-coverage
    additionalContext), or None for a silent allow. Every detection failure
    returns None."""
    if not transcript_path or not os.path.isfile(transcript_path):
        return None

    if not _detect_opus(transcript_path):
        return None

    if agent_n < 1:
        return None

    if modeled_n == 0:
        # Resolution runs ONLY here -- the one path that would otherwise
        # DENY on the pre-existing agent_n/modeled_n rung alone. A fully-
        # or partially-modeled script (either branch below this one) never
        # reaches `_resolve_call_site_tier()` and performs zero
        # agent-definition reads.
        tiers = [_resolve_call_site_tier(agent_type) for agent_type in agent_types]
        if all(tier is not None for tier in tiers):
            # Every call site resolved via its own agentType, and since
            # modeled_n == 0 none of those tiers came from a call-site
            # `model:` override -- each is pinned to its definition's own
            # charter model. An asserted agentType is self-enforcing:
            # asserting it makes it true, so there is no forgery to
            # defend against here.
            #
            # That alone is not the exemption. Opus in a workflow is
            # gated because Opus is expensive; a declared persona fleet
            # spends that money just as surely as an undeclared one, so
            # "every call site is a persona" would exempt every Opus
            # fleet and gate nothing. The exemption is for REVIEW, and
            # the published roster is what a review workflow dispatches.
            # A sonnet-tier fleet costs nothing to gate and is never
            # reached by this branch's opus check.
            if all(
                tier != "opus" or agent_type in _rostered_agent_types()
                for tier, agent_type in zip(tiers, agent_types)
            ):
                return None
            reason = _compose_unrostered_opus_deny_reason(
                [
                    agent_type
                    for tier, agent_type in zip(tiers, agent_types)
                    if tier == "opus" and agent_type not in _rostered_agent_types()
                ]
            )
            return {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        # At least one call site's agentType is absent, non-literal, or
        # names no resolvable definition -- falls back to the
        # un-resolved deny rung. Never crash, never silently pass.
        return {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": _compose_zero_modeled_deny_reason(agent_n),
        }

    if modeled_n < agent_n:
        # An un-modeled call pinned to an agentType costs its definition's
        # charter model, so it counts as covered on the same terms as the
        # all-unmodeled branch above: resolvable, and not an unrostered Opus.
        calls = _walk_agent_calls(stripped, _string_mask(stripped))
        covered_n = modeled_n
        for has_model, agent_type in calls:
            if has_model:
                continue
            tier = _resolve_call_site_tier(agent_type)
            if tier is not None and (tier != "opus" or agent_type in _rostered_agent_types()):
                covered_n += 1
        if covered_n == agent_n:
            return None
        return {
            "hookEventName": "PreToolUse",
            "additionalContext": _compose_partial_modeled_context(agent_n, covered_n),
        }

    return None


if __name__ == "__main__":
    sys.exit(main())
