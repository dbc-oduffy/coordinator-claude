"""coordinator/bin/coordinator-publish.py — namespaced canonical alias for
`coordinator/bin/publish.py` (the percolate publish driver).

Why this file exists: `publish` is/was the only bare generic verb among the
installed forwarder set (see `docs/plans/2026-07-25-posix-bareword-path-provisioning.md`
task D1 — deferred there pending PM ratification, since ratified). `<settings-home>/bin` went
onto PATH 2026-07-26 (commit 96708025), turning a theoretical bareword collision into a live
one. Every other generic verb (`check`/`run`/`build`/`validate`/`setup`/`doctor`) only ever appears as a
compound-prefixed name (`publish-resolve-target`, `publish-time-transform-py`, etc.) — `publish`
was the sole exception. This file installs `coordinator-publish` (+ its generated `.cmd` twin) as
the namespaced canonical name, matching the fleet's existing `coordinator-*` prefix convention
(`coordinator-doc-new`, `coordinator-lesson-add`, `coordinator-queue-append`).

`publish` itself is INTENTIONALLY still installed and untouched — this is an additive rename,
not a cutover. `coordinator/skills/percolate/SKILL.md` (DoE-claude) invokes the bareword
`"${COORDINATOR_SETTINGS_HOME:-...}/bin/publish"` today; deleting `publish` here would break that
skill immediately. Deleting the old name is a separate, gated follow-up once callers have
actually moved to `coordinator-publish` — see the D1 dispatch report for the caller list.

Delegates by `runpy`-executing `publish.py` in this same directory as `__main__`, rather than
importing and re-calling its `main()`, so this alias never drifts from `publish.py`'s own
`sys.argv`/`sys.exit` contract and carries zero duplicated dispatch logic — `publish.py` remains
the SOLE owner of the percolate publish driver's behavior; this file is purely a namespaced
second name for the same on-disk artifact.

Negative-spec: do NOT reimplement or re-import `publish.py`'s `main()` here and call it directly
— that would fork argv/exit-code handling into a second implementation the moment either file's
signature changes. `runpy.run_path(..., run_name="__main__")` re-executes the target module's own
`if __name__ == "__main__":` block verbatim, so this alias is always byte-identical in behavior to
invoking `publish.py` directly.
"""

import runpy
import sys
from pathlib import Path

if __name__ == "__main__":
    _target = Path(__file__).resolve().with_name("publish.py")
    sys.argv[0] = str(_target)
    runpy.run_path(str(_target), run_name="__main__")
