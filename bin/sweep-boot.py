# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""sweep-boot.py — native trampoline over session.boot_sweep.

Purpose: bare-name entrypoint that spawns coordinator_core.invoke's
session.boot_sweep op (ONE cold-start for all four boot-time archival
classes — consumed handoffs, terminal plans, shipped handoffs, actioned
memos) via cc_invoke.route_mutation. De-bash-coordinator campaign (Wave 1b,
unit sweep-boot.sh, shape-(b) per-op trampoline —
docs/plans/2026-07-19-debash-coordinator-windows.md § Pinned pattern).

Native successor to the retired coordinator/bin/sweep-boot.sh strangler
facade. big-bang cutover: the legacy bash three-state routing (State 1 —
seam-absent per-class bash sweeps) is NOT reproduced. `_legacy_fn` below
raises instead of shelling to sweep-terminal-plans.sh /
sweep-shipped-handoffs.sh / the (since-retired) cs_sweep_actioned_memos —
there is no bash fallback leg left to strangle back to. The op is assumed present (verified
at scout time); a raised legacy_fn only fires if the seam is genuinely
absent, which is treated as a transport failure identically to a native
spawn error (see Exit codes below) — this preserves the bash oracle's
"always exit 0, best-effort ceremony" contract rather than crashing session
boot on a missing engine.

Usage:
    python sweep-boot.py [<repo_root>] [<state_common_dir>]

    <repo_root>          Optional; defaults to `git rev-parse --show-toplevel`.
    <state_common_dir>   Optional; the STATE-hosting repo's `.git` common dir
                          (cross-repo memo 2026-07-07-gap6-gpgsign-landed-boot-
                          sweep-two-repo-split.md item 2). Forwarded into the
                          op's params JSON only when non-empty; absent -> the
                          op's own unified-state fallback applies.

Stdout contract: an INTEGER count of items archived, printed on every path —
success (sum of len(.archived) across the four result buckets:
consumed_handoffs, plans, shipped_handoffs, memos), partial (op-level
refusal — sum from the partial result payload), and transport failure
(0, best-effort ceremony). Byte-parity with the retired bash oracle's
stdout contract.

Commit semantics: the op self-commits all four archival classes — this
trampoline MUST NOT stage or commit (mirrors the bash oracle's
never-stages/never-commits invariant; no such git subprocess appears below —
`git rev-parse --show-toplevel` is the only git spawn in this file).

Exit codes:
    0 — normal completion on every path (success, partial, or transport
        failure) — this op is best-effort ceremony, never a boot-blocking
        gate. Matches the retired bash oracle's exit-code contract exactly.
        Deliberately UNCHANGED by the fail-loud work below — the goal is to
        stop being SILENT about a broken sweep, never to start blocking
        session boot on one.

Fail-loud side channel (C20, 2026-07-23): stdout/exit-code alone used to make
a genuinely-empty sweep byte-indistinguishable from a dead one — an op
refusal, a transport failure, or a malformed op response all printed "0" and
exited 0, identically to "there was nothing to archive". Each of those three
failure shapes now also appends a CHILD-FAILED record to the shared
housekeeping-failures log (`coordinator_core.ops.ceremony.detached_spawn.
record_child_failure`) so C17b's orientation-cache surfacing picks it up at
the next session start; a genuine zero-item sweep writes no such record. A
successful sweep also stamps the `archive_sweeps` housekeeping-liveness key
(`coordinator_core.ops.ceremony.housekeeping_liveness.stamp_liveness`) — see
`_stamp_archive_sweeps_liveness`'s docstring for why a second producer
stamping the same key later is additive, not a double-count. Both side
channels are best-effort and never raise into this trampoline's own
already-best-effort ceremony contract.

Spec backlink: pln-strang-11-b8-session-init-boot-f78455 § C2 / AC7
Spec backlink: docs/plans/2026-07-19-debash-coordinator-windows.md § Pinned pattern, Wave 1b
Spec backlink: pln-wsc-tail-slim-down-op-scoped-c-e9a265 § C20
DR-215: single-process four-class sweep replaces four separate cc_invoke cold-starts.

Negative-spec: this module never sources or shells to strangler-facade.sh,
never spawns bash, and never re-implements a per-class legacy sweep. All
routing goes through cc_invoke.route_mutation — no local --bare ladder. It
also never invents a second housekeeping-failures-log format or a second
liveness-stamp store — both route through the shared C17a/C17b seam.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any

