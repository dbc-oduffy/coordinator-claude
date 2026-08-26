"""
coordinator-invoke.py — CLI trampoline over claude-klabauter
coordinator_core.invoke.__main__.main.

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

This file is a thin trampoline: resolve the engine root, import, hand off to
`coordinator_core.invoke.__main__.main` — matching coordinator-install.py's
shape, its closest sibling in both naming and lifecycle. `main()` parses
`sys.argv` itself and terminates the process via `os._exit()` on every path
(success and error alike — see that module's own docstring, § Exit codes),
so this trampoline never returns and never needs its own `sys.exit()` call.

Fail-loud-on-ambiguity: if the engine root cannot be resolved or the claude-klabauter
module is not importable, exit 1 rather than 0 — a silent no-op here would
be indistinguishable from "op declined", which is the exact ambiguity
`coordinator-invoke`'s own pyproject.toml comment calls out as the reason
this entrypoint must fail as "command not found", not a mid-dispatch decline.

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
    from coordinator_core.invoke.__main__ import main as _op_main
    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"coordinator-invoke.py: engine-root resolution failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except ImportError as exc:
        print(
            f"coordinator-invoke.py: coordinator_core.invoke.__main__ "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
    op_main()


if __name__ == "__main__":
    main()
