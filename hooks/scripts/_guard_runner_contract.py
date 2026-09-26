"""The guard-on-runner contract: what an enrolled write-path guard must (and
must not) do so the in-process runner (C1, next wave) can batch multiple
guards inside ONE Python interpreter safely, and what the aggregation,
exception-isolation, lazy-import, sys.path-ordering, and measurement-mode
seams around it guarantee.

Written FIRST, ahead of the runner (C1) and the guard migrations (C2), per
this repo's CLAUDE.md discharge test: "for every rule, what artifact
discharges it? If the operator remembers, the work is not finished." The
2026-08-06 in-process prototype proved the mechanism works; this module is
the durable, greppable statement of the contract that proof was promoted
into, registered alongside it in
`coordinator/docs/wiki/coordinator-tripwires/guard-on-runner-contract.md` under the
`GUARD-ON-RUNNER-CONTRACT` token (same commit, per the greppability rule).

Sibling module, not a `preuse-write-dispatch.py` docstring/constant surface
-- C1 owns that file in a later wave and must not collide with this one
here. Import-free at module scope beyond the standard library: this module
is imported on the cold hook path (every edit), so it carries only
constants/enums/dataclasses, never guard logic.

Spec: docs/plans/2026-08-06-hook-spawn-fan-in-finish-and-extend.md § C1a.

--------------------------------------------------------------------------
CONTRACT MINIMUM (every enrolled guard must satisfy all of the following)
--------------------------------------------------------------------------

1. ENTRYPOINT SHAPE. A guard exposes `main() -> int`. `main()` MUST NOT use
   `sys.exit()` for control flow -- the runner calls `main()` directly and
   inspects its return value; it never wraps the call in a
   `try/except SystemExit` to recover a control-flow exit. The guard's own
   `__main__` block MAY still read `sys.exit(main())` (this is what keeps
   the guard independently invocable as a standalone script -- see clause
   9, MEASUREMENT MODE), but that block is never reached when the runner
   calls `main()` in-process.

2. NO `os._exit`. Unrecoverable -- `os._exit()` bypasses cleanup and kills
   the whole hook process mid-run, taking down every OTHER guard batched in
   the same runner invocation along with it.

3. NO `atexit` HANDLER REGISTRATION. A guard's `atexit` handler would fire
   at hook-PROCESS exit, not at the guard's own logical end -- registering
   one leaks guard-local cleanup timing into every subsequent guard's run
   inside the same process and into the process's own shutdown.

4. NO CWD MUTATION; NO `sys.path` MUTATION FROM GUARD CODE. A guard runs
   batched with siblings inside one process -- `os.chdir()` or an
   uncoordinated `sys.path` write inside guard logic corrupts every guard
   that runs after it in the same batch. (The RUNNER may perform its own
   sys.path setup once, at import-scope discovery time -- see clause 8,
   SYS.PATH ORDERING -- but that is runner-owned, not guard-owned, and
   happens before any guard's `main()` executes.)

5. NO CROSS-INVOCATION MODULE-GLOBAL STATE. A guard module must not
   accumulate state in a module-level global across separate `main()`
   invocations within the same process lifetime. The 2026-08-06 prototype
   measured module-global accumulation flat across 10 consecutive
   in-process runs -- this clause is what keeps that true going forward,
   not a one-time measurement result to cite in place of the rule.

6. STDERR CAPTURE. The runner captures each guard's stderr output
   per-guard; a guard's stderr text never reaches the real stderr stream
   directly under the runner. (Needed so a captured deny reason is
   recoverable downstream -- see C3's exit-code-to-`permissionDecisionReason`
   mapping, which is out of scope for this module.)

7. IMPORT SIDE-EFFECT FREEDOM. Importing a guard module (the module-scope
   code that runs on `import guard_module`, before any function is called)
   must be side-effect-free -- no I/O, no env mutation, no state
   registration. The runner may import many guard modules in sequence
   inside one process; an import-time side effect in one guard is invisible
   to review and corrupts every guard imported after it.

8. SYS.PATH PLACEMENT. The runner (not any individual guard) is responsible
   for `sys.path` setup, and it places the sibling engine's root by calling
   `_engine_root.place_engine_root_on_path()` -- never by hand-rolling an
   append or an insert at a call site. That primitive puts the root at index 1,
   immediately BEHIND the hooks directory (`coordinator/hooks/scripts/`) and
   ahead of everything else, so a module-NAME collision between a
   doctrine-plane-local helper and a same-named engine-side module still
   resolves toward the doctrine-plane-local helper.
   Do NOT reintroduce `sys.path.append` here. Appending satisfies the
   hooks-dir-ahead requirement and nothing else: it puts the root behind
   site-packages, and therefore behind an editable install of the engine, so
   the resolver answers the published mirror while the import returns the
   working tree -- in a clean process, every time. Placement is necessary but
   not sufficient; it still loses to a module cache bound by an earlier bare
   `import coordinator_core`, which `_engine_root.engine_import_provenance()`
   is what actually detects.
   If a caller needs the engine root resolved before its own self-resolution,
   it must restore the hooks dir to the front of `sys.path` before the
   guard-import phase runs, not leave the engine root ahead of it permanently.

9. MEASUREMENT MODE IS STANDALONE-INVOCATION-ONLY. `_message_envelope.emit()`
   already special-cases `COORDINATOR_HOOK_MESSAGE_MEASURE=1` to write a
   structured measurement record (see `_message_envelope.py`'s
   `_write_measurement_record`) instead of the real channel output. This
   contract does NOT specify a runner-side passthrough for that mode: the
   runner's own aggregation (clause 10) concatenates every guard's captured
   stdout into ONE additionalContext envelope, which would swallow or
   mangle a measurement record emitted by an individual guard mid-batch.
   Measurement mode is therefore standalone-invocation-only -- a guard's own
   `__main__` entry (clause 1) stays live specifically so measurement
   continues to work by invoking the guard as a standalone script, never
   through the runner's batched path. A future runner MAY add passthrough,
   but until it does, this is the deliberate, stated resolution -- not an
   omission.

--------------------------------------------------------------------------
RUNNER-SIDE GUARANTEES (properties the runner itself must hold; not
guard-authored, but every enrolled guard depends on them)
--------------------------------------------------------------------------

10. AGGREGATION IS CLASS-AWARE, NOT FIRST-DENY-WINS. Across one batch of
    guards run against one payload: at most one DENY reaches the harness --
    the FIRST guard whose verdict is `CHANNEL_DENY` short-circuits any
    REMAINING `CHANNEL_DENY` guards (they do not run, or their verdict is
    discarded if they already ran) -- but ALL `additionalContext` texts
    produced by every guard in the batch (deny-channel or not) are
    concatenated into a SINGLE `additionalContext` envelope, because stdout
    can carry only one hookSpecificOutput envelope per hook process. A deny
    and an advisory firing on the SAME payload must both reach the harness
    -- the deny via `permissionDecisionReason`, the advisory via the
    aggregated `additionalContext` text.

11. EXCEPTION ISOLATION. Each guard's `main()` call runs inside its own
    `try/except BaseException` (deliberately as broad as `BaseException`,
    not `Exception`, so a stray `SystemExit` or `KeyboardInterrupt` escaping
    guard code is also caught) -- on failure, the runner records the
    guard's name and CONTINUES to the next guard, rather than aborting the
    whole batch. The runner reuses `preuse-write-dispatch.py`'s existing
    `_skipped` breadcrumb list and its
    "[preuse-write-dispatch] write-guard module(s) failed to import and
    were skipped" stderr message (see that file) for this fact -- this
    contract does NOT invent a second breadcrumb surface for the same
    thing; a guard-`main()`-time failure is recorded onto the SAME
    `_skipped` list an import-time failure already populates.

12. LAZY IMPORT IS TWO-STAGE. Each guard declares a cheap, dependency-free
    SCOPE DESCRIPTOR (see `GuardScopeDescriptor` below) that the runner
    evaluates WITHOUT importing the guard's body module; only a match
    against the descriptor triggers the guard's real import. This is
    required, not merely an optimization: guard imports cost a measured
    ~63ms EACH, paid on every edit (hook processes are always cold) -- a
    runner that imports every guard body up front to ask "am I in scope"
    reintroduces that cost for every guard on every edit regardless of
    whether it is ever in scope.

    The descriptor must be import-free and live OUTSIDE the guard's own
    body module, because the naive "defer the whole guard import until the
    payload matches its scope" design is CIRCULAR: the scope predicate
    itself often lives inside the guard module being deferred (e.g.
    `guard-oss-payload-locality.py`'s `is_in_scope` reaches
    `_prompt_surface_locality.is_in_scope`, imported at guard module scope)
    -- importing the guard to ask whether to import the guard defeats the
    lazy-import win entirely.

    REJECTED ALTERNATIVE (recorded so it is not re-proposed): one merged
    guard module with a shared import surface. That design gives back the
    lazy-import win entirely (importing the merged module pays every
    guard's import cost regardless of scope) AND couples four
    independently-owned policies into one file, which this contract
    explicitly does not want.

--------------------------------------------------------------------------
Shared vocabulary
--------------------------------------------------------------------------
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PureWindowsPath
from typing import FrozenSet, Optional, Tuple

TRIPWIRE_TOKEN = "GUARD-ON-RUNNER-CONTRACT"

#: `_message_envelope.py`'s `CHANNEL_STOP` / `CHANNEL_ADDITIONAL_CONTEXT` /
#: `CHANNEL_DENY` constants (NOT re-imported here -- this module stays
#: one). Only CHANNEL_ADDITIONAL_CONTEXT and CHANNEL_DENY are relevant to
#: the PreToolUse write-path runner this contract targets; CHANNEL_STOP is
CHANNEL_ADDITIONAL_CONTEXT = "additional_context"
CHANNEL_DENY = "deny"

#: `MEASURE_ENV_VAR` for the same import-free-module-scope reason as the
MEASURE_ENV_VAR = "COORDINATOR_HOOK_MESSAGE_MEASURE"

FORBIDDEN_OS_EXIT = r"os\._exit"
FORBIDDEN_ATEXIT = r"atexit\."
FORBIDDEN_CHDIR = r"os\.chdir"
#: the existing `_HOOKS_DIR` self-resolution idiom every guard in this
FORBIDDEN_LATE_PATH_INSERT = r"sys\.path\.insert"


@dataclass(frozen=True)
class GuardScopeDescriptor:
    """The cheap, dependency-free scope predicate the runner evaluates
    WITHOUT importing a guard's body module (clause 12, LAZY IMPORT).

    `path_suffixes`: a frozenset of filename suffixes (e.g. `.py`, `.md`)
    the guard cares about; empty means "no suffix restriction" (checked by
    `directory_predicate` alone, if any).

    `directory_substrings`: a tuple of path substrings at least one of
    which must appear in the target path for the guard to be in scope
    (e.g. `("coordinator/hooks/scripts/",)`); empty means "no directory
    restriction" (checked by `path_suffixes` alone, if any).

    `basenames`: a frozenset of exact filename basenames (e.g.
    `{"coordinator.local.md"}`) that match REGARDLESS of directory --
    an OR alternative to the `path_suffixes`+`directory_substrings` pair,
    not a further restriction on it (C1/C3, config-file-class plan). Added
    because the two-field form above cannot express "suffix A confined to
    these dirs, OR suffix B matching anywhere": a repo-root
    `coordinator.local.md` carries no `coordinator/`-prefixed directory
    segment, so it can never satisfy `directory_substrings` however that
    tuple is widened, and widening `directory_substrings` to admit it would
    also admit every OTHER path ending `.md` at any repo root -- a real
    over-match, not the deliberate overapproximation this class already
    accepts elsewhere. `basenames` matching is separator-normalized the
    same way `directory_substrings` is (see `matches()`).

    A descriptor with ALL THREE fields empty is never in scope (matches
    nothing) -- an enrolled guard must declare at least one restriction, or
    its entry is a bug (it would defeat lazy import by always matching).
    """

    guard_module: str
    path_suffixes: FrozenSet[str] = field(default_factory=frozenset)
    directory_substrings: Tuple[str, ...] = ()
    basenames: FrozenSet[str] = field(default_factory=frozenset)

    def matches(self, target_path: Optional[str]) -> bool:
        if not target_path:
            return False
        if not self.path_suffixes and not self.directory_substrings and not self.basenames:
            return False

        if self.basenames:
            normalized_path = PureWindowsPath(target_path).as_posix()
            basename = normalized_path.rsplit("/", 1)[-1]
            if basename in self.basenames:
                return True
            if not self.path_suffixes and not self.directory_substrings:
                return False

        suffix_ok = True
        if self.path_suffixes:
            suffix_ok = any(target_path.endswith(suf) for suf in self.path_suffixes)
        if not suffix_ok:
            return False
        if self.directory_substrings:
            normalized_path = PureWindowsPath(target_path).as_posix()
            return any(sub in normalized_path for sub in self.directory_substrings)
        return True


ENROLLED_GUARD_MODULES: Tuple[str, ...] = (
    "guard-oss-payload-locality.py",
    "nudge-plan-test-surface-tier.py",
    "guard-prompt-surface-citations.py",
    "check-claude-md-size.py",
    "guard-doctrine-changelog-prose.py",
    "guard-test-tree-git-fixture-spawn.py",
    "guard-python-syntax-on-write.py",
    "guard-doctrine-surface-ratio.py",
    "guard-posix-invocation-doctrine-write.py",
    "guard-handoff-summary-cap-on-write.py",
)

#: REAL_GUARD_REGISTRY`, and a descriptor defined only in a test would mean
#: "one home for the enrolment facts" (see `ENROLLED_GUARD_MODULES` above)
#: `_doctrine_changelog_prose.DOCTRINE_MD_DIRS` trees, or a `*.schema.json`
#: file directly inside `DOCTRINE_SCHEMAS_DIR` -- both reachable only by
#: governed trees `DOCTRINE_MD_DIRS`/`DOCTRINE_SCHEMAS_DIR` name -- still a
#: enforce `DOCTRINE_SCHEMAS_DIR`'s "direct children only" restriction), so
#: the LIVE `DOCTRINE_MD_DIRS`/`DOCTRINE_SCHEMAS_DIR` constants, read at
#: guard: `_guard_runner.REAL_GUARD_REGISTRY` (out of this plan's file
DOCTRINE_CHANGELOG_PROSE_SCOPE_DESCRIPTOR = GuardScopeDescriptor(
    guard_module="guard-doctrine-changelog-prose.py",
    path_suffixes=frozenset({".md", ".schema.json"}),
    directory_substrings=(
        "coordinator/skills/",
        "coordinator/agents/",
        "coordinator/commands/",
        "coordinator/snippets/",
        "coordinator/docs/wiki/",
        "coordinator/schemas/",
    ),
    basenames=frozenset({"coordinator.local.md"}),
)


#: `DOCTRINE_CHANGELOG_PROSE_SCOPE_DESCRIPTOR` above does (contract clause
#: needs that module's `DOCTRINE_MD_DIRS` constant, and building the
#: `_doctrine_changelog_prose.DOCTRINE_MD_DIRS` trees (`.schema.json` is
GUARD_DOCTRINE_SURFACE_RATIO_SCOPE_DESCRIPTOR = GuardScopeDescriptor(
    guard_module="guard-doctrine-surface-ratio.py",
    path_suffixes=frozenset({".md"}),
    directory_substrings=(
        "coordinator/skills/",
        "coordinator/agents/",
        "coordinator/commands/",
        "coordinator/snippets/",
        "coordinator/docs/wiki/",
    ),
)


#: `check-claude-md-size.py`'s `GuardScopeDescriptor` -- ORIGINALLY defined
#: identical reason `DOCTRINE_CHANGELOG_PROSE_SCOPE_DESCRIPTOR` above lives
#: REAL_GUARD_REGISTRY` is a module-level tuple built at `_guard_runner.py`
#: GOVERNED_AUTHORING_SURFACES` -- `global-doctrine/CLAUDE.md`, `CLAUDE.md`,
#: hypothetical `MY-CLAUDE.md`, the safe direction) -- can never under
#: `_claude_md_ledger.GOVERNED_AUTHORING_SURFACES` constant, read at test
#: `_guard_runner.REAL_GUARD_REGISTRY`'s entry for this guard uses
CHECK_CLAUDE_MD_SIZE_SCOPE_DESCRIPTOR = GuardScopeDescriptor(
    guard_module="check-claude-md-size.py",
    path_suffixes=frozenset(
        {"CLAUDE.md", "em-operating-doctrine.md", "agent-role-dispatched.md"}
    ),
)
