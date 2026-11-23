"""session-start-pm-rulings-context.py -- load the repo's accepted PM rulings at session start (SessionStart leg).

A StartGuard in `sessionstart-dispatch.py`. Lists the session repo's accepted PM rulings through
`coordinator/bin/check-pm-ruling-gate.py --rulings` and emits them as `additionalContext`, so a
session sees what the PM already settled before it writes a deferral to the PM. Rulings whose
`topics:` match the `category:` of the newest `state/handoffs/*.md` print first.
Output is capped by bytes (MAX_BYTES), with a remainder line. Silent when the repo has no accepted rulings. Fail-open; exit 0.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

CHECK = Path(__file__).resolve().parents[2] / "bin" / "check-pm-ruling-gate.py"
#: Text bytes; the unwrapped leg output (text + newline) must stay under the per-leg ceiling in
#: tests/baselines/sessionstart-injection-budget.json (default 1300).
MAX_BYTES = 1200
_LIST_CMD = "python coordinator/bin/check-pm-ruling-gate.py --rulings"
_REMAINDER_RESERVE = len(f"... and 999 more ({_LIST_CMD})") + 1
_TIMEOUT_S = 20
_CATEGORY = re.compile(r"^category:\s*(.+?)\s*$", re.M)


def _payload(raw: str) -> dict:
    try:
        obj = json.loads(raw) if raw else {}
    except ValueError:
        return {}
    return obj if isinstance(obj, dict) else {}


def _repo_root(cwd: str) -> Optional[Path]:
    start = Path(cwd or os.getcwd())
    for d in (start, *start.parents):
        if (d / ".git").exists() or (d / "coordinator.local.md").is_file():
            return d
    return None


def _run_check(repo: Path, *extra: str) -> List[str]:
    proc = subprocess.run(
        [sys.executable, str(CHECK), "--repo", str(repo), "--rulings", *extra],
        capture_output=True, text=True, encoding="utf-8", timeout=_TIMEOUT_S,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if proc.returncode != 0:
        return []
    return [ln for ln in proc.stdout.splitlines() if ln.strip()]


def _handoff_category(repo: Path) -> str:
    handoffs = repo / "state" / "handoffs"
    if not handoffs.is_dir():
        return ""
    files = sorted(handoffs.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return ""
    head = files[0].read_text(encoding="utf-8", errors="replace").split("\n---", 2)[0][:4000]
    m = _CATEGORY.search(head)
    return m.group(1).strip("'\" ").lower() if m else ""


def build(raw_stdin: str) -> str:
    """The context text for the session's repo; "" when there is no repo or no accepted ruling."""
    repo = _repo_root(_payload(raw_stdin).get("cwd") or "")
    if repo is None:
        return ""
    lines = _run_check(repo)
    if not lines:
        return ""
    category = _handoff_category(repo)
    if category:
        first = set(_run_check(repo, "--topic", category))
        lines = [ln for ln in lines if ln in first] + [ln for ln in lines if ln not in first]
    lines = [ln.rsplit(" | ", 1)[0] for ln in lines]
    header = (f"Accepted PM rulings ({repo.name}): a deferral to the PM on these topics "
              "is refused by check-pm-ruling-gate.py")
    out, used, shown = [header], len(header.encode("utf-8")) + 1, 0
    for ln in lines:
        cost = len(ln.encode("utf-8")) + 1
        if used + cost + _REMAINDER_RESERVE > MAX_BYTES:
            break
        out.append(ln)
        used += cost
        shown += 1
    if shown < len(lines):
        out.append(f"... and {len(lines) - shown} more ({_LIST_CMD})")
    return "\n".join(out)


def main(argv=None) -> int:
    try:
        text = build(sys.stdin.read())
        if text:
            sys.stdout.write(json.dumps(
                {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))
            sys.stdout.write("\n")
    except Exception:  # noqa: BLE001 -- fail open: a session start is never blocked by this leg
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
