"""lint-frontmatter.py — CLI trampoline over coordinator_core.frontmatter.schema_validate.main.

Thin trampoline — lives in claude-klabauter's own coordinator/bin/ (this repo), NOT
DoE-claude's contract surface, per DR-047 (DoE owns contract/generator,
Claude-klabauter owns engine). Consumed by DoE's 3 live callers via the resolved
forwarder. Wraps claude-klabauter's frontmatter validator + coordinator_core.dag
reachability primitives to restore the DoE-consumed
lint-frontmatter CLI after coordinator/bin/lint-frontmatter.js was deleted at
Claude-klabauter commit c79e66cd (declared "zero live callers" — false; DoE has 3 live
callers: workweek-complete.md's Step 2.5 strict referential-integrity gate,
update-docs.md's Phase 11d drift sweep, and handoff/SKILL.md's write-time
gate). All CLI logic lives in coordinator_core.frontmatter.schema_validate.main
— this file only resolves the engine root, imports, and forwards argv/exit code.

Spec backlink: pln-python-ize-claude-klabauter-bin-oracles--218413 § A1
"""
from __future__ import annotations

import os
import sys


def _import_main():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.frontmatter.schema_validate import main as _op_main
    return _op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"lint-frontmatter.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 3
    except ImportError as exc:
        print(
            f"lint-frontmatter.py: coordinator_core.frontmatter.schema_validate not importable: {exc}",
            file=sys.stderr,
        )
        return 3
    return op_main((sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
