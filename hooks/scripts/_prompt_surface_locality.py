"""Detector for OSS-payload LOCALITY defects — a private sibling-repo name
(today: `claude-klabauter`, the doctrine-authoring engine with no OSS
distribution of its own) appearing in a file that reaches the OSS
`coordinator-claude` mirror, in a position that COSTS an OSS reader
something rather than merely mentioning machinery that doesn't concern them.

Companion to `_prompt_surface_citations.py` (a DIFFERENT defect class —
citations of documents an outside reader cannot open, e.g. `docs/plans/…` or
a bare `DR-NNN` id) and to `_oss_payload.py` (single source of truth for
WHICH tracked files reach the mirror at all). This module answers a THIRD
question over that same payload set: given a file that does ship, does its
TEXT leak a name only this fleet's operators would recognize, un-substituted
by any resolution mechanism a fresh OSS install actually has?

THE HEADLINE THIS MODULE IS BUILT AGAINST (do not regress past it): a
stratified close-read of the tracked payload found attribution prose — the
actual defect — at 5-30% of sibling-repo-name hits per tree, NEVER the
majority; operative strings, resolved paths, and incidental "other" hits
make up the rest. A detector that flags the majority of hits in any tree is
wrong, not thorough, and this module's own `current_counts()` should be
sanity-checked against that ceiling before it is trusted.

THE CEILING'S SOURCE: `docs/plans/2026-07-30-oss-payload-ratchet.md:106-118`,
a stratified close-read broken out PER TREE, not averaged across sibling
names. `hooks/`, `skills/`, and `commands/` were each independently measured
at 25-30% attribution — that per-tree figure, not a cross-name average, is
the number a fresh measurement in any one of those trees is held to.

FAIL-OPEN POSTURE, mirroring `_prompt_surface_citations.py`: every ratified
classification input (`_oss_operative_strings.py`'s table/shape-rule/MCP-
prefix data, `STRUCTURAL_MARKERS`) is loaded via `importlib` and degrades to
an EMPTY result on any load failure, never a raised exception — a hiccup in
one of those inputs narrows this detector's carve-outs (more false positives
surface) rather than bricking the PreToolUse hook built on it. A Python file
that fails to `ast.parse` degrades the SAME way for that one file only: the
sibling-name/attribution scan is skipped for it (the position lens has
nothing to stand on), while the drive-path scan — which does not depend on
AST position — still runs, subject to the escape-sequence discriminator
below.

DRIVE-PATH SCAN IS POSITION-INDEPENDENT FOR ATTRIBUTION PURPOSES, BUT NOT
CONTENT-BLIND, FOR `.py` PATHS: inside a non-raw Python string-literal
token, a lone separator backslash is an escape character, not a path
separator — genuine Python source hardcoding a drive path must write the
separator doubled, use a raw-prefixed string, or use a forward slash
instead. A `WINDOWS_DRIVE_PATH` match inside a non-raw `.py` string
literal, whose matched separator is a lone, undoubled backslash, is read
as an escape sequence and skipped — every other case (comments, raw
strings, doubled-backslash literals, forward slashes, non-`.py` files)
still flags. See `_python_string_literal_spans` and its use at the match
site in `iter_violations`.

THE COVERAGE ASYMMETRY this module inherits from `_oss_payload.py`: a
write-time guard built on `is_in_scope()` only ever sees files LOCAL to this
clone (`hooks/`, `skills/`, `agents/`, `commands/`, `snippets/`, …) because a
write to the engine repo's own `bin`/`lib` payload happens in ANOTHER
session's working tree. `current_counts()`, by contrast, enumerates the
FULL payload via `_oss_payload.payload_files()` (local + engine, when the
engine repo is resolvable) — the same local/engine split, restated here
because an unstated asymmetry reads as coverage a mechanism does not have.

THE SIBLING-NAME PATTERN ITSELF IS PAYLOAD-SCOPED: the engine leg of
`current_counts()` scans with a pattern built ONLY from record entries with
`is_engine_sibling is True` (`_ENGINE_SIBLING_NAME_TOKEN`), never the full
`SIBLING_REPO_RECORD` the local leg uses — a name outside that engine subset
is unreachable from a tree this repo has no standing commit grant to fix, so
counting it there is a tripwire nobody holding this branch can clear;
`is_in_scope()`/the write-time guard is unaffected, since it never touches
engine files in the first place.

THREE CARVE-OUTS, each toggled off/on and diffed against the corpus by the
carve-out narrowness tests in this module's own companion test suite
(three `test_*_carveout_is_narrow` tests, one per carve-out below) rather
than merely asserted narrow:

  1. RATIFIED OPERATIVE LITERALS — `_oss_operative_strings.py`. Most of its
     classes are DERIVABLE rather than curated (MCP tool-name prefixes from
     `coordinator/mcp-topology.yaml`; the env-var/registry-key SHAPE RULE;
     the minted-stable-artifact-id SHAPE RULE, covering the fleet's
     `pln-`/`dlv-`/`hnd-`/`cmp-` spec-backlink citation form explicitly,
     where the older `docs/plans/<slug>.md` path form only ever cleared
     incidentally, on the dot its extension supplies), leaving one
     genuinely irreducible literal residue. Both shape rules reach this
     detector through the SINGLE `is_identifier_shape_operative` call site
     below — a new operative shape is taught to that ratified module, never
     grown as a second classification mechanism here. See that module's own
     docstring and ENTRY CRITERION.
  2. REGISTERED SNIPPET `<!-- BEGIN … -->` / `<!-- END … -->` FENCES —
     `STRUCTURAL_MARKERS`, loaded from the SAME ratified source
     `_prompt_surface_citations.py` already uses
     (`test_prompt_surfaces_carry_no_provenance.py`), never re-derived.
     Synced canonical snippet content is not the citing file's prose and the
     citing file cannot fix it, so the ENTIRE fenced span is exempt from
     every violation kind this module raises, not merely the marker line.
  3. POSITION LENS for `hooks/*.py` — `ast`-established, never a regex over
     source text. A `.py` docstring or `tokenize`-detected comment is
     ATTRIBUTION (counts); every other position — string literal, dict key,
     identifier — is LOAD-BEARING (does not count), independent of what the
     string's content happens to be. This is a deliberate simplification:
     the position decides, the string's own content does not get a second,
     content-based classification pass inside it.

DO NOT use backtick-delimited inline code spans as a signal in either
direction for this detector — unlike the sibling citation detector's
narrow, deliberately-scoped `_literal_sentinel_spans` exemption, a single
backtick span here carries no reliable signal at all: this corpus has both a
backticked Windows-path illustration that IS a real drive-path defect and a
BEGIN/END-fenced bare-prose block that is entirely sanctioned despite
carrying no backticks whatsoever. Treat backtick-delimited text exactly like
any other prose for both the sibling-name and drive-path checks; only
`STRUCTURAL_MARKERS` fences and the `ast`/`tokenize` position lens make a
real distinction.
"""

