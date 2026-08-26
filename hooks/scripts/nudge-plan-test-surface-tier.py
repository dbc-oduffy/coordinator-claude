"""PreToolUse hook (matcher: Write|Edit|MultiEdit): plan-write-time ADVISORY
closing the gap where `block-dispatch-suite-invocation.py` (registered on
`Agent|Workflow` only) never sees a plan body being authored -- an EM can
write "run the full suite green" into a chunk's test-surface row, the plan
gets reviewed and ratified carrying it, and the only catch is the dispatch
guard firing later, after the plan has already cleared review on the
strength of a test-surface row that was never enforceable as written. See
`coordinator/skills/plan/residue/shared-corpus.md` (the test-surface row:
the named surface must be Tier T, path-scoped to the files the chunk
authors or touches -- naming the repo's fast tier or full suite is
malformed at plan-write time for the same reason it is at dispatch time).

ADVISORY, NOT A DENY. A plan body legitimately QUOTES a suite command in
prose, an Anti-scope list, or a Tried/Failed record -- the dispatch guard
denies because a dispatch prompt is an instruction; a plan body is a
document. Per global doctrine's "design tooling as offers, not nags", this
leads with the alternative: name the chunk's own path-scoped (Tier T) tests
-- global/cadence-tier verification is EM-owned at the wave boundary, never
a chunk deliverable.

Tripwire token: PLAN-TEST-SURFACE-TIER (emitted literally in the advisory
text below; registered in `coordinator/docs/wiki/coordinator-tripwires/tripwire-registry/`).

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

Reconstructing the write's content -- via the shared
`_sentinel_write_guard.reconstruct_after` re-export (Write: `content`
verbatim; Edit: single or `replace_all` substitution into the on-disk
`before`; MultiEdit: the same, applied sequentially). This hook classifies
`after` directly (not a before/after diff) -- unlike the citation guard,
there is no large legacy-violation corpus to avoid re-flagging; a plan body carrying an
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
`coordinator/docs/wiki/coordinator-tripwires/tripwire-registry/` -- NOT touched here.

SECOND DETECTOR (C4, `docs/plans/2026-08-19-vehicle-prohibition-caught-by-a-mechanism.md`)
-- a plan cannot pick its execution vehicle
(`coordinator/docs/wiki/coordinator-tripwires/a-plan-does-not-pick-the-execution-vehicle.md`,
token `A-PLAN-DOES-NOT-PICK-THE-EXECUTION-VEHICLE`). C1/C2 (a dispatch-time detector) were
CUT on a measured zero fire rate (`state/audits/2026-08-19-vehicle-advisory-baseline.md`) --
this is the one authorship-time leg that ships. NARROW OR NOTHING: this detector matches
`_VEHICLE_PHRASE_PATTERNS` (kept as one named constant so a reader can diff this guard's
vocabulary against the `plan-coverage-checker` Anti-scope lens's finding text) ONLY inside a
plan body's `## Anti-scope` section -- the first `## Anti-scope` heading to the next
same-level `## ` heading, fenced code blocks excluded (`_extract_anti_scope_section`). A
vehicle-naming sentence anywhere else in the body (a Tried/Failed record, a quoted parent
baton, a whole-body scan) is deliberately invisible to this detector -- see
`writing-plans.md` § Test Surface's standing objection to whole-corpus prose-matching, which
this narrowing answers by construction rather than by tuning. The vocabulary is narrow by
design: literal execution-vehicle nouns (`fan-out`, `EM-sequenced`, `chunk-at-a-time`,
`hand-dispatch`, "one executor owns the whole thing"), not generic mechanism words -- a
registration/hook prohibition inside `## Anti-scope` (e.g. "do not add a seventh standalone
PreToolUse:Agent registration") names no vehicle noun and stays silent, which is the plan's
own worked fixture for the negative case.

Review: coordinator:code-reviewer (finding 2) -- `chunk-at-a-time`/`hand-dispatch` can also
fire on legitimate non-dispatch prose (e.g. a data-migration batching constraint); accepted
residual risk of the narrow-vocabulary design, not tightened further.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

from _sentinel_write_guard import extract_target_path, reconstruct_after  # noqa: E402
from _message_envelope import CHANNEL_ADDITIONAL_CONTEXT, Message, compose, emit  # noqa: E402

_GUARDED_TOOLS = ("Write", "Edit", "MultiEdit")

#: Mirrors `coordinator_core.write_guards.block_subagent_plan_body_write.
#: _PLAN_BODY_RE`, narrowed to `plans/` only -- see module docstring.
_PLAN_BODY_RE_SUFFIX = "/docs/plans/"

#: Mirrors that same module's `_FIXTURE_PATH_RE` test-fixture exemption.
_FIXTURE_SEGMENT = "/tests/fixtures/"

_ANCHOR = "coordinator/skills/plan/residue/shared-corpus.md § test-surface row"

_TOKEN = "PLAN-TEST-SURFACE-TIER"

#: One named constant, per the module docstring's "SECOND DETECTOR" note --
#: kept narrow (literal execution-vehicle nouns from the tripwire's own
#: "Tell", not generic mechanism/registration words) so it never matches a
#: legitimate hook/registration prohibition sitting in the same section.
_VEHICLE_TOKEN = "A-PLAN-DOES-NOT-PICK-THE-EXECUTION-VEHICLE"

_VEHICLE_ANCHOR = (
    "coordinator/docs/wiki/coordinator-tripwires/"
    "a-plan-does-not-pick-the-execution-vehicle.md"
)

_ANTI_SCOPE_HEADING = "## Anti-scope"

_VEHICLE_PHRASE_PATTERNS: "tuple[re.Pattern[str], ...]" = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bfan-out\b",
        r"\bem-sequenced\b",
        r"\bchunk[- ]at[- ]a[- ]time\b",
        r"\bhand-dispatch(?:ed)?\b",
        r"one executor owns the whole thing",
    )
)


def _extract_anti_scope_section(text: str) -> str:
    """Section boundary: the first `## Anti-scope` heading (exact, own
    line) to the next same-level `## ` heading, exclusive. Fenced code
    blocks (```...```) within that span are stripped before returning, so a
    quoted example inside a fence never reaches the phrase matcher. Returns
    "" when no `## Anti-scope` heading exists -- the caller treats that as
    "nothing to match".

    Review: coordinator:code-reviewer (finding 1) -- fence PARITY is carried
    in from the top of the document, not reset to False at `start`. A fence
    opened before `## Anti-scope` and still open when the section begins
    (malformed markdown, but plans are long freeform documents) would
    otherwise make genuinely-fenced content read as plain text, the exact
    false-positive shape the in-section fence handling below exists to
    rule out -- just triggered from outside the section."""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip() == _ANTI_SCOPE_HEADING:
            start = i + 1
            break
    if start is None:
        return ""

    end = len(lines)
    for j in range(start, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break

    in_fence = False
    for line in lines[:start]:
        if line.strip().startswith("```"):
            in_fence = not in_fence

    kept: "list[str]" = []
    for line in lines[start:end]:
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        kept.append(line)
    return "\n".join(kept)


def _vehicle_match(anti_scope_text: str) -> "str | None":
    """First `_VEHICLE_PHRASE_PATTERNS` match in `anti_scope_text`, or None.
    Caller is responsible for having already scoped `anti_scope_text` to a
    `## Anti-scope` section -- this function does no section detection of
    its own."""
    for pattern in _VEHICLE_PHRASE_PATTERNS:
        hit = pattern.search(anti_scope_text)
        if hit:
            return hit.group(0)
    return None


def _vehicle_advisory_message(target: str, phrase: str) -> Message:
    return compose(
        f"{_VEHICLE_TOKEN}: {target}'s ## Anti-scope names an execution "
        f"vehicle (\"{phrase}\") -- a plan owns what changes and what must "
        "not, not how it is dispatched; the vehicle is resolved at "
        "dispatch time from file overlap and the gate graph. Re-express a "
        "real constraint as a depends_on edge or a named carve-out instead.",
        anchor=_VEHICLE_ANCHOR,
    )


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


def _classify(text: str) -> "list[Any]":
    """Resolve the engine plane's root, import the shared classifier, call
    it. Returns [] (never raises) on any infra failure -- byte-for-byte the
    same fail-open contract as
    `block-dispatch-suite-invocation.py::_classify`, which this mirrors
    rather than imports (that file is not a module other hooks import from;
    every consumer re-does this same seam)."""
    try:
        from _engine_root import (  # noqa: E402
            resolve_claude_klabauter_root,
            place_engine_root_on_path as _place_engine_root_on_path,
        )
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
    # root on sys.path, so a module-name collision between a doctrine-plane-local
    # helper and a same-named engine-side module resolves toward the
    # doctrine-plane-local helper. Migrated to append-ordered resolution as part of
    # C2 (see _LATE_INSERT_RATCHET's former entry for this guard in
    # coordinator/tests/test_guard_runner_contract.py).
    # Index-1 placement via the shared primitive: hooks dir stays at 0, engine root
    # outranks site-packages. A bare append put it BEHIND an editable install of the
    # engine, so the resolver answered the mirror and the import returned the working
    # tree -- see _engine_root.place_engine_root_on_path.
    _place_engine_root_on_path(engine_root)

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
        f"{_TOKEN}: {target} names {detected} as its test surface -- "
        "Tier T (path-scoped to the chunk's own files) is what a plan may "
        "name; global/cadence verification is EM-owned at the wave "
        "boundary, not a chunk's job.",
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

    after = reconstruct_after(payload.get("tool_name", ""), tool_input, before)
    if after is None:
        return 0

    matches = _classify(after)
    imperative = [m for m in matches if getattr(m, "position", "") == "imperative"]
    if imperative:
        hit = imperative[0]
        detected = getattr(hit, "detected", "a test-suite command")
        emit(_advisory_message(target_raw, detected), CHANNEL_ADDITIONAL_CONTEXT)
        return 0

    anti_scope_text = _extract_anti_scope_section(after)
    if anti_scope_text:
        phrase = _vehicle_match(anti_scope_text)
        if phrase:
            emit(_vehicle_advisory_message(target_raw, phrase), CHANNEL_ADDITIONAL_CONTEXT)
            return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
