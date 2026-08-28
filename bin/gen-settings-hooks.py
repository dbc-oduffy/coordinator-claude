# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
gen-settings-hooks.py — CLI trampoline over claude-klabauter coordinator_core.install.gen_settings_hooks.

Collapses install.md § 3.5c ("Seed settings.json hook block") into one call —
this trampoline owns no logic of its own beyond the standard engine-root
resolve-and-import dance (mirrors coordinator/bin/ensure-doe-clone.py's own
shape 1:1). All install-time behavior — kill-switch check, coordinator-root
resolution, hooks.json read/merge, stray-hook detection, atomic write,
``--check-only`` short-circuit, and the ``settings_hooks_seed: <status>``
stdout row install.md's Phase 7 status table reads — lives in
coordinator_core.install.gen_settings_hooks; see that module's own docstring
for the full design rationale and negative-spec.

Spec backlink: DoE-claude:pln-extirpate-pasted-code-from-em--0f42e9 § M3
"""

from __future__ import annotations

import os
import sys

def _import_main():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.install.gen_settings_hooks import main as _op_main
    return _op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        # rc=3 preserves the exit-code contract carried over from the retired
        # bash trampoline (install.md § 3.5c): "3  engine-root/import transport
        # failure" is never conflated with rc=1 (generator business error) —
        # a claude-klabauter outage must never be misread as a business error.
        print(f"gen-settings-hooks.py: engine-root resolution failed: {exc}", file=sys.stderr)
        print("settings_hooks_seed: failed (engine-root transport failure)")
        return 3
    except ImportError as exc:
        print(
            f"gen-settings-hooks.py: coordinator_core.install.gen_settings_hooks not importable: {exc}",
            file=sys.stderr,
        )
        print("settings_hooks_seed: failed (engine-root transport failure)")
        return 3
    return op_main((sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
