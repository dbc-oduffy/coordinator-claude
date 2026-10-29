"""The declared OSS release set, and the shipped-surface references checked against it.

`shipped(relpath)` answers one question over plugin-relative POSIX paths: does this path reach
the public mirror? It is composed from `_oss_payload.parse_mirror_row()` (allowlist, `!`
exclusions, `^` denies) minus `.percolate-ignore` matches, never a second hand-kept list.

Entries the row routes through `source_map` (the engine-resident trees) cannot be answered from
this clone. With an export root (`COORDINATOR_OSS_EXPORT_ROOT`, the plugin root of an exported
tree) they resolve against it; without one they classify `unverified-engine-routed` and are never
reported as shipped. `COORDINATOR_OSS_RELEASE_STRICT=1` makes the gate count them as failures.

`referenced_paths(file)` extracts the plugin-relative paths a shipped surface names: a
plugin-root variable prefix, a `coordinator/` prefix outside `docs/`, and Path-join chains of
string literals. `docs/` targets are not gated here; the wiki-pointer detector owns them.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

import _oss_payload  # noqa: E402

REPO_ROOT = _oss_payload.REPO_ROOT

EXPORT_ROOT_ENV = "COORDINATOR_OSS_EXPORT_ROOT"
STRICT_ENV = "COORDINATOR_OSS_RELEASE_STRICT"

SHIPPED = "shipped"
NOT_SHIPPED = "not-shipped"
UNVERIFIED = "unverified-engine-routed"

#: Top-level plugin directories whose files are scanned as referrers.
_SURFACE_DIRS = frozenset({"skills", "commands", "agents", "hooks", "snippets", "docs"})

_TEXT_SUFFIXES = frozenset(
    {".md", ".py", ".sh", ".json", ".yaml", ".yml", ".toml", ".tmpl", ".txt"}
)

_PATH_CHARS = r"[A-Za-z0-9_.\-/]+"
_PLUGIN_ROOT_REF = re.compile(r"\$\{?CLAUDE_PLUGIN_ROOT\}?/(" + _PATH_CHARS + r")")
_COORDINATOR_REF = re.compile(r"(?<![\w/.\-])coordinator/(" + _PATH_CHARS + r")")
_JOIN_CHAIN = re.compile(r"""(?:"[^"\n/]+"|'[^'\n/]+')(?:\s*/\s*(?:"[^"\n/]+"|'[^'\n/]+'))+""")
_JOIN_SEGMENT = re.compile(r"""["']([^"'\n/]+)["']""")
_HAS_EXTENSION = re.compile(r"\.[A-Za-z0-9]{1,6}$")
_PLACEHOLDER_NEXT = frozenset("<>{}$*[]")
_TRAILING_STRIP = ".,;:-"


def export_root() -> "Path | None":
    raw = os.environ.get(EXPORT_ROOT_ENV, "").strip()
    return Path(raw) if raw else None


def strict() -> bool:
    return os.environ.get(STRICT_ENV, "").strip() == "1"


@dataclass(frozen=True)
class _Composition:
    allow: tuple
    exclude: tuple
    deny: tuple
    routed: frozenset
    coarse: frozenset
    ignore: tuple


def _composition() -> _Composition:
    row = _oss_payload.parse_mirror_row()
    deny = tuple(e[1:] for e in row.allowlist if e.startswith("^"))
    allow = tuple(e for e in row.allowlist if not e.startswith("^"))
    routed: set = set()
    for entries in row.source_map.values():
        routed.update(entries)
    return _Composition(
        allow=allow,
        exclude=tuple(row.exclusions),
        deny=deny,
        routed=frozenset(routed),
        coarse=frozenset(e for e in allow if "/" not in e and "." not in e),
        ignore=_oss_payload.excluded_patterns(),
    )


def _under(rel: str, entry: str) -> bool:
    entry = entry.rstrip("/")
    return rel == entry or rel.startswith(entry + "/")


def _toplevel_wiki_names() -> frozenset:
    return frozenset(_oss_payload.toplevel_wiki_allowlist())


def classify(rel: str, root: "Path | None | str" = "env") -> str:
    """`shipped`, `not-shipped` or `unverified-engine-routed` for a plugin-relative POSIX path.

    A directory path is `shipped` when it is admitted or is an ancestor of an admitted entry.
    `root` defaults to the environment's export root; pass `None` to force "no export root".
    """
    rel = rel.strip().removeprefix("./").rstrip("/")
    comp = _composition()
    if any(_under(rel, d) for d in comp.deny):
        return NOT_SHIPPED
    if rel.startswith("docs/wiki/") and rel.count("/") == 2:
        if rel.rsplit("/", 1)[1] in _toplevel_wiki_names():
            return SHIPPED
    owner = next((e for e in comp.allow if _under(rel, e)), None)
    if owner is None:
        if any(_under(e, rel) for e in comp.allow):
            return SHIPPED
        return NOT_SHIPPED
    if any(_under(rel, x) for x in comp.exclude):
        return NOT_SHIPPED
    if owner in comp.coarse and _oss_payload._is_excluded(rel, comp.ignore):
        return NOT_SHIPPED
    if owner in comp.routed:
        resolved = export_root() if root == "env" else root
        if resolved is None:
            return UNVERIFIED
        return SHIPPED if (Path(resolved) / rel).exists() else NOT_SHIPPED
    return SHIPPED


