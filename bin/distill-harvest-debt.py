# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
coordinator/bin/distill-harvest-debt.py — thin CLI wrapper over
coordinator_core.distill.harvest_debt.

Purpose: claude-klabauter's harvest-debt DR-047 distill-ceremony engine script. Parses the CANONICAL
distillation log (run|path|disposition|fate; ASCII "->") — plus the DoE schema-header
action-table format (date|action|path|...) sibling repos' live logs carry — and emits, as
JSON on stdout, the archive/specs paths (keyed specs_dir-relative, not bare basename) that
have never been recorded under a harvested disposition/action
(DISTILLED/PROMOTE/harvested/deleted; see harvest_debt.HARVESTED_DISPOSITIONS) — the
harvest-debt list — for the DoE distill Workflow/skill to consume.

Usage:
    coordinator/bin/distill-harvest-debt.py <specs-dir> <log-path>

Output (stdout, JSON): {"harvest_debt": [...], "harvested_count": N, "total_specs": N,
"warn": bool}

FAIL LOUD: if <log-path> does not exist, this exits non-zero with an error on stderr — it
NEVER treats an absent log as "nothing harvested yet, harvest everything."

Negative-spec: no LLM calls, no writes. All logic lives in
coordinator_core.distill.harvest_debt; this file is argv/stdout/exit-code plumbing only.

Relocated from bin/distill-harvest-debt.py (DEC-3, 2026-07-23
Claude-klabauter-driven-ceremony-redesign) to coordinator/bin/ conventions — discoverability
(fleet `resolve-claude-klabauter-bin` machinery points at coordinator/bin, not top-level bin/)
plus Windows `.cmd` twin coverage. The old bin/ path is now a thin deprecation
forwarder; see that file. The engine root is resolved via cc_invoke's
resolve_colocated_claude_klabauter_root ladder: this file's own coordinator/bin/ parent-of-
parent location is tried FIRST (self-location, zero external dependency, cannot be
unset) and accepted once it probes as a real claude-klabauter checkout; the machine-local
registry lookup is a fallback reached only if that probe misses (this file has been
published/vendored to a location outside the claude-klabauter checkout).

Spec backlink: pln-distill-ceremony-mechanical-su-1bcb38 § C4
Spec backlink: pln-claude-klabauter-driven-ceremony-redesig-c7fe9a § C6
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
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
    from coordinator_core.distill.harvest_debt import (
        DistillationLogMissingError,
        compute_harvest_debt,
    )

    parser = argparse.ArgumentParser(
        description=(
            "Parse the canonical distillation log and emit archive/specs paths "
            "(specs_dir-relative) absent from any harvested-disposition row "
            "(DISTILLED/PROMOTE/harvested/deleted) — the harvest-debt list."
        )
    )
    parser.add_argument("specs_dir", type=str, help="Path to the specs directory to scan (e.g. archive/specs).")
    parser.add_argument("log_path", type=str, help="Path to the canonical distillation log file.")
    args = parser.parse_args(argv)

    specs_dir = Path(args.specs_dir)
    log_path = Path(args.log_path)

    try:
        result = compute_harvest_debt(specs_dir, log_path)
    except DistillationLogMissingError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if result.warn:
        print(
            f"warning: harvest-debt ({len(result.harvest_debt)}) is disproportionately "
            f"large relative to the logged harvested-disposition rows ({result.harvested_count}) "
            "— the log may be stale or incomplete",
            file=sys.stderr,
        )

    json.dump(asdict(result), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