from __future__ import annotations

import importlib.util
import re
import tokenize
import io
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[3]
_HOOKS_SCRIPTS_DIR = REPO_ROOT / "coordinator" / "hooks" / "scripts"
_TESTS_DIR = REPO_ROOT / "coordinator" / "tests"

import sys

if str(_HOOKS_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_SCRIPTS_DIR))

import _oss_payload  # noqa: E402


def _load_module(path: Path, name: str):
    """Best-effort `importlib` load of a sibling module by file path. Returns
    `None` on any failure — see module docstring's fail-open contract."""
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        return module
    except Exception:
        return None


def _load_operative_strings():
    return _load_module(
        _HOOKS_SCRIPTS_DIR / "_oss_operative_strings.py",
        "_prompt_surface_locality_operative_strings",
    )


def _load_structural_markers() -> tuple:
    module = _load_module(
        _TESTS_DIR / "test_prompt_surfaces_carry_no_provenance.py",
        "_prompt_surface_locality_structural_markers",
    )
    if module is None:
        return ()
    return tuple(getattr(module, "STRUCTURAL_MARKERS", ()))


#: Every file `importlib`-loaded to classify a violation — the comparability
#: surface for any future ratchet built on this module (mirrors
#: `_DETECTOR_SEMANTICS_PATHS` in `test_prompt_surfaces_cite_resolvably.py`).
CARVE_OUT_SOURCES: "tuple[Path, ...]" = (
    _HOOKS_SCRIPTS_DIR / "_oss_operative_strings.py",
    REPO_ROOT / "coordinator" / "mcp-topology.yaml",
    _TESTS_DIR / "test_prompt_surfaces_carry_no_provenance.py",
)

_operative_strings_module = _load_operative_strings()


def _normalize_sibling_record(raw) -> dict:
    """Normalize whatever the operative-strings module exposes into the
    one name-keyed record shape `name -> {is_engine_sibling, oss_reachable,
    short_forms, aliases, case_sensitive}`.

    Two input shapes are accepted, one normalizer:

    - A record mapping already in the target shape is consumed directly,
      unchanged.
    - A legacy plain tuple-of-names is normalized per entry to
      `{is_engine_sibling: True, oss_reachable: False, short_forms:
      (<trailing part> if the name has more than one `-`/`_`-delimited
      part else ()), aliases: (), case_sensitive: False}` — reproducing
      exactly the old derive-from-trailing-part, case-insensitive
      behavior, so no name in the legacy tuple changes matching behavior
      by passing through this normalizer."""
    if isinstance(raw, dict):
        return raw
    record: dict = {}
    for name in raw or ():
        if not isinstance(name, str) or not name:
            continue
        norm = name.replace("-", "_")
        parts = norm.split("_")
        short_forms = (parts[-1],) if len(parts) > 1 else ()
        record[name] = {
            "is_engine_sibling": True,
            "oss_reachable": False,
            "short_forms": short_forms,
            "aliases": (),
            "case_sensitive": False,
        }
    return record


_raw_sibling_source = (
    getattr(_operative_strings_module, "SIBLING_REPO_RECORD", None)
    if _operative_strings_module
    else None
)
if _raw_sibling_source is None:
    _raw_sibling_source = (
        getattr(_operative_strings_module, "SIBLING_REPO_NAMES", ())
        if _operative_strings_module
        else ()
    )

