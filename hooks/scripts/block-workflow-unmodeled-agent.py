#!/usr/bin/env python3
"""PreToolUse hook (matcher: Workflow): closes the un-modeled agent() cost trap
documented in coordinator/docs/wiki/workflow-orchestration.md § "Model
selection: Sonnet by default, Opus is PM-gated". That doc's own
negative-spec says: "an un-modeled agent() in an Opus session is a defect,
not a shortcut... there is no warning, no gate, and no retry." This hook
is the gate.

Originally ported naked-Python (W5 straggler port from a now-retired bash
oracle) -- no reusable claude-klabauter op exists for this hook's per-call-site
agent()/model: string-aware parse, so this is a SELF-CONTAINED hook, not a
thin claude-klabauter stub -- zero Git-Bash cold-start per Workflow launch on Windows).

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
  - AGENT_N >= 1 AND MODELED_N == 0 (unambiguous -- no call site modeled):
    DENY (Form A permissionDecision:"deny"), message leads with the fix
    (add model: 'sonnet' to each agent() call) before naming the violation,
    and names the override + PM-gate escape hatches.
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
    nested one level deeper inside a schema/meta/opts sub-object).
  - Residual limitation: this is a string-aware depth-counting pass, not
    a full JS parser. It does not model JS regex literals (`/.../`) as a
    distinct token class -- a `/` that is genuinely a regex delimiter
    (not inside a string) is not specially recognized, though this does
    not desync depth counting since regex bodies containing `(`/`)`/`{`/
    `}` are vanishingly rare inside Workflow agent() call arguments in
    practice, and any residual desync still fails toward the documented
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

from _message_envelope import compose, render  # noqa: E402
from _win_portability import no_console_creationflags  # noqa: E402
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
    "coordinator/docs/wiki/guard-message-concision.md"
    "#workflow-model-guard-override-hatches-and-pm-gate"
)


_IDENTIFIER_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$"
)


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

    Not a full JS parser -- does not model regex literals as a distinct
    token class (see module docstring "Known limitations").
    """
    n = len(script)
    string_mask = bytearray(n)
    comment_mask = bytearray(n)
    stack = [("code", 0)]
    i = 0
    while i < n:
        kind, depth = stack[-1]

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
            if kind == "interp":
                if ch == "{":
                    stack[-1] = ("interp", depth + 1)
                elif ch == "}":
                    if depth == 0:
                        stack.pop()
                    else:
                        stack[-1] = ("interp", depth - 1)
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


def _count_agent_modeled(buf: str) -> "tuple[int, int]":
    """Per-call-site agent(/model: attribution -- string-aware paren/brace
    depth walk (see module docstring "Known limitations" for the
    documented residual edges).
    """
    mask = _string_mask(buf)
    n = len(buf)
    i = 0
    agent_n = 0
    modeled_n = 0

    while i < n:
        pos = buf.find("agent(", i)
        if pos == -1:
            break
        if mask[pos] or (pos > 0 and buf[pos - 1] in _IDENTIFIER_CHARS):
            i = pos + 1
            continue
        call_start = pos
        paren_open = call_start + 5  # index of the "(" character

        depth = 0
        brace_depth = 0
        j = paren_open
        close_idx = -1
        has_direct_model = False
        while j < n:
            if mask[j]:
                j += 1
                continue
            ch = buf[j]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    close_idx = j
                    break
            elif ch == "{":
                if depth == 1:
                    brace_depth += 1
            elif ch == "}":
                if depth == 1:
                    brace_depth -= 1
            elif ch == "m" and depth == 1 and brace_depth == 1:
                # Review: code-reviewer -- Finding 2: identifier-boundary guard,
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
                    # Review: code-reviewer -- Finding 3: blank out masked
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

        agent_n += 1
        if has_direct_model:
            modeled_n += 1

        i = close_idx + 1

    return agent_n, modeled_n


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
            **no_console_creationflags(),
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
        "session (~4x cost). Add model: 'sonnet' to each, or override "
        "with PM approval.",
        alternative=f"touch {_OVERRIDE_SENTINEL_NAME}",
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
        if not script_path:
            return 0
        # Fail OPEN on a missing/unreadable file -- never wedge a launch on
        # a detection failure, consistent with every other guard.
        try:
            if not os.path.isfile(script_path):
                return 0
            with open(script_path, "r", encoding="utf-8", errors="replace") as fh:
                script = fh.read(1_000_000)
        except Exception:
            return 0
        if not script:
            return 0

    # --- Extract transcript_path, detect session model tier (Opus only fires) ---
    transcript_path = payload.get("transcript_path", "") or ""
    if not transcript_path or not os.path.isfile(transcript_path):
        return 0

    if not _detect_opus(transcript_path):
        return 0

    stripped = _strip_comments(script)
    agent_n, modeled_n = _count_agent_modeled(stripped)

    if agent_n < 1:
        return 0

    if modeled_n == 0:
        reason = _compose_zero_modeled_deny_reason(agent_n)
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

    if modeled_n < agent_n:
        msg = _compose_partial_modeled_context(agent_n, modeled_n)
        out = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": msg,
            }
        }
        sys.stdout.write(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
        sys.stdout.write("\n")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
