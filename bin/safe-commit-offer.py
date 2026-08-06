"""
safe-commit-offer — CLI trampoline over the engine plane's
``coordinator_core.ops.session.safe_commit_offer`` module (direct-import
entrypoint, same shape as ``check-harvest-debt.py``: this file has no bash
predecessor and no RPC op registration — it is a thin trampoline over a
plain Python function-and-main() module, reached from the contract plane's
always-loaded doctrine so a stop-event ceremony (or an unattended
SessionEnd hook) has a settings-home-forwarder-reachable CLI to call rather
than a hardcoded engine-plane path.

This module is also the SIGTERM-handling seam for the SessionEnd-hook
child: ``sessionend-auto-commit.py`` (DoE-claude) soft-terminates this
process and waits a grace window before hard-killing, and ``main()``
installs a handler converting that SIGTERM into a normal ``SystemExit``
unwind so ``commit_pipeline.py``'s cleanup ``finally`` block actually runs
on POSIX (see ``_install_sigterm_handler()``).

PIVOT (PM ruling, 2026-07-31): this CLI now AUTO-COMMITS AND PUSHES by
default — no confirmation step. See the module docstring on the engine side
for the full rationale (being asked whether to commit was itself the
defect the PM named). ``--dry-run`` computes and prints without committing,
for inspection/testing — never gate a real invocation behind it.

WHY THIS FILE EXISTS: the computation+commit mechanism lives entirely in
the engine plane, with no caller-reachable entrypoint of its own. A
session's only CLI surface is the settings-home forwarder dir, whose
contents are derived from a scan of this directory — see
``scoped-git-commit``'s own docstring for the fuller rationale, which this
file mirrors: an op with no artifact here is unreachable without hardcoding
an engine-plane path, which reads to a caller exactly like no mechanism at
all.

Usage:
  safe-commit-offer [--session <id>] [--root <worktree-root>] [--json]
                     [--message <subject>] [--groups-json <file>] [--dry-run]
    Computes the safe pathspec for the resolved (or explicit) session and
    commits+pushes it — grouped mechanically (`--message`/`--groups-json`
    absent) or per caller-supplied groups. Reports what was committed, its
    sha/push state, and the excluded paths with why — AFTER the fact, never
    as a gate. ``--dry-run`` computes only, commits nothing.

Exit codes:
  0 — ran (an empty result is itself a valid "nothing to commit" outcome).
  1 — business failure (session id could not be resolved unambiguously).
  2 — usage error.
  3 — transport failure (CLAUDE_KLABAUTER_ROOT unresolvable / seam absent).
"""
from __future__ import annotations

import os
import signal
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402

_EXIT_TRANSPORT_FAIL = 3


def _install_sigterm_handler() -> None:
    """Convert SIGTERM into a `SystemExit` unwind, POSIX only.

    Python's default SIGTERM disposition is `SIG_DFL` -- the OS terminates
    the process outright, and no `finally` block runs (it is not a
    `KeyboardInterrupt`-shaped unwind). The SessionEnd hook now soft-
    terminates this process and waits a grace window before hard-killing;
    that grace window is inert unless something in the child turns the
    signal into ordinary Python control flow. `sys.exit(1)` raises
    `SystemExit`, which DOES propagate through `finally` blocks -- notably
    `commit_pipeline.py`'s reset-on-non-landed cleanup -- the way `SIG_DFL`
    never would.

    Windows has no SIGTERM: `Popen.terminate()` there is `TerminateProcess`,
    which runs no handler regardless of what is installed here. This
    function is a no-op off POSIX (`hasattr` guard) so the guarantee stays
    honestly POSIX-only rather than implying a cross-platform promise the
    Windows path cannot keep.

    Idempotent / re-entrant-safe: only installs over `SIG_DFL`. If
    something upstream (a caller, a future pipeline change) already
    installed a non-default handler, this leaves it alone rather than
    clobbering it -- installing blind here could silently discard a
    handler another part of the process depends on.
    """
    if not hasattr(signal, "SIGTERM"):
        return
    current = signal.getsignal(signal.SIGTERM)
    if current is signal.SIG_DFL:
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(1))


def _import_main():
    """Resolve CLAUDE_KLABAUTER_ROOT, put it on sys.path, and import the op's main().

    Plain in-process import, not an RPC invoke — this module registers no
    op, it is a direct-import function-and-main() module, same shape as
    ``coordinator_core.ops.check_harvest_debt``.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.ops.session.safe_commit_offer import main as _op_main

    return _op_main


def main() -> None:
    _install_sigterm_handler()
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"safe-commit-offer: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(_EXIT_TRANSPORT_FAIL)
    except ImportError as exc:
        print(
            f"safe-commit-offer: coordinator_core.ops.session.safe_commit_offer "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(_EXIT_TRANSPORT_FAIL)

    sys.exit(op_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