def shipped(rel: str, root: "Path | None | str" = "env") -> bool:
    """True only when `classify` answers `shipped`; an unverified engine-routed path is False."""
    return classify(rel, root) == SHIPPED


def _clean(target: str) -> str:
    return target.rstrip(_TRAILING_STRIP)


def referenced_paths(file) -> "set[str]":
    """Plugin-relative POSIX paths named by `file`: plugin-root prefixes, `coordinator/` prefixes
    and Path-join chains of string literals. Directories (trailing slash), placeholders and
    `docs/` targets are dropped."""
    text = Path(file).read_text(encoding="utf-8", errors="replace")
    return referenced_paths_in_text(text)


def referenced_paths_in_text(text: str) -> "set[str]":
    found: set = set()
    for pattern in (_PLUGIN_ROOT_REF, _COORDINATOR_REF):
        for match in pattern.finditer(text):
            nxt = text[match.end() : match.end() + 1]
            raw = match.group(1)
            if nxt and nxt in _PLACEHOLDER_NEXT:
                continue
            if raw.endswith("/") or ".." in raw or "//" in raw:
                continue
            found.add(_clean(raw))
    tops = _toplevel_names()
    for match in _JOIN_CHAIN.finditer(text):
        segments = _JOIN_SEGMENT.findall(match.group(0))
        if len(segments) < 2 or segments[0] not in tops:
            continue
        if not _HAS_EXTENSION.search(segments[-1]):
            continue
        found.add("/".join(segments))
    return {p for p in found if p and not p.startswith("docs/") and p != "docs"}


def _toplevel_names() -> frozenset:
    comp = _composition()
    names = {e.split("/", 1)[0] for e in comp.allow}
    names.update(comp.routed)
    return frozenset(names)


def _tracked_plugin_paths() -> frozenset:
    tracked = _oss_payload._git_ls_files(REPO_ROOT, "coordinator")
    return frozenset(p[len("coordinator/") :] for p in tracked)


def surface_files() -> "tuple[Path, ...]":
    """Absolute paths of the shipped, locally-enumerable referrer files: allowlisted tracked
    files under the prompt/hook/doc directories, text suffixes only."""
    out = []
    for rel in _oss_payload.local_payload_files():
        parts = rel.parts
        if len(parts) < 3 or parts[0] != "coordinator" or parts[1] not in _SURFACE_DIRS:
            continue
        if rel.suffix not in _TEXT_SUFFIXES:
            continue
        if (REPO_ROOT / rel).is_file():
            out.append(REPO_ROOT / rel)
    return tuple(out)


@dataclass
class ScanResult:
    #: referrer (repo-relative POSIX) -> targets that are in the authoring tree yet not shipped
    missing: dict = field(default_factory=dict)
    #: referrer -> engine-routed targets that cannot be verified without an export root
    unverified: dict = field(default_factory=dict)

    def pairs(self, which: str) -> "set[tuple[str, str]]":
        data = getattr(self, which)
        return {(ref, tgt) for ref, tgts in data.items() for tgt in tgts}


def scan(files=None, root: "Path | None | str" = "env", tracked=None) -> ScanResult:
    """Check every referenced path of `files` (default: all shipped surfaces) against the set.

    A target counts only when it exists in the authoring tree (tracked) or is engine-routed; a path
    that exists nowhere is a dangling pointer, owned by the pointer detector."""
    tracked = _tracked_plugin_paths() if tracked is None else tracked
    comp = _composition()
    result = ScanResult()
    for file in surface_files() if files is None else files:
        file = Path(file)
        try:
            referrer = file.resolve().relative_to(REPO_ROOT).as_posix()
        except ValueError:
            referrer = file.as_posix()
        for target in sorted(referenced_paths(file)):
            engine = any(_under(target, e) for e in comp.routed)
            if not engine and target not in tracked:
                continue
            verdict = classify(target, root)
            if verdict == NOT_SHIPPED:
                result.missing.setdefault(referrer, set()).add(target)
            elif verdict == UNVERIFIED:
                result.unverified.setdefault(referrer, set()).add(target)
    return result


def unbaselined(observed: "set[tuple[str, str]]", baseline: dict) -> "list[tuple[str, str]]":
    """Observed (referrer, target) failures the baseline does not list."""
    allowed = {(ref, tgt) for ref, tgts in baseline.items() for tgt in tgts}
    return sorted(observed - allowed)
