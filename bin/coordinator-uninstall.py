# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
coordinator-uninstall.py — CLI trampoline over claude-klabauter
coordinator_core.install.uninstall_legs.orchestrate_uninstall.

Purpose: CLI entrypoint that sequences the uninstall legs
  (coordinator_core.install.uninstall_legs, C3-C6) in dependency order to
  reverse the maximalist coordinator install's out-of-repo surfaces
  (tasks/coordinator-uninstall/surface-map.md). Two end-states:
  full-remove (default) and revert-to-marketplace (--keep-marketplace).

All orchestration logic (flag parsing, ordered-plan printing, --dry-run
short-circuit, fail-loud leg sequencing) now lives claude-klabauter-side —
naked-Python port, T4a-g3b/uninstall-orchestrator chunk. This file is a
thin CLI trampoline: resolve the engine root, import, forward argv, forward
exit code. Kept as a `.sh`-suffixed polyglot (not renamed) so every
existing caller (`bash coordinator-uninstall.py ...`, direct exec, docs)
keeps working unchanged — the sh/python polyglot shebang below makes
`bash`, `python`, and direct-exec invocation all "just work" against the
SAME file.

Fail-loud-on-ambiguity doctrine (prior-art Compatible #6): this
  orchestrator's aggregation instantiates DoE-claude's
  coordinator/docs/wiki/implementation-standards-by-domain.md § Cross-cutting
  standards, "Detect-then-silently-pick is a footgun — refactor to
  detect-then-fail-loud on ambiguity" (coordinator/CLAUDE.md § Implementation
  Standards retired 2026-07-27) — already the discipline every leg follows.
  If the engine root cannot be resolved or the claude-klabauter module is not
  importable, this trampoline exits 1 (fail-loud), matching the
  orchestrator's own leg-failure exit convention — never exit 0 on a
  broken link, since a silent no-op here would leave the maximalist
  install's out-of-repo surfaces un-reversed with no indication anything
  went wrong.

Spec backlink: DoE-claude:pln-first-class-coordinator-uninst-15db2e § C7
Surface source of truth: tasks/coordinator-uninstall/surface-map.md
Leg source of truth: coordinator_core.install.uninstall_legs (claude-klabauter)
Port backlink: docs/plans/2026-07-15-bash-to-naked-python-engine-migration.md
"""

from __future__ import annotations

import os
import sys


def _import_main():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.install.uninstall_legs import orchestrate_uninstall as _op_main
    return _op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"coordinator-uninstall.py: engine-root resolution failed: {exc}", file=sys.stderr)
        return 1
    except ImportError as exc:
        print(
            f"coordinator-uninstall.py: coordinator_core.install.uninstall_legs not importable: {exc}",
            file=sys.stderr,
        )
        return 1
    return op_main((sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
