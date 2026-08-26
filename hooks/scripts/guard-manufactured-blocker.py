"""Stop-hook guard — the manufactured-blocker check (off-altitude items in
end-of-turn PM handoffs).

Spec backlink: docs/plans/2026-08-10-posture-scaled-autonomous-disposition.md
(chunk C5); "A fourth shape, and the one the ledger cannot see" in that plan's
Problem section is the motivating incident this guard encodes.

THE PROBLEM. An EM closed a turn: "Three things now wait on you: the cascade
exit-code call (blocks the fix), the retro --write (now sequenced behind it),
and the doctrine-plane negative-spec entry." The PM's reaction supplies the test this
guard applies: "I don't even know what these things are, but I'm sure they're
EM calls. It's the 'wait on you' and that sort of crap. No it doesn't. These
are EM things." A second, subtler family says the same thing by assertion
rather than by an overt handoff clause -- "genuinely yours", "still yours, and
unchanged", "that's a PM call, not mine" -- tagging an item as PM-owned
without demonstrating it is. The PM names this a tic: the possessive does the
work no analysis did, and a softening qualifier ("genuinely", "actually",
"still") is an AGGRAVATING signal, not a mitigating one.

THE TEST -- copied, not re-derived. It exists as the plan skill's B.0
doubt-check un-gaming clause, which disqualifies tactical uncertainties
(naming, test framework, commit shape, file structure) as "off-altitude,
not merely low-stakes", however unsure the author is. That clause has TWO
route-keyed arms since the route segmentation -- the full triad in
`plan-corpus.md`, a proportional falsifiability arm in
`spec-dispatch-corpus.md` -- so cite it by name rather than by file: an
S-lane EM never loads the `plan` segment, and a message naming a file its
reader cannot open is worse than one naming none.

This guard applies the same discriminator to
end-of-turn reports: a genuine PM call concerns scope, deliverable, or
product direction, and states itself in the PM's vocabulary. If the PM would
not recognise the nouns, it is an EM call -- decide it, do not hand it up.

WHY THIS IS NOT THE STOOD-DOWN WATCHER. `runtime-tripwire-stop-watcher.py`
inferred a STATE ("is this session abandoned?") from timing and transcript
shape, fired 681 times in 26 days at ~99.4% wrong, and was stood down by PM
ruling. This guard matches a SPEECH ACT the EM literally wrote in its own
final message -- the trigger text is right there in the output, nothing is
inferred. No timing, idle-duration, or session-age predicate exists anywhere
in this module (grep-asserted by the test suite, same discipline as A5).

SCOPE OF THE READ. Stop hooks receive a transcript path. This module reads
ONLY the final assistant message -- never the whole conversation -- which is
what keeps it a cheap `command` hook.

EXEMPTIONS ARE LOAD-BEARING (A13). A real PM gate must never be suppressed --
a false fire here is worse than a miss, because it trains the EM to route
around a genuine gate. Silent pass when any of these hold, checked against
the same turn's sizing state and a SCOPED window of the final-message text
(the sentence carrying the C5 trigger plus one sentence either side -- never
the whole message; see EXEMPTION SCOPE below for why):
  - the session's routed sizing object carries an unresolved appetite/post-
    size fork (`fork: null` with the matching detent open) or an unresolved
    XL exit (`route: pm-decision`, `xl_exit: null`) -- predicate copied from
    the sibling engine's `nudge_unrouted_sizing` op (`_appetite_fork_open` /
    `_post_size_prompt_open`), reimplemented here as a self-contained
    line-scan (no YAML dependency, matching `_posture.py`'s own stdlib-only
    convention) since this guard has no sibling engine op to delegate to.
    Conjunctive with the trigger window, like the other lexical exemptions:
    the on-disk fork must be open AND the C5 trigger sentence must itself be
    about the size of the ask. An open post-size prompt exempts the sentence
    that ASKS it -- never every possessive construct sharing the turn, which
    would silence C5 for the whole of any session sized M or above, i.e. in
    exactly the sessions whose reports carry multiple items. A recorded
    `pm_resolution` block closes the fork on its own: the engine always emits
    `fork` null and the schema fills it only on a cut-/raise-shaped answer,
    so `fork` alone cannot witness a PM answer of "go with that";
  - an ask-before-external-action is pending (an irreversible/external act
    named without pre-authorization already granted);
  - a conflict of interest / wrong signatory (the EM is structurally
    disqualified from acting -- e.g. a two-decider record naming the EM as
    one of the deciders, so the EM ratifying its own authorship is the wrong
    signature regardless of how well it understands the content). Lexical,
    two halves with DELIBERATELY DIFFERENT scope (A13 finding 1's
    resolution): a standalone phrase ("wrong signature", "ratifying my own
    authorship", "two-decider"/"named deciders" construct) is checked
    against the scoped window like the other exemption above, since
    the phrase is self-contained and its appearing far from the trigger is
    exactly the incidental-co-occurrence failure mode this guard must not
    reward. An authorship admission ("I wrote/authored it") co-occurring
    with ratification vocabulary (sign-off/ratify/approve) is checked
    against the WHOLE message on purpose and stays that way -- the
    admission and the ratification ask legitimately sit in different
    sentences of a real wrong-signatory report, so narrowing this half
    would break genuine cases, not just incidental ones. Neither half alone
    is enough, so an ordinary "I wrote the plan, so the approach call is
    yours" still fires the ordinary handoff check.
The exemption check applies identically to BOTH pattern groups below -- the
discriminator is never the phrasing, it is whether one of these three actually
holds.

EXEMPTION SCOPE (A13 finding 1, live incident). The two lexical exemptions
above were originally checked against the whole final message -- so an EM
final message that both (a) genuinely hands an item to the PM and (b)
separately mentions this guard's own exemption vocabulary while discussing
something else entirely (e.g. summarizing the exemption list, or writing a
retro about this very guard) got silently exempted, with no observable
signal. `_trigger_window_text` narrows the check to the sentence carrying
the actual C5 trigger plus one sentence of surrounding context on each
side -- wide enough for a legitimate exemption phrasing that spans two
adjacent sentences (e.g. "before I force-push, may I get your
authorization? Your call --"), narrow enough that a mention several
sentences away, for an unrelated reason, no longer silently exempts.

SIZING EXEMPTION'S SECOND SCOPE (Chunk B, docs/plans/2026-08-11-stop-the-
guard-splat.md; the section proven by direct execution against a
reconstructed scenario matching the real on-disk sizing object's shape --
no confirmed live guard fire is attributed to this gap). A turn that
closes an appetite/post-size fork can legitimately report an UNRELATED PM
item first (e.g. a genuine "your call" scope question) and only THEN ask
the post-size prompt as its closing line -- the engine emits that prompt
to CLOSE the turn, so it can land past the ±1-sentence trigger window.
The sizing topic check therefore ALSO runs against the message's own
final sentence (`_final_sentence`), but ONLY when that final sentence is
the sentence immediately following the trigger window, with no
intervening filler sentence -- never as an unconditional second location,
and never merely because it falls outside the window. Consulting the
final sentence whenever it is merely outside the window (regardless of
distance) would let ANY final sentence carrying sizing vocabulary exempt
the whole turn no matter how far from the trigger, reopening A13 finding
1's incidental-co-occurrence failure mode at final-sentence scope; the
adjacency requirement keeps it to the one structural shape this fix
targets (trigger, its ±1 context, then the engine's own closing prompt
immediately after).

SEVERITY BY POSTURE: advisory (stdout, exit 0) at `precision`; blocking
(stderr, exit 2, Stop-family shape) at `default`/`substrate-free`, matching
`nudge-unrouted-sizing.py` and `nudge-harness-directive-dispatch.py` -- this
applies to the altitude verdict (C5) only.

SECOND VERDICT BRANCH (C6, A15-A17). C5 answers "is this the PM's call?".
This branch answers what comes after a YES: "can the PM actually answer it
as written?" -- checked once an item survives C5 (no trigger, or a triggered
item that an A13 exemption cleared). Detection is lexical (module-level
pattern data, same style as the two groups above): a bare identifier with no
plain-language gloss, the choice named as a category ("a scope call") rather
than stated, or no recommendation anywhere in the message. This branch is
UNCONDITIONALLY advisory-only, hardcoded rather than posture-gated -- it
never returns exit 2, at any posture. Suppressing a genuine PM decision for
being worded badly is the one unrecoverable failure on this surface; the
worst permitted outcome is that the EM restates it.

Contract:
  stdin   -- Stop JSON (session_id, transcript_path, cwd, stop_hook_active, agent_id...)
  stdout  -- the correction text, at posture `precision` only
  stderr  -- the correction text, at posture `default`/`substrate-free` only
  exit 2  -- guard fires at a blocking posture (blocks the stop; stderr shown to Claude)
  exit 0  -- every other path, including every failure path (fail-open)

Graceful degradation: any failure to read stdin, parse the transcript, or
resolve posture falls through to a silent exit 0 (posture resolution itself
already fails open to "precision" -- see `_posture.py`).
"""

