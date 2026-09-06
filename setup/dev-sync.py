#!/usr/bin/env python3
from __future__ import annotations
"""
dev-sync.py — sync coordinator-claude plugin source to Claude Code's cache.

For plugin developers: run after editing plugin files to make changes take
effect without restarting Claude Code or bumping versions.

Claude Code caches plugins by version. Edits to source files don't
propagate to the cache automatically. This script bridges that gap.

Usage:
    python3 setup/dev-sync.py              # sync all plugins
    python3 setup/dev-sync.py coordinator  # sync one plugin

Requires: the plugins were previously installed via setup/install.py
(so the cache directory structure exists).

DELIBERATELY SELF-CONTAINED — not a claude-klabauter direct-import trampoline (unlike
most other bash-to-Python ports in this migration). This file percolates
verbatim into the standalone OSS `coordinator-claude` publish repo
(`setup/dev-sync.py` there — see dist/publish-repo-setup/README.md), which
ships to third-party plugin developers with NO `claude-klabauter` sibling
clone, no `coordinator_core`, and no `.claude-klabauter-root` machine-local pointer.
A `from coordinator_core.ops.dev_sync import main` trampoline would resolve
the live-working-tree engine root — COORDINATOR_ENGINE_ROOT — successfully on
a Claude-Central/DoE developer machine but raise/exit-1 for every OSS
consumer — silently breaking the shipped tool.
This script therefore ports the bash oracle's logic directly, with zero
external imports beyond the stdlib. A behavior-equivalent copy also lives
Claude-klabauter-side at coordinator_core/ops/dev_sync.py (co-located pytest suite)
for engine-tree test coverage / potential future reuse from Claude-Central
tooling — that module is NOT imported by this file and the two must be
kept in sync by hand if either changes.

Exit codes (parity-critical, preserved from the bash oracle):
    0 — sync completed (including all-SKIP runs)
    1 — safety-guard trip only: cache_target computed empty, or resolved
        outside $HOME/.claude/plugins/cache — refuses to `rm -rf` and aborts

Port source: coordinator/dist/publish-repo-setup/dev-sync.py (self; prior
bash body ported in place — see git log for the original implementation)
Spec backlink: docs/plans/2026-07-15-bash-to-naked-python-engine-migration.md

Negative-spec (retired/never-had patterns — do NOT reintroduce):
    - Does NOT touch ~/.claude/plugins/marketplaces/ — cache tree only.
    - Does NOT bump plugin.json version — human-driven, separate step.
    - Does NOT recurse into plugins/*/ beyond one level.
    - Does NOT import coordinator_core / claude-klabauter — see rationale above.
    - Does NOT reproduce the bash oracle's `find ... | wc -l` leading-space
      padding on the SYNC line's file count (e.g. bash prints
      "—        2 files", this prints "— 2 files"). That padding is BSD-
      vs-GNU-`wc`-width-dependent — not meaningful content, cosmetic
      console-only noise never parsed downstream — so reproducing it
      byte-exact would itself be a portability bug, not fidelity.
"""

import json
import os
import shutil
import sys
from pathlib import Path
from typing import List, Optional

MARKETPLACE = "coordinator-claude"


def _read_version(plugin_json: Path) -> Optional[str]:
    try:
        data = json.loads(plugin_json.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    version = data.get("version")
    if not isinstance(version, str) or not version:
        return None
    return version


def _sync_plugin(name: str, source_dir: Path, cache_dir: Path) -> str:
    src = source_dir / name
    if not src.is_dir():
        return f"  SKIP: {name} (source dir not found)"

    plugin_json = src / ".claude-plugin" / "plugin.json"
    if not plugin_json.is_file():
        return f"  SKIP: {name} (no .claude-plugin/plugin.json)"

    version = _read_version(plugin_json)
    if not version:
        return f"  SKIP: {name} (couldn't read version)"

    cache_target = cache_dir / name / version

    lines: List[str] = []
    if not cache_target.is_dir():
        lines.append(f"  NEW:  {name} ({version}) — creating cache dir")
        cache_target.mkdir(parents=True, exist_ok=True)

    orphaned_at_path = cache_target / ".orphaned_at"
    orphaned_at = orphaned_at_path.read_text() if orphaned_at_path.is_file() else None

    # Safety guard (issue #13): never rm -rf an empty path or a path outside
    # the expected plugins cache root.
    cache_target_str = str(cache_target)
    if not cache_target_str:
        print("  ERROR: cache_target is empty — refusing to clean. Aborting.", file=sys.stderr)
        sys.exit(1)
    expected_prefix = str(Path.home() / ".claude" / "plugins" / "cache")
    if not (cache_target_str == expected_prefix or cache_target_str.startswith(expected_prefix + os.sep)):
        print(
            f"  ERROR: cache_target ({cache_target_str}) is not under {expected_prefix} — "
            "refusing to clean. Aborting.",
            file=sys.stderr,
        )
        sys.exit(1)

    if cache_target.is_dir():
        for child in cache_target.iterdir():
            if child.name == ".orphaned_at":
                continue
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)

    shutil.copytree(src, cache_target, dirs_exist_ok=True)

    if orphaned_at is not None:
        orphaned_at_path.write_text(orphaned_at)

    file_count = sum(1 for p in cache_target.rglob("*") if p.is_file())
    lines.append(f"  SYNC: {name} ({version}) — {file_count} files")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    script_path = Path(os.path.abspath(__file__))
    repo_root = script_path.parent.parent
    source_dir = repo_root / "plugins"
    cache_dir = Path.home() / ".claude" / "plugins" / "cache" / MARKETPLACE

    target = argv[0] if argv else ""

    print(f"dev-sync: {source_dir} → cache")
    print("")

    if target:
        print(_sync_plugin(target, source_dir, cache_dir))
    else:
        if source_dir.is_dir():
            for entry in sorted(source_dir.iterdir()):
                if entry.is_dir():
                    print(_sync_plugin(entry.name, source_dir, cache_dir))

    print("")
    print("Done. Changes take effect on next Claude Code session (or next hook invocation for hooks).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
