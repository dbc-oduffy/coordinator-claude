# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
coordinator/bin/distill-sidecar-sweep.py — thin CLI over
coordinator_core.distill.sidecar_sweep.

Purpose: pattern-matches process-scaffolding sidecar files (prior-art-check,
plan-coverage-check, docs-check, review, c0-findings, node-map, phase0, plus
timestamped variants) under a scan directory, and emits a deletion-manifest
(JSON to stdout) of candidates that clear the shared active-reference guard.
Candidates still actively referenced under docs/ tasks/ archive/ are reported
separately as retained, never as deletion rows.

Usage:
    coordinator/bin/distill-sidecar-sweep.py --scan-root <dir> [--repo-root <dir>]

    --scan-root   Directory to scan for sidecar files (required).
    --repo-root   Repo root for the active-reference guard scope
                  (default: cwd).

Read-only invariant: performs no writes / deletions. Emits JSON only.

Relocated from bin/distill-sidecar-sweep.py (DEC-3, 2026-07-23
Claude-klabauter-driven-ceremony-redesign) to coordinator/bin/ conventions — discoverability
(fleet `resolve-claude-klabauter-bin` machinery points at coordinator/bin, not top-level bin/)
plus Windows `.cmd` twin coverage. The old bin/ path is now a thin deprecation
forwarder; see that file. CLAUDE_KLABAUTER_ROOT is resolved via cc_invoke's
resolve_colocated_claude_klabauter_root ladder: this file's own coordinator/bin/ parent-of-
parent location is tried FIRST (self-location, zero external dependency, cannot be
unset) and accepted once it probes as a real claude-klabauter checkout; the machine-local
registry lookup is a fallback reached only if that probe misses (this file has been
published/vendored to a location outside the claude-klabauter checkout).

Spec backlink: pln-distill-ceremony-mechanical-su-1bcb38 § C2
Spec backlink: pln-claude-klabauter-driven-ceremony-redesig-c7fe9a § C6
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_LIB_DIR = str(Path(__file__).resolve().parent / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_colocated_engine_on_path  # noqa: E402

try:
    require_colocated_engine_on_path(__file__)
except RuntimeError as _exc:
    print(f"{Path(__file__).name}: CLAUDE_KLABAUTER_ROOT resolution failed: {_exc}", file=sys.stderr)
    sys.exit(1)

from coordinator_core.distill.sidecar_sweep import sweep_sidecars


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scan-root", required=True, type=Path, help="Directory to scan for sidecar files."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repo root for the active-reference guard scope (default: cwd).",
    )
    args = parser.parse_args(argv)

    result = sweep_sidecars(args.scan_root.resolve(), args.repo_root.resolve())
    output = {
        "deletion_manifest": result.deletion_manifest,
        "retained": result.retained,
    }
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
