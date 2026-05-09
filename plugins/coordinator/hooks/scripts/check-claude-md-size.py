#!/usr/bin/env python3
"""PreToolUse hook: gate Write/Edit/MultiEdit on CLAUDE.md by post-edit size.

Claude Code emits a load-time performance warning at 40KB on auto-loaded
CLAUDE.md files. This hook simulates the pending edit, then:
  - >39900 bytes  → exit 2 (BLOCK, stderr fed to Claude)
  - >39000 bytes  → exit 1 (advisory, stderr shown to user)
  - otherwise     → exit 0

Fires only when the target basename is CLAUDE.md (case-sensitive — matches
the auto-load filename Claude Code looks for). All other paths fast-exit 0.
Simulation failures fail open (exit 0) — never block on a parse error in the
gate itself.
"""

import json
import os
import sys

HARD = 39900
SOFT = 39000


def simulate(tool, inp):
    file_path = inp.get("file_path", "")
    if tool == "Write":
        return inp.get("content", "")
    if tool == "Edit":
        with open(file_path, "r", encoding="utf-8") as f:
            cur = f.read()
        old_s = inp.get("old_string", "")
        new_s = inp.get("new_string", "")
        return cur.replace(old_s, new_s) if inp.get("replace_all") else cur.replace(old_s, new_s, 1)
    if tool == "MultiEdit":
        with open(file_path, "r", encoding="utf-8") as f:
            buf = f.read()
        for edit in inp.get("edits", []):
            old_s = edit.get("old_string", "")
            new_s = edit.get("new_string", "")
            buf = buf.replace(old_s, new_s) if edit.get("replace_all") else buf.replace(old_s, new_s, 1)
        return buf
    return None


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool = data.get("tool_name", "")
    if tool not in ("Write", "Edit", "MultiEdit"):
        sys.exit(0)

    inp = data.get("tool_input") or {}
    file_path = inp.get("file_path", "")
    if os.path.basename(file_path) != "CLAUDE.md":
        sys.exit(0)

    try:
        new_content = simulate(tool, inp)
    except Exception:
        sys.exit(0)

    if new_content is None:
        sys.exit(0)

    size = len(new_content.encode("utf-8"))

    if size > HARD:
        sys.stderr.write(
            f"BLOCKED: edit would push {file_path} to {size} bytes "
            f"(hard limit {HARD}, Claude Code 40KB perf threshold at 40000). "
            f"Trim other content in the same edit, or split the change.\n"
        )
        sys.exit(2)

    if size > SOFT:
        sys.stderr.write(
            f"WARNING: {file_path} after edit would be {size} bytes "
            f"(soft warn {SOFT}, hard block {HARD}). Approaching 40KB perf threshold.\n"
        )
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
