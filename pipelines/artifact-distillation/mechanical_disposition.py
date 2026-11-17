"""Model-free fate rule for distill manifest rows; stdlib only, deterministic.

`dispose(rows)` takes rows shaped {path, cohort, reason} plus optional `text` (a nugget, memo or file
body) and returns one `Disposition(fate, rule)` per row, same order. Fates:

  captured    the source hash is already recorded as harvested; nothing left to extract
  superseded  the text itself says it is superseded or closed
  archive     a completion record the pipeline never cited; stays archived, no extraction
  drop        below the admission bar, a one-off acknowledgement, or text with no durable section
  agent       a judgment call; the only fate that costs a model

Rules run in order and the first that claims a row decides it. `agent` is the fail-safe: plans and
specs not already captured by hash (minus their sampled-fact-free sections), any text with a durable section, and any text-free row no
settle-rule claims. A durable fact outranks every settle rule except already-captured (a recorded
hash leaves nothing to extract). Paths are POSIX-normalised strings.

Section level: `split_sections` cuts a body into frontmatter-free sections (`##`/`###` headings, plus
top-level bullet runs and prose before the first heading); `durable_sections` keeps the ones that
carry a durable fact; `agent_items` is the queue payload for a file, durable sections only, each with
path and heading. A file settles mechanically iff it has no durable section.

Plans and specs are filtered by heading class, not by the durable-fact regex: `plan_spec_agent_items`
sends every section except those whose class has a recorded 0/20 durable-fact sample (the
`_PLAN_MECHANICAL_HEADINGS`, `_FRONTMATTER_META_KEYS` and `_TASK_ROW_META_KEYS` tables); an unlisted
class goes to the agent.

`pointer_entries` / `pointer_index` build the model-free pointer index: one {path, heading, start_line,
end_line, tag} entry per section and non-metadata frontmatter block, whatever the fate rules or markers decide,
so any fact the detectors or the plan filter keep from the agent stays findable; the tag names the marker
that fired, or `section` when none did.

`python mechanical_disposition.py input.json [repo_root] [--pointer-index OUT.jsonl]` measures the rule over a distill manifest
with every row's file text loaded, for the v1 and v2 marker sets.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Callable, Dict, Iterable, List, NamedTuple, Optional, Set, Tuple

FATES = ("captured", "superseded", "archive", "drop", "agent")
AGENT = "agent"

_PLAN_SPEC_PREFIXES = ("docs/plans/", "archive/specs/")

# v1: the first-cut regex; bare must/never/fleet/because match, so it over-routes. Kept for the recall comparison.
_DURABLE_MARKERS_V1 = re.compile(
    r"""\broot[ -]cause\b|\bcause:|\bdecid(?:e|ed|es|ing)\b|\bdecision\b|\bruling\b|\bruled\b
    |\brevers(?:e|ed|es|al)\b|\boverrul|\boverrid|\bsupersedes\b|\bDR-\d+|\bmust\b|\bnever\b
    |\binvariant\b|\bfail[- ]open\b|\bgotcha\b|\btrap\b|\bbecause\b|\bwrong\b|\bdefect\b|\bbug\b
    |\bexit(?:\s+code)?\s*[0-9]\b|\|\s*exit\s*\||\bstdout\b|\bstderr\b|\bcontract (?:table|is|says)\b
    |\bpersists?\b|\bfleet\b|\bregress""",
    re.IGNORECASE | re.VERBOSE,
)

# v2 strong regex: a durable fact is a root cause, a decision/ruling/reversal of a prior, a stable contract
# (exit-code/stdout/schema table, CLI signature), or a DR-n citation stating a rule. A bare modal
# (must/never/should) or a bare topic word (fleet, bug, because) alone never matches.
_DURABLE_MARKERS = re.compile(
    r"""
      \broot[ -]cause\b
    | (?:^|[.!?]\s+|\n|\*\*)\s*cause\s*:
    | \bthe\s+(?:defect|bug|failure|regression)\s+(?:is|was)\b
    | \b(?:caused|triggered)\s+by\b
    | \b(?:decision|ruling)\s*(?::|is\b|was\b|=)
    | \bdecision\s+to\b
    | \b(?:PM|G-EM|EM|reviewer)\s+ruling\b
    | \bruling\s+that\b
    | \b(?:decided|ruled)\s+(?:to|that|on)\b
    | \b(?:we|PM|G-EM|EM|reviewer)\s+(?:decided|ruled|chose)\b
    | \b(?:revers(?:es|ed|ing|e)|overrul(?:es|ed|ing|e)|overrid(?:es|ing|den)|supersed(?:es|ed|ing))\s+
        (?:the\s+|a\s+|its\s+|that\s+)?(?:prior|earlier|previous|former|old|ruling|decision|DR-\d+)
    | \b(?:prior|earlier|previous)\s+(?:ruling|decision)\s+(?:is|was|stands|reversed|overruled)\b
    | \|\s*exit(?:\s+code)?\s*\|
    | \bexit(?:\s+code)?\s*[0-9]\s*(?:=|:|means\b|when\b|on\b|if\b|always\b|only\b)
    | \bexits?\s+(?:code\s+)?[0-9]\s+(?:when|on|if|means|always|only)\b
    | \b(?:stdout|stderr)\s*(?:is\b|carries\b|:)
    | \b(?:turned\s+out|proved\s+(?:false|wrong)|falsified|misdiagnos\w+|root-caused)\b
    | \b(?:revert(?:ed|s)?|retract(?:ed|s)?|reinstat\w+)\b
    | \bno\s+such\s+[\w-]+(?:\s+[\w-]+)?\s+(?:exists?|ceiling|key|field)\b
    | \b(?:does|did|do)\s+not\s+exist\b
    | \bwas\s+\W{0,2}(?:inert|dead|vacuous|unenforced)\b
    | \bsilently\s+(?:\w+\s+){0,3}?(?:fail\w*|miss\w*|drop\w*|ignor\w*|discard\w*|return\w*|fork\w*|unenforc\w*|dead|vacuous|skipp?\w*|allow\w*)
    | \b(?:hazard|trap|gotcha)\b
    | \bcontract\s+says\b
    | \bcodif(?:y|ies|ying|ied)\b
    | \bchose\b
    | \b(?:crash|fail|broke|abort|hang|hung|deny|denied|refus)\w*\b[^.\n]{0,150}?\bbecause\b
    | \bratif(?:y|ies|ied)\s+(?:the|as|that)\b
    | \bschema\s+table\b
    | \busage\s*:\s*\S+
    | \b[a-z][\w-]*-(?:cli|invoke)\s+[a-z][\w-]+\s+[<\[]
    | \bno\s+fabrication\b
    | \bowns\s+(?:what|the)\b[^.]{0,80}?\bnever\b
    | \bnot\s+just\s+the\s+symptom\b
    | \bfail-loud\b
    | \bhard-fail\w*
    | \bDR-\d+\b[^.\n]{0,120}?\b(?:rules|ruled|requires|mandates|forbids|prohibits|states|says|asks)\b(?![-\w])
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Weak markers never qualify a section alone, and the bare modals (must, never, should) and topic
# words (fleet) are not weak markers at all: a section is durable on a strong marker, or on at least
# `_WEAK_MIN_TERMS` distinct weak terms (a narrative dense in causal or defect vocabulary carries a
# finding the strong regex cannot name).
_WEAK_MARKERS = re.compile(
    r"""\b(?:because|rather\s+than|instead\s+of|defects?|bugs?|wrong|invariant|fail[- ]open
    |load-bearing|deliberately|regress\w*|persists?|so\s+that|silently|decisions?(?![-\w])|revers\w+
    |retired?|outweigh\w*|supersed\w+|overrid\w+|bypass\w*|unguarded)\b""",
    re.IGNORECASE | re.VERBOSE,
)
_WEAK_MIN_TERMS = 2


class Detector(NamedTuple):
    """A durable-fact detector: a strong regex, plus an optional weak regex needing `min_weak` distinct terms."""

    strong: "re.Pattern[str]"
    weak: Optional["re.Pattern[str]"] = None
    min_weak: int = 0  # distinct weak terms required


DETECTOR_V1 = Detector(_DURABLE_MARKERS_V1)
DETECTOR_V2_STRONG = Detector(_DURABLE_MARKERS)
DETECTOR_V2 = Detector(_DURABLE_MARKERS, _WEAK_MARKERS, _WEAK_MIN_TERMS)


def is_durable(text: str, detector: Detector = DETECTOR_V2) -> bool:
    """True when `text` carries a durable fact under `detector`."""
    if detector.strong.search(text):
        return True
    return bool(detector.weak) and len({w.lower() for w in detector.weak.findall(text)}) >= detector.min_weak


_ACK_LEAD = re.compile(
    r"^(?:[^:\n]{0,60}:\s*)?(?:superseded|noted|agreed|acknowledged|ack|closed|no action|fyi)\b",
    re.IGNORECASE,
)
_SUPERSEDED_WORD = re.compile(r"\b(?:superseded|closed)\b", re.IGNORECASE)
_ACK_MAX_CHARS = 400

_HEADING = re.compile(r"^(#{2,3})\s+(\S.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(?:```|~~~)")
_BULLET = re.compile(r"^(?:[-*+]|\d+[.)])\s+\S")


class Disposition(NamedTuple):
    """One row's fate (a member of FATES) and the name of the rule that decided it."""

    fate: str
    rule: str


class Section(NamedTuple):
    """One slice of a file body: its heading label and its text (heading line included)."""

    heading: str
    text: str


def _norm(path: str) -> str:
    return path.replace("\\", "/").removeprefix("./")


def _frontmatter_parts(text: str) -> tuple:
    """(frontmatter body, remainder, 1-based file line of the remainder's first line); ("", text, 1)
    when no closed `---` block opens the file."""
    lines = text.lstrip("\ufeff").split("\n")
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return "\n".join(lines[1:i]), "\n".join(lines[i + 1 :]), i + 2
    return "", text, 1


def _split_frontmatter(text: str) -> tuple:
    """(frontmatter body, remainder); ("", text) when no closed `---` block opens the file."""
    return _frontmatter_parts(text)[:2]


def _trim_blank(rows: List[tuple]) -> List[tuple]:
    """Drop leading and trailing empty-string lines from (line number, line) pairs."""
    lo, hi = 0, len(rows)
    while lo < hi and rows[lo][1] == "":
        lo += 1
    while hi > lo and rows[hi - 1][1] == "":
        hi -= 1
    return rows[lo:hi]


def _split_top_level(rows: List[tuple]) -> List[tuple]:
    """Cut pre-heading (line number, line) pairs into prose blocks and top-level bullet runs, in order;
    returns (label, [(line number, line)]) pairs."""
    chunks: List[tuple] = []  # (kind, [(n, line)])
    cur_kind: Optional[str] = None
    cur: List[tuple] = []
    in_fence = False
    for n, ln in rows:
        if _FENCE.match(ln):
            in_fence = not in_fence
        if in_fence or not ln.strip():
            kind = cur_kind  # fenced lines and blanks continue the current chunk
        elif _BULLET.match(ln):
            kind = "bullets"
        elif ln[:1] in (" ", "\t") and cur_kind == "bullets":
            kind = "bullets"  # indented continuation of a bullet
        else:
            kind = "preamble"
        if kind != cur_kind and kind is not None:
            if cur:
                chunks.append((cur_kind or "preamble", cur))
            cur_kind, cur = kind, []
        cur.append((n, ln))
    if cur:
        chunks.append((cur_kind or "preamble", cur))
    seen: Counter = Counter()
    out: List[tuple] = []
    for kind, body in chunks:
        body = _trim_blank(body)
        if not "\n".join(ln for _, ln in body).strip():
            continue
        seen[kind] += 1
        label = f"({kind})" if seen[kind] == 1 else f"({kind} {seen[kind]})"
        out.append((label, body))
    return out


class SectionSpan(NamedTuple):
    """A Section plus its 1-based inclusive line span in the original file (frontmatter counted)."""

    heading: str
    text: str
    start: int
    end: int


def split_sections_spans(text: str) -> List[SectionSpan]:
    """`split_sections` with each section's line span in the file `text`."""
    _, body, first = _frontmatter_parts(text)
    head: List[tuple] = []
    blocks: List[tuple] = []  # (heading, [(n, line)])
    in_fence = False
    cur: Optional[tuple] = None
    for n, ln in enumerate(body.split("\n"), start=first):
        if _FENCE.match(ln):
            in_fence = not in_fence
        m = None if in_fence else _HEADING.match(ln)
        if m:
            if cur:
                blocks.append(cur)
            cur = (m.group(2), [(n, ln)])
        elif cur is None:
            head.append((n, ln))
        else:
            cur[1].append((n, ln))
    if cur:
        blocks.append(cur)
    out: List[SectionSpan] = []
    for heading, rows in _split_top_level(head) + blocks:
        rows = _trim_blank(rows)
        out.append(SectionSpan(heading, "\n".join(ln for _, ln in rows), rows[0][0], rows[-1][0]))
    return out


def split_sections(text: str) -> List[Section]:
    """Split a file body into sections: frontmatter stripped; `##`/`###` headings open a section
    (heading line kept in its text); lines before the first heading split into prose and top-level
    bullet runs. Blank-only slices are dropped; heading lines inside code fences do not split."""
    return [Section(s.heading, s.text) for s in split_sections_spans(text)]


def durable_sections(text: str, detector: Optional[Detector] = None) -> List[Section]:
    """Return the sections of `text` that carry a durable fact under `detector`. The default is the
    routing detector, v1 or v2: v2 alone drops v1-durable facts, and the coverage bar is zero-drop."""
    if detector is None:
        return [s for s in split_sections(text)
                if is_durable(s.text, DETECTOR_V1) or is_durable(s.text, DETECTOR_V2)]
    return [s for s in split_sections(text) if is_durable(s.text, detector)]


def agent_items(path: str, text: str, detector: Optional[Detector] = None) -> List[dict]:
    """Return the agent-queue payload for one file: durable sections only, each {path, heading, text}.
    An empty list means the file settles mechanically."""
    p = _norm(path)
    return [{"path": p, "heading": s.heading, "text": s.text} for s in durable_sections(text, detector)]


# Plan/spec section classes proven fact-free by a hand-checked 0/20 sample (delivery doc
# docs/delivery/2026-11/ask-20261116T054351-4af671.md). A class absent from these tables goes to the agent.
_PLAN_MECHANICAL_HEADINGS = frozenset({"width rationale"})
_FRONTMATTER_META_KEYS = frozenset({
    "title", "grouping_approvals", "register_claims", "initiative", "sizing_object", "deliverable_id", "plan_id",
    "branch", "created", "status", "author", "scope_mode", "pm_brief", "approved_body_sha",
    "execution_authorized_sha", "execution_authorized_at",
})
_TASK_ROW_META_KEYS = frozenset({
    "id", "change_kind", "surface", "writes", "writes_under", "reads_at_head", "model", "effort",
    "agent_type", "queue_scope", "disposition", "disposition_ref", "deferred", "register_rows",
})
_TOP_KEY = re.compile(r"^[A-Za-z_][\w-]*(?=:)")
# An approved grouping carries the approver's verbatim words: a ruling, so its block stays with the agent.
_APPROVAL_RECORD = re.compile(r"\bpm_utterance\s*:|\bstatus:\s*approved\b")
_ROW_KEY = re.compile(r"^(?:- |  )([A-Za-z_][\w-]*):")


def heading_class(heading: str) -> str:
    """Normalise a section heading to its class key: markup stripped, lower-cased, leading number dropped."""
    h = re.sub(r"[`*]", "", heading).lower().strip()
    return re.sub(r"^\d+[.)]?\s*", "", h)


def _frontmatter_text(text: str) -> str:
    return _split_frontmatter(text)[0]


def _frontmatter_residue(text: str) -> str:
    """Frontmatter minus machine-metadata key blocks (ids, dates, refs, hashes, template comments). A
    block is a top-level key line plus every line up to the next top-level key."""
    blocks: List[tuple] = []  # (key or None, [lines])
    for ln in _frontmatter_text(text).split("\n"):
        m = _TOP_KEY.match(ln)
        if m or not blocks:
            blocks.append((m.group(0) if m else None, []))
        blocks[-1][1].append(ln)
    kept: List[str] = []
    for key, lines in blocks:
        if key in _FRONTMATTER_META_KEYS and not _APPROVAL_RECORD.search("\n".join(
                ln for ln in lines if not ln.lstrip().startswith("#"))):
            continue
        kept.extend(lines)
    return "\n".join(kept).strip("\n")


def _tasks_residue(section_text: str) -> str:
    """A Tasks section with each plan-tasks row's machine fields (paths, enums, ids) removed; bodies,
    titles, acceptance, gate notes and everything outside the fence stay."""
    out: List[str] = []
    in_tasks = False
    drop = False
    for ln in section_text.split("\n"):
        if not in_tasks:
            if re.match(r"^```\s*yaml\s+plan-tasks\b", ln):
                in_tasks = True
            out.append(ln)
            continue
        if ln.startswith("```"):
            in_tasks = False
            out.append(ln)
            continue
        m = _ROW_KEY.match(ln)
        if m:
            drop = m.group(1) in _TASK_ROW_META_KEYS
        elif ln.strip() and not (ln.startswith("    ") or ln.startswith("  - ")):
            drop = False
        if not drop:
            out.append(ln)
    return "\n".join(out)


def plan_spec_agent_items(path: str, text: str) -> List[dict]:
    """Agent-queue payload for a plan or spec: every section whose heading class lacks a 0/20 sample,
    each {path, heading, text}. Class-mechanical sections and machine-metadata fields are dropped."""
    p = _norm(path)
    items: List[dict] = []
    fm = _frontmatter_residue(text)
    if fm.strip():
        items.append({"path": p, "heading": "(frontmatter)", "text": fm})
    for s in split_sections(text):
        cls = heading_class(s.heading)
        if cls in _PLAN_MECHANICAL_HEADINGS:
            continue
        body = _tasks_residue(s.text) if cls == "tasks" else s.text
        if body.strip():
            items.append({"path": p, "heading": s.heading, "text": body})
    return items


# Pointer index: one entry per durable section, on the broad v1 detector and zero agent tokens. The tag
# is the rule that fired, in priority order; the tag regexes together cover every v1 alternative.
_POINTER_TAGS = (
    ("root cause", re.compile(r"\broot[ -]cause\b|\bcause:", re.IGNORECASE)),
    ("decision", re.compile(r"\bdecid(?:e|ed|es|ing)\b|\bdecision\b|\bcodif|\bchose\b|\bratif\w*|"
                            r"\b(?:I|we)\s+(?:did\s+not|didn't|chose\s+not\s+to)\b", re.IGNORECASE)),
    ("ruling", re.compile(r"\bruling\b|\bruled\b|\badjudicat\w*", re.IGNORECASE)),
    ("reversed prior", re.compile(
        r"\brevers(?:e|ed|es|al)\b|\boverrul|\boverrid|\bsupersed|\brevert|\bretract|\breinstat", re.IGNORECASE)),
    ("DR citation", re.compile(r"\bDR-\d+", re.IGNORECASE)),
    ("contract", re.compile(
        r"\bexit(?:\s+code)?\s*[0-9]\b|\|\s*exit\s*\||\bstdout\b|\bstderr\b|\bcontract (?:table|is|says)\b|\bcontract\s+says\b|\bschema\s+table\b|\busage\s*:",
        re.IGNORECASE)),
    ("trap", re.compile(
        r"\bgotcha\b|\btrap\b|\bhazard\b|\bfail[- ]open\b|\bfail-loud\b|\binvariant\b|\bsilently\b", re.IGNORECASE)),
    ("finding", re.compile(
        r"\bturned\s+out\b|\bproved\s+(?:false|wrong)\b|\bfalsified\b|\bmisdiagnos|\broot-caused\b"
        r"|\bnot\s+just\s+the\s+symptom\b|\b(?:does|did|do)\s+not\s+exist\b|\bno\s+fabrication\b"
        r"|\bwas\s+\W{0,2}(?:inert|dead|vacuous|unenforced)\b|\b(?:crash|broke|hung|refus)\w*"
        r"|\bnothing\b[^.\n]{0,60}\bcan\b|\bnone\b[^.\n]{0,40}\b(?:can|starts?|exists?|works?|reach\w*)\b",
        re.IGNORECASE)),
    ("defect", re.compile(r"\bwrong\b|\bdefect\b|\bbug\b|\bregress", re.IGNORECASE)),
    ("rule", re.compile(r"\bmust\b|\bnever\b|\brefus\w*|\bforbid\w*|\bprohibit\w*|\benum\b|\bconsent\b", re.IGNORECASE)),
    ("rationale", re.compile(r"\bbecause\b", re.IGNORECASE)),
    ("persistence", re.compile(r"\bpersists?\b", re.IGNORECASE)),
    ("fleet", re.compile(r"\bfleet\b", re.IGNORECASE)),
)
_POINTER_TAG_MAX = 3


def pointer_tag(text: str) -> str:
    """One-line rule-derived tag for a durable section: up to three matching tag names, priority order."""
    names = [name for name, rx in _POINTER_TAGS if rx.search(text)]
    return "+".join(names[:_POINTER_TAG_MAX]) or "durable"


def _frontmatter_pointer_blocks(text: str) -> List[tuple]:
    """(key, start line, end line, text) per top-level frontmatter key block outside the machine-metadata
    keys (an approved grouping stays), lines 1-based in the file."""
    fm, _, first = _frontmatter_parts(text)
    if first == 1:
        return []
    blocks: List[list] = []  # [key or None, first line, [lines]]
    for n, ln in enumerate(fm.split("\n"), start=2):
        m = _TOP_KEY.match(ln)
        if m or not blocks:
            blocks.append([m.group(0) if m else None, n, []])
        blocks[-1][2].append(ln)
    out = []
    for key, n, lines in blocks:
        body = "\n".join(lines).strip("\n")
        if key in _FRONTMATTER_META_KEYS and not _APPROVAL_RECORD.search("\n".join(
                ln for ln in lines if not ln.lstrip().startswith("#"))):
            continue
        out.append((key or "?", n, n + len(lines) - 1, body))
    return out


# Negated capability ("nothing on the MCP surface can trigger", "none starts an index", "no tool to ...")
# and a decision stated as a refusal of the obvious path ("I did not put X ... so: Y").
_NEGATED_CAPABILITY = (r"\bnothing\b[^.\n]{0,60}\bcan\b|\bnone\b[^.\n]{0,40}\b(?:can|starts?|exists?|works?|reach\w*)\b"
                       r"|\bno\s+(?:way|tool|path|surface|op|verb|command|caller)\b[^.\n]{0,40}\b(?:to|can|that)\b")
_DID_NOT_DECISION = r"\b(?:I|we)\s+(?:did\s+not|didn't|chose\s+not\s+to)\b|\badjudicat\w*"
_POINTER_ONLY = re.compile(r"\brefus\w*|\bforbid\w*|\bprohibit\w*|\bratif\w*|\benum\b|\bconsent\b|"
                           + _NEGATED_CAPABILITY + "|" + _DID_NOT_DECISION, re.IGNORECASE)


def _pointed(text: str) -> bool:
    """A section earns a pointer when the broad v1 detector, the v2 detector or a pointer-only marker
    (refusal, prohibition, ratification, closed enum, consent) flags it: v1 recall is never narrowed by
    v2, v2's own catches that v1 misses are kept, and an index entry costs no agent tokens."""
    return is_durable(text, DETECTOR_V1) or is_durable(text, DETECTOR_V2) or bool(_POINTER_ONLY.search(text))


def _entry_tag(text: str) -> str:
    """The marker tag for a flagged section; `section` for one no marker flags. The tag is a grep aid only:
    it never gates the entry."""
    return pointer_tag(text) if _pointed(text) else "section"


def pointer_entries(path: str, text: str) -> List[dict]:
    """Pointer index for one file: {path, heading, start_line, end_line, tag} for every non-blank section
    and every non-metadata frontmatter key block, whatever its heading or markers. Coverage is findability
    over the whole backlog, and no marker set predicts which section someone will look for (an "Out of
    scope" bullet carries none). Lines are 1-based and inclusive in the file as stored."""
    p = _norm(path)
    out: List[dict] = []
    for key, start, end, body in _frontmatter_pointer_blocks(text):
        out.append({"path": p, "heading": f"(frontmatter) {key}", "start_line": start,
                    "end_line": end, "tag": _entry_tag(body)})
    for s in split_sections_spans(text):
        out.append({"path": p, "heading": s.heading, "start_line": s.start, "end_line": s.end,
                    "tag": _entry_tag(s.text)})
    return out


_WIDEN_ROOTS = ("archive", "state", "docs/decisions", "docs/wiki", "coordinator/docs/wiki")
_PAGE_PATH = "docs/pointer-index/durable-pointer-index.md"
_WIDEN_SUFFIXES = (".md", ".yaml", ".yml")


def widen_rows(rows: List[dict], repo_root: Path) -> List[dict]:
    """Pointer-only rows for every tracked doc under the archive, state, decision and wiki trees (state/scratch
    and the pointer page excluded) that the scope manifest does not already carry: the deep backlog
    distill.scope never admits still gets pointers, and a fact already homed in a DR or wiki page is
    reachable from the same page."""
    import subprocess
    listed = subprocess.run(["git", "-C", str(repo_root), "ls-files", "-z", "--", *_WIDEN_ROOTS],
                            capture_output=True, text=True, check=True).stdout.split("\0")
    seen = {_norm(r["path"]) for r in rows}
    return [{"path": f, "cohort": "/".join(f.split("/")[:2]), "reason": "pointer-only"}
            for f in sorted(listed)
            if f.endswith(_WIDEN_SUFFIXES) and not f.startswith("state/scratch/") and f != _PAGE_PATH
            and _norm(f) not in seen]


def pointer_index(rows: Iterable[dict], repo_root: Path) -> List[dict]:
    """Pointer entries for every readable manifest row, in row order; the model-free coverage leg, so no
    row's durable section is unfindable for want of an agent read. Already-captured rows are indexed too:
    a capture may itself be this page's citation, and skipping it would drop the pointer that made it."""
    out: List[dict] = []
    for row in rows:
        try:
            text = (repo_root / _norm(row["path"])).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        out.extend(pointer_entries(row["path"], text))
    return out


def _rule_plan_or_spec(row: dict, text: str) -> Optional[Disposition]:
    if not _norm(row.get("path", "")).startswith(_PLAN_SPEC_PREFIXES):
        return None
    if not text.strip():
        return Disposition(AGENT, "plan-or-spec-always-agent")
    if not plan_spec_agent_items(row.get("path", ""), text):
        return Disposition("drop", "plan-or-spec-all-sections-mechanical")
    return Disposition(AGENT, "plan-or-spec-sections-agent")


def _rule_already_captured(row: dict, text: str) -> Optional[Disposition]:
    if row.get("reason") == "already_captured":
        return Disposition("captured", "already-captured-hash")
    return None


def _rule_durable_fact(row: dict, text: str) -> Optional[Disposition]:
    if text and durable_sections(text):
        return Disposition(AGENT, "durable-fact-marker")
    return None


def _rule_ack(row: dict, text: str) -> Optional[Disposition]:
    body = text.strip()
    if not body or len(body) > _ACK_MAX_CHARS or not _ACK_LEAD.match(body):
        return None
    if _SUPERSEDED_WORD.search(body):
        return Disposition("superseded", "ack-superseded-or-closed")
    return Disposition("drop", "ack-noted-no-action")


def _rule_below_admission(row: dict, text: str) -> Optional[Disposition]:
    if row.get("reason") == "below_admission" and row.get("cohort") in ("completed", "memos"):
        return Disposition("drop", "below-admission-record")
    return None


def _rule_uncited_completion(row: dict, text: str) -> Optional[Disposition]:
    if row.get("reason") == "not_log_cited" and _norm(row.get("path", "")).startswith("archive/completed/"):
        return Disposition("archive", "uncited-completion-record")
    return None


def _rule_no_durable_section(row: dict, text: str) -> Optional[Disposition]:
    # Reached only after _rule_durable_fact found nothing, so any text here has no durable section.
    if text.strip():
        return Disposition("drop", "no-durable-section")
    return None


RULES: List[Callable[[dict, str], Optional[Disposition]]] = [
    _rule_already_captured,
    _rule_plan_or_spec,
    _rule_durable_fact,
    _rule_ack,
    _rule_below_admission,
    _rule_uncited_completion,
    _rule_no_durable_section,
]


def dispose_row(row: dict) -> Disposition:
    """Return the fate and deciding rule for one manifest row; unclaimed rows go to agent."""
    text = str(row.get("text") or row.get("nugget") or row.get("body") or "")
    for rule in RULES:
        verdict = rule(row, text)
        if verdict is not None:
            return verdict
    return Disposition(AGENT, "default-agent")


def dispose(rows: Iterable[dict]) -> List[Disposition]:
    """Return one Disposition per row, in input order."""
    return [dispose_row(r) for r in rows]


def tally(dispositions: Iterable[Disposition]) -> Dict[str, int]:
    """Count dispositions by fate, every fate present."""
    counts = Counter(d.fate for d in dispositions)
    return {f: counts.get(f, 0) for f in FATES}


def _manifest_rows(manifest: dict) -> List[dict]:
    """Rows of a distill input.json: `not_admitted` and `deferred` dicts plus `batches` path strings, deduped
    by path. Deferred rows are backlog the slice did not reach; omitting them leaves their facts unpointed."""
    rows: List[dict] = []
    seen = set()
    for r in manifest.get("not_admitted", []):
        rows.append(dict(r))
        seen.add(_norm(r["path"]))
    for r in manifest.get("deferred", []):
        if _norm(r["path"]) not in seen:
            rows.append({"reason": "deferred", **r})
            seen.add(_norm(r["path"]))
    for batch in manifest.get("batches", []):
        for item in batch:
            row = {"path": item} if isinstance(item, str) else dict(item)
            if _norm(row["path"]) not in seen:
                rows.append(row)
                seen.add(_norm(row["path"]))
    return rows


def _measure_with(rows: List[dict], root: Path, detector: Detector) -> dict:
    captured = 0
    plan_rows = plan_chars = unreadable = 0
    files = settled = dur_secs = dur_chars = all_secs = 0
    for row in rows:
        path = _norm(row["path"])
        if row.get("reason") == "already_captured":
            captured += 1
            continue
        try:
            text = (root / path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            unreadable += 1
            continue
        if path.startswith(_PLAN_SPEC_PREFIXES):
            plan_rows += 1
            plan_chars += len(text)
            continue
        files += 1
        secs = split_sections(text)
        all_secs += len(secs)
        durable = [s for s in secs if is_durable(s.text, detector)]
        if durable:
            dur_secs += len(durable)
            dur_chars += sum(len(s.text) for s in durable)
        else:
            settled += 1
    return {
        "non_plan_files": files,
        "non_plan_files_settled": settled,
        "non_plan_files_to_agent": files - settled,
        "sections_total": all_secs,
        "durable_sections": dur_secs,
        "durable_section_chars": dur_chars,
        "plan_or_spec_rows": plan_rows,
        "plan_or_spec_chars": plan_chars,
        "already_captured_rows": captured,
        "unreadable_rows": unreadable,
    }


def _measure_plan_spec(rows: List[dict], root: Path) -> dict:
    """Plan/spec agent-queue chars before (whole file) and after (heading-class filter), with the kept
    chars per heading class."""
    files = before = after = 0
    kept_by_class: Counter = Counter()
    for row in rows:
        path = _norm(row["path"])
        if row.get("reason") == "already_captured" or not path.startswith(_PLAN_SPEC_PREFIXES):
            continue
        try:
            text = (root / path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        files += 1
        before += len(text)
        for item in plan_spec_agent_items(path, text):
            after += len(item["text"])
            kept_by_class[heading_class(item["heading"])] += len(item["text"])
    return {
        "plan_or_spec_files": files,
        "agent_chars_before": before,
        "agent_chars_after": after,
        "kept_chars_by_class": dict(kept_by_class.most_common(12)),
    }


def _measure_pointers(entries: List[dict]) -> dict:
    """Size of a pointer index: entries, files covered, entries by leading tag. Entries cost no agent tokens."""
    tags: Counter = Counter(e["tag"].split("+")[0] for e in entries)
    return {
        "entries": len(entries),
        "files": len({e["path"] for e in entries}),
        "entries_by_leading_tag": dict(tags.most_common()),
    }


def measure(manifest: dict, repo_root: Path, pointer_entries_: Optional[List[dict]] = None) -> dict:
    """Measure the fate rule over a distill manifest with every row's file text loaded from
    `repo_root`: per marker set (v1, v2), files settled, durable sections and their total chars, the
    plan/spec agent-queue chars before and after the heading-class filter, and the v1 pointer index.
    `pointer_entries_` is an index the caller already built: tagging every section is the dominant cost,
    so a pointer pass hands its entries in rather than paying for the index twice. Trap: an incremental pass
    reuses the page's coalesced spans, so its entry count is not comparable with a fresh build's; the
    `spans` field says which one was counted."""
    rows = _manifest_rows(manifest)
    spans = "per-section"
    if pointer_entries_ is None:
        pointer_entries_ = pointer_index(rows, repo_root)
    else:
        paths = {_norm(r["path"]) for r in rows}
        pointer_entries_ = [e for e in pointer_entries_ if e["path"] in paths]
        if any(e["heading"] == "(pointer page)" for e in pointer_entries_):
            spans = "page-coalesced where reused"
    return {
        "rows": len(rows),
        "plan_spec": _measure_plan_spec(rows, repo_root),
        "pointer_index": {**_measure_pointers(pointer_entries_), "spans": spans},
        "v1": _measure_with(rows, repo_root, DETECTOR_V1),
        "v2_strong_only": _measure_with(rows, repo_root, DETECTOR_V2_STRONG),
        "v2": _measure_with(rows, repo_root, DETECTOR_V2),
    }


_PAGE_DIR = re.compile(r"^## @(?P<sha>[0-9a-f]+) (?P<dir>\S*)$")
_PAGE_FILE = re.compile(r"^- `(?P<name>[^`]+)` (?P<spans>.+)$")
_PAGE_SPAN = re.compile(r"^(?P<start>\d+)-(?P<end>\d+) (?P<tag>\S+)$")
_PAGE_HEAD = """# Durable pointer index

Every section the distill pointer pass found in the backlog, one line per file:
`- <file> <start>-<end> <tag>; ...` (file in backticks; spans within 3 lines merged), under a `## @<sha> <directory>` header naming the directory and the
commit the spans were read at. Tags are rule-derived codes: rc root cause, dec decision, rul ruling,
rev reversed prior, dr DR citation, con contract, trap trap, fnd finding, def defect, rule rule,
why rationale, per persistence, flt fleet, dur durable, sec a section no marker flagged. A pointer is coverage: the source may since be archived or deleted, and
`git show <sha>:<directory>/<file> | sed -n '<start>,<end>p'` recovers the section. Grep it by file name,
directory or tag; do not read it whole. Generated by
`coordinator/pipelines/artifact-distillation/mechanical_disposition.py --pointer-page`; never hand-edit.
"""


def read_pointer_page(text: str) -> List[dict]:
    """Entries of a rendered pointer page, one per span; lines that are not entries are ignored."""
    out: List[dict] = []
    sha = directory = None
    for ln in text.splitlines():
        d = _PAGE_DIR.match(ln)
        if d:
            sha, directory = d.group("sha"), d.group("dir")
            continue
        f = _PAGE_FILE.match(ln)
        if not f or sha is None:
            continue
        path = f"{directory}/{f.group('name')}" if directory else f.group("name")
        for part in f.group("spans").split("; "):
            m = _PAGE_SPAN.match(part)
            if m:
                out.append({"path": path, "start_line": int(m.group("start")), "end_line": int(m.group("end")),
                            "tag": m.group("tag"), "sha": sha})
    return out


_TAG_CODES = {"root cause": "rc", "decision": "dec", "ruling": "rul", "reversed prior": "rev", "DR citation": "dr",
              "contract": "con", "trap": "trap", "finding": "fnd", "defect": "def", "rule": "rule",
              "rationale": "why", "persistence": "per", "fleet": "flt", "durable": "dur", "section": "sec"}


def _tag_code(tag: str) -> str:
    return "+".join(_TAG_CODES.get(t, t.replace(" ", "-")) for t in tag.split("+"))


_CODE_NAMES = {code: name for name, code in _TAG_CODES.items()}


def _git_paths(repo_root: Path, *args: str) -> Optional[Set[str]]:
    """NUL-separated path output of a git query, or None when git refuses it."""
    import subprocess
    done = subprocess.run(["git", "-C", str(repo_root), *args], capture_output=True, text=True, encoding="utf-8",
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return None if done.returncode else {p for p in done.stdout.split("\0") if p}


def _changed_since(repo_root: Path, sha: str, untracked: Set[str]) -> Optional[Set[str]]:
    """Paths whose working-tree content may differ from `sha` (committed, staged, unstaged, untracked); None
    when `sha` is not a commit in this repository."""
    if not re.fullmatch(r"[0-9a-f]{4,64}", sha):
        return None
    changed = _git_paths(repo_root, "diff", "--name-only", "-z", "--no-renames", sha, "--")
    return None if changed is None else changed | untracked


def _generator_changed(repo_root: Path, changed: Set[str]) -> bool:
    """True when this script itself is among the changed paths: new rules would index unchanged files differently."""
    try:
        return Path(__file__).resolve().relative_to(repo_root.resolve()).as_posix() in changed
    except ValueError:
        return False


def incremental_pointer_index(rows: Iterable[dict], repo_root: Path, page_text: str) -> Tuple[List[dict], int]:
    """`pointer_index` for `rows`, rereading only files that may differ from the page's recorded sha: a row whose
    path has entries on the page at a sha it has not changed since reuses them (spans as the page coalesced
    them, full tag names, a placeholder heading); every other row is read. Returns (entries, files reread).
    The page merged with the result equals a full rebuild's, as merge_pointer_page replaces entries by path."""
    prior: Dict[str, List[dict]] = {}
    for e in read_pointer_page(page_text):
        prior.setdefault(e["path"], []).append(e)
    untracked = _git_paths(repo_root, "ls-files", "-o", "--exclude-standard", "-z") or set()
    # Generator drift invalidates only the sha groups it postdates: a stale section for a path no run
    # rereads would otherwise force every path's full reread forever.
    changed = {}
    for sha in {es[0]["sha"] for es in prior.values()}:
        c = _changed_since(repo_root, sha, untracked)
        changed[sha] = None if c is None or _generator_changed(repo_root, c) else c
    out: List[dict] = []
    reread = 0
    for row in rows:
        path = _norm(row["path"])
        es = prior.get(path)
        ch = changed.get(es[0]["sha"]) if es else None
        if ch is not None and path not in ch:
            out.extend({"path": path, "heading": "(pointer page)", "start_line": e["start_line"],
                        "end_line": e["end_line"], "tag": "+".join(_CODE_NAMES.get(c, c) for c in e["tag"].split("+"))}
                       for e in es)
            continue
        reread += 1
        out.extend(pointer_index([row], repo_root))
    return out, reread


# Spans this close (the blank lines between sections) coalesce on the page. The page is agent-read and
# token-counted; the per-section .jsonl stays exact. A merged span covers every line its parts did, so a
# fact that resolved through a part still resolves through the merge.
_PAGE_MERGE_GAP = 3
_CODE_ORDER = {c: i for i, c in enumerate(_TAG_CODES.values())}


def _coalesce(spans: List[dict]) -> List[dict]:
    runs: List[dict] = []
    for e in sorted(spans, key=lambda e: e["start_line"]):
        codes = set(_tag_code(e["tag"]).split("+"))
        if runs and e["start_line"] <= runs[-1]["end_line"] + _PAGE_MERGE_GAP:
            runs[-1]["end_line"] = max(runs[-1]["end_line"], e["end_line"])
            runs[-1]["codes"] |= codes
        else:
            runs.append({"start_line": e["start_line"], "end_line": e["end_line"], "codes": codes})
    for r in runs:
        codes = r.pop("codes")
        codes = codes - {"sec"} or codes  # `sec` names a run with no marker at all
        r["tag"] = "+".join(sorted(codes, key=lambda c: (_CODE_ORDER.get(c, len(_CODE_ORDER)), c)))
    return runs


def render_pointer_page(entries: List[dict]) -> str:
    """The page for `entries` (each carrying `sha`): files grouped by (sha, directory), adjacent spans
    coalesced (`_coalesce`), in line order."""
    groups: Dict[tuple, Dict[str, List[dict]]] = {}
    for e in entries:
        directory, _, name = e["path"].rpartition("/")
        groups.setdefault((e["sha"], directory), {}).setdefault(name, []).append(e)
    lines = [_PAGE_HEAD]
    for (sha, directory) in sorted(groups, key=lambda k: (k[1], k[0])):
        lines.append(f"\n## @{sha} {directory}\n")
        for name in sorted(groups[(sha, directory)]):
            spans = _coalesce(groups[(sha, directory)][name])
            body = "; ".join(f"{e['start_line']}-{e['end_line']} {e['tag']}" for e in spans)
            lines.append(f"- `{name}` {body}\n")
    return "".join(lines)


def merge_pointer_page(existing: str, entries: List[dict], sha: str) -> str:
    """Render the tracked pointer page: this run's entries, stamped with `sha`, replace every prior entry for
    the same paths; entries for other paths persist, so a pointer outlives its source file's deletion."""
    fresh = [{**e, "sha": sha} for e in entries]
    paths = {e["path"] for e in fresh}
    kept = [e for e in read_pointer_page(existing) if e["path"] not in paths]
    return render_pointer_page(kept + fresh)


def _take_flag(args: List[str], flag: str) -> Optional[str]:
    if flag not in args:
        return None
    i = args.index(flag)
    if i + 1 >= len(args):
        raise SystemExit(f"usage: {flag} needs a value")
    value = args[i + 1]
    del args[i : i + 2]
    return value


def main(argv: Optional[List[str]] = None) -> int:
    """CLI: `input.json [repo_root] [--pointer-index OUT.jsonl] [--pointer-page PAGE.md --sha SHA] [--widen]`; prints
    the measurement as JSON. --pointer-index writes the run's index one JSON entry per line (scratch, for
    prepare); --pointer-page merges it into the tracked page that makes the pointers findable, each entry
    stamped with SHA (the commit the sections were read at). --widen adds pointer-only rows for every tracked
    archive/ and state/ doc the manifest lacks (widen_rows). repo_root defaults to this file's repository."""
    args = list(sys.argv[1:] if argv is None else argv)
    out_path = _take_flag(args, "--pointer-index")
    page_path = _take_flag(args, "--pointer-page")
    widen = "--widen" in args
    if widen:
        args.remove("--widen")
    sha = _take_flag(args, "--sha")
    if not args or (page_path is None) != (sha is None):
        print("usage: mechanical_disposition.py input.json [repo_root] [--pointer-index OUT.jsonl] "
              "[--pointer-page PAGE.md --sha SHA] [--widen]", file=sys.stderr)
        return 2
    root = Path(args[1]) if len(args) > 1 else Path(__file__).resolve().parents[3]
    manifest = json.loads(Path(args[0]).read_text(encoding="utf-8"))
    if out_path is None and page_path is None:
        print(json.dumps(measure(manifest, root), indent=2))
        return 0
    rows = _manifest_rows(manifest)
    extra = widen_rows(rows, root) if widen else []
    page = Path(page_path) if page_path is not None else None
    existing = page.read_text(encoding="utf-8") if page is not None and page.exists() else ""
    reread = None
    if widen and existing:
        entries, reread = incremental_pointer_index(rows + extra, root, existing)
    else:
        entries = pointer_index(rows + extra, root)
    print(json.dumps(measure(manifest, root, entries), indent=2))
    print(json.dumps({"pointer_pass": {"manifest_rows": len(rows), "widened_rows": len(extra),
                                       "entries": len(entries), "files": len({e["path"] for e in entries}),
                                       **({"reread_files": reread} if reread is not None else {})}}))
    if out_path is not None:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")
    if page is not None:
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(merge_pointer_page(existing, entries, str(sha)), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
