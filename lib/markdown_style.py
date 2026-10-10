"""In-process markdown style runner for the doctrine wiki gate.

Contract: ``lint(paths)`` answers "which violations of rule R does file F carry?" as
``(repo_relative_posix_path, 1-based line, rule_id)`` tuples. Spawns nothing, reads utf-8,
normalises CRLF, derives its root from ``__file__``.

``KNOWN_RULE_IDS`` is the frozen rule universe (the markdownlint 0.41.1 census), pinned here as
a literal so it never shrinks to whatever ``IMPLEMENTED_RULE_IDS`` happens to cover. A rule the
decision table keeps must be in ``IMPLEMENTED_RULE_IDS``, or keeping it would be vacuous.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]

KNOWN_RULE_IDS: tuple[str, ...] = (
    "MD001", "MD003", "MD004", "MD005", "MD007", "MD009", "MD010", "MD011", "MD012", "MD013",
    "MD014", "MD018", "MD019", "MD020", "MD021", "MD022", "MD023", "MD024", "MD025", "MD026",
    "MD027", "MD028", "MD029", "MD030", "MD031", "MD032", "MD033", "MD034", "MD035", "MD036",
    "MD037", "MD038", "MD039", "MD040", "MD041", "MD042", "MD043", "MD044", "MD045", "MD046",
    "MD047", "MD048", "MD049", "MD050", "MD051", "MD052", "MD053", "MD054", "MD055", "MD056",
    "MD058", "MD059", "MD060",
)

IMPLEMENTED_RULE_IDS: frozenset[str] = frozenset({
    "MD001", "MD009", "MD011", "MD012", "MD019", "MD020", "MD021", "MD022", "MD027", "MD028",
    "MD031", "MD032", "MD039", "MD042", "MD047", "MD052", "MD055", "MD058",
})

_FENCE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")
_ATX = re.compile(r"^ {0,3}(#{1,6})(?:\s|$)")
_SETEXT_UL = re.compile(r"^ {0,3}(=+|-+)\s*$")
_LIST = re.compile(r"^\s*(?:[-*+]|(\d{1,9})[.)])(?:\s+|$)")
_HR = re.compile(r"^ {0,3}([-*_])(?: *\1){2,}\s*$")
_DELIM = re.compile(r"^\s*\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*\|?\s*$")
_CODE_SPAN = re.compile(r"(`+)(?:(?!\1).)+?\1")
_REVERSED = re.compile(r"(^|[^\\])\(([^()]+)\)\[([^\]^][^\]]*)\](?!\()")
_SPACE_LINK = re.compile(r"\[(?:\s+[^\]\s][^\]]*|[^\]\s][^\]]*\s+)\]\([^)]*\)")
_EMPTY_LINK = re.compile(r"\[[^\]]*\]\(\s*(?:#|<>)?\s*\)")
_REF_USE = re.compile(r"\[([^\]\n]+)\]\[([^\]\n]*)\]")
_REF_DEF = re.compile(r"^ {0,3}\[([^\]\n]+)\]:")
_CLOSED_NO_SPACE = re.compile(r"^#{1,6}[^#\s].*[^\\#]#+\s*$")
_CLOSED_MULTI = re.compile(r"^#{1,6}(?:\s{2,}\S.*\S\s*#+\s*|\s+\S.*\S\s{2,}#+\s*)$")
_MULTI_ATX = re.compile(r"^#{1,6}\s{2,}\S")
_QUOTE_MULTI = re.compile(r"^\s{0,3}>+ {2,}\S")
_LIST_LEAD = frozenset("-*+0123456789")


def _blank(line: str) -> bool:
    return not line.strip()


def _strip_code(line: str) -> str:
    return _CODE_SPAN.sub(lambda m: "x" * len(m.group(0)), line) if "`" in line else line


def _classify(lines: list[str]) -> list[str]:
    """Per-line kind: fm | fopen | fclose | code | text."""
    kinds = ["text"] * len(lines)
    start = 0
    if lines and lines[0].rstrip() == "---":
        for j in range(1, len(lines)):
            if lines[j].rstrip() in ("---", "..."):
                for k in range(j + 1):
                    kinds[k] = "fm"
                start = j + 1
                break
    fence: tuple[str, int] | None = None
    for i in range(start, len(lines)):
        m = _FENCE.match(lines[i])
        if fence is None:
            if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
                fence = (m.group(1)[0], len(m.group(1)))
                kinds[i] = "fopen"
        elif m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1] and _blank(m.group(2)):
            kinds[i] = "fclose"
            fence = None
        else:
            kinds[i] = "code"
    return kinds


def _scan(text: str) -> set[tuple[int, str]]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    out: set[tuple[int, str]] = set()
    if not text:
        return out
    lines = text.split("\n")
    if text.endswith("\n"):
        lines.pop()
    else:
        out.add((len(lines), "MD047"))
    n = len(lines)
    kinds = _classify(lines)
    stripped = [ln.strip() for ln in lines]
    blanks = [not s for s in stripped]
    blankish = [not s or (s.startswith("<!--") and s.endswith("-->")) for s in stripped]

    def add(i: int, rule: str) -> None:
        out.add((i + 1, rule))

    defs = (
        {m.group(1).casefold() for m in re.finditer(r"^ {0,3}\[([^\]\n]+)\]:", text, re.M)}
        if "][" in text else set()
    )
    prev_level = 0
    skip_next = False
    in_list = False
    prev_blank = True

    for i, line in enumerate(lines):
        k = kinds[i]
        if k == "fm":
            continue
        if line and line[-1] in " \t":
            w = len(line) - len(line.rstrip(" \t"))
            if not (w == 2 and line.strip()):
                add(i, "MD009")
        if k == "fopen":
            if i > 0 and not blankish[i - 1] and kinds[i - 1] != "fm":
                add(i, "MD031")
        elif k == "fclose":
            if i + 1 < n and not blankish[i + 1]:
                add(i, "MD031")
        real_blank = blanks[i]
        if real_blank and i > 0 and blanks[i - 1] and kinds[i - 1] != "fm":
            add(i, "MD012")
        if k == "code":
            continue

        blank = blankish[i]
        if blank:
            if real_blank and k == "text":
                j, p = i - 1, i + 1
                while j >= 0 and blanks[j]:
                    j -= 1
                while p < n and blanks[p]:
                    p += 1
                if (j >= 0 and p < n and kinds[j] == "text" and kinds[p] == "text"
                        and lines[j].lstrip().startswith(">") and lines[p].lstrip().startswith(">")):
                    add(i, "MD028")
            prev_blank = True
            continue

        if k == "fclose":
            prev_blank = False
            continue
        if k == "fopen":
            if in_list and not prev_blank and len(line) - len(line.lstrip()) < 2:
                add(i, "MD032")
                in_list = False
            elif prev_blank and len(line) - len(line.lstrip()) < 2:
                in_list = False
            prev_blank = False
            continue

        if skip_next:
            skip_next = False
            prev_blank = False
            continue

        stripped = line.lstrip()
        if stripped.startswith(">"):
            if _QUOTE_MULTI.match(line):
                add(i, "MD027")
            prev_blank = False
            continue

        if (")[" in line or "](" in line or "][" in line) and (in_list or len(line) - len(stripped) < 4):
            scrubbed = _strip_code(line)
            if _REVERSED.search(scrubbed):
                add(i, "MD011")
            if _SPACE_LINK.search(scrubbed):
                add(i, "MD039")
            if _EMPTY_LINK.search(scrubbed):
                add(i, "MD042")
            for m in _REF_USE.finditer(scrubbed):
                if m.group(1).startswith("^"):
                    continue
                label = (m.group(2) or m.group(1)).casefold()
                if label not in defs:
                    add(i, "MD052")

        atx = _ATX.match(line) if "#" in line[:4] else None
        if atx:
            level = len(atx.group(1))
            if prev_level and level > prev_level + 1:
                add(i, "MD001")
            prev_level = level
            if i > 0 and not blankish[i - 1] and kinds[i - 1] != "fm":
                add(i, "MD022")
            if i + 1 < n and not blankish[i + 1]:
                add(i, "MD022")
            if _MULTI_ATX.match(line):
                add(i, "MD019")
            if _CLOSED_NO_SPACE.match(line):
                add(i, "MD020")
            if _CLOSED_MULTI.match(line):
                add(i, "MD021")
        elif (i + 1 < n and lines[i + 1][:1] in ("=", "-", " ") and kinds[i + 1] == "text"
              and _SETEXT_UL.match(lines[i + 1]) and not _LIST.match(line) and not _HR.match(line)
              and not stripped.startswith(("|", "#")) and len(line) - len(stripped) < 4):
            level = 1 if lines[i + 1].lstrip().startswith("=") else 2
            if prev_level and level > prev_level + 1:
                add(i, "MD001")
            prev_level = level
            skip_next = True

        item = _LIST.match(line) if stripped[:1] in _LIST_LEAD else None
        if item and _HR.match(line):
            item = None
        if item and not in_list and not prev_blank and i > 0 and kinds[i - 1] != "fm":
            ordinal = item.group(1)
            if ordinal is not None and int(ordinal) != 1:
                item = None
        indent = len(line) - len(stripped)
        if item:
            if not in_list and not prev_blank and i > 0 and kinds[i - 1] != "fm":
                add(i, "MD032")
            in_list = True
        elif in_list:
            if prev_blank:
                if indent < 2:
                    in_list = False
            elif atx and indent < 2:
                add(i, "MD032")
                in_list = False
        prev_blank = False

    i = 0
    while i + 1 < n:
        if (kinds[i] == "text" and kinds[i + 1] == "text" and "|" in lines[i]
                and _DELIM.match(lines[i + 1]) and "|" in lines[i + 1]):
            end = i + 1
            while (end + 1 < n and kinds[end + 1] == "text" and not blanks[end + 1]
                   and "|" in lines[end + 1]):
                end += 1
            if i > 0 and not blankish[i - 1] and kinds[i - 1] != "fm":
                add(i, "MD058")
            if end + 1 < n and not blankish[end + 1]:
                add(end, "MD058")
            lead = lines[i].strip().startswith("|")
            trail = lines[i].rstrip().endswith("|") and not lines[i].rstrip().endswith("\\|")
            for r in range(i + 1, end + 1):
                row = lines[r].strip()
                if row.startswith("|") != lead or (row.endswith("|") and not row.endswith("\\|")) != trail:
                    add(r, "MD055")
            i = end + 1
        else:
            i += 1
    return out


def lint(paths: Iterable[Path], rules: Iterable[str] | None = None) -> list[tuple[str, int, str]]:
    """Return ``(rel_path, line, rule_id)`` for every violation in ``paths``, sorted.

    ``rules`` restricts the result to those rule ids; ``None`` reports every implemented rule.
    """
    wanted = None if rules is None else set(rules)
    found: list[tuple[str, int, str]] = []
    for p in paths:
        path = Path(p)
        text = path.read_text(encoding="utf-8")
        hits = [(line, rule) for line, rule in _scan(text) if wanted is None or rule in wanted]
        if not hits:
            continue
        try:
            rel = path.resolve().relative_to(ROOT).as_posix()
        except ValueError:
            rel = path.as_posix()
        found.extend((rel, line, rule) for line, rule in hits)
    return sorted(found)
