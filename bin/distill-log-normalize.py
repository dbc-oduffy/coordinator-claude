# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
coordinator/bin/distill-log-normalize.py — thin CLI wrapper over
coordinator_core.distill.log_normalize.

Purpose: the one-time, run-once-per-repo migrator from a legacy pipe-table distillation
log (`date | action | path | last_sha | belongs_to_spec | reason`) to the DoE C1 canonical
schema (`## Run <run-id>` / `- <path> -> <disposition>, <fate> (run: <run-id>)`).

Usage:
    python3 coordinator/bin/distill-log-normalize.py --log-path state/distillation-log.md

Emits a single-line JSON result object on stdout matching contract §7 exactly:
    {"log_path": "<str>", "rows_migrated": <int>, "rows_skipped": <int>,
     "skipped": [{"line": <int>, "reason": "<str>"}], "backup_path": "<str>"}
Exits 0 on success. Exits 2 (benign, already-migrated no-op) if the log is already
canonical. Exits 1 with a JSON error object on stdout ({"error": "<message>"}) for any
other genuine error (missing file, not legacy-shaped, existing backup collision).

# Review: code-reviewer (Finding 7) — a distinct exit code for the benign
# already-canonical outcome lets a scripted caller (e.g. a setup/install step) treat
# "already migrated" as a no-op success rather than string-matching the error message.

Negative-spec: this CLI performs the migration exactly once per invocation and never
deletes the legacy file — the pre-migration original is preserved at `backup_path`.

Relocated from bin/distill-log-normalize.py (DEC-3, 2026-07-23
Claude-klabauter-driven-ceremony-redesign) to coordinator/bin/ conventions — discoverability
(fleet `resolve-claude-klabauter-bin` machinery points at coordinator/bin, not top-level bin/)
plus Windows `.cmd` twin coverage. The old bin/ path is now a thin deprecation
forwarder; see that file. The engine root is resolved via cc_invoke's
resolve_colocated_claude_klabauter_root ladder: this file's own coordinator/bin/ parent-of-
parent location is tried FIRST (self-location, zero external dependency, cannot be
unset) and accepted once it probes as a real claude-klabauter checkout; the machine-local
registry lookup is a fallback reached only if that probe misses (this file has been
published/vendored to a location outside the claude-klabauter checkout).

Spec backlink: pln-distill-ceremony-mechanical-su-1bcb38 § C8;
DoE-claude/docs/contracts/distill-engine-scripts.md § 7 (binding I/O contract).
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
    from coordinator_core.distill.log_normalize import (
        AlreadyCanonicalError,
        NotLegacyShapedError,
        normalize_log,
    )

    parser = argparse.ArgumentParser(
        description="One-time migration of a legacy pipe-table distillation log to C1 canonical shape."
    )
    parser.add_argument("--log-path", required=True, help="Path to the legacy-shaped log file.")
    args = parser.parse_args(argv)

    log_path = Path(args.log_path)

    try:
        result = normalize_log(log_path)
    except AlreadyCanonicalError as exc:
        json.dump({"error": str(exc)}, sys.stdout)
        sys.stdout.write("\n")
        return 2
    except (FileNotFoundError, NotLegacyShapedError, FileExistsError) as exc:
        json.dump({"error": str(exc)}, sys.stdout)
        sys.stdout.write("\n")
        return 1

    json.dump(result.to_dict(), sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
