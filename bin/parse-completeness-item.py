# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""parse-completeness-item.py — parses and classifies one completeness-checklist item.

Single-source parse+classify of a completeness-checklist line of the shape
`<class>: <assertion> [probe: <cmd>]`, called from bash callers (the pickup
skill) that consume its structured output. Pure-computation, no-I/O parser;
logic lives claude-klabauter-side in coordinator_core.ops.parse_completeness_item, and
this file is a thin direct-import trampoline over it.
"""
# parse-completeness-item.py — CLI trampoline over claude-klabauter
# coordinator_core.ops.parse_completeness_item.
#
# Finish-strangler port: the bash implementation (single-source parse+classify
# of one completeness-checklist item: <class>: <assertion> [probe: <cmd>]) has
# been fully ported to coordinator_core/ops/parse_completeness_item.py, with
# co-located pytest coverage (test_parse_completeness_item.py). This file is
# now a thin DoE-side (contract) trampoline over that claude-klabauter (engine) module,
# per DR-047 (DoE owns contract/generator, claude-klabauter owns engine).
#
# Op registered? NO — plain module, direct in-process import (no register_op,
# no ops/__init__.py / _registry_map.py / ipc.py / classification.py entry).
# This is a pure-computation, no-I/O parser called from bash callers (the
# pickup skill, C4) that are NOT themselves being ported this wave — the
# direct-import shape mirrors coordinator-auto-push's variant-#1 template
# rather than the registered-IPC-op variant.
#
# Exit codes (parity-critical — matches Usage/oracle contract byte-for-byte):
#   0 — success
#   1 — malformed input (business outcome; message on stderr)
#   2 — engine-root resolution / coordinator_core import failure (transport
#       failure — dedicated code, does NOT collide with the business codes
#       0/1 above; this is a fail-loud gate/validator shape per the porting
#       addendum § 3b, not a best-effort/never-block shape like auto-push).
#
# Shebang note: the SHEBANG line above is `#!/usr/bin/env python3`, generator-
# owned by `gen-launcher-shim.py --ensure-unix`, and correct for this shape. On
# Windows, this file's co-located `.cmd` twin wins via `PATHEXT` when invoked
# as a bareword, so the shebang is never read there; on macOS/Linux `python3`
# is the right interpreter. Caution: callers must invoke via the extensionless
# name or a resolved-interpreter prefix, never a bareword `.py` through git-
# bash — git-bash DOES honor the shebang and would exec-127 with no `python3`
# present. See the carve-out in DoE-claude's coordinator/docs/wiki/bash-on-
# windows-gotchas.md § Carve-out (cross-repo — this wiki lives in the
# DoE-claude repo, not here).
#
# Spec backlink: docs/plans/2026-06-24-install-baton-completeness-claude-code-validation.md § C3
# Prior bash implementation: see git log (parse-completeness-item.py, 284 lines, retired on this cutover)
from __future__ import annotations

import os
import sys

_TRANSPORT_FAILURE_EXIT = 2


def _import_run_op_main():
    """Resolve the engine root, put it on sys.path, and import `run_op_main`.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it -- this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here (this is a pure in-process string-parser call,
    no benefit to a second subprocess hop).

    DR-276: the op is run through `coordinator_core.cli_entry.run_op_main`
    rather than by calling its `main` directly, so any path it declares via
    `declare_write` becomes a session scope-touch claim instead of an
    unclaimed orphan at the `scoped_git_commit` sink.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        run_op_main = _import_run_op_main()
    except RuntimeError as exc:
        print(f"parse-completeness-item: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return _TRANSPORT_FAILURE_EXIT
    except ImportError as exc:
        print(
            f"parse-completeness-item: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return _TRANSPORT_FAILURE_EXIT

    try:
        code = run_op_main("coordinator_core.ops.parse_completeness_item", (sys.argv[1:] if argv is None else argv))
    except ImportError as exc:
        print(
            f"parse-completeness-item: coordinator_core.ops.parse_completeness_item not importable: {exc}",
            file=sys.stderr,
        )
        return _TRANSPORT_FAILURE_EXIT

    return code


if __name__ == "__main__":
    sys.exit(main())
