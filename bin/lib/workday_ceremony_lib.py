"""workday_ceremony_lib — shared helpers for the workday-ceremony Python entrypoints.

Consumed by the native ports of the four /workday-{start,complete} ceremony step
scripts:
    - workday-start-step0.py                    (Step 0 branch precedence switch)
    - workday-complete-step1-validate.py        (Step 1 UBT + fast-test gate)
    - workday-complete-step3-consolidate.py      (Step 3 branch consolidation)
    - workday-complete-backfill-inject-anchor.py (Phase A0 anchor injection)

Purpose: git operations are done natively (subprocess `git`). The bash-lib bridge
(`bash_capture`/`lib_func`) this module used to expose for not-yet-ported bash libs is
RETIRED (de-bash campaign, docs/2026-07-29-debash-residual-sites-spec.md § Group C):
coordinator-daily-branch.sh (Port of: DoE 2fbe0e77, 2026-07-19), coordinator-daily-day.sh
(Port of: DoE c6d97219, 2026-07-22), coordinator-resolve-validation-cmd.sh (Port of: DoE
c187f5b9, 2026-07-21), and coordinator-state-root.sh (Port of: DoE 6fb5fb37, 2026-07-22)
were already retired before this — their consumer entrypoints import
coordinator_core.daily_branch / coordinator_core.machine_resolver / coordinator_core.daily_day
natively instead of using this bridge. The bridge's LAST caller,
workday-complete-backfill-inject-anchor.py's `_completion_count()`, used it only to reach
`coordinator-claude-klabauter-root.sh`'s `coordinator_claude_klabauter_root` function and to gate a
now-nonexistent `node` dependency on query-completions.py (itself already fully native —
see coordinator_core/ops/query_completions.py's own "Node-subprocess retirement" note); it
was repointed to `cc_invoke._resolve_claude_klabauter_root()` (the resolver the same file already
uses in `_derive_machine()`) plus a direct in-process call to
`coordinator_core.ops.ceremony.records_query.query_records`, so the bridge has zero
remaining callers. `bash_capture`/`lib_func`/`_source_prelude` are deleted rather than left
dead — the next lib that still needs porting gets a fresh bridge if one is ever needed
again, not a resurrected one.

Negative-spec: this is a LIBRARY module — no __main__, no CLI. Do NOT add a shebang-driven
entrypoint here; the four ceremony scripts are the entrypoints. Does NOT spawn `bash`/`sh`
anywhere — the transitional bridge that once did is retired (see Purpose above).
"""
from __future__ import annotations

import os
import subprocess
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from cc_invoke import require_engine_on_path  # noqa: E402

_ENGINE_ROOT = require_engine_on_path(__file__)

from coordinator_core.win_portability import no_console_creationflags  # noqa: E402


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def plugin_root() -> str:
    """Absolute path to the coordinator plugin root (the `coordinator/` tree).

    This module lives at coordinator/bin/lib/workday_ceremony_lib.py, so the
    plugin root is two directories up from bin/lib/.
    """
    _this_dir = os.path.dirname(os.path.abspath(__file__))  # .../coordinator/bin/lib
    return os.path.dirname(os.path.dirname(_this_dir))       # .../coordinator


def lib_dir(root: str | None = None) -> str:
    return os.path.join(root or plugin_root(), "lib")


# ---------------------------------------------------------------------------
# git convenience — native, no bash.
# ---------------------------------------------------------------------------

def git(
    *args: str,
    cwd: str | None = None,
    env: dict | None = None,
    check: bool = False,
    timeout: int = 300,
) -> subprocess.CompletedProcess:
    """Run `git <args>`; capture stdout/stderr as text. Never raises unless check=True."""
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        check=check,
        timeout=timeout,
        **no_console_creationflags(),
    )


def git_ok(*args: str, cwd: str | None = None, env: dict | None = None) -> bool:
    """True iff `git <args>` exits 0 (output discarded)."""
    return git(*args, cwd=cwd, env=env).returncode == 0


def git_out(*args: str, cwd: str | None = None, env: dict | None = None) -> str:
    """stdout of `git <args>`, stripped of the trailing newline (bash $() semantics).
    Returns '' on non-zero exit."""
    proc = git(*args, cwd=cwd, env=env)
    if proc.returncode != 0:
        return ""
    return proc.stdout.rstrip("\n")
