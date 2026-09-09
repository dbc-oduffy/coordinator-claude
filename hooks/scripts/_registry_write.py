"""Shared machine-local registry WRITE seam for `coordinator/hooks/scripts/*.py`.

Counterpart to `_engine_root.py`'s zero-spawn registry READ seam: this is the
one place a hook turns a decided key/value into a registry write, so there is
one implementation of "which `_machine_local.py` do we actually run".

**Why this module exists — the writer that is missing exactly when it is
needed.** `session-start-register-doe-claude-root.py` resolved its writer as
`<settings-home>/bin/_machine_local.py` and no-opped when that file was
absent. That file is written by the engine plane's installer, so the resolver
was unavailable on precisely the boxes whose registry needs self-healing: a
container that clones the fleet and installs nothing has an empty (or missing)
`<settings-home>/bin/`, so every registry self-heal in this repo silently did
nothing there and the operator met the consequence three refusals later.

**Resolution order, and why the in-tree template is a first-class rung rather
than a fallback of last resort.** `coordinator/templates/bin/_machine_local.py`
under THIS plugin tree is the SOURCE the installed copy is derived from — same
code, same `registry.local.toml` writer, same concern-namespace refusals — and
it ships with the plugin, so it is present whenever a hook is running at all.
The installed copy is still preferred when present: on an installed box it is
the live artifact, and preferring it keeps a hand-patched or migrated install
authoritative over a plugin tree that may be a different checkout.

  1. `<settings-home>/bin/_machine_local.py` — the installed implementation.
  2. `<plugin-root>/templates/bin/_machine_local.py` — the in-tree template.

**Never a hand-edit of the registry TOML.** A concurrent session may be writing
it, and `cmd_set` is idempotent, atomic, and concern-aware in ways a hand-rolled
append is not — see `docs/wiki/machine-local-registry.md` § "Use this instead of
editing registry files by hand". This module runs that writer; it never composes
TOML.

**This module never decides WHETHER to write** — that judgement (idempotence,
never-overwrite, wrong-repo guards) belongs to each calling hook, which has the
context. This module only executes a write the caller already decided on.

Contract: `machine_local_set` returns `None` unconditionally and never raises,
never prints, never exits non-zero. Every failure mode — unresolvable settings
home, no implementation on either rung, a permissions error, a spawn failure, a
timeout — degrades to a silent no-op. Its callers are SessionStart hooks, where
a raised exception greets every session in the fleet with a stack trace.

Multi-OS: invoked as `sys.executable <impl>.py …`, which is correct on macOS,
Windows and Linux alike — never a shell, never a `.cmd`/`.ps1` leg, never a
bare-name PATH lookup. `CREATE_NO_WINDOW` suppresses the Windows console flash
under a headless SessionStart parent and degrades to a harmless `0` elsewhere.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

try:
    from _engine_root import _find_plugin_root, _settings_home
except Exception:  # pragma: no cover - partial-deploy defence
    def _find_plugin_root(start):  # type: ignore[no-redef]
        return None

    def _settings_home():  # type: ignore[no-redef]
        return None


#: Below the 15s whole-process timeout of the async SessionStart fan-in that
#: hosts this module's callers, so the in-process catch fires and returns on
#: the graceful path rather than losing the race to the harness hard-kill.
_SPAWN_TIMEOUT_SECONDS = 6


def resolve_machine_local_impl() -> Path | None:
    """The `_machine_local.py` this box can actually run, or `None`.

    See the module docstring for the two rungs and why the in-tree template is
    a real rung. Never raises; any resolution failure yields `None`.
    """
    try:
        home = _settings_home()
    except Exception:
        home = None
    if home is not None:
        try:
            installed = Path(home) / "bin" / "_machine_local.py"
            if installed.is_file():
                return installed
        except Exception:
            pass

    try:
        plugin_root = _find_plugin_root(Path(__file__).resolve().parent)
        if plugin_root is not None:
            template = plugin_root / "templates" / "bin" / "_machine_local.py"
            if template.is_file():
                return template
    except Exception:
        pass

    return None


def machine_local_set(key: str, value: str) -> None:
    """Run `machine-local set <key> <value>`. Fail-open, silent, never raises.

    The registry directory is created first when absent: `cmd_set` writes
    `<registry-dir>/registry.local.toml` and does not itself bootstrap a
    settings home that has never been installed into, which is the state this
    whole seam exists to survive.
    """
    impl = resolve_machine_local_impl()
    if impl is None:
        return
    try:
        home = _settings_home()
        if home is not None:
            (Path(home) / "machine-local").mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    try:
        subprocess.run(
            [sys.executable, str(impl), "set", key, value],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=_SPAWN_TIMEOUT_SECONDS,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return
