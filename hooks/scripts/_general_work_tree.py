"""Full coordinator-repo tree seeding for the general-work root.

`seed_full_tree` converges a root toward the tree repo-setup gives any repo: the engine's
`scaffold_canonical_structure` against the plugin's `canonical-structure.yaml` (no parallel list of dirs
lives here), plus the general-work extras (`archive/`, `coordinator.local.md`, the canonical
`.gitignore` block, `state/orientation_cache.md`). It returns the manifest, `archive/` and
`coordinator.local.md` paths that exist after convergence (seeded now or earlier); content outside
that set, such as a pre-existing `tax-2025/`, is never named. TRAP: the legacy `[general-work]` brackets are glob
metacharacters, so the root is never handed to glob/fnmatch. Best-effort: never raises.
"""

from __future__ import annotations

from pathlib import Path

import _engine_root

_FALLBACK_KEEPS = (
    "state/handoffs/.gitkeep",
    "state/cross-repo/inbox/.gitkeep",
    "docs/plans/.gitkeep",
)
_ARCHIVE_KEEP = "archive/.gitkeep"
_LOCAL_MD = "coordinator.local.md"
_LOCAL_MD_BODY = "---\nproject_type: general\n---\n"
_ORIENTATION = "state/orientation_cache.md"
_ORIENTATION_BODY = "## Active workstreams\n\n## Branch\n\n## Pinboard\n"
_GITIGNORE_TEMPLATE = Path("skills") / "repo-setup" / "templates" / "gitignore.project.template"


def _write_new(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "x", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def _touch_keep(root: Path, rel: str) -> None:
    target = root / rel
    if not target.exists():
        _write_new(target, "")


def _manifest_paths(root: Path, manifest_root: Path) -> list[str] | None:
    """Scaffold live and return the commit-eligible manifest paths, or None when the engine is unusable."""
    try:
        engine = _engine_root.resolve_claude_klabauter_root()
        if not engine:
            return None
        _engine_root.place_engine_root_on_path(engine)
        from coordinator_core.install import scaffold_structure as ss

        ss.scaffold_canonical_structure(root, manifest_root)
        parsed = ss.parse_manifest(ss.locate_manifest(manifest_root).read_text(encoding="utf-8"))
    except Exception:
        return None
    found: list[str] = []
    for entry in parsed.entries:
        if entry.is_dir:
            base = entry.path.rstrip("/")
            name = ".gitkeep" if entry.gitkeep else ("README.md" if entry.readme else "")
            rel = f"{base}/{name}" if name else ""
        else:
            rel = entry.path
        if rel and (root / rel).is_file():
            found.append(rel)
    return found


def _append_gitignore_block(root: Path, manifest_root: Path) -> None:
    template = manifest_root / _GITIGNORE_TEMPLATE
    if not template.is_file():
        return
    target = root / ".gitignore"
    existing = target.read_text(encoding="utf-8") if target.is_file() else ""
    have = {line.strip() for line in existing.splitlines()}
    missing = [
        line.rstrip()
        for line in template.read_text(encoding="utf-8").splitlines()
        if line.strip() and line.strip() not in have
    ]
    if not missing:
        return
    lead = "" if not existing or existing.endswith("\n") else "\n"
    with open(target, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(lead + "\n".join(missing) + "\n")


def seed_full_tree(root: Path, manifest_root: Path) -> list[str]:
    """Create every missing path of the full coordinator tree under `root`.

    Returns the root-relative posix paths that exist and may be committed. `.gitignore` and
    `state/orientation_cache.md` are created but not returned (the caller owns `.gitignore`;
    the cache is gitignored).
    """
    root = Path(root)
    manifest_root = Path(manifest_root)
    try:
        root.mkdir(parents=True, exist_ok=True)
        paths = _manifest_paths(root, manifest_root)
        if paths is None:
            paths = []
            for rel in _FALLBACK_KEEPS:
                _touch_keep(root, rel)
                paths.append(rel)
        _touch_keep(root, _ARCHIVE_KEEP)
        if _ARCHIVE_KEEP not in paths:
            paths.append(_ARCHIVE_KEEP)
        if not (root / _LOCAL_MD).exists():
            _write_new(root / _LOCAL_MD, _LOCAL_MD_BODY)
        if (root / _LOCAL_MD).is_file():
            paths.append(_LOCAL_MD)
        _append_gitignore_block(root, manifest_root)
        if not (root / _ORIENTATION).exists():
            _write_new(root / _ORIENTATION, _ORIENTATION_BODY)
    except Exception:
        return [p for p in (locals().get("paths") or []) if (root / p).is_file()]
    return sorted(set(paths))