from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _posture import resolve_posture  # noqa: E402

# ---------------------------------------------------------------------------
# Trigger patterns -- module-level DATA, not inline in the matching logic, so
# the vocabulary is reviewable and extensible in one place. Two named groups
# for two distinct speech-act shapes; both feed the same verdict.
# ---------------------------------------------------------------------------

# The overt handoff-to-PM construct -- the EM directly hands an item to the
# PM ("wait on you", "your call", ...).
_HANDOFF_PATTERNS = [
    re.compile(r"\bwait(?:s|ing)?\s+on\s+you\b", re.IGNORECASE),
    re.compile(r"\bblocks?\s+on\s+you\b", re.IGNORECASE),
    re.compile(r"\byour\s+call\b", re.IGNORECASE),
    re.compile(r"\bneeds?\s+your\s+(?:decision|input|sign-off)\b", re.IGNORECASE),
    re.compile(r"\bover\s+to\s+you\b", re.IGNORECASE),
    # An enumerated list introduced by a "now wait on you"-shaped clause.
    re.compile(r"\bnow\s+wait\s+on\s+you\b", re.IGNORECASE),
]

# The possessive form -- the EM tags an item as PM-owned by assertion rather
# than demonstrating it. The PM's own framing: a "tic" whose softening
# qualifier ("genuinely", "actually", "still", "and unchanged") is an
# aggravating signal, not a mitigating one.
_POSSESSIVE_PATTERNS = [
    re.compile(r"\bgenuinely\s+yours\b", re.IGNORECASE),
    re.compile(r"\bgenuinely\s+unresolved\b", re.IGNORECASE),
    re.compile(r"\bstill\s+yours\b", re.IGNORECASE),
    re.compile(r"\bone\s+item\s+that'?s\s+actually\s+yours\b", re.IGNORECASE),
    re.compile(r"that'?s\s+a\s+PM\s+call,?\s*not\s+mine\b", re.IGNORECASE),
    re.compile(r"\bis\s+yours\s+to\s+(?:decide|disposition|call)\b", re.IGNORECASE),
]

