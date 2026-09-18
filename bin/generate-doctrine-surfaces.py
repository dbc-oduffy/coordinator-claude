#!/usr/bin/env python3
"""coordinator/bin/generate-doctrine-surfaces.py — emits
<DoE-claude>/coordinator/doctrine-surfaces.json, the DoE-supplied
doctrine-surface manifest consumed by claude-klabauter's
`coordinator_core.ops.verify_skill_anchor_links`.

WHY THIS EXISTS. That gate resolves each `<path>.md § <section>` citation
path-directed, against the file it names. A citation naming
`~/.claude/CLAUDE.md` — a derived artifact with no in-repo file of its own —
resolves to nothing the gate can check, so it is recorded QUALIFIED and
skipped rather than genuinely verified. Only DoE-claude knows that its
in-repo canonical for that derived path is `global-doctrine/CLAUDE.md`.
Supplying that mapping, plus the full set of doctrine homes DoE-claude owns,
upgrades those citations from QUALIFIED to real OK/DEAD verdicts.

`surfaces` is DERIVED, never hand-listed: a hand-written index rots into
plausible findings the moment a snippet or wiki page is added or removed
without updating it in lockstep — the exact failure class this manifest
exists to prevent on the consumer side. Re-running this generator is the
only way `surfaces` changes; DoE-claude's own pytest tier fails the moment
the committed file drifts from what this generator produces now.

`aliases` carries only mappings that genuinely cannot be derived from a tree
walk — see `ALIASES` below for the one entry and why it's there.

No section headings are ever emitted here. The consumer extracts headings
live from the files this manifest names; snapshotting them here would rot
against the very files the manifest indexes.

Usage:
    python coordinator/bin/generate-doctrine-surfaces.py           # write
    python coordinator/bin/generate-doctrine-surfaces.py --check   # verify, exit 1 on drift

DOE-INTERNAL. This CLI generates a file that lives and is committed inside
the DoE-claude checkout (`<doe_root>/coordinator/doctrine-surfaces.json`),
never anything in this repo — claude-klabauter owns and runs it, DoE-claude is where
its output lands.

Path resolution: "doctrine asset" class (§ Path resolution,
docs/plans/2026-09-18-doe-holds-no-scripts.md), resolved through the plugin
root exactly as that section names: `coordinator_core.warm.caller_context ::
resolve_caller_context`, falling back to
`coordinator_core.subagent_sandbox.provision_report :: resolve_plugin_root`'s
own three-rung ambient probe (`CLAUDE_PLUGIN_ROOT` env var -> plugin dir ->
`.doe-root` pointer) — the same pair chunk W2-C9's mise-prep-entry.py already
uses for its own doctrine-asset seam. The DoE original derived its own repo
root from `Path(__file__).resolve().parent.parent.parent` — the
DoE-claude@b644d5a9 lesson this whole wave exists to fix: that resolved
correctly only so long as the file stayed inside DoE-claude's own
`coordinator/lib/`. Arriving here, `__file__` resolves inside claude-klabauter's own
tree, which has neither a `global-doctrine/` nor a `coordinator/docs/wiki/`
to walk. A bare CLI invocation of this script (no warm-server payload in
front of it) is exactly the "genuinely fresh dispatch" case
`resolve_caller_context`'s own docstring names for its no-payload call —
this module calls it with no payload, so it degrades straight to
`resolve_plugin_root()`'s ambient probe.

Arrived from DoE-claude coordinator/lib/generate-doctrine-surfaces.py
(docs/plans/2026-09-18-doe-holds-no-scripts.md, chunk W3-C6).
Spec backlink: state/plans/2026-08-05-doctrine-surfaces-manifest-emission.md
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import sys
from pathlib import Path

#: Populated by `_resolve_caller_context()`, deferred out of module scope so the non-stdlib
#: import it performs is not a module-body-inertness violation
#: (`coordinator_core.warm.serve_classifier`). Left resolvable as a plain module attribute (not a
#: PEP 562 `__getattr__` shim) so `test_arrival_generate_doctrine_surfaces.py`'s
#: `monkeypatch.setattr(gds, "resolve_caller_context", ...)` keeps working unchanged.
resolve_caller_context = None  # type: ignore[assignment]

SCHEMA_VERSION = 1

MANIFEST_BASENAME = "doctrine-surfaces.json"

#: Mappings that cannot be computed from a repo-tree walk because the cited
#: form names a path that does not exist in DoE-claude's repo at all — it
#: names a DERIVED artifact (a hook-rendered file living outside that repo's
#: own tree) whose in-repo canonical source lives there under a different
#: path. `~/.claude/CLAUDE.md` is re-derived from `global-doctrine/CLAUDE.md`
#: by a hook; the path-directed resolver has no way to discover that
#: relationship on its own, so it is supplied here explicitly. Do not add
#: entries the path-directed resolver already handles by walking the tree.
ALIASES = {
    "~/.claude/CLAUDE.md": "global-doctrine/CLAUDE.md",
}


def _repo_root() -> Path:
    """The DoE-claude checkout root this generator walks.

    `resolve_caller_context().plugin_root` is a CONTENT root (DoE-claude's
    `coordinator/` subdir) one level below the repo root this generator's
    output paths are relative to — this generator's own `global-doctrine/`
    lookup is a sibling of that subdir, not inside it."""
    global resolve_caller_context
    if resolve_caller_context is None:
        from coordinator_core.warm.caller_context import resolve_caller_context as _rcc

        resolve_caller_context = _rcc

    plugin_root = resolve_caller_context().plugin_root
    if plugin_root is None:
        raise RuntimeError(
            "generate-doctrine-surfaces: cannot resolve the DoE-claude plugin "
            "root -- resolve_caller_context().plugin_root returned no result. "
            "Set CLAUDE_PLUGIN_ROOT, or register the coordinator-claude plugin "
            "install / .doe-root pointer (see resolve_plugin_root())."
        )
    return Path(plugin_root).resolve().parent


def _walk_wiki_dir(wiki_dir: Path) -> list[Path]:
    """Recursive walk of `docs/wiki/`, `<name>/README.md`-aware.

    A split subdirectory (`generate-doctrine-surface-split.py`'s shape:
    `<name>/` holding split body files plus a generated `README.md` index)
    contributes only its `README.md` as the surface representing `<name>` —
    sibling body files inside that directory are not separately listed as
    top-level guides. A directory with no `README.md` lists every `.md`
    file it directly contains. Applied at every depth via `os.walk`."""
    found: list[Path] = []
    for dirpath, _dirnames, filenames in os.walk(wiki_dir):
        d = Path(dirpath)
        md_files = sorted(f for f in filenames if f.endswith(".md"))
        depth = len(d.relative_to(wiki_dir).parts)
        if d == wiki_dir:
            found.extend(d / f for f in md_files)
        elif "README.md" in filenames:
            found.append(d / "README.md")
        elif depth > 1:
            # The documented split shape is exactly one level deep: `<name>/`
            # holding flat body files plus a generated `README.md`. A
            # directory nested deeper than that with no `README.md` of its
            # own has no sanctioned shape to fall back to; silently listing
            # every `.md` file inside it (the branch below) would diverge
            # from "one entry per split page" without any signal. Loud is
            # correct here, same posture as the split mechanism itself.
            raise ValueError(
                f"{d} is a wiki subdirectory nested deeper than one level below "
                f"{wiki_dir}, with no README.md of its own -- the documented split "
                "shape is one level deep only; either give it a README.md or "
                "restructure it, rather than let it fall through to a per-file listing"
            )
        else:
            found.extend(d / f for f in md_files)
    return found


def compute_surfaces(repo_root: Path) -> list[str]:
    """Every doctrine home in DoE-claude's repo, repo-relative, sorted for a
    stable diff. `coordinator/CLAUDE.md` is included only when present — it
    does not exist as of this generator's authoring, but doctrine evolves."""
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").strip().splitlines()[0])
    parser.add_argument(
        "--check", action="store_true", help="diff the manifest against a fresh render; write nothing"
    )
    check_mode = parser.parse_args(argv).check
    repo_root = _repo_root()

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