#: Resolved once at import time. Empty/no-op on load failure — see the
#: module docstring's fail-open contract. One name-keyed record; see
#: `_normalize_sibling_record`.
SIBLING_REPO_RECORD: dict = _normalize_sibling_record(_raw_sibling_source)

#: Derived VIEW over `SIBLING_REPO_RECORD` -- every name whose record
#: declares `oss_reachable is False`. Kept for callers (and the
#: identifier-shape carve-out below) that only need the bare name set.
SIBLING_REPO_NAMES: tuple = tuple(
    name for name, data in SIBLING_REPO_RECORD.items() if data.get("oss_reachable") is False
)
IRREDUCIBLE_LITERALS: tuple = (
    getattr(_operative_strings_module, "IRREDUCIBLE_LITERALS", ()) if _operative_strings_module else ()
)
MCP_TOOL_PREFIXES: frozenset = (
    getattr(_operative_strings_module, "MCP_TOOL_PREFIXES", frozenset())
    if _operative_strings_module
    else frozenset()
)
MCP_TOOL_PREFIX_SPAN = (
    getattr(_operative_strings_module, "MCP_TOOL_PREFIX_SPAN", None) if _operative_strings_module else None
)
_is_identifier_shape_operative = (
    getattr(_operative_strings_module, "is_identifier_shape_operative", None)
    if _operative_strings_module
    else None
)
_strip_trailing_sentence_period = (
    # Degrading to None here means "don't strip" -- a token keeps its
    # trailing period, fails the carve-out match, and the detector flags
    # it. That's the fail-safe direction: over-flagging, never a silently
    # widened exemption.
    getattr(_operative_strings_module, "_strip_trailing_sentence_period", None)
    if _operative_strings_module
    else None
)

STRUCTURAL_MARKERS: tuple = _load_structural_markers()


@dataclass(frozen=True)
class Violation:
    """Mirrors `_prompt_surface_citations.Violation`'s shape, plus `path` —
    this detector's own consumers (`current_counts()`, a locality guard,
    a locality ratchet test) aggregate across many files at once, so each
    violation carries which file it came from rather than relying on an
    external dict key."""

    path: str
    line: int
    kind: str
    excerpt: str
    fingerprint: str = ""


# ---------------------------------------------------------------------------
# Scope
# ---------------------------------------------------------------------------


def is_in_scope(path) -> bool:
    """True if `path` is one of THIS clone's own tracked OSS-payload files
    (`_oss_payload.is_payload_path`) with a suffix this detector knows how
    to classify (`.py`, `.md`).

    Deliberately LOCAL-only, same as `_oss_payload.is_payload_path` itself —
    a write-time guard built on this can only ever observe a write in THIS
    repo's working tree; the engine third of the payload (`bin`, `lib`,
    resolved against `claude-klabauter`) is out of reach for a guard by
    construction. `current_counts()` below reaches further, via
    `_oss_payload.payload_files()`, because a ratchet test (unlike a guard)
    is not scoped to "what did this one write touch"."""
    candidate = Path(path)
    if candidate.suffix not in (".py", ".md"):
        return False
    return _oss_payload.is_payload_path(candidate)


# ---------------------------------------------------------------------------
# Violation patterns
# ---------------------------------------------------------------------------

#: A drive-rooted Windows path — a single drive letter, a colon, then either
#: separator, followed by the rest of the path. The
#: negative lookbehind is load-bearing, not decorative: a naive
#: `[A-Za-z]:[\\/]` also matches the `s:` in `https://` (and `p:` in
#: `ftp://`, etc.) because every URL-scheme letter immediately preceding the
#: `://` is itself preceded by ANOTHER scheme letter — `(?<![A-Za-z0-9_])`
#: requires the candidate drive letter to be its own token, which a scheme
#: letter never is.
WINDOWS_DRIVE_PATH = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/]")

#: Contiguous identifier-shaped run of characters immediately touching a
#: match — used to recover the FULL token (an env-var name, or a dotted
#: registry key) around a bare substring hit before classifying it,
#: exactly as `_prompt_surface_citations._PRECEDING_RUN` recovers a run for
#: its own placeholder check. Stops at anything that is not itself part of
#: an identifier/registry-key/env-var shape (whitespace, punctuation,
#: apostrophe) — a possessive in prose correctly yields the bare name, with
#: the trailing apostrophe-s excluded.
_IDENT_CHAR = re.compile(r"[A-Za-z0-9_.\-]")


def _token_span(line: str, start: int, end: int) -> tuple:
    """The full identifier-shaped token span containing `[start, end)`,
    extended in both directions over `_IDENT_CHAR` runs. Companion to
    `_surrounding_token` (which returns the text of this same span) --
    kept separate because a caller that needs to inspect the characters
    FLANKING the span (`_is_angle_bracket_placeholder` below) needs the
    boundary indices, not just the substring."""
    s = start
    while s > 0 and _IDENT_CHAR.match(line[s - 1]):
        s -= 1
    e = end
    while e < len(line) and _IDENT_CHAR.match(line[e]):
        e += 1
    return s, e


def _surrounding_token(line: str, start: int, end: int) -> str:
    s, e = _token_span(line, start, end)
    return line[s:e]


