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
path) and the `description`/`$comment` string VALUES inside
`coordinator/schemas/*.schema.json` (direct children only, matching the
governing glob literally — not `coordinator/schemas/fixtures/*.schema.json`).

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

#: `.md` trees this module governs. `docs/wiki` is included alongside the
#: agent-prompt trees because doctrine wiki pages are exactly the surface
#: the PM ruling names ("doctrine surfaces" is not scoped to agent-facing
#: prompt text only).
DOCTRINE_MD_DIRS = (
    REPO_ROOT / "coordinator" / "skills",
    REPO_ROOT / "coordinator" / "agents",
    REPO_ROOT / "coordinator" / "commands",
    REPO_ROOT / "coordinator" / "snippets",
    REPO_ROOT / "coordinator" / "docs" / "wiki",
)

#: `coordinator/schemas/*.schema.json` — direct children only, matching the
#: governing glob literally. `coordinator/schemas/fixtures/` is excluded by
#: this non-recursion, same as the `*.md` trees' explicit tests/fixtures skip.
DOCTRINE_SCHEMAS_DIR = REPO_ROOT / "coordinator" / "schemas"

#: Subdirectory names that, anywhere in a governed `.md` file's relative
#: path, exempt it entirely — test fixtures and example data, not doctrine
#: prose a model reads mid-task.
_EXEMPT_PATH_SEGMENTS = frozenset({"tests", "fixtures"})

#: JSON object keys whose string VALUES are in scope inside a `*.schema.json`
#: file. `x-bump-note`/`x-bump-class` are deliberately absent — see module
#: docstring.
_SCHEMA_PROSE_KEYS = frozenset({"description", "$comment"})


@dataclass(frozen=True)
class Violation:
    line_no: int
    kind: str
    excerpt: str
    line_fingerprint: str = ""
    confidence: str = "high"  # "high" | "ambiguous"


# ---------------------------------------------------------------------------
# Scope
# ---------------------------------------------------------------------------


def is_in_scope(path: Path) -> bool:
    """True for an in-scope `.md` file under `DOCTRINE_MD_DIRS`, or a
    `*.schema.json` file directly inside `DOCTRINE_SCHEMAS_DIR`."""
    try:
        resolved = path.resolve()
    except Exception:
        return False

    if resolved.suffix == ".md":
        for root in DOCTRINE_MD_DIRS:
            try:
                rel = resolved.relative_to(root)
            except ValueError:
                continue
            if _EXEMPT_PATH_SEGMENTS.intersection(rel.parts[:-1]):
                return False
            return True
        return False

    if resolved.name.endswith(".schema.json"):
        return resolved.parent == DOCTRINE_SCHEMAS_DIR.resolve()

    return False


def iter_doctrine_surface_files() -> Iterable[Path]:
    """Every in-scope file, sorted for deterministic reporting."""
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


# ---------------------------------------------------------------------------
# Line-level exemptions
# ---------------------------------------------------------------------------

_FENCE = re.compile(r"^\s*```")

#: Lines that are never scanned, regardless of content — required doctrine
#: machinery, not prose.
_EXEMPT_LINE_PATTERNS = (
    re.compile(r"^\s*<!--\s*spec-backlink:", re.IGNORECASE),
    re.compile(r"^\s*<!--\s*Spec backlink:", re.IGNORECASE),
    re.compile(r"^\s*>\s*Spec backlink:", re.IGNORECASE),
    re.compile(r"^\s*<!--\s*consumers:", re.IGNORECASE),
)

#: Strip common leading markdown decoration (list markers, blockquote,
#: bold/italic delimiters) so a paragraph-leading construction like
#: `- **Origin:** ...` or `> Update 2026-08-06: ...` is still recognized as
#: paragraph-leading.
_LEADING_MARKUP = re.compile(r"^[\s>*\-]+")
_BOLD_ITALIC = re.compile(r"^[*_]+")


def _dequote_leading(line: str) -> str:
    stripped = _LEADING_MARKUP.sub("", line)
    stripped = _BOLD_ITALIC.sub("", stripped)
    return stripped


# ---------------------------------------------------------------------------
# High-confidence rules
# ---------------------------------------------------------------------------

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_TOKEN = re.compile(r"\S+")
_TOKEN_STRIP = ".,;:()[]\"'"

