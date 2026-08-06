"""The Stop-family PostToolUse advisory runner contract: a SIBLING contract
to `_guard_runner_contract.py` (GUARD-ON-RUNNER-CONTRACT), not an extension
of it, for a genuinely different aggregation problem.

Why a second contract, not a widened first one
-------------------------------------------------
`_guard_runner_contract.py` earned its twelve clauses solving ONE specific
problem: many PreToolUse guards, one stdout `hookSpecificOutput` envelope,
one exit code, CLASS-AWARE deny-vs-additionalContext combining (at most one
deny surfaces; every advisory concatenates). Four of the five PostToolUse
write-path guards this contract enrolls (`derive-global-doctrine-live-copy.py`,
`derive-setup-copies.py`, `nudge-initiative-goals-ladder.py`,
`nudge-new-file-zero-budget-ratchets.py`) speak a DIFFERENT native protocol
entirely -- the Stop-family shape (`_message_envelope.CHANNEL_STOP`, or the
identical hand-rolled stderr-write-then-`return 2` idiom the two `derive-*`
guards use pre-`_message_envelope`): each guard EITHER writes its own prose
directly to stderr and returns `2`, OR stays silent and returns `0`. There is
no deny/advisory class distinction here, no `permissionDecisionReason` vs
`additionalContext` split -- just N independent "did I have something to say"
signals that must combine into ONE process's ONE stderr write and ONE exit
code. `_guard_runner_contract.py`'s own docstring scopes this out explicitly:
"CHANNEL_STOP is a Stop-family shape out of scope here." Widening that
contract's vocabulary to also describe this shape would produce one contract
describing two protocols imprecisely, forcing every future guard author to
work out which half applies to them. Two small honest contracts beat one
general dishonest one -- this module is the second one, deliberately kept
independent (its own enrolment list, its own aggregation rule, its own
conformance test) rather than layered onto the first.

The ONE thing reused from `_guard_runner_contract.py`, and why that is not
"widening" it: `GuardScopeDescriptor` (imported below) is a channel-neutral
primitive -- a frozen dataclass doing cheap path-suffix/directory-substring
matching, with zero knowledge of DENY/ADDITIONAL_CONTEXT/STOP or any other
channel concept. Reusing it here is the same kind of reuse `str`/`Path`
would be; it is not sharing this contract's own vocabulary.

Spec: docs/plans/2026-08-06-hook-spawn-fan-in-finish-and-extend.md § C4b
(the PostToolUse Stop-family collapse, split from C4's PreToolUse phase 1
because this is CONSTRUCTION -- a genuinely new aggregation mechanism -- not
wiring an existing one).

--------------------------------------------------------------------------
CONTRACT MINIMUM (every enrolled Stop-family guard must satisfy)
--------------------------------------------------------------------------

1. ENTRYPOINT SHAPE. A guard exposes `main() -> int`, returning `0` (silent)
   or `2` (fired -- prose already written to `sys.stderr` by the guard
   itself before returning). `main()` MUST NOT use `sys.exit()` for control
   flow -- same reasoning as `_guard_runner_contract.py` clause 1: the
   runner calls `main()` directly and uses its return value. The guard's
   own `__main__` block MAY still read `sys.exit(main())`.

2. NO `os._exit`, NO `atexit` HANDLER REGISTRATION, NO CWD/`sys.path`
   MUTATION FROM GUARD CODE, NO CROSS-INVOCATION MODULE-GLOBAL STATE,
   IMPORT SIDE-EFFECT FREEDOM -- identical reasoning to
   `_guard_runner_contract.py` clauses 2-5, 7 (general Python-hygiene rules
   for code batched inside one process, not specific to either channel).

3. STDERR CAPTURE. The runner captures each guard's stderr per-guard,
   never letting it reach the real stderr stream directly -- needed so the
   combined dispatcher can compose ONE stderr write from every fired
   guard's captured text, per the AGGREGATION RULE below.

4. AGGREGATION IS CONCATENATE-ALL, NEVER FIRST-FIRES-WINS. Across one
   batch of guards run against one payload: the combined dispatcher writes
   ONE stderr blob containing the captured text of EVERY guard that
   returned `2` (never just the first), separated so each guard's advisory
   stays legible, and returns `2` if ANY guard fired, `0` only if none did.
   This is the one clause that genuinely differs from
   `_guard_runner_contract.py` clause 10's class-aware DENY-vs-advisory
   split -- there is no "class" here, every fired guard's text is
   equally an advisory the reader must see. First-fires-wins would
   silently drop every subsequent guard's advisory on a payload where two
   or more fire together, which is exactly the "a guard fires and says
   nothing" failure this whole plan sequence keeps turning up -- see the
   README write to `~/.claude/CLAUDE.md` case in the PreToolUse runner
   (`_guard_runner_contract.py` clause 10's own rationale) for the same
   argument in the sibling channel.

5. EXCEPTION ISOLATION. Each guard's `main()` call runs inside its own
   `try/except BaseException`; on failure, the runner records the guard's
   name and CONTINUES to the next guard rather than aborting the batch --
   same reasoning as `_guard_runner_contract.py` clause 11.

6. LAZY IMPORT IS TWO-STAGE, via `GuardScopeDescriptor` (imported from
   `_guard_runner_contract.py` -- see the module docstring's "ONE thing
   reused" section for why this import is not itself a contract-widening).
   Descriptors live HERE, in `STOP_FAMILY_SCOPE_DESCRIPTORS` below, never
   inside a guard's own body module -- identical reasoning to
   `_guard_runner_contract.py` clause 12.

Conformance test: `coordinator/tests/test_stop_family_runner_contract.py`
-- the same grep-conformance sweep `test_guard_runner_contract.py` runs for
`ENROLLED_GUARD_MODULES`, sourced from THIS module's own
`ENROLLED_GUARD_MODULES` constant, plus the concatenate-all aggregation
case and the exception-isolation case.
"""

