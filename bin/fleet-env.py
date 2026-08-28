# Unix shebang — see advance-tracker-status.py's own module docstring for the
# generator-retirement note this line's presence/absence follows; kept for
# parity with the rest of this family's convention.
"""fleet-env.py — operator CLI over the fleet-environment registry key.

Purpose: `fleet_env.root` (minted by C0, see
`docs/reference/fleet-shared-environment-contract.md` § DECISIONS (b)) is the
fleet's one documented entry point to the shared Python environment. This
script is the resolver that turns that key into an environment path, plus the
operator-facing CLI that reads it. No other code in this repo may read a
hardcoded path to the environment (plan AC1) — this file, and modules that
import its resolver function, are the sole read site.

Contract used, and why: `fleet_env.root`'s VALUE is a filesystem path, but the
mechanism that reaches that value is the read-a-key contract
(`coordinator/bin/lib/cc_invoke.py::_machine_local_get`), not
`coordinator/bin/lib/machine_local_resolve.py`. The latter resolves the
`machine-local` CLI EXECUTABLE's own location for a caller that needs an
invokable binary path to `subprocess.run` directly — it performs no registry
read at all (see that module's own docstring). `_machine_local_get` already
has a precedent for a path-valued key: `_machine_local_get("repos.claude_klabauter")`
(`cc_invoke.py`, `_resolve_claude_klabauter_root`'s rung 2). This script delegates to
`_machine_local_get` for the read; it does not re-derive a second resolution
ladder. `machine_local_resolve.resolve_machine_local_bin` is unused here —
`_machine_local_get` already resolves its own `machine-local` invocation
internally (via `machine_local_impl_resolve`), so this script never needs to
locate that binary itself.

Day-one absent-key behaviour (AC5b, priced here per C1's own body, not C5):
absent-or-unreadable resolves to the documented default AT THE READ SITE
(`resolve_fleet_env_root` below), never as a second stored registry value.
That default is `None` — this module names no directory fallback of its own;
locating a working fallback location for an absent key is C5's
`coordinator_core/install/fleet_env_resolve.py` fallback ladder, not this
file's concern. A caller wanting "the key, or else a usable directory" needs
C5's ladder; this module answers only "what does the registry say."

Negative-spec: does not build, provision, or health-probe the environment
(C4); does not implement the absent-key fallback ladder (C5); does not
implement sibling `.pth` binding (C6). Read-only against the registry.

Exit codes: 0 — path printed to stdout. 2 — usage error (bad/missing subcommand). 3 — key absent
or unreadable; remediation printed to stderr.

Spec backlink: docs/plans/2026-08-16-one-environment-for-the-fleet.md C1
Spec backlink: docs/reference/fleet-shared-environment-contract.md § DECISIONS (b)
"""
from __future__ import annotations

import argparse
import os
import sys

_FLEET_ENV_ROOT_KEY = "fleet_env.root"

_USAGE_FAIL = 2
_ABSENT = 3


def resolve_fleet_env_root() -> "str | None":
    """Return the fleet environment's root path, or None if the key is absent
    or unreadable.

    The sole sanctioned read site for `fleet_env.root` (plan AC1 — no other
    code in this repo may read a hardcoded path to the environment). Delegates
    to `cc_invoke._machine_local_get`, the read-a-key contract; see module
    docstring for why that contract and not `machine_local_resolve`.

    None on absence is a normal, expected outcome during the rollout window
    documented in `docs/reference/fleet-shared-environment-contract.md` § The
    day-one absent-key property — this function names no fallback directory
    of its own. A caller wanting a working fallback location for the absent
    case uses `coordinator_core/install/fleet_env_resolve.py` (C5).
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    import cc_invoke

    return cc_invoke._machine_local_get(_FLEET_ENV_ROOT_KEY)


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fleet-env.py",
        description=(
            "Read the fleet-environment registry key (fleet_env.root) and "
            "print its resolved path."
        ),
    )
    parser.add_argument(
        "command",
        choices=["get"],
        help="get — print the resolved fleet_env.root path, or report absence.",
    )
    args = parser.parse_args(argv)

    if args.command != "get":
        parser.print_usage(sys.stderr)
        return _USAGE_FAIL

    root = resolve_fleet_env_root()
    if root is None:
        print(
            "fleet-env.py: fleet_env.root is not set on this machine. "
            "Set it with: machine-local set fleet_env.root <path>. "
            "For a working fallback, use coordinator_core.install.fleet_env_resolve's ladder.",
            file=sys.stderr,
        )
        return _ABSENT

    print(root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