_PATTERN_GROUPS = (_HANDOFF_PATTERNS, _POSSESSIVE_PATTERNS)

# The bare ownership cue -- a third, narrower group that catches a handoff
# phrased too loosely for the first two groups ("...and it's yours.") but
# still marks the sentence as a candidate PM-handoff for the C6 decidability
# check below. Not itself an altitude verdict -- C5's own verdict is governed
# solely by `_PATTERN_GROUPS` above, unchanged.
_OWNERSHIP_CUE_PATTERNS = [
    re.compile(r"\b(?:is|'s)\s+yours\b", re.IGNORECASE),
    re.compile(r"\byours\s+to\s+\w+", re.IGNORECASE),
]

# ---------------------------------------------------------------------------
# C6 -- decidability patterns (A15). Once an item survives the altitude test
# (it is genuinely PM-owned -- C5 either didn't trigger, or triggered and was
# exempted), a second question applies: can the PM answer it as written, with
# zero retained context? Module-level DATA, same style as the two groups
# above, so the vocabulary stays reviewable and extensible in one place.
# ---------------------------------------------------------------------------

# A bare identifier with no plain-language gloss beside it: a chunk/AC id, a
# plan slug, or a hex SHA/delivery id. The chunk/AC forms are anchored to
# their usual citation shapes ("chunk C5", "AC A13", "(C5)", "/A13") rather
# than a standalone `\bC\d+\b`/`\bA\d+\b`, which also matches ordinary prose
# ("C3 propulsion", "A1 sauce", a room number) -- this heuristic is
# deliberately coarse where the citation shapes above don't apply, but C6 is
# advisory-only (never blocks), so the residual over-match is bounded to a
# spurious nudge, not a suppressed or blocked turn.
_BARE_IDENTIFIER_PATTERNS = [
    re.compile(r"\bchunk\s+C\d+\b", re.IGNORECASE),
    re.compile(r"\bAC\s+A\d+\b", re.IGNORECASE),
    re.compile(r"[(/]\s*[AC]\d+\b"),
    re.compile(r"\bdocs/plans/\S+"),
    re.compile(r"\b[0-9a-f]{7,40}\b", re.IGNORECASE),
    re.compile(r"\b(?:dlv|pln)-\S+", re.IGNORECASE),
]

# The choice named as a CATEGORY rather than stated -- "a scope call", "a
# product call", etc. -- with no statement of what the alternatives are.
_CATEGORY_CALL_RE = re.compile(
    r"\ba\s+(?:scope|product|direction|prioritization)\s+call\b", re.IGNORECASE
)

# Presence (not absence) of a recommendation -- checked against the WHOLE
# final message, since a recommendation need not sit in the same sentence as
# the handoff clause.
_RECOMMENDATION_RE = re.compile(
    r"\bI\s+recommend\b"
    r"|\bI'?d\s+suggest\b"
    r"|\bI\s+would\s+suggest\b"
    r"|\bmy\s+read\s+is\b"
    r"|\bI\s+lean\b"
    r"|\bunless\s+you'?d\s+rather\b"
    r"|\bunless\s+you\s+would\s+rather\b",
    re.IGNORECASE,
)

_DECIDABILITY_CORRECTION_TEXT = (
    "[guard] This is a PM call, but not decidable as written -- presume zero "
    "retained PM context: no bare identifiers up front, state the choice in "
    "plain words, the options, and a recommendation with its cost (this "
    "repo's reporting doctrine). Restate it so the PM can answer cold.\n"
)

# ---------------------------------------------------------------------------
# A13 exemptions.
# ---------------------------------------------------------------------------

# An irreversible/external act named without pre-authorization already
# granted. No established predicate exists elsewhere in this corpus for this
# exemption (unlike the sizing-fork one, which is copied verbatim) -- this is
# a conservative vocabulary match on the ask-before-external-action gate
# itself and its usual phrasing, kept narrow rather than broad per this
# guard's own "a false fire is worse than a miss" posture.
_EXTERNAL_ACTION_PENDING_RE = re.compile(
    r"ask-before-external-action"
    r"|external[- ]action\b.{0,40}\b(?:pending|awaiting|authoriz)"
    r"|(?:may\s+i|requesting\s+(?:your\s+)?(?:authorization|permission))\b.{0,60}"
    r"\b(?:push|force[- ]push|delete|deploy|merge|commit)\b"
    r"|before\s+i\s+(?:push|force[- ]push|delete|deploy|commit)\b.{0,40}"
    r"(?:\bok\b|\bokay\b|\bconfirm|authoriz|permission)",
    re.IGNORECASE,
)

