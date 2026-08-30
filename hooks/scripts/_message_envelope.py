"""The single message-construction seam every Category-A (locally-authored,
speaking) hook under `coordinator/hooks/scripts/` routes through.

Purpose: the PM named a concrete failure mode -- guard prose growing without
bound because doctrine alone never enforced a limit, and a static/lint check
over source text cannot see prose assembled at emit time from `_`-prefixed
helper templates (`guard-doctrine-surface-bash-write.py` measures 0 chars
statically, 1,744 at runtime). This module gives every Category-A hook one
place to compose its message so a runtime harness can measure it correctly,
and gives every future hook author the 280-char ceiling and the fenced-
alternative exemption "by construction" rather than by remembering a rule
written in a wiki.

NEVER used by a Category-B (DR-118 pointer/relay) hook. DR-118
(`docs/decisions/DR-118-doe-resident-transport-seam-is-a-pointer.md`) rules
that a doctrine-plane-resident transport seam holds no message policy of its own --
"resolve, hand over, translate, degrade unconditionally at every step -- no
fail-open policy, no detection policy of its own." A Category-B shim's
prose is authored on the sibling engine plane and relayed verbatim
(`_engine_root.run_stop_hook_pointer_shim` and its siblings); routing it
through this envelope would hand a doctrine-plane-resident transport seam message
policy DR-118 forbids it from holding. Category-A hooks own their own
prose and are exactly what this module is for.

Two responsibilities, deliberately kept in one small module rather than
split, because C1's in-process measurement harness needs both:

  1. A PURE composing callable (`compose`) -- separable from any
     stdin-reading `main()` and from exit-code plumbing -- that a hook's
     own message-constructor function builds a `Message` with, and that
     C1 can call directly (no process, no stdin, no environment setup) once
     per emission site in its parameter sweep.
  2. An IMPURE `emit` that actually writes a composed `Message` to one of
     the three real hook channels in use (Stop stderr+exit-2, PreToolUse
     `additionalContext`, PreToolUse `permissionDecisionReason`), UNLESS
     `COORDINATOR_HOOK_MESSAGE_MEASURE=1` is set, in which case it writes a
     structured `{"prose": ..., "alternative": ..., "anchor": ...}` record
     instead of the flattened channel text -- this is what lets the harness
     measure `len(prose)` directly rather than re-parsing triple-backtick
     fences out of an already-flattened blob (the Staff Engineer finding this
     module exists to close: any hook could otherwise wrap arbitrary prose
     in backticks and score zero).

Spec: `docs/plans/2026-08-02-guard-message-character-cap.md` § C2 (see also
the plan's "Measurement mechanism" and "The cap-versus-ladder tension"
sections) and DR-118.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

#: The cap, defined once. C3 (the exception manifest) and C4 (the five-leg
#: gate test) import this constant; they do not redeclare it. See the plan's
#: "The cap is five separately-testable legs" section for how 280 was
#: derived from a working exemplar, not chosen for round-numberedness.
#:
#: RULED (2026-08-13, `docs/plans/2026-08-13-doe-guard-text-trust-failure-
#: coverage.md` chunk C6, AC7): kept at 280 CHARS, deliberately NOT
#: converged with the sibling control-plane engine's own 220-BYTE guard-
#: message cap. Two independent reasons, either sufficient on its own:
#:   1. Different corpora. 280 was derived here against THIS repo's own
#:      Category-A hook population (`docs/plans/2026-08-02-guard-message-
#:      character-cap.md`'s "working exemplar" derivation); the sibling
#:      figure was derived against a different corpus entirely. A shared
#:      number would be true of neither corpus by construction -- two
#:      different real distributions coincidentally sharing a digit.
#:   2. Different units. The sibling figure counts BYTES; this ceiling
#:      counts Python `len(str)` CHARS. Reassigning 280 to mean bytes, or
#:      rescaling it to a byte-equivalent, would change what the 26 tests
#:      currently passing against it actually measure, for no
#:      corpus-derived reason.
#: Converging the two numbers on sight is a number-matching move, not a
#: corpus-derived one -- exactly what this repo's own Anti-scope for this
#: chunk warns against. If a future measured Category-A distribution
#: genuinely outgrows 280, that is grounds to re-derive a NEW char ceiling
#: from THIS corpus, never to borrow the sibling's byte figure.
CEILING = 280

#: Environment variable that switches `emit()` from writing a hook's real
#: channel output to writing a structured measurement record instead. Set by
#: C1's in-process harness, never by a hook itself.
MEASURE_ENV_VAR = "COORDINATOR_HOOK_MESSAGE_MEASURE"

#: The three channel shapes in use across `coordinator/hooks/scripts/`
#: today (see the plan's Measurement mechanism section). `emit()` accepts
#: exactly one of these.
CHANNEL_STOP = "stop"
CHANNEL_ADDITIONAL_CONTEXT = "additional_context"
CHANNEL_DENY = "deny"

_CHANNELS = frozenset({CHANNEL_STOP, CHANNEL_ADDITIONAL_CONTEXT, CHANNEL_DENY})

#: A bounded line count for the fenced alternative block (AC3's "bounded
#: line count" leg). Not specified numerically by the plan; picked generous
#: enough for a real copy-pasteable command/diff (a few lines) while still
#: ruling out a converted hook smuggling paragraphs of prose into the
#: exempt slot under cover of a fence.
ALTERNATIVE_MAX_LINES = 10


@dataclass(frozen=True)
class Message:
    """The result of `compose()` -- what `emit()` writes to a real channel
    or a measurement record. `prose` is the only field the 280-char ceiling
    counts; `alternative` and `anchor` are structurally separate and
    EXEMPT from the count (see AC3)."""

    prose: str
    alternative: Optional[str] = None
    anchor: Optional[str] = None


# --------------------------------------------------------------------------
# Alternative-block shape validation (AC3) -- the structural exemption.
# Exposed as an importable function so C4's `_goes_red` teeth can drive it
# with synthesized data, per the chunk brief.
# --------------------------------------------------------------------------

#: First non-blank-line "looks like a command or path" proxy. Deliberately
#: cheap, not a real shell parser -- see `_looks_like_command_or_path`'s own
#: docstring for what it does and does not catch. A token carrying a literal
#: `$` (a `${VAR}`/`$VAR` shell expansion) is checked against the WIDER
#: `_SHELL_VAR_TOKEN_RE` instead -- kept as a separate, narrower carve-out
#: (gated on the presence of `$`) rather than folding `${}:=,@%+~` into the
#: base charset outright, so a bare colon-bearing prose token (e.g. `Note:`)
#: does not newly slip through just because the base charset widened.
#: A Windows drive-letter prefix -- a single letter immediately followed by
#: `:` and a path separator -- is admitted as an optional leading segment,
#: mirroring the identical narrow carve-out `_PROSE_PUNCT_RE` already
#: applies to the SAME shape (see that regex's own comment). This is the
#: only new thing the widened charset admits: a bare drive-letter colon at
#: the very start of the token, still followed by a separator. It does not
#: admit a colon anywhere else in the token (a mid-token colon, or a
#: trailing prose colon, still fail), so a genuinely malformed alternative
#: block is no more likely to pass than before.
_COMMAND_TOKEN_RE = re.compile(r"^(?:[A-Za-z]:[\\/])?[A-Za-z0-9_./\\-]+$")
_SHELL_VAR_TOKEN_RE = re.compile(r"^[A-Za-z0-9_./\\${}:=,@%+~-]+$")
_SENTENCE_END_RE = re.compile(r"[.!?]\s*$")
#: A comma/semicolon/em-dash, or a colon that is not part of a
#: drive-letter-style path prefix (a single letter immediately followed by
#: `:` and a path separator) -- punctuation shapes common in natural-
#: language prose and rare in a single command or path invocation.
_PROSE_PUNCT_RE = re.compile(r"[,;\u2014]|(?<![A-Za-z]):(?![\\/])")
#: Curated content-word list (pre-existing) -- two or more hits among the
#: line's tokens is treated as prose. Kept at its original >=2 threshold
#: for back-compat: these are ordinary content words that CAN legitimately
#: appear once in a real command/path (e.g. a flag literally named `name`),
#: so a single incidental hit is not enough on its own.
_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "is",
        "are",
        "that",
        "this",
        "instead",
        "name",
        "one",
        "dispatch",
        "applies",
        "reviewer",
        "or",
        "not",
        "amending",
        "for",
    }
)
#: Closed-class English grammar words (articles, prepositions, conjunctions,
#: pronouns, auxiliary/modal verbs) -- ANY single hit among the line's
#: tokens is treated as prose, unlike `_STOPWORDS`'s >=2 threshold. A real
#: shell command or path essentially never contains a standalone closed-
#: class function word as one of its own tokens (flags, subcommands, and
#: path segments are open-class/symbolic, not grammatical glue); an
#: imperative remedy PHRASE ("delete THE shebang line", "IRREDUCIBLE_LITERALS
#: IN _oss_operative_strings.py") almost always does, in exactly the two
#: reviewer-found bypasses this hardening closes. Deliberately excludes
#: everyday CLI-subcommand-shaped verbs (`add`, `remove`, `use`, `fix`, ...)
#: -- those are NOT closed-class and appear in genuine commands (`git add`),
#: so blacklisting them would reject real, live hook alternatives instead of
#: only the prose-smuggling shape this set targets.
_FUNCTION_WORDS = frozenset(
    {
        "the", "a", "an",
        "in", "on", "at", "by", "with", "from", "into", "onto", "of", "to",
        "as", "before", "after", "under", "over", "about", "between",
        "during", "without", "within", "than", "per", "via", "against",
        "and", "but", "nor", "yet", "because", "if", "unless", "while",
        "though", "although", "then",
        "it", "its", "these", "those", "which", "who", "whom", "whose",
        "was", "were", "be", "been", "being", "has", "have", "had",
        "do", "does", "did", "will", "would", "can", "could", "should",
        "must", "may", "might",
    }
)


def _first_non_blank_line(text: str) -> Optional[str]:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def _looks_like_command_or_path(line: str) -> bool:
    """Cheap runnability proxy for AC3: does `line` look like a
    copy-pasteable command or path invocation rather than a prose sentence?

    Deliberately NOT a shell parser. It rejects a line that ends in
    sentence-terminating punctuation, carries prose-shaped punctuation
    (comma/semicolon/em-dash/non-drive-letter colon), whose first token is
    not a plausible executable/path shape, that carries two or more of the
    curated content-word `_STOPWORDS`, OR that carries even ONE closed-class
    `_FUNCTION_WORDS` grammar word among its tokens -- the last check is what
    closes the reviewer-found bypass (a stopword-count heuristic alone let a
    short imperative remedy PHRASE like "delete the shebang line" or
    "IRREDUCIBLE_LITERALS in _oss_operative_strings.py" parse as
    command-shaped: neither carries 2+ `_STOPWORDS` hits, but each carries
    exactly the kind of grammatical glue word real commands/paths never
    do). This is enough to make AC3's falsifiable property hold -- prose
    wrapped in a fence fails this check -- without claiming to validate that
    a command is actually runnable."""
    if not line:
        return False
    if _SENTENCE_END_RE.search(line):
        return False
    if _PROSE_PUNCT_RE.search(line):
        return False
    tokens = line.split()
    if not tokens:
        return False
    first_token = tokens[0].strip("\"'")
    if not first_token:
        return False
    token_shaped = bool(_COMMAND_TOKEN_RE.match(first_token))
    if not token_shaped and "$" in first_token:
        token_shaped = bool(_SHELL_VAR_TOKEN_RE.match(first_token))
    if not token_shaped:
        return False
    normalized_tokens = [t.strip(".,;:'\"").lower() for t in tokens]
    if any(t in _FUNCTION_WORDS for t in normalized_tokens):
        return False
    stopword_hits = sum(1 for t in normalized_tokens if t in _STOPWORDS)
    if stopword_hits >= 2:
        return False
    return True


def validate_alternative_shape(
    alternative: Optional[str], *, max_lines: int = ALTERNATIVE_MAX_LINES
) -> "tuple[bool, Optional[str]]":
    """The alternative-block structural validator (AC3), importable
    directly so C4's `_goes_red` teeth can drive it with synthesized data
    rather than live disk state.

    Returns `(True, None)` when `alternative` is `None` (no block supplied
    -- always valid) or a valid runnable block. Returns `(False, reason)`
    otherwise. Enforces, in order:

      - non-empty text;
      - no embedded triple-backtick fence -- callers pass RAW block text,
        this module owns the fencing at render time (`render()`); an
        embedded fence would let a caller smuggle a second "alternative"
        inside the first, defeating the "at most one alternative per
        message" rule that `compose()`'s single-parameter signature
        otherwise enforces structurally;
      - at most `max_lines` lines;
      - the first non-blank line parses as a command or path invocation
        (`_looks_like_command_or_path`) -- this is the check that makes
        AC3's falsifiable property hold: prose wrapped in a fence must NOT
        pass as an alternative.
    """
    if alternative is None:
        return True, None
    if not isinstance(alternative, str) or not alternative.strip():
        return False, "alternative must be non-empty text"
    if "```" in alternative:
        return False, "alternative must not itself contain a fenced block"
    lines = alternative.splitlines()
    if len(lines) > max_lines:
        return False, f"alternative exceeds the {max_lines}-line bound"
    first = _first_non_blank_line(alternative)
    if first is None:
        return False, "alternative has no non-blank line"
    if not _looks_like_command_or_path(first):
        return (
            False,
            "alternative's first non-blank line does not parse as a "
            "command or path invocation",
        )
    return True, None


# --------------------------------------------------------------------------
# The pure composer. C1 calls this (or a hook's own thin wrapper around it)
# directly per emission site, with no process, stdin, or environment setup.
# --------------------------------------------------------------------------


def compose(
    prose: str, alternative: Optional[str] = None, anchor: Optional[str] = None
) -> Message:
    """Build a `Message` from a hook's diagnosis (`prose`, the ONLY field
    the 280-char ceiling counts), an optional fenced runnable `alternative`
    (structurally separate, exempt from the count -- see
    `validate_alternative_shape`), and an optional wiki `anchor` naming
    where the relocated explanation lives.

    Pure: no I/O, no environment read, no process interaction. Raises
    `ValueError` on a shape violation (empty prose, an invalid alternative
    block, or an empty-string anchor) rather than composing a malformed
    `Message` -- callers (hooks, and C1's harness) get the failure at the
    point of composition, not silently downstream at measurement or emit
    time."""
    if not isinstance(prose, str) or not prose.strip():
        raise ValueError("_message_envelope.compose: prose must be non-empty text")
    if alternative is not None:
        ok, reason = validate_alternative_shape(alternative)
        if not ok:
            raise ValueError(f"_message_envelope.compose: invalid alternative block ({reason})")
    if anchor is not None and (not isinstance(anchor, str) or not anchor.strip()):
        raise ValueError(
            "_message_envelope.compose: anchor must be non-empty text when provided"
        )
    return Message(prose=prose.strip(), alternative=alternative, anchor=anchor)


# --------------------------------------------------------------------------
# Wiki-citation resolution -- the C2 seam fix.
#
# Every `_WIKI_ANCHOR` constant across the 16 converted hooks (and the
# hand-rolled "Reference: docs/wiki/..." strings in the two runtime-tripwire
# hooks) is authored as a `coordinator/docs/wiki/<page>.md#<slug>`-shaped
# literal. That literal is REPO-RELATIVE: it resolves only from this source
# repo's own root, and 404s for a reader in any OTHER repo the plugin is
# installed into (verified live from project-rag's checkout -- see the C2
# dispatch report). `render()` was appending it verbatim ("See <anchor>."),
# per the standing reviewer note in `derive-global-doctrine-live-copy.py`
# that a bare fragment (no path at all) is even less useful -- that note is
# correct and is why the fix is NOT to strip the path down, but to resolve
# it against the plugin root the hook is ACTUALLY running from.
#
# `_coordinator_dir()` is deliberately NOT `os.environ["CLAUDE_PLUGIN_ROOT"]`.
# `enforce-agent-dispatch-mode.py`'s "Concern B" note records that env var
# as an "undeclared ... dependency" not reliably present/correct in a hook
# subprocess's own environment. What IS reliable: this very module's own
# `__file__`. Every hook that carries a `_WIKI_ANCHOR` lives at
# `<coordinator-dir>/hooks/scripts/<hook>.py` in EVERY install shape (this
# dev source tree, or a `--plugin-dir`-resolved installed copy) -- that is a
# structural fact of the plugin layout, not an inherited value that can go
# missing or point somewhere else.
# --------------------------------------------------------------------------

#: `docs/wiki/`, optionally `coordinator/`-prefixed -- the two forms
#: observed across the 16 `_WIKI_ANCHOR` constants and the six hand-rolled
#: runtime-tripwire "Reference:" citations (see the C2 plan chunk body for
#: the full site list).
#:
#: The page part spans SUBDIRECTORIES, not just a flat page name: real
#: anchors live at `docs/wiki/coordinator-tripwires/<page>.md` and
#: `docs/wiki/coordinator-tripwires/tripwire-registry/<page>.md`. Each
#: interior segment must itself match the same conservative character class
#: and the final one must end `.md`, so a directory-only target
#: (`docs/wiki/`, `docs/wiki/coordinator-tripwires/`) still does not match
#: and is emitted verbatim -- resolving one to an absolute path would point
#: a reader at a directory, not a page.
#: CROSS-TRANSPORT CONTRACT, not a local edit. The control-plane engine's
#: ported bash guards mirror THIS pattern by construction so the cold
#: transport (here) and the warm/resident transport emit byte-identical deny
#: text, and a cold-vs-warm parity oracle asserts over it. Widening this
#: pattern to nested anchors turned 19 of that oracle's cases red mid-flight
#: -- the widening was correct and the oracle is what caught it, but the
#: lesson is that editing this regex changes test outcomes outside this
#: repo. Re-check the engine-side copy at source before touching it; do not
#: reason about it from here.
#:
#: KNOWN DEFECT, coordinated fix or none: `resolve_wiki_citation` below emits
#: an ABSOLUTE path, so on a marketplace-shaped install -- where the plugin
#: root sits under the operator's home directory -- deny text names that
#: home directory. Not reproducible from a development clone, whose root is
#: outside the home tree; the engine side has a register lint that catches
#: it, this side has no equivalent, and both transports share the property.
#: Suppressing it on one transport alone re-opens the divergence both sides
#: just closed, so it is a coordinated change, not a local cleanup.
_WIKI_CITATION_RE = re.compile(
    r"(?:coordinator/)?docs/wiki/((?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.md)"
)


def _coordinator_dir() -> "Path":
    """The `coordinator/` directory THIS process is actually running from.
    `_message_envelope.py` itself lives at
    `<coordinator-dir>/hooks/scripts/_message_envelope.py`, so its own
    resolved parent-of-parent-of-parent IS `coordinator/` -- in BOTH install
    shapes: the source-repo layout (where `coordinator/` IS the plugin
    root) and an installed layout (where the true plugin root sits one
    level ABOVE this same `coordinator/` subdirectory; see this repo's own
    CLAUDE.md § Architecture). This function returns the `coordinator/`
    directory itself in either case, never the true plugin root of an
    installed layout -- hence the name, not `plugin_root`. Callers
    resolving `docs/wiki/` are unaffected by that offset, since `docs/wiki/`
    lives under `coordinator/` in both layouts -- but a future caller
    resolving something that genuinely lives at the true plugin root (one
    level up from here in the installed case) must not assume this
    function's return value already is that root. Renamed from the prior
    `plugin_root()` (module-private, no external call site referenced that
    name -- verified via a repo-wide grep before the rename) because the old
    name overclaimed: it collided with a genuinely different `plugin_root`
    concept already in use elsewhere in this directory (e.g.
    `assert-em-role.py`, `project-orientation.py`), and its return value is
    the plugin root only in the source-repo layout, not the installed one."""
    return Path(__file__).resolve().parent.parent.parent


def _render_resolved(path: "Path") -> str:
    """Render an already-resolved citation path for a reader.

    A resolved path is not automatically fit to send. On an INSTALLED layout
    the plugin lives under the operator's home, so the absolute form carries
    their account name into text whose audience is a dispatched subagent --
    an identity token the repo-relative literal never held. Resolution is
    what introduces it, which is why this cannot be left to the caller: the
    leak is invisible on a source-repo checkout (every dev box) and fires on
    the layout users actually run.

    Collapsed to `~/` when the path is under the home directory, native
    absolute otherwise -- a root outside home (a system-wide install) has no
    identity to hide and stays as it is.

    THE SEPARATOR IS LOAD-BEARING, NOT COSMETIC. The remainder is emitted
    POSIX-style even on Windows because `~\\...` does not expand for the
    reader (measured against the tool a denied subagent reads with: `~/`
    opens, `~\\` reports the file does not exist), while `~/` does. Building
    this with `str(Path("~") / relative)` yields the backslash form on
    Windows and trades the identity leak for an unopenable citation -- the
    same defect the resolver exists to fix, on the one platform where the
    leak matters most.

    Fails open to the absolute form: a home directory that cannot be
    determined is a rendering question, never a reason to drop a citation.
    """
    try:
        relative = path.relative_to(Path.home())
    except (ValueError, RuntimeError, OSError):
        return str(path)
    return f"~/{relative.as_posix()}" if relative.parts else "~"


def resolve_wiki_citation(text: str) -> str:
    """Rewrite every `docs/wiki/<page>.md` citation embedded in `text`
    (optionally `coordinator/`-prefixed, per `_WIKI_CITATION_RE`) into an
    absolute path anchored at `_coordinator_dir()`, preserving whatever precedes
    and follows the matched `docs/wiki/<page>.md` substring (a `#slug`
    fragment, a ` § SECTION` locator, surrounding prose) untouched. A `text`
    carrying no such citation is returned unchanged. Pure -- no I/O beyond
    the `__file__`-derived path computation `_coordinator_dir()` already does.

    Guards against double-mangling an already-resolved or foreign-anchored
    citation: `_WIKI_CITATION_RE` only anchors on the immediately-preceding
    optional `coordinator/` literal, not on the start of the whole path
    token, so a match embedded inside a longer existing absolute-path prefix
    (e.g. a citation some earlier call already resolved, or a foreign
    `/other/root/coordinator/docs/wiki/<page>.md`) would otherwise have only its
    `coordinator/docs/wiki/<page>.md` suffix replaced, leaving the unrelated
    prefix concatenated in front of the new absolute path -- a broken hybrid
    string. A match is only substituted when it starts at the beginning of
    `text` or immediately follows whitespace/an opening delimiter (never
    mid-token, as it would inside an already-resolved absolute path); any
    other match is left untouched rather than partially rewritten. No
    current call site passes an already-resolved or foreign-prefixed
    citation -- this is defensive, not a fix for a live defect."""

    def _sub(match: "re.Match[str]") -> str:
        start = match.start()
        if start > 0 and text[start - 1] not in " \t\n(['\"`":
            return match.group(0)
        return _render_resolved(_coordinator_dir() / "docs" / "wiki" / match.group(1))

    return _WIKI_CITATION_RE.sub(_sub, text)


# --------------------------------------------------------------------------
# Rendering (pure*) and emission (impure) -- attaches to the existing hook
# seam, does not create a parallel one. (*`render()` reads `__file__` via
# `resolve_wiki_citation()` -- no environment/network/process I/O.)
# --------------------------------------------------------------------------


def render(message: Message) -> str:
    """Flatten `message` to the text a real (non-measurement) channel
    carries: the prose, then the alternative re-fenced in triple backticks
    (if present), then a trailing pointer at the wiki anchor (if present).
    The anchor is resolved via `resolve_wiki_citation()` (see above) so the
    emitted pointer resolves for the reader wherever they are, not only from
    this source repo's own cwd."""
    parts = [message.prose]
    if message.alternative:
        parts.append("")
        parts.append("```\n" + message.alternative.rstrip("\n") + "\n```")
    if message.anchor:
        parts.append("")
        parts.append(f"See {resolve_wiki_citation(message.anchor)}.")
    return "\n".join(parts)


def measurement_enabled() -> bool:
    return os.environ.get(MEASURE_ENV_VAR) == "1"


def _measurement_record(message: Message) -> str:
    return json.dumps(
        {"prose": message.prose, "alternative": message.alternative, "anchor": message.anchor},
        separators=(",", ":"),
    )


def _write_measurement_record(message: Message) -> None:
    """Write the structured measurement record for `message` to fd 3, or a
    documented fallback when fd 3 is not open (the common case outside the
    harness -- fd 3 is not a channel any process is guaranteed to inherit).

    Windows-safe: this never assumes POSIX fd semantics hold. The `os.write`
    call is wrapped so a closed/unavailable fd 3 (any `OSError`, including
    the Windows "bad file descriptor" shape) degrades to the fallback
    instead of crashing the hook. The fallback is stdout: under measurement
    mode this module never also writes the flattened channel output (see
    `emit`), so stdout is free for the harness to read the SAME structured
    line from instead. Never silently swallows the record -- one of the two
    writes always happens."""
    line = _measurement_record(message)
    try:
        os.write(3, (line + "\n").encode("utf-8"))
        return
    except Exception:
        pass
    sys.stdout.write(line + "\n")


def emit(message: Message, channel: str) -> Optional[int]:
    """Impure: the one emission seam. Writes `message` to `channel` exactly
    as hooks do today -- UNLESS `COORDINATOR_HOOK_MESSAGE_MEASURE=1` is set,
    in which case it writes the structured measurement record (see
    `_write_measurement_record`) INSTEAD of the flattened channel output,
    and returns `None` without touching the real channel at all.

    `channel` is one of `CHANNEL_STOP`, `CHANNEL_ADDITIONAL_CONTEXT`,
    `CHANNEL_DENY`:

      - `CHANNEL_STOP`: writes `render(message)` to stderr, returns `2`
        (the exit code a Stop-family hook's `main()` should `sys.exit()`
        with).
      - `CHANNEL_ADDITIONAL_CONTEXT`: writes a
        `{"hookSpecificOutput": {"hookEventName": "PreToolUse",
        "additionalContext": <text>}}` envelope to stdout (compact
        separators, matching the shape already in use across this
        directory, e.g. `nudge-multiwave-workflow.py`), returns `0`.
      - `CHANNEL_DENY`: writes a `{"hookSpecificOutput": {"hookEventName":
        "PreToolUse", "permissionDecision": "deny",
        "permissionDecisionReason": <text>}}` envelope to stdout, returns
        `0`.

    Raises `ValueError` for an unrecognised `channel` -- a hook author
    routing through a channel this module does not know how to shape should
    fail loudly at authoring time, not silently emit nothing."""
    if channel not in _CHANNELS:
        raise ValueError(f"_message_envelope.emit: unknown channel {channel!r}")

    if measurement_enabled():
        _write_measurement_record(message)
        return None

    text = render(message)

    if channel == CHANNEL_STOP:
        # Review: code-reviewer -- .buffer.write bypasses Python's Windows
        # text-mode newline translation (stderr in text mode would silently
        # turn every LF into CRLF, breaking byte-fidelity with the bash
        # oracle's stderr output). Mirrors coordinator-reminder.py /
        # ue-knowledge-distrust.py; this seam is the one home for the
        # contract every CHANNEL_STOP caller inherits.
        sys.stderr.buffer.write(text.encode("utf-8"))
        return 2

    if channel == CHANNEL_ADDITIONAL_CONTEXT:
        envelope = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": text,
            }
        }
        sys.stdout.write(json.dumps(envelope, separators=(",", ":")))
        return 0

    envelope = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": text,
        }
    }
    sys.stdout.write(json.dumps(envelope, separators=(",", ":")))
    return 0
