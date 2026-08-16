"""Single source of truth for the small set of literal string/format
contracts shared between `coordinator/bin/percolate-round.py` (writer) and
`coordinator/bin/publish.py` (reader) — no other dependency, so importing
this module carries no risk of a cycle or a heavy transitive import into
either bin script.

Review: code-reviewer nit — `_INHERITED_LOCK_ROOTS_ENV` was previously
defined byte-for-byte in both modules with only a comment keeping them in
sync; a future edit to one literal without the other would silently drop
back to always-locking (the safe direction) with no test catching the
drift, since each module's tests only referenced its own local copy.
"""
from __future__ import annotations

#: D1 fix — inherited-holder handoff env var. `percolate-round.py` writes
#: `"<its own pid>=<realpath>"` (pathsep-joined for multiple roots);
#: `publish.py::main` reads it, verifying the PID against `os.getppid()`
#: before honouring the skip. See each module's own call site for the
#: full mechanism/rationale.
INHERITED_LOCK_ROOTS_ENV = "PERCOLATE_ROUND_INHERITED_LOCK_ROOTS"
