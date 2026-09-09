"""fleet-env-bind.py — the sibling-facing CLI over the fleet environment's binding registry.

Purpose: `docs/reference/fleet-shared-environment-contract.md` § The sibling
`.pth` binding contract tells a sibling-repo maintainer to "call
`coordinator_core.install.fleet_env.register_sibling_binding(...)`". That
instruction had no reachable surface. `register_sibling_binding` is an
in-process engine API, and a sibling repo cannot import `coordinator_core`:
the tri-plane boundary puts the engine in claude-klabauter's plane
(`docs/reference/boundary-and-data-planes.md`), and consumers like
Example-market-data-repo declare no engine dependency and resolve no engine root.
So every consumer the contract addresses was told to make a call it had no
way to make.

This file closes that. It is the binding surface's exact analogue of
`fleet-env.py`, which is already how a sibling reaches the OTHER half of the
contract (`fleet-env.py get` for the root). A sibling shells out to a
documented CLI with a documented exit-code contract; it never imports the
engine, never reads the binding registry, and never writes a `.pth` itself.

Found by example-market-data-repo-em while wiring `example-market-data-repo/scripts/setup.py`
to the fleet environment — the first consumer to actually follow the contract's
instruction end to end.

Why a script and not a slash command: this runs from another repo's INSTALLER,
before any Claude Code session exists. See CLAUDE.md § Runtime conventions
"Cold-path remediation names a runnable script, never a slash command" and
`coordinator/tests/test_cold_path_remediation_is_runnable.py`.

Usage:
    python3 coordinator/bin/fleet-env-bind.py register <repo> <sibling> <absolute-path>
    python3 coordinator/bin/fleet-env-bind.py deregister <repo> <sibling>
    python3 coordinator/bin/fleet-env-bind.py check
    python3 coordinator/bin/fleet-env-bind.py --help

`register` is safe to call when the environment does not yet exist — that is
the normal rollout-window state, not an error. The registry entry persists and
the next provisioning pass replays it into the new tree
(`fleet_env._replay_sibling_bindings`, run unconditionally after every
rebuild). This is the property that makes a consumer's install order
independent of the fleet's provisioning order, and it is why `register`
returning 0 does NOT assert that a `.pth` exists yet. `check` is what asserts
that.

Exit codes, matching `fleet-env.py`'s family:
    0  registered / deregistered, or `check` found nothing wrong
    1  the operation failed (`FleetEnvError` — e.g. a relative sibling path)
    2  usage error (bad/missing subcommand or arity)
    3  `check` only: there is nothing to check bindings against on this
       machine — either the root does not resolve at all, or it resolves but
       the environment has never been provisioned there. Distinct from exit 1
       — absence is not a failure, per § The day-one absent-key property.
    4  `check` only: the environment IS provisioned, and a registered binding
       is flagged (`stale_path` or `missing_pth`). Reported by name on
       stdout, never silently.

`check` deliberately splits "cannot look" (3) from "looked and found problems"
(4), and the split takes real work rather than falling out of the API. On an
unprovisioned machine `resolve_environment_root` does NOT raise: C5's fallback
ladder degrades to `<settings-home>/.fleet-env`, so a root always comes back.
Its site-packages then does not exist, so `check_sibling_bindings` correctly
reports every registered binding as `missing_pth`. Returning 4 there would fire
on every machine mid-rollout and train a caller to ignore the code — so this
script probes for the provisioned tree first and returns 3. Exit 4 therefore
means what a caller needs it to mean: the environment is really there and a
binding is really broken.

Spec backlink: docs/reference/fleet-shared-environment-contract.md § The sibling `.pth` binding contract
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_USAGE_FAIL = 2
_UNRESOLVABLE = 3
_FLAGGED = 4


def _bootstrap_engine() -> None:
    """Put `coordinator/bin/lib` and the resolved claude-klabauter engine on `sys.path`.

    Same shape and same call order as `fleet-env-cutover.py::_bootstrap_engine`
    — `import lib` before `require_colocated_engine_on_path`. Copied
    deliberately rather than re-derived: this family's bootstrap has a
    recorded failure mode (see `fleet-env.py`'s module docstring, "Root cause
    of ModuleNotFoundError"), and a second spelling of it is how that
    recurs.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_colocated_engine_on_path

    require_colocated_engine_on_path(__file__)


def _cmd_register(repo: str, sibling: str, path: str) -> int:
    _bootstrap_engine()
    from coordinator_core.install.fleet_env import FleetEnvError, register_sibling_binding

    try:
        register_sibling_binding(repo, sibling, path)
    except FleetEnvError as exc:
        print(f"fleet-env-bind.py: {exc}", file=sys.stderr)
        return 1
    print(f"fleet-env-bind.py: registered {repo} -> {sibling} = {path}")
    return 0


def _cmd_deregister(repo: str, sibling: str) -> int:
    _bootstrap_engine()
    from coordinator_core.install.fleet_env import FleetEnvError, deregister_sibling_binding

    try:
        deregister_sibling_binding(repo, sibling)
    except FleetEnvError as exc:
        print(f"fleet-env-bind.py: {exc}", file=sys.stderr)
        return 1
    print(f"fleet-env-bind.py: deregistered {repo} -> {sibling}")
    return 0


def _cmd_check() -> int:
    _bootstrap_engine()
    from coordinator_core.install.fleet_env import (
        FleetEnvError,
        _site_packages_dir,
        check_sibling_bindings,
        resolve_environment_root,
    )

    _NOT_PROVISIONED = (
        "Registered bindings, if any, are intact and replay on the next provisioning pass."
    )

    try:
        env_root = resolve_environment_root()
    except FleetEnvError as exc:
        # Rare: both of C5's ladder rungs unwritable. Not a failure.
        print(
            f"fleet-env-bind.py: the fleet environment root does not resolve on this "
            f"machine ({exc}). {_NOT_PROVISIONED}",
            file=sys.stderr,
        )
        return _UNRESOLVABLE

    # The common rollout-window state, and the reason this probe exists: the
    # root resolves (C5's ladder always yields one) but nothing was ever built
    # there. Every registered binding would read `missing_pth`, which is
    # accurate and useless — see the exit-code note in the module docstring.
    if not _site_packages_dir(Path(env_root)).is_dir():
        print(
            f"fleet-env-bind.py: {env_root} resolves but carries no provisioned "
            f"environment. {_NOT_PROVISIONED}",
            file=sys.stderr,
        )
        return _UNRESOLVABLE

    flagged = check_sibling_bindings(Path(env_root))
    if not flagged:
        print(f"fleet-env-bind.py: all registered bindings resolve against {env_root}")
        return 0
    for binding in flagged:
        print(
            f"fleet-env-bind.py: FLAGGED {binding['reason']} "
            f"{binding['repo']} -> {binding['sibling']} = {binding['path']}"
        )
    return _FLAGGED


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fleet-env-bind.py",
        description=(
            "Register, remove, or verify a sibling repo's binding into the fleet "
            "shared environment. The one surface a sibling repo uses; it must not "
            "import coordinator_core itself."
        ),
    )
    sub = parser.add_subparsers(dest="command")

    p_register = sub.add_parser(
        "register",
        help="register (or replace) a binding; safe before the environment exists",
    )
    p_register.add_argument("repo", help="the binding's owning repo, e.g. market_intel")
    p_register.add_argument("sibling", help="what is being bound, e.g. project_rag")
    p_register.add_argument("path", help="ABSOLUTE path to bind onto sys.path")

    p_deregister = sub.add_parser("deregister", help="remove a binding and its .pth")
    p_deregister.add_argument("repo")
    p_deregister.add_argument("sibling")

    sub.add_parser("check", help="report every registered binding that is stale or unreplayed")

    args = parser.parse_args(argv)

    if args.command == "register":
        return _cmd_register(args.repo, args.sibling, args.path)
    if args.command == "deregister":
        return _cmd_deregister(args.repo, args.sibling)
    if args.command == "check":
        return _cmd_check()

    parser.print_usage(sys.stderr)
    return _USAGE_FAIL


if __name__ == "__main__":
    sys.exit(main())
