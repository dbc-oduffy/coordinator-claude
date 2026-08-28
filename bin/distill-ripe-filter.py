# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
coordinator/bin/distill-ripe-filter.py — thin CLI wrapper over
coordinator_core.distill.ripe_filter.

Purpose: claude-klabauter's first DR-047 distill-ceremony engine script. Scans a spec directory's
Markdown frontmatter (recursing into subdirectories, so a month-foldered
`archive/specs/YYYY-MM/` layout is one invocation) and emits a JSON partition of
harvest-ripe vs skip-worthy specs on stdout, for the DoE distill Workflow/skill to consume.

Usage:
    coordinator/bin/distill-ripe-filter.py <spec-dir>

Output (stdout, JSON): {"harvest": [...], "skip": [{"path", "status", "reason"}, ...]}

Negative-spec: no LLM calls, no writes, no coupling to the canonical distillation log or
DoE's distill_fate schema — pure frontmatter scan. All logic lives in
coordinator_core.distill.ripe_filter; this file is argv/stdout plumbing only.

Relocated from bin/distill-ripe-filter.py (DEC-3, 2026-07-23
Claude-klabauter-driven-ceremony-redesign) to coordinator/bin/ conventions — discoverability
(fleet `resolve-claude-klabauter-bin` machinery points at coordinator/bin, not top-level bin/)
plus Windows `.cmd` twin coverage. The old bin/ path is now a thin deprecation
forwarder; see that file. The engine root is resolved via cc_invoke's
resolve_colocated_claude_klabauter_root ladder: this file's own coordinator/bin/ parent-of-
parent location is tried FIRST (self-location, zero external dependency, cannot be
unset) and accepted once it probes as a real claude-klabauter checkout; the machine-local
registry lookup is a fallback reached only if that probe misses (this file has been
published/vendored to a location outside the claude-klabauter checkout).

Spec backlink: pln-distill-ceremony-mechanical-su-1bcb38 § C1
Spec backlink: pln-claude-klabauter-driven-ceremony-redesig-c7fe9a § C6
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

def _bootstrap_engine() -> None:
    """Bootstrap coordinator/bin/lib onto sys.path and resolve the engine root.

    Moved out of module scope so this file carries no non-stdlib import at
    module scope — same failure/exit behavior preserved.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_colocated_engine_on_path

    try:
        require_colocated_engine_on_path(__file__)
    except RuntimeError as _exc:
        print(f"{Path(__file__).name}: engine-root resolution failed: {_exc}", file=sys.stderr)
        sys.exit(1)


def main(argv: list[str] | None = None) -> int:
    _bootstrap_engine()
    from coordinator_core.distill.ripe_filter import scan_spec_dir

    parser = argparse.ArgumentParser(
        description="Scan a spec directory's frontmatter and partition into harvest-ripe vs skip."
    )
    parser.add_argument("spec_dir", type=str, help="Path to the spec directory to scan.")
    args = parser.parse_args(argv)

    spec_dir = Path(args.spec_dir)
    if not spec_dir.is_dir():
        print(f"error: not a directory: {spec_dir}", file=sys.stderr)
        return 1

    result = scan_spec_dir(spec_dir)
    json.dump(result.to_dict(), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
