"""_guard_runner.py -- the in-process guard runner (chunk C1) that batches
doctrine-plane-resident write-path guards inside the same interpreter
`preuse-write-dispatch.py` already starts for the sibling engine call.

Implements `_guard_runner_contract.py` (the GOVERNING SURFACE, landed C1a,
commit `6fe03bc5`) verbatim -- see that module's numbered clauses for the
authoritative statement of each behaviour below; this docstring cross-refers
rather than restating.

Deviation from the C1 chunk brief's stated footprint, recorded here and in
this dispatch's run-report sidecar per the brief's own escalation
instruction: the brief's footprint list names only
`preuse-write-dispatch.py` and the two test files, but
`coordinator/tests/test_guard_runner_contract.py` (already landed, C1's
brief permits ONLY removing its stale xfail markers, no other change) hard
-codes `from _guard_runner import run_guards` in its two xfail-pending-C1
legs. Satisfying that already-committed, unmodifiable import is only
possible by creating this module under exactly this name -- there is no
footprint-respecting alternative that still turns those xfails green, which
the chunk brief separately states as expected ("Your work should turn those
xfails into passes"). Treated as the minimal necessary file, not a scope
expansion: it holds only the runner mechanism the brief describes.

Two layers:

  1. `run_guards()` -- the pure, class-aware AGGREGATION core (clause 10)
     with per-entry EXCEPTION ISOLATION (clause 11). Operates on already
     -produced verdict dicts (`{"channel": ..., "text": ...}`) or
     `(name, callable)` pairs it invokes itself. This is what the
     contract's Leg 2 (aggregation) and Leg 3 (exception isolation)
     conformance tests drive directly.

  2. `run_registered_guards()` -- the real-guard invocation wrapper: TWO
     -STAGE LAZY IMPORT (clause 12) via `GuardScopeDescriptor.matches()`
     evaluated before any guard body is imported, per-guard stdin/stdout
     /stderr capture (STDERR CAPTURE, clause 6), translation of a guard's
     JSON stdout envelope into the verdict shape `run_guards()` aggregates,
     then a call into `run_guards()` for the actual aggregation. This is
     what `preuse-write-dispatch.py` calls after the engine call; C2 (next
     wave) populates the currently-empty registry with the three residual
     guards.

Spec: docs/plans/2026-08-06-hook-spawn-fan-in-finish-and-extend.md, § C1.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Union

#: Runner-owned sys.path setup (clause 4: guard code itself must never
#: mutate sys.path; only the runner may, once, at discovery time -- clause
#: 8 governs ORDERING). This module's own self-resolution idiom mirrors
#: every guard's `_HOOKS_DIR` pattern: inserted at the top, before any
#: other import, so it is exempt from the "late insert" conformance check
#: that applies to guard modules (this module is the runner, not a guard).
_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

from _guard_runner_contract import (  # noqa: E402
    CHANNEL_ADDITIONAL_CONTEXT,
    CHANNEL_DENY,
    CHECK_CLAUDE_MD_SIZE_SCOPE_DESCRIPTOR,
    DOCTRINE_CHANGELOG_PROSE_SCOPE_DESCRIPTOR,
    GUARD_DOCTRINE_SURFACE_RATIO_SCOPE_DESCRIPTOR,
    GuardScopeDescriptor,
)

#: A verdict is the shape both layers speak: `{"channel": ..., "text": ...}`.
GuardVerdict = Dict[str, str]
#: `run_guards()` accepts either an already-computed verdict dict, or a
#: `(name, callable)` pair it invokes itself under exception isolation.
GuardEntry = Union[GuardVerdict, Tuple[str, Callable[[Any], Optional[GuardVerdict]]]]


def run_guards(
    guards: Iterable[GuardEntry],
    payload: Any,
    skipped_out: Optional[List[str]] = None,
) -> dict:
    """Contract clause 10 (class-aware aggregation) + clause 11 (exception
    isolation), as one pure-ish core: no I/O beyond invoking `callable`
    entries, no sys.path/env mutation.

    At most one DENY reaches the result -- the FIRST `CHANNEL_DENY` verdict
    wins; every `CHANNEL_ADDITIONAL_CONTEXT` text (deny-channel or not)
    concatenates into one `additionalContext` string, so a deny and an
    advisory firing on the same payload both surface.

    A `(name, callable)` entry that raises `BaseException` (clause 11 is
    deliberately this broad -- a stray `SystemExit`/`KeyboardInterrupt`
    escaping guard code must not abort the batch either) has its `name`
    appended to `skipped_out` and the batch continues; `skipped_out`
    defaults to a fresh list when the caller does not supply one (mirrors
    `preuse-write-dispatch.py`'s own `_skipped` breadcrumb -- callers pass
    that exact list in so this function populates it directly, per clause
    11's "reuses the SAME breadcrumb" requirement).
    """
    if skipped_out is None:
        skipped_out = []

    deny_text: Optional[str] = None
    context_parts: List[str] = []

    for entry in guards:
        if isinstance(entry, tuple):
            name, fn = entry
            try:
                verdict = fn(payload)
            except BaseException:
                skipped_out.append(name)
                continue
        else:
            verdict = entry

        if not verdict:
            continue

        channel = verdict.get("channel")
        text = verdict.get("text")
        if not text:
            continue

        if channel == CHANNEL_DENY:
            if deny_text is None:
                deny_text = text
        elif channel == CHANNEL_ADDITIONAL_CONTEXT:
            context_parts.append(text)

    result: dict = {}
    if deny_text is not None:
        result["permissionDecision"] = "deny"
        result["permissionDecisionReason"] = deny_text
    result["additionalContext"] = "\n\n".join(context_parts)
    return result


def envelope_to_verdict(out: Optional[dict]) -> Optional[GuardVerdict]:
    """Translate an existing `{"hookSpecificOutput": {...}}` envelope (the
    shape both the sibling engine call and a guard's own `_message_envelope`
    -composed stdout already produce) into the `{"channel", "text"}` verdict
    shape `run_guards()` aggregates. `None` in, `None` out; an envelope with
    neither a deny nor an additionalContext key also yields `None`."""
    if not out or not isinstance(out, dict):
        return None
    hook_output = out.get("hookSpecificOutput")
    if not isinstance(hook_output, dict):
        return None
    if hook_output.get("permissionDecision") == "deny":
        return {"channel": CHANNEL_DENY, "text": hook_output.get("permissionDecisionReason") or ""}
    if "additionalContext" in hook_output:
        return {
            "channel": CHANNEL_ADDITIONAL_CONTEXT,
            "text": hook_output.get("additionalContext") or "",
        }
    return None


def verdict_to_envelope(result: dict) -> Optional[dict]:
    """Inverse of `envelope_to_verdict`: fold a `run_guards()` aggregate
    result back into the ONE `{"hookSpecificOutput": {...}}` envelope a
    PreToolUse hook may write to stdout (only one hookSpecificOutput
    envelope per hook process -- clause 10). Returns `None` when the
    aggregate carries neither a deny nor any advisory text, matching
    `preuse-write-dispatch.py`'s existing "print nothing on allow"
    contract."""
    has_deny = result.get("permissionDecision") == "deny"
    has_context = bool(result.get("additionalContext"))
    if not has_deny and not has_context:
        return None
    hook_output: dict = {"hookEventName": "PreToolUse"}
    if has_deny:
        hook_output["permissionDecision"] = "deny"
        hook_output["permissionDecisionReason"] = result["permissionDecisionReason"]
    if has_context:
        hook_output["additionalContext"] = result["additionalContext"]
    return {"hookSpecificOutput": hook_output}


def _target_path_from_payload(payload: Any) -> Optional[str]:
    """Cheap, import-free extraction of the edited path from a raw
    PreToolUse payload dict -- the input `GuardScopeDescriptor.matches()`
    is evaluated against (clause 12). Covers the `file_path`/`notebook_path`
    shapes `tool_input` carries across Write/Edit/MultiEdit/NotebookEdit."""
    if not isinstance(payload, dict):
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    for key in ("file_path", "notebook_path", "path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return value
    return None


@dataclass(frozen=True)
class RegisteredGuard:
    """One enrolled guard: where its `main()` lives (a filesystem path, not
    a dotted module name -- guard filenames are hyphenated and not valid
    Python identifiers), its import-free `GuardScopeDescriptor`, the
    `sys.modules` key the runner registers it under on import (observable
    directly by a test per AC2 -- "assert this by observing sys.modules,
    not by inference from timing"), and its entrypoint attribute name
    (`main` for every guard on the contract's `ENROLLED_GUARD_MODULES`
    list).

    `verdict_attr` (C4): the STDOUT-JSON invocation path (`entry_attr` +
    `_invoke_guard_main`) is what every guard conveys its verdict through
    EXCEPT `check-claude-md-size.py`, whose deny/advisory text travels via
    captured STDERR instead (its own `verdict_from_exit`/`run_via_runner`,
    per the C3 PM ruling -- that guard predates `_message_envelope` and
    routing its prose through `emit()` would additionally enrol it in the
    unrelated Category-A message-budget census). `verdict_attr`, when set,
    names a module attribute matching the `GuardEntry` callable shape
    directly (`Callable[[Any], Optional[GuardVerdict]]`) -- `build_registry_
    entries` calls it with the PARSED payload dict instead of going through
    `_invoke_guard_main`'s stdin/stdout swap. `None` (the default) preserves
    the original stdout-JSON path unchanged for every other enrolled guard.
    This is the registry learning the stderr-verdict shape (C4's chosen fix
    over a one-off adapter entry) -- any future guard whose verdict travels
    outside the stdout-JSON envelope can reuse this same seam rather than
    each inventing its own."""

    module_key: str
    module_path: str
    descriptor: GuardScopeDescriptor
    entry_attr: str = "main"
    verdict_attr: Optional[str] = None


def _invoke_guard_main(main_fn: Callable[[], int], stdin_text: str) -> GuardVerdict:
    """Runs one guard's `main()` with stdin/stdout/stderr swapped
    (prototype-proven shape -- `state/audits/2026-08-06-inprocess-guard-
    runner-prototype/proto_inproc.py`), catches `SystemExit` (clause 1: the
    runner calls `main()` directly and never lets a guard's own
    control-flow exit escape), captures the guard's stdout JSON envelope
    (clause 6: STDERR CAPTURE -- captured here too, per-guard, never
    forwarded to the real stderr stream directly), and translates the
    envelope into the `{"channel", "text"}` verdict shape via
    `envelope_to_verdict`. A guard that raises something other than
    `SystemExit` propagates -- the caller (`run_guards`, via its
    `(name, callable)` entry path) is responsible for exception isolation
    (clause 11); this function's job is translation, not isolation."""
    stdin_buf = io.StringIO(stdin_text)
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    old_stdin = sys.stdin
    with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
        sys.stdin = stdin_buf
        try:
            try:
                main_fn()
            except SystemExit:
                pass
        finally:
            sys.stdin = old_stdin

    out_text = stdout_buf.getvalue().strip()
    if not out_text:
        return {}
    try:
        envelope = json.loads(out_text)
    except Exception:
        return {}
    verdict = envelope_to_verdict(envelope)
    return verdict or {}


def _import_guard_module(guard: RegisteredGuard):
    """Stage-two import (clause 12): only reached once
    `guard.descriptor.matches(target_path)` is already `True`. Uses
    `importlib.util.spec_from_file_location` (not `import_module`) because
    guard filenames are hyphenated and not importable dotted names; the
    module is registered into `sys.modules[guard.module_key]` so a test can
    observe the import directly, per AC2."""
    if guard.module_key in sys.modules:
        return sys.modules[guard.module_key]
    spec = importlib.util.spec_from_file_location(guard.module_key, guard.module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load guard module at {guard.module_path!r}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[guard.module_key] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(guard.module_key, None)
        raise
    return module


def build_registry_entries(
    registry: Iterable[RegisteredGuard],
    raw_payload_text: str,
    payload: Any,
) -> List[Tuple[str, Callable[[Any], GuardVerdict]]]:
    """Two-stage lazy import (clause 12), realised as a list of
    `(name, callable)` entries `run_guards()` can consume directly. A
    guard whose descriptor does NOT match `payload`'s target path never
    appears here at all -- its module is never imported, because the
    callable that would import it is never constructed, let alone called."""
    target_path = _target_path_from_payload(payload)
    entries: List[Tuple[str, Callable[[Any], GuardVerdict]]] = []
    for guard in registry:
        if not guard.descriptor.matches(target_path):
            continue

        def _call(_payload: Any, _guard: RegisteredGuard = guard) -> GuardVerdict:
            module = _import_guard_module(_guard)
            if _guard.verdict_attr:
                # STDERR-verdict path (C4): the guard's own callable already
                # returns the `{"channel", "text"}` shape (or `None`) given
                # the parsed payload directly -- no stdin/stdout swap here,
                # that plumbing is internal to the guard's own callable.
                verdict_fn = getattr(module, _guard.verdict_attr)
                return verdict_fn(_payload) or {}
            main_fn = getattr(module, _guard.entry_attr)
            return _invoke_guard_main(main_fn, raw_payload_text)

        entries.append((guard.module_key, _call))
    return entries


#: C4 enrolment registry: ALL FIVE `_guard_runner_contract.
#: ENROLLED_GUARD_MODULES` write-path guards -- the three C2 enrolled first
#: (`guard-oss-payload-locality.py`, `nudge-plan-test-surface-tier.py`,
#: `guard-prompt-surface-citations.py`), plus `guard-doctrine-changelog-
#: prose.py` (C3b) and `check-claude-md-size.py` (C3's protocol translation,
#: wired for real here) added by C4 once each guard's parity was proven.
#: Every descriptor here is IMPORTED from `_guard_runner_contract`, never a
#: copy re-declared in this file -- `DOCTRINE_CHANGELOG_PROSE_SCOPE_
#: DESCRIPTOR` and `CHECK_CLAUDE_MD_SIZE_SCOPE_DESCRIPTOR` are the same
#: objects `coordinator/tests/test_inprocess_guard_runner.py` and
#: `coordinator/tests/test_check_claude_md_size_runner_fold.py` verify --
#: the three C2 guards' descriptors are still declared inline below (their
#: own scope predicates were never at risk of the "test-file-only, never
#: wired" drift the other two were flagged for, since they were authored
#: alongside this registry from the start). Every descriptor lives HERE (or
#: in the contract module, for the two C3/C3b guards), not inside the
#: guard's own body module, per contract clause 12's explicit "import-free
#: and live OUTSIDE the guard's own body module" requirement -- a
#: descriptor sourced from the guard module itself would be circular
#: (importing the guard to ask whether to import the guard defeats the
#: lazy-import win). Each descriptor deliberately OVERAPPROXIMATES its
#: guard's own real `is_in_scope()` predicate (which the guard body still
#: applies, correctly, once imported) -- a descriptor's only job is to rule
#: out payloads that could never possibly match, cheaply, before paying an
#: import; false-positive matches here just mean the real (and still
#: authoritative) in-guard scope check runs and fails open, exactly as it
#: does when invoked standalone.
_GUARD_OSS_PAYLOAD_LOCALITY = "guard-oss-payload-locality.py"
_GUARD_PLAN_TEST_SURFACE_TIER = "nudge-plan-test-surface-tier.py"
_GUARD_PROMPT_SURFACE_CITATIONS = "guard-prompt-surface-citations.py"
_GUARD_DOCTRINE_CHANGELOG_PROSE = "guard-doctrine-changelog-prose.py"
_GUARD_CHECK_CLAUDE_MD_SIZE = "check-claude-md-size.py"
_GUARD_TEST_TREE_GIT_FIXTURE_SPAWN = "guard-test-tree-git-fixture-spawn.py"
_GUARD_PYTHON_SYNTAX_ON_WRITE = "guard-python-syntax-on-write.py"
_GUARD_DOCTRINE_SURFACE_RATIO = "guard-doctrine-surface-ratio.py"
_GUARD_POSIX_INVOCATION_DOCTRINE_WRITE = "guard-posix-invocation-doctrine-write.py"
_GUARD_HANDOFF_SUMMARY_CAP_ON_WRITE = "guard-handoff-summary-cap-on-write.py"

REAL_GUARD_REGISTRY: Tuple[RegisteredGuard, ...] = (
    RegisteredGuard(
        module_key="guard_python_syntax_on_write",
        module_path=str(Path(_HOOKS_DIR) / _GUARD_PYTHON_SYNTAX_ON_WRITE),
        descriptor=GuardScopeDescriptor(
            guard_module=_GUARD_PYTHON_SYNTAX_ON_WRITE,
            # Real scope (the guard's own `is_in_scope`) is ".py" files with
            # "coordinator" among the RESOLVED ABSOLUTE path's parts. This
            # descriptor instead substring-tests the RAW tool_input path —
            # a different test that over-admits relative to `is_in_scope`,
            # which is the safe direction (under-admitting would not be).
            # They agree in practice only because Write/Edit/MultiEdit
            # mandate absolute `file_path` inputs.
            path_suffixes=frozenset({".py"}),
            directory_substrings=("coordinator/",),
        ),
    ),
    RegisteredGuard(
        module_key="guard_oss_payload_locality",
        module_path=str(Path(_HOOKS_DIR) / _GUARD_OSS_PAYLOAD_LOCALITY),
        descriptor=GuardScopeDescriptor(
            guard_module=_GUARD_OSS_PAYLOAD_LOCALITY,
            # Real scope (`_prompt_surface_locality.is_in_scope` ->
            # `_oss_payload.is_payload_path`) is ".py"/".md" tracked payload
            # files, mostly under coordinator/ (the local third of the OSS
            # mirror). ".py"/".md" + "coordinator/" overapproximates that
            # cheaply without importing the payload-membership machinery.
            path_suffixes=frozenset({".py", ".md"}),
            directory_substrings=("coordinator/",),
        ),
    ),
    RegisteredGuard(
        module_key="nudge_plan_test_surface_tier",
        module_path=str(Path(_HOOKS_DIR) / _GUARD_PLAN_TEST_SURFACE_TIER),
        descriptor=GuardScopeDescriptor(
            guard_module=_GUARD_PLAN_TEST_SURFACE_TIER,
            # Real scope is `docs/plans/**/*.md` (see the guard's own
            # `_is_plan_body_path`).
            path_suffixes=frozenset({".md"}),
            directory_substrings=("docs/plans/",),
        ),
    ),
    RegisteredGuard(
        module_key="guard_prompt_surface_citations",
        module_path=str(Path(_HOOKS_DIR) / _GUARD_PROMPT_SURFACE_CITATIONS),
        descriptor=GuardScopeDescriptor(
            guard_module=_GUARD_PROMPT_SURFACE_CITATIONS,
            # Real scope is `.md` under the five PROMPT_SURFACE_DIRS trees
            # (see `_prompt_surface_citations.PROMPT_SURFACE_DIRS`).
            path_suffixes=frozenset({".md"}),
            directory_substrings=(
                "coordinator/agents/",
                "coordinator/skills/",
                "coordinator/commands/",
                "coordinator/snippets/",
                "coordinator/pipelines/",
            ),
        ),
    ),
    RegisteredGuard(
        module_key="guard_doctrine_changelog_prose",
        module_path=str(Path(_HOOKS_DIR) / _GUARD_DOCTRINE_CHANGELOG_PROSE),
        descriptor=DOCTRINE_CHANGELOG_PROSE_SCOPE_DESCRIPTOR,
    ),
    RegisteredGuard(
        module_key="check_claude_md_size",
        module_path=str(Path(_HOOKS_DIR) / _GUARD_CHECK_CLAUDE_MD_SIZE),
        descriptor=CHECK_CLAUDE_MD_SIZE_SCOPE_DESCRIPTOR,
        # STDERR-verdict path (C4): see `RegisteredGuard.verdict_attr`'s own
        # docstring -- this guard's verdict travels via captured stderr
        # (`check-claude-md-size.py`'s own `run_via_runner`), not the
        # stdout-JSON envelope the other four enrolled guards use.
        verdict_attr="run_via_runner",
    ),
    RegisteredGuard(
        module_key="guard_test_tree_git_fixture_spawn",
        module_path=str(Path(_HOOKS_DIR) / _GUARD_TEST_TREE_GIT_FIXTURE_SPAWN),
        descriptor=GuardScopeDescriptor(
            guard_module=_GUARD_TEST_TREE_GIT_FIXTURE_SPAWN,
            # C9 (docs/plans/2026-08-07-restore-the-excised-tests-spawn-free.md).
            # Deliberately OVER-approximating and repo-generic: a bare
            # "tests/" substring (never "coordinator/tests/") plus ".py"
            # suffix -- the guard's own `spawn_detect.is_test_tree_site()`
            # call is the real, precise, structural scope predicate (see
            # that guard's own module docstring "SCOPE-EXPRESSION NOTE");
            # this descriptor's only job is to rule out payloads that could
            # never possibly match, cheaply, before paying the import.
            path_suffixes=frozenset({".py"}),
            directory_substrings=("tests/",),
        ),
    ),
    RegisteredGuard(
        module_key="guard_doctrine_surface_ratio",
        module_path=str(Path(_HOOKS_DIR) / _GUARD_DOCTRINE_SURFACE_RATIO),
        descriptor=GUARD_DOCTRINE_SURFACE_RATIO_SCOPE_DESCRIPTOR,
    ),
    RegisteredGuard(
        module_key="guard_posix_invocation_doctrine_write",
        module_path=str(Path(_HOOKS_DIR) / _GUARD_POSIX_INVOCATION_DOCTRINE_WRITE),
        descriptor=GuardScopeDescriptor(
            guard_module=_GUARD_POSIX_INVOCATION_DOCTRINE_WRITE,
            # Real scope (the guard's own `is_in_scope`) is a target path
            # under one of the three AC5 trees (skills/, commands/,
            # docs/wiki/), no suffix restriction beyond that. This
            # descriptor is exactly that predicate -- no heavier import is
            # needed to build it, unlike the doctrine-changelog-prose /
            # doctrine-surface-ratio guards above, which pull their governed
            # trees from a module this registry must not import eagerly.
            directory_substrings=(
                "coordinator/skills/",
                "coordinator/commands/",
                "coordinator/docs/wiki/",
            ),
        ),
    ),
    RegisteredGuard(
        module_key="guard_handoff_summary_cap_on_write",
        module_path=str(Path(_HOOKS_DIR) / _GUARD_HANDOFF_SUMMARY_CAP_ON_WRITE),
        descriptor=GuardScopeDescriptor(
            guard_module=_GUARD_HANDOFF_SUMMARY_CAP_ON_WRITE,
            # Real scope (the guard's own `is_in_scope`) is ".md" files
            # under a `state/handoffs/` directory (live or archived). This
            # descriptor is exactly that predicate.
            path_suffixes=frozenset({".md"}),
            directory_substrings=("state/handoffs/",),
        ),
    ),
)


def run_registered_guards(
    registry: Iterable[RegisteredGuard],
    raw_payload_text: str,
    payload: Any,
    skipped_out: Optional[List[str]] = None,
) -> dict:
    """The dispatcher-facing entrypoint: two-stage lazy import
    (`build_registry_entries`) feeding the aggregation/exception-isolation
    core (`run_guards`). Returns the same aggregate shape `run_guards`
    does; `preuse-write-dispatch.py` folds this together with the engine's
    own verdict via `envelope_to_verdict`/`verdict_to_envelope` so exactly
    one `hookSpecificOutput` envelope reaches the harness."""
    entries = build_registry_entries(registry, raw_payload_text, payload)
    return run_guards(entries, payload, skipped_out=skipped_out)
