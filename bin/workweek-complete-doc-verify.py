# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
coordinator/bin/workweek-complete-doc-verify.py — thin CLI wrapper over
coordinator_core.ops.doc_content_verify.

Purpose: bareword-invokable entrypoint for the human-facing doc content
verifier (AC12) — `coordinator_core.ops.doc_content_verify` already owns a
full `main(argv) -> int` CLI (its own `--root`/`--doc`/`--ignore` argv
parsing and JSON-to-stdout emission, `{"findings": [...]}`), so this
trampoline is direct-import argv passthrough only (mirrors
`coordinator/bin/workweek-complete-brief.py` over
`coordinator_core.workweek_complete.brief`), not a reimplementation of that
parsing.

Not registered as an IPC op (`_registry_map.py`/`@register_op`) — same
reasoning as the sibling `workweek-complete-doc-staleness.py`: this is a
plain `main(argv) -> int` CLI, the shape `check_arch_audit_staleness.py`
already establishes as the convention for an op that is both
directly-callable and named as a bareword CLI in `directives[].cli`, never
dispatched as an IPC op name. See that file's docstring for the full
rationale (C2: "decide the shape once and apply it to both new ops
consistently").

Usage:
    workweek-complete-doc-verify [--root PATH] [--doc PATH ...] [--ignore TOKEN ...]

Exits 3 if the engine root cannot be resolved (see stderr) before ever reaching
`main()`; otherwise exit code and stdout/stderr are exactly
`coordinator_core.ops.doc_content_verify.main`'s.

Spec backlink: DoE-claude DoE-claude:pln-human-facing-doc-staleness-det-d9c047 § C2, AC12
Spec backlink: claude-klabauter coordinator_core/ops/doc_content_verify.py

Negative-spec: does NOT parse or reinterpret argv itself — forwards verbatim
to `doc_content_verify.main`.
"""

from __future__ import annotations

import sys
from pathlib import Path

def main(argv: "list[str] | None" = None) -> int:
    """Zero-arg trampoline: reads `sys.argv` itself and forwards args-only
    (no `argv[0]` program-name placeholder) to `doc_content_verify.main` via
    `run_op_main` — the exact CLI shape `check-arch-audit-staleness.py`
    already establishes for this same op class (see this module's
    docstring); required so the manifest's static prog-slot contract
    (`coordinator_core/ceremony_common/test_argv_prog_slot_contract.py`)
    finds a top-level `main` symbol via `getattr(module, "main", None)`,
    since a bare re-exported name is not itself a module-level `FunctionDef`
    this AST-driven check can see.

    DR-276: routed through `coordinator_core.cli_entry.run_op_main` for
    parity with every other operator-CLI trampoline, though
    `doc_content_verify` is read-only and declares nothing — this is a
    consistency conversion, not a behavior change (see module docstring)."""
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_colocated_engine_on_path

    try:
        require_colocated_engine_on_path(__file__)
    except RuntimeError as exc:
        print(f"{Path(__file__).name}: engine-root resolution failed: {exc}", file=sys.stderr)
        return 3

    from coordinator_core.cli_entry import run_op_main

    return run_op_main("coordinator_core.ops.doc_content_verify", (sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
