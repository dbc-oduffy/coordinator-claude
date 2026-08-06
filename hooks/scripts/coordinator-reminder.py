#!/usr/bin/env python3
"""SessionStart(startup|clear|compact) naked-Python port of coordinator-reminder.sh.

DoE owns only this thin PLUMBING stub (same DR-047 transport-seam carve-out as
`preuse-write-dispatch.py`): resolve the claude-klabauter engine, call its reminder-render
function IN-PROCESS, relay stdout. Claude-klabauter owns the content-rendering LOGIC
(`coordinator_core.hooks.coordinator_reminder.render_reminder`). No bash, no
`python3 -m` subprocess re-spawn.

Ported per the W4a SessionStart-cohort recipe (§2.4).
This is a "naked-Python direct port, with deletion" disposition -- the bash
source's PROJECT_TYPE/PROJECT_SUBTYPES coordinator.local.md frontmatter parse
(lines 12-48) is dropped entirely: verified dead (neither variable is referenced
anywhere after line 48 in the bash source). The ported behavior is exactly:
static "Quick Orient" heredoc + capability-catalog.md read with HTML-comment
lines stripped (silent skip if the catalog is absent). Confirmed byte-identical
across varying coordinator.local.md frontmatter contents (the dropped block
never affected output).

Contract (mirrors the bash hook it replaces):
  stdin   -- none read (the bash source never drains stdin either)
  stdout  -- the reminder text (heredoc [+ stripped capability catalog])
  exit 0  -- always (SessionStart hooks must exit 0 unconditionally; this hook
            is registered `async: true` in hooks.json today, so a failure here
            was already non-fatal to the session -- the Python port preserves
            that same fail-open posture)

Graceful degradation -- REQUIRED: any failure to resolve/import/run the claude-klabauter
engine falls through to fail-open silent exit 0 (no stdout). A missing sibling
engine must never brick session start -- identical philosophy to
`preuse-write-dispatch.py`.

NOT WIRED: the PM's 2026-07-15 full-kill-keep-fast-orientation directive
removed the boot-time reminder/detector SessionStart hooks entirely (see
hooks.json's top-level `_comment`) — this script is not registered anywhere.
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
    # Defensive fallback -- a hook script copied/deployed WITHOUT its
    # sibling _engine_root.py (e.g. an isolated test harness, or a
    # partial deploy) must still fail-open rather than crash on import.
    def _resolve_claude_klabauter_root() -> str | None:
        return None


def main() -> int:
    root = _resolve_claude_klabauter_root()
    if not root:
        return 0  # fail-open silent exit -- claude-klabauter unresolvable on this machine

    if root not in sys.path:
        sys.path.insert(0, root)

    try:
        from coordinator_core.hooks.coordinator_reminder import render_reminder
    except Exception:
        return 0  # engine unimportable -> fail-open silent exit

    # Capability catalog lives at the DoE plugin root -- mirrors the bash
    # PLUGIN_ROOT ($SCRIPT_DIR/../..) resolution and preuse-write-dispatch.py's
    # policy_path convention. __file__ parents: [0]=scripts [1]=hooks
    # [2]=coordinator (plugin root).
    catalog_path = Path(__file__).resolve().parents[2] / "capability-catalog.md"

    try:
        text = render_reminder(catalog_path)
    except Exception:
        return 0  # any engine failure -> fail-open silent exit

    # Write raw bytes, not sys.stdout.write() -- on Windows, text-mode stdout
    # translates LF to CRLF, which would diverge byte-for-byte from the bash
    # oracle's LF-only heredoc/grep output (golden-diff parity requirement).
    sys.stdout.buffer.write(text.encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
