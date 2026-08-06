"""PreToolUse hook (matcher: Write|Edit|MultiEdit): plan-write-time ADVISORY
closing the gap where `block-dispatch-suite-invocation.py` (registered on
`Agent|Workflow` only) never sees a plan body being authored -- an EM can
write "run the full suite green" into a chunk's test-surface row, the plan
gets reviewed and ratified carrying it, and the only catch is the dispatch
guard firing later, after the plan has already cleared review on the
strength of a test-surface row that was never enforceable as written. See
`coordinator/skills/plan/SKILL.md` line ~156 (the test-surface row: "The
named test surface MUST be Tier T ... Naming the repo's fast tier or full
suite as a chunk's test surface is malformed at plan-write time").

ADVISORY, NOT A DENY. A plan body legitimately QUOTES a suite command in
prose, an Anti-scope list, or a Tried/Failed record -- the dispatch guard
denies because a dispatch prompt is an instruction; a plan body is a
document. Per global doctrine's "design tooling as offers, not nags", this
leads with the alternative: name the chunk's own path-scoped (Tier T) tests
-- global/cadence-tier verification is EM-owned at the wave boundary, never
a chunk deliverable.

Tripwire token: PLAN-TEST-SURFACE-TIER (emitted literally in the advisory
text below; registered in `coordinator/docs/wiki/coordinator-tripwires.md`).

Classification -- ZERO new regex over suite commands. This hook reuses the
exact same classifier `block-dispatch-suite-invocation.py` already reuses:
`coordinator_core.bash_guards.check_test_suite_invocation.classify_text`,
imported through the same `_engine_root.resolve_claude_klabauter_root()` seam. A
`classify_text` match with `position == "imperative"` is, by that module's
own contract, ALWAYS a Tier-F or Tier-U (suite-shaped, i.e. NOT
path/node-id-scoped) invocation -- `classify_text` never reports a Tier-T
match at all (see its module docstring's negative spec) -- so "any
imperative match" and "names the fast tier or full suite" are the same
predicate here; no separate tier check is needed. `position` in
{"fenced_code", "inline_code", "negated", "reported", "descriptive",
"unknown"} is exactly the "quoting it in prose, not instructing it" shape a
plan body legitimately carries, and is never advised on.

Plan-body detection -- mirrors the sibling engine plane's
`coordinator_core.write_guards.block_subagent_plan_body_write` regex idiom
(`_PLAN_BODY_RE` / `_FIXTURE_PATH_RE`), narrowed to `docs/plans/` only (not
`docs/problems/`, which is a ratified problem-set, not a chunk-bearing plan
body with a test-surface row). Applied to the raw `file_path` string
(separator-normalized), same as that module -- no `Path.resolve()`, so this
fires identically whether the dispatching call named an absolute or
repo-relative path. A `tests/fixtures/**` path is exempted for the same
reason that module exempts it: static golden fixtures under a test package
are not a live plan a chunk deliverable will ever be dispatched from.

Reconstructing the write's content -- same `before`/`old_string`/
`new_string` replacement idiom as `guard-prompt-surface-citations.py`'s
`_reconstruct_after` (Write: `content` verbatim; Edit: single or
`replace_all` substitution into the on-disk `before`; MultiEdit: the same,
applied sequentially). This hook classifies `after` directly (not a
before/after diff) -- unlike the citation guard, there is no large
legacy-violation corpus to avoid re-flagging; a plan body carrying an
un-fixed Tier-F/U test-surface row is worth advising on every touch of that
file until it is fixed.

Fail-open guards (all silent, exit 0): unreadable/unparseable stdin;
`tool_name` not in {Write, Edit, MultiEdit}; no target path in
`tool_input`; target not plan-body-shaped (or under `tests/fixtures/`);
`after`-content reconstruction ambiguous (mirrors the citation guard's own
fail-open list -- missing/wrong-typed field, `old_string` absent from
`before`); the engine root unresolvable; `coordinator_core.bash_guards.
check_test_suite_invocation` unimportable; `classify_text` itself raising;
zero imperative matches. A broken/half-landed sibling classifier must never
brick plan authoring -- worse than the gap this hook closes.

Spec: inline dispatch brief (no plan file), team-lead dispatch
2026-08-06, "Plan-write-time tier advisory hook". Sibling deliverable
(tripwire registration, SKILL.md/wiki wording) owned by a peer worker in
`coordinator/skills/plan/SKILL.md`, `coordinator/docs/wiki/writing-plans.md`,
`coordinator/docs/wiki/coordinator-tripwires.md` -- NOT touched here.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

from _sentinel_write_guard import extract_target_path  # noqa: E402
from _message_envelope import CHANNEL_ADDITIONAL_CONTEXT, Message, compose, emit  # noqa: E402

_GUARDED_TOOLS = ("Write", "Edit", "MultiEdit")

#: Mirrors `coordinator_core.write_guards.block_subagent_plan_body_write.
#: _PLAN_BODY_RE`, narrowed to `plans/` only -- see module docstring.
_PLAN_BODY_RE_SUFFIX = "/docs/plans/"

#: Mirrors that same module's `_FIXTURE_PATH_RE` test-fixture exemption.
_FIXTURE_SEGMENT = "/tests/fixtures/"

_ANCHOR = "coordinator/skills/plan/SKILL.md § test-surface row (line ~156)"

_TOKEN = "PLAN-TEST-SURFACE-TIER"


def _normalize_path(file_path: str) -> str:
    """Native-separator -> slash, collapse repeated slashes -- same
    normalization intent as `block_subagent_plan_body_write._normalize_path`
    (so the two guards agree on what counts as a plan-body path), expressed
    via `os.sep` rather than a literal backslash so this file carries no
    hardcoded Windows-separator constant for the POSIX-exec-assumption
    scanner to flag (`path_separator` -- zero-budget for a new file)."""
    normalized = file_path.replace(os.sep, "/")
    while "//" in normalized:
        normalized = normalized.replace("//", "/")
    return normalized


def _is_plan_body_path(normalized: str) -> bool:
    """True iff `normalized` is a `docs/plans/**/*.md` path, at any depth,
    and NOT under a `tests/fixtures/` segment. Deliberately string-suffix
    based (not a full regex port) since the only shapes this hook needs to
    tell apart are "ends under docs/plans/ as markdown" and "is repo-root
    vs. nested under a fixtures tree" -- see module docstring."""
    if not normalized.endswith(".md"):
        return False
    if not (normalized.startswith("docs/plans/") or _PLAN_BODY_RE_SUFFIX in normalized):
        return False
    if _FIXTURE_SEGMENT in normalized or normalized.startswith("tests/fixtures/"):
        return False
    return True


