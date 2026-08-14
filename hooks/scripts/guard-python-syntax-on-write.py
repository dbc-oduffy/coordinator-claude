# guard-not-a-hook-entrypoint -- invoked via the in-process guard runner's
# REAL_GUARD_REGISTRY (coordinator/hooks/scripts/_guard_runner.py), which
# preuse-write-dispatch.py's own hooks.json PreToolUse(Write|Edit|MultiEdit)
# registration calls in-process. This basename is deliberately never
# referenced literally in hooks.json text -- that IS the mechanism, not an
# omission.
"""PreToolUse hook (matcher: Write|Edit|MultiEdit): denies a write that
would leave unparseable Python on disk under `coordinator/`.

Why this exists
----------------
This tree's hooks are interpreted source with no build step, resolved live
via `--plugin-dir`. A `SyntaxError` written into a hook script therefore
does not fail a test run later -- it lands in every concurrent session at
once, on the next hook firing, as a bootstrap traceback with hooks failing
open. The observed instance was a missing `+` between a string literal and
a call in a `return (...)` expression: valid-looking prose, invalid syntax,
and every Stop hook in the fleet broken by it.

The hazard was already known and already discharged the wrong way --
`docs/plans/2026-08-07-powershell-guard-chain-rearm.md` instructs an
executor to `python -m py_compile` the hook before reporting done. A rule
whose only enforcement is that the brief remembered to say it fails the
discharge test (`docs/wiki/invisible-doctrine.md`). This guard is that
instruction's mechanism.

Parseability ONLY -- a deliberately narrow bar
------------------------------------------------
`compile()` in "exec" mode, nothing more. Not lint, not import resolution,
and emphatically not executing or importing the module: a guard with side
effects at the write seam is a worse failure than the one it prevents. A
file that parses but is semantically wrong is out of scope by design and
belongs to the test surface, not here.

Deny, not advise -- and unlike its sibling locality guard, no before/after
diff. Unparseable is unparseable regardless of what was there before; there
is no legacy-violation corpus to be safe against, so the deny is absolute
on the reconstructed after-text.

Fail-open guards (all exit 0 silent, in order): unreadable/unparseable
stdin payload; tool_name not in the guarded set; no target path in
tool_input; target not a `.py` file under `coordinator/`; on-disk read
failure for an existing file; ambiguous before/after reconstruction
(`reconstruct_after` returned None); after-text that compiles. A guard that
cannot compute its own input has no basis to deny.

Deny message
-------------
The reason carries the `SyntaxError`'s line number, message, and the
offending line's text -- deliberately NOT routed through a wiki anchor the
way `guard-oss-payload-locality.py`'s per-kind remedies are. The reader is
mid-repair on a file they are looking at; the line number IS the remedy,
and an anchor would spend the character budget sending them somewhere with
less information than the message already has.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

from _sentinel_write_guard import extract_target_path, reconstruct_after  # noqa: E402
from _message_envelope import CHANNEL_DENY, Message, compose, emit  # noqa: E402

_GUARDED_TOOLS = ("Write", "Edit", "MultiEdit")

#: Only this tree's own plugin source. A `.py` write elsewhere in the repo
#: (or in a sibling checkout) is not a live hook and carries none of the
#: fleet-wide blast radius this guard exists for.
_SCOPE_DIR = "coordinator"


def is_in_scope(target: Path) -> bool:
    """A `.py` file under the repo's `coordinator/` plugin tree."""
    if target.suffix != ".py":
        return False
    return _SCOPE_DIR in target.parts


def _excerpt(text: str, lineno: "int | None") -> str:
    if not isinstance(lineno, int) or lineno < 1:
        return ""
    lines = text.split("\n")
    if lineno > len(lines):
        return ""
    return " ".join(lines[lineno - 1].split())[:120]


def _deny_reason(target: str, exc: SyntaxError, after: str) -> str:
    """The prose diagnosis (the only part `_message_envelope.CEILING`
    counts), kept importable and plain-string-returning for the character-cap
    measurement harness, same contract as
    `guard-oss-payload-locality.py::_deny_reason`."""
    where = f"line {exc.lineno}" if exc.lineno else "an unknown line"
    excerpt = _excerpt(after, exc.lineno)
    tail = f": {excerpt}" if excerpt else ""
    return (
        f"python syntax: this write leaves {target} unparseable at {where} "
        f"-- {exc.msg}{tail}. A live hook with a SyntaxError breaks every "
        "concurrent session at once, so it cannot land."
    )


def _deny_message(target: str, exc: SyntaxError, after: str) -> Message:
    return compose(_deny_reason(target, exc, after))


def main() -> int:
    try:
        raw = sys.stdin.read()
    except Exception:
        return 0
    if not raw:
        return 0

    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return 0
    except Exception:
        return 0

    if payload.get("tool_name", "") not in _GUARDED_TOOLS:
        return 0

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0

    target_raw = extract_target_path(tool_input)
    if not target_raw:
        return 0

    try:
        target = Path(target_raw).resolve()
    except Exception:
        return 0

    if not is_in_scope(target):
        return 0

    try:
        before = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else ""
    except Exception:
        return 0

    after = reconstruct_after(payload.get("tool_name", ""), tool_input, before)
    if after is None:
        return 0

    try:
        compile(after, str(target), "exec")
    except SyntaxError as exc:
        emit(_deny_message(target_raw, exc, after), CHANNEL_DENY)
        return 0
    except Exception:
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