# The conflict-of-interest / wrong-signatory exemption: an item only the PM
# can act on because the EM is structurally disqualified from acting on it
# (a two-decider record naming the EM as one of the deciders), not because of
# scope or direction. Lexical, module-level, same style as the other
# exemption -- co-occurrence preferred over a single loose keyword so an
# ordinary offload ("I wrote the plan, so the approach call is yours") cannot
# trivially borrow the phrasing.
_WRONG_SIGNATORY_PATTERNS = [
    re.compile(r"\bwrong\s+signat(?:ure|ory)\b", re.IGNORECASE),
    re.compile(r"\bratify(?:ing)?\s+my\s+own\b", re.IGNORECASE),
    re.compile(r"\bmy\s+own\s+authorship\b", re.IGNORECASE),
    re.compile(r"\bapprove\s+my\s+own\b", re.IGNORECASE),
    re.compile(r"\bsign(?:ing)?\s+off\s+on\s+my\s+own\b", re.IGNORECASE),
    re.compile(r"\btwo-decider\b", re.IGNORECASE),
    re.compile(r"\bnamed\s+deciders\b", re.IGNORECASE),
    re.compile(r"\bthe\s+record'?s\s+deciders\b", re.IGNORECASE),
    re.compile(r"\bboth\s+deciders\b", re.IGNORECASE),
]

# An authorship admission -- "I wrote/authored it" or "I am one of the named
# deciders" -- co-occurring with ratification/sign-off vocabulary ANYWHERE in
# the message. DELIBERATELY whole-message, not window-scoped (A13 finding 1):
# a real wrong-signatory report legitimately states the admission and the
# ratification ask in different sentences. Neither half alone is sufficient;
# an ordinary "I wrote the plan, so the approach call is yours" carries the
# admission half but no ratification vocabulary, so it must still fire the
# ordinary handoff check.
_AUTHORSHIP_ADMISSION_RE = re.compile(
    r"\bI\s+(?:wrote|authored)\s+\S+\b"
    r"|\bI(?:'m|\s+am)\s+one\s+of\s+the\s+named\s+deciders\b",
    re.IGNORECASE,
)

_RATIFICATION_VOCAB_RE = re.compile(
    r"\bsign[- ]?off\b|\bratif\w*\b|\bapprove\b", re.IGNORECASE
)


def _wrong_signatory_pending(scope: str, full_text: str) -> bool:
    """`scope` is the A13 trigger window (narrow, incidental-co-occurrence
    guarded); `full_text` is the whole final message, used only for the
    admission+ratification co-occurrence half, which is deliberately
    whole-message -- see `_AUTHORSHIP_ADMISSION_RE`'s comment."""
    if any(pattern.search(scope) for pattern in _WRONG_SIGNATORY_PATTERNS):
        return True
    return bool(
        _AUTHORSHIP_ADMISSION_RE.search(full_text)
        and _RATIFICATION_VOCAB_RE.search(full_text)
    )


_SIZING_PATH_RE = re.compile(r"^state/sizings/[^/]+\.ya?ml$")

_APPETITE_DIVERGENCE_DETENT = "appetite_exceeded"
_POST_SIZE_PROMPT_DETENT = "post_size_prompt_pending"

_TAIL_WINDOW_BYTES = 200_000

_CORRECTION_TEXT = (
    "[guard] This turn closed with a PM-handoff construct for an item the PM "
    "would not recognise by its own nouns. Apply the altitude test "
    "(the plan skill's B.0 un-gaming clause, on whichever route you loaded): "
    "a genuine PM call concerns scope, deliverable, or product direction, "
    "and states itself in the PM's vocabulary. If the PM would not recognise "
    "the nouns, "
    "it is an EM call -- decide it, do not hand it up. Re-close the turn "
    "having resolved it yourself, or state the genuine PM-altitude question "
    "plainly if one actually remains.\n"
)


def _tail_text(path: str, max_bytes: int = _TAIL_WINDOW_BYTES) -> str:
    """Return the last `max_bytes` of `path`, decoded, or "" on any I/O failure.

    Bounded binary-seek read -- never loads a multi-MB transcript whole. This
    is the ONLY read this module performs against the transcript; the whole
    conversation is never scanned.
    """
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            if size > max_bytes:
                fh.seek(size - max_bytes)
                fh.readline()  # discard the partial line the seek landed inside
            raw = fh.read()
        return raw.decode("utf-8", errors="replace")
    except OSError:
        return ""