def _reconstruct_after(tool_name: str, tool_input: dict, before: str) -> "Optional[str]":
    """Same idiom as `guard-prompt-surface-citations.py::_reconstruct_after`
    -- ported rather than imported since that module's function is private
    to its own file and this hook has no other dependency on it."""
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


def _classify(text: str) -> "list[Any]":
    """Resolve the engine plane's root, import the shared classifier, call
    it. Returns [] (never raises) on any infra failure -- byte-for-byte the
    same fail-open contract as
    `block-dispatch-suite-invocation.py::_classify`, which this mirrors
    rather than imports (that file is not a module other hooks import from;
    every consumer re-does this same seam)."""
    try:
        from _engine_root import resolve_claude_klabauter_root  # noqa: E402
    except Exception:
        return []

    try:
        engine_root = resolve_claude_klabauter_root()
    except Exception:
        engine_root = None

    if not engine_root:
        return []

    # Contract clause 8 (SYS.PATH ORDERING, _guard_runner_contract.py):
    # appended, never inserted at index 0 -- the hooks dir (inserted at the
    # top of this module, before this point) must stay AHEAD of the engine
    # root on sys.path, so a module-name collision between a DoE-local
    # helper and a same-named engine-side module resolves toward the
    # DoE-local helper. Migrated to append-ordered resolution as part of
    # C2 (see _LATE_INSERT_RATCHET's former entry for this guard in
    # coordinator/tests/test_guard_runner_contract.py).
    if engine_root not in sys.path:
        sys.path.append(engine_root)

    try:
        from coordinator_core.bash_guards.check_test_suite_invocation import (  # noqa: E402
            classify_text,
        )
    except Exception:
        return []

    try:
        return list(classify_text(text, cwd=os.getcwd()))
    except Exception:
        return []


def _advisory_message(target: str, detected: str) -> Message:
    return compose(
        f"{_TOKEN}: {target} names {detected} as a chunk's test surface -- "
        "Tier T (path-scoped to the chunk's own files) is what a plan "
        "deliverable may name; global/cadence verification is EM-owned at "
        "the wave boundary, never a chunk's job.",
        anchor=_ANCHOR,
    )


def main() -> int:
    # Review: coordinator:code-reviewer (finding 2) -- outer backstop so the
    # module docstring's closed "Fail-open guards" list is actually closed:
    # `_reconstruct_after` and the final compose()/emit() call previously sat
    # outside any guard. Not exploitable today, but a later template change
    # (e.g. an empty `detected`) could reintroduce a hard crash on this
    # advisory-only path without this wrapper.
    try:
        return _main_impl()
    except Exception:
        return 0


def _main_impl() -> int:
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

    normalized = _normalize_path(target_raw)
    if not _is_plan_body_path(normalized):
        return 0

    try:
        target_path = Path(target_raw)
        before = (
            target_path.read_text(encoding="utf-8", errors="replace")
            if target_path.is_file()
            else ""
        )
    except Exception:
        before = ""

    after = _reconstruct_after(payload.get("tool_name", ""), tool_input, before)
    if after is None:
        return 0

    matches = _classify(after)
    imperative = [m for m in matches if getattr(m, "position", "") == "imperative"]
    if not imperative:
        return 0

    hit = imperative[0]
    detected = getattr(hit, "detected", "a test-suite command")

    emit(_advisory_message(target_raw, detected), CHANNEL_ADDITIONAL_CONTEXT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
