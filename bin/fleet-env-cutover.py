from __future__ import annotations

INSTALL_CLASS = True

import argparse
import sys
from pathlib import Path

_BIN_DIR = Path(__file__).resolve().parent

_RETRY_EXHAUSTED = 2


def _bootstrap_engine() -> None:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_colocated_engine_on_path

    require_colocated_engine_on_path(__file__)


def _report_check(env_root: Path) -> int:
    _bootstrap_engine()
    from coordinator_core.install import junction

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
    try:
        _bootstrap_engine()
    except RuntimeError as exc:
        print(f"fleet-env-cutover.py: could not locate the claude-klabauter engine: {exc}", file=sys.stderr)
        return 1

    from coordinator_core.install.fleet_env import (
        FleetEnvCutoverBlocked,
        FleetEnvError,
        _cutover_to_junction_layout,
        resolve_environment_root,
    )

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