def _is_angle_bracket_placeholder(line: str, start: int, end: int) -> bool:
    """True if the sibling-name match at `[start, end)` sits inside an
    angle-bracket-delimited doc placeholder -- e.g. a sibling-repo-root
    token spelled `<...-root>`, not a bare mention or a real path. This
    repo already documents that exact convention (substitute your own
    resolved path, via the machine-local registry or an env override)
    right alongside the placeholder in prose -- an OSS reader loses
    nothing a bare attribution mention would cost them, which is the
    actual defect this ratchet exists to catch. Symmetric with
    `_prompt_surface_citations._preceded_by_placeholder`'s own reuse of
    `<`/`>` as members of `_PLACEHOLDER_CHARS`.

    Requires BOTH flanks present -- a stray `<` or `>` elsewhere on the
    line, with nothing on the other side of the token, must not
    manufacture a false exemption."""
    s, e = _token_span(line, start, end)
    return s > 0 and e < len(line) and line[s - 1] == "<" and line[e] == ">"


def _sibling_name_pattern(record: "dict | None" = None) -> "re.Pattern | None":
    """Compiled alternation over every known sibling repo name's full and
    short forms, in both hyphenated and underscored spellings, plus each
    name's declared `short_forms`/`aliases`. `None` when the record is
    empty/unloadable (fail-open: the sibling-name scan is skipped
    entirely, never manufactured from a hardcoded guess).

    Reads per-name data off `record` (`SIBLING_REPO_RECORD` by default) —
    a name contributes a short-form arm ONLY where one is declared for it,
    never a bare derived trailing-part. Case sensitivity is compiled
    per-arm from each record entry's `case_sensitive` field via an inline
    `(?i:...)` group, not one module-wide `re.IGNORECASE`."""
    if record is None:
        record = SIBLING_REPO_RECORD
    if not record:
        return None
    alternatives = []
    for name, data in record.items():
        if not isinstance(name, str) or not name:
            continue
        norm = name.replace("-", "_")
        forms = {name, norm}
        forms.update(f for f in data.get("short_forms", ()) if f)
        forms.update(f for f in data.get("aliases", ()) if f)
        case_sensitive = bool(data.get("case_sensitive", False))
        for form in forms:
            escaped = re.escape(form)
            wrapped = escaped if case_sensitive else f"(?i:{escaped})"
            # Review: coordinator:code-reviewer -- sort by the underlying
            # literal's length, not the wrapped alternative's, so a
            # case-insensitive form's `(?i:...)` overhead can't make a
            # shorter literal outrank a longer case-sensitive one and
            # misorder leftmost-alternative-wins precedence.
            alternatives.append((len(form), wrapped))
    if not alternatives:
        return None
    pattern = "|".join(
        wrapped for _length, wrapped in sorted(set(alternatives), key=lambda pair: pair[0], reverse=True)
    )
    return re.compile(rf"\b(?:{pattern})\b")


_SIBLING_NAME_TOKEN = _sibling_name_pattern()

#: Engine-leg pattern, built ONLY from `is_engine_sibling is True` record
#: entries — narrower than `_SIBLING_NAME_TOKEN`, which is compiled from the
#: full record. `_sibling_name_pattern` already fails open to `None` on an
#: empty record, so an empty/unloadable `SIBLING_REPO_RECORD` degrades this
#: the same way as the local pattern. See module docstring's "THE
#: SIBLING-NAME PATTERN ITSELF IS PAYLOAD-SCOPED" note.
_ENGINE_SIBLING_RECORD: dict = {
    name: data
    for name, data in SIBLING_REPO_RECORD.items()
    if data.get("is_engine_sibling") is True
}
_ENGINE_SIBLING_NAME_TOKEN = _sibling_name_pattern(_ENGINE_SIBLING_RECORD)


def _is_irreducible_literal(token: str, path_str: str, line_no: int) -> bool:
    """True only at the exact `(file, line)` site an `IRREDUCIBLE_LITERALS`
    entry names — never for the same literal recurring elsewhere, including
    elsewhere in the same file. See `_oss_operative_strings.py`'s ENTRY
    CRITERION and per-entry scoping note.

    Strips a trailing sentence-period like `is_identifier_shape_operative`
    does, for the same reason (a sentence-final mention is not a different
    token) — safe here specifically because the match is additionally
    gated on the exact `(file, line)` site, so stripping can only affect
    whether *that* one site matches, never widen the carve-out to any other
    occurrence of the literal."""
    if _strip_trailing_sentence_period is not None:
        token = _strip_trailing_sentence_period(token)
    normalized = token.lower().replace("-", "_")
    for literal, entry_file, entry_line, _reason in IRREDUCIBLE_LITERALS:
        if normalized != literal.lower().replace("-", "_"):
            continue
        if path_str == entry_file and line_no == entry_line:
            return True
    return False


