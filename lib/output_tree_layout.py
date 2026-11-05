"""output_tree_layout -- shard layout for dated record trees: LAYOUT, shard_path, resolve, stray_entries.

LAYOUT holds shape only; every tree glob is a RECORD glob of state_layout.CONTRACT. A record tree
is sharded `<tree>/<YYYY-MM>/<file>`; the month comes from a per-tree date extractor. Stdlib only;
reached by explicit path insertion (coordinator/lib is not a package). Wiki: output-tree-layout-contract.md.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

FLAT_THRESHOLD = 50
SHARD_MONTH = "month"
REDIRECTS_NAME = "REDIRECTS.md"
# Names that legitimately sit at a tree root next to the shards.
ROOT_EXEMPT_NAMES = (REDIRECTS_NAME, "INDEX.md", ".gitkeep")
ROOT_EXEMPT_PREFIXES = ("README",)

_LEADING_DATE = re.compile(r"^(\d{4})-(\d{2})-\d{2}(?!\d)")
_ASK_STAMP = re.compile(r"^ask-(\d{4})(\d{2})\d{2}T\d{6}")
_WARP_DATE = re.compile(r"^warp-(\d{4})-(\d{2})-\d{2}-")


def _month(rx: re.Pattern[str], name: str) -> str | None:
    m = rx.match(name)
    return f"{m.group(1)}-{m.group(2)}" if m else None


def _leading_date_month(name: str) -> str | None:
    return _month(_LEADING_DATE, name)


def _delivery_month(name: str) -> str | None:
    return _month(_ASK_STAMP, name) or _month(_WARP_DATE, name)


# (tree_glob, shard_rule, writer_owner); each tree_glob is a RECORD glob in state_layout.CONTRACT.
LAYOUT: tuple[tuple[str, str, str], ...] = (
    ("docs/plans/**", SHARD_MONTH, "claude-klabauter"),
    ("state/sizings/**", SHARD_MONTH, "claude-klabauter"),
    ("state/handoffs/**", SHARD_MONTH, "claude-klabauter"),
    ("docs/delivery/**", SHARD_MONTH, "claude-klabauter"),
)

_EXTRACTORS: dict[str, Callable[[str], str | None]] = {
    "docs/plans": _leading_date_month,
    "state/sizings": _leading_date_month,
    "state/handoffs": _leading_date_month,
    "docs/delivery": _delivery_month,
}


def tree_of(glob: str) -> str:
    """Return the tree directory a LAYOUT glob names (`docs/plans/**` -> `docs/plans`)."""
    return glob[:-3] if glob.endswith("/**") else glob


def trees() -> tuple[str, ...]:
    return tuple(tree_of(g) for g, _, _ in LAYOUT)


def _norm(path: str) -> str:
    p = str(path).replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p.strip("/")


def _is_exempt(name: str) -> bool:
    return name in ROOT_EXEMPT_NAMES or name.startswith(ROOT_EXEMPT_PREFIXES)


def month_for(tree: str, filename: str) -> str | None:
    """Return `YYYY-MM` for a filename under tree, or None when no extractor matches."""
    extractor = _EXTRACTORS.get(tree_of(_norm(tree)))
    if extractor is None:
        raise KeyError(f"no LAYOUT row for tree {tree!r}")
    return extractor(filename)


def shard_path(tree: str, filename: str) -> str:
    """Return the repo-relative POSIX path `<tree>/<YYYY-MM>/<filename>` a new entry belongs at.

    Raises ValueError when no extractor of the tree matches the name: such a name is a stray.
    """
    t = tree_of(_norm(tree))
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    month = month_for(t, name)
    if month is None:
        raise ValueError(f"{name!r} carries no date this tree's extractor accepts")
    return f"{t}/{month}/{name}"


def _split_cells(line: str) -> list[str]:
    return [c.strip().strip("`").strip() for c in line.strip().strip("|").split("|")]


def _redirect_target(redirects: Path, old: str) -> str | None:
    try:
        text = redirects.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = _split_cells(line)
        if len(cells) >= 2 and _norm(cells[0]) == old:
            return _norm(cells[1])
    return None


def resolve(path: str, repo_root: str | Path | None = None) -> str:
    """Return where a cited tree path lives now.

    An existing path returns itself; else the tree's REDIRECTS.md old -> new row; else the shard
    rule. A path under no LAYOUT tree, or whose name no extractor matches, returns unchanged.
    """
    p = _norm(path)
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    if (root / p).exists():
        return p
    for tree in trees():
        if not p.startswith(tree + "/"):
            continue
        hit = _redirect_target(root / tree / REDIRECTS_NAME, p)
        if hit:
            return hit
        rest = p[len(tree) + 1:]
        if "/" in rest:
            return p
        try:
            return shard_path(tree, rest)
        except ValueError:
            return p
    return p


_MONTH_DIR = re.compile(r"\d{4}-\d{2}")


def iter_tree_entries(repo_root: str | Path, tree: str, pattern: str) -> list[Path]:
    """Return sorted files matching `pattern` at a LAYOUT tree root and in every `<YYYY-MM>/` shard.

    Exempt names (REDIRECTS.md, INDEX.md, README*, .gitkeep) are skipped; a missing tree returns [].
    Raises ValueError when `tree` is not a LAYOUT tree.
    """
    t = tree_of(_norm(tree))
    if t not in trees():
        raise ValueError(f"{tree!r} is not a LAYOUT tree")
    base = Path(repo_root) / t
    if not base.is_dir():
        return []
    dirs = [base] + [
        c for c in base.iterdir() if c.is_dir() and _MONTH_DIR.fullmatch(c.name)
    ]
    out: list[Path] = []
    for d in dirs:
        out.extend(p for p in d.glob(pattern) if p.is_file() and not _is_exempt(p.name))
    return sorted(out)


def stray_entries(repo_root: str | Path) -> list[str]:
    """Return sorted repo-relative paths of files sitting at a LAYOUT tree root that belong in a shard.

    Every non-exempt root file is a stray, dated or not: an undated name has no shard to go to.
    """
    root = Path(repo_root)
    out: list[str] = []
    for tree in trees():
        d = root / tree
        if not d.is_dir():
            continue
        for child in d.iterdir():
            if child.is_file() and not _is_exempt(child.name):
                out.append(f"{tree}/{child.name}")
    return sorted(out)