_BIN_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_BIN_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from cc_invoke import RouteMutationError, _no_console_kw, _resolve_claude_klabauter_root, route_mutation  # noqa: E402
from sweep_argv import parse_repo_root_argv  # noqa: E402

_OP = "session.boot_sweep"
_ARCHIVE_BUCKETS = ("consumed_handoffs", "plans", "shipped_handoffs", "memos")
_USAGE = "usage: python sweep-boot.py [-h] [<repo_root>] [<state_common_dir>]"


def _import_housekeeping_seam():
    """Resolve CLAUDE_KLABAUTER_ROOT and import the shared C17a/C17b housekeeping-failures +
    liveness seam (`coordinator_core.ops.ceremony.detached_spawn.record_child_failure`,
    `coordinator_core.ops.ceremony.housekeeping_liveness.{stamp_liveness,ARCHIVE_SWEEPS}`).

    Mirrors `agent-worktree-sweep.py::_import_main`'s resolve-then-sys.path-insert shape —
    this trampoline's own `__file__` lives inside the claude-klabauter checkout, but the seam must be
    imported via the resolved CLAUDE_KLABAUTER_ROOT (not a relative import) for the same reason every
    other in-process op import in this directory does: `repo_root` here is the CALLER's repo
    (may be a consumer repo), not necessarily where this file's coordinator_core sibling
    lives. Returns None on any resolution/import failure -- this seam is best-effort
    forensics, never a reason to fail the sweep itself louder than it already fails.
    """
    try:
        claude_klabauter_root = _resolve_claude_klabauter_root()
        if claude_klabauter_root not in sys.path:
            sys.path.insert(0, claude_klabauter_root)
        from coordinator_core.ops.ceremony.detached_spawn import record_child_failure
        from coordinator_core.ops.ceremony.housekeeping_liveness import (
            ARCHIVE_SWEEPS,
            stamp_liveness,
        )
    except Exception:  # noqa: BLE001 -- best-effort; never let seam-import failure mask the real error
        return None
    return record_child_failure, stamp_liveness, ARCHIVE_SWEEPS


def _record_housekeeping_failure(repo_root: str, exc: BaseException) -> None:
    """Best-effort append a CHILD-FAILED record to the shared housekeeping-failures log.

    This is the fix for the finding this chunk exists to close: a dead transport or a
    refused op used to be byte-indistinguishable from a genuinely-empty sweep (both printed
    "0" and exited 0). Swallows every failure of its own -- a housekeeping-failures-log
    write failing must never escalate past this best-effort trampoline's already-best-effort
    ceremony contract.
    """
    seam = _import_housekeeping_seam()
    if seam is None:
        return
    record_child_failure, _stamp_liveness, _archive_sweeps = seam
    try:
        record_child_failure(repo_root, os.path.abspath(__file__), exc=exc)
    except Exception:  # noqa: BLE001 -- never raise out of a best-effort forensics call
        pass


def _stamp_archive_sweeps_liveness(repo_root: str) -> None:
    """Best-effort stamp the shared `archive_sweeps` housekeeping-liveness key.

    Decision (this chunk): boot_sweep IS the natural producer for this stamp -- it is,
    today, the only occasion that runs all four archival classes end-to-end, and
    `housekeeping_liveness.stamp_liveness` is an explicit last-writer-wins read-modify-write
    (module docstring) designed for exactly this: multiple producers stamping the SAME class
    key is additive-safe by construction, not a double-count -- there is no counter here,
    only "last time this class ran". C2's later detached fire stamping the same key from a
    different call site is therefore not in tension with this stamp; whichever ran most
    recently wins, which is the correct semantics for a liveness signal (not a correctness-
    critical store, per that module's own docstring). Only stamped on a genuinely successful
    sweep (this function is called from the success path only, never from a refusal/transport
    failure) -- a failed sweep must NOT look live.
    """
    seam = _import_housekeeping_seam()
    if seam is None:
        return
    _record_child_failure, stamp_liveness, archive_sweeps = seam
    try:
        stamp_liveness(repo_root, archive_sweeps)
    except Exception:  # noqa: BLE001 -- never raise out of a best-effort liveness stamp
        pass

