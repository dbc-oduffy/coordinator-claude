"""PreToolUse hook (matcher: Write|Edit|MultiEdit): advises when a write
introduces NEW changelog-shaped prose into a coordinator doctrine surface.

Why this exists
----------------
A doctrine surface states the rule as it stands now, present tense, addressed
to the reader who has to obey it next -- it does not carry the rule's own
history (ruling dates, `DR-` supersession chains, "was P now Q", "retired on
<date>", origin-incident narration). That standing rule lives in this repo's
`CLAUDE.md` § Conventions. See `_doctrine_changelog_prose.py`'s module
docstring for the full detection-rule writeup, the two explicitly-handled
ambiguous classes, and the false-positive exemptions this deliberately does
NOT flag.

Advisory, never a deny
-----------------------
This guard cannot always tell a real violation from a legitimate authority
citation with certainty -- the two ambiguous classes in the detector exist
precisely because some shapes are genuinely undecidable from the text alone.
A guard in that position should offer the alternative rather than refuse the
write; the real teeth are `coordinator/tests/test_doctrine_surfaces_are_not_
changelogs.py`, a ratchet whose baseline can only shrink. Routed through
`_message_envelope.compose`/`emit` on `CHANNEL_ADDITIONAL_CONTEXT`, same
channel and one-sentence-diagnosis-plus-remedy shape as its sibling
`guard-prompt-surface-citations.py`.

Scoping
-------
Fires only on `new_violations(before, after)` -- a multiset difference
between the file's violations before and after THIS write -- never on
pre-existing debt sitting untouched in a file being edited for an unrelated
reason. See `_doctrine_changelog_prose.new_violations`'s docstring.

Reconstructing before/after
-----------------------------
Same contract as `guard-prompt-surface-citations.py`: `before` is the current
on-disk content (empty string for a not-yet-existing file); `after` is
reconstructed from `tool_input` -- Write's `content` directly, Edit's single
`old_string`/`new_string` replacement (or all occurrences under
`replace_all`), MultiEdit's sequential application over `tool_input["edits"]`.

Fail-open guards (all exit 0 silent, in order): unreadable/unparseable stdin
payload; tool_name not in the guarded set; no target path in tool_input;
target not `is_in_scope()` (wrong tree/extension, or a `tests/`/`fixtures/`
subdirectory); on-disk read failure for an existing file; unreconstructable
before/after; zero new violations.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

from _sentinel_write_guard import extract_target_path  # noqa: E402
from _doctrine_changelog_prose import is_in_scope, new_violations  # noqa: E402
from _message_envelope import CHANNEL_ADDITIONAL_CONTEXT, Message, compose, emit  # noqa: E402

_GUARDED_TOOLS = ("Write", "Edit", "MultiEdit")

#: Where the rule this guard enforces actually lives -- not a wiki page (this
#: guard was not asked to author one), the repo's own standing convention.
_RULE_ANCHOR = "CLAUDE.md § Conventions (\"Doctrine is not changelog\")"


def _reconstruct_after(tool_name: str, tool_input: dict, before: str) -> "str | None":
    if tool_name == "Write":
        content = tool_input.get("content")
        return content if isinstance(content, str) else None

    if tool_name == "Edit":
        old_s = tool_input.get("old_string")
        new_s = tool_input.get("new_string")
        if not isinstance(old_s, str) or not isinstance(new_s, str):
            return None
        if old_s == "":
            return new_s
        if old_s not in before:
            return None
        return (
            before.replace(old_s, new_s)
            if tool_input.get("replace_all")
            else before.replace(old_s, new_s, 1)
        )

    if tool_name == "MultiEdit":
        edits = tool_input.get("edits")
        if not isinstance(edits, list):
            return None
        text = before
        for edit in edits:
            if not isinstance(edit, dict):
                return None
            old_s = edit.get("old_string")
            new_s = edit.get("new_string")
            if not isinstance(old_s, str) or not isinstance(new_s, str):
                return None
            if old_s == "":
                text = new_s
                continue
            if old_s not in text:
                return None
            text = (
                text.replace(old_s, new_s)
                if edit.get("replace_all")
                else text.replace(old_s, new_s, 1)
            )
        return text

    return None


def _advisory_reason(target: str, violations: list) -> str:
    """The prose diagnosis, kept as a plain-string-returning function
    separable from stdin/envelope plumbing -- same shape as the sibling
    guard's `_deny_reason`.

    High-confidence hits are named directly; an ambiguous-only result gets
    softer language ("worth a second look") since a bare-phrase match can't
    establish a real violation on its own -- see the detector module
    docstring's writeup of the two ambiguous classes."""
    high = [v for v in violations if v.confidence == "high"]
    ambiguous = [v for v in violations if v.confidence == "ambiguous"]

    if high:
        kinds = sorted({v.kind for v in high})
        shown = kinds[:2]
        kinds_text = ", ".join(shown)
        if len(kinds) > len(shown):
            kinds_text += f", +{len(kinds) - len(shown)} more"
        extra = f" (+{len(ambiguous)} ambiguous)" if ambiguous else ""
        return (
            f"{target} adds {len(high)} changelog-shaped passage(s){extra} "
            f"({kinds_text}). State the rule in present tense; put history "
            "in the commit message or a decision record."
        )

    kinds = sorted({v.kind for v in ambiguous})
    kinds_text = ", ".join(kinds[:2])
    return (
        f"{target} adds {len(ambiguous)} passage(s) worth a second look "
        f"({kinds_text}) -- may be live-rule provenance, may be reversal "
        "narration."
    )


def _advisory_message(target: str, violations: list) -> Message:
    return compose(_advisory_reason(target, violations), anchor=_RULE_ANCHOR)


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

    after = _reconstruct_after(payload.get("tool_name", ""), tool_input, before)
    if after is None:
        return 0

    is_json = target.suffix == ".json"
    new = new_violations(before, after, is_json=is_json)
    if not new:
        return 0

    emit(_advisory_message(target_raw, new), CHANNEL_ADDITIONAL_CONTEXT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
