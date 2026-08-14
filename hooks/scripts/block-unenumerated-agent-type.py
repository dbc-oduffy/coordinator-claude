"""PreToolUse(Agent) doctrine-plane-side registration shim for the engine plane's
unenumerated-`subagent_type` hard-deny guard.

DR-047 boundary: this file is the thin transport shim ONLY -- it resolves
the engine plane, imports and calls `coordinator_core.hooks.
block_unenumerated_agent_type.check`, and relays whatever it returns to
stdout. It owns ZERO roster grammar, ZERO deny-reason wording for the
enumerated-vs-not decision itself -- that logic is entirely the engine
plane's (coordinator_core/hooks/block_unenumerated_agent_type.py). This shim adds
exactly one thing the engine module cannot own from its side of the
boundary: the fail-CLOSED behavior on a transport failure (see below), plus
duplicated honoring of the override marker so that fail-closed leg has an
escape hatch.

FAIL-CLOSED, INVERTING THE SIBLING ADVISORY CONTRACT. Every other shim in
this directory (nudge-named-agent-report-delivery.py, nudge-foreground-
agent-dispatch.py's own transport leg, block-dispatch-suite-invocation.py)
fails OPEN on an unresolvable engine root, unimportable engine module, or
handler exception -- a broken advisory or classifier must never brick a
live dispatch. This shim inverts that: a roster-load or transport failure
here means the guard CANNOT PROVE the dispatched `subagent_type` is
enumerated, and the whole point of the guard (closing the unenumerated-type
loophole, see the engine module's own docstring "THE HOLE THIS CLOSES") is
defeated by treating "cannot verify" as "assume fine". So steps 6/7/8 below
(engine-root resolution, import, and the `check()` call itself) all deny on
failure, each reason naming plainly that the denial is because verification
failed, not because the type is known-bad, plus the concrete failure and
the override escape hatch.

STEP 4 ORDERING -- the override marker check runs in THIS file, before any
fail-closed leg, and is a deliberate duplication of the engine module's own
`_has_override_marker` check inside `check()`. Why duplicate rather than
rely on the engine: `check()` only gets a chance to honor the marker once
the engine is successfully imported and running -- on a fail-closed leg
(steps 6/7/8) `check()` is never reached at all, so without this
duplication a broken engine would leave the operator with NO escape hatch
from a guard that cannot itself be reached to read one. This is the whole
reason for the duplication; it must survive any future refactor of this
file.

OVERRIDE -- last resort, clears THIS dispatch only: add a line, on its
own, carrying a non-empty reason, to the SAME dispatch prompt that hit
this guard --

    COORDINATOR-OVERRIDE-UNENUMERATED-AGENT-TYPE: <why this dispatch is safe>

`_has_override_marker` requires the reason to be non-empty and non-
whitespace-only; a bare marker line with nothing after the colon does not
override. This exact syntax is deliberately NOT rendered inline in
`_fail_closed_reason`'s deny text (2026-08-11, PM-raised finding) -- a
ready-to-paste incantation sitting inside deny output reads as an
instruction rather than a fact to a model scanning for actionable text.
This docstring section is now that syntax's one documented home; the deny
text only points here.

STEP 5 -- HARNESS-SHAPE CARVE-OUT (`_HARNESS_SHAPES_NOT_IN_ENGINE_ROSTER`).
Harness-owned Agent dispatch shapes that the engine plane's roster does not
yet enumerate. `fork` is a documented value of the Agent tool's own
`subagent_type` schema and was MEASURED LIVE on this host reaching
PreToolUse(Agent) as the literal string `"fork"` (observed in
`.git/coordinator-sessions/<sid>/dispatched-agents.txt` column 3). Each
entry in this set is PROVISIONAL: it is removed the moment the engine
plane's own `_HARNESS_BUILTIN_TYPES` constant carries it -- the outbound memo
requesting that addition is cross-repo/inbox/-side commit 787871452. This
set is NOT a second roster and must NEVER grow to hold coordinator-authored
or plugin agent types -- those belong in `subagent-sandbox-policy.yaml` or
`coordinator/agents/`, never here.

HONEST LIMITATION -- the shared `runpy` bootstrap in `hooks.json` (the
`python3 -c ...; runpy.run_path(p, ...) if os.path.isfile(p) else
sys.stderr.write('COORDINATOR HOOK SEAM: ... unreachable -- failing OPEN
...')` wrapper every entry in this file's matcher list shares) fails OPEN
when THIS script itself is missing or has drifted off its registered path
-- it writes one `COORDINATOR HOOK SEAM:` line to stderr and runs nothing,
silently disarming this entire guard. That is install drift, outside this
file's control, and must NOT be "fixed" by editing the shared bootstrap
(every other registered hook shares that same wrapper and that same
fail-open contract for a missing script).

Spec backlink: cross-repo/inbox/2026-08-10-claude-klabauter-em-agent-type-deny-guard-needs-registration.md
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Optional


#: Mirrors the engine module's own `_OVERRIDE_MARKER_PREFIX` /
#: `_OVERRIDE_MARKER_RE` bit-for-bit (anchored to line start, leading
#: whitespace allowed, case-sensitive, non-empty non-whitespace-only
#: reason) -- see module docstring "STEP 4 ORDERING" for why this shim
#: duplicates rather than defers to the engine's own check.
_OVERRIDE_MARKER_PREFIX = "COORDINATOR-OVERRIDE-UNENUMERATED-AGENT-TYPE:"
_OVERRIDE_MARKER_RE = re.compile(
    r"^[ \t]*" + re.escape(_OVERRIDE_MARKER_PREFIX) + r"[ \t]*(\S.*)?$",
    re.MULTILINE,
)

#: See module docstring "STEP 5" -- harness-owned dispatch shapes the
#: engine roster does not yet enumerate. Provisional; removed once the
#: engine plane's `_HARNESS_BUILTIN_TYPES` carries the entry. NEVER grows to hold
#: coordinator-authored or plugin agent types.
_HARNESS_SHAPES_NOT_IN_ENGINE_ROSTER = frozenset({"fork"})


_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
try:
    from _engine_root import resolve_claude_klabauter_root as _resolve_claude_klabauter_root  # noqa: E402
except Exception:
    # Defensive fallback -- a hook script copied/deployed WITHOUT its
    # sibling _engine_root.py must still resolve to a callable that
    # returns None (driving the fail-CLOSED leg below), never crash on
    # import.
    def _resolve_claude_klabauter_root() -> Optional[str]:
        return None


def _has_override_marker(prompt_text: str) -> bool:
    for match in _OVERRIDE_MARKER_RE.finditer(prompt_text):
        reason = match.group(1)
        if reason and reason.strip():
            return True
    return False


def _deny_envelope(reason: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def _fail_closed_reason(what_failed: str) -> str:
    """2026-08-11 (PM-raised finding): the prior render handed the reader a
    working, backtick-quoted, ready-to-paste override line -- worse than
    naming a bare setting, since this one is directly pasteable into the
    agent's own next dispatch prompt. The override still exists and still
    works (`_has_override_marker` below is unchanged); this message now
    only states that a documented, last-resort, this-dispatch-only
    override exists and where to read its exact syntax, never the literal
    line itself, and never inside backticks (a backticked span reads as an
    executable alternative to both agents and to the sibling engine
    plane's own `_alternative_liveness` extractor)."""
    return (
        "AGENT DISPATCH BLOCKED: this guard denied because it could NOT "
        "VERIFY the dispatched subagent_type against the enumerated "
        "roster -- this is NOT a claim that the type is known-bad. "
        f"Concrete failure: {what_failed} A documented, last-resort "
        "override exists that clears THIS dispatch only -- see this "
        "guard's own module docstring (coordinator/hooks/scripts/"
        "block-unenumerated-agent-type.py, Override section) for its "
        "exact syntax."
    )


def main() -> int:
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""
    if not raw:
        return 0
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return 0
    except Exception:
        return 0

    if (payload.get("tool_name") or "") != "Agent":
        return 0

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0

    subagent_type = tool_input.get("subagent_type")
    if not isinstance(subagent_type, str) or not subagent_type.strip():
        return 0
    subagent_type = subagent_type.strip()

    prompt = tool_input.get("prompt")
    prompt_text = prompt if isinstance(prompt, str) else ""
    if prompt_text and _has_override_marker(prompt_text):
        return 0

    if subagent_type in _HARNESS_SHAPES_NOT_IN_ENGINE_ROSTER:
        return 0

    try:
        root = _resolve_claude_klabauter_root()
    except Exception as exc:
        sys.stdout.write(json.dumps(
            _deny_envelope(_fail_closed_reason(
                f"engine-root resolution raised {type(exc).__name__}: {exc}"
            )),
            ensure_ascii=False, separators=(",", ":"),
        ))
        sys.stdout.write("\n")
        return 0
    if not root:
        sys.stdout.write(json.dumps(
            _deny_envelope(_fail_closed_reason(
                "engine root (the engine plane's checkout) is unresolvable on this host."
            )),
            ensure_ascii=False, separators=(",", ":"),
        ))
        sys.stdout.write("\n")
        return 0

    if root not in sys.path:
        sys.path.insert(0, root)

    try:
        from coordinator_core.hooks.block_unenumerated_agent_type import check  # noqa: E402
    except Exception as exc:
        sys.stdout.write(json.dumps(
            _deny_envelope(_fail_closed_reason(
                f"coordinator_core.hooks.block_unenumerated_agent_type is "
                f"unimportable: {type(exc).__name__}: {exc}"
            )),
            ensure_ascii=False, separators=(",", ":"),
        ))
        sys.stdout.write("\n")
        return 0

    try:
        envelope = check(payload)
    except Exception as exc:
        sys.stdout.write(json.dumps(
            _deny_envelope(_fail_closed_reason(
                f"check() raised {type(exc).__name__}: {exc}"
            )),
            ensure_ascii=False, separators=(",", ":"),
        ))
        sys.stdout.write("\n")
        return 0

    if envelope:
        sys.stdout.write(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")))
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
