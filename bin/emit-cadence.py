#!/usr/bin/env python3
# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""emit-cadence.py — native Python trampoline for the emit.cadence transport op.

Purpose: routes emit.cadence — claude-klabauter's composite op (backlog.record THEN
artifact.emit aggregation, in that order, as a claude-klabauter-internal invariant)
through cc_invoke.route_mutation. This is the per-repo cadence TRIGGER fired
from `-complete` ceremonies: DoE owns the cadence (WHEN emission fires),
Claude-klabauter owns the op (backlog.record -> artifact.emit ordering, and everything
the op does internally).

2026-07-19 Windows de-bash campaign, Wave 1b. Replaces the bash strangler
facade with a native Python entry: `python3 emit-cadence.py`, no shell in
the middle, no #!/bin/sh polyglot header. Big-bang cutover — the legacy
bash body is NOT retained; legacy_cadence() below raises instead of
running a fallback bash emitter.

Spec backlink: docs/plans/2026-07-11-emission-cadence-trigger-rewire.md § C2 / D3
Spec backlink: docs/plans/2026-07-19-debash-coordinator-windows.md § Wave 1b

Gate flag (D2, RATIFIED PM 2026-07-11):
    COORDINATOR_EMISSION_CADENCE_LIVE — default ON. Only an explicit off
    value (0, false, off — case-insensitive) disables cadence emission;
    unset or any other value leaves it ON. When OFF, this script logs once
    to stderr and exits 0 (benign skip — never wedges/errors the calling
    ceremony).

Exit codes:
    0 — success, OR gate-off benign skip
    1 — seam absent (no claude-klabauter control plane) OR op-level refusal
        (RouteMutationError) — no emission fired
    3 — native op: post-spawn transport failure
    4 — structural contract-pin failure (will not self-heal; remediation
        named in stderr)

Negative-spec (retired patterns — DO NOT reintroduce):
    - No bash fallback emitter body. The pre-campaign strangler facade's
      State-1 legacy_cadence() only ever printed a fail-loud message and
      returned 1 (DoE never carried a real bash emission body for this op);
      this port preserves that fail-loud contract by raising instead.
    - No local --bare/cc_invoke ladder. Imports route_mutation from
      coordinator/bin/lib/cc_invoke.py (Wave 1a) rather than re-inlining one.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_BIN_DIR = Path(__file__).resolve().parent
_LIB_DIR = _BIN_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from cc_invoke import RouteMutationError, StructuralPinError, route_mutation  # noqa: E402


class _SeamAbsentError(RuntimeError):
    """Raised by legacy_cadence() on State-1 (seam absent) — no bash fallback."""


def _gate_is_off() -> bool:
    """True iff COORDINATOR_EMISSION_CADENCE_LIVE is an explicit off value."""
    raw = os.environ.get("COORDINATOR_EMISSION_CADENCE_LIVE", "")
    return raw.strip().lower() in ("0", "false", "off")


def _resolve_repo_root() -> str:
    """Resolve the git repo root from cwd — mirrors strangle_route's
    `git -C "$PWD" rev-parse --show-toplevel` auto-resolution (standalone-repo
    assumption; no repo-root argument on this entry).
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(Path.cwd()), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        print(
            f"emit-cadence: cannot resolve git repo root from {Path.cwd()}",
            file=sys.stderr,
        )
        sys.exit(1)
    return proc.stdout.strip()


def legacy_cadence() -> None:
    """State-1 fallback — fails loud. emit.cadence's composite
    backlog.record -> artifact.emit ordering lives entirely in claude-klabauter's
    engine; DoE never carried a bash body for this op. No fallback emission
    is fired when the claude-klabauter control plane is absent on disk.
    """
    raise _SeamAbsentError(
        "emit-cadence: cockpit emission cadence requires the claude-klabauter control "
        "plane, which is not present in this distribution. No emission fired."
    )


def main() -> int:
    if _gate_is_off():
        print(
            "emit-cadence: COORDINATOR_EMISSION_CADENCE_LIVE is off — "
            "skipping cadence emission.",
            file=sys.stderr,
        )
        return 0

    repo_root = _resolve_repo_root()

    # emit.cadence takes no params. Requires only _origin_worktree, resolved
    # from cwd by the seam itself — zero new dependency vs artifact.emit.
    try:
        route_mutation("emit.cadence", {}, repo_root, legacy_cadence)
    except _SeamAbsentError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except RouteMutationError as exc:
        print(f"emit-cadence: {exc}", file=sys.stderr)
        return 1
    except StructuralPinError as exc:
        print(f"emit-cadence: {exc}", file=sys.stderr)
        print(
            "emit-cadence: structural contract-pin failure — will NOT "
            "self-heal on retry; apply the remediation named above before "
            "re-running.",
            file=sys.stderr,
        )
        return 4
    except RuntimeError as exc:
        print(f"emit-cadence: {exc}", file=sys.stderr)
        return 3

    return 0


if __name__ == "__main__":
    sys.exit(main())
