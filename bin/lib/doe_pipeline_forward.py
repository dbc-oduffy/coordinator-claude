"""doe_pipeline_forward - run a script from DoE's coordinator/pipelines tree under a bare CLI name.

A trampoline in coordinator/bin calls forward(relpath, name); the DoE root comes only from
coordinator_data_root.data_root("pipelines"), so no second copy of that ladder exists here.

Invariants:
  - The target runs in-process via runpy, never as a child process: the spawn count stays at
    the one interpreter the caller already paid for.
  - Help is answered locally and resolves nothing, so the name stays publishable on a box
    with no DoE clone.
  - SystemExit from the target propagates untouched; its exit code is the caller's.
  - A resolution failure exits 127 with one stderr line and no traceback.
"""
from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path
from typing import NoReturn

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_NOT_FOUND = 127


def _fail(message: str) -> NoReturn:
    print(message, file=sys.stderr)
    raise SystemExit(_NOT_FOUND)


def forward(relpath: str, name: str) -> NoReturn:
    """Run DoE coordinator/pipelines/<relpath> as __main__ with the caller's argv.

    argv[1:] equal to ["--help"] or ["-h"] prints usage naming `name` and `relpath` and exits 0
    without resolving the DoE root. Otherwise exits 127 when the root is unresolvable, the
    target is missing, or relpath escapes the pipelines root.
    """
    args = sys.argv[1:]
    if args in (["--help"], ["-h"]):
        print(
            f"usage: {name} [args...]\n"
            f"Runs DoE coordinator/pipelines/{relpath} with the given arguments.\n"
            f"Arguments are the target's own; run the target for its options."
        )
        raise SystemExit(0)

    try:
        if _THIS_DIR not in sys.path:
            sys.path.insert(0, _THIS_DIR)
        import coordinator_data_root

        root = Path(coordinator_data_root.data_root("pipelines")).resolve()
    except Exception as exc:
        _fail(
            f"{name}: DoE pipelines root unresolved ({type(exc).__name__}: {exc}). "
            f"Register the coordinator-claude content root, then rerun."
        )

    target = (root / relpath).resolve()
    if root != target and root not in target.parents:
        _fail(f"{name}: {relpath} escapes {root}. Pass a relpath inside pipelines.")
    if not target.is_file():
        _fail(f"{name}: {target} not found. Update the DoE clone, then rerun.")

    sys.argv = [str(target), *args]
    sys.path.insert(0, str(target.parent))
    runpy.run_path(str(target), run_name="__main__")
    raise SystemExit(0)
