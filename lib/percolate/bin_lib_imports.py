"""Every coordinator/lib module a published coordinator/bin script imports must
publish too: klabauter's bin resolves `lib/` siblings inside klabauter alone, and a
withheld one is a ModuleNotFoundError on every host that forwards to it
(statusline, 2026-10-04: compaction_defaults and win_portability were never in
the lib row and every status bar on the box went blank).

The walk covers the whole AST, so a lazy import inside a function counts.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, Iterable, List, Set

BIN_ROW = "claude-klabauter-coordinator-bin"
LIB_ROW = "claude-klabauter-coordinator-lib"


def field7(targets_text: str, row: str) -> Set[str]:
    for line in targets_text.splitlines():
        fields = line.split("|")
        if fields[0] == row and len(fields) > 6:
            return {e for e in fields[6].split(",") if e and not e.startswith("!")}
    raise KeyError(row)


def _lib_modules(lib_dir: Path) -> Dict[str, str]:
    mods = {p.stem: p.name for p in lib_dir.glob("*.py")}
    mods.update({p.name: p.name for p in lib_dir.iterdir() if (p / "__init__.py").is_file()})
    return mods


def _imported_tops(path: Path) -> Set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return set()
    tops: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            tops.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            tops.add(node.module.split(".")[0])
    return tops


def unpublished_lib_imports(bin_files: Iterable[Path], lib_dir: Path, published_lib: Set[str]) -> Dict[str, List[str]]:
    """`{lib file name: [importing bin files]}` for every lib module imported but withheld."""
    lib_mods = _lib_modules(lib_dir)
    missing: Dict[str, List[str]] = {}
    for f in bin_files:
        for top in sorted(_imported_tops(f)):
            name = lib_mods.get(top)
            if name and name not in published_lib:
                missing.setdefault(name, []).append(f.as_posix())
    return missing
