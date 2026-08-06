"""PreToolUse hook (matcher: Write|Edit|MultiEdit): denies a write that
introduces a NEW OSS-payload locality defect into a file that ships to the
OSS `coordinator-claude` mirror.

Why this exists
----------------
Files under this tree's OSS payload (see `_oss_payload.py`) percolate
outward to a publish-only mirror an OSS reader installs with none of this
fleet's private sibling-repo checkouts on disk. A private sibling-repo name
(today: `claude-klabauter`) appearing as ATTRIBUTION PROSE in that payload — a
mention, not a load-bearing wire value — costs that reader something: the
name means nothing to them and the reference is dead on arrival. A
drive-rooted Windows path hardcodes a machine-specific value into shipped
prose or code where a portable form was available. See
`_prompt_surface_locality.py`'s module docstring for the full defect-class
writeup, the three carve-outs (ratified operative literals, registered
snippet fences, the `.py` docstring/comment position lens), and why this
scan is not a blanket "any sibling-repo mention" flag.

Deny, not advise — scoped to the write's own new violations
--------------------------------------------------------------
This is a hard-deny, but only on `new_violations(before, after, path=...)` —
see that function's docstring in `_prompt_surface_locality.py`, and the
identical reasoning in the sibling citation guard
(`guard-prompt-surface-citations.py`) this hook mirrors. A legacy violation
sitting untouched anywhere else in the file contributes equally to both
sides of the before/after multiset diff and never surfaces here; only a
violation THIS write is the first to introduce (or duplicates a second
time) does. That is what makes hard-deny safe against the existing corpus
without wedging every future touch to an already-imperfect payload file.

Reconstructing before/after
-----------------------------
Identical contract to `guard-prompt-surface-citations.py::_reconstruct_after`
— Write uses `tool_input["content"]` directly; Edit/MultiEdit replay
`old_string`/`new_string` (and `replace_all`) over the on-disk `before`.
Any shape this hook cannot confidently reconstruct fails OPEN — a guard
that cannot compute its own input has no basis to deny.

Fail-open guards (all exit 0 silent, in order): unreadable/unparseable
stdin payload; tool_name not in the guarded set; no target path in
tool_input; target not `is_in_scope()` (not part of the local OSS payload,
or a suffix this detector doesn't classify); on-disk read failure for an
existing file; ambiguous before/after reconstruction; zero new violations.
Also fails open, by construction of `_prompt_surface_locality.py`'s own
loaders, if a ratified classification input (`_oss_operative_strings.py`,
`mcp-topology.yaml`, `STRUCTURAL_MARKERS`) fails to load — that narrows
detection (more false positives could surface) rather than bricking this
hook or denying on data it never actually classified.

Design-as-offers deny message
-------------------------------
The deny reason (`_deny_reason`/`_deny_message`, routed through
`_message_envelope.compose`/`emit` per
`docs/plans/2026-08-02-guard-message-character-cap.md`) is now a
one-sentence diagnosis plus a wiki anchor, not the full inline
explanation. The full worked reasoning for each defect kind -- naming the
CAPABILITY instead of the repo, when a name is load-bearing enough to earn
a spot in the ratified `IRREDUCIBLE_LITERALS` table, and why a portable
form replaces a hardcoded drive path -- now lives at `_WIKI_ANCHOR`; see
`state/relocations/guard-message-cap/guard-oss-payload-locality.py.md` for
the relocated prose verbatim.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

from _sentinel_write_guard import extract_target_path  # noqa: E402
from _prompt_surface_locality import is_in_scope, new_violations  # noqa: E402
from _message_envelope import CHANNEL_DENY, Message, compose, emit  # noqa: E402

_GUARDED_TOOLS = ("Write", "Edit", "MultiEdit")

#: Wiki anchor carrying the relocated per-kind remedy explanations -- see
#: `state/relocations/guard-message-cap/guard-oss-payload-locality.py.md`.
_WIKI_ANCHOR = "coordinator/docs/wiki/guard-message-concision.md#oss-payload-locality"

#: Per-kind SHORT alternative, keyed by the exact `Violation.kind` strings
#: `_prompt_surface_locality.iter_violations` emits. The full reasoning for
#: each (the ENTRY CRITERION for `IRREDUCIBLE_LITERALS`, why a portable form
#: replaces a drive path) lives at `_WIKI_ANCHOR`, not here.
_ALTERNATIVES = {
    "private sibling-repo-name attribution": (
        "name the capability, not the repo, or add it to IRREDUCIBLE_LITERALS"
    ),
    "drive-rooted windows path": "use a portable form (pathlib/env var) instead",
}

_DEFAULT_ALTERNATIVE = "prefer a portable, capability-named alternative"


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


def _deny_reason(target: str, violations: list) -> str:
    """The prose diagnosis (the ONLY part `_message_envelope.CEILING`
    counts) -- kept as a separate, importable, plain-string-returning
    function so the character-cap measurement harness's adapter
    (`_adapt_guard_oss_payload_locality` in
    `message_measurement_harness.py`) can call it directly with synthesized
    violations, with no process/stdin/envelope setup. `_deny_message` below
    is what wires this into the real `Message`/emission path.

    Review: code-reviewer, Finding 5 -- a mixed-kind write used to collapse
    to a bare count with a generic default remedy, losing exactly the
    per-kind information an operator needs to act on which violation fired.
    Restores the first two distinct kinds inline (still counted prose, but
    a short list rather than none) for the multi-kind case; the
    single-kind case is unaffected."""
    kinds = sorted({v.kind for v in violations})
    if len(kinds) == 1:
        alt = _ALTERNATIVES.get(kinds[0], _DEFAULT_ALTERNATIVE)
        return (
            f"oss-payload locality: {target} has {len(violations)} "
            f"OSS-unresolvable defect(s) -- {alt}."
        )
    shown = kinds[:2]
    kinds_text = ", ".join(shown)
    if len(kinds) > len(shown):
        kinds_text += f", +{len(kinds) - len(shown)} more"
    return (
        f"oss-payload locality: {target} has {len(violations)} "
        f"OSS-unresolvable defect(s): {kinds_text} -- {_DEFAULT_ALTERNATIVE}."
    )


def _deny_message(target: str, violations: list) -> Message:
    return compose(_deny_reason(target, violations), anchor=_WIKI_ANCHOR)


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

    try:
        new = new_violations(before, after, path=target)
    except Exception:
        return 0
    if not new:
        return 0

    emit(_deny_message(target_raw, new), CHANNEL_DENY)
    return 0


if __name__ == "__main__":
    sys.exit(main())
