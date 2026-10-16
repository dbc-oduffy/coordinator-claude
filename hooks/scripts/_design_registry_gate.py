"""Design-registry intersect check: a plan whose touched files fall under a registered design
entry must cite that entry's harvest record or carry a ratified `design-deviation`.
Contract: coordinator/docs/wiki/schema-and-validation-contracts/design-registry.md.

Stdlib only; reads local files and calls nothing over the network. The write leg
(`guard-canvas-citation-needs-harvest.py`) calls `check(text, repo_root)`.
"""

from __future__ import annotations

import os
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import _canvas_harvest_gate  # noqa: E402
import _message_envelope  # noqa: E402

_LIB_DIR = os.path.normpath(os.path.join(_HERE, "..", "..", "lib"))
if _LIB_DIR not in sys.path:
    sys.path.append(_LIB_DIR)
try:
    from frontmatter_scan import read_text as _read_text  # noqa: E402
    from frontmatter_scan import scan_frontmatter as _scan_frontmatter  # noqa: E402
except ImportError:  # an install shape without coordinator/lib falls back to the default path
    _read_text = None
    _scan_frontmatter = None

SCHEMA_ID = "design-registry/1"
WIKI_ANCHOR = "coordinator/docs/wiki/schema-and-validation-contracts/design-registry.md"
DEFAULT_PATH = "docs/design/registry.yaml"
LOCAL_KEY = "design_registry_path"

_STATUSES = ("designed", "partial", "implemented", "deviated")
_KEY_RE = re.compile(r"^([A-Za-z0-9_\-]+):(?:[ \t]+(.*))?$")
_FENCE_OPEN_RE = re.compile(r"^\s*```+\s*ya?ml\s+([\w\-]+)\s*$")
_BLOCK_SCALAR_RE = re.compile(r"^[|>][+\-0-9]*$")
_WRITE_KEY_RE = re.compile(r"^(\s*)(-\s+)?(writes|writes_under):[ \t]*(.*)$")
_KEY_LINE_RE = re.compile(r"^(\s*)(-\s+)?[A-Za-z0-9_\-]+:[ \t]*(.*)$")

_UNPARSEABLE = "registry-unparseable"


class Refusal(NamedTuple):
    entry: str
    code: str
    message: str


class _SubsetError(ValueError):
    pass


# ---- scalars -------------------------------------------------------------


def _strip_comment(value: str) -> str:
    quote = ""
    for i, ch in enumerate(value):
        if quote:
            if ch == quote:
                quote = ""
        elif ch in ("'", '"'):
            quote = ch
        elif ch == "#" and (i == 0 or value[i - 1] in " \t"):
            return value[:i]
    return value


def _split_flow(body: str) -> list:
    items: list = []
    cur: list = []
    quote = ""
    for ch in body:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = ""
        elif ch in ("'", '"'):
            quote = ch
            cur.append(ch)
        elif ch == ",":
            items.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    items.append("".join(cur))
    return [i.strip() for i in items if i.strip()]


def _scalar(raw: str):
    """One subset scalar: quoted, plain or `null`. Raises _SubsetError outside the subset."""
    value = _strip_comment(raw).strip()
    if not value:
        return ""
    if value[0] in ("'", '"'):
        close = value.find(value[0], 1)
        if close == -1 or value[close + 1 :].strip():
            raise _SubsetError("unterminated or trailing-text quoted scalar")
        return value[1:close]
    if value[0] in "&*!%@`" or _BLOCK_SCALAR_RE.match(value) or value[0] in "{":
        raise _SubsetError("scalar outside the subset")
    if value in ("null", "~"):
        return None
    return value


def _value(raw: str):
    """A scalar or a flow list of scalars."""
    value = _strip_comment(raw).strip()
    if value.startswith("["):
        if not value.endswith("]"):
            raise _SubsetError("unterminated flow list")
        return [_scalar(i) for i in _split_flow(value[1:-1])]
    return _scalar(raw)


# ---- registry ------------------------------------------------------------


def _indent_of(line: str) -> int:
    if line[: len(line) - len(line.lstrip())].count("\t"):
        raise _SubsetError("tab indentation")
    return len(line) - len(line.lstrip(" "))


