"""SessionStart hook — thin doctrine-plane shim for the engine op
`hooks.repin_cloud_engine_root` (`coordinator_core/hooks/repin_cloud_engine_root.py`).

MUST RUN FIRST, SYNCHRONOUSLY, BEFORE ANYTHING ELSE RESOLVES THE ENGINE ROOT.
Its own module docstring: it atomically re-points the cloud engine-root
symlink `scripts/cloud_setup.py` pins (frozen at install) onto a fresher,
stamped, per-session-mounted engine checkout, when one exists. Every
engine-root reader in this chain — this repo's own `_engine_root` ladder
included — follows that symlink, so a leg that resolves the engine root
ahead of this one can resolve the stale target for the whole session.
Registered as hooks.json's FIRST SessionStart entry, sync (`async: false`),
ahead of every other leg in the chain.

NOT A CHICKEN-AND-EGG PROBLEM, though it looks like one at first glance:
this shim resolves the engine root the same way `session-start-write-bump-
anchor.py` does (`_engine_root.resolve_claude_klabauter_root()`) in order to import
the op module and call it — i.e. it reaches `coordinator_core` through
whatever the registry/symlink currently answers, which on a fresh cloud
boot is `cloud_setup.py`'s own frozen install-time clone (the symlink
target BEFORE this hook ever runs). The op's own body does no version-
sensitive work — it only performs filesystem operations against its own
(injectable, test-covered) path constants — so it is correct regardless of
which checkout happened to serve the module that defines it. There is no
wait on the checkout this hook is about to pin; only a single
already-resolvable import ahead of it.

Off-cloud (`CLAUDE_CODE_REMOTE` unset or not `"true"`), or where the engine
root does not resolve at all, this hook is a silent no-op — the op itself
is documented inert there, and an unresolvable root degrades exactly like
every other doctrine-plane shim in this directory (fail open, no import,
no call).

Contract:
  stdin   — SessionStart JSON payload (unused; the op reads `os.environ`
            directly, per its own signature)
  stdout  — NOTHING on every path (no context to inject)
  exit 0  — ALWAYS. Fail open at every step, matching the op's own
            documented fail-open contract and every sibling hook here.

Ported from the engine repo's own history — spec and commit details in that
repo's own git blame.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
try:
    from _engine_root import resolve_claude_klabauter_root as _resolve_claude_klabauter_root  # noqa: E402
except Exception:
    def _resolve_claude_klabauter_root() -> str | None:
        return None


def main() -> int:
    root = _resolve_claude_klabauter_root()
    if not root:
        return 0

    from _engine_root import place_engine_root_on_path as _place_engine_root_on_path
    _place_engine_root_on_path(root)

    try:
        from coordinator_core.hooks.repin_cloud_engine_root import (
            repin_cloud_engine_root,
        )
    except Exception:
        return 0

    try:
        repin_cloud_engine_root()
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
