# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
aggregate-chain-loe.py — CLI trampoline over claude-klabauter
coordinator_core.session_ledger.aggregate_chain_loe.

Finish-strangler port (DR-047/DR-059): the bash implementation (chain-walk
aggregator — traverse a handoff predecessor chain, parse all Session Ledger
blocks, emit summed LoE metrics) has been fully ported to
coordinator_core/session_ledger/aggregate_chain_loe.py (already registered as
the "session_ledger.aggregate_chain_loe" JSON-RPC op — see central-reg commit
7b30a94a). This file is now a thin DoE-side (contract) trampoline over that
Claude-klabauter (engine) module, per DR-047 (DoE owns contract/generator, claude-klabauter owns
engine).

Shebang note: the SHEBANG line above is `#!/usr/bin/env python3`, generator-
owned by `gen-launcher-shim.py --ensure-unix`, and correct for this shape. On
Windows, this file's co-located `.cmd` twin wins via `PATHEXT` when invoked as
a bareword, so the shebang is never read there; on macOS/Linux `python3` is the
right interpreter. Caution: callers must invoke via the extensionless name or a
resolved-interpreter prefix, never a bareword `.py` through git-bash — git-bash
DOES honor the shebang and would exec-127 with no `python3` present. See the
carve-out in DoE-claude's coordinator/docs/wiki/bash-on-windows-gotchas.md §
Carve-out (cross-repo — this wiki lives in the DoE-claude repo, not
here).

Filename kept WITH the .sh suffix (unlike coordinator-auto-push /
handoff-gate-aging, which dropped it) — this is a cold ceremony-only CLI
consumed directly by a human/handoff-authoring session, not a hot per-commit
hook path, so there is no caller-repoint benefit to dropping the suffix, and
keeping it avoids a docs/wiki cross-reference sweep.

Cold path — not a daemon-RPC hot path. Direct in-process import + call
(mirrors coordinator-auto-push/handoff-gate-aging's direct-import trampoline
shape, template-variant #1), NOT cc_invoke()/route() — this is a
ceremony-only CLI invocation (one process, one call), so there is no
subprocess-spawn-and-JSON-RPC-envelope benefit to routing through the IPC
transport.

Spec backlink: docs/plans/2026-06-29-handoff-lineage-dag-fan-in-fan-out.md § C2
Port source: coordinator/bin/aggregate-chain-loe.py (retired on cutover; see git log)

Concurrency posture: read-only against handoff files in state/handoffs/ and
  archive/handoffs/**/ (unchanged from the bash oracle — see the ported
  module's own docstring). Handoff files are append-only; safe under
  concurrent reads; no locking required.
Idempotency posture: deterministic given a fixed terminal-handoff and fixed
  handoff content; same input => same output every invocation. No side
  effects; nothing written.
Resume strategy: stateless — re-running with the same --terminal-handoff
  always produces identical output as long as handoff files haven't changed.
  No checkpoint needed; re-run is free.
"""

from __future__ import annotations

import os
import sys


def _import_main():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.session_ledger.aggregate_chain_loe import main as _op_main
    return _op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"aggregate-chain-loe.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 1
    except ImportError as exc:
        print(f"aggregate-chain-loe.py: coordinator_core.session_ledger.aggregate_chain_loe not importable: {exc}", file=sys.stderr)
        return 1
    return op_main((sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