def _inside_mcp_prefix_span(line: str, index: int) -> bool:
    """True if `index` falls inside an `mcp__<server>__` prefix match, or
    inside the identifier-shaped tool-name suffix immediately following it —
    the server name is the prefix's OWN content, and a sibling-name hit
    landing inside the tool-name suffix that follows `__` is still part of
    the same operative token, not a separate prose mention. The suffix
    boundary is the actual identifier span (recovered the same way
    `_surrounding_token` recovers one), not a fixed-width guess — a fixed
    window either cuts off a long tool name or reaches past it into
    unrelated prose on the same line."""
    if MCP_TOOL_PREFIX_SPAN is None:
        return False
    for m in MCP_TOOL_PREFIX_SPAN.finditer(line):
        if m.start() > index:
            continue
        suffix_end = m.end()
        while suffix_end < len(line) and _IDENT_CHAR.match(line[suffix_end]):
            suffix_end += 1
        if index < suffix_end:
            return True
    return False


_HTML_COMMENT_LINE = re.compile(r"^\s*<!--(.*)-->\s*$")
_BEGIN_WORD = re.compile(r"^\s*BEGIN\b")
_END_WORD = re.compile(r"^\s*END\b")

#: The `coordinator:fleet-only:start`/`:end` marker pair is a second,
#: independent fence vocabulary alongside `BEGIN`/`END` — it is already in
#: `STRUCTURAL_MARKERS` (so it survives the publish-side provenance ban) but
#: its body never satisfies `_BEGIN_WORD`/`_END_WORD`, which only recognize
#: the literal words "BEGIN"/"END". A `coordinator:fleet-only` span is
#: stripped wholesale by the publish transform (`strip_fleet_only_fences`)
#: and never reaches an OSS reader, so it earns the same scan-skip treatment
#: as a `BEGIN`/`END` fence -- counting content inside it is a false
#: positive against this detector's own "does an OSS reader see it" test.
_FLEET_ONLY_BEGIN_WORD = re.compile(r"^\s*coordinator:fleet-only:start\b")
_FLEET_ONLY_END_WORD = re.compile(r"^\s*coordinator:fleet-only:end\b")


def _matches_any(patterns: Iterable, text: str) -> bool:
    return any(p.search(text) for p in patterns)


def _structural_comment_body(line: str) -> "str | None":
    """The body text of an HTML comment occupying the WHOLE line (a fence
    marker is always its own line), or `None` if the line isn't shaped like
    one. Mirrors `_prompt_surface_citations._HTML_COMMENT`'s body extraction
    rather than re-deriving a second regex for the same shape."""
    m = _HTML_COMMENT_LINE.match(line)
    return m.group(1).strip() if m else None


def _is_snippet_begin(line: str) -> bool:
    body = _structural_comment_body(line)
    if body is None:
        return False
    if _FLEET_ONLY_BEGIN_WORD.search(body):
        return True
    if not STRUCTURAL_MARKERS:
        return False
    return _matches_any(STRUCTURAL_MARKERS, body) and bool(_BEGIN_WORD.search(body))


def _is_snippet_end(line: str) -> bool:
    body = _structural_comment_body(line)
    if body is None:
        return False
    if _FLEET_ONLY_END_WORD.search(body):
        return True
    if not STRUCTURAL_MARKERS:
        return False
    return _matches_any(STRUCTURAL_MARKERS, body) and bool(_END_WORD.search(body))


def _excerpt(line: str) -> str:
    return " ".join(line.split())[:90]


# ---------------------------------------------------------------------------
# Position lens for .py files — ast + tokenize, never a text regex
# ---------------------------------------------------------------------------

_DOCSTRING_OWNER_TYPES: tuple = ()


