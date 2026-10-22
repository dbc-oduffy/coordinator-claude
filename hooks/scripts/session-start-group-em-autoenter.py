"""SessionStart: a session the PM starts in the group-em home enters Group EM standing.

Starting a session in the machine-local group-em home (`_gem_home.is_home`) is the PM's act, so
it carries the same authority as a typed `/group-em`. This leg runs the same entry op the
`/group-em` autofire does (`group-em-autofire.py`, reused by path, never copied) with
`--home-start` in place of `--prompt-id`: the engine verifies the proof itself, from the
session's own transcript (its project directory and first-line cwd lie in the home), so nothing
this hook passes can forge it.

Fires on:
  - `startup` in the home: enter.
  - `resume` / `clear` / `compact` in the home: re-enter only when this session already holds
    the standing (refreshes roster and digest). Never claims on these: a resumed or cleared
    session the PM did not just start must not take the role from a live holder.
  - anything else (`fork`, outside the home, a refused home): silent.

Own top-level registration, never a leg of `sessionstart-dispatch.py`: the entry context needs
its own stdout stream and preview window, as `assert-em-role.py` does. Rendered inside
`_PREVIEW_BUDGET_CHARS`; truncation drops roster rows, never the arm/gate/workflow tail.

Inherits the autofire's negative spec: never `--supersede`, never `--local`, never sends, never
blocks. Fails open (silent exit 0) on any error.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_HOOKS_DIR = Path(__file__).resolve().parent
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

_PREVIEW_BUDGET_CHARS = 1_900
_REENTRY_SOURCES = frozenset({"resume", "clear", "compact"})
_TYPE_IT_HINT = "Type `/group-em` to enter by hand."


def _autofire():
    spec = importlib.util.spec_from_file_location(
        "_gem_autoenter_autofire", _HOOKS_DIR / "group-em-autofire.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def should_enter(source: str, session_id: str, holder: dict | None) -> bool:
    if source == "startup":
        return True
    if source in _REENTRY_SOURCES:
        return bool(holder) and holder.get("session_id") == session_id
    return False


def compute_context(stdin_text: str) -> str | None:
    try:
        payload = json.loads(stdin_text) if stdin_text else {}
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(payload, dict):
        return None
    source, session_id, cwd = (payload.get(k) for k in ("source", "session_id", "cwd"))
    if not (isinstance(source, str) and isinstance(session_id, str) and session_id):
        return None
    if not (isinstance(cwd, str) and cwd):
        return None

    import _gem_home

    if not _gem_home.is_home(cwd):
        return None
    holder = _gem_home.gem_holder() if source in _REENTRY_SOURCES else None
    if not should_enter(source, session_id, holder):
        return None

    af = _autofire()
    script = af.resolve_enter_cli()
    if script is None:
        return None
    result = af._run_enter(script, cwd, session_id, home_start=True)
    if result is None:
        return None
    try:
        entered = json.loads(result.stdout) if result.stdout.strip() else {}
        if not isinstance(entered, dict):
            entered = {}
    except Exception:  # noqa: BLE001
        entered = {}
    if not entered and result.returncode not in af._NOT_ENTERED_HEADS:
        return None

    boxes: list[str] = []
    if result.returncode == 0 and (entered.get("standing") or {}).get("claimed"):
        boxes = af._box_blocks(cwd, session_id, entered)
    context = af.render_additional_context(
        entered, result.returncode, result.stderr or "", boxes, budget=_PREVIEW_BUDGET_CHARS
    )
    if result.returncode in af._NOT_ENTERED_HEADS:
        context = f"{context}\n\n{_TYPE_IT_HINT}"
    return context or None


def main() -> int:
    try:
        context = compute_context(sys.stdin.read())
    except Exception:  # noqa: BLE001
        return 0
    if not context:
        return 0
    try:
        print(
            json.dumps(
                {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}
            )
        )
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
