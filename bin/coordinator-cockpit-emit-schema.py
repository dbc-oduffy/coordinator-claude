"""
coordinator-cockpit-emit-schema.py — CLI trampoline over claude-klabauter
coordinator_core.contract.cockpit_schema.emit_schema.main.

Purpose: `coordinator-invoke` and `coordinator-cockpit-emit-schema` already
exist as `[project.scripts]` console-script entrypoints (pyproject.toml),
but a console script only materialises somewhere ON PATH when it lands in
the interpreter's Scripts/bin dir — which is NOT itself on PATH for the
interpreters this installer provisions (see
docs/plans/2026-08-17-machine-first-install-surface.md § C3: that directory
also carries bare `python3`/`pip3`, so adding IT to PATH was rejected).
This file is the discoverable, always-on-PATH stand-in: it lives in
`coordinator/bin/`, so substrate's dynamic agent-helper forwarder derivation
(`_derive_agent_helper_target_map`, off a live `coordinator/bin/` listing)
picks it up automatically and emits a forwarder for it into the already-
PATH'd settings-home `bin/` — no edit to substrate.py needed.

This is the seam DoE's live ask (`coordinator_core.contract.cockpit_schema.
emit_schema` is the sole regeneration path for their frozen schema — see
this repo's CLAUDE.md § Architecture) actually points at: DoE consumes this
by spawning a command, per DR-215, never by resolving claude-klabauter's interpreter
and importing internals.

This file is a thin trampoline: resolve the engine root, import, forward argv
— matching coordinator-install.py's shape, its closest sibling in both
naming and lifecycle. `main(argv)` parses `argv` itself (defaulting to
`sys.argv[1:]` when called with none) and either returns normally (success,
implicit exit 0) or raises `SystemExit` (error) — unlike
`coordinator-invoke`'s `main()`, it never calls `os._exit()` itself, so
forwarding `sys.argv[1:]` and letting any `SystemExit` propagate is
sufficient; no explicit `sys.exit()` wrapping is needed here either.

Fail-loud-on-ambiguity: if the engine root cannot be resolved or the claude-klabauter
module is not importable, exit 1 rather than 0 — a silent no-op here would
be indistinguishable from a well-formed empty schema emission, which is
exactly the ambiguity DoE's release capability cannot tolerate.

Entry placement: no edit to coordinator/lib/bin-templates-manifest.py is
needed or wanted, for the same reason coordinator-install.py's docstring
gives — that manifest classifies DoE-owned templates/bin/ artifacts, and
this CLI is a claude-klabauter-generated one instead.

Spec backlink: docs/plans/2026-08-17-machine-first-install-surface.md § C3
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _import_main():
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.contract.cockpit_schema.emit_schema import main as _op_main
    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"coordinator-cockpit-emit-schema.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except ImportError as exc:
        print(
            f"coordinator-cockpit-emit-schema.py: coordinator_core.contract."
            f"cockpit_schema.emit_schema not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
    op_main(sys.argv[1:])


if __name__ == "__main__":
    main()