from __future__ import annotations

from typing import Tuple

from _guard_runner_contract import GuardScopeDescriptor

#: Greppable registry token for this contract, registered in
#: coordinator/docs/wiki/coordinator-tripwires.md in the same commit as
#: this module.
TRIPWIRE_TOKEN = "STOP-FAMILY-RUNNER-CONTRACT"

#: The four PostToolUse write-path guards that speak the Stop-family
#: protocol (stderr text + `return 2`, or silent `return 0`) -- the
#: residual set left after C4 phase 1 folded `track-touched-files.py` into
#: `postuse-advisory-dispatch.py` instead (it has no advisory text to
#: aggregate, so it needed no new aggregation mechanism at all). Filenames
#: only (no directory prefix) -- each is a sibling of this module under
#: coordinator/hooks/scripts/.
ENROLLED_GUARD_MODULES: Tuple[str, ...] = (
    "derive-global-doctrine-live-copy.py",
    "derive-setup-copies.py",
    "nudge-initiative-goals-ladder.py",
    "nudge-new-file-zero-budget-ratchets.py",
)

#: Each descriptor deliberately OVERAPPROXIMATES its guard's own real
#: scope predicate (still applied, correctly, once the guard body is
#: imported) -- see each guard's own module docstring for the authoritative
#: scope. Keyed by filename so `postuse-stop-family-dispatch.py` and the
#: conformance test can both source from THIS one dict rather than either
#: re-declaring a copy.
STOP_FAMILY_SCOPE_DESCRIPTORS = {
    # Real scope: file_path resolves to exactly the tracked
    # `global-doctrine/CLAUDE.md` path (see `_tracked_path()`), or a
    # `hook_event_name == "SessionStart"` payload (not reachable via this
    # guard's current PostToolUse-only hooks.json registration -- see this
    # module's own docstring section on C4b -- so path-shape is the only
    # discriminant a Write|Edit|MultiEdit-scoped descriptor needs).
    "derive-global-doctrine-live-copy.py": GuardScopeDescriptor(
        guard_module="derive-global-doctrine-live-copy.py",
        path_suffixes=frozenset({"CLAUDE.md"}),
        directory_substrings=("global-doctrine/",),
    ),
    # Real scope: file_path resolves to one of six canonical/derived rows,
    # all under a `setup/` tree (either `<repo>/setup/...` or
    # `coordinator/templates/setup/...` -- see `_resolved_rows()`). No
    # suffix restriction: the three tracked pairs are `.yaml`, `.md`, `.py`.
    "derive-setup-copies.py": GuardScopeDescriptor(
        guard_module="derive-setup-copies.py",
        directory_substrings=("setup/",),
    ),
    # Real scope: file_path is a `state/initiatives/*.yaml` write (see
    # `is_initiative_yaml` in `main()`).
    "nudge-initiative-goals-ladder.py": GuardScopeDescriptor(
        guard_module="nudge-initiative-goals-ladder.py",
        path_suffixes=frozenset({".yaml"}),
        directory_substrings=("state/initiatives/",),
    ),
    # Real scope: a NEW (untracked) file under either this repo's own
    # `coordinator/` tree ("local" leg) or a resolvable sibling engine
    # checkout's root ("engine" leg -- see `_classify_leg()`). KNOWN,
    # DOCUMENTED GAP: the "engine" leg has no fixed directory substring a
    # cheap descriptor can name without resolving the engine root itself
    # (exactly the import this descriptor exists to defer paying) -- an
    # engine-leg write to a path that does not also contain "coordinator/"
    # under-matches. Accepted for the same reason `guard-oss-payload-
    # locality.py`'s own descriptor (C2) is scoped to "coordinator/" only:
    # the "local" leg is the common, load-bearing case; the "engine" leg
    # is a rare cross-repo edge the guard's own real predicate (still
    # authoritative once imported) already fails open on when this repo's
    # OWN write path is what fires -- see that guard's descriptor in
    # `_guard_runner.REAL_GUARD_REGISTRY` for the identical precedent.
    "nudge-new-file-zero-budget-ratchets.py": GuardScopeDescriptor(
        guard_module="nudge-new-file-zero-budget-ratchets.py",
        directory_substrings=("coordinator/",),
    ),
}
