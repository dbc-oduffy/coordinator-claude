#!/usr/bin/env python3
"""SessionStart(startup|clear|compact) naked-Python port of the former
platform-dispatch wrapper (which delegated to a PowerShell script on Windows,
falling through to a bash script on any pwsh failure).

W4b bash-to-naked-python-hook-migration cohort, recipe SS2.8: PORT disposition
(PM default mandate + the Staff Engineer adjudication) - both the retired `.ps1` and bash
oracles implement IDENTICAL logic (bounded upward directory-marker walk, one file-mtime
stat, two `git` subprocess calls); no pwsh-only primitive exists anywhere in
the pair, so there is nothing here that requires the stays-bash fallback.

The doctrine plane owns only this thin PLUMBING shim (same shape as preuse-write-dispatch.py):
resolve the engine repo, hand it the cwd, relay its stdout banner verbatim.
The engine repo owns the detection LOGIC (`coordinator_core.hooks.project_rag_detect`).
The engine is imported and run IN-PROCESS - no bash, no pwsh, no `python3 -m`
subprocess re-spawn - collapsing the old wrapper's "try pwsh, fall through to
bash" two-process race into a single interpreter start.

Contract (mirrors the bash/ps1 wrapper it replaces):
  stdin   - SessionStart JSON payload (not required; this hook only needs cwd,
            and reads it from the process cwd exactly as the bash/ps1 oracles
            did via `pwd`/`Get-Location`, not from the payload)
  stdout  - the freshness banner text (possibly multi-line, incl. a wrapped
            <system-reminder> block), or NOTHING when the oracle would have
            exited silently
  exit 0  - always (SessionStart hooks MUST exit 0 unconditionally regardless
            of internal success/failure - this hook fails open on any
            resolve/import/detection error, identical philosophy to
            preuse-write-dispatch.py's fail-open ALLOW)

NOTE (transition): hooks.json still points at the legacy bash/ps1 wrapper;
this stub is NOT wired into hooks.json here (EM cutover, per W4b task scope).
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path


def _read_stdin(timeout: float = 2.0) -> str:
    box = {"data": ""}

    def _read() -> None:
        try:
            box["data"] = sys.stdin.read()
        except Exception:
            box["data"] = ""

    t = threading.Thread(target=_read, daemon=True)
    t.start()
    t.join(timeout)
    return box["data"]


_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
try:
    from _engine_root import resolve_claude_klabauter_root as _resolve_claude_klabauter_root  # noqa: E402
except Exception:
    def _resolve_claude_klabauter_root() -> str | None:
        return None


def main() -> int:
    _read_stdin()

    root = _resolve_claude_klabauter_root()
    if not root:
        return 0

    from _engine_root import place_engine_root_on_path as _place_engine_root_on_path
    _place_engine_root_on_path(root)

    try:
        from coordinator_core.hooks.project_rag_detect import detect_banner
    except Exception:
        return 0

    try:
        banner = detect_banner(os.getcwd())
    except Exception:
        return 0

    if banner:
        sys.stdout.buffer.write(banner.encode("utf-8"))
        sys.stdout.buffer.write(b"\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
