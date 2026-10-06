"""Resolve, extract, render, digest and trace a plan's PM brief -- the verbatim words behind it.

WHY THIS EXISTS. Measured across 32 installed-arm coordinator runs (dbc-oduffy/experiments PR
#10), a distinctive line from the PM's own brief reached exactly one executor prompt. Executors
and code reviewers act on the plan's title, exit criterion, a truncated problem excerpt, and their
own spine row -- never the PM's words, because nothing carries them. This module is the one home
for that text: it resolves which source holds it, extracts it, renders it for an audience, digests
it so a report can prove it was read, and checks whether a spine row's `traces_to_brief` actually
quotes it.

RESOLUTION CHAIN, first hit wins:
1. the plan's own `## PM brief` body section;
2. the plan's `execution_authorized_note` frontmatter field;
3. a baton handoff -- `predecessor_handoff` first, then the plan's `deliverable_id` matched
   against `state/handoffs/*.md`, then `archive/handoffs/**/*.md`, state tier before archive
   tier. More than one match within a single tier is unresolvable -- this never guesses between
   two live candidates;
4. nothing: `NoPmBriefError`, naming all three sources checked and the remedy.

The baton-tier precedence (state before archive, ambiguous-within-a-tier refuses) mirrors
`emit-dispatch-workflow.py :: _resolve_baton_cell_to_path`, which resolves a `## Baton
disposition` table cell instead of a plan's `deliverable_id` -- a different lookup key over the
same two directories, so the rule is mirrored here rather than imported: importing the hyphenated
script from this module would invert C4's own import direction (emit-dispatch-workflow.py imports
this module, never the reverse).

NEGATIVE SPEC. `pm_brief` (frontmatter) records ONLY where the words came from (`source`, `ref`);
the words themselves live in the plan body's `## PM brief` section and nowhere else -- one home
for the text, never a frontmatter copy that can drift from it. This is also not
`execution_authorized_note` (why execution was stamped) and not a sizing object's `intent` (what
the lobby routed on): those are different questions, answered elsewhere, never conflated here.

Pure module: no subprocess, no engine import, no network. Reads plan and handoff bytes as UTF-8
and normalises CRLF before any section extraction, so a CRLF checkout and an LF checkout of the
same plan produce identical brief text and an identical `pm-brief-sha` digest.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

SOURCE_PM_VERBATIM = "pm-verbatim"
SOURCE_EXECUTION_UTTERANCE = "execution-utterance"
SOURCE_BATON_ORIGINATING_ASK = "baton-originating-ask"

_PM_BRIEF_HEADING_RE = re.compile(r"^##\s+PM brief\s*$", re.M)
_ANY_HEADING_RE = re.compile(r"^#{1,6}\s+\S", re.M)
_WHAT_THIS_COVERS_RE = re.compile(r"^##\s+What this covers\s*$", re.M)
_SUMMARY_LINE_RE = re.compile(r"^summary:\s*(.+)$", re.M)
_BLOCKQUOTE_PREFIX_RE = re.compile(r"^>\s?", re.M)

_EXECUTOR_FRAMING = (
    "The spine row is your contract; this is the PM intent it serves. Do not widen scope to it, "
    "but do not violate it."
)
_REVIEWER_FRAMING = (
    "Judge this diff against the PM's ask as well as the plan. Scope beyond it and violations of "
    "it are findings."
)


class NoPmBriefError(Exception):
    """Raised when none of the three PM-brief sources resolve.

    The message names all three sources checked and the remedy, per the resolution chain's
    fourth step -- this is a loud refusal, never an empty brief.
    """


@dataclass(frozen=True)
class Brief:
    text: str
    source: str
    ref: Optional[str]


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _strip_blockquote(text: str) -> str:
    return _BLOCKQUOTE_PREFIX_RE.sub("", text)


def _read_frontmatter(text: str) -> dict:
    """Best-effort YAML frontmatter read; `{}` on anything not a clean `---` block."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    try:
        data = yaml.safe_load(text[3:end])
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def extract_brief_section(plan_text: str) -> Optional[str]:
    """The body under `## PM brief`, up to the next heading of any level.

    CRLF is normalised first. Blockquote markers (`> `) are stripped from each line, and the
    result is stripped of leading/trailing blank lines. `None` when no `## PM brief` heading is
    present.
    """
    text = _normalize(plan_text)
    m = _PM_BRIEF_HEADING_RE.search(text)
    if not m:
        return None
    rest = text[m.end():]
    next_heading = _ANY_HEADING_RE.search(rest)
    body = rest[: next_heading.start()] if next_heading else rest
    body = _strip_blockquote(body)
    return body.strip("\n").strip() or None


def _extract_what_this_covers(handoff_text: str) -> Optional[str]:
    text = _normalize(handoff_text)
    m = _WHAT_THIS_COVERS_RE.search(text)
    if not m:
        return None
    rest = text[m.end():]
    next_heading = _ANY_HEADING_RE.search(rest)
    body = rest[: next_heading.start()] if next_heading else rest
    return body.strip("\n").strip() or None


def _baton_text(handoff_path: Path) -> Optional[str]:
    """A baton's carried brief: its `summary:` line, a blank line, then `## What this covers`."""
    try:
        raw = handoff_path.read_text(encoding="utf-8")
    except OSError:
        return None
    text = _normalize(raw)
    fm = _read_frontmatter(text)
    summary = fm.get("summary") if isinstance(fm, dict) else None
    if not isinstance(summary, str) or not summary.strip():
        m = _SUMMARY_LINE_RE.search(text)
        summary = m.group(1).strip().strip("\"'").strip() if m else None
    covers = _extract_what_this_covers(text)
    parts = [p for p in (summary, covers) if p]
    if not parts:
        return None
    return "\n\n".join(parts)


