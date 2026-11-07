"""session-start-engine-guards-importable.py -- SessionStart probe for unimportable engine guards.

A StartGuard in `sessionstart-dispatch.py`. Each engine-backed `block-*` guard passes loudly, per
dispatch, when its `coordinator_core.hooks.*` module cannot be imported (e.g. PyYAML missing). This
leg imports those same modules once at session start and, when any fails, emits one
`additionalContext` banner naming each module and its exception. Silent when all import. Fail-open;
exit 0. Rule: `coordinator/docs/wiki/coordinator-tripwires/tripwire-registry/engine-guards-unimportable-sessionstart-banner.md`.
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import List, Optional, Tuple

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

#: One entry per engine module a `block-*` guard script imports; keep in step with those scripts.
GUARD_MODULES: Tuple[str, ...] = (
    "coordinator_core.hooks.block_dispatch_suite_invocation",
    "coordinator_core.hooks.block_unenumerated_agent_type",
    "coordinator_core.hooks.block_workflow_foreign_emission",
)


def _resolve_root() -> Optional[str]:
    from _engine_root import resolve_claude_klabauter_root
    return resolve_claude_klabauter_root()


def probe() -> List[Tuple[str, str]]:
    """(module, "ExcType: message") for each guard module that fails to import; [] when all import.

    An unresolvable engine root fails every module, since each guard would loud-pass the same way.
    """
    try:
        root = _resolve_root()
        if not root:
            return [(m, "engine root unresolvable on this host") for m in GUARD_MODULES]
        from _engine_root import place_engine_root_on_path
        place_engine_root_on_path(root)
    except Exception as exc:  # noqa: BLE001
        reason = f"engine-root resolution raised {type(exc).__name__}: {exc}"
        return [(m, reason) for m in GUARD_MODULES]
    failures: List[Tuple[str, str]] = []
    for name in GUARD_MODULES:
        try:
            importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001
            failures.append((name, f"{type(exc).__name__}: {exc}"))
    return failures


def banner(failures: List[Tuple[str, str]]) -> str:
    """One line per distinct reason, naming every module that shares it (an unresolvable engine root
    fails all modules for one reason, so the banner stays small on the resume/fork byte cap)."""
    by_reason: dict = {}
    for mod, why in failures:
        by_reason.setdefault(why, []).append(mod)
    lines = "\n".join(f"  - {why}: {', '.join(mods)}" for why, mods in by_reason.items())
    return (
        "ENGINE GUARDS UNIMPORTABLE: these guards cannot load their engine module and pass every "
        "call unchecked (a loud pass, never a deny) until the import is repaired:\n" + lines
    )


def main(argv=None) -> int:
    try:
        failures = probe()
        if failures:
            sys.stdout.write(json.dumps(
                {"hookSpecificOutput": {"hookEventName": "SessionStart",
                                        "additionalContext": banner(failures)}}))
            sys.stdout.write("\n")
    except Exception:  # noqa: BLE001 -- fail open: session start is never blocked by this probe
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
