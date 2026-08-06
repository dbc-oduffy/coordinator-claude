"""PreToolUse hook (matcher: Write|Edit|MultiEdit): warns on a write that
introduces a NEW unresolvable citation into a coordinator prompt surface.

Why this exists
----------------
`coordinator/{agents,skills,commands,snippets,pipelines}/` percolate — they run
in sibling repos, on other operators' machines, and in OSS installs that ship a
deliberately sparse curated wiki seed. A citation that resolves in THIS clone (a plan,
a decision record, an archived spec, a cross-repo memo, a non-seed wiki, a bare
`DR-`/`SC-DR-` id) 404s for those readers. See `_prompt_surface_citations.py`'s
module docstring for the full defect-class writeup and the false-positive
classes this guard deliberately does NOT flag.

Advise, not deny (PM ruling, 2026-08-05)
-----------------------------------------
This was a hard-deny; it is now an advisory on `CHANNEL_ADDITIONAL_CONTEXT`.
The detector is unchanged — only the channel moved.

Nothing ships broken as a result, because the deny was never the last line of
defence. `coordinator/tests/test_prompt_surfaces_cite_resolvably.py` is a
ratchet whose baseline is `{}`: a new unresolvable citation anywhere in the
governed surfaces fails the test tier, and its baseline may not be regenerated
to launder a regression. Denying at write time bought earlier feedback on a
call the author is better placed to make — some citations are worth inlining,
some are worth an allowlist entry, and a guard that cannot tell the difference
should offer the alternative rather than refuse the write.

The scoping that made hard-deny defensible still governs what fires at all,
and still matters now that the message is advisory: this hook flags only
`new_violations(before, after)` — see that function's docstring in
`_prompt_surface_citations.py` — a multiset difference between the file's
citations before and after this specific write. The governed corpus is
currently at zero (`test_prompt_surfaces_cite_resolvably.py`'s baseline is
`{}`); the scoping is what keeps this guard correct if that debt is ever
reintroduced — an import, a merge, a bulk authoring pass — rather than
re-flagging every legacy citation in a file each time someone edits it.
Review: code-reviewer — Finding 5, ~550-figure was stale against the
ratchet's zero baseline.

Reconstructing before/after
-----------------------------
`before` is the current on-disk content (empty string for a not-yet-existing
file). `after` is reconstructed from `tool_input` without ever needing the
harness to hand it over pre-computed:
  - Write: `tool_input["content"]` directly.
  - Edit: `before` with `old_string` replaced by `new_string` once — matching
    the Edit tool's own single-replacement contract. `old_string == ""` is the
    Edit tool's own "file did not exist / is empty" shape, so `after` is just
    `new_string` in that case.
  - MultiEdit: the same replacement applied sequentially over `tool_input["edits"]`.
Any shape this hook cannot confidently reconstruct (missing/wrong-typed field,
`old_string` absent from `before`) fails OPEN — a guard that cannot compute its
own input has no basis to deny, and NotebookEdit is out of matcher scope
entirely since prompt surfaces are exclusively `.md`.

Fail-open guards (all exit 0 silent, in order): unreadable/unparseable stdin
payload; tool_name not in the guarded set; no target path in tool_input;
target not `is_in_scope()` (wrong tree, wrong extension, or under a
`tests/`/`fixtures/` subdirectory); on-disk read failure for an existing file;
ambiguous before/after reconstruction; zero new violations.

Design-as-offers message
--------------------------
The advisory text (`_deny_reason`/`_deny_message` — names retained so the
character-cap measurement harness's adapter keeps resolving them, routed through
`_message_envelope.compose`/`emit` per
`docs/plans/2026-08-02-guard-message-character-cap.md`) is now a one-sentence
diagnosis plus a wiki anchor, not the full inline explanation. The two
legitimate exits it used to spell out here -- inline the content if the
dispatched agent needs it to do its job, or promote the target into the OSS
seed wiki allowlist (a deliberate, ratified edit to
`coordinator/tests/test_publish_seed_wiki_allowlist.py`'s `SEED_WIKIS`, cited
resolvably via `${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}`,
never a bare repo-relative path), or delete the pointer if neither is worth
doing -- now live at `_WIKI_ANCHOR`; see
`state/relocations/guard-message-cap/guard-prompt-surface-citations.py.md`
for the relocated prose verbatim.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

from _sentinel_write_guard import extract_target_path  # noqa: E402
from _prompt_surface_citations import is_in_scope, new_violations  # noqa: E402
from _message_envelope import CHANNEL_ADDITIONAL_CONTEXT, Message, compose, emit  # noqa: E402

_GUARDED_TOOLS = ("Write", "Edit", "MultiEdit")

#: Wiki anchor carrying the relocated explanation of why an unresolvable
#: citation is a problem and the two legitimate exits -- see
#: `state/relocations/guard-message-cap/guard-prompt-surface-citations.py.md`.
_WIKI_ANCHOR = "coordinator/docs/wiki/guard-message-concision.md#prompt-surface-citations"


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
        # Review: coordinator:code-reviewer -- F1: mirror check-claude-md-size.py's
        # replace_all handling. A single-replace here undercounts a `replace_all`
        # write that introduces the same new citation in several places.
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
            # Review: coordinator:code-reviewer -- F1: mirror check-claude-md-size.py's
            # per-edit replace_all handling.
            text = (
                text.replace(old_s, new_s)
                if edit.get("replace_all")
                else text.replace(old_s, new_s, 1)
            )
        return text

    return None


def _deny_reason(target: str, violations: list) -> str:
    """The prose diagnosis (the ONLY part `_message_envelope.CEILING` counts)
    -- kept as a separate, importable, plain-string-returning function so
    the character-cap measurement harness's adapter
    (`_adapt_guard_prompt_surface_citations` in
    `message_measurement_harness.py`) can call it directly with synthesized
    violations, with no process/stdin/envelope setup. `_deny_message` below
    is what wires this into the real `Message`/emission path.

    Review: code-reviewer, Finding 5 -- restores the first couple of
    distinct violation `kind`s inline so a multi-violation write still
    names WHICH citation kind fired, rather than a bare count."""
    kinds = sorted({v.kind for v in violations})
    shown = kinds[:2]
    kinds_text = ", ".join(shown)
    if len(kinds) > len(shown):
        kinds_text += f", +{len(kinds) - len(shown)} more"
    return (
        f"{target} adds {len(violations)} citation(s) unresolvable outside "
        f"this clone ({kinds_text}). Inline it, or add to the OSS seed wiki "
        "allowlist."
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

    new = new_violations(before, after)
    if not new:
        return 0

    emit(_deny_message(target_raw, new), CHANNEL_ADDITIONAL_CONTEXT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