def _final_assistant_text(transcript_path: str) -> str:
    """Return the text of the FINAL assistant message in the tail window, or "".

    Scans assistant entries in the bounded tail window and keeps only the
    last one seen -- this module never reads or reasons about any earlier
    turn in the conversation.
    """
    text = _tail_text(transcript_path)
    if not text:
        return ""
    last_text = ""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict) or entry.get("type") != "assistant":
            continue
        msg = entry.get("message")
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        # This IS the chronologically-last assistant entry seen so far --
        # always overwrite, never only-if-non-empty. A tool_use-only turn
        # (no text block) must reset last_text to "", not silently retain an
        # earlier turn's text; the module's own invariant is "final message
        # only", never "last message that happened to have text".
        last_text = "\n".join(parts) if parts else ""
    return last_text


def _matches_manufactured_blocker(text: str) -> bool:
    for patterns in _PATTERN_GROUPS:
        for pattern in patterns:
            if pattern.search(text):
                return True
    return False


def _external_action_pending(text: str) -> bool:
    return bool(_EXTERNAL_ACTION_PENDING_RE.search(text))


def _repo_root(payload: dict) -> str | None:
    cwd = payload.get("cwd") or os.getcwd()
    if not isinstance(cwd, str):
        return None
    probe = os.path.abspath(cwd)
    while True:
        if os.path.exists(os.path.join(probe, ".git")):
            return probe
        parent = os.path.dirname(probe)
        if parent == probe:
            return None
        probe = parent


def _resolve_git_dir(dot_git: str) -> str | None:
    if os.path.isdir(dot_git):
        return dot_git
    try:
        with open(dot_git, "r", encoding="utf-8", errors="replace") as fh:
            pointer = fh.read().strip()
    except OSError:
        return None
    if not pointer.startswith("gitdir:"):
        return None
    target = pointer[len("gitdir:"):].strip()
    if not target:
        return None
    if not os.path.isabs(target):
        target = os.path.join(os.path.dirname(dot_git), target)
    return os.path.normpath(target)


def _touch_path(line: str) -> str | None:
    """Return the bare repo-relative path a `touched.txt` line records.

    Tolerates both the verb-prefixed event shape ('T <ISO-8601> <path>') and
    the bare legacy `<path>`-only line.
    """
    line = line.strip()
    if not line:
        return None
    parts = line.split()
    if len(parts) >= 3 and parts[0] in ("T", "R"):
        return parts[-1]
    return line


def _extract_scalar(lines: list[str], key: str) -> str | None:
    """Flat `key: value` line-scan, matching `_posture.py`'s own idiom."""
    prefix = key + ":"
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith(prefix):
            value = stripped[len(prefix):].strip()
            if "#" in value:
                value = value.split("#", 1)[0].strip()
            value = value.strip("'\"")
            return value
    return None


def _extract_detents(lines: list[str]) -> list[str]:
    """Return the `detents` list values from a flat sizing-object line-scan.

    Handles both the inline-list shape (`detents: [a, b]`) and the block-list
    shape (`detents:` followed by `  - a` lines). No general YAML parsing --
    stdlib-only, mirroring `_posture.py`'s own line-scan convention.
    """
    values: list[str] = []
    collecting = False
    for raw_line in lines:
        stripped = raw_line.strip()
        if not collecting:
            if not stripped.startswith("detents:"):
                continue
            rest = stripped[len("detents:"):].strip()
            if rest.startswith("[") and rest.endswith("]"):
                inner = rest[1:-1]
                return [item.strip().strip("'\"") for item in inner.split(",") if item.strip()]
            collecting = True
            continue
        if stripped.startswith("- "):
            values.append(stripped[2:].strip().strip("'\""))
        elif stripped == "":
            continue
        else:
            break
    return values


def _is_null_scalar(value: str | None) -> bool:
    return value is None or value in ("null", "~", "None", "")


# The sizing exemption is topical, not turn-global: an open post-size prompt
# exempts the sentence that ASKS it, never every possessive construct that
# happens to share the turn. Matched generously -- A13's "a false fire is
# worse than a miss" applies to the exemption too, so an ambiguous sizing
# sentence resolves toward silence.
_SIZING_TOPIC_PATTERNS = [
    re.compile(r"\bt-?shirt\b", re.IGNORECASE),
    re.compile(r"\bappetite\b", re.IGNORECASE),
    re.compile(r"\bxl[_ -]?exit\b", re.IGNORECASE),
    re.compile(r"\bpm-decision\b", re.IGNORECASE),
    re.compile(r"\b(?:XS|XL|XXL)\b"),
    re.compile(r"\b(?:cut|split)\s+it\b", re.IGNORECASE),
    re.compile(r"\bgo\s+with\s+that\b", re.IGNORECASE),
    re.compile(r"\bmulti-session\b", re.IGNORECASE),
    # Unambiguous sizing-gate vocabulary only -- bare `size`/`sized`/`sizing`
    # was dropped (review finding): an ordinary word like "window size" or
    # "resize the panel" carries no necessary connection to the PM
    # sizing-gate, and combined with any session that has an open post-size
    # fork this reopened a narrower version of the exact turn-global leak
    # the topical-scoping fix exists to close.
    re.compile(r"\bsizing\s+lobby\b", re.IGNORECASE),
    re.compile(r"\bsized\s+it\b", re.IGNORECASE),
    re.compile(r"\bpost_size_prompt\b", re.IGNORECASE),
]


