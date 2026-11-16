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

Registered in hooks.json as its own SessionStart entry. When it has nothing
else to say and project-rag is absent (no CLI on PATH, no `repos.project_rag`
registry entry) it prints one line: "project-rag not connected".
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path


def _read_stdin(timeout: float = 2.0) -> str:
    """Bounded read: a bare sys.stdin.read() can block forever if the harness
    never closes stdin's write end; this backstops with a timeout instead of
    hanging session start."""
    box = [""]

    def _read() -> None:
        try:
            box[0] = sys.stdin.read()
        except Exception:
            box[0] = ""

    t = threading.Thread(target=_read, daemon=True)
    t.start()
    t.join(timeout)
    return box[0]


_ENC = "utf-8"
# The stale-index fallback; the tier-1 nudge is withheld when the freshness line routes here.
_FALLBACK = "use Grep/Read"


_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
try:
    from _engine_root import resolve_claude_klabauter_root as _resolve_claude_klabauter_root  # noqa: E402
except Exception:
    # Fallback for a hook script deployed without its sibling _engine_root.py:
    # must fail-open rather than crash on import.
    def _resolve_claude_klabauter_root() -> str | None:
        return None


_CACHE_REL = Path(".coordinator-local") / "index-freshness-verdict.json"
_CACHE_VERSION = 1


def _age(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 3600:
        return f"{max(1, seconds // 60)}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


def staleness_line(cwd: str, now: float | None = None) -> str | None:
    """One line from the verdict cache `session-start-index-freshness.py` writes (verdict, reason,
    commits behind, cache age). Reads the file only and never invokes the CLI; None
    when no repo root or cache is found or the cache is unreadable."""
    import json
    import time
    try:
        for candidate in (Path(cwd), *Path(cwd).parents):
            if (candidate / ".git").exists():
                break
        else:
            return None
        data = json.loads((candidate / _CACHE_REL).read_text(encoding=_ENC))
        if not isinstance(data, dict) or data.get("cache_version") != _CACHE_VERSION:
            return None
        verdict = data.get("verdict")
        epoch = data.get("checked_epoch")
        if not isinstance(verdict, str) or not isinstance(epoch, (int, float)):
            return None
        row = data.get("row") if isinstance(data.get("row"), dict) else {}
        parts = [f"Index freshness (project-rag): {verdict}"]
        if data.get("reason"):
            parts[0] += f" ({data['reason']}"
            behind = row.get("index_behind_head")
            parts[0] += f", {behind} commits behind HEAD)" if isinstance(behind, int) else ")"
        parts.append(f"checked {_age((time.time() if now is None else now) - epoch)} ago")
        if verdict != "current":
            parts.append(_FALLBACK)
        return "; ".join(parts) + "."
    except Exception:
        return None


def project_rag_present() -> bool:
    """True when the project-rag CLI is on PATH or `repos.project_rag` resolves in the
    machine-local registry. Files and PATH only, no spawn; any failure reads as present so
    the absent line never fires on a probe error."""
    try:
        import shutil
        if shutil.which("project-rag"):
            return True
        from _engine_root import _registry_value, _settings_home_registry_dir
        return bool(_registry_value(_settings_home_registry_dir(), "repos.project_rag"))
    except Exception:
        return True


def main() -> int:
    # Only cwd is needed, but SessionStart always sends a JSON payload on
    # stdin; drain it so the harness never sees a broken pipe.
    _read_stdin()

    banner = None
    root = _resolve_claude_klabauter_root()
    if root:
        from _engine_root import place_engine_root_on_path as _place_engine_root_on_path
        _place_engine_root_on_path(root)

        # The published engine mirror renames this module; the engine's authoring
        # tree (live-tree override) keeps the original name. Published name first.
        detect_banner = None
        try:
            from coordinator_core.hooks.example_retrieval_repo_detect import detect_banner
        except Exception:
            try:
                from coordinator_core.hooks.project_rag_detect import detect_banner
            except Exception:
                pass  # engine unimportable -> fail-open, no engine banner
        if detect_banner is not None:
            try:
                banner = detect_banner(os.getcwd())
            except Exception:
                banner = None  # any detection failure -> fail-open, silent

    # Binary buffer, not text-mode stdout.write(): text mode translates
    # "\n" to the platform separator, which would force CRLF on Windows.
    if banner:
        sys.stdout.buffer.write(banner.encode(_ENC))
        sys.stdout.buffer.write(b"\n")
    line = staleness_line(os.getcwd())
    if line:
        sys.stdout.buffer.write(line.encode(_ENC))
        sys.stdout.buffer.write(b"\n")
    if not banner and not line and not project_rag_present():
        sys.stdout.buffer.write(b"project-rag not connected\n")
    try:
        import _project_rag_nudge
        if _project_rag_nudge.rag_present(os.getcwd()) and not (line and _FALLBACK in line):
            sys.stdout.buffer.write(_project_rag_nudge.nudge_text().encode(_ENC))
            sys.stdout.buffer.write(b"\n")
    except Exception:
        pass  # fail open: the nudge is advisory
    return 0


if __name__ == "__main__":
    sys.exit(main())
