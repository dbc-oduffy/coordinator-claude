"""_claude_md_ledger.py — shared ledger-parsing + admission-predicate module
for the CLAUDE.md admission gate.

Purpose: ONE definition of the admission predicate, read by both enforcement
points named in C7:
  (a) the PreToolUse hook (`check-claude-md-size.py`), fast-path, catches
      Write/Edit/MultiEdit only;
  (b) the repo-level invariant test (`coordinator/tests/
      test_claude_md_ledger_invariant.py`), slow/CI path, catches any write
      path the hook cannot see (subprocess, a future `verify-snippet-sync
      --fix` enrolment, a direct script).

Neither enforcement point defines a rival predicate -- both import from here.

REPOINTED AND WIDENED (C7a, `docs/plans/2026-07-30-boot-doctrine-cut-and-
refill-gate.md` § C7a). The gate used to fire on `~/.claude/CLAUDE.md`
ONLY -- the DERIVED live copy `derive-global-doctrine-live-copy.py` writes
via `shutil.copyfile`, invisible to every PreToolUse hook. Agents author
`global-doctrine/CLAUDE.md`, not the derived copy, so a gate pointed only at
the derived copy was structurally unreachable on the surface agents actually
edit. `GOVERNED_AUTHORING_SURFACES` below now names the TRACKED AUTHORING
surfaces the gate governs by AUDIENCE (every surface on the every-agent-or-
EM boot path), not by filename -- `resolve_governed_surface` still also
recognizes the derived `~/.claude/CLAUDE.md` copy for defense-in-depth, but
that is no longer the only path admission-checked.

Each governed surface resolves to its OWN per-surface classification ledger
via `resolve_ledger_path` -- by explicit override for a surface whose ledger
predates this convention (`global-doctrine/CLAUDE.md` ->
`state/audits/2026-07-27-doctrine-envelope-classification.md`), otherwise by
the `state/audits/<surface-slug>-classification.md` convention, so a newly
governed surface's ledger resolves without a further code change once the
ledger file exists at that conventional path. A governed surface with NO
ledger file yet at its resolved path gets the bootstrap disposition
(`admission_check_for_surface`): growth is refused outright, shrinkage is
always permitted -- so a surface can be cut into compliance before its full
pre-cut content has been classified line-by-line.

Each per-surface ledger MAY additionally carry a "## Watermark" section
(`parse_watermark`) recording the audience-budget RATCHET: a byte ceiling
that may only be raised by an explicit, reasoned edit to that section, never
implicitly by a growing edit slipping under the ceiling one byte at a time,
and never re-derived from git history (a git-derived watermark would silently
re-baseline at whatever the tree happened to be the last time someone looked).
Arming a watermark (writing the section for the first time, post-cut) is
C7b's job, not this chunk's -- this module only builds the machinery C7b
arms.

Spec backlink: docs/plans/2026-07-30-boot-doctrine-cut-and-refill-gate.md § C7a
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

#: The closed disposition enum -- exhaustive, per the ledger's own table.
DISPOSITION_ENUM = frozenset(
    {"FLOOR", "DISCHARGED", "DUPLICATE", "CROSS-FILE", "PATH-SCOPED", "ROTTEN"}
)

#: Heading levels this module tracks -- matches the ledger's own count method
#: (`grep -c '^##'`, i.e. `##` AND `###`, never `#` alone or `####`+).
_HEADING_RE = re.compile(r"^(#{2,3})\s+(.+?)\s*$")

#: A demote-target annotation inside a Reason cell -- an inline code span
#: (backtick-quoted path/artifact name) naming a candidate destination for
#: content currently classified FLOOR. This is a NEW convention this module
#: introduces to make "a named demote target" (C7's own phrase) machine-
#: checkable; it did not previously exist as ledger syntax. See this file's
#: own `admission_check` docstring for why FLOOR (not just the "demoted"
#: dispositions) is the row that must additionally carry one.
_DEMOTE_TARGET_RE = re.compile(r"`([^`]*(?:\.md|/)[^`]*)`")

#: A fenced-code-block delimiter (``` or ~~~, three-or-more of either char,
#: optionally indented). Review: code-reviewer — F3: `_HEADING_RE` has no
#: fence awareness on its own, so a `## `/`### `-prefixed line inside a fence
#: (a shell comment, a markdown-syntax illustration in an example) would
#: otherwise parse as a real heading. `extract_headings`/`split_into_sections`
#: both toggle fence state against this pattern and skip heading-like lines
#: while a fence is open.
_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")


@dataclass(frozen=True)
class LedgerRow:
    heading: str
    byte_count: Optional[int]
    disposition: str
    reason: str


class LedgerError(Exception):
    """Raised on a missing or unparseable ledger -- fail LOUD, never a
    silent admit. Callers must surface `str(exc)` verbatim (it carries
    remediation text) rather than swallowing it."""


class DuplicateHeadingError(LedgerError):
    """Raised when a CLAUDE.md-class file contains two `##`/`###` headings
    with identical text. Review: code-reviewer — F2: `split_into_sections`
    keys its section-body dict on heading text; a duplicate would otherwise
    silently overwrite the first occurrence, which can mask real growth or
    manufacture a false one and let the admission gate validate against the
    wrong section entirely. Subclasses `LedgerError` so existing `except
    LedgerError` call sites (the hook, the CI-path invariant test) catch this
    without a separate clause."""


def _split_table_cells(line: str) -> List[str]:
    # Table cells never contain a literal, unescaped "|" in this ledger
    # (verified at authoring time -- every classification-table row has
    # exactly 6 pipe chars for 5 columns). Strip the leading/trailing empty
    # cells produced by the leading/trailing "|".
    parts = line.split("|")
    return [p.strip() for p in parts[1:-1]]


def parse_ledger(ledger_path: Path) -> List[LedgerRow]:
    """Parse the "## Classification table" section of the ledger at
    `ledger_path` into a list of `LedgerRow`. Raises `LedgerError` (fail
    loud, never a silent admit) if the file is missing, the section is
    absent, or a row fails to parse.
    """
    if not ledger_path.is_file():
        raise LedgerError(
            f"Admission ledger not found at {ledger_path} -- an addition to a "
            f"governed CLAUDE.md cannot be admitted without it. Remediation: "
            f"restore the C2(narrowed) ledger, or classify the target section "
            f"there before retrying this edit."
        )

    try:
        text = ledger_path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        raise LedgerError(f"Admission ledger at {ledger_path} could not be read: {exc}") from exc

    lines = text.splitlines()
    start = None
    end = len(lines)
    for i, line in enumerate(lines):
        if line.strip() == "## Classification table":
            start = i
        elif start is not None and i > start and line.startswith("## "):
            end = i
            break

    if start is None:
        raise LedgerError(
            f"Admission ledger at {ledger_path} has no '## Classification table' "
            f"section -- cannot parse rows. Remediation: restore that heading, "
            f"or point the admission gate at a corrected ledger."
        )

    rows: List[LedgerRow] = []
    for line_no, line in enumerate(lines[start:end], start=start + 1):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = _split_table_cells(stripped)
        if len(cells) != 5:
            # Review: code-reviewer — F4: a malformed row (e.g. a Reason
            # cell embedding an unescaped "|") must fail loud, not silently
            # drop the row -- a dropped row causes over-refusal ("no ledger
            # row") that is indistinguishable from an unclassified heading,
            # which contradicts this module's own "fail LOUD, never silent"
            # framing honored everywhere else in this file.
            raise LedgerError(
                f"Admission ledger at {ledger_path} has a malformed row (line "
                f"{line_no}: {stripped!r}) -- expected exactly 5 cells, found "
                f"{len(cells)}. Remediation: fix the row by hand (check for "
                f"an unescaped '|' in a cell); this parser will not guess."
            )
        num, heading_cell, bytes_cell, disposition_cell, reason_cell = cells
        if num == "#" or set(num) <= {"-"}:
            # header row or separator row
            continue
        heading_match = re.match(r"^`(#{2,3}\s+.+?)`$", heading_cell)
        if not heading_match:
            raise LedgerError(
                f"Admission ledger at {ledger_path} has an unparseable heading "
                f"cell {heading_cell!r} in row {num!r} -- expected a backtick-"
                f"quoted `##`/`###` heading. Remediation: fix the row by hand; "
                f"this parser will not guess."
            )
        heading = heading_match.group(1)
        try:
            byte_count: Optional[int] = int(bytes_cell)
        except ValueError:
            byte_count = None
        rows.append(
            LedgerRow(
                heading=heading,
                byte_count=byte_count,
                disposition=disposition_cell.strip(),
                reason=reason_cell.strip(),
            )
        )

    return rows


def extract_headings(claude_md_text: str) -> List[str]:
    """Return every `##`/`###` heading line (verbatim, minus trailing
    whitespace) in `claude_md_text`, in file order. Heading-like lines
    inside an open ``` or ~~~ fence are skipped -- see `_FENCE_RE`."""
    headings = []
    in_fence = False
    for line in claude_md_text.splitlines():
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _HEADING_RE.match(line)
        if m:
            headings.append(f"{m.group(1)} {m.group(2)}")
    return headings


def split_into_sections(claude_md_text: str) -> "dict[str, str]":
    """Split `claude_md_text` into {heading: section_body_bytes_as_str},
    matching the ledger's own byte-count method: each row's byte count is
    that section's OWN content, from the heading line up to (not including)
    the next `##`/`###` heading -- i.e. nested subsections get their own
    entry, not folded into the parent's count.

    Heading-like lines inside an open ``` or ~~~ fence are treated as
    ordinary body content, not real headings (see `_FENCE_RE`). Raises
    `DuplicateHeadingError` if the same heading text appears twice -- see
    that exception's docstring for why silent overwrite is unsafe here.
    """
    lines = claude_md_text.splitlines(keepends=True)
    sections: "dict[str, str]" = {}
    current_heading: Optional[str] = None
    buf: List[str] = []
    in_fence = False

    def _finalize(heading: str, body: List[str]) -> None:
        if heading in sections:
            raise DuplicateHeadingError(
                f"Heading {heading!r} appears more than once -- the "
                f"admission gate's section diff keys on heading text and "
                f"cannot safely fold two same-named sections into one "
                f"entry. Rename one of the duplicate headings."
            )
        sections[heading] = "".join(body)

    for line in lines:
        stripped_line = line.rstrip("\n")
        if _FENCE_RE.match(stripped_line):
            in_fence = not in_fence
            if current_heading is not None:
                buf.append(line)
            continue
        m = None if in_fence else _HEADING_RE.match(stripped_line)
        if m:
            if current_heading is not None:
                _finalize(current_heading, buf)
            current_heading = f"{m.group(1)} {m.group(2)}"
            buf = [line]
        else:
            if current_heading is not None:
                buf.append(line)
    if current_heading is not None:
        _finalize(current_heading, buf)
    return sections


def has_named_demote_target(reason: str) -> bool:
    """True iff `reason` names a candidate demote target -- an inline-code
    reference to another artifact (a wiki, a snippet, a sibling file) the
    content could move to. See module docstring for why this convention
    exists and why FLOOR rows are the ones required to carry it."""
    return bool(_DEMOTE_TARGET_RE.search(reason))


def admission_check(
    old_content: str,
    new_content: str,
    ledger_rows: List[LedgerRow],
) -> "tuple[bool, str]":
    """The admission predicate: for every heading section that GREW (or is
    newly introduced) between `old_content` and `new_content`, a ledger row
    for that heading must (a) pre-exist with a non-empty disposition from
    the closed enum, and (b) if that disposition is FLOOR, additionally name
    a demote target in its Reason cell.

    Why FLOOR (not the "demoted" dispositions) is the one that must ALSO
    carry a demote target: FLOOR is the disposition an author could reach
    for reflexively to avoid ever having to move anything -- "no artifact
    can discharge it" is exactly the claim a bloat-refill would want to make
    for every new paragraph. Requiring even a FLOOR row to name a fallback
    destination forces the ledger author to have actually considered
    discharge before asserting FLOOR, which is the whole point of this gate
    (five prior trims refilled because nothing ever asked WHY an addition
    belonged). The other five dispositions (DISCHARGED/DUPLICATE/CROSS-FILE/
    PATH-SCOPED/ROTTEN) already name their destination by construction --
    DISCHARGED names the discharging artifact, CROSS-FILE the assigned home,
    etc. -- so this module does not additionally gate them on the same
    regex; a non-empty Reason is enough for those five.

    Returns (allowed, message). `message` is populated on refusal with the
    offer-shaped decoration C7 requires: current cost, why it was refused,
    and the better home (if the ledger names one) or the concrete next step
    (classify the row) if it does not.
    """
    old_sections = split_into_sections(old_content)
    new_sections = split_into_sections(new_content)
    ledger_by_heading = {row.heading: row for row in ledger_rows}

    grown_or_new: List[str] = []
    for heading, new_body in new_sections.items():
        old_body = old_sections.get(heading, "")
        if len(new_body.encode("utf-8")) > len(old_body.encode("utf-8")):
            grown_or_new.append(heading)

    for heading in grown_or_new:
        row = ledger_by_heading.get(heading)
        if row is None or not row.disposition:
            return False, (
                f"Refused: {heading!r} grew, but no ledger row (or an empty "
                f"disposition) exists for it in the C2(narrowed) admission "
                f"ledger. Classify the section there first -- name a "
                f"disposition from {sorted(DISPOSITION_ENUM)} and a reason -- "
                f"before this addition can be admitted."
            )
        if row.disposition not in DISPOSITION_ENUM:
            return False, (
                f"Refused: {heading!r}'s ledger row names disposition "
                f"{row.disposition!r}, which is not in the closed enum "
                f"{sorted(DISPOSITION_ENUM)}. Fix the ledger row."
            )
        if row.disposition == "FLOOR" and not has_named_demote_target(row.reason):
            return False, (
                f"Refused: {heading!r} is classified FLOOR but its ledger "
                f"row names no demote target (an inline-code reference to "
                f"where overflow content could go). Even a FLOOR row must "
                f"name a considered fallback home before it can absorb more "
                f"content -- add one to the Reason cell in "
                f"state/audits/2026-07-27-doctrine-envelope-classification.md."
            )

    return True, ""


# ---------------------------------------------------------------------------
# C7a — audience-governed surface set, per-surface ledger resolution, and the
# ratchet watermark. See module docstring "REPOINTED AND WIDENED" for why
# these exist and how they compose with `admission_check` above.
# ---------------------------------------------------------------------------

#: The audience-governed AUTHORING surfaces (C7a's "THREE MOVES" #2,
#: `docs/plans/2026-07-30-boot-doctrine-cut-and-refill-gate.md` § C7a) --
#: enumerated explicitly, repo-root-relative, POSIX-separated. Governed by
#: WHO must not do the wrong thing without this content (every agent, or the
#: EM), not by which file happens to be named `CLAUDE.md`. Adding a new
#: every-agent-or-EM boot surface to this tuple is the one code change this
#: module still requires (AC3's "enumerated explicitly"); its LEDGER PATH
#: then resolves by convention with no further code change (see
#: `resolve_ledger_path`).
GOVERNED_AUTHORING_SURFACES = (
    "global-doctrine/CLAUDE.md",
    "CLAUDE.md",
    "coordinator/snippets/em-operating-doctrine.md",
    "coordinator/snippets/agent-role-dispatched.md",
)

#: Explicit ledger-path overrides for a governed surface whose classification
#: ledger predates the `state/audits/<surface-slug>-classification.md`
#: convention this module introduces. Every OTHER governed surface resolves
#: its ledger purely by convention -- see `resolve_ledger_path`.
_LEDGER_PATH_OVERRIDES = {
    "global-doctrine/CLAUDE.md": "state/audits/2026-07-27-doctrine-envelope-classification.md",
}

#: Offer-shaped fallback demote-target text appended to any refusal message
#: that does not already name one -- C7a requires every refusal to name a
#: demote target, not merely refuse (an offer, not a nag). Points at the
#: channel-purpose contract that is the routing authority for where content
#: should go instead.
_DEFAULT_DEMOTE_TARGET_HINT = (
    "Demote target: route non-conduct, reference, or rationale content to "
    "the wiki/decision-record channel (coordinator/docs/wiki/, channel 5) "
    "per coordinator/docs/wiki/doctrine-channel-purposes.md, unless it "
    "genuinely governs every agent's (or the EM's) conduct."
)


def surface_slug(surface: str) -> str:
    """`global-doctrine/CLAUDE.md` -> `global-doctrine-claude-md` -- the
    conventional ledger-filename fragment for a governed surface with no
    `_LEDGER_PATH_OVERRIDES` entry. Path separators become hyphens, a
    trailing `.md` is dropped, and the whole slug is lower-cased so a
    surface's ledger path is a pure function of its own path."""
    slug = surface.replace("/", "-")
    if slug.lower().endswith(".md"):
        slug = slug[: -len(".md")]
    return slug.lower()


def resolve_ledger_path(repo_root: Path, surface: str) -> Path:
    """Resolve `surface`'s (repo-root-relative, POSIX-separated) per-surface
    classification ledger path under `repo_root`. An override in
    `_LEDGER_PATH_OVERRIDES` wins; otherwise the path is the
    `state/audits/<surface-slug>-classification.md` convention -- so a newly
    governed surface's ledger resolves the moment the file is authored at
    that path, with no further code change here."""
    override = _LEDGER_PATH_OVERRIDES.get(surface)
    if override:
        return repo_root / Path(override)
    return repo_root / "state" / "audits" / f"{surface_slug(surface)}-classification.md"


def resolve_governed_surface(
    abs_file_path: str, repo_root: Path, home: Optional[Path] = None
) -> Optional[str]:
    """Return the `GOVERNED_AUTHORING_SURFACES` entry `abs_file_path`
    resolves to, or `None` if it is not a governed surface at all.

    Recognizes each tracked authoring surface directly, AND -- for
    defense-in-depth, since `derive-global-doctrine-live-copy.py` writes the
    derived `~/.claude/CLAUDE.md` copy via `shutil.copyfile` with no tool
    call in the path, so no PreToolUse hook ever sees that write on its own
    -- a direct edit to the derived global copy, mapped back onto
    `global-doctrine/CLAUDE.md`'s governance (same ledger, same predicate).
    """
    resolved = Path(abs_file_path).resolve()
    for surface in GOVERNED_AUTHORING_SURFACES:
        if resolved == (repo_root / Path(surface)).resolve():
            return surface

    home_dir = (home or Path.home()).resolve()
    if resolved == (home_dir / ".claude" / "CLAUDE.md").resolve():
        return "global-doctrine/CLAUDE.md"

    return None


@dataclass(frozen=True)
class LedgerWatermark:
    bytes: int
    reason: str


_WATERMARK_HEADING = "## Watermark"
_WATERMARK_BYTES_RE = re.compile(r"^-\s*Bytes:\s*(\d+)\s*$", re.IGNORECASE)
_WATERMARK_REASON_RE = re.compile(r"^-\s*Reason:\s*(.+?)\s*$", re.IGNORECASE)


def parse_watermark(ledger_path: Path) -> Optional[LedgerWatermark]:
    """Parse the ratchet watermark from `ledger_path`'s own "## Watermark"
    section -- persisted IN THE LEDGER, never derived from git history (a
    git-derived watermark would silently re-baseline at whatever the tree
    happened to be, with no reasoned bump on record). Returns `None` when
    the ledger is missing or carries no "## Watermark" section at all --
    the ratchet is simply UNARMED for that surface (arming it is C7b's job,
    not this module's); this is not an error. Raises `LedgerError` when the
    section EXISTS but is malformed (no `- Bytes:` row, or no `- Reason:`
    row) -- an armed-but-broken watermark must fail loud, never silently
    disable the ratchet it claims to enforce.
    """
    if not ledger_path.is_file():
        return None

    text = ledger_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip() == _WATERMARK_HEADING:
            start = i
            break
    if start is None:
        return None

    bytes_val: Optional[int] = None
    reason_val: Optional[str] = None
    for line in lines[start + 1:]:
        if line.startswith("## "):
            break
        stripped = line.strip()
        m = _WATERMARK_BYTES_RE.match(stripped)
        if m:
            bytes_val = int(m.group(1))
            continue
        m2 = _WATERMARK_REASON_RE.match(stripped)
        if m2:
            reason_val = m2.group(1)

    if bytes_val is None:
        raise LedgerError(
            f"Admission ledger at {ledger_path} has a '## Watermark' section "
            f"with no '- Bytes: N' row -- the ratchet cannot be enforced "
            f"against a malformed watermark. Fix the row by hand; this "
            f"parser will not guess."
        )
    if not reason_val:
        raise LedgerError(
            f"Admission ledger at {ledger_path}'s '## Watermark' section has "
            f"no non-empty '- Reason: ...' row -- a watermark bump requires "
            f"a stated reason. Add one before this ledger can arm the ratchet."
        )
    return LedgerWatermark(bytes=bytes_val, reason=reason_val)


def ratchet_check(
    new_content: str, watermark: Optional[LedgerWatermark]
) -> "tuple[bool, str]":
    """The AC4 ratchet predicate: a governed surface may shrink or hold,
    never grow past its recorded watermark, without an explicit reasoned
    bump. `watermark is None` means the ratchet is unarmed for this surface
    (nothing to check yet, per C7b) -- always allowed."""
    if watermark is None:
        return True, ""
    new_size = len(new_content.encode("utf-8"))
    if new_size > watermark.bytes:
        return False, (
            f"Refused: this edit grows the surface to {new_size} bytes, past "
            f"its recorded ratchet watermark of {watermark.bytes} bytes "
            f"(bumped for: {watermark.reason}). The budget only shrinks or "
            f"holds without an explicit, reasoned watermark bump -- raise "
            f"the ledger's '## Watermark' 'Bytes:' row and state a new "
            f"'Reason:' for the bump, or trim the addition back under the "
            f"watermark. {_DEFAULT_DEMOTE_TARGET_HINT}"
        )
    return True, ""


def admission_check_for_surface(
    surface: str, old_content: str, new_content: str, repo_root: Path
) -> "tuple[bool, str]":
    """Per-surface entry point composing (a) the bootstrap disposition for a
    surface with no ledger yet, (b) the per-heading `admission_check`
    predicate once a ledger exists, and (c) the AC4 ratchet watermark, if
    the ledger's armed one. This is what both enforcement points (the
    PreToolUse hook and the slow/CI-path invariant test) should call for a
    `GOVERNED_AUTHORING_SURFACES` entry -- neither should re-derive this
    composition itself.

    Every refusal path names a demote target (directly, or via
    `_DEFAULT_DEMOTE_TARGET_HINT`) -- C7a requires an offer, not a bare nag.
    """
    ledger_path = resolve_ledger_path(repo_root, surface)

    if not ledger_path.is_file():
        old_size = len(old_content.encode("utf-8"))
        new_size = len(new_content.encode("utf-8"))
        if new_size > old_size:
            return False, (
                f"Refused: {surface} has no classification ledger yet "
                f"(bootstrap disposition -- expected at {ledger_path}). "
                f"Growth is blocked until one exists; shrinkage is always "
                f"permitted. {_DEFAULT_DEMOTE_TARGET_HINT}"
            )
        return True, ""

    ledger_rows = parse_ledger(ledger_path)
    allowed, message = admission_check(old_content, new_content, ledger_rows)
    if not allowed:
        if "demote target" not in message.lower():
            message = f"{message} {_DEFAULT_DEMOTE_TARGET_HINT}"
        return False, message

    watermark = parse_watermark(ledger_path)
    return ratchet_check(new_content, watermark)
