# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""bin/sync-cockpit-contract.py — Vendor-sync staleness check for the cockpit-contract JSON Schema.

Purpose: consumer-invocable precondition check that detects version DRIFT between the
canonical cockpit-contract schema (authored here, under cockpit-contract/schema/) and a
vendored copy in a consumer repo (e.g. Example-cockpit-repo at contract/schema/).

Designed to be run BEFORE a re-vendor: if drift is detected the consumer knows to pull the
latest schema/*.json and regenerate (bin/regen-cockpit-schema.py) before ingesting new snapshots.
This is the producer-side half of the vendor-sync safety gate (tc-1 R5 / the Director of Engineering Z-F4);
the consumer-side half is the ingest-time schema_version assertion in example-cockpit-repo
src/lib/store/ingest.ts (Ask-1).

Spec backlink: state/handoffs/2026-06-22_230001_roadmap-cockpit-contract-ext-2026-06-22-tc-1.md
§ Vendor-sync staleness gate (the Director of Engineering Z-F1/Z-F4).
Port backlink: docs/plans/2026-07-19-debash-coordinator-windows.md § E3-b

Usage:
  sync-cockpit-contract.py --vendored <path/to/vendored/cockpit-contract.schema.json>
  sync-cockpit-contract.py --vendored <path> [--canonical <path>]
  COCKPIT_CANONICAL=<path> COCKPIT_VENDORED=<path> sync-cockpit-contract.py

Exit codes:
  0  — versions match (in sync)
  1  — DRIFT: versions differ, or vendored copy missing
  2  — usage / environment error (canonical schema missing, bad flags)
"""
from __future__ import annotations

import json
import os
import sys

def _default_canonical() -> str | None:
    """Resolve the canonical cockpit-contract schema path via
    `coordinator_data_root.data_root()`'s co-located/DoE-resident two-rung
    chain, not a bare `__file__`-relative walk: the 2026-07-22
    executable-surface migration moved this script into claude-klabauter while
    `cockpit-contract/` (contract data, DR-047) stayed in DoE-claude, so a
    `${script_dir}/../cockpit-contract` walk no longer lands anywhere.

    Returns None if data_root can't resolve it — an explicit --canonical or
    COCKPIT_CANONICAL override must still work even when this default can't
    resolve, so failure here is surfaced at the call site as a normal
    "canonical schema not found" error, not an import-time crash.
    """
    try:
        import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
        from coordinator_data_root import data_root

        return os.path.join(
            str(data_root("cockpit-contract")), "schema", "cockpit-contract.schema.json"
        )
    except RuntimeError:
        return None


def _read_version(path: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    version = data.get("version") if isinstance(data, dict) else None
    if not version:
        return None
    return str(version)


def main(argv: list[str]) -> int:
    canonical = os.environ.get("COCKPIT_CANONICAL") or _default_canonical() or ""
    vendored = os.environ.get("COCKPIT_VENDORED", "")
    prog = os.path.basename(sys.argv[0])

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--canonical":
            if i + 1 >= len(argv):
                print("ERROR: --canonical requires a path", file=sys.stderr)
                return 2
            canonical = argv[i + 1]
            i += 2
        elif arg == "--vendored":
            if i + 1 >= len(argv):
                print("ERROR: --vendored requires a path", file=sys.stderr)
                return 2
            vendored = argv[i + 1]
            i += 2
        elif arg in ("-h", "--help"):
            print(__doc__)
            return 0
        else:
            print("ERROR: unknown argument: %s" % arg, file=sys.stderr)
            print(
                "Usage: %s --vendored <path> [--canonical <path>]" % prog,
                file=sys.stderr,
            )
            return 2

    if not vendored:
        print(
            "ERROR: --vendored <path> is required (or set COCKPIT_VENDORED env var).",
            file=sys.stderr,
        )
        print(
            "  Example: %s --vendored <cockpit>/contract/schema/cockpit-contract.schema.json"
            % prog,
            file=sys.stderr,
        )
        return 2

    if not os.path.isfile(canonical):
        print("ERROR: canonical schema not found: %s" % canonical, file=sys.stderr)
        print(
            "  Override with --canonical <path> or COCKPIT_CANONICAL env var.",
            file=sys.stderr,
        )
        return 2

    canonical_version = _read_version(canonical)
    if not canonical_version:
        print(
            "ERROR: could not read .version from canonical schema: %s" % canonical,
            file=sys.stderr,
        )
        return 2

    if not os.path.isfile(vendored):
        print("DRIFT: vendored schema not found at: %s" % vendored, file=sys.stderr)
        print("  Canonical version: v%s" % canonical_version, file=sys.stderr)
        print(
            "  Action: vendor schema/*.json from cockpit-contract/schema/ and "
            "run bin/regen-cockpit-schema.py before ingest.",
            file=sys.stderr,
        )
        return 1

    vendored_version = _read_version(vendored)
    if not vendored_version:
        print(
            "DRIFT: could not read .version from vendored schema: %s" % vendored,
            file=sys.stderr,
        )
        print("  Canonical version: v%s" % canonical_version, file=sys.stderr)
        print(
            "  Action: re-vendor schema/*.json and run bin/regen-cockpit-schema.py "
            "before ingest.",
            file=sys.stderr,
        )
        return 1

    if canonical_version == vendored_version:
        print("in sync (v%s)" % canonical_version)
        return 0

    print(
        "DRIFT: canonical v%s vs vendored v%s — re-vendor schema/*.json and run "
        "bin/regen-cockpit-schema.py before ingest."
        % (canonical_version, vendored_version),
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
