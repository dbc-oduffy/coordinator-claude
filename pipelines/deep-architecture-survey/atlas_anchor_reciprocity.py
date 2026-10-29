"""Atlas anchor-reciprocity and repo-root-relative path check (stdlib only).

Reads <repo-root>/<atlas-dir>/systems/*.md frontmatter and file-index.md.
Exit 1 lists each one-sided connection pair (A lists B, B does not list A, and
the pair is not recorded under A's or B's `one_sided_connections`) and each path
that is not repo-root-relative. Exit 0 on a reciprocal, clean atlas.

Edges come from the list-valued `connected_systems` key, or from
`cross_system_connections` when it is a list (a bare count carries no edges).
Path keys checked: any frontmatter key named path/paths/file/files or ending in
`_path`/`_paths`/`_file`/`_files`, plus every `<path> -> <system>` line of
file-index.md.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")
_PATH_KEY = re.compile(r"^(path|paths|file|files|.*_(path|paths|file|files))$")


def _scalar(text: str):
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text


def _split_inline_list(text: str) -> list[str]:
    inner = text.strip()[1:-1]
    return [_scalar(p) for p in inner.split(",") if p.strip()]


def parse_frontmatter(text: str) -> dict:
    """Minimal YAML reader: scalars, inline `[a, b]` lists, and `- item` block lists."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    data: dict = {}
    current: str | None = None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        item = re.match(r"^\s+-\s+(.*)$", line)
        if item and current is not None:
            if not isinstance(data.get(current), list):
                data[current] = []
            data[current].append(_scalar(item.group(1)))
            continue
        kv = re.match(r"^([A-Za-z0-9_.-]+):\s*(.*)$", line)
        if not kv:
            continue
        current = kv.group(1)
        raw = kv.group(2).split(" #")[0].strip()
        if raw.startswith("[") and raw.endswith("]"):
            data[current] = _split_inline_list(raw)
        elif raw == "":
            data[current] = None
        else:
            data[current] = _scalar(raw)
    return data


def bad_path_reason(path: str) -> str | None:
    p = path.strip()
    if not p:
        return None
    if p.startswith("/"):
        return "leading '/'"
    if p.startswith("./") or p.startswith(".\\"):
        return "leading './'"
    if _DRIVE.match(p):
        return "drive letter"
    return None


def _as_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    return []


def check_atlas(atlas: Path) -> list[str]:
    problems: list[str] = []
    systems_dir = atlas / "systems"
    edges: dict[str, set[str]] = {}
    recorded: set[frozenset[str]] = set()
    for page in sorted(systems_dir.glob("*.md")) if systems_dir.is_dir() else []:
        fm = parse_frontmatter(page.read_text(encoding="utf-8", errors="replace"))
        name = str(fm.get("system") or page.stem)
        conns = _as_list(fm.get("connected_systems")) or _as_list(
            fm.get("cross_system_connections")
        )
        edges[name] = {c.strip() for c in conns if c.strip()}
        for other in _as_list(fm.get("one_sided_connections")):
            recorded.add(frozenset((name, other.strip())))
        for key, value in fm.items():
            if not _PATH_KEY.match(key):
                continue
            for entry in value if isinstance(value, list) else [value]:
                reason = bad_path_reason(str(entry or ""))
                if reason:
                    problems.append(
                        f"non-repo-root-relative path ({reason}): {page.name} {key}: {entry}"
                    )
    for a in sorted(edges):
        for b in sorted(edges[a]):
            if a in edges.get(b, set()):
                continue
            if frozenset((a, b)) in recorded:
                continue
            problems.append(f"one-sided connection: {a} -> {b} (no {b} -> {a})")
    index = atlas / "file-index.md"
    if index.is_file():
        for line in index.read_text(encoding="utf-8", errors="replace").splitlines():
            if "->" not in line or line.lstrip().startswith(">"):
                continue
            reason = bad_path_reason(re.sub(r"^\s*(?:[-*]\s+|\|\s*)?`?", "", line.split("->")[0]))
            if reason:
                problems.append(
                    f"non-repo-root-relative path ({reason}): file-index.md: {line.strip()}"
                )
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo-root", type=Path, default=Path.cwd())
    ap.add_argument("--atlas-dir", default="docs/architecture")
    args = ap.parse_args(argv)
    atlas = args.repo_root / args.atlas_dir
    if not (atlas / "systems").is_dir() and (args.repo_root / "systems").is_dir():
        atlas = args.repo_root
    if not (atlas / "systems").is_dir():
        print(f"no systems/ directory under {atlas}: wrong --repo-root/--atlas-dir or atlas not written")
        return 1
    problems = check_atlas(atlas)
    for p in problems:
        print(p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
