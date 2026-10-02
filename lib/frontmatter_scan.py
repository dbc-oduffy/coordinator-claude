"""Stdlib-only column-zero key scanner for frontmatter and flat YAML mappings.

Failure semantic: nothing in this module raises. An unreadable file is ``None`` out
of ``read_text``. Every other failure (no fence, an unterminated fence, text
that is not a mapping) is ``{}``. The caller decides what ``None`` means.

Key rules: only column-zero ``key: value`` lines are keys (an indented line is
never a key); the first occurrence of a key wins; a trailing ``#`` comment
(at value start or after whitespace, outside quotes) is dropped; matching
quotes are removed; ``[a, b]`` and ``- item`` blocks become ``list[str]``; a
block or folded scalar indicator (``|``, ``>-``) is returned verbatim and its
continuation lines never surface as keys; any other empty value is ``""``.

Tripwire: A-FRONTMATTER-LINE-SCANNER-IS-IMPORTED-NEVER-COPIED. A hook or lib
script reads frontmatter keys through this module; it does not carry its own
scanner.

Hook import: put ``_LIB_DIR = Path(__file__).resolve().parents[2] / "lib"`` on
``sys.path``, then import the names. A lib sibling inserts its own directory
on ``sys.path`` first, then imports plainly.
"""

from __future__ import annotations

_BOM = "﻿"


def read_text(path) -> str | None:
    """Return the file's text (UTF-8, undecodable bytes replaced, one leading
    BOM removed), or None when the file cannot be read."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except (OSError, ValueError, TypeError):
        return None
    return text[1:] if text.startswith(_BOM) else text


def _lines(text: str) -> list[str]:
    if text.startswith(_BOM):
        text = text[1:]
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _strip_comment(value: str) -> str:
    quote = ""
    for i, ch in enumerate(value):
        if quote:
            if ch == quote:
                quote = ""
        elif ch in ("'", '"'):
            quote = ch
        elif ch == "#" and (i == 0 or value[i - 1] in " \t"):
            return value[:i].rstrip()
    return value


def _unquote(value: str) -> str:
    """Strip a trailing comment and one matching quote pair."""
    value = value.strip()
    if value[:1] in ("'", '"'):
        close = value.find(value[0], 1)
        if close != -1:
            tail = value[close + 1 :].strip()
            if not tail or tail.startswith("#"):
                return value[1:close]
    return _strip_comment(value)


def _split_inline(body: str) -> list[str]:
    items: list[str] = []
    cur: list[str] = []
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
    return [_unquote(i) for i in items if i.strip()]


def _is_block_indicator(value: str) -> bool:
    if value[:1] not in ("|", ">"):
        return False
    return all(c in "+-0123456789" for c in value[1:]) and len(value) <= 4


def _is_skippable(line: str) -> bool:
    s = line.strip()
    return not s or s.startswith("#")


def _is_item(line: str) -> bool:
    s = line.lstrip()
    return s == "-" or s.startswith("- ") or s.startswith("-\t")


def scan_mapping(text: str | None) -> dict[str, str | list[str]]:
    """Return the column-zero keys of flat YAML-shaped text; {} on None, ""
    or anything unparseable."""
    if not isinstance(text, str) or not text:
        return {}
    try:
        lines = _lines(text)
        out: dict[str, str | list[str]] = {}
        i = 0
        while i < len(lines):
            line = lines[i]
            i += 1
            if not line or line[0] in " \t#" or _is_item(line):
                continue
            colon = line.find(":")
            if colon <= 0:
                continue
            rest = line[colon + 1 :]
            if rest and rest[0] not in " \t":
                continue
            key = line[:colon].rstrip()
            value = _strip_comment(rest.strip())
            if value:
                if value.startswith("[") and value.endswith("]"):
                    parsed: str | list[str] = _split_inline(value[1:-1])
                elif _is_block_indicator(value):
                    parsed = value
                else:
                    parsed = _unquote(rest)
            else:
                items: list[str] = []
                j = i
                while j < len(lines) and (_is_skippable(lines[j]) or _is_item(lines[j])):
                    if not _is_skippable(lines[j]):
                        items.append(_unquote(lines[j].lstrip()[1:]))
                    j += 1
                if items:
                    parsed = items
                    i = j
                else:
                    parsed = ""
            out.setdefault(key, parsed)
        return out
    except Exception:
        return {}


def scan_frontmatter(text: str | None) -> dict[str, str | list[str]]:
    """Return scan_mapping of the leading ``---`` block; {} when there is no
    opening fence or no closing fence."""
    if not isinstance(text, str) or not text:
        return {}
    lines = _lines(text)
    if lines[0].rstrip() != "---":
        return {}
    for end in range(1, len(lines)):
        if lines[end].rstrip() == "---":
            return scan_mapping("\n".join(lines[1:end]))
    return {}