def _sizing_topic_in_scope(scope: str) -> bool:
    """Return True iff the C5 trigger window is talking about the size of the
    ask -- the only subject the open post-size/XL-exit prompt can be about."""
    return any(pattern.search(scope) for pattern in _SIZING_TOPIC_PATTERNS)


def _sizing_object_exempts(repo_root: str, rel_path: str) -> bool:
    """Return True iff the sizing object at `rel_path` carries an unresolved
    appetite/post-size fork or an unresolved XL exit.

    Predicate copied from the sibling engine's `nudge_unrouted_sizing` op
    (`_appetite_fork_open` / `_post_size_prompt_open` / the `route:
    pm-decision` + `xl_exit: null` case in `_matches_criteria`) --
    reimplemented as a self-contained stdlib line-scan since this guard has
    no sibling engine op to delegate to (unlike the DR-118 transport shims).

    Any read/parse failure reads as "cannot prove the exemption doesn't
    apply" -> True -> silence, matching the source predicate's own
    fail-toward-silence posture on every hard-exemption read.
    """
    try:
        with open(os.path.join(repo_root, rel_path), "r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return True

    route = _extract_scalar(lines, "route")
    fork = _extract_scalar(lines, "fork")
    xl_exit = _extract_scalar(lines, "xl_exit")
    detents = _extract_detents(lines)

    # A recorded `pm_resolution` block IS the answer to the post-size prompt.
    # `fork` alone cannot carry that signal: the engine always emits it null
    # and the schema fills it only when the PM's answer happens to be cut- or
    # raise-shaped, so a "go with that" or a straight resize leaves it null
    # for the life of the object.
    if any(line.strip().startswith("pm_resolution:") for line in lines):
        return False

    fork_open = (
        _APPETITE_DIVERGENCE_DETENT in detents or _POST_SIZE_PROMPT_DETENT in detents
    ) and _is_null_scalar(fork)
    xl_open = route == "pm-decision" and _is_null_scalar(xl_exit)
    return fork_open or xl_open


def _sizing_exemption_applies(payload: dict) -> bool:
    """Outer preconditions (no session id, no resolvable repo root, no
    `.git`, no `touched.txt` for this session) fail to False -- no
    exemption -- deliberately NOT matching `_sizing_object_exempts`'s
    fail-toward-True posture on its own inner YAML read. The two are not
    the same kind of failure: by the time `_sizing_object_exempts` runs, a
    sizing file is already known to have been touched this turn, so failing
    toward silence is bounded to that one file. Failing open on a missing
    repo root or missing touched.txt would instead exempt on every
    unresolvable-environment case regardless of whether a sizing object was
    ever in play -- effectively disabling C5 whenever the guard can't find
    `.git` (a live case: this module's own test harness runs the guard
    against a plain tmp_path with no `.git` anywhere above it), which is a
    worse failure than the miss this asymmetry accepts.
    """
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        return False
    repo_root = _repo_root(payload)
    if repo_root is None:
        return False
    git_dir = _resolve_git_dir(os.path.join(repo_root, ".git"))
    if not git_dir:
        return False
    touched_path = os.path.join(git_dir, "coordinator-sessions", session_id, "touched.txt")
    try:
        with open(touched_path, "r", encoding="utf-8", errors="replace") as fh:
            raw_lines = fh.readlines()
    except OSError:
        return False

    sizing_paths = []
    for raw_line in raw_lines:
        rel = _touch_path(raw_line)
        if rel and _SIZING_PATH_RE.match(rel):
            sizing_paths.append(rel)

    return any(_sizing_object_exempts(repo_root, rel) for rel in sizing_paths)


def _split_sentences(text: str) -> list[str]:
    """Coarse sentence split -- lexical, not linguistic. Good enough to scope
    the bare-identifier / category-call checks to the sentence carrying the
    handoff/possessive construct rather than the whole message."""
    pieces = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip() for p in pieces if p.strip()]


def _trigger_window_idxs(text: str) -> tuple[list[str], set[int]]:
    """Return `(sentences, window_idxs)` -- the sentence list and the set of
    sentence indices in the A13 exemption-check scope (every sentence
    carrying a C5 trigger, plus one sentence of context on each side; see
    the module docstring's EXEMPTION SCOPE section). `window_idxs` is empty
    when no trigger sentence is found."""
    sentences = _split_sentences(text)
    if not sentences:
        return sentences, set()
    trigger_idxs = set()
    for i, sentence in enumerate(sentences):
        for patterns in _PATTERN_GROUPS:
            if any(pattern.search(sentence) for pattern in patterns):
                trigger_idxs.add(i)
                break
    if not trigger_idxs:
        return sentences, set()
    window_idxs = set()
    for i in trigger_idxs:
        window_idxs.update(range(max(0, i - 1), min(len(sentences), i + 2)))
    return sentences, window_idxs


