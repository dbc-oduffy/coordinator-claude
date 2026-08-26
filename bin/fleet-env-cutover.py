"""fleet-env-cutover.py — one-time cutover of the fleet shared environment
from a real directory to the junction layout (C4).

Purpose: the named runnable fallback `_cutover_to_junction_layout`
(`coordinator_core/install/fleet_env.py`) points operators at when its
bounded retry is exhausted — a fleet session was importing the whole
`retry_budget_secs` window, so the caller stopped rather than looping
unboundedly or forcing the rename. Re-running this script IS the retry:
`_cutover_to_junction_layout` is idempotent (already-junction is a no-op),
so running it again costs nothing if a prior attempt already succeeded.

Why a script and not a slash command: this can run before any Claude Code
session exists (cold path) — a slash command names a remedy that cannot run
at that moment. See CLAUDE.md § Runtime conventions "Cold-path remediation
text names a runnable script, never a slash command" and
`coordinator/tests/test_cold_path_remediation_is_runnable.py`.

Usage:
    python3 coordinator/bin/fleet-env-cutover.py           # perform the cutover
    python3 coordinator/bin/fleet-env-cutover.py --check   # report layout only, no mutation
    python3 coordinator/bin/fleet-env-cutover.py --help

Exit codes: 0 — already a junction, or cutover succeeded. 1 — resolution or
provisioning error (`FleetEnvError`). 2 — retry budget exhausted
(`FleetEnvCutoverBlocked`) — a fleet session is still importing; retry later.

Spec backlink: docs/plans/2026-08-20-the-fleet-env-publishes-through-a-juncti.md § C4
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_BIN_DIR = Path(__file__).resolve().parent
_LIB_DIR = _BIN_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
from cc_invoke import require_colocated_engine_on_path  # noqa: E402

try:
    require_colocated_engine_on_path(__file__)
except RuntimeError as exc:
    print(f"fleet-env-cutover.py: could not locate the claude-klabauter engine: {exc}", file=sys.stderr)
    sys.exit(1)

from coordinator_core.install import junction  # noqa: E402
from coordinator_core.install.fleet_env import (  # noqa: E402
    FleetEnvCutoverBlocked,
    FleetEnvError,
    _cutover_to_junction_layout,
    resolve_environment_root,
)

_RETRY_EXHAUSTED = 2


def _report_check(env_root: Path) -> int:
    if junction.is_junction(env_root):
        target = junction.junction_target(env_root)
        print(f"fleet-env-cutover.py: {env_root} is already a junction -> {target}")
        return 0
    if env_root.is_dir():
        print(
            f"fleet-env-cutover.py: {env_root} is a real directory — the "
            "pre-junction layout. Run without --check to cut it over."
        )
        return 0
    print(f"fleet-env-cutover.py: {env_root} does not exist.")
    return 0


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fleet-env-cutover.py",
        description=(
            "One-time cutover of the fleet environment root from a real "
            "directory to the junction publication layout."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report the current layout without mutating disk.",
    )
    args = parser.parse_args(argv)

    try:
        env_root = resolve_environment_root()
    except FleetEnvError as exc:
        print(f"fleet-env-cutover.py: {exc}", file=sys.stderr)
        return 1

    if args.check:
        return _report_check(env_root)

    try:
        outcome = _cutover_to_junction_layout(env_root)
    except FleetEnvCutoverBlocked as exc:
        print(str(exc), file=sys.stderr)
        return _RETRY_EXHAUSTED
    except FleetEnvError as exc:
        print(f"fleet-env-cutover.py: {exc}", file=sys.stderr)
        return 1

    if outcome.status == "already-junction":
        print(
            f"fleet-env-cutover.py: {env_root} is already a junction -> "
            f"{outcome.generation} — nothing to do."
        )
    else:
        print(
            f"fleet-env-cutover.py: cut {env_root} over to a junction "
            f"pointing at {outcome.generation}; verified a read through it."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
