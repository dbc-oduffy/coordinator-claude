"""Shared detector for changelog-shaped prose in coordinator doctrine surfaces.

A doctrine surface states the rule as it stands now, present tense, addressed
to the reader who has to obey it next. It does not carry the rule's history —
ruling dates, `DR-` supersession chains, "was P now Q", "retired on <date>",
origin-incident narration. That standing rule lives in this repo's own
`CLAUDE.md` § Conventions ("Doctrine is not changelog. State the rule as it
stands, present tense... history belongs in commits, decisions, plans.");
this module is the write-time and ratchet-test detector for it.

Governed surfaces: `coordinator/{skills,agents,commands,snippets,docs/wiki}/**/*.md`
(excluding any `tests/`/`fixtures/` subdirectory anywhere in the relative
path, and any basename in `_EXEMPT_BASENAMES` -- a file whose own stated
purpose is to BE a changelog, e.g. `changelog-history.md`, not a doctrine
surface this module's rule applies to) and the `description`/`$comment`
string VALUES inside `coordinator/schemas/*.schema.json` (direct children
only, matching the governing glob literally — not
`coordinator/schemas/fixtures/*.schema.json`).

`x-bump-note`/`x-bump-class` JSON keys are OUT of scope by construction, not
by omission: this module only walks `description`/`$comment` values, so a
changelog-shaped field that exists precisely to carry changelog content never
enters the walk. Widening the walk to catch it would flag a field whose whole
job is to hold the history this module exists to keep OUT of every other
field.

Consumers — both import `iter_violations()`/`new_violations()` from here
rather than keeping a second copy of the regexes:
  - `coordinator/hooks/scripts/guard-doctrine-changelog-prose.py` — PreToolUse
    advisory. Uses `new_violations()` so only the CURRENT write's own new
    hits fire, never the corpus's pre-existing debt.
  - `coordinator/tests/test_doctrine_surfaces_are_not_changelogs.py` —
    ratchet test. Uses `iter_violations()` against each file's full current
    text and compares the per-file COUNT to a checked-in baseline.

Two governed file CLASSES, one shared module
----------------------------------------------
`scope_class(path)` names which of two classes a path belongs to --
`"doctrine"` (the prose corpus documented above, governed by
`DOCTRINE_MD_DIRS`/`DOCTRINE_SCHEMAS_DIR`) or `"config"` (a repo-root
`coordinator.local.md`, resolved from the CANDIDATE PATH's own nearest
`.git` ancestor, never by comparison against this module's `REPO_ROOT` --
`REPO_ROOT` names the plugin's own tree, which is the wrong repo for every
sibling that mirrors this module). `is_in_scope()` stays the boolean either
class implies. The config class is scanned by its own, tier-free predicate
(`_scan_config_line`) rather than the prose rules above -- config debt wears
none of the shapes those rules were tuned to catch. Both classes route
through `iter_violations()`/`new_violations()` via an explicit
`is_config`/`is_json` caller-supplied selector, never a path sniff.

Two confidence tiers, not one
------------------------------
`Violation.confidence` is `"high"` or `"ambiguous"`. HIGH-confidence hits are
the signal classes a 53-file classification probe (plus two corpus-wide
follow-up sweeps) found reliable: a history verb within ~15 tokens of an ISO
date, a paragraph-leading `Origin:`/`Rationale (<date>):`/`Update <date>:`/
`Added <date>:` construction, an explicit two-`DR-`-id supersession chain, a
dated provenance tag, and a bare dated parenthetical.

`_HISTORY_VERB` widened past the original stem set (`retir*`, `remov*`,
`delet*`, `kill*`, `deprecat*`, `supersed*`, `formerly`, `previously`,
`renam*`, `amend*`, `narrow*`, `re-spec'd`, `ruled down`, `used to`, `no
longer`) to also cover `demoted`, `promoted`, `added`, `landed`, `shipped`,
`completion`, `reversed`, `relocated`, `moved`, `dropped`, `restored`,
`widened`, `corrected`, `confirmed` -- a corpus sample of the lines a bare
`grep` for dates/DR-ids found but the original verb set missed (`` `/fan-out`
demoted 2026-05-30 ``, `added ENVELOPE_VERSION 5 (E-RUNTIME,
2026-05-1...)`). These are literal words, not `\\w*` stems like the original
set, deliberately: several of them (`moved`, `dropped`, `restored`,
`corrected`, `confirmed`) are common enough in their present-tense/gerund
forms (`moves`, `dropping`, `confirming`) that stemming them would widen the
match surface into ordinary operative prose that happens to sit near an
unrelated date, not just the historical-narration shape being targeted.

A bare dated parenthetical -- `the callee inherits the same scrubbed env
(2026-07-04, coordinator-core-shim P0)` -- carries no verb and no provenance
keyword, so neither `_HISTORY_VERB` nor `_PROVENANCE_KEYWORDS` sees it, yet
the shape is exactly the same defect: a claim dated as though the date were
load-bearing. `_bare_dated_parenthetical_hit` catches a parenthesized or
italicized span containing a bare date token not preceded by an operative-
threshold cue (`pre`/`before`/`since`/`as of`). It fires ONLY as a fallback
-- `if not violations` in `_scan_text_line` -- after every other rule has
had a chance to claim the line, so it never double-counts a passage another
rule already caught under a more specific kind.

Dated provenance tags — a rule stated correctly in present tense, tagged
with an empirical-basis citation like `(Source: 2026-06-26, project-rag)` or
a trailing italicized `*2026-06-26, project-rag*` — are the largest single
bucket in the corpus. The remedy is narrower than the other high-confidence
classes: strip the DATE, keep the ATTRIBUTION (`(Source: 2026-06-26,
project-rag)` becomes `(Source: project-rag)`), because the attribution
itself is a live fact about where the rule's empirical basis comes from,
while the date is when someone last checked it. Detected via
`_PROVENANCE_KEYWORDS` (`Source`/`Origin`/`Encoded`/`Established` within a
short token window of a bare date token) and `_ITALIC_PROVENANCE` (an
italic `*...*` span pairing a bare date with a trailing attribution via a
comma, in either order). The keyword form dedupes against the
paragraph-leading `Origin:` header rule above via `_is_paragraph_leading` —
a leading `Origin:` construction is narration to rewrite wholesale, not a
tag to trim, so it stays exclusively in that bucket; `Source`/`Encoded`/
`Established` have no such header rule and are always classified as a
provenance tag, leading or not.

The probe also found two classes genuinely ambiguous and handles them
EXPLICITLY rather than folding them into either bucket by accident:

  - `PM ruling` — sometimes bare provenance for a rule that is still fully
    present-tense and live ("by explicit PM ruling, do not add one"),
    sometimes a dated citation for a still-live rule ("Advise, not deny (PM
    ruling, 2026-08-05)" describing a CURRENT state), sometimes reversal
    narration ("PM ruling D5 retired that audit's auto-write"). This module
    flags a hit into the AMBIGUOUS bucket only when the line ALSO carries a
    bare ISO date token (the same date-token detection every other rule in
    this module uses), a history verb (`_HISTORY_VERB`), or a reversal verb
    from the separate, narrower `_PM_RULING_REVERSAL_VERB` set (`flip`,
    `switch`, `change`, `walked back`, `downgrade`, `soften`, `revert`,
    `undone`, `abandon`, `scrap`, and stems) — deliberately kept out of
    `_HISTORY_VERB` because that constant also drives the HIGH-confidence
    verb-near-date rule, gated by a shrink-only ratchet baseline that a
    corpus-wide widening would break. A bare "PM ruling" with none of these
    three signals on the line is left unflagged, on the working assumption
    that it is bare provenance for a still-live rule; this is a probe-corpus
    finding, not a proof — the reversal-verb sample above is not exhaustive,
    so a dateless reversal narrated with some other verb can still pass
    through unflagged. Even with a date or a verb signal present, the phrase
    still cannot tell bare dated provenance from reversal narration on its
    own — nothing about "PM ruling <date>" itself names what changed, and a
    dateless history/reversal verb near the phrase is exactly the
    reversal-narration shape — so both keep landing in AMBIGUOUS rather
    than being resolved automatically to either bucket.
    `guard-doctrine-changelog-prose.py` reports this bucket with materially
    softer language ("worth a second look", not "is changelog prose") so
    the advisory doesn't overclaim what a bare-phrase match can actually
    establish.
  - Archived-schema read-tolerance notes — `'superseded' is retired
    (2026-06-26) but retained for archived read-tolerance` reads, on the
    high-confidence rule alone, as a textbook verb-near-date hit ("retired"
    fifteen tokens from a date). But the SUBSTANCE survives present-tense
    rewriting (drop the date, keep "retained for archived read-tolerance,"
    per CLAUDE.md § Conventions item 5: a live asymmetry, not history) — it
    is a genuinely different shape from ordinary reversal narration, not a
    edge case of it. Detected into its own ambiguous kind via a small
    cue-phrase set (`_READ_TOLERANCE_CUES`) checked on any line that would
    otherwise score high-confidence, so it downgrades rather than either
    silently passing or getting flagged with a message that tells the editor
    to do exactly the wrong thing (delete the substance instead of the
    date).

Neither ambiguous kind inflates the baseline silently: both carry their own
`kind` string (prefixed `ambiguous:`), so a baseline diff or a report reader
can see the ambiguous count separately from the high-confidence count rather
than the two collapsing into one number.

NOT a violation (see module docstring for the full false-positive-class
reasoning that motivated each exemption):
  - `<!-- spec-backlink: ... -->` / `<!-- Spec backlink: ... -->` / `>
    Spec backlink: ...` / `<!-- consumers: ... -->` lines — skipped
    outright, never scanned;
  - a bare `DR-\\d+` with no history verb nearby and no two-id chain — a live
    rule citation ("per DR-097, a bump owes a sibling notice"), not history;
  - anything inside a fenced code block, or the frontmatter block (first
    `---`-delimited region) — a fixture/example date in frontmatter is data,
    not narrated history;
  - a date embedded in a PATH or FILENAME token
    (`docs/plans/2026-07-31-foo.md`, `state/handoffs/2026-08-06-bar.md`) —
    the date-matching rule only fires on a token that, after stripping
    surrounding punctuation, is EXACTLY an ISO date and carries no `/`; a
    path/filename token fails that check because it carries extra
    characters (a slash, or a trailing `-slug.ext`) around the digits;
  - an operative threshold date ("Pre-2026-05-22 memos are grandfathered but
    PM-relay evidence still applies") — the date token here is fused to a
    `Pre-` prefix, so it never becomes a bare ISO-date token in the first
    place, and no history verb sits near it regardless.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[3]

DOCTRINE_MD_DIRS = (
    REPO_ROOT / "coordinator" / "skills",
    REPO_ROOT / "coordinator" / "agents",
    REPO_ROOT / "coordinator" / "commands",
    REPO_ROOT / "coordinator" / "snippets",
    REPO_ROOT / "coordinator" / "docs" / "wiki",
)

DOCTRINE_SCHEMAS_DIR = REPO_ROOT / "coordinator" / "schemas"

_EXEMPT_PATH_SEGMENTS = frozenset({"tests", "fixtures"})

#: a doctrine surface -- exempt from `DOCTRINE_MD_DIRS` scanning regardless
#: pre-consolidation release history VERBATIM ("Entry content, dates,
_EXEMPT_BASENAMES = frozenset({"changelog-history.md"})

_SCHEMA_PROSE_KEYS = frozenset({"description", "$comment"})


@dataclass(frozen=True)
class Violation:
    line_no: int
    kind: str
    excerpt: str
    line_fingerprint: str = ""
    confidence: str = "high"


#: repo-root `coordinator.local.md`, resolved from the CANDIDATE PATH's own
#: nearest `.git` ancestor (see `_find_repo_root`), never from `REPO_ROOT`
#: CLASSES" section for why an appended `DOCTRINE_MD_DIRS` entry can never
_CONFIG_FILE_BASENAME = "coordinator.local.md"

_REPO_ROOT_WALK_MAX_DEPTH = 32


def _find_repo_root(path: Path) -> "Path | None":
    """Walk up from `path`'s parent directory for a sibling `.git` entry,
    stat-only (`Path.exists()`, never a `git rev-parse` subprocess -- this
    runs on the hook hot path), bounded by `_REPO_ROOT_WALK_MAX_DEPTH`.
    Returns `None` if no `.git` ancestor is found within the bound, or if
    the walk reaches a filesystem root first."""
    current = path.parent
    for _ in range(_REPO_ROOT_WALK_MAX_DEPTH):
        try:
            found = (current / ".git").exists()
        except OSError:
            return None
        if found:
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent
    return None


def surface_of(path: Path) -> "str | None":
    """Which of the five `DOCTRINE_MD_DIRS` surfaces `path` belongs to --
    `"skills"`, `"agents"`, `"commands"`, `"snippets"`, or `"wiki"` -- or
    `None` if `path` is not an in-scope `.md` file under any of them.

    A sibling accessor to `scope_class()`, added for the doctrinal surface
    weight ratchet (C8, docs/plans/2026-08-13-doctrinal-surface-weight-
    ratchet.md, § D6/D7). `scope_class()`'s three-value contract
    (`"doctrine"`/`"config"`/`None`) cannot distinguish WHICH doctrine
    surface a path is on -- only that it is one -- and the ratio guard
    (`guard-doctrine-surface-ratio.py`) needs the surface name to select a
    tier table. This composes `DOCTRINE_MD_DIRS` internally, exactly the
    same population `scope_class()` already walks, rather than re-deriving
    it: reuse of `DOCTRINE_MD_DIRS`, not a second population scoper.
    `scope_class()`'s own return shape and suite are untouched by this
    addition.

    Returns the matching `DOCTRINE_MD_DIRS` root's directory name --
    `"skills"`, `"agents"`, `"commands"`, `"snippets"`, `"wiki"` -- which is
    also the exact surface key `coordinator/lib/doctrine_surface_tiers.py`'s
    `tier_boundaries_for(surface)` and the C2 baseline
    (`coordinator/tests/baselines/doctrine-surface-weight.json`) both key
    on. Non-`.md` files (e.g. `*.schema.json`, which `scope_class()` also
    recognises as `"doctrine"`) are not one of the five measured surfaces
    and return `None` here, even though `scope_class()` would return
    `"doctrine"` for them -- the two functions answer different questions.
    """
    try:
        resolved = path.resolve()
    except Exception:
        return None
    if resolved.suffix != ".md":
        return None
    if resolved.name in _EXEMPT_BASENAMES:
        return None
    for root in DOCTRINE_MD_DIRS:
        try:
            rel = resolved.relative_to(root)
        except ValueError:
            continue
        if _EXEMPT_PATH_SEGMENTS.intersection(rel.parts[:-1]):
            return None
        return root.name
    return None


def scope_class(path: Path) -> "str | None":
    try:
        resolved = path.resolve()
    except Exception:
        return None

    if resolved.name == _CONFIG_FILE_BASENAME:
        repo_root = _find_repo_root(resolved)
        if repo_root is not None and resolved.parent == repo_root:
            return "config"
        return None

    if resolved.suffix == ".md":
        if resolved.name in _EXEMPT_BASENAMES:
            return None
        for root in DOCTRINE_MD_DIRS:
            try:
                rel = resolved.relative_to(root)
            except ValueError:
                continue
            if _EXEMPT_PATH_SEGMENTS.intersection(rel.parts[:-1]):
                return None
            return "doctrine"
        return None

    if resolved.name.endswith(".schema.json"):
        if resolved.parent == DOCTRINE_SCHEMAS_DIR.resolve():
            return "doctrine"
        return None

    return None


def is_in_scope(path: Path) -> bool:
    """True for an in-scope `.md` file under `DOCTRINE_MD_DIRS`, a
    `*.schema.json` file directly inside `DOCTRINE_SCHEMAS_DIR`, or a
    repo-root `coordinator.local.md` (see `scope_class`)."""
    return scope_class(path) is not None


def iter_doctrine_surface_files() -> Iterable[Path]:
    """Every in-scope file, sorted for deterministic reporting -- the
    doctrine-class corpus (`DOCTRINE_MD_DIRS`/`DOCTRINE_SCHEMAS_DIR`), plus
    THIS repo's own config-class file if it exists (C4, config-file-class
    plan): the ratchet this function feeds governs the config class too, so
    a repo-root `coordinator.local.md` accretion is caught by the same
    shrink-only budget rather than being exempted from the very ratchet its
    own plan exists to extend. `REPO_ROOT`-relative here is correct (unlike
    `scope_class`'s general classification of an arbitrary write target,
    which must never use `REPO_ROOT` -- see that function's docstring):
    this is enumerating THIS repo's OWN file for THIS repo's own ratchet
    run, not classifying a payload path that could belong to any repo."""
    for root in DOCTRINE_MD_DIRS:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.md")):
            if is_in_scope(path):
                yield path
    if DOCTRINE_SCHEMAS_DIR.is_dir():
        for path in sorted(DOCTRINE_SCHEMAS_DIR.glob("*.schema.json")):
            if is_in_scope(path):
                yield path
    config_path = REPO_ROOT / _CONFIG_FILE_BASENAME
    if scope_class(config_path) == "config":
        yield config_path


_FENCE = re.compile(r"^\s*```")

_EXEMPT_LINE_PATTERNS = (
    re.compile(r"^\s*<!--\s*spec-backlink:", re.IGNORECASE),
    re.compile(r"^\s*<!--\s*Spec backlink:", re.IGNORECASE),
    re.compile(r"^\s*>\s*Spec backlink:", re.IGNORECASE),
    re.compile(r"^\s*<!--\s*consumers:", re.IGNORECASE),
)

_LEADING_MARKUP = re.compile(r"^[\s>*\-]+")
_BOLD_ITALIC = re.compile(r"^[*_]+")


def _dequote_leading(line: str) -> str:
    stripped = _LEADING_MARKUP.sub("", line)
    stripped = _BOLD_ITALIC.sub("", stripped)
    return stripped


_MENTION_SPAN = re.compile(
    r"`[^`]*`"
    r'|"[^"]*"'
    r"|“[^”]*”"
)


def _strip_mentions(line: str) -> str:
    return _MENTION_SPAN.sub(lambda m: " " * len(m.group()), line)


_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_TOKEN = re.compile(r"\S+")
_TOKEN_STRIP = ".,;:()[]\"'*"

#: `_PROVENANCE_KEYWORDS` below for the identical reason.
_HISTORY_VERB = re.compile(
    r"(?<![\w.-])("
    r"retir\w*|remov\w*|delet\w*|kill\w*|deprecat\w*|supersed\w*|"
    r"formerly|previously|renam\w*|amend\w*|narrow\w*|re-?spec'?d|"
    r"ruled\s+down|used\s+to|no\s+longer|"
    r"demoted|promoted|added|landed|shipped|completion|reversed|"
    r"relocated|moved|dropped|restored|widened|corrected|confirmed|"
    r"bumped"
    r")(?![\w.-])",
    re.IGNORECASE,
)

#: co-located date or `_HISTORY_VERB` hit required (C7/plan Rulings). Each
#: `_HISTORY_VERB` -- that constant only drives the proximity-gated
#: false-positived on the FUNCTIONAL "is used to <verb>" construction
#: (`"RECEIVER-ROUTING-CRITICAL — used to determine delivery target"`,
_USED_TO_STANDALONE = re.compile(
    r"\b(this|it|that|they|which)\s+used\s+to\b|\bused\s+to\s+be\b", re.IGNORECASE
)
_NO_LONGER_STANDALONE = re.compile(r"\bno\s+longer\b(?!\s+than\b)", re.IGNORECASE)

#: The same narrowing `_USED_TO_STANDALONE` above already earned, applied to
#:   CHANGELOG — a definite subject in main-clause position narrates that THIS
#:   FUNCTIONAL — a RELATIVE CLAUSE describes a runtime state the reader may
#: DELIBERATELY CONSERVATIVE, in the direction of the guard FIRING. The window
_NO_LONGER_RELATIVE_CLAUSE = re.compile(
    r"\b(?:that|which|who|whose|where)\b(?:\s+\w+){0,3}?\s+no\s+longer\b", re.IGNORECASE
)
_NEW_VERSION_STANDALONE = re.compile(
    r"\bnew\s+version\s+has\b|\bthe\s+new\s+version\b", re.IGNORECASE
)

#: `UPDATE:` as a paragraph/line preamble -- distinct from `_ORIGIN_HEADER`'s
_UPDATE_PREAMBLE = re.compile(r"^UPDATE\s*:", re.IGNORECASE)

#: `PM decision:`/`PM ruling:` used as a DATELINE/ATTRIBUTION PREAMBLE --
#: the inline `_PM_RULING` ambiguous rule below, which matches the phrase
#: ANYWHERE on a line and requires a date/verb signal to fire at all -- a
_PM_DATELINE_PREAMBLE = re.compile(r"^PM\s+(decision|ruling)\s*:", re.IGNORECASE)

_TOKEN_PROXIMITY_WINDOW = 15

_ORIGIN_HEADER = re.compile(
    r"^(Origin(\s+incident)?|Rationale\s*\([^)]*\)|Update\s+\d{4}-\d{2}-\d{2}|"
    r"Added\s+\d{4}-\d{2}-\d{2})\s*:",
    re.IGNORECASE,
)

_DR_CHAIN = re.compile(r"\bDR-\d+\s+supersed(es|ed)\s+DR-\d+\b", re.IGNORECASE)
_SUPERSEDED_DATE = re.compile(r"\bsuperseded\s+(in part\s+)?\d{4}-\d{2}-\d{2}\b", re.IGNORECASE)

_READ_TOLERANCE_CUES = re.compile(
    r"retained for|read-tolerance|read tolerance|backward-compat|"
    r"legacy read|archived read",
    re.IGNORECASE,
)

_PM_RULING = re.compile(r"\bPM ruling\b", re.IGNORECASE)

#: below -- deliberately NOT folded into `_HISTORY_VERB`, whose match also
#: Widening `_HISTORY_VERB` corpus-wide would raise high-confidence counts
#: advisory." has no date and no `_HISTORY_VERB` hit, so it needs its own,
#: narrower-scoped verb set to stay in the AMBIGUOUS bucket rather than
_PM_RULING_REVERSAL_VERB = re.compile(
    r"(?<![\w.-])("
    r"flip\w*|switch\w*|chang\w*|walked?\s+back|downgrad\w*|soften\w*|"
    r"revert\w*|undone|abandon\w*|scrapp\w*"
    r")(?![\w.-])",
    re.IGNORECASE,
)

#: undercounted. Still narrower than `_TOKEN_PROXIMITY_WINDOW` -- these tags
#: Same `(?<![\w.-])`/`(?![\w.-])` boundary fix as `_HISTORY_VERB` -- plain
_PROVENANCE_KEYWORDS = re.compile(
    r"(?<![\w.-])(Source|Origin|Encoded|Established)(?![\w.-])", re.IGNORECASE
)
_PROVENANCE_WINDOW = 10

_ITALIC_PROVENANCE = re.compile(
    r"\*\s*(?:\d{4}-\d{2}-\d{2}\s*,\s*[^*\n]+?|[^*\n]+?,\s*\d{4}-\d{2}-\d{2})[.,;:]?\s*\*"
)

#: A cue immediately before a bare date token that names an OPERATIVE
#: THRESHOLD the rule gates on now ("Pre-2026-05-22 memos...", "before
_THRESHOLD_CUE = re.compile(r"(?i)\b(pre|before|since|as\s+of)[\s-]*$")

_PAREN_SPAN = re.compile(r"\(([^()]*)\)")
_ITALIC_SPAN = re.compile(r"\*([^*\n]*)\*")


def _is_paragraph_leading(line: str, start: int) -> bool:
    prefix = line[:start]
    return prefix.strip(" \t>*_-") == ""


def _date_token_positions(line: str) -> "list[tuple[int, int]]":
    spans = []
    for m in _TOKEN.finditer(line):
        raw = m.group(0)
        stripped = raw.strip(_TOKEN_STRIP)
        if "/" in stripped:
            continue
        if _ISO_DATE.fullmatch(stripped):
            start = m.start() + raw.index(stripped)
            spans.append((start, start + len(stripped)))
    return spans


def _token_index_at(char_pos: int, token_spans: "list[tuple[int, int]]") -> int:
    for i, (start, end) in enumerate(token_spans):
        if start <= char_pos < end:
            return i
    for i in range(len(token_spans) - 1, -1, -1):
        if token_spans[i][0] <= char_pos:
            return i
    return 0


def _excerpt(line: str) -> str:
    return " ".join(line.split())[:90]


def _bare_dated_parenthetical_hit(line: str, date_spans: "list[tuple[int, int]]") -> bool:
    """A parenthesized or italicized span carrying a bare ISO date with no
    verb, no provenance keyword, and no operative-threshold cue immediately
    before the date -- `(the callee inherits the same scrubbed env
    (2026-07-04, coordinator-core-shim P0))`. See module docstring for why
    this fires only as a FALLBACK, never alongside another hit on the same
    line -- one flag per changelog-shaped passage, not one per date token in
    it."""
    for span_re in (_PAREN_SPAN, _ITALIC_SPAN):
        for m in span_re.finditer(line):
            g_start, g_end = m.start(), m.end()
            for d_start, d_end in date_spans:
                if g_start < d_start and d_end <= g_end:
                    prefix_window = line[max(0, d_start - 20) : d_start]
                    if _THRESHOLD_CUE.search(prefix_window):
                        continue
                    return True
    return False


def _scan_text_line(line: str, line_no: int) -> "list[Violation]":
    violations: list = []
    for pattern in _EXEMPT_LINE_PATTERNS:
        if pattern.match(line):
            return []

    fingerprint = " ".join(line.split())
    if not fingerprint:
        return []

    exempt_date = bool(_RETIREMENT_EXEMPTION_MARKER.search(line))

    scannable = _strip_mentions(line)

    all_token_spans = [(m.start(), m.end()) for m in _TOKEN.finditer(line)]
    date_spans = [] if exempt_date else _date_token_positions(scannable)
    verb_matches = list(_HISTORY_VERB.finditer(scannable))

    read_tolerance = bool(_READ_TOLERANCE_CUES.search(line))

    verb_date_hit = False
    if date_spans and verb_matches:
        date_token_idx = [
            _token_index_at(start, all_token_spans) for start, _end in date_spans
        ]
        for vm in verb_matches:
            verb_token_idx = _token_index_at(vm.start(), all_token_spans)
            if any(abs(verb_token_idx - di) <= _TOKEN_PROXIMITY_WINDOW for di in date_token_idx):
                verb_date_hit = True
                break

    if verb_date_hit:
        kind = (
            "ambiguous: archived/legacy read-tolerance note"
            if read_tolerance
            else "history verb near date"
        )
        confidence = "ambiguous" if read_tolerance else "high"
        violations.append(Violation(line_no, kind, _excerpt(line), fingerprint, confidence))

    dequoted = _dequote_leading(line)
    origin_header_hit = bool(_ORIGIN_HEADER.match(dequoted))
    if origin_header_hit:
        violations.append(
            Violation(
                line_no,
                "changelog-shaped section header (Origin/Rationale/Update/Added)",
                _excerpt(line),
                fingerprint,
                "high",
            )
        )

    if date_spans:
        date_token_idx = [
            _token_index_at(start, all_token_spans) for start, _end in date_spans
        ]
        provenance_tag_hit = False
        for km in _PROVENANCE_KEYWORDS.finditer(line):
            if km.group(0).lower() == "origin" and (
                origin_header_hit or _is_paragraph_leading(line, km.start())
            ):
                continue
            kw_idx = _token_index_at(km.start(), all_token_spans)
            if any(abs(kw_idx - di) <= _PROVENANCE_WINDOW for di in date_token_idx):
                provenance_tag_hit = True
                break
        if provenance_tag_hit:
            violations.append(
                Violation(
                    line_no,
                    "dated provenance tag (Source/Origin/Encoded/Established)",
                    _excerpt(line),
                    fingerprint,
                    "high",
                )
            )

    if not exempt_date and _ITALIC_PROVENANCE.search(line):
        violations.append(
            Violation(
                line_no,
                "dated provenance tag (italic attribution)",
                _excerpt(line),
                fingerprint,
                "high",
            )
        )

    if not exempt_date and (_DR_CHAIN.search(line) or _SUPERSEDED_DATE.search(line)):
        if not verb_date_hit:
            violations.append(
                Violation(
                    line_no,
                    "explicit DR supersession chain",
                    _excerpt(line),
                    fingerprint,
                    "high",
                )
            )

    if _PM_RULING.search(line) and (
        date_spans or _HISTORY_VERB.search(line) or _PM_RULING_REVERSAL_VERB.search(line)
    ):
        violations.append(
            Violation(
                line_no,
                "ambiguous: PM ruling <date> (bare provenance vs reversal narration)",
                _excerpt(line),
                fingerprint,
                "ambiguous",
            )
        )

    if (
        not violations
        and not exempt_date
        and date_spans
        and _bare_dated_parenthetical_hit(line, date_spans)
    ):
        violations.append(
            Violation(
                line_no,
                "bare dated parenthetical (no verb, no provenance keyword)",
                _excerpt(line),
                fingerprint,
                "high",
            )
        )

    # ---- `_HISTORY_VERB` hit required (C7/plan Rulings). ----
    # A phrase inside a code span or quotation marks is being MENTIONED, not
    mention_free = _strip_mentions(line)

    if _USED_TO_STANDALONE.search(mention_free):
        violations.append(
            Violation(line_no, "history phrase (used to)", _excerpt(line), fingerprint, "high")
        )

    if _NO_LONGER_STANDALONE.search(_NO_LONGER_RELATIVE_CLAUSE.sub(" ", mention_free)):
        violations.append(
            Violation(line_no, "history phrase (no longer)", _excerpt(line), fingerprint, "high")
        )

    if _NEW_VERSION_STANDALONE.search(mention_free):
        violations.append(
            Violation(
                line_no,
                "history phrase (new version has / the new version)",
                _excerpt(line),
                fingerprint,
                "high",
            )
        )

    if _UPDATE_PREAMBLE.match(dequoted):
        violations.append(
            Violation(
                line_no,
                "changelog-shaped section header (bare UPDATE: preamble)",
                _excerpt(line),
                fingerprint,
                "high",
            )
        )

    if _PM_DATELINE_PREAMBLE.match(dequoted):
        violations.append(
            Violation(
                line_no,
                "PM decision:/PM ruling: used as dateline preamble",
                _excerpt(line),
                fingerprint,
                "high",
            )
        )

    return violations


#: reference. Same `(?<![\w.-])`/`(?![\w.-])` boundary as `_HISTORY_VERB` so
_CONFIG_DR_ID = re.compile(r"(?<![\w.-])DR-\d+(?![\w.-])")

_CONFIG_ROT_PATH_RE = re.compile(r"cross-repo/inbox/|archive/|state/handoffs/")

#: `_CONFIG_DR_ID`'s `(?![\w.-])` boundary already lets through
#: unflagged -- so exempting the leg would license only the one citation
_RETIREMENT_EXEMPTION_MARKER = re.compile(
    r"<!--\s*doctrine-retirement-exemption:\s*[^>]*-->", re.IGNORECASE
)


def _scan_config_line(line: str, line_no: int) -> "list[Violation]":
    fingerprint = " ".join(line.split())
    if not fingerprint:
        return []

    violations: list = []
    exempt_date = bool(_RETIREMENT_EXEMPTION_MARKER.search(line))

    if not exempt_date:
        for _start, _end in _date_token_positions(line):
            violations.append(
                Violation(line_no, "config: bare ISO date", _excerpt(line), fingerprint, "high")
            )
    for _m in _CONFIG_DR_ID.finditer(line):
        violations.append(
            Violation(line_no, "config: bare DR-<id>", _excerpt(line), fingerprint, "high")
        )

    for _m in _CONFIG_ROT_PATH_RE.finditer(line):
        violations.append(
            Violation(
                line_no,
                "config: rot-prone path reference (cross-repo/inbox, archive, or "
                "state/handoffs)",
                _excerpt(line),
                fingerprint,
                "high",
            )
        )

    return violations


def _iter_config_violations(text: str) -> "list[Violation]":
    violations: list = []
    for line_no, line in _iter_scannable_lines(text):
        violations.extend(_scan_config_line(line, line_no))
    return violations


def _iter_scannable_lines(text: str) -> "Iterable[tuple[int, str]]":
    lines = text.split("\n")
    in_fence = False
    in_frontmatter = False

    for line_no, line in enumerate(lines, start=1):
        stripped = line.strip()

        if stripped == "---" and line_no <= 2:
            in_frontmatter = True
            continue
        if stripped == "---" and in_frontmatter:
            in_frontmatter = False
            continue
        if in_frontmatter:
            continue

        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        yield line_no, line


def _iter_markdown_violations(text: str) -> "list[Violation]":
    violations: list = []
    for line_no, line in _iter_scannable_lines(text):
        violations.extend(_scan_text_line(line, line_no))
    return violations


def _schema_prose_value_line_no(text: str, value: str, cursor: int) -> "tuple[int, int]":
    for ensure_ascii in (True, False):
        encoded = json.dumps(value, ensure_ascii=ensure_ascii)[1:-1]
        pos = text.find(encoded, cursor)
        if pos != -1:
            return text.count("\n", 0, pos) + 1, pos + len(encoded)
    return 0, cursor


def _iter_schema_json_violations(text: str) -> "list[Violation]":
    try:
        data = json.loads(text)
    except Exception:
        return []

    violations: list = []
    cursor = 0

    def _walk(node):
        nonlocal cursor
        if isinstance(node, dict):
            for key, value in node.items():
                if key in _SCHEMA_PROSE_KEYS and isinstance(value, str):
                    line_no, cursor = _schema_prose_value_line_no(text, value, cursor)
                    for candidate_line in value.split("\n"):
                        violations.extend(_scan_text_line(candidate_line, line_no))
                else:
                    _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(data)
    return violations


def iter_violations(
    text: str, *, is_json: bool = False, is_config: bool = False
) -> "list[Violation]":
    if is_config:
        return _iter_config_violations(text)
    if is_json:
        return _iter_schema_json_violations(text)
    return _iter_markdown_violations(text)


def _violation_key(v: Violation) -> tuple:
    return (v.kind, v.confidence, v.line_fingerprint)


def new_violations(
    before: str, after: str, *, is_json: bool = False, is_config: bool = False
) -> "list[Violation]":
    before_counts = Counter(
        _violation_key(v)
        for v in iter_violations(before, is_json=is_json, is_config=is_config)
    )
    after_violations = iter_violations(after, is_json=is_json, is_config=is_config)
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
