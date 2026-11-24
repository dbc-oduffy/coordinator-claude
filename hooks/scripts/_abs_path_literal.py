"""Stdlib detector for literal absolute paths and drive roots in written text.

Consumed in-process by the doctrine-plane write guard run from
`preuse-write-dispatch.py`, which imports no engine code, so this module is
pure stdlib. The `posix-home`, `drive-letter` and `unc` rules are pinned to
`coordinator_core.ops.session.guard_concrete_path_citations.detect_in_text` by
`coordinator/tests/test_abs_path_literal_engine_parity.py`; change them in
step with the engine. `mounted-volume` has no engine counterpart.

Interface:
  detect_abs_path_literals(text) -> list[Finding]   every literal, marked or not
  new_literals(before, after)    -> list[Finding]   literals `after` adds
  is_marked(line, finding=None)  -> bool            reasoned same-line escape
  replacement_hint(finding)      -> str             what to write instead

A reasoned marker never exempts a data, cache, scratch or run-output root.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import List, Optional

RULES = ("posix-home", "drive-letter", "unc", "mounted-volume")

_SEG = r"[A-Za-z0-9_.\-<>${}]+"
_NOT_AFTER = r"(?<![A-Za-z0-9_./\\:-])"

_POSIX_HOME_RE = re.compile(
    r"(?:" + _NOT_AFTER + r"(?:/mnt)?/[A-Za-z](?=/(?:Users|home)/)|" + _NOT_AFTER + r")"
    r"/(?:Users|home)/(" + _SEG + r")(?![A-Za-z0-9_.\-<>${}])"
)
_WIN_DRIVE_RE = re.compile(
    r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/](?![ntrbfv0](?![A-Za-z0-9_\-]))"
)
_UNC_RE = re.compile(
    r"(?<!\\)\\\\(?![.?]\\)[A-Za-z0-9_.\-]+\\(?![ntrbfv0](?![A-Za-z0-9_\-]))[A-Za-z0-9_.\-]+"
)
_MOUNTED_RE = re.compile(
    _NOT_AFTER + r"/(?:Volumes|mnt)/(" + _SEG + r")(?![A-Za-z0-9_.\-<>${}])"
)
_TOKEN_RE = re.compile(r"[^\s\"'`]+")

_PLACEHOLDER_WORDS = frozenset(
    {
        "alice", "bob", "username", "you", "me", "foo", "bar", "baz", "test",
        "example", "someone", "operator", "yourname",
        "host", "hostname", "server", "share", "fileserver", "machine",
    }
)
_PROFILE_ROOTS = frozenset({"users", "home"})
_WELL_KNOWN_WIN_ROOTS = frozenset(
    {"windows", "program files", "program files (x86)", "programdata", "symbols"}
)

# System paths no one repoints; none matches a rule today, the set pins that.
_SYSTEM_PATHS = frozenset({"/dev/null", "/usr/bin/env", "/bin/sh", "/bin/bash"})

# A path segment naming one of these words marks a data, cache, scratch or
# run-output root; the segment is split on `-`, `_` and `.` before matching.
_DATA_ROOT_WORDS = frozenset(
    {
        "scratch", "cache", "caches", "render", "renders", "output", "outputs",
        "runs", "data", "datasets", "model", "models", "vendor", "index",
        "indexes", "indices", "build", "builds", "tmp", "temp", "intermediate",
        "derived", "artifacts", "checkpoints",
    }
)

_MARKER_RE = re.compile(r"(?:^|[^A-Za-z0-9_])(?:abs-path-ok|foreign-path-ok):")
_COMMENT_CLOSER_RE = re.compile(r"\s*(?:-->|\*/)\s*$")


@dataclass(frozen=True)
class Finding:
    """One literal absolute path. `line_text` rides along for `is_marked`."""

    line_no: int
    literal: str
    rule: str
    root_class: str = "general"  # "general" | "data"
    line_text: str = field(default="", compare=False)


def _is_placeholder(seg: str) -> bool:
    core = seg.rstrip("/\\")
    if core == "...":
        return True
    if core.startswith("<") and core.endswith(">"):
        return True
    if core.startswith("$"):
        return True
    return core.lower() in _PLACEHOLDER_WORDS


def _first_segment(token: str, root_len: int) -> str:
    m = re.match(r"[^/\\]*", token[root_len:])
    return m.group(0) if m else ""


def _has_ellipsis_segment(token: str, root_len: int) -> bool:
    for seg in re.split(r"[\\/]+", token[root_len:]):
        if seg == "...":
            return True
        if seg and not _is_placeholder(seg):
            return False
    return False


def _profile_account(token: str, root_len: int) -> Optional[str]:
    rest = "/" + token[root_len:].replace("\\", "/")
    m = _POSIX_HOME_RE.match(rest)
    return m.group(1) if m else None


def _drive_token_exempt(token: str, root_len: int) -> bool:
    first = _first_segment(token, root_len)
    if _is_placeholder(first):
        return True
    low = first.lower()
    if low in _PROFILE_ROOTS:
        account = _profile_account(token, root_len)
        return account is not None and _is_placeholder(account)
    if low not in _WELL_KNOWN_WIN_ROOTS:
        return False
    rest = [
        s for s in re.split(r"[\\/]+", token[root_len + len(first):]) if s
    ]
    if not rest:
        return True
    if low == "symbols":
        return rest[0].lower().startswith(("http:", "https:"))
    for i in range(len(rest) - 1):
        if rest[i].lower() in _PROFILE_ROOTS and not _is_placeholder(rest[i + 1]):
            return False
    return True


def _extract_token(line: str, start: int) -> str:
    m = _TOKEN_RE.match(line, start)
    return m.group(0) if m else line[start : start + 1]


def _root_class(token: str) -> str:
    for seg in re.split(r"[\\/]+", token):
        for word in re.split(r"[-_.]+", seg.lower()):
            if word in _DATA_ROOT_WORDS:
                return "data"
    return "general"


def _is_system_path(token: str) -> bool:
    return token.rstrip(".,;:)]}") in _SYSTEM_PATHS


def detect_abs_path_literals(text: str) -> List[Finding]:
    """Every literal absolute path or drive root in `text`, marked lines included.

    Callers drop a finding with `is_marked(f.line_text, f)`; a data-root
    finding survives its marker.
    """
    findings: List[Finding] = []
    for line_no, line in enumerate(text.splitlines(), start=1):

        def add(literal: str, rule: str, token: str) -> None:
            if _is_system_path(token):
                return
            findings.append(
                Finding(line_no, literal, rule, _root_class(token), line)
            )

        home_spans = []
        for m in _POSIX_HOME_RE.finditer(line):
            home_spans.append(m.span())
            if not _is_placeholder(m.group(1)):
                add(m.group(0), "posix-home", _extract_token(line, m.start()))

        for m in _WIN_DRIVE_RE.finditer(line):
            token = _extract_token(line, m.start())
            root_len = m.end() - m.start()
            if _drive_token_exempt(token, root_len) or _has_ellipsis_segment(
                token, root_len
            ):
                continue
            add(token, "drive-letter", token)

        for m in _UNC_RE.finditer(line):
            host = m.group(0).lstrip("\\").split("\\")[0]
            if _is_placeholder(host):
                continue
            token = _extract_token(line, m.start())
            add(token, "unc", token)

        for m in _MOUNTED_RE.finditer(line):
            if any(a <= m.start() < b for a, b in home_spans):
                continue
            if _is_placeholder(m.group(1)):
                continue
            add(m.group(0), "mounted-volume", _extract_token(line, m.start()))
    return findings


def is_marked(line: str, finding: Optional[Finding] = None) -> bool:
    """True when `line` carries a same-line marker with a non-empty reason.

    Accepts `abs-path-ok:` and the older `foreign-path-ok:`. A bare marker, or
    one followed only by a comment closer, is not a reason. A data-root
    `finding` is never marked.
    """
    if finding is not None and finding.root_class == "data":
        return False
    for m in _MARKER_RE.finditer(line):
        if _COMMENT_CLOSER_RE.sub("", line[m.end():]).strip():
            return True
    return False


def new_literals(before: str, after: str) -> List[Finding]:
    """Findings `after` carries beyond those already in `before`.

    A multiset difference keyed by (rule, literal, marked), so an unrelated edit
    never re-flags a legacy literal, and a duplicate or an unmarked copy of a
    marked one counts as new. Line numbers are ignored.
    """

    def key(f: Finding) -> tuple:
        return (f.rule, f.literal, is_marked(f.line_text, f))

    seen = Counter(key(f) for f in detect_abs_path_literals(before))
    new: List[Finding] = []
    for f in detect_abs_path_literals(after):
        k = key(f)
        if seen[k] > 0:
            seen[k] -= 1
        else:
            new.append(f)
    return new


_RESOLVE_HINT = (
    "Resolve the path, never type it: a sibling repo or machine-local root via "
    "`machine-local get <key>` (confirm the key with `machine-local keys`; Python "
    "`claude_machine_local.repos`, shell `claude-machine-local.sh`); a file beside "
    "the running code via `__file__` / `BASH_SOURCE` self-resolution; a repo-owned "
    "file as a repo-relative path; scratch under `<repo>/scratch/`."
)
_MARKER_HINT = (
    "Only a line quoting the literal as evidence stays: append "
    "`abs-path-ok: <reason>` on that line."
)
_DATA_HINT = (
    "This is a data, cache, scratch or run-output root: resolve it through a "
    "settings-home key with `machine-local get <key>`, a missing key a typed "
    "refusal naming the key, never a default path. `abs-path-ok:` does not "
    "exempt a data root. Repo scratch is `<repo>/scratch/`."
)


def replacement_hint(finding: Finding) -> str:
    """The resolving replacement to write instead of `finding.literal`."""
    head = f"Literal absolute path `{finding.literal}` ({finding.rule}) names one machine."
    if finding.root_class == "data":
        return f"{head} {_DATA_HINT} {_RESOLVE_HINT}"
    return f"{head} {_RESOLVE_HINT} {_MARKER_HINT}"