def _legacy_fn() -> Any:
    """No-bash-fallback marker — big-bang cutover per the de-bash campaign.

    The retired bash facade's State-1 leg ran three separate per-class
    sweeps (the (since-retired) cs_sweep_actioned_memos, sweep-terminal-plans.sh,
    sweep-shipped-handoffs.sh) plus a documented caller-owned gap for
    consumed-handoff sweeping. None of that is reproduced here — raising
    is the correct behavior for a facade whose native op already exists
    and passes (sequencing law, Wave 1b). The caller (main, below) treats
    this raise identically to any other transport failure: log-and-continue,
    print 0, exit 0 — never a hard crash on session boot.
    """
    raise RuntimeError(
        "sweep-boot.py: native seam absent and no bash fallback remains "
        "(big-bang cutover, de-bash campaign) — session.boot_sweep is a hard "
        "prerequisite; ensure coordinator_core is installed and importable."
    )


def _no_console_kw_safe() -> dict:
    """``_no_console_kw`` needs a resolved CLAUDE_KLABAUTER_ROOT, which can raise
    RuntimeError; on any resolution failure, fall back to the same
    suppression kwargs computed inline (zero imports beyond ``subprocess``)
    rather than silently dropping console suppression -- a resolution
    failure must never turn a quiet spawn into a visible console window."""
    try:
        return _no_console_kw(_resolve_claude_klabauter_root())
    except Exception:  # noqa: BLE001 -- fail-open, matches this module's transport posture
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def _resolve_repo_root(explicit: str | None) -> str | None:
    """Resolve repo_root — explicit arg wins; else `git rev-parse --show-toplevel`."""
    if explicit:
        return explicit
    try:
        claude_klabauter_root = _resolve_claude_klabauter_root()
        if claude_klabauter_root not in sys.path:
            sys.path.insert(0, claude_klabauter_root)
        from coordinator_core.git.repo_root import show_toplevel

        return show_toplevel()
    except Exception:  # noqa: BLE001 -- fail-open, matches this module's transport posture
        return None


def _count_archived(result: dict[str, Any]) -> int:
    """Sum len(.archived) across the four result buckets; missing/malformed -> 0 for that bucket."""
    total = 0
    for bucket in _ARCHIVE_BUCKETS:
        b = result.get(bucket, {})
        if not isinstance(b, dict):
            continue
        archived = b.get("archived", [])
        if isinstance(archived, list):
            total += len(archived)
    return total


def _build_params(state_common_dir: str | None) -> dict[str, Any]:
    if state_common_dir:
        return {"state_common_dir": state_common_dir}
    return {}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    positional, _flags, early_exit = parse_repo_root_argv(
        argv, prog="sweep-boot.py", usage=_USAGE, max_positional=2
    )
    if early_exit is not None:
        return early_exit
    explicit_repo_root = positional[0] if len(positional) >= 1 and positional[0] else None
    state_common_dir = positional[1] if len(positional) >= 2 and positional[1] else None

    from coordinator_core.install.forwarder_self_heal import self_heal_forwarders

    self_heal_forwarders()

    repo_root = _resolve_repo_root(explicit_repo_root)
    if not repo_root:
        print("sweep-boot.py: cannot resolve git repo root", file=sys.stderr)
        print("0")
        return 0

    params = _build_params(state_common_dir)

    try:
        result = route_mutation(_OP, params, repo_root, _legacy_fn)
    except RouteMutationError as exc:
        # Op-level refusal (non-zero exit_code / failed items / error string).
        # Mirrors the bash oracle's exit_code:2 DETERMINATE-PARTIAL handling:
        # still print the partial archived count, WARN to stderr, exit 0.
        count = _count_archived(exc.result) if isinstance(exc.result, dict) else 0
        print(f"sweep-boot.py: WARN: {_OP} returned a refusal — archived {count} item(s): {exc}", file=sys.stderr)
        _record_housekeeping_failure(repo_root, exc)
        print(count)
        return 0
    except RuntimeError as exc:
        # Transport failure (native spawn error, timeout, seam absent -> _legacy_fn raised).
        # Best-effort ceremony: log-and-continue, print 0, exit 0 — never blocks session boot.
        print(f"sweep-boot.py: WARN: {_OP} transport error — skipping ({exc})", file=sys.stderr)
        _record_housekeeping_failure(repo_root, exc)
        print("0")
        return 0

    if not isinstance(result, dict):
        print(f"sweep-boot.py: WARN: {_OP} returned a non-object result — skipping", file=sys.stderr)
        _record_housekeeping_failure(
            repo_root, RuntimeError(f"{_OP} returned a non-object result: {result!r}")
        )
        print("0")
        return 0

    _stamp_archive_sweeps_liveness(repo_root)
    print(_count_archived(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
