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

Root cause of `ModuleNotFoundError: No module named 'cc_invoke'` (oracle item
15, `docs/problems/2026-09-01-every-defect-the-oss-install-dogfood-sur.md`
#15; confirmed by staff-eng review at
`state/subagent-share/fd90860d-.../coordinatorstaff-eng.a3dc2f765549cecc2.md`
finding 1(b)): `coordinator_core/install/fleet_env.py::_load_c1_resolver`
loads THIS file via `importlib.util.spec_from_file_location` +
`exec_module` — not as the interpreter's top-level script. Only a script
run directly as `__main__` gets its own directory auto-prepended to
`sys.path[0]`; an `exec_module`-loaded module gets no such prepend. The old
`import lib` bootstrap relied entirely on that auto-prepend (this file's own
directory being on `sys.path` so the bare-name `lib` package resolves), so
under the installer's real load path it silently failed to put
`coordinator/bin/lib` on `sys.path`, and the subsequent `import cc_invoke`
had nowhere to find it. `resolve_fleet_env_root` below computes the lib
directory from its own `__file__` instead (the same `__file__`-based
pattern `cc_invoke.py` itself uses for its self-bootstrap, ` :441-443`),
which is invocation-path-independent — it works identically whether this
file is run as `__main__`, `exec_module`-loaded, or imported by package
path.

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

#: `coordinator/bin/lib`, derived from this file's own `__file__` — never
#: from `sys.path[0]`. See module docstring's "Root cause" note: an
#: `exec_module`-loaded copy of this file (the installer's real load path,
#: `coordinator_core/install/fleet_env.py::_load_c1_resolver`) gets no
#: auto-prepended script directory, so the bootstrap must be
#: invocation-path-independent.
_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")


def _repo_root_from_file() -> str:
    """Repo root derived from this file's own location -- `coordinator/bin/
    fleet-env.py` is two directories under it -- the same `__file__`-based,
    invocation-path-independent pattern `_LIB_DIR` already uses above.
    Review: overengineering-reviewer -- the degrade route in
    `resolve_fleet_env_root`'s except clause used to re-run
    `_import_cc_invoke()` and `_resolve_claude_klabauter_root()` to reach this path,
    which re-derives exactly the import the try block just failed on; a
    packaging defect that makes `cc_invoke` unimportable made that route
    fail silently for the one case DR-402 rung 3 names. This helper reaches
    the same root without importing `cc_invoke` at all."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _import_cc_invoke():
    """Import `cc_invoke` with an invocation-path-independent bootstrap.

    Inserts `_LIB_DIR` onto `sys.path` directly (mirroring `cc_invoke.py`'s
    own `__file__`-based self-bootstrap, ` :441-443`) rather than going
    through the bare-name `lib` package, whose own bootstrap only fires
    reliably when this file's directory is already on `sys.path` — true for
    `python fleet-env.py ...` but NOT true for `exec_module` loading. See
    module docstring's "Root cause" note for the failure this replaces.
    """
    if _LIB_DIR not in sys.path:
        sys.path.insert(0, _LIB_DIR)
    import cc_invoke

    return cc_invoke


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

    DR-402 rung 3 (`docs/decisions/DR-402-...md`): if the bootstrap or the
    read itself fails for any reason (e.g. a packaging defect that leaves
    `cc_invoke` unimportable), this step PROCEEDS — it never aborts the
    install over it — but the failure is recorded as a durable, attributable
    degrade row (`warm/telemetry.py::record_degrade`) rather than left
    silent. Best-effort: a failure to record the row itself is swallowed by
    `record_degrade`, never allowed to mask the original failure.
    """
    try:
        cc_invoke = _import_cc_invoke()
        return cc_invoke._machine_local_get(_FLEET_ENV_ROOT_KEY)
    except Exception as exc:
        try:
            claude_klabauter_root = _repo_root_from_file()
            if claude_klabauter_root not in sys.path:
                sys.path.insert(0, claude_klabauter_root)
            from coordinator_core.warm import telemetry

            telemetry.record_degrade(
                kind=telemetry.KIND_COLD_FAILED,
                cause=(
                    "fleet-env.py::resolve_fleet_env_root: fleet_env.root "
                    f"read failed ({type(exc).__name__}: {exc}); fleet "
                    "environment provisioning proceeds without it "
                    "(DR-402 rung 3)"
                ),
            )
        except Exception:
            pass
        return None


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
