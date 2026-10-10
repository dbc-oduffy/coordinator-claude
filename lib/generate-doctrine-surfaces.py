"""coordinator/lib/generate-doctrine-surfaces.py — emits
coordinator/doctrine-surfaces.json, the DoE-supplied doctrine-surface
manifest consumed by claude-klabauter's
`coordinator_core.ops.verify_skill_anchor_links`.

WHY THIS EXISTS. That gate resolves each `<path>.md § <section>` citation
path-directed, against the file it names. A citation naming
`~/.claude/CLAUDE.md` — a derived artifact with no in-repo file of its own —
resolves to nothing the gate can check, so it is recorded QUALIFIED and
skipped rather than genuinely verified. Only this repo knows that its
in-repo canonical for that derived path is `global-doctrine/CLAUDE.md`.
Supplying that mapping, plus the full set of doctrine homes this repo owns,
upgrades those citations from QUALIFIED to real OK/DEAD verdicts.

`surfaces` is DERIVED, never hand-listed: a hand-written index rots into
plausible findings the moment a snippet or wiki page is added or removed
without updating it in lockstep — the exact failure class this manifest
exists to prevent on the consumer side. Re-running this generator is the
only way `surfaces` changes; `coordinator/tests/test_doctrine_surfaces_manifest.py`
fails the pytest tier (which gates merge and percolate) the moment the
committed file drifts from what this generator produces now.

`aliases` carries only mappings that genuinely cannot be derived from a tree
walk — see `ALIASES` below for the one entry and why it's there.

No section headings are ever emitted here. The consumer extracts headings
live from the files this manifest names; snapshotting them here would rot
against the very files the manifest indexes.

Usage:
    python coordinator/lib/generate-doctrine-surfaces.py           # write
    python coordinator/lib/generate-doctrine-surfaces.py --check   # verify, exit 1 on drift

Spec backlink: state/plans/2026-08-05-doctrine-surfaces-manifest-emission.md
"""
from __future__ import annotations

import difflib
import json
import os
import sys
from pathlib import Path

SCHEMA_VERSION = 1

MANIFEST_BASENAME = "doctrine-surfaces.json"

#: Mappings that cannot be computed from a repo-tree walk because the cited
#: form names a path that does not exist in this repo at all — it names a
#: DERIVED artifact (a hook-rendered file living outside this repo's own
#: tree) whose in-repo canonical source lives here under a different path.
#: `~/.claude/CLAUDE.md` is re-derived from `global-doctrine/CLAUDE.md` by a
#: hook (see this repo's own CLAUDE.md, "Four `CLAUDE.md`-class surfaces");
#: the path-directed resolver has no way to discover that relationship on
#: its own, so it is supplied here explicitly. Do not add entries the
#: path-directed resolver already handles by walking the tree.
ALIASES = {
    "~/.claude/CLAUDE.md": "global-doctrine/CLAUDE.md",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _walk_wiki_dir(wiki_dir: Path) -> list[Path]:
    """Recursive walk of `docs/wiki/`, `<name>/README.md`-aware.

    A split subdirectory (C10's `generate-doctrine-surface-split.py` shape:
    `<name>/` holding split body files plus a generated `README.md` index)
    contributes only its `README.md` as the surface representing `<name>` —
    sibling body files inside that directory are not separately listed as
    top-level guides. Any other directory, at any depth, lists every `.md`
    file it directly contains except the generated `_index.md` navigation
    page, which is not a doctrine surface."""
    found: list[Path] = []
    for dirpath, _dirnames, filenames in os.walk(wiki_dir):
        d = Path(dirpath)
        if d != wiki_dir and "README.md" in filenames:
            found.append(d / "README.md")
            continue
        found.extend(
            d / f for f in sorted(filenames) if f.endswith(".md") and f != "_index.md"
        )
    return found


def compute_surfaces(repo_root: Path) -> list[str]:
    """Every doctrine home in this repo, repo-relative, sorted for a stable
    diff. `coordinator/CLAUDE.md` is included only when present — it does
    not exist as of this generator's authoring, but doctrine evolves."""
    surfaces: list[str] = []

    global_claude_md = repo_root / "global-doctrine" / "CLAUDE.md"
    if global_claude_md.is_file():
        surfaces.append("global-doctrine/CLAUDE.md")

    coordinator_claude_md = repo_root / "coordinator" / "CLAUDE.md"
    if coordinator_claude_md.is_file():
        surfaces.append("coordinator/CLAUDE.md")

    snippets_dir = repo_root / "coordinator" / "snippets"
    if snippets_dir.is_dir():
        for f in snippets_dir.glob("*.md"):
            surfaces.append(f.relative_to(repo_root).as_posix())

    wiki_dir = repo_root / "coordinator" / "docs" / "wiki"
    if wiki_dir.is_dir():
        for f in _walk_wiki_dir(wiki_dir):
            surfaces.append(f.relative_to(repo_root).as_posix())

    return sorted(surfaces)


def build_manifest(repo_root: Path) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "surfaces": compute_surfaces(repo_root),
        "aliases": dict(ALIASES),
    }


def render(manifest: dict) -> str:
    return json.dumps(manifest, indent=2, sort_keys=False) + "\n"


def manifest_path(repo_root: Path) -> Path:
    return repo_root / "coordinator" / MANIFEST_BASENAME


def main(argv: list[str]) -> int:
    repo_root = _repo_root()
    check_mode = "--check" in argv

    manifest = build_manifest(repo_root)
    rendered = render(manifest)
    target = manifest_path(repo_root)

    if check_mode:
        on_disk = target.read_text(encoding="utf-8") if target.is_file() else ""
        if on_disk == rendered:
            return 0
        diff = "".join(
            difflib.unified_diff(
                on_disk.splitlines(keepends=True),
                rendered.splitlines(keepends=True),
                fromfile=str(target),
                tofile="<generated>",
            )
        )
        print(diff, file=sys.stderr)
        return 1

    # LF is pinned here rather than left to `.gitattributes`: universal-newline
    # mode would write os.linesep on a Windows author's machine, making the
    # generator's own output platform-dependent.
    target.write_text(rendered, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
