"""PreToolUse(Skill) fan-in dispatcher -- the four computed-input legs, one
interpreter, run CONCURRENTLY.

Hosts `nudge-workflow-authoring-trampoline.py` (its Skill-tool fire point
only -- its Workflow-tool leg is untouched, still its own separate
registration), `pickup-autofire.py`, `mise-autofire.py`, and
`handoff-segment-inject.py`'s model-invoked `Skill`-tool entry path -- the
same registry + import-by-path shape `preuse-agent-dispatch.py` already
ships (a `REGISTRY` tuple, `importlib.util.spec_from_file_location`), but
CONCATENATE-ALL like `stop-dispatch.py`, never first-deny-wins: every leg
here is advisory and none of them denies. This is the shape
`docs/decisions/DR-141-advisory-hooks-port-to-the-engine-only-w.md`
establishes -- one dispatcher collapsing N registered advisory legs, not N
registrations.

Problem this closes: `docs/plans/2026-09-11-computed-skill-inputs-reach-
skill-tool-entry.md` census row 2 -- a model-invoked `Skill` tool call never
fires `UserPromptExpansion` at all, so a typed `/pickup`/`/mise-en-place`/
`/warp-speed-execute`/`/handoff` gets its computed brief/claim/run-id/
residue segments, and the same verb invoked programmatically via the
`Skill` tool got nothing. C2/C3/C4 each grew a `compute_context(stdin_text)
-> str | None` entry point reusable from either firing path; this module is
the `PreToolUse(Skill)` registration that reaches them.

Pre-gate: `sys.stdin` is read ONCE, and the verb is read via
`_skill_invocation.read_invocation`. A `Skill` call naming no leg's verb
imports NOTHING and exits 0 silently -- the all-miss path (almost every
Skill-tool call) never pays for a single one of the four modules' imports.

REGISTRY rows -- (leg id, script filename, verb set):
  - trampoline            {"workflow-authoring"}
  - pickup-autofire        {"pickup", "mise-en-place", "warp-speed-execute"}
  - mise-autofire          {"mise-en-place", "warp-speed-execute"}
  - handoff-segment-inject {"handoff"}
`group-em-autofire` is deliberately ABSENT (plan Anti-scope) -- never add it
here. Each non-trampoline row's verb set is pinned in
`test_preuse_skill_dispatch.py` to EQUAL that module's own frozenset
(`pickup-autofire.py`'s `_PICKUP_COMMAND_NAMES | _BATON_GRAB_COMMAND_NAMES`,
`mise-autofire.py`'s `_MISE_COMMAND_NAMES`, `handoff-segment-inject.py`'s
`_HANDOFF_COMMAND_NAMES`) -- a verb added to one of those hooks and not
mirrored here fails that test loudly, closing the
`A-RENAMED-COMMAND-VERB-SILENTLY-UNWIRES-ITS-AUTOFIRE-HOOK` class
mechanically rather than by remembering to update two files in lockstep.

Concurrency (staff-eng F0): every MATCHED leg runs on its own daemon thread
-- the work is subprocess/IO-bound (each leg shells out to a forwarder CLI
with its own multi-second timeout), so the GIL is not a concern. All matched
legs are awaited TOGETHER against one internal deadline
(`_INTERNAL_DEADLINE_SECONDS`, 40s), strictly below C6's 45s PreToolUse(Skill)
registration timeout, leaving headroom for import + scheduling overhead atop
each leg's own subprocess timeouts. A sequential run under one shared budget
could let the harness kill the whole registration and discard every leg's
already-computed context after (say) pickup's `apply` half had already
claimed a baton; running concurrently under a shared sub-deadline means one
slow/hung leg never erases a sibling that finished in time. A leg still
running past the deadline is NOT awaited and does not suppress a sibling
that finished -- see `test_a_slow_leg_does_not_suppress_a_sibling`.

C2/C3/C4 are called through their `compute_context(stdin_text) -> str |
None` entry points DIRECTLY -- no stdout capture needed, they return their
computed context as a plain value. Only the trampoline (no context-
returning entry point; it reads stdin and writes stdout/stderr directly via
`main()`) still needs a stdin-swap-and-capture wrapper -- `_invoke_trampoline`
below is modelled byte-for-byte on `preuse-agent-dispatch.py::_invoke` (the
existing precedent for this exact pattern in this directory), which swaps
`sys.stdin` and redirects BOTH stdout AND stderr per leg, so a leg's
traceback is captured rather than going straight to the harness uncaptured.

Daemon threads, not a `ThreadPoolExecutor` (`_run_legs_concurrently`):
stdlib's `concurrent.futures.thread._python_exit` atexit hook joins EVERY
worker thread of EVERY pool ever created in the process, unconditionally --
`shutdown(wait=False)` does not exempt a pool from it. A leg that genuinely
hangs past the internal deadline would then still block this hook's own
process at interpreter exit, silently defeating the whole point of having a
deadline. Daemon threads are skipped by that join, and daemonizing a pool
would mean re-implementing the private `_adjust_thread_count` against
`_worker`/`_threads_queues`/`_idle_semaphore` -- private stdlib surface this
dispatcher buys nothing from, since four legs need neither a work queue nor
thread reuse.

Extraction: `pickup-autofire.py`, `mise-autofire.py`, and
`handoff-segment-inject.py`'s `compute_context` all return bare
`additionalContext` prose (or `None`) -- `_extract_context_text` just
strips it and turns empty/whitespace-only into `None`. The trampoline is
the one leg with no `compute_context` entry point; its captured stdout is
still the full `hookSpecificOutput` JSON envelope `_message_envelope.emit`
renders directly (that call site is unowned by this diff), so
`_unwrap_trampoline_envelope` unwraps that one shape to the same bare-text
form the other three already return, falling back to the raw stripped text
if unparseable.

Emission: collect each finished leg's non-empty extracted text, in
REGISTRY order, and emit exactly ONE
`_skill_invocation.context_envelope("PreToolUse", "\\n\\n".join(parts))` --
or nothing at all when no leg produced a part. Never two envelopes, never a
leg's raw envelope nested inside this one.

Isolation: each leg's run is isolated by its own `Future` -- an exception
raised inside `_run_leg` (a leg's own `sys.exit`, including the
trampoline's, included: `_invoke_trampoline` catches `SystemExit`) is
caught individually when reading that leg's `.result()`, and skips only that
leg (fail-open for it alone) without affecting any sibling. This dispatcher
always exits 0 and never emits `permissionDecision` -- every leg here is
advisory only.

Negative spec: does not re-implement any leg's own logic (brief/apply/mint/
residue-selection all stay inside their own modules); does not host
`group-em-autofire.py`; does not change the trampoline's own once-per-session
sentinel or its Workflow-tool leg (both untouched, out of this file's reach
entirely -- this file never sees a `tool_name != "Skill"` payload, since it
is registered on the `PreToolUse(Skill)` matcher only).

Spec: docs/plans/2026-09-11-computed-skill-inputs-reach-skill-tool-entry.md
chunk C5.
Precedent this file follows: coordinator/hooks/scripts/preuse-agent-
dispatch.py (registry + import-by-path + per-leg `_invoke` capture shape),
coordinator/hooks/scripts/stop-dispatch.py (concatenate-all aggregation,
never first-deny-wins).

Contract:
  stdin   -- PreToolUse JSON (tool_name == "Skill", tool_input, session_id,
             agent_id, ...)
  stdout  -- one hookSpecificOutput JSON envelope (additionalContext) when
             at least one matched leg produced non-empty context; NOTHING
             otherwise (a Skill call naming no leg's verb, every matched leg
             producing nothing, or every matched leg failing/timing out)
  exit 0  -- always. This dispatcher is advisory-fan-in only and never
             blocks/denies.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, FrozenSet, List, Optional, Tuple

_HOOKS_DIR = Path(__file__).resolve().parent
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

from _skill_invocation import context_envelope, read_invocation  # noqa: E402
# Channel-agnostic despite its home module's stderr framing: it captures this
# dispatcher's stdout.
from _stop_family_runner import _BufferedTextCapture  # noqa: E402

# Strictly below C6's 45s PreToolUse(Skill) registration timeout -- see this
# module's docstring "Concurrency" section for the arithmetic/rationale.
_INTERNAL_DEADLINE_SECONDS = 40.0

# Verb sets -- see this module's docstring "REGISTRY rows" section. Kept as
# named constants (not inline tuple literals) so
# `test_preuse_skill_dispatch.py` can import and pin each one directly
# against the owning module's own frozenset without re-deriving it from
# REGISTRY first.
_TRAMPOLINE_VERBS: FrozenSet[str] = frozenset({"workflow-authoring"})
_PICKUP_AUTOFIRE_VERBS: FrozenSet[str] = frozenset(
    {"pickup", "mise-en-place", "warp-speed-execute"}
)
_MISE_AUTOFIRE_VERBS: FrozenSet[str] = frozenset({"mise-en-place", "warp-speed-execute"})
_HANDOFF_SEGMENT_INJECT_VERBS: FrozenSet[str] = frozenset({"handoff"})


@dataclass(frozen=True)
class SkillLeg:
    leg_id: str
    module_key: str
    filename: str
    verbs: FrozenSet[str]
    # True for the one leg with no `compute_context` entry point -- it must
    # run through the stdin-swap-and-capture wrapper instead of being called
    # directly.
    is_trampoline: bool = False


REGISTRY: Tuple[SkillLeg, ...] = (
    SkillLeg(
        "trampoline",
        "nudge_workflow_authoring_trampoline",
        "nudge-workflow-authoring-trampoline.py",
        _TRAMPOLINE_VERBS,
        is_trampoline=True,
    ),
    SkillLeg(
        "pickup-autofire",
        "pickup_autofire",
        "pickup-autofire.py",
        _PICKUP_AUTOFIRE_VERBS,
    ),
    SkillLeg(
        "mise-autofire",
        "mise_autofire",
        "mise-autofire.py",
        _MISE_AUTOFIRE_VERBS,
    ),
    SkillLeg(
        "handoff-segment-inject",
        "handoff_segment_inject",
        "handoff-segment-inject.py",
        _HANDOFF_SEGMENT_INJECT_VERBS,
    ),
)


def _run_legs_concurrently(
    matched: List[SkillLeg], stdin_text: str
) -> Tuple[dict, List[str]]:
    """Run every matched leg on its own DAEMON thread, joining each under one
    shared deadline. Returns `({leg_id: context_text_or_None}, [skipped ids])`.

    Daemon threads, not a `ThreadPoolExecutor`: stdlib's
    `concurrent.futures.thread._python_exit` atexit hook joins every worker
    thread of every pool ever created, and `shutdown(wait=False)` does not
    exempt a pool from it -- so a leg hanging past
    `_INTERNAL_DEADLINE_SECONDS` would still block the host process at
    interpreter exit, silently defeating the deadline this dispatcher exists
    to enforce (staff-eng F0). Daemon threads are skipped by that join. A
    pool could only be daemonized by re-implementing the private
    `_adjust_thread_count` against `_worker`/`_threads_queues`/
    `_idle_semaphore`; four legs need no work-queue or thread reuse, so
    plain threads do the same job with no private stdlib surface.

    Each leg's result lands under its own key and each exception is caught
    inside its own thread, so one leg's crash or hang never reaches a
    sibling. `dict.__setitem__` and `list.append` are atomic under the GIL,
    which is all the synchronisation the result handoff needs.
    """
    results: dict = {}
    failed: List[str] = []

    def _runner(leg: SkillLeg) -> None:
        try:
            results[leg.leg_id] = _run_leg(leg, stdin_text)
        except BaseException:
            failed.append(leg.leg_id)

    threads = [
        (leg, threading.Thread(target=_runner, args=(leg,),
                               name="skill-leg-" + leg.leg_id, daemon=True))
        for leg in matched
    ]
    for _leg, thread in threads:
        thread.start()

    deadline = time.monotonic() + _INTERNAL_DEADLINE_SECONDS
    for _leg, thread in threads:
        thread.join(max(0.0, deadline - time.monotonic()))

    skipped = list(failed)
    for leg, thread in threads:
        if thread.is_alive():
            skipped.append(leg.leg_id + " (past internal deadline)")
    return results, skipped


def _import_leg(leg: SkillLeg) -> Any:
    if leg.module_key in sys.modules:
        return sys.modules[leg.module_key]
    spec = importlib.util.spec_from_file_location(leg.module_key, str(_HOOKS_DIR / leg.filename))
    if spec is None or spec.loader is None:
        raise ImportError(leg.filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[leg.module_key] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop(leg.module_key, None)
        raise
    return mod


def _invoke_trampoline(main_fn, stdin_text: str) -> Tuple[int, str, str]:
    """Run the trampoline's `main()` with stdin swapped and BOTH stdout and
    stderr captured -- byte-for-byte modelled on
    `preuse-agent-dispatch.py::_invoke`, this fan-in's own cited precedent
    for the exact pattern a no-`compute_context` leg needs. Catches
    `SystemExit` (the trampoline's own `sys.exit(main())` guard, and any
    `main_fn` that exits rather than returns) so it never escapes this
    leg's own isolation.
    """
    old_stdin = sys.stdin
    out_buf = _BufferedTextCapture()
    err_buf = _BufferedTextCapture()
    rc = 0
    with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
        sys.stdin = io.StringIO(stdin_text)
        try:
            try:
                rc = main_fn()
            except SystemExit as exc:
                rc = exc.code if isinstance(exc.code, int) else 0
        finally:
            sys.stdin = old_stdin
    return (rc or 0), out_buf.combined(), err_buf.combined()


def _extract_context_text(raw: Optional[str]) -> Optional[str]:
    """Strip a `compute_context` leg's bare `additionalContext` return
    value; returns `None` for an empty/`None`/whitespace-only value. All
    three `compute_context` legs return bare prose (F1), so no
    envelope-unwrapping happens here -- see this module's own docstring
    "Extraction" section.
    """
    if not raw or not raw.strip():
        return None
    return raw.strip()


def _unwrap_trampoline_envelope(raw: Optional[str]) -> Optional[str]:
    """Unwrap the trampoline's captured stdout -- the one leg with no
    `compute_context` entry point, whose captured output is still the full
    `hookSpecificOutput` JSON envelope `_message_envelope.emit` renders --
    to the same bare `additionalContext` text shape the other three legs
    return. Falls back to the raw stripped text if unparseable, so a shape
    change here degrades to visible text rather than disappearing.
    """
    if not raw or not raw.strip():
        return None
    text = raw.strip()
    try:
        obj = json.loads(text)
    except Exception:
        return text
    if isinstance(obj, dict):
        hso = obj.get("hookSpecificOutput")
        if isinstance(hso, dict):
            ctx = hso.get("additionalContext")
            if isinstance(ctx, str) and ctx:
                return ctx
    return text


def _run_leg(leg: SkillLeg, stdin_text: str) -> Optional[str]:
    """Import and run ONE matched leg to completion, returning its extracted
    `additionalContext` text or `None`. Any exception raised anywhere in
    this function (import failure, a leg's own crash) propagates into this
    leg's own `Future`, isolating it from every sibling leg's future.
    """
    mod = _import_leg(leg)
    if leg.is_trampoline:
        _rc, out, _err = _invoke_trampoline(getattr(mod, "main"), stdin_text)
        return _unwrap_trampoline_envelope(out)
    compute_context = getattr(mod, "compute_context")
    return _extract_context_text(compute_context(stdin_text))


def main() -> int:
    raw = sys.stdin.read()

    try:
        payload = json.loads(raw) if raw else {}
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    inv = read_invocation(payload)
    if inv is None:
        return 0  # unrecognized payload shape -- silent pass, nothing imported

    matched = [leg for leg in REGISTRY if inv.command_name in leg.verbs]
    if not matched:
        return 0  # a Skill call naming no leg's verb -- silent pass, nothing imported

    parts: List[str] = []
    results, skipped = _run_legs_concurrently(matched, raw)

    # REGISTRY order, not completion order -- a deterministic render
    # regardless of which leg happened to finish first.
    for leg in matched:
        text = results.get(leg.leg_id)
        if text:
            parts.append(text)

    if skipped:
        try:
            sys.stderr.write(
                "[preuse-skill-dispatch] leg(s) skipped (fail-open for those "
                "only): " + ", ".join(skipped) + "\n"
            )
        except Exception:
            pass

    if not parts:
        return 0

    try:
        print(context_envelope("PreToolUse", "\n\n".join(parts)))
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
