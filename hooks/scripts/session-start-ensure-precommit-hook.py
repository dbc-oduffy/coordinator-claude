#!/usr/bin/env python3
"""SessionStart self-heal: this repo's `.git/hooks/pre-commit` gate chain is
installed on every box that runs a session here.

`.git/hooks` is per-clone and untracked, so a gate chain that only an operator
installs by hand is installed nowhere. It sat that way for weeks: the engine's
installer (`coordinator_core.ops.install_doe_claude_precommit_hook`) existed
and nothing called it, so the gates it installs -- the doctrine-surface
admission leg, the doctrine-weight ratchet's enforcing leg, and the
phantom-staged-deletion leg of the committer P0 -- never ran on any commit.
The admission leg is the one porcelain `git commit` needs: engine commits get
the same check in-process (`ops/ceremony/commit_admission.py`), because they
run no git hook at all.

This calls that installer for the session's own repo. The installer is
idempotent ("already installed and current -- no-op"), refuses any repo other
than the doctrine repo it targets, and appends to rather than clobbering a
foreign hook, so calling it on every boot costs one file read on a healthy box.

Silent unless the installer fails. Fails open everywhere: an unresolvable
engine, an import error or an exception returns 0 without a word, because a
SessionStart hook must never stand between an operator and a session.

Negative-spec:
    Does NOT author the hook body or the gate list -- both belong to the
    installer, so there is one definition of what this repo's pre-commit runs.
    Does NOT touch a repo other than the session's own working directory.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
from pathlib import Path

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)


def _payload_cwd() -> "str | None":
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    cwd = payload.get("cwd")
    return cwd if isinstance(cwd, str) and cwd else None


def main() -> int:
    try:
        from _engine_root import resolve_claude_klabauter_root, place_engine_root_on_path

        engine_root = resolve_claude_klabauter_root()
        if not engine_root:
            return 0
        place_engine_root_on_path(str(engine_root))
        from coordinator_core.ops import install_doe_claude_precommit_hook as installer

        target_cwd = _payload_cwd() or os.getcwd()
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            rc = installer.main([target_cwd])
        if rc != 0:
            sys.stderr.write(captured.getvalue())
    except Exception:  # noqa: BLE001 -- fail open, see module docstring.
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