def _docstring_owner_types():
    import ast

    return (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


def _python_attribution_lines(text: str) -> "frozenset[int] | None":
    """Every line number in `text` that is ATTRIBUTION position — a module/
    class/function docstring, or a `#` comment — per the position lens: only
    these two positions count toward a sibling-name-attribution violation in
    a `.py` file; every other position (ordinary string literal, identifier)
    is LOAD-BEARING regardless of content.

    Returns `None` on a `SyntaxError` (the file does not parse as Python) —
    the caller skips the sibling-name scan entirely for that file rather
    than falling back to a text-regex guess, which would silently reintroduce
    exactly the false-positive class this lens exists to avoid."""
    import ast

    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None

    lines: set = set()
    for node in ast.walk(tree):
        if not isinstance(node, _docstring_owner_types()):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            start = first.lineno
            end = getattr(first, "end_lineno", start)
            lines.update(range(start, end + 1))

    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                lines.add(tok.start[0])
    except (tokenize.TokenError, IndentationError, SyntaxError):
        # Comment detection narrows on a tokenize failure (e.g. a file with
        # inconsistent tabs/spaces past the point ast.parse tolerated) --
        # docstring-derived lines above are still valid and kept.
        pass

    return frozenset(lines)


def _python_string_literal_spans(text: str) -> "dict[int, list] | None":
    """Per-line column spans covered by a Python string-literal TOKEN
    (`tokenize.STRING`, plus f-string parts on interpreters that emit them
    separately), each tagged with whether that token is raw-prefixed.

    Scoped narrowly to feed the drive-path escape-sequence discriminator: a
    lone backslash immediately preceding a drive letter's separator, inside
    one of these non-raw spans, is a Python escape character in the SOURCE
    TEXT, not a literal path separator — see module docstring. A raw-prefixed
    token (`r"..."`, `rb"..."`, any prefix containing `r`/`R`) is excluded
    from that reading because Python does not treat backslash as an escape
    lead-in there, so a single backslash inside a raw string genuinely means
    one backslash character, i.e. a real path separator.

    Multi-line tokens are split across their covered lines: the first line
    from the token's start column to end-of-line, interior lines covered in
    full, the last line from column 0 to the token's end column — mirroring
    how a match on any of those lines could legitimately fall inside the
    token's span.

    Fails open (`None`) on ANY `tokenize` failure, matching this module's
    stated posture: the discriminator then contributes nothing and the
    drive-path scan behaves exactly as it did before this carve-out
    existed."""
    spans: dict = {}
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return None
    except Exception:
        return None

    fstring_start_type = getattr(tokenize, "FSTRING_START", None)
    fstring_part_types = set()
    for attr in ("FSTRING_MIDDLE", "FSTRING_END"):
        tok_type = getattr(tokenize, attr, None)
        if tok_type is not None:
            fstring_part_types.add(tok_type)

    string_types = {tokenize.STRING} | fstring_part_types
    if fstring_start_type is not None:
        string_types.add(fstring_start_type)

    # `FSTRING_MIDDLE`/`FSTRING_END` token text carries no prefix or quote
    # characters to recover rawness from (it is the literal content only) --
    # rawness for those parts must be carried forward from the `FSTRING_START`
    # token of the SAME logical f-string, established once per string rather
    # than recomputed per-token.
    current_fstring_is_raw = False

    for tok in tokens:
        if tok.type not in string_types:
            continue
        if tok.type == fstring_start_type:
            prefix = tok.string.rstrip("'\"")
            current_fstring_is_raw = any(c in ("r", "R") for c in prefix)
            is_raw = current_fstring_is_raw
        elif tok.type in fstring_part_types:
            is_raw = current_fstring_is_raw
        else:
            # Recover the literal's prefix (r, rb, Rb, f, ...) from the raw
            # token text -- only characters preceding the first quote can be
            # a string prefix. Correct for ordinary `STRING` tokens, which
            # always carry their own prefix and quote characters.
            prefix = ""
            for ch in tok.string:
                if ch in ("'", '"'):
                    break
                prefix += ch
            is_raw = any(c in ("r", "R") for c in prefix)

        start_line, start_col = tok.start
        end_line, end_col = tok.end
        if start_line == end_line:
            spans.setdefault(start_line, []).append((start_col, end_col, is_raw))
            continue
        spans.setdefault(start_line, []).append((start_col, None, is_raw))
        for mid_line in range(start_line + 1, end_line):
            spans.setdefault(mid_line, []).append((0, None, is_raw))
        spans.setdefault(end_line, []).append((0, end_col, is_raw))

    return spans


def _is_escaped_drive_path_match(
    line: str, match_start: int, match_end: int, literal_spans: "list | None"
) -> bool:
    """True if a `WINDOWS_DRIVE_PATH` match at `[match_start, match_end)` on
    `line` should be read as a Python escape sequence rather than a real
    path separator -- i.e. it falls inside a non-raw string-literal span AND
    its matched separator character is a lone backslash not immediately
    followed by another backslash (a doubled backslash IS a real single
    backslash character in the literal's value, so it stays flagged same as
    a forward slash would).

    Single-character lookahead only -- an odd-length (3+) backslash run at
    the match boundary is not distinguished from a doubled one and is
    deliberately out of scope."""
    if not literal_spans:
        return False
    separator = line[match_end - 1]
    if separator != "\\":
        return False
    if match_end < len(line) and line[match_end] == "\\":
        return False
    for span_start, span_end, is_raw in literal_spans:
        if is_raw:
            continue
        effective_end = span_end if span_end is not None else len(line)
        if span_start <= match_start and match_end <= effective_end:
            return True
    return False


# ---------------------------------------------------------------------------
# Position lens for .md files — fenced code blocks, never a snippet fence
# ---------------------------------------------------------------------------

#: Opening fence delimiter: optional leading indent, then 3+ backtick or
#: tilde characters, optionally followed by an info string (` ```bash `,
#: ` ~~~text `, etc.) — the info string's own content is not inspected.
_MD_FENCE_OPEN = re.compile(r"^[ \t]{0,3}([`~]{3,})")


def _markdown_fence_lines(text: str) -> frozenset:
    """Every line number inside a fenced code block (``` or ~~~, 3+
    markers, optionally indented up to 3 spaces per common Markdown fence
    convention) — LOAD-BEARING for the sibling-name check, exactly like a
    `.py` string literal/identifier position, never ATTRIBUTION. Deliberately
    narrower than the `BEGIN`/`END`/`coordinator:fleet-only` snippet-fence
    vocabulary (`_is_snippet_begin`/`_is_snippet_end`): this reclassifies
    ONLY the sibling-name check's position for the span it covers, while a
    snippet fence skips every violation kind including the drive-path check.
    The two mechanisms are independent and neither one substitutes for the
    other's job.

    Deliberately does NOT handle: fences opened inside an already-fenced
    block (nested/lazy continuation per CommonMark's own edge cases), a
    closing fence whose marker run is shorter than to the opener but still
    followed by trailing content beyond whitespace, or an unbalanced fence
    (never closed) reopening semantics — an unclosed fence simply covers the
    rest of the file, the same fail-safe direction the snippet-fence
    vocabulary already takes elsewhere in this module.
    """
    lines = text.split("\n")
    fence_lines: set = set()
    in_fence = False
    fence_char = ""
    fence_len = 0
    close_re = None
    for line_no, line in enumerate(lines, start=1):
        if not in_fence:
            m = _MD_FENCE_OPEN.match(line)
            if m:
                fence_char = m.group(1)[0]
                fence_len = len(m.group(1))
                close_re = re.compile(
                    rf"^[ \t]{{0,3}}{re.escape(fence_char)}{{{fence_len},}}[ \t]*$"
                )
                in_fence = True
                fence_lines.add(line_no)
            continue
        fence_lines.add(line_no)
        if close_re.match(line):
            in_fence = False
    return frozenset(fence_lines)


# ---------------------------------------------------------------------------
# Violation detection
# ---------------------------------------------------------------------------


def iter_violations(text: str, *, path=None, sibling_pattern=_SIBLING_NAME_TOKEN) -> list:
    """Every locality violation in `text`, in line order.

    `path` is optional but load-bearing for classification: when it names a
    `.py` file, the sibling-name/attribution check is gated by the `ast`/
    `tokenize` position lens (`_python_attribution_lines`); for any other
    path (or `path=None`), the sibling-name check runs over every
    non-fenced line, matching the markdown/prose trees this module also
    covers. The drive-path check is position-independent for attribution
    purposes and runs everywhere except inside a structural snippet fence —
    but for a `.py` path it is not content-blind: a match whose separator
    is a lone, undoubled backslash inside a non-raw string-literal token is
    read as a Python escape sequence, not a path separator, and skipped
    (`_python_string_literal_spans`).

    `sibling_pattern` is optional, defaulting to the module-level
    `_SIBLING_NAME_TOKEN` (every existing caller unchanged). A caller
    scanning the engine leg of the payload passes `_ENGINE_SIBLING_NAME_TOKEN`
    instead — the narrower, `is_engine_sibling`-only pattern — so a name
    pinned reachable only on the local leg does not flag there. `None`
    (fail-open, e.g. an empty/unloadable record) skips the sibling-name scan
    entirely, same as today.
    """
    path_str = ""
    is_python = False
    if path is not None:
        p = Path(path)
        is_python = p.suffix == ".py"
        try:
            path_str = p.resolve().relative_to(REPO_ROOT).as_posix()
        except Exception:
            path_str = str(p)

    attribution_lines = _python_attribution_lines(text) if is_python else None
    python_scan_disabled = is_python and attribution_lines is None
    literal_spans = _python_string_literal_spans(text) if is_python else None
    markdown_fence_lines = _markdown_fence_lines(text) if not is_python else None

    lines = text.split("\n")
    violations: list = []
    # An unclosed fence (BEGIN/END or coordinator:fleet-only) skips every
    # remaining line to EOF rather than reopening the scan at any point --
    # same contract as the pre-existing BEGIN/END vocabulary. This detector
    # does not replicate the publish-side unbalanced/nested-fence failure;
    # an unbalanced fleet-only fence still fails loud there.
    in_snippet_fence = False

    for line_no, line in enumerate(lines, start=1):
        if not in_snippet_fence and _is_snippet_begin(line):
            in_snippet_fence = True
            continue
        if in_snippet_fence:
            if _is_snippet_end(line):
                in_snippet_fence = False
            continue

        fingerprint = " ".join(line.split())

        for m in WINDOWS_DRIVE_PATH.finditer(line):
            if is_python and _is_escaped_drive_path_match(
                line, m.start(), m.end(), literal_spans.get(line_no) if literal_spans else None
            ):
                continue
            violations.append(
                Violation(path_str, line_no, "drive-rooted windows path", _excerpt(line), fingerprint)
            )

        if sibling_pattern is None:
            continue
        if python_scan_disabled:
            continue
        if is_python and line_no not in attribution_lines:
            continue
        if not is_python and markdown_fence_lines and line_no in markdown_fence_lines:
            continue

        for m in sibling_pattern.finditer(line):
            if _inside_mcp_prefix_span(line, m.start()):
                continue
            if _is_angle_bracket_placeholder(line, m.start(), m.end()):
                continue
            token_start, token_end = _token_span(line, m.start(), m.end())
            # A trailing sentence-period extends the token span past the
            # match (identifier-shaped `.` recovery), same reason
            # `_strip_trailing_sentence_period` exists -- a sentence-final
            # mention is still the WHOLE token, not a fragment of a longer
            # local identifier, so it is not disqualified here.
            effective_token_end = token_end
            if token_end == m.end() + 1 and line[m.end()] == ".":
                effective_token_end = m.end()
            if (token_start, effective_token_end) != (m.start(), m.end()):
                # The matched sibling-name substring is only a fragment of a
                # longer `-`/`_`-joined LOCAL identifier (e.g. a script named
                # `check-claude-klabauter-doctor-sentinel.sh`) rather than the whole
                # surrounding token -- not a pointer at the sibling repo.
                continue
            token = _surrounding_token(line, m.start(), m.end())
            if _is_irreducible_literal(token, path_str, line_no):
                continue
            if _is_identifier_shape_operative is not None and _is_identifier_shape_operative(
                token, SIBLING_REPO_NAMES
            ):
                continue
            violations.append(
                Violation(
                    path_str,
                    line_no,
                    "private sibling-repo-name attribution",
                    _excerpt(line),
                    fingerprint,
                )
            )

    return violations


def _violation_key(v: Violation) -> tuple:
    """Identity for the before/after multiset diff — kind + full normalized
    line, deliberately not line number, for the same line-shift-safety
    reason `_prompt_surface_citations._violation_key` gives."""
    return (v.kind, v.fingerprint)


def _sibling_scan_disabled(text: str, path) -> bool:
    """Whether `iter_violations` will skip the sibling-name scan for `text` —
    true only for a `.py` path whose text does not `ast.parse`."""
    if path is None or Path(path).suffix != ".py":
        return False
    return _python_attribution_lines(text) is None


def new_violations(before: str, after: str, *, path=None) -> list:
    """Violations present in `after` that were not already present in
    `before`, as a multiset difference — same contract as
    `_prompt_surface_citations.new_violations`, so a hard-deny guard built on
    this is safe against the existing corpus's legacy violations: a
    violation sitting untouched elsewhere in the file contributes equally to
    both sides of the diff and never surfaces here.

    Negative spec: when only ONE side of a `.py` diff parses, the two sides
    are not comparable for the sibling-name class — the unparseable side
    scans zero of them by design, so every legacy violation on the parseable
    side would read as new. That asymmetry makes a syntax-error repair
    undeniable-by-construction (the very write that restores parseability is
    the one denied), so the sibling-name class fails OPEN across it. The
    drive-path class is position-independent and stays comparable.

    RESIDUAL GAP this fail-open leaves OPEN, not merely the case it closes:
    when `before` fails to parse and `after` does (the repair direction),
    the sibling-name class is skipped entirely rather than falling back to
    any comparison — so a write that BOTH fixes the syntax error AND
    introduces a genuinely new sibling-repo-name attribution in the same
    edit is caught by neither guard. `guard-oss-payload-locality` fails
    open by design here (this docstring's own contract), and
    `guard-python-syntax-on-write` has nothing to deny once the after-text
    compiles. The OPPOSITE direction (before parses, after doesn't) is
    closed only as a composition property of the two guards under
    `preuse-write-dispatch.py`'s first-deny-wins ordering: that write is
    denied outright by `guard-python-syntax-on-write` on the syntax defect
    before this guard's own posture ever matters. Named, narrow trade-off
    (the alternative is an unrepairable file) — not a defect to fix here."""
    if _sibling_scan_disabled(before, path) != _sibling_scan_disabled(after, path):
        before_drive = Counter(
            _violation_key(v)
            for v in iter_violations(before, path=path)
            if v.kind == "drive-rooted windows path"
        )
        after_drive = [
            v
            for v in iter_violations(after, path=path)
            if v.kind == "drive-rooted windows path"
        ]
        delta = Counter(_violation_key(v) for v in after_drive) - before_drive
        seen: Counter = Counter()
        out: list = []
        for v in after_drive:
            key = _violation_key(v)
            if seen[key] < delta.get(key, 0):
                out.append(v)
                seen[key] += 1
        return out
    before_counts = Counter(_violation_key(v) for v in iter_violations(before, path=path))
    after_violations = iter_violations(after, path=path)
    after_counts = Counter(_violation_key(v) for v in after_violations)
    delta = after_counts - before_counts
    if not delta:
        return []
    result: list = []
    seen: Counter = Counter()
    for v in after_violations:
        key = _violation_key(v)
        if seen[key] < delta.get(key, 0):
            result.append(v)
            seen[key] += 1
    return result


# ---------------------------------------------------------------------------
# Corpus aggregation
# ---------------------------------------------------------------------------


def current_counts() -> dict:
    """repo-relative path -> violation count, over the FULL OSS payload
    (`_oss_payload.payload_files()`: local files resolved against this
    clone, plus engine files resolved against the `claude-klabauter` checkout
    when it is resolvable). See module docstring's coverage-asymmetry note —
    this reaches further than `is_in_scope()`/a write-time guard ever could,
    because a ratchet test (unlike a guard) is not scoped to one write."""
    counts: dict = {}

    local_and_wiki = (
        _oss_payload.local_payload_files() + _oss_payload.toplevel_wiki_payload_files()
    )
    for rel in local_and_wiki:
        if rel.suffix not in (".py", ".md"):
            continue
        full = REPO_ROOT / rel
        try:
            text = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        n = len(iter_violations(text, path=full))
        if n:
            counts[rel.as_posix()] = n

    available, _reason = _oss_payload.engine_repo_available()
    if available:
        from _engine_root import resolve_claude_klabauter_root

        engine_root = Path(resolve_claude_klabauter_root())
        for rel in _oss_payload.engine_payload_files():
            if rel.suffix not in (".py", ".md"):
                continue
            full = engine_root / rel
            try:
                text = full.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            n = len(iter_violations(text, path=full, sibling_pattern=_ENGINE_SIBLING_NAME_TOKEN))
            if n:
                counts[f"(engine){rel.as_posix()}"] = n

    return counts