#: History-verb stems/phrases. Matched as a substring search over the whole
#: line (multi-word phrases like "used to"/"no longer"/"ruled down" can't be
#: single-token matches), then converted to a token index for the proximity
#: check against a date token.
#:
#: `(?<![\w.-])`/`(?![\w.-])` REPLACE plain `\b` on both ends -- `\b` alone
#: treats `-` and `.` as boundaries, so `\bcompletion\b` matched inside
#: `local-completion` and `\bsource\b`-adjacent logic matched inside
#: `cross-source` (confirmed false positives: `completion.fold`,
#: `local-completion`, `cross-source`, all compound identifiers/filenames/
#: dotted attribute paths, none of them prose). The lookaround additionally
#: excludes `-`/`.` from BOTH sides so a verb only counts as a standalone
#: word, never a segment of a hyphenated or dotted compound. Applies to
#: `_PROVENANCE_KEYWORDS` below for the identical reason.
_HISTORY_VERB = re.compile(
    r"(?<![\w.-])("
    r"retir\w*|remov\w*|delet\w*|kill\w*|deprecat\w*|supersed\w*|"
    r"formerly|previously|renam\w*|amend\w*|narrow\w*|re-?spec'?d|"
    r"ruled\s+down|used\s+to|no\s+longer|"
    r"demoted|promoted|added|landed|shipped|completion|reversed|"
    r"relocated|moved|dropped|restored|widened|corrected|confirmed"
    r")(?![\w.-])",
    re.IGNORECASE,
)

_TOKEN_PROXIMITY_WINDOW = 15

_ORIGIN_HEADER = re.compile(
    r"^(Origin(\s+incident)?|Rationale\s*\([^)]*\)|Update\s+\d{4}-\d{2}-\d{2}|"
    r"Added\s+\d{4}-\d{2}-\d{2})\s*:",
    re.IGNORECASE,
)

_DR_CHAIN = re.compile(r"\bDR-\d+\s+supersed(es|ed)\s+DR-\d+\b", re.IGNORECASE)
_SUPERSEDED_DATE = re.compile(r"\bsuperseded\s+(in part\s+)?\d{4}-\d{2}-\d{2}\b", re.IGNORECASE)

#: Cue phrases that reclassify an otherwise-high-confidence verb-near-date
#: hit as the archived-read-tolerance ambiguous class — see module docstring.
_READ_TOLERANCE_CUES = re.compile(
    r"retained for|read-tolerance|read tolerance|backward-compat|"
    r"legacy read|archived read",
    re.IGNORECASE,
)

_PM_RULING = re.compile(r"\bPM ruling\b", re.IGNORECASE)

#: Reversal verbs used ONLY to widen the `PM ruling` ambiguous condition
#: below -- deliberately NOT folded into `_HISTORY_VERB`, whose match also
#: drives the HIGH-confidence verb-near-date rule gated by the shrink-only
#: ratchet baseline (`coordinator/tests/doctrine_changelog_prose_baseline.json`).
#: Widening `_HISTORY_VERB` corpus-wide would raise high-confidence counts
#: and break that ratchet; a bare "PM ruling flipped this from a hard-deny to
#: advisory." has no date and no `_HISTORY_VERB` hit, so it needs its own,
#: narrower-scoped verb set to stay in the AMBIGUOUS bucket rather than
#: passing unflagged.
_PM_RULING_REVERSAL_VERB = re.compile(
    r"(?<![\w.-])("
    r"flip\w*|switch\w*|chang\w*|walked?\s+back|downgrad\w*|soften\w*|"
    r"revert\w*|undone|abandon\w*|scrapp\w*"
    r")(?![\w.-])",
    re.IGNORECASE,
)

#: Keyword-form dated provenance tag -- see module docstring. Widened from
#: an initial 6-token window: a real tag can carry a short qualifier between
#: the keyword and the date (`Source: claude-central L10, 2026-05-30`), so 6
#: undercounted. Still narrower than `_TOKEN_PROXIMITY_WINDOW` -- these tags
#: are compact, not paragraphs.
#:
#: Same `(?<![\w.-])`/`(?![\w.-])` boundary fix as `_HISTORY_VERB` -- plain
#: `\b` matched `source` inside `cross-source` (a compound identifier, not a
#: provenance tag); see that constant's comment for the full reasoning.
_PROVENANCE_KEYWORDS = re.compile(
    r"(?<![\w.-])(Source|Origin|Encoded|Established)(?![\w.-])", re.IGNORECASE
)
_PROVENANCE_WINDOW = 10

#: Italic-form dated provenance tag: `*2026-06-26, project-rag*` or
#: `*project-rag, 2026-06-26*` -- a bare ISO date and a trailing/leading
#: attribution joined by a comma, inside a single `*...*` span. The
#: `[.,;:]?` before the closing `*` tolerates a sentence-final period inside
#: the italics (`*Source: claude-central L10, 2026-05-30.*`) -- without it,
#: the trailing period sat between the date and the closing delimiter and
#: the match failed outright.
_ITALIC_PROVENANCE = re.compile(
    r"\*\s*(?:\d{4}-\d{2}-\d{2}\s*,\s*[^*\n]+?|[^*\n]+?,\s*\d{4}-\d{2}-\d{2})[.,;:]?\s*\*"
)

#: A cue immediately before a bare date token that names an OPERATIVE
#: THRESHOLD the rule gates on now ("Pre-2026-05-22 memos...", "before
#: 2026-08-01, X applies", "as of 2026-08-01") rather than a historical
#: event -- see `_bare_dated_parenthetical_hit`.
_THRESHOLD_CUE = re.compile(r"(?i)\b(pre|before|since|as\s+of)[\s-]*$")

