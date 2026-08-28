# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
# coordinator-doctor-sentinel.py — pure-Python CLI; no sh/python polyglot
# trampoline. Wave 4a (2026-07-20) dropped the .sh suffix and the trampoline
# entirely — this used to be coordinator-doctor-sentinel.sh, kept on .sh
# because callers referenced it by literal name; that call is reversed by the
# Wave 4a PM amendment, and every caller (workday-start.md,
# workday-start-cross-repo-memo-outbox-surface.py, and the test suites — see
# recipe § Callers/parity net) has been repointed to .py in the same wave.
# Invoke via the generated launcher (coordinator-doctor-sentinel.cmd/.ps1) or
# `python coordinator-doctor-sentinel.py` directly.
"""
coordinator-doctor-sentinel.py — CLI trampoline over claude-klabauter
coordinator_core.plugin_health.sentinel.

Fires the coordinator-doctor wiki's probes (P-1..P-19, minus the pre-existing
P-16 manifest/sentinel skew — see sentinel.py's module docstring) and writes
~/.claude/plugins/coordinator-claude/data/doctor-last-run.json that
scan-addon-health.py (coordinator_core.plugin_health.scan) consumes. Surfaces
daily via /workday-start Step 1.10 Addon Health.

Selection grammar (scalpel-not-hammer):
  bare / --triage        default; run only triage probes + emit RECOMMENDATION
  --full                 run all probes + write sentinel (cadence / daily path)
  --cluster NAME         run probes in cluster NAME; print verdict; do NOT write
  --probe ID             run single probe by id; print verdict; do NOT write
  --symptom TEXT         symptom match -> cluster(s) -> run those probes; do NOT write

Usage:
  coordinator-doctor-sentinel.py [--triage|--full|--cluster NAME|--probe ID|--symptom TEXT]

Exit codes: 0 — advisory (probe run completed, verdict is in stdout/sentinel);
2 — argument error or selector error (unknown cluster/probe/symptom, vacuous
selection, or no Python interpreter found); 1 — engine-root resolution or
import failure.

Environment: CLAUDE_HOME, COORDINATOR_PLUGINS_ROOT, MACHINE_LOCAL_REGISTRY_DIR,
COORDINATOR_PYTHON, DOCTOR_PROBES_MANIFEST, COORDINATOR_PREREQ_PROBE_LIB_DIR,
COORDINATOR_BIN_ROOT (test isolation for the DoE-side sibling-script root).

Spec backlink: DoE-claude:pln-bash-to-naked-python-engine-mi-c09292 § T3a-g2/T3b
Port of: coordinator-doctor-sentinel.sh (DoE b5a4192c, 2026-07-20; 989-line bash oracle)
"""

from __future__ import annotations

import os
import sys


def _import_main():
    """Resolve the engine root, put it on sys.path, and import the ported CLI entry.

    Also seeds COORDINATOR_BIN_ROOT (this script's own directory, i.e. THIS
    coordinator/bin/) so sentinel.py's DoE-side sibling-script resolution
    (P-9/P-11/P-12/P-13/P-15/P-17/P-18/P-19's still-bash dependency scripts)
    finds them relative to wherever this trampoline is actually installed,
    exactly mirroring the bash oracle's `_SCRIPT_DIR` (self-relative, not a
    hardcoded dev-clone path) — only set when unset, so an explicit operator/
    test override always wins.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    os.environ.setdefault(
        "COORDINATOR_BIN_ROOT", os.path.dirname(os.path.abspath(__file__))
    )
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.plugin_health.sentinel import main as _op_main

    return _op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(
            f"coordinator-doctor-sentinel.py: engine-root resolution failed: {exc}",
            file=sys.stderr,
        )
        return 1
    except ImportError as exc:
        print(
            "coordinator-doctor-sentinel.py: coordinator_core.plugin_health.sentinel "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        return 1

    return op_main((sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