def _parse_registry(text: str) -> dict:
    """The subset: top-level scalars plus `entries`, a block list of flat mappings."""
    lines = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    top: dict = {}
    entries: Optional[list] = None
    entry: Optional[dict] = None
    dash_indent = key_indent = -1
    pending: Optional[str] = None
    skipping_top = False
    for raw in lines:
        stripped = _strip_comment(raw).rstrip()
        if not stripped.strip():
            continue
        indent = _indent_of(stripped)
        body = stripped.strip()
        is_item = body == "-" or body.startswith("- ")
        if indent == 0 and not (is_item and entries is not None):
            if body.startswith("-"):
                raise _SubsetError("list item at column zero")
            m = _KEY_RE.match(body)
            if not m:
                raise _SubsetError("top-level line is not `key: value`")
            key, rest = m.group(1), m.group(2)
            entry, pending, skipping_top = None, None, False
            if key == "entries":
                if rest:
                    raise _SubsetError("`entries` must be a block list")
                entries = []
                dash_indent = -1
            elif rest:
                top[key] = _value(rest)
            else:
                skipping_top = True
            continue
        if skipping_top:
            continue
        if entries is None:
            raise _SubsetError("indented line outside `entries`")
        if body == "-" or body.startswith("- "):
            if dash_indent == -1:
                dash_indent = indent
            if indent == dash_indent:
                inner = body[1:].strip()
                m = _KEY_RE.match(inner)
                if not m:
                    raise _SubsetError("entry item is not a mapping")
                entry = {}
                entries.append(entry)
                key_indent = indent + (len(body) - len(body[1:].lstrip()))
                pending = None
                key, rest = m.group(1), m.group(2)
                if rest:
                    entry[key] = _value(rest)
                else:
                    entry[key] = []
                    pending = key
                continue
            if entry is not None and pending is not None and indent > dash_indent:
                item = body[1:].strip()
                if _KEY_RE.match(item) and not item.startswith(("'", '"')) and ": " in item:
                    raise _SubsetError("nesting deeper than the subset")
                entry[pending].append(_scalar(item))
                continue
            raise _SubsetError("unexpected list item")
        if entry is None:
            raise _SubsetError("mapping line before the first entry")
        if indent != key_indent:
            raise _SubsetError("entry key is not aligned")
        m = _KEY_RE.match(body)
        if not m:
            raise _SubsetError("entry line is not `key: value`")
        key, rest = m.group(1), m.group(2)
        pending = None
        if rest:
            entry[key] = _value(rest)
        else:
            entry[key] = []
            pending = key
    top["entries"] = entries if entries is not None else None
    return top


def _norm(path: str) -> str:
    path = path.strip().replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path


def _validate_entries(top: dict) -> list:
    if top.get("schema") != SCHEMA_ID:
        raise _SubsetError("schema is not design-registry/1")
    raw_entries = top.get("entries")
    if not isinstance(raw_entries, list):
        raise _SubsetError("entries is missing")
    out: list = []
    seen: set = set()
    for raw in raw_entries:
        ident = raw.get("id")
        if not isinstance(ident, str) or not ident or ident in seen:
            raise _SubsetError("entry id missing or repeated")
        seen.add(ident)
        board = raw.get("board")
        match = _canvas_harvest_gate._URL_RE.search(board) if isinstance(board, str) else None
        if match is None or board[match.end() :].strip():
            raise _SubsetError("board is not an artifact URL ending at its id")
        artboards, sources = raw.get("artboards"), raw.get("sources")
        # An empty `sources` is legal: a board with no source hit yet (a state no code renders).
        # It intersects nothing, so the gate never fires on it; reviewers surface it as unbuilt.
        if not isinstance(artboards, list) or not artboards:
            raise _SubsetError("artboards need at least one item")
        if not isinstance(sources, list):
            raise _SubsetError("sources must be a list")
        for items in (artboards, sources):
            if not all(isinstance(i, str) and i for i in items):
                raise _SubsetError("artboards and sources hold non-empty strings")
        harvest = raw.get("harvest")
        if not isinstance(harvest, str) or not _norm(harvest).strip("/"):
            raise _SubsetError("harvest missing")
        status = raw.get("status")
        if status not in _STATUSES:
            raise _SubsetError("status outside the enum")
        ratification = raw.get("ratification")
        if ratification is not None and not isinstance(ratification, (str, list)):
            raise _SubsetError("ratification malformed")
        if isinstance(ratification, list) or ratification == "":
            ratification = None
        if status == "deviated" and not ratification:
            raise _SubsetError("deviated entry without ratification")
        out.append(
            {
                "id": ident,
                "board": match.group(0),
                "artboards": list(artboards),
                "harvest": _norm(harvest).rstrip("/"),
                "sources": [_norm(s) for s in sources],
                "status": status,
                "ratification": ratification,
            }
        )
    return out


def registry_path(repo_root) -> Path:
    """The registry file for this repo: the `coordinator.local.md` key, else the default.

    A key that escapes the repo root resolves to a path outside it, which `load` refuses."""
    root = Path(repo_root)
    relative = DEFAULT_PATH
    if _read_text is not None and _scan_frontmatter is not None:
        text = _read_text(root / "coordinator.local.md")
        value = _scan_frontmatter(text).get(LOCAL_KEY) if text else None
        if isinstance(value, str) and value.strip():
            relative = value.strip()
    return (root / _norm(relative)).resolve()


