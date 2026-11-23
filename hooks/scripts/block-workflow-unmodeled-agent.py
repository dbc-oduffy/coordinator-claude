#!/usr/bin/env python3
"""PreToolUse hook (matcher: Workflow): closes the un-modeled agent() cost trap
documented in coordinator/docs/wiki/em-operating-model/workflow-orchestration.md § "Model
selection: Sonnet by default, Opus is PM-gated". An un-modeled agent() inherits the session
model, so in an Opus session every such worker runs at ~4x cost with no visible signal.

Behavior: the hook never denies a model choice (a model choice is recoverable). It pins to
model 'sonnet' every `agent()` call that is unmodeled (no `model:` and no non-opus agentType
pin) or effectively Opus (literal `model: 'opus'`, or an unmodeled call whose agentType
definition pins opus), unless its agentType is rostered or in `_OPUS_ALLOWLIST_EXTRA`. An
inline `script` is returned as `updatedInput` with the rewritten script plus an
`additionalContext` advisory naming each reroute; no change needed is a silent allow. A
non-literal `model:` expression is left alone. The rewrite does not depend on the session
model.

The lexical scanner (`_scan_masks` and the constants and helpers from `_QUOTED_TOKENS`
through `_strip_comments`) and `rewrite_agent_models` are the canonical engine port's, commit
cb963fe0f5, taken verbatim. Named divergences from it:
  - `_compose_reroute_advisory` takes no `env`: `_message_envelope.render` has no such kwarg.
  - A `scriptPath` launch gets the advisory only; the file and `scriptPath` are untouched.
    The submission stage and `allow-emitted-workflow-fire.py` verify an emitted run by its
    `scriptPath` receipt, which an inline rewrite would defeat.
  - `_scan_agent_call_options` matches `countedAgent(` call sites too (via `_AGENT_CALL_RE`),
    since those wrapper sites carry the model: keys, and skips a function declaration.
  - Doctrine-asset paths are the repo-relative `_AGENTS_DIR`, `_ROSTER_FRAGMENT` and
    `_REVIEW_SIGNALS`, not an installed-layout resolver.
  - `int.from_bytes`/`to_bytes` pass `"big"`; a definition's `model:` is read by `_FRONTMATTER_MODEL_RE`.

The one deny kept is the absent-roster deny: a launch naming agent types the session roster
lacks would fail at its first agent() call. It is not a model choice.

Fail-open guards (all exit 0 silent, in order):
  - COORDINATOR_OVERRIDE_WORKFLOW_MODEL_GUARD=1 set, OR a repo-root sentinel file
    `.coordinator-override-workflow-model-guard` exists (a live session cannot set an env var
    into its own running hook; `touch <repo-root>/.coordinator-override-workflow-model-guard`
    is the session-reachable equivalent). See `_sentinel_override_active()`.
  - tool_name != "Workflow".
  - subagent/nested call (payload carries "agent_id").
  - No script text extractable: an inline `script`, or a readable file at `scriptPath`; a
    `name:` launch carries no contents and is out of scope. An unreadable file fails open.
  - Nothing to reroute.

Known limitations -- string-literal-aware:
  - `agent(` occurrences and the paren/brace depth walk skip string-literal spans (single,
    double, backtick templates with `${...}` interpolation tracked back to code, and JS regex
    literals masked by the previous significant token). Compound identifiers such as
    `sub_agent(` are not call sites: the character before a candidate must not be an
    identifier character.
  - Comment stripping shares the same one-pass mask, so a `//` or `/*` inside a string is not
    a comment, and an apostrophe inside a comment never opens a string.
  - `model:` attribution is per call site: a direct key of the options object passed to
    agent() (brace depth 1), or of an object literal handed through a helper call after the
    prompt argument. A `model:` whose value is `undefined`/`null` counts as absent.
  - A string-aware depth-counting pass, not a full JS parser; residual desync fails toward
    attributing nothing for that call site and guaranteed forward progress.
  - An `agent(` nested as an argument to another `agent()` call is consumed by the outer
    call's scan and not counted independently.

Spec backlink: cross-repo/inbox/2026-07-13-example-store-repo-em-workflow-sonnet-default-guard.md
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
from _win_portability import (  # noqa: E402
    no_console_spawn_kwargs,
    noninteractive_git_env,
)
try:
    from _git_root_walk import git_root_walk as _git_root_walk  # noqa: E402
except Exception:
    # A deploy missing its sibling _git_root_walk.py must still fail open to the
    # subprocess rung below, not crash on import.
    def _git_root_walk() -> str | None:
        return None

#: Wiki section carrying the override-hatch explanation (env var, sentinel file, PM-gate).
_WIKI_ANCHOR = (
    "coordinator/docs/wiki/guards/guard-message-concision.md"
    "#workflow-model-guard-override-hatches-and-pm-gate"
)


_IDENTIFIER_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$"
)


_QUOTED_TOKENS = (
    r"'(?:[^'\\]++|\\[\s\S])*+(?:'|\\(?=\Z))?"
    r'|"(?:[^"\\]++|\\[\s\S])*+(?:"|\\(?=\Z))?'
)
_CODE_STOP = re.compile(_QUOTED_TOKENS + r"|[/`]")
_INTERP_STOP = re.compile(_QUOTED_TOKENS + r"|[/`{}]")
_TEMPLATE_RUN = re.compile(r"(?:[^`$\\]++|\\[\s\S]|\$(?!\{))*+")
_COMMENT_RUN = re.compile(rb"\x01+")
_REGEX_LITERAL = re.compile(
    r"/(?:\\[\s\S]|\[(?:\\[\s\S]|[^\]\\\n])*+\]|[^/\[\\\n])*+/[a-zA-Z0-9_$]*"
)
_REGEX_PRECEDING_KEYWORDS = frozenset({
    "return", "typeof", "case", "in", "of", "delete", "void", "throw",
    "new", "else", "do", "instanceof", "yield", "await",
})
_MAX_REGEX_KEYWORD = max(map(len, _REGEX_PRECEDING_KEYWORDS))


def _regex_after_gap(script: str, start: int, end: int, previous: bool) -> bool:
    """Read only the significant suffix before a slash. Comments do not reset it."""
    while end > start and script[end - 1].isspace():
        end -= 1
    if end == start:
        return previous
    last = script[end - 1]
    if last not in _IDENTIFIER_CHARS:
        return last not in (")", "]", "'")
    first = end - 1
    while first > start and script[first - 1] in _IDENTIFIER_CHARS:
        first -= 1
        if end - first > _MAX_REGEX_KEYWORD:
            return False
    return script[first:end] in _REGEX_PRECEDING_KEYWORDS


def _scan_masks(script: str) -> "tuple[bytearray, bytearray]":
    n = len(script)
    string_mask = bytearray(n)
    comment_mask = bytearray(n)
    stack: list[int | None] = [0]
    regex_allowed = True
    i = 0
    while i < n:
        depth = stack[-1]
        if depth is None:
            end = _TEMPLATE_RUN.match(script, i).end()
            if script.startswith("${", end):
                string_mask[i:end + 1] = b"\x01" * (end + 1 - i)
                stack.append(1)
                i = end + 2
            else:
                # The only other stops are the closing backtick, EOF, or a lone final escape.
                end = min(n, end + 1)
                string_mask[i:end] = b"\x01" * (end - i)
                stack.pop()
                regex_allowed = False
                i = end
            continue

        match = (_INTERP_STOP if depth else _CODE_STOP).search(script, i)
        if match is None:
            break
        start, i = i, match.start()
        token = script[i]
        if token in "'\"":
            end = match.end()
            string_mask[i:end] = b"\x01" * (end - i)
            i = end
            regex_allowed = False
            continue
        if token == "`":
            string_mask[i] = 1
            stack.append(None)
            regex_allowed = _regex_after_gap(script, start, i, regex_allowed)
        elif token == "/":
            regex_allowed = _regex_after_gap(script, start, i, regex_allowed)
            if script.startswith("//", i):
                end = script.find("\n", i + 2)
                end = n if end == -1 else end
                comment_mask[i:end] = b"\x01" * (end - i)
                i = end
                continue
            if script.startswith("/*", i):
                end = script.find("*/", i + 2)
                end = n if end == -1 else end + 2
                comment_mask[i:end] = b"\x01" * (end - i)
                i = end
                continue
            if regex_allowed and (literal := _REGEX_LITERAL.match(script, i)):
                end = literal.end()
                string_mask[i:end] = b"\x01" * (end - i)
                i = end
                regex_allowed = False
                continue
            regex_allowed = True
        elif depth and token == "{":
            stack[-1] = depth + 1
            regex_allowed = True
        elif depth and token == "}":
            if depth == 1:
                stack.pop()
                regex_allowed = False
            else:
                stack[-1] = depth - 1
                regex_allowed = True
        i += 1

    return string_mask, comment_mask


def _string_mask(script: str) -> bytearray:
    return _scan_masks(script)[0]


def _strip_comments(script: str) -> str:
    _, comment_mask = _scan_masks(script)
    pieces = []
    previous = 0
    for span in _COMMENT_RUN.finditer(comment_mask):
        start, end = span.span()
        pieces.extend((script[previous:start], "\n" * script.count("\n", start, end)))
        previous = end
    pieces.append(script[previous:])
    return "".join(pieces)


# Call names counted as agent() call sites: the runtime hook, plus a workflow's pass-through counting
# wrapper (distill-harvest's countedAgent, which tallies calls against the runtime's 1000-agent cap).
# A wrapper's call sites carry the model: keys, so they are the sites the guard must see.
_AGENT_CALL_RE = re.compile(r"(?:countedAgent|agent)\(")
# A wrapper's own declaration (`function countedAgent(prompt, opts)`) is not a call site.
_FUNCTION_DECL_BEFORE = re.compile(r"\bfunction\s+$")


def _walk_agent_calls(buf: str, mask: "bytearray") -> "list[tuple[bool, str | None]]":
    """Per-call-site agent(/model:/agentType: attribution -- string-aware
    paren/brace depth walk (see module docstring "Known limitations").

    Returns one `(has_direct_model, agent_type)` tuple per real,
    successfully-balanced call site, in source order. `agent_type` is the
    call's own `agentType:` string literal, or `None` when absent, masked,
    or not a plain literal. An unbalanced call site contributes no tuple.
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
        paren_open = m.end() - 1  # index of the "(" character

        depth = 0
        brace_depth = 0
        # Brace depth per paren frame, and whether the prompt argument is behind us. An options
        # object handed through a helper -- `agent(prompt, withRole(r, { model: 'opus' }))` --
        # carries its `model:` as a direct key one paren frame deeper.
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
                # Identifier-boundary guard: a key ending in the literal substring
                # "model:" (base_model:, submodel:) is not a real `model:` key.
                if (
                    buf[j:j + 6] == "model:"
                    and not any(mask[j:j + 6])
                    and not (j > 0 and not mask[j - 1] and buf[j - 1] in _IDENTIFIER_CHARS)
                ):
                    value = _extract_model_value(buf, mask, j + 6, n)
                    # Blank masked (string-literal) characters first, so a literal value
                    # containing the word "undefined"/"null" is not an undefined value.
                    masked_value = "".join(
                        ch2 if not mask[j + 6 + idx] else " "
                        for idx, ch2 in enumerate(value)
                    )
                    if not _UNDEFINED_NULL_RE.search(masked_value):
                        has_direct_model = True
            elif ch == "a" and depth == 1 and brace_depth == 1:
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
            # Unbalanced (truncated/malformed) call: attribute nothing, and jump to n so
            # a pathological unclosed tail is not rescanned per later match (O(n^2)).
            i = n
            continue

        calls.append((has_direct_model, agent_type))
        i = close_idx + 1

    return calls


def _count_agent_modeled(buf: str) -> "tuple[int, int]":
    """`(agent_n, modeled_n)`: call sites, and the subset carrying their own `model:`."""
    mask = _string_mask(buf)
    calls = _walk_agent_calls(buf, mask)
    agent_n = len(calls)
    modeled_n = sum(1 for has_model, _ in calls if has_model)
    return agent_n, modeled_n


def _count_agent_modeled_with_types(buf: str) -> "tuple[int, int, list[str | None]]":
    """`_count_agent_modeled()` plus each call site's `agentType:` literal (or None), in
    source order. A pure string extraction off the same walk, so it reads no file."""
    mask = _string_mask(buf)
    calls = _walk_agent_calls(buf, mask)
    agent_n = len(calls)
    modeled_n = sum(1 for has_model, _ in calls if has_model)
    agent_types = [agent_type for _, agent_type in calls]
    return agent_n, modeled_n, agent_types


_UNDEFINED_NULL_RE = re.compile(r"\b(?:undefined|null)\b")


def _extract_model_value(buf: str, mask: "bytearray", start: int, n: int) -> str:
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
_FRONTMATTER_MODEL_RE = re.compile(r"^model:\s*(\S+)\s*$", re.MULTILINE)
_AGENTS_DIR = _SCRIPTS_DIR.parent.parent / "agents"
_ROSTER_FRAGMENT = _SCRIPTS_DIR.parent.parent / "contract" / "review-roster-fragment.json"
_REVIEW_SIGNALS = _SCRIPTS_DIR.parent.parent / "contract" / "review-signals.json"


def _tier_walked_agent_types() -> "frozenset[str]":
    """Every `agentType` the published review roster dispatches via the tier walk
    (`fragment['tiers'] -> tier['stages'] -> stage['agents']`). Fails CLOSED to the empty set
    on a missing or malformed fragment: an unreadable contract exempts nobody."""
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
    """Every `selects` value in `contract/review-signals.json`'s `signals` map: a
    signal-selectable agent is dispatched by the review workflow when its signal fires.
    Same fail-CLOSED-to-empty posture as `_tier_walked_agent_types()`."""
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
    """Every `agentType` the published review roster dispatches: the tier walk plus every
    signal-selectable agent. Version-controlled contract files, so a hand-written workflow
    cannot add itself by typing. Each half fails closed independently."""
    return _tier_walked_agent_types() | _signal_selected_agent_types()


def _resolve_call_site_tier(agent_type: "str | None") -> "str | None":
    if not agent_type:
        return None
    name = agent_type
    if name.startswith(_COORDINATOR_AGENT_TYPE_PREFIX):
        name = name[len(_COORDINATOR_AGENT_TYPE_PREFIX):]
    if not name:
        return None
    path = _AGENTS_DIR / f"{name}.md"
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    m = _FRONTMATTER_MODEL_RE.search(text[:end])
    if not m:
        return None
    return m.group(1).strip().strip("'\"").lower()


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
    """Repo root as `git rev-parse --show-toplevel` would report it: an in-process parent
    walk first, with a 1s-timeout subprocess kept only as a fallback. Any failure returns
    None and the sentinel check is skipped -- toward the env-var-only guard, never a crash."""
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
    """True when the repo-root sentinel file `.coordinator-override-workflow-model-guard`
    exists: the override a live session can set, unlike the env var. Fails toward "no
    override" on any resolution failure."""
    root = _git_root()
    if not root:
        return False
    try:
        return os.path.isfile(os.path.join(root, _OVERRIDE_SENTINEL_NAME))
    except Exception:
        return False


# The named Opus personas that are not on the review roster: the ask keeps Opus for "the named
# reviewers and other allowlisted", and these are the named ones the roster does not list.
_OPUS_ALLOWLIST_EXTRA = frozenset(
    {
        "coordinator:apm",
        "coordinator:overengineering-reviewer",
        "coordinator:vp-product",
        "coordinator:subtractive-adjudicator",
        "coordinator:blitz-em",
    }
)

_SONNET = "'sonnet'"


def _opus_allowlist() -> "frozenset[str]":
    return _rostered_agent_types() | _OPUS_ALLOWLIST_EXTRA


def _literal_after_key(buf: str, mask: "bytearray", j: int, key_len: int, n: int) -> "tuple[int, int, str | None, str]":
    """(value_start, value_end, literal_or_None, text) for the value following a key at `j`."""
    raw = _extract_model_value(buf, mask, j + key_len, n)
    start = j + key_len + (len(raw) - len(raw.lstrip()))
    end = j + key_len + len(raw.rstrip())
    return start, end, _extract_string_literal(raw), raw.strip()


def _key_here(buf: str, mask: "bytearray", j: int, key: str) -> bool:
    return (
        buf[j:j + len(key)] == key
        and not any(mask[j:j + len(key)])
        and not (j > 0 and not mask[j - 1] and buf[j - 1] in _IDENTIFIER_CHARS)
    )


def _scan_agent_call_options(buf: str, mask: "bytearray") -> "list[dict]":
    """One record per `agent(` call: close paren, depth-1 options-object `{` (or None),
    whether a second argument exists, and the direct model/agentType/label values."""
    n = len(buf)
    keys = {"m": "model:", "a": "agentType:", "l": "label:"}
    records: "list[dict]" = []
    i = 0
    while i < n:
        m = _AGENT_CALL_RE.search(buf, i)
        if m is None:
            break
        pos = m.start()
        if (mask[pos] or (pos > 0 and buf[pos - 1] in _IDENTIFIER_CHARS)
                or _FUNCTION_DECL_BEFORE.search(buf[max(0, pos - 24):pos])):
            i = pos + 1
            continue
        depth = 0
        brace = 0
        past_prompt = False
        rec = {
            "options_open": None, "other_second_arg": False, "model": None,
            "agent_type": None, "label": None, "close": -1,
        }
        j = m.end() - 1
        while j < n:
            if mask[j]:
                j = mask.find(b"\x00", j + 1)
                if j == -1:
                    break
            ch = buf[j]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    rec["close"] = j
                    break
            elif ch == "{":
                if depth == 1:
                    if brace == 0 and past_prompt and rec["options_open"] is None:
                        rec["options_open"] = j
                    brace += 1
            elif ch == "}":
                if depth == 1:
                    brace -= 1
            elif ch == "," and depth == 1 and brace == 0:
                past_prompt = True
            elif ch in " \t\r\n":
                pass
            elif past_prompt and depth == 1 and brace == 0 and rec["options_open"] is None:
                rec["other_second_arg"] = True
            elif depth == 1 and brace == 1 and rec["options_open"] is not None:
                key = keys.get(ch)
                if key and _key_here(buf, mask, j, key):
                    start, end, lit, text = _literal_after_key(buf, mask, j, len(key), n)
                    if key == "model:":
                        rec["model"] = (start, end, lit, text)
                    elif key == "agentType:":
                        rec["agent_type"] = lit
                    else:
                        rec["label"] = lit
            j += 1
        if rec["close"] == -1:
            break
        records.append(rec)
        i = rec["close"] + 1
    return records


def rewrite_agent_models(script: str) -> "tuple[str, list[str]]":
    """Pin every effectively-Opus or unmodeled `agent()` call to model 'sonnet'.

    The effective model is the call's own literal `model:`, else its agentType definition's
    frontmatter model, else sonnet. Opus survives only for an allowlisted agentType. Non-literal
    model expressions are left alone. Returns the new script and one reroute string per change."""
    string_mask, comment_mask = _scan_masks(script)
    mask = bytearray(
        (int.from_bytes(string_mask, "big") | int.from_bytes(comment_mask, "big")).to_bytes(len(script), "big")
    )
    allow = _opus_allowlist()
    edits: "list[tuple[int, int, str]]" = []
    reroutes: "list[str]" = []
    for idx, rec in enumerate(_scan_agent_call_options(script, mask), start=1):
        agent_type = rec["agent_type"]
        name = rec["label"] or agent_type or f"agent #{idx}"
        model = rec["model"]
        if model is not None:
            start, end, lit, text = model
            if lit is not None and lit.strip().lower() == "opus" and agent_type not in allow:
                edits.append((start, end, _SONNET))
                reroutes.append(f"{name} opus->sonnet")
            elif lit is None and text in ("undefined", "null"):
                edits.append((start, end, _SONNET))
                reroutes.append(f"{name} unmodeled->sonnet")
            continue
        if rec["other_second_arg"]:
            continue
        tier = _resolve_call_site_tier(agent_type)
        if tier is not None and (tier != "opus" or agent_type in allow):
            continue
        what = "opus->sonnet" if tier == "opus" else "unmodeled->sonnet"
        if rec["options_open"] is not None:
            at = rec["options_open"] + 1
            edits.append((at, at, f" model: {_SONNET}, "))
        else:
            close = rec["close"]
            k = close
            while k > 0 and (script[k - 1].isspace() or comment_mask[k - 1]):
                k -= 1
            trailing_comma = k > 0 and script[k - 1] == "," and not mask[k - 1]
            edits.append((close, close, f" {{ model: {_SONNET} }}" if trailing_comma else f", {{ model: {_SONNET} }}"))
        reroutes.append(f"{name} {what}")
    for start, end, text in sorted(edits, key=lambda e: e[0], reverse=True):
        script = script[:start] + text + script[end:]
    return script, reroutes


def _compose_reroute_advisory(reroutes: "list[str]") -> str:
    """The advisory naming each rerouted call (first four, then a count)."""
    shown = ", ".join(reroutes[:4]) + (f" (+{len(reroutes) - 4} more)" if len(reroutes) > 4 else "")
    message = compose(
        f"{len(reroutes)} agent() call(s) rerouted to sonnet: {shown}. "
        "Opus is for rostered reviewers.",
        anchor=_WIKI_ANCHOR,
    )
    return render(message)


def _compose_scriptpath_advisory(reroutes: "list[str]") -> str:
    """The reroute advisory for a `scriptPath` launch, whose file is left untouched."""
    shown = ", ".join(reroutes[:4]) + (f" (+{len(reroutes) - 4} more)" if len(reroutes) > 4 else "")
    message = compose(
        f"{len(reroutes)} agent() call(s) in the scriptPath file would run Opus or "
        f"inherit the session model: {shown}. The file is not rewritten; add "
        "model: 'sonnet' to each, or use a rostered reviewer.",
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

    # --- Script text: inline `script`, else the file at `scriptPath`; a `name:` launch
    # exposes no contents and is out of scope. A missing/unreadable file fails open.
    script = tool_input.get("script", "") or ""
    inline = bool(script)
    if not script:
        script_path = tool_input.get("scriptPath", "") or ""
        try:
            if script_path and os.path.isfile(script_path):
                with open(script_path, "r", encoding="utf-8", errors="replace") as fh:
                    script = fh.read(1_000_000)
        except Exception:
            script = ""

    transcript_path = payload.get("transcript_path", "") or ""

    # --- Roster check: the one deny this hook keeps ---
    stripped = _strip_comments(script) if script else ""
    _, _, agent_types = (
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

    out = _model_guard(tool_input, script, inline)
    if roster_note:
        prior = (out or {}).get("additionalContext")
        out = {
            **(out or {}),
            "hookEventName": "PreToolUse",
            "additionalContext": f"{prior}\n{roster_note}" if prior else roster_note,
        }
    if out is not None:
        _write_hook_output(out)
    return 0


def _write_hook_output(specific: dict) -> None:
    """Emit one PreToolUse `hookSpecificOutput` envelope on stdout."""
    sys.stdout.write(
        json.dumps({"hookSpecificOutput": specific}, ensure_ascii=False, separators=(",", ":"))
    )
    sys.stdout.write("\n")


def _model_guard(tool_input: dict, script: str, inline: bool) -> "dict | None":
    """The `hookSpecificOutput` body for the model rewrite, or None when nothing is rerouted.

    An inline script is returned rewritten as `updatedInput` (every other `tool_input` field
    kept) with the reroute advisory; a `scriptPath` launch gets the advisory only. Never a deny."""
    if not script:
        return None
    new_script, reroutes = rewrite_agent_models(script)
    if not reroutes:
        return None
    if not inline:
        return {
            "hookEventName": "PreToolUse",
            "additionalContext": _compose_scriptpath_advisory(reroutes),
        }
    return {
        "hookEventName": "PreToolUse",
        "updatedInput": {**tool_input, "script": new_script},
        "additionalContext": _compose_reroute_advisory(reroutes),
    }


if __name__ == "__main__":
    sys.exit(main())