def _trigger_window_text(text: str) -> str:
    """Return the A13 exemption-check scope text -- see `_trigger_window_idxs`.

    Falls back to the whole message if no trigger sentence is found (the
    caller only reaches this once a trigger has already matched somewhere
    in the message, so this is defensive, not a real path)."""
    sentences, window_idxs = _trigger_window_idxs(text)
    if not sentences or not window_idxs:
        return text
    return " ".join(sentences[i] for i in sorted(window_idxs))


def _any_exemption_applies(payload: dict, text: str) -> bool:
    sentences, window_idxs = _trigger_window_idxs(text)
    scope = " ".join(sentences[i] for i in sorted(window_idxs)) if window_idxs else text

    # The final sentence is consulted for sizing vocabulary ONLY when it sits
    # IMMEDIATELY after the trigger window with no intervening sentence --
    # the structural shape an engine-emitted closing prompt produces
    # (module docstring, SIZING EXEMPTION'S SECOND SCOPE): the window ends
    # before the message does, and the final sentence is the very next one.
    # Contiguity, not merely "outside the window", is the gate: without it,
    # a trigger sentence far from the end with unrelated filler sentences in
    # between would still let ANY final sentence carrying sizing vocabulary
    # exempt the whole turn regardless of distance from the trigger -- the
    # A13 incidental-co-occurrence failure mode this guard exists to close,
    # reopened at final-sentence scope. Requiring adjacency narrows this to
    # the one shape the fix targets (trigger, then immediate context, then
    # the engine's own closing prompt) without accepting that residual risk.
    final_idx = len(sentences) - 1 if sentences else -1
    final_sentence_eligible = bool(window_idxs) and final_idx == max(window_idxs) + 1
    sizing_in_scope = _sizing_topic_in_scope(scope) or (
        final_sentence_eligible and _sizing_topic_in_scope(_final_sentence(text))
    )
    return (
        _external_action_pending(scope)
        or (sizing_in_scope and _sizing_exemption_applies(payload))
        or _wrong_signatory_pending(scope, text)
    )


def _candidate_ownership_sentence(text: str) -> str | None:
    """Return the first sentence carrying a handoff/possessive/ownership
    construct, or None if the message hands nothing to the PM at all."""
    groups = (_HANDOFF_PATTERNS, _POSSESSIVE_PATTERNS, _OWNERSHIP_CUE_PATTERNS)
    for sentence in _split_sentences(text):
        for patterns in groups:
            for pattern in patterns:
                if pattern.search(sentence):
                    return sentence
    return None


def _has_bare_identifier(sentence: str) -> bool:
    return any(pattern.search(sentence) for pattern in _BARE_IDENTIFIER_PATTERNS)


def _has_category_call(sentence: str) -> bool:
    return bool(_CATEGORY_CALL_RE.search(sentence))


def _has_recommendation(full_text: str) -> bool:
    return bool(_RECOMMENDATION_RE.search(full_text))


def _fails_decidability(sentence: str, full_text: str) -> bool:
    """A15: any one of the three signals is sufficient -- a bare identifier
    with no gloss, the choice named as a category rather than stated, or no
    recommendation anywhere in the message."""
    return (
        _has_bare_identifier(sentence)
        or _has_category_call(sentence)
        or not _has_recommendation(full_text)
    )


# ---------------------------------------------------------------------------
# C10 -- the declarative stall. The EM ends its turn having ANNOUNCED its next
# action rather than taken it ("Proceeding with: A, then B, then C."), so the
# work resumes only when the PM speaks. No question is asked and no second
# person appears, so neither C5 group can see it; no tool is called, so the
# AskUserQuestion nudge cannot; and a self-authored slate opens no ledger
# obligation, so the next-move watchdog has nothing to leave undischarged.
#
# Matched ONLY against the final sentence. An intent stated mid-message and
# then acted on in the same turn is a report, not a stall -- it is the
# announcement in terminal position that makes the turn end on a promise.
#
# ADVISORY-ONLY by construction (see `_emit_declarative_stall_verdict`): this
# is a speech act whose wrongness depends on whether the action was available,
# which the guard cannot see. A13's "a false fire is worse than a miss" is
# discharged by never blocking, not by narrowing until the tic escapes.
# ---------------------------------------------------------------------------

_DECLARATIVE_STALL_PATTERNS = [
    re.compile(r"^\s*(?:now\s+|so\s+)?proceeding\s+with\b", re.IGNORECASE),
    re.compile(r"^\s*(?:now\s+)?(?:starting|beginning)\s+(?:on|with|the)\b", re.IGNORECASE),
    re.compile(
        r"\bI'?ll\s+(?:now\s+)?(?:start|begin|get\s+on\s+with|move\s+on\s+to|"
        r"crack\s+on\s+with|kick\s+off|pick\s+up)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bnext\s+(?:up\b|I'?ll\b)", re.IGNORECASE),
    # The confessional subspecies -- the EM narrating its own course
    # correction to the PM instead of simply correcting course.
    re.compile(r"\bI'?ll\s+stop\s+\w+ing\b", re.IGNORECASE),
]