def _read_deliverable_id(path: Path) -> Optional[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    fm = _read_frontmatter(_normalize(text))
    value = fm.get("deliverable_id")
    return value if isinstance(value, str) and value else None


def _resolve_baton_by_deliverable_id(deliverable_id: str, repo_root: Path) -> Optional[Path]:
    """Match `deliverable_id` against `state/handoffs/*.md`, then `archive/handoffs/**/*.md`.

    State tier is searched before archive tier. More than one match within a single tier is
    unresolvable -- this does not guess between two live candidates, and a resolved state-tier
    match is never overridden by an archive-tier one.
    """
    state_dir = repo_root / "state" / "handoffs"
    if state_dir.is_dir():
        state_matches = [
            p for p in sorted(state_dir.glob("*.md"))
            if _read_deliverable_id(p) == deliverable_id
        ]
        if len(state_matches) == 1:
            return state_matches[0]
        if len(state_matches) > 1:
            return None

    archive_dir = repo_root / "archive" / "handoffs"
    if archive_dir.is_dir():
        archive_matches = [
            p for p in sorted(archive_dir.rglob("*.md"))
            if _read_deliverable_id(p) == deliverable_id
        ]
        if len(archive_matches) == 1:
            return archive_matches[0]
    return None


def resolve(plan_path: Path, repo_root: Path) -> Brief:
    """Walk the four-step resolution chain and return the first hit.

    Raises `NoPmBriefError` naming all three sources checked and the remedy when nothing
    resolves.
    """
    plan_path = Path(plan_path)
    repo_root = Path(repo_root)
    plan_text = _normalize(plan_path.read_text(encoding="utf-8"))
    fm = _read_frontmatter(plan_text)

    section = extract_brief_section(plan_text)
    if section:
        ref = None
        pm_brief_fm = fm.get("pm_brief") if isinstance(fm, dict) else None
        if isinstance(pm_brief_fm, dict) and isinstance(pm_brief_fm.get("ref"), str):
            ref = pm_brief_fm["ref"]
        return Brief(text=section, source=SOURCE_PM_VERBATIM, ref=ref)

    note = fm.get("execution_authorized_note") if isinstance(fm, dict) else None
    if isinstance(note, str) and note.strip():
        return Brief(text=note.strip(), source=SOURCE_EXECUTION_UTTERANCE, ref=None)

    predecessor = fm.get("predecessor_handoff") if isinstance(fm, dict) else None
    handoff_path: Optional[Path] = None
    if isinstance(predecessor, str) and predecessor.strip():
        candidate = repo_root / predecessor.strip()
        if candidate.is_file():
            handoff_path = candidate

    if handoff_path is None:
        deliverable_id = fm.get("deliverable_id") if isinstance(fm, dict) else None
        if isinstance(deliverable_id, str) and deliverable_id.strip():
            handoff_path = _resolve_baton_by_deliverable_id(deliverable_id.strip(), repo_root)

    if handoff_path is not None:
        baton_text = _baton_text(handoff_path)
        if baton_text:
            try:
                ref = handoff_path.resolve().relative_to(repo_root.resolve()).as_posix()
            except ValueError:
                ref = handoff_path.as_posix()
            return Brief(text=baton_text, source=SOURCE_BATON_ORIGINATING_ASK, ref=ref)

    raise NoPmBriefError(
        f"no PM brief resolves for {plan_path}: checked (1) a `## PM brief` body section, "
        "(2) the `execution_authorized_note` frontmatter field, (3) a baton via "
        "`predecessor_handoff` or `deliverable_id` matched against state/handoffs/*.md then "
        "archive/handoffs/**/*.md. Remedy: re-stamp with --utterance \"<PM's words>\" or add a "
        "`## PM brief` section."
    )


def digest(brief: Brief) -> str:
    """First 8 hex characters of sha256 over the brief text, post-normalisation.

    Taken after CRLF-normalisation and blockquote-marker stripping, never over raw on-disk
    bytes, so a CRLF checkout and an LF checkout of the same plan produce the same
    `pm-brief-sha`.
    """
    return hashlib.sha256(brief.text.encode("utf-8")).hexdigest()[:8]


def render_block(brief: Brief, audience: str) -> str:
    """Render the `## PM intent (verbatim)` block for `audience` ("executor" or "reviewer")."""
    if audience not in ("executor", "reviewer"):
        raise ValueError(f"audience must be 'executor' or 'reviewer', got {audience!r}")
    framing = _EXECUTOR_FRAMING if audience == "executor" else _REVIEWER_FRAMING
    sha = digest(brief)
    ref_display = brief.ref if brief.ref else "null"
    return (
        "## PM intent (verbatim)\n\n"
        f"pm-brief-sha: {sha}\n\n"
        f"{framing}\n\n"
        f"{brief.text}\n\n"
        f"Source: {brief.source} ({ref_display})\n"
    )


def _collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def trace_ok(trace: Optional[str], brief_text: str) -> bool:
    """True when `trace` is non-empty and its whitespace-collapsed form is a substring of the
    whitespace-collapsed brief text."""
    if not trace or not trace.strip():
        return False
    return _collapse_whitespace(trace) in _collapse_whitespace(brief_text)
