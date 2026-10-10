#!/usr/bin/env python3
"""plan-chain-run — drive one accepted pm/ceo sizing from plan wave to terminal commit.

Usage:

    plan-chain-run --manifest <chain-manifest.json>

Builds a `ChainManifest` from the file, calls `plan_chain.run`, prints the final digest path then
the digest JSON. Exit 0 on a completed chain, 3 on a halt (a result, not a crash), 2 on usage.
Runs cold and long by design; it is deliberately absent from the warm entrypoint allowlist.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_HALTED = 3


def _bootstrap() -> None:
    import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path

    from cc_invoke import require_colocated_engine_on_path

    require_colocated_engine_on_path(__file__)


def _digest_path(manifest) -> Path | None:
    """Newest final digest under the manifest's trail dir; `run` returns the digest, not its path."""
    trail = Path(manifest.trail_dir)
    if not trail.is_absolute():
        trail = Path(manifest.repo_root) / trail
    found = sorted(trail.glob("chain-*.final-digest.json"), key=lambda p: p.stat().st_mtime)
    return found[-1] if found else None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="plan-chain-run", description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", required=True, help="chain manifest JSON written by emit-wave-fire --chain")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return EXIT_USAGE if exc.code else EXIT_OK

    _bootstrap()
    from coordinator_core.ops import plan_chain
    from coordinator_core.ops.plan_chain.contract import ChainManifest

    path = Path(args.manifest)
    try:
        manifest = ChainManifest.from_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        print(f"plan-chain-run: cannot read manifest {path}: {exc}", file=sys.stderr)
        return EXIT_USAGE

    digest = plan_chain.run(manifest)
    out = _digest_path(manifest)
    print(str(out) if out else "(final digest path unavailable)")
    print(json.dumps(digest, indent=2, sort_keys=True))
    halted = (digest.get("chain") or {}).get("halted_at")
    return EXIT_HALTED if halted else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
