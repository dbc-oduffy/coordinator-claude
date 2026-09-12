# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""coordinator-resolve-validation-cmd.py — thin CLI trampoline over
coordinator_core.resolve_validation_cmd.

Consolidation (C1, docs/plans/2026-07-30-diff-scoped-ceremony-gates-elegant.md
Design decision 1): this file used to carry its OWN independent resolver
implementation, which had drifted from coordinator_core/resolve_validation_cmd.py
(a repo-local `.venv`-first interpreter preference, a Windows `sys.executable`
preference, and a different return-type/exception shape). That superset
behaviour now lives in ONE place — coordinator_core.resolve_validation_cmd's
bin-shape API section — and this file re-exports it rather than
re-implementing it. Path, CLI contract (--fast/--full/--read-key), exit-code
contract (0/2/3/126/127), and module-level names (resolve_fast_test_cmd,
resolve_full_test_cmd, read_local_md_key, main) are UNCHANGED — AC1/AC11.

`main(argv)` MUST stay importable from this path: the consumes-manifest
dispatch does `getattr(module, "main", None)`, and a prior rename of it
silently broke `d_step2_resolve_validation_cmd`.

Three in-process callers load this file via `importlib.util.spec_from_file_location`
and consume `.stdout`/`.stderr`/`.returncode` off the resolved result, plus
module-private attributes (`_resolve_python_interp`, `_normalize_python_token`,
`shutil`, `sys`, `os`) for direct testing/monkeypatch — see
coordinator/bin/tests/test_coordinator_resolve_validation_cmd.py, which loads
this file the same way and monkeypatches `rvc.shutil`/`rvc.sys`/`rvc.os`
directly. Because `os`/`sys`/`shutil` are singleton stdlib modules, patching
an attribute on this module's imported reference to them patches the SAME
object coordinator_core.resolve_validation_cmd's functions call into — the
monkeypatch reaches the real implementation even though it now lives in a
different module.

Spec backlink: archive/specs/2026-05-28-workday-complete-fast-test-resolution.md § 3.4
Consolidation backlink: docs/plans/2026-07-30-diff-scoped-ceremony-gates-elegant.md (C1)
"""

from __future__ import annotations

import os
import shutil
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_BOOTSTRAP_DONE = False


def _bootstrap_engine() -> None:
    """Put the repo root on ``sys.path`` before ``coordinator_core`` is
    imported.

    coordinator_core is co-located in this same repo (claude-klabauter) --
    resolvable only from the repo root, which is NOT on sys.path when this
    file is run directly (its own dir is) or loaded via
    importlib.util.spec_from_file_location by a sibling script (e.g.
    workday-complete-step1-validate.py). Idempotent; safe to call more than
    once.
    """
    global _BOOTSTRAP_DONE
    if _BOOTSTRAP_DONE:
        return
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)
    _BOOTSTRAP_DONE = True


_bootstrap_engine()

from coordinator_core.resolve_validation_cmd import (  # noqa: E402
    InterpreterMissing,
    MalformedValue,
    ResolveResult,
    _metachar_warn,
    _normalize_python_token,
    _read_frontmatter,
    _read_frontmatter_key,
    _resolve_python_interp,
    _venv_interp,
    main,
    read_local_md_key,
    resolve_fast_test_cmd,
    resolve_full_test_cmd,
)

__all__ = [
    "InterpreterMissing",
    "MalformedValue",
    "ResolveResult",
    "main",
    "read_local_md_key",
    "resolve_fast_test_cmd",
    "resolve_full_test_cmd",
]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
