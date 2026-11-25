"""Resolve the throwaway-scratch directory for a writer: `paths.scratch_root` when it names an existing directory, else `<repo>/scratch`.

Only throwaway, TEMP-class output belongs here; anything read back stays in the repo.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from types import ModuleType

SCRATCH_ROOT_KEY = "paths.scratch_root"

_KERNEL: ModuleType | None = None


def _settings_home() -> Path:
    env = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if env:
        return Path(env)
    return Path(os.environ.get("CLAUDE_HOME") or Path.home()) / ".coordinator-claude-settings"


def _kernel() -> ModuleType:
    """The machine-local kernel, loaded once from the settings-home install, else this plugin's template copy.

    Trap: never spawn the machine-local CLI here; each spawn costs a process per scratch write.
    """
    global _KERNEL
    if _KERNEL is not None:
        return _KERNEL
    candidates = (
        _settings_home() / "bin" / "_machine_local.py",
        Path(__file__).resolve().parents[2] / "templates" / "bin" / "_machine_local.py",
    )
    for impl in candidates:
        if not impl.is_file():
            continue
        spec = importlib.util.spec_from_file_location("_machine_local_kernel_scratch_root", impl)
        if spec is None or spec.loader is None:
            continue
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _KERNEL = mod
        return mod
    raise RuntimeError("machine-local kernel not found")


def _root_from_registry() -> Path | None:
    """The configured scratch root when set and an existing directory; None on any miss or read error."""
    try:
        kernel = _kernel()
        layers = kernel._build_resolution_layers(kernel._registry_dir())
        rc, value = kernel.resolve_one(SCRATCH_ROOT_KEY, layers)
        if rc != kernel.EXIT_OK or not value or not value.strip():
            return None
        root = Path(value.strip()).expanduser()
        return root if root.is_dir() else None
    except (Exception, SystemExit):
        return None


def scratch_dir(repo: Path, tool: str, run_id: str) -> Path:
    """Create and return the scratch leaf for one run.

    `<paths.scratch_root>/<repo dir name>/<tool>/<run_id>` when the key names an existing
    directory, else `<repo>/scratch/<tool>/<run_id>`. The root itself is never created.
    """
    for part in (tool, run_id):
        if not part or part.startswith(".") or "/" in part or "\\" in part:
            raise ValueError(f"scratch path segment must be a plain name: {part!r}")
    repo = Path(repo)
    root = _root_from_registry()
    base = root / repo.resolve().name if root is not None else repo / "scratch"
    leaf = base / tool / run_id
    leaf.mkdir(parents=True, exist_ok=True)
    return leaf