_DECLARATIVE_STALL_CORRECTION_TEXT = (
    "[guard] This turn ends on an announcement of the next action rather than "
    "the action. Announcing and stopping is a wait wearing the costume of "
    "momentum: the work resumes only when the PM speaks, and the PM is "
    "charged a turn for a result they did not receive. If the action was "
    "available, take it and report what happened; if it was genuinely "
    "blocked, name the blocker and your recommendation. "
    "'Phase/wave/chunk boundaries are not stop boundaries' "
    "(coordinator/snippets/em-operating-doctrine.md).\n"
)


def _final_sentence(text: str) -> str:
    """Not fence/table-aware, unlike `_final_stall_unit`: a message ending on
    a trailing code-fence or table line returns that line, not the prose
    above it -- acceptable today because the engine's post-size prompt is
    plain prose, but a future editor should not assume this is fence-aware."""
    sentences = _split_sentences(text)
    return sentences[-1] if sentences else ""


# A bulleted or numbered continuation line -- "- x", "* x", "+ x", "1. x",
# "2) x". `_final_stall_unit` strips these back to the line that introduces
# them, since `_split_sentences`'s hard `\n+` split otherwise leaves the last
# list item as the checked unit and the announcement itself (e.g.
# "Proceeding with:") goes unseen -- the most common real shape of a
# declarative stall in this repo's own bullet-favoring conventions.
_BULLET_CONTINUATION_LINE_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")


def _final_stall_unit(text: str) -> str:
    """Return the text C10 checks for a terminal announcement.

    Terminal-position discipline is preserved: only the LAST paragraph (text
    after the last blank line) is ever considered, and within it, trailing
    bullet/numbered lines are walked back to the non-bullet line that
    introduces them -- never merged across a blank-line paragraph break, and
    never pulled from mid-message. A paragraph with no trailing bullet lines
    falls back to the ordinary final-sentence check, unchanged.
    """
    paragraphs = [p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    if not paragraphs:
        return ""
    lines = [ln for ln in paragraphs[-1].splitlines() if ln.strip()]
    if len(lines) > 1 and _BULLET_CONTINUATION_LINE_RE.match(lines[-1]):
        idx = len(lines) - 1
        while idx > 0 and _BULLET_CONTINUATION_LINE_RE.match(lines[idx]):
            idx -= 1
        if not _BULLET_CONTINUATION_LINE_RE.match(lines[idx]):
            return lines[idx].strip()
    return _final_sentence(text)


def _is_declarative_stall(text: str) -> bool:
    unit = _final_stall_unit(text)
    if not unit:
        return False
    return any(pattern.search(unit) for pattern in _DECLARATIVE_STALL_PATTERNS)


def _emit_declarative_stall_verdict(text: str) -> int:
    """UNCONDITIONAL advisory-only, on the same hardcoded footing as
    `_emit_decidability_verdict` -- never returns 2, at any posture."""
    if _is_declarative_stall(text):
        sys.stdout.write(_DECLARATIVE_STALL_CORRECTION_TEXT)
    return 0


def _emit_decidability_verdict(candidate: str, text: str) -> int:
    """A17: UNCONDITIONAL advisory-only. Never returns 2, at any posture --
    this is not a posture lookup a later edit could widen, it is hardcoded
    here. A genuine PM call worded badly must never be suppressed."""
    if _fails_decidability(candidate, text):
        sys.stdout.write(_DECIDABILITY_CORRECTION_TEXT)
    return 0


def main() -> int:
    try:
        raw = sys.stdin.read()
    except Exception:
        return 0

    try:
        payload = json.loads(raw) if raw else {}
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    if payload.get("agent_id"):
        return 0
    if payload.get("stop_hook_active"):
        return 0

    transcript_path = payload.get("transcript_path")
    if not isinstance(transcript_path, str) or not transcript_path:
        return 0

    text = _final_assistant_text(transcript_path)
    if not text:
        return 0

    if not _matches_manufactured_blocker(text):
        # C5's own trigger groups didn't fire -- this is not an off-altitude
        # handoff. It may still be a genuinely PM-owned item worded as a bare
        # ownership cue (e.g. "...and it's yours."); C6 checks decidability
        # on that candidate sentence. No candidate at all -> silent.
        # C10 runs here and not on the blocking path: a turn already stopped
        # for an off-altitude handoff has its correction, and stacking a
        # second one buries it. C10 and C6 are mutually exclusive on this
        # path too -- C10 only runs when no ownership candidate exists, so a
        # message never carries both advisories in the same turn.
        candidate = _candidate_ownership_sentence(text)
        if candidate is None:
            return _emit_declarative_stall_verdict(text)
        return _emit_decidability_verdict(candidate, text)

    if _any_exemption_applies(payload, text):
        # ALTITUDE PASSED (A13 exemption -- a real PM gate). Ordering (A15):
        # altitude first, decidability second. This item survived C5; now C6
        # asks whether the PM can actually answer it as written.
        candidate = _candidate_ownership_sentence(text) or text
        return _emit_decidability_verdict(candidate, text)

    try:
        posture = resolve_posture()
    except Exception:
        posture = "precision"

    if posture in ("default", "substrate-free"):
        sys.stderr.write(_CORRECTION_TEXT)
        return 2

    sys.stdout.write(_CORRECTION_TEXT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
