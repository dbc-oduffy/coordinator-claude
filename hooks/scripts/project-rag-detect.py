#!/usr/bin/env python3
"""SessionStart(startup|clear|compact) naked-Python port of the former
platform-dispatch wrapper (which delegated to a PowerShell script on Windows,
falling through to a bash script on any pwsh failure).

W4b bash-to-naked-python-hook-migration cohort, recipe SS2.8: PORT disposition
(PM default mandate + the Staff Engineer adjudication) - both the retired `.ps1` and bash
oracles implement IDENTICAL logic (bounded upward directory-marker walk, one file-mtime
stat, two `git` subprocess calls); no pwsh-only primitive exists anywhere in
the pair, so there is nothing here that requires the stays-bash fallback.

DoE owns only this thin PLUMBING shim (same shape as preuse-write-dispatch.py):
resolve the claude-klabauter engine, hand it the cwd, relay its stdout banner verbatim.
Claude-klabauter owns the detection LOGIC (`coordinator_core.hooks.project_rag_detect`).
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
    """Bounded stdin read (Windows hang guard) -- copied from
    runtime-tripwire-stop-watcher.py._read_stdin (~186-201).

    A bare sys.stdin.read() blocks forever if the harness never closes
    stdin's write end (observed Windows failure mode); this backstops with a
    2s threaded-join timeout, returning "" (the same fail-open value a
    drained-but-empty payload would produce) instead of hanging the whole
    hook chain -- SessionStart is a PRE-tool-call gate, so a hang here stalls
    session start, not just one tool call.
    """
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
    # Defensive fallback -- a hook script copied/deployed WITHOUT its
    # sibling _engine_root.py (e.g. an isolated test harness, or a
    # partial deploy) must still fail-open rather than crash on import.
    def _resolve_claude_klabauter_root() -> str | None:
        return None


def main() -> int:
    # This hook needs only cwd (exactly as the bash/ps1 oracles used `pwd` /
    # `Get-Location`, not the SessionStart JSON payload) - but SessionStart
    # hooks are invoked with a JSON payload on stdin regardless of whether the
    # hook consumes it; drain it so the harness never sees a broken pipe.
    _read_stdin()

    root = _resolve_claude_klabauter_root()
    if not root:
        return 0  # fail-open - claude-klabauter unresolvable on this machine

    if root not in sys.path:
        sys.path.insert(0, root)

    try:
        from coordinator_core.hooks.project_rag_detect import detect_banner
    except Exception:
        return 0  # engine unimportable -> fail-open

    try:
        banner = detect_banner(os.getcwd())
    except Exception:
        return 0  # any detection failure -> fail-open, silent

    if banner:
        # Route through the binary buffer, not text-mode sys.stdout.write():
        # text mode translates "\n" to the platform line separator, which on
        # Windows means every embedded newline in a multi-line banner (incl.
        # the wrapped <system-reminder> block) comes out CRLF -- a needless
        # divergence from the bash/ps1 oracles' LF-only output.
        sys.stdout.buffer.write(banner.encode("utf-8"))
        sys.stdout.buffer.write(b"\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