def load(repo_root) -> tuple:
    """(entries, None) when present and valid; (None, None) when absent; (None, code) otherwise."""
    root = Path(repo_root).resolve()
    path = registry_path(root)
    try:
        path.relative_to(root)
    except ValueError:
        return None, _UNPARSEABLE
    if not path.is_file():
        return None, None
    try:
        text = path.read_text(encoding="utf-8")
        return _validate_entries(_parse_registry(text)), None
    except (OSError, UnicodeError, _SubsetError):
        return None, _UNPARSEABLE


# ---- glob ----------------------------------------------------------------


def _segment_regex(segment: str):
    parts = []
    for ch in segment:
        if ch == "*":
            if not parts or parts[-1] != "[^/]*":
                parts.append("[^/]*")
        elif ch == "?":
            parts.append("[^/]")
        else:
            parts.append(re.escape(ch))
    return re.compile("".join(parts))


@lru_cache(maxsize=512)
def _compiled(glob: str) -> tuple:
    return tuple(
        "**" if seg == "**" else _segment_regex(seg) for seg in _norm(glob).split("/") if seg
    )


def matches(glob: str, path: str) -> bool:
    """Whether `glob` covers `path`: POSIX segments, case-sensitive, `**` spans whole segments."""
    pattern = _compiled(glob)
    parts = tuple(seg for seg in _norm(path).split("/") if seg)

    @lru_cache(maxsize=None)
    def walk(pi: int, si: int) -> bool:
        if pi == len(pattern):
            return si == len(parts)
        seg = pattern[pi]
        if seg == "**":
            return any(walk(pi + 1, k) for k in range(si, len(parts) + 1))
        return si < len(parts) and seg.fullmatch(parts[si]) is not None and walk(pi + 1, si + 1)

    return walk(0, 0)


def _literal_head(glob: str) -> str:
    glob = _norm(glob)
    cut = min((glob.find(c) for c in "*?" if c in glob), default=len(glob))
    return glob[:cut]


def _intersects(glob: str, touched: str) -> bool:
    if touched.endswith("/"):
        head = _literal_head(glob)
        return head.startswith(touched) or touched.startswith(head)
    return matches(glob, touched)


# ---- plan text -----------------------------------------------------------


def _fences(text: str, kind: str) -> list:
    """The inner line lists of every ```yaml <kind> fence."""
    blocks: list = []
    current: Optional[list] = None
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if current is None:
            m = _FENCE_OPEN_RE.match(line)
            if m and m.group(1) == kind:
                current = []
        elif line.strip().startswith("```"):
            blocks.append(current)
            current = None
        else:
            current.append(line)
    return blocks


def _leading_spaces(line: str) -> int:
    return len(line) - len(line.lstrip())


def _block_items(lines: list, start: int, key_col: int) -> tuple:
    """Items of a block list under a key at `key_col`; (items, next index)."""
    items: list = []
    i = start
    while i < len(lines):
        line = lines[i]
        s = _strip_comment(line).strip()
        if not s:
            i += 1
            continue
        if _leading_spaces(line) >= key_col and (s == "-" or s.startswith("- ")):
            items.append(s[1:].strip())
            i += 1
            continue
        break
    return items, i


def plan_writes(text: str) -> list:
    """Every `writes:` file and `writes_under:` prefix (trailing `/`) in the plan-tasks fence(s)."""
    files: list = []
    prefixes: list = []
    for lines in _fences(text, "plan-tasks"):
        i = 0
        while i < len(lines):
            line = lines[i]
            i += 1
            m = _WRITE_KEY_RE.match(line)
            if not m:
                km = _KEY_LINE_RE.match(line)
                if km and km.group(3).strip()[:1] in ("|", ">"):
                    key_col = len(km.group(1)) + (len(km.group(2)) if km.group(2) else 0)
                    while i < len(lines) and (
                        not lines[i].strip() or _leading_spaces(lines[i]) > key_col
                    ):
                        i += 1
                continue
            key_col = len(m.group(1)) + (len(m.group(2)) if m.group(2) else 0)
            rest = _strip_comment(m.group(4)).strip()
            raw: list = []
            if rest.startswith("["):
                buf = rest
                while "]" not in buf and i < len(lines):
                    buf += " " + _strip_comment(lines[i]).strip()
                    i += 1
                raw = _split_flow(buf[1 : buf.rfind("]")] if "]" in buf else buf[1:])
            elif not rest:
                raw, i = _block_items(lines, i, key_col + 1)
            elif rest != "[]":
                raw = [rest]
            target = prefixes if m.group(3) == "writes_under" else files
            for item in raw:
                try:
                    value = _scalar(item)
                except _SubsetError:
                    continue
                if isinstance(value, str) and value:
                    path = _norm(value)
                    target.append(path if m.group(3) == "writes" else path.rstrip("/") + "/")
    return files + prefixes


