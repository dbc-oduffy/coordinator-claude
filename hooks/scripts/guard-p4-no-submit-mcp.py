"""PreToolUse hook (matcher: `mcp__.*example-game-repo.*`): on a box that declares the machine-local
key `policy.p4_no_submit`, denies every example-game-repo-control route that puts a changelist on the
Perforce server -- `source_control_submit` / shelve tools, called directly or named through
`execute_domain_tool`, plus a narrow string match over `execute_python_code` source.

Policy scope: the key is the box declaration. Any non-empty value (list of identifiers, string,
`true`) arms the guard; an MCP call carries no depot identifier, so an armed box denies the
submit/shelve tools wholesale. Checkout, file_state and stream_state stay allowed.

Limits, stated plainly: the `execute_python_code` leg sees only the code string, so it is a
tripwire, not a lock -- indirection (built strings, getattr, reading code from a file) escapes
it. Registry unreadable or key absent means no policy to enforce: the guard allows. Any
internal failure past the policy read denies (fail closed on an armed box).
"""

from __future__ import annotations

import json
import os
import re
import sys

_HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

from _message_envelope import CHANNEL_DENY, compose, emit  # noqa: E402

POLICY_KEY = "policy.p4_no_submit"

_WIKI_ANCHOR = (
    "coordinator/docs/wiki/coordinator-tripwires/"
    "p4-submit-and-shelve-are-denied-on-a-no-submit-box.md"
)

_DENY_PROSE = (
    "This box forbids putting a changelist on the Perforce server: no submit, no shelve. "
    "Checkout, sync, build and local edits stay available."
)

_SUBMIT_TOOL_RE = re.compile(
    r"source_control_(?:submit|shelve|check_?in)\w*|(?:submit|shelve)_changelist", re.I
)

_PY_SUBMIT_RE = re.compile(
    r"check_?in|submit|\bshelve|\bp4\b[^\n]{0,80}\b(?:submit|shelve)\b|"
    r"source_?control[^\n]{0,120}(?:submit|shelve|check_?in)",
    re.I,
)


def _policy_armed() -> bool:
    try:
        import tomllib

        from _engine_root import _flatten_registry, _settings_home_registry_dir

        reg_dir = _settings_home_registry_dir()
    except Exception:
        return False
    for name in ("registry.local.toml", "registry.toml"):
        reg = reg_dir / name
        try:
            if not reg.is_file():
                continue
            with reg.open("rb") as fh:
                value = _flatten_registry(tomllib.load(fh)).get(POLICY_KEY)
        except Exception:
            continue
        if value not in (None, "", False, [], 0):
            return True
    return False


def _violates(tool_name: str, tool_input: object) -> bool:
    base = tool_name.rsplit("__", 1)[-1]
    if _SUBMIT_TOOL_RE.fullmatch(base):
        return True
    if base == "execute_domain_tool":
        try:
            blob = json.dumps(tool_input, default=str)
        except Exception:
            return True
        return bool(_SUBMIT_TOOL_RE.search(blob))
    if base == "execute_python_code":
        code = tool_input.get("code") if isinstance(tool_input, dict) else None
        if not isinstance(code, str):
            code = json.dumps(tool_input, default=str)
        return bool(_PY_SUBMIT_RE.search(code))
    return False


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "")
        if not isinstance(payload, dict):
            return 0
    except Exception:
        return 0

    tool_name = payload.get("tool_name", "")
    if not isinstance(tool_name, str) or not tool_name.startswith("mcp__"):
        return 0

    if not _policy_armed():
        return 0

    try:
        denied = _violates(tool_name, payload.get("tool_input"))
    except Exception:
        denied = True
    if denied:
        emit(compose(_DENY_PROSE, anchor=_WIKI_ANCHOR), CHANNEL_DENY)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