_PAREN_SPAN = re.compile(r"\(([^()]*)\)")
_ITALIC_SPAN = re.compile(r"\*([^*\n]*)\*")


def _is_paragraph_leading(line: str, start: int) -> bool:
    """True if nothing but whitespace/list/blockquote/bold markup precedes
    `start` on `line` -- the same leading-decoration set `_dequote_leading`
    strips, checked inline so callers don't need a second dequoted copy of
    the line just to answer this."""
    prefix = line[:start]
    return prefix.strip(" \t>*_-") == ""


def _date_token_positions(line: str) -> "list[tuple[int, int]]":
    """Char spans of tokens that, after stripping surrounding punctuation,
    are EXACTLY an ISO date and carry no `/` — the path/filename exclusion
    described in the module docstring."""
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
    # char_pos falls between tokens (shouldn't normally happen for a match
    # start) -- fall back to the nearest token before it.
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
    """All violations on a single already-frontmatter/fence-filtered line."""
    violations: list = []
    for pattern in _EXEMPT_LINE_PATTERNS:
        if pattern.match(line):
            return []

    fingerprint = " ".join(line.split())
    if not fingerprint:
        return []

    all_token_spans = [(m.start(), m.end()) for m in _TOKEN.finditer(line)]
    date_spans = _date_token_positions(line)
    verb_matches = list(_HISTORY_VERB.finditer(line))

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
                # A leading "Origin:" construction is narration to rewrite
                # wholesale (see the header rule above), not a tag to trim --
                # stays exclusively in that bucket.
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

    if _ITALIC_PROVENANCE.search(line):
        violations.append(
            Violation(
                line_no,
                "dated provenance tag (italic attribution)",
                _excerpt(line),
                fingerprint,
                "high",
            )
        )

    if _DR_CHAIN.search(line) or _SUPERSEDED_DATE.search(line):
        # Avoid double-counting a line already caught by verb_date_hit for
        # the same underlying "superseded <date>" text.
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

    if not violations and date_spans and _bare_dated_parenthetical_hit(line, date_spans):
        violations.append(
            Violation(
                line_no,
                "bare dated parenthetical (no verb, no provenance keyword)",
                _excerpt(line),
                fingerprint,
                "high",
            )
        )

    return violations


def _iter_markdown_violations(text: str) -> "list[Violation]":
    lines = text.split("\n")
    violations: list = []
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

        violations.extend(_scan_text_line(line, line_no))

    return violations


def _iter_schema_json_violations(text: str) -> "list[Violation]":
    """Walk a `*.schema.json` document, scanning only `description`/`$comment`
    string values (see module docstring for why `x-bump-note`/`x-bump-class`
    are excluded by construction). `line_no` here is a sequence index over
    the traversal order (stable for a given document), NOT a real file line
    number -- JSON has no natural per-value line, and the traversal order is
    deterministic for identity-key purposes.

    Fails open (returns `[]`) on any parse failure -- an unparseable schema
    is not this module's problem to diagnose."""
    try:
        data = json.loads(text)
    except Exception:
        return []

    violations: list = []
    seq = 0

    def _walk(node):
        nonlocal seq
        if isinstance(node, dict):
            for key, value in node.items():
                if key in _SCHEMA_PROSE_KEYS and isinstance(value, str):
                    seq += 1
                    for candidate_line in value.split("\n"):
                        violations.extend(_scan_text_line(candidate_line, seq))
                else:
                    _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(data)
    return violations


def iter_violations(text: str, *, is_json: bool = False) -> "list[Violation]":
    """Every changelog-prose violation in `text`, in traversal order.

    `is_json` selects the schema-file walk over the markdown line-scan; the
    caller (which already knows the file's path/extension) decides. Pure
    function over already-loaded text, same shape as its `_prompt_surface_
    citations.py` sibling -- the caller decides whether that text is a whole
    file (the ratchet test) or a reconstructed before/after (the hook, via
    `new_violations`)."""
    if is_json:
        return _iter_schema_json_violations(text)
    return _iter_markdown_violations(text)


def _violation_key(v: Violation) -> tuple:
    """Identity for before/after delta comparison -- kind + confidence + the
    full normalized text, deliberately not line number (line-shift safety,
    same reasoning as the sibling module's `_violation_key`)."""
    return (v.kind, v.confidence, v.line_fingerprint)


def new_violations(before: str, after: str, *, is_json: bool = False) -> "list[Violation]":
    """Violations present in `after` that were NOT already present in
    `before`, as a multiset difference -- see `_prompt_surface_citations.
    new_violations` for the full "why this makes an advisory safe against
    legacy debt" reasoning; identical shape here."""
    before_counts = Counter(_violation_key(v) for v in iter_violations(before, is_json=is_json))
    after_violations = iter_violations(after, is_json=is_json)
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
