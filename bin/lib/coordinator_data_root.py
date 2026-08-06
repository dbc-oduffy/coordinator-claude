"""coordinator_data_root — shared resolver for coordinator DATA directories
(snippets/, schemas/, templates/, docs/) across the split-repo layout.

The 2026-07-22 executable-surface migration moved ~1100 executables from
DoE-claude/coordinator/{bin,lib,scripts,tests} into claude-klabauter/coordinator/,
but their sibling DATA dirs — schemas/, snippets/, templates/, docs/, hooks/ —
correctly stayed in DoE-claude (DR-047: contract/data lives with DoE, engine
with claude-klabauter). Any migrated script that resolved a sibling data dir via a bare
`__file__`-relative walk (the old `bin/../<data-dir>` shape) is now broken: that
walk lands inside claude-klabauter, where the data dir no longer exists.

`coordinator_registry.py`'s `_MANIFEST_PATH` bootstrap (see that module, fix
commit 4f74656c) was the first caller to hit this and fixed itself inline with
a two-rung chain. This module extracts that SAME two-rung shape into one
shared, importable resolver so the five (now six, counting the fixed original)
remaining callers do not each hand-roll their own copy — six independent
copies of the resolution chain is exactly the drift that caused this bug.

Two live layouts:
  1. Co-located    — the data dir sits beside bin/ under the same coordinator
                     root (the pre-migration DoE layout, and any OSS install
                     that ships both halves together). Free, no registration.
  2. Split-repo    — this code lives in claude-klabauter while the data dir
                     stayed in DoE-claude. Resolve the DoE root the same way
                     every other doctrine CLI does (coordinator_registry.doe_root()).

Rung 1 first so the co-located case costs nothing and needs no registration.

Negative-spec: this module does NOT reimplement the DOE_ROOT resolution chain
(env DOE_ROOT -> machine-local repos.doe_claude -> raise). That chain lives in
exactly one place, `coordinator_registry.doe_root()`, and this module calls it
rather than duplicating it. A caller that hand-rolls its own DOE_ROOT lookup
instead of importing `data_root()` from here re-introduces the six-copies-of-
one-chain drift this module exists to close.

Import-time purity (negative-spec, load-bearing): `coordinator_registry` is
imported LAZILY, inside `data_root()`, NOT at module top level.
`coordinator_registry` eagerly resolves its own manifest at import time (a
`machine-local` subprocess needing `HOME` in the environment) — so a
top-level `from coordinator_registry import ...` here would make merely
IMPORTING this module able to fail or spawn a subprocess, even for callers
who never call `data_root()` because rung 1 (co-located) already resolves
their case, or who run under a stripped/minimal environment (e.g. a test
harness that replaces rather than merges `os.environ`). This module's own
rung-1 resolution (`_colocated_root()`) is zero-subprocess, zero-env-
dependent by construction, and must stay that way. A future editor hoisting
the `coordinator_registry` import back to module level reintroduces exactly
this bug — do not do it, no matter how natural "just import it up top like
everything else" feels. See regression test
`coordinator/tests/test_coordinator_data_root.py` (stripped-env import
assertion).

Public API:
    data_root(dir_name: str) -> Path
        Resolve one of "snippets", "schemas", "templates", "docs" (or any other
        coordinator data-dir name) to its absolute, existing directory Path.
        Raises RuntimeError, naming the dir and both rungs tried, if neither
        rung resolves to an existing directory. Never returns a path that
        doesn't exist; never silently falls back to a wrong location.

Spec backlink: cross-repo/archive/2026-07-22-claude-central-em-executable-surface-migrated-and-76-op-ask.md
               (the originating memo; in cross-repo/inbox/ until the boot sweep moves it)
DR backlink:   docs/decisions/DR-047-doe-claude-klabauter-boundary-redraw-contract-vs-e.md (DoE-side)
Reference fix: coordinator/bin/lib/coordinator_registry.py `_MANIFEST_PATH` bootstrap
               (commit 4f74656c, "coordinator_registry: resolve the schemas manifest
               across the repo split")
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Defensive self-locate — mirrors the sys.path.insert convention every bin/
# entrypoint already uses (see coordinator/bin/snippet-registry's own
# `_LIB_DIR` insertion) so this module resolves its `coordinator_registry`
# sibling import regardless of whether the caller already inserted bin/lib.
#
# NOTE: this insertion is safe to do at import time (pure sys.path mutation,
# no subprocess, no env read) — it is the actual `coordinator_registry`
# import, below in `data_root()`, that is NOT safe at import time. See the
# module docstring's "Import-time purity" negative-spec.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)


def _colocated_root() -> Path:
    """The coordinator root this module's own bin/lib sits under (rung-1 base).

    coordinator/bin/lib/coordinator_data_root.py -> parents[2] == coordinator/
    (file -> lib/ -> bin/ -> coordinator/), the same triple `os.path.dirname`
    walk `coordinator_registry.py`'s `_MANIFEST_PATH` bootstrap uses.
    """
    return Path(__file__).resolve().parents[2]


def data_root(dir_name: str) -> Path:
    """Resolve `dir_name` (e.g. "snippets", "schemas", "templates", "docs") to
    its absolute, existing directory Path.

    Resolution chain (two-rung, co-located -> DoE-resident):
      1. Co-located — `<coordinator-root>/<dir_name>` beside this module's own
         bin/lib, where `<coordinator-root>` is computed identically to
         `coordinator_registry.py`'s manifest-path bootstrap. Free, no
         registration, wins whenever both halves ship together.
      2. DoE-resident — `<doe_root()>/coordinator/<dir_name>`, delegating the
         DOE_ROOT/machine-local resolution to `coordinator_registry.doe_root()`
         (never reimplemented here — see module negative-spec).

    Raises RuntimeError, naming `dir_name` and both candidate paths tried
    (or the DoE-resolution failure reason), if neither rung resolves to an
    existing directory. Never returns a path that doesn't exist.
    """
    colocated = _colocated_root() / dir_name
    if colocated.is_dir():
        return colocated

    # Lazy import — see module docstring's "Import-time purity" negative-spec.
    # Paid only on this rung-2 path, which already needs the subprocess/env
    # dependent `coordinator_registry.doe_root()` resolution anyway.
    from coordinator_registry import _DoeUnresolvable, doe_root

    try:
        doe = doe_root()
    except _DoeUnresolvable as exc:
        raise RuntimeError(
            f"coordinator_data_root: cannot resolve data dir {dir_name!r}. "
            f"Rung 1 (co-located) tried: {colocated} (not found). "
            f"Rung 2 (DoE-resident) failed: {exc}"
        ) from exc

    candidate = Path(doe) / "coordinator" / dir_name
    if candidate.is_dir():
        return candidate

    raise RuntimeError(
        f"coordinator_data_root: cannot resolve data dir {dir_name!r}. "
        f"Rung 1 (co-located) tried: {colocated} (not found). "
        f"Rung 2 (DoE-resident) tried: {candidate} (not found)."
    )