def deviations(text: str) -> list:
    """The mapping items of every ```yaml design-deviation fence."""
    items: list = []
    for lines in _fences(text, "design-deviation"):
        current: Optional[dict] = None
        for line in lines:
            s = _strip_comment(line).rstrip()
            if not s.strip():
                continue
            body = s.strip()
            if body.startswith("- ") or body == "-":
                current = {}
                items.append(current)
                body = body[1:].strip()
            m = _KEY_RE.match(body) if body else None
            if m and current is not None:
                try:
                    current[m.group(1)] = _scalar(m.group(2) or "")
                except _SubsetError:
                    current[m.group(1)] = None
    return items


# ---- check ---------------------------------------------------------------

_REASONS = {
    _UNPARSEABLE: (
        "the design registry is present but malformed",
        "Repair the registry per the contract.",
    ),
    "design-not-cited": (
        "touches files a registered design covers and cites neither its harvest record nor a ratified design-deviation",
        "Cite {harvest}/harvest.json, or add a design-deviation block naming a PM ratification.",
    ),
    "design-harvest-refused": (
        "cites the harvest record and the canvas judgment refuses it",
        "Fix the record per canvas-harvest-record.md.",
    ),
    "deviation-unratified": (
        "carries a design-deviation whose ratified_by is not an existing file",
        "Name the file carrying the PM's ratification.",
    ),
}


def _refusal(entry: str, code: str, harvest: str = "", detail: str = "") -> Refusal:
    what, remedy = _REASONS[code]
    who = f" entry {entry}" if entry else ""
    prose = f"Design {code}:{who} {what}{detail}. {remedy.format(harvest=harvest)}"
    if len(prose) > _message_envelope.CEILING:
        prose = prose[: _message_envelope.CEILING - 3].rstrip() + "..."
    message = _message_envelope.compose(prose, anchor=WIKI_ANCHOR)
    return Refusal(entry, code, _message_envelope.render(message))


def _names_record(text: str, harvest: str) -> bool:
    target = re.escape(harvest.strip("/") + "/harvest.json")
    flat = re.sub(r"(?<![\w.\-/])\./", "", text.replace("\\", "/"))
    return re.search(r"(?<![\w.\-/])" + target, flat) is not None


def _is_plan(root: Path, target: Path) -> bool:
    """A plan cannot ratify its own deviation: `docs/plans/**` never counts as PM words."""
    try:
        target.resolve().relative_to((root / "docs" / "plans").resolve())
    except ValueError:
        return False
    return True


def _ratified(root: Path, entry_id: str, items: list):
    """(satisfied, saw_item) for the deviation items naming `entry_id`."""
    saw = False
    for item in items:
        if item.get("entry") != entry_id:
            continue
        saw = True
        cited = item.get("ratified_by")
        if not isinstance(cited, str) or not cited.strip():
            continue
        target = _canvas_harvest_gate._resolve(root, cited.strip())
        if target is not None and target.is_file() and not _is_plan(root, target):
            return True, True
    return False, saw


def check(text: str, repo_root) -> list:
    """One `Refusal` per intersected entry (or one for a malformed registry) left unsatisfied.

    No touched files or no registry file: no refusal. Judges the whole `text`."""
    touched = plan_writes(text)
    if not touched:
        return []
    root = Path(repo_root)
    entries, error = load(root)
    if error:
        return [_refusal("", error)]
    if not entries:
        return []
    items = deviations(text)
    refusals: list = []
    for entry in entries:
        if not any(_intersects(g, t) for g in entry["sources"] for t in touched):
            continue
        harvest_refusal = None
        if _names_record(text, entry["harvest"]):
            judged = _canvas_harvest_gate._judge(entry["board"], text, root, None)
            if judged is None:
                continue
            harvest_refusal = judged
        satisfied, saw_item = _ratified(root, entry["id"], items)
        if satisfied:
            continue
        if harvest_refusal is not None:
            refusals.append(
                _refusal(entry["id"], "design-harvest-refused", detail=f" ({harvest_refusal.code})")
            )
        elif saw_item:
            refusals.append(_refusal(entry["id"], "deviation-unratified"))
        else:
            refusals.append(_refusal(entry["id"], "design-not-cited", harvest=entry["harvest"]))
    return refusals
