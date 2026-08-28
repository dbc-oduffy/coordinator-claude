# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
extract-scope-paths.py — CLI trampoline over claude-klabauter
coordinator_core.ops.extract_scope_paths.

Purpose: extracts the `scope:` path list from a handoff's YAML frontmatter,
one path per line, stripping the leading two-space `- ` list-item prefix.
Fails loud (exit 1) when the block is absent or empty so callers (the
handoff/pickup skills' Step 1 preflight) get a clear diagnostic rather than
silently proceeding with zero paths.

Usage: extract-scope-paths.py <handoff-file>
  Prints matching scope paths to stdout, one per line.
  Exit 0 on success; exit 1 when scope block is missing or empty, or when
  claude-klabauter-link resolution/import fails; exit 2 on usage error (missing arg /
  file not found).

Why the polyglot shebang, not a plain `#!/usr/bin/env python3` script: the
file must remain invokable three ways that all "just work" — direct exec
(`extract-scope-paths.py ...`), explicit `python extract-scope-paths.py
...`, and `python extract-scope-paths.py ...` (the existing callers —
coordinator/skills/handoff/SKILL.md, coordinator/skills/pickup/SKILL.md —
both invoke via `python "${_cc_root}/bin/extract-scope-paths.py" "$HANDOFF"`
and are NOT edited by this port). Line 2 is inert-Python-but-executable-sh:
under sh/bash it resolves `python3 || python || py` and `exec`s it; under
Python it's a no-op string.

Filename keeps its `.sh` suffix (unlike coordinator-auto-push /
handoff-gate-aging, which dropped it) — deliberately, to avoid a caller edit
across the two SKILL.md call sites above; nothing in the polyglot mechanism
requires dropping the suffix.

Exit convention: this is a fail-loud preflight gate (handoff/pickup scope
enumeration) — claude-klabauter-link failure exits 1, not a silent-degrade 0, so a
missing/broken claude-klabauter install surfaces immediately rather than letting a
caller proceed with an empty scope list.

Port source: coordinator/bin/extract-scope-paths.py (retired on cutover;
see git log)
Spec: docs/plans/2026-06-30-session-terminator-mechanism-unification.md C4
"""

from __future__ import annotations

import os
import sys

def _resolve_run_op_main():
    """DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather
    than a bare `main` import, so any paths the op declares become a session
    scope-touch claim instead of an unclaimed orphan at the
    `scoped_git_commit` sink.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main
    return run_op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        run_op_main = _resolve_run_op_main()
    except RuntimeError as exc:
        print(f"extract-scope-paths: engine-root resolution failed: {exc}", file=sys.stderr)
        return 1
    except ImportError as exc:
        print(f"extract-scope-paths: coordinator_core.cli_entry not importable: {exc}", file=sys.stderr)
        return 1
    try:
        code = run_op_main("coordinator_core.ops.extract_scope_paths", (sys.argv[1:] if argv is None else argv))
    except ImportError as exc:
        print(f"extract-scope-paths: coordinator_core.ops.extract_scope_paths not importable: {exc}", file=sys.stderr)
        return 1
    return code


if __name__ == "__main__":
    sys.exit(main())
