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

CAVEAT ON THAT CEILING: the `hooks/` tree's own measured attribution
fraction, run against this detector, came out well above the 5-30% range
above. The sample the ceiling was drawn from surveyed several sibling-repo
names across the corpus; this detector, by contrast, scans for the ONE
sibling name this fleet's OSS-payload machinery currently knows about. A
tree whose real attribution content clusters around that single name will
plausibly measure a higher fraction than a sample averaged over several
names, so a `hooks/`-tree fraction above the ceiling is not on its own
evidence the detector over-flags — reconcile against the ceiling's own
per-name composition before treating a hooks/-tree overage as a detector
defect.

FAIL-OPEN POSTURE, mirroring `_prompt_surface_citations.py`: every ratified
classification input (`_oss_operative_strings.py`'s table/shape-rule/MCP-
prefix data, `STRUCTURAL_MARKERS`) is loaded via `importlib` and degrades to
an EMPTY result on any load failure, never a raised exception — a hiccup in
one of those inputs narrows this detector's carve-outs (more false positives
surface) rather than bricking the PreToolUse hook built on it. A Python file
that fails to `ast.parse` degrades the SAME way for that one file only: the
sibling-name/attribution scan is skipped for it (the position lens has
nothing to stand on), while the drive-path scan — which does not depend on
AST position — still runs.

THE COVERAGE ASYMMETRY this module inherits from `_oss_payload.py`: a
write-time guard built on `is_in_scope()` only ever sees files LOCAL to this
clone (`hooks/`, `skills/`, `agents/`, `commands/`, `snippets/`, …) because a
write to the engine repo's own `bin`/`lib` payload happens in ANOTHER
session's working tree. `current_counts()`, by contrast, enumerates the
FULL payload via `_oss_payload.payload_files()` (local + engine, when the
engine repo is resolvable) — the same local/engine split, restated here
because an unstated asymmetry reads as coverage a mechanism does not have.

THREE CARVE-OUTS, each toggled off/on and diffed against the corpus by the
carve-out narrowness tests in this module's own companion test suite
(three `test_*_carveout_is_narrow` tests, one per carve-out below) rather
than merely asserted narrow:

  1. RATIFIED OPERATIVE LITERALS — `_oss_operative_strings.py`. Two of its
     four historically-considered classes are DERIVABLE (MCP tool-name
     prefixes from `coordinator/mcp-topology.yaml`; the env-var/registry-key
     SHAPE RULE), leaving one genuinely irreducible literal residue. See
     that module's own docstring and ENTRY CRITERION.
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

#: Resolved once at import time. Empty/no-op on load failure — see the
#: module docstring's fail-open contract.
SIBLING_REPO_NAMES: tuple = (
    getattr(_operative_strings_module, "SIBLING_REPO_NAMES", ()) if _operative_strings_module else ()
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


def _sibling_name_pattern() -> "re.Pattern | None":
    """Compiled alternation over every known sibling repo name's full
    and short forms, in both hyphenated and underscored spellings. `None`
    when `SIBLING_REPO_NAMES` failed to load (fail-open:
    the sibling-name scan is skipped entirely, never manufactured from a
    hardcoded guess)."""
    if not SIBLING_REPO_NAMES:
        return None
    alternatives = []
    for name in SIBLING_REPO_NAMES:
        norm = name.replace("-", "_")
        parts = norm.split("_")
        alternatives.append(re.escape(name))
        alternatives.append(re.escape(norm))
        if len(parts) > 1:
            alternatives.append(re.escape(parts[-1]))
    pattern = "|".join(sorted(set(alternatives), key=len, reverse=True))
    return re.compile(rf"\b(?:{pattern})\b", re.IGNORECASE)


_SIBLING_NAME_TOKEN = _sibling_name_pattern()


def _is_irreducible_literal(token: str, path_str: str, line_no: int) -> bool:
    """True only at the exact `(file, line)` site an `IRREDUCIBLE_LITERALS`
    entry names — never for the same literal recurring elsewhere, including
    elsewhere in the same file. See `_oss_operative_strings.py`'s ENTRY
    CRITERION and per-entry scoping note."""
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
    if not STRUCTURAL_MARKERS:
        return False
    body = _structural_comment_body(line)
    if body is None:
        return False
    return _matches_any(STRUCTURAL_MARKERS, body) and bool(_BEGIN_WORD.search(body))


def _is_snippet_end(line: str) -> bool:
    if not STRUCTURAL_MARKERS:
        return False
    body = _structural_comment_body(line)
    if body is None:
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


# ---------------------------------------------------------------------------
# Violation detection
# ---------------------------------------------------------------------------


def iter_violations(text: str, *, path=None) -> list:
    """Every locality violation in `text`, in line order.

    `path` is optional but load-bearing for classification: when it names a
    `.py` file, the sibling-name/attribution check is gated by the `ast`/
    `tokenize` position lens (`_python_attribution_lines`); for any other
    path (or `path=None`), the sibling-name check runs over every
    non-fenced line, matching the markdown/prose trees this module also
    covers. The drive-path check is position-independent and runs
    everywhere except inside a structural snippet fence.
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

    lines = text.split("\n")
    violations: list = []
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
            violations.append(
                Violation(path_str, line_no, "drive-rooted windows path", _excerpt(line), fingerprint)
            )

        if _SIBLING_NAME_TOKEN is None:
            continue
        if python_scan_disabled:
            continue
        if is_python and line_no not in attribution_lines:
            continue

        for m in _SIBLING_NAME_TOKEN.finditer(line):
            if _inside_mcp_prefix_span(line, m.start()):
                continue
            if _is_angle_bracket_placeholder(line, m.start(), m.end()):
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


def new_violations(before: str, after: str, *, path=None) -> list:
    """Violations present in `after` that were not already present in
    `before`, as a multiset difference — same contract as
    `_prompt_surface_citations.new_violations`, so a hard-deny guard built on
    this is safe against the existing corpus's legacy violations: a
    violation sitting untouched elsewhere in the file contributes equally to
    both sides of the diff and never surfaces here."""
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
            n = len(iter_violations(text, path=full))
            if n:
                counts[f"(engine){rel.as_posix()}"] = n

    return counts
