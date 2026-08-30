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

#: Greppable registry token for this contract, registered in
#: coordinator/docs/wiki/coordinator-tripwires.md in the same commit as
#: this module. Grep this exact token to find the tripwire entry.
TRIPWIRE_TOKEN = "GUARD-ON-RUNNER-CONTRACT"

#: The channel names a guard's verdict is expressed in, mirrored from
#: `_message_envelope.py`'s `CHANNEL_STOP` / `CHANNEL_ADDITIONAL_CONTEXT` /
#: `CHANNEL_DENY` constants (NOT re-imported here -- this module stays
#: import-free at module scope beyond the standard library; a guard or the
#: runner cross-checks these string values against `_message_envelope`'s
#: own constants at the call site instead of this module importing that
#: one). Only CHANNEL_ADDITIONAL_CONTEXT and CHANNEL_DENY are relevant to
#: the PreToolUse write-path runner this contract targets; CHANNEL_STOP is
#: a Stop-family shape out of scope here.
CHANNEL_ADDITIONAL_CONTEXT = "additional_context"
CHANNEL_DENY = "deny"

#: Environment variable that puts a guard's own `_message_envelope.emit()`
#: call into measurement mode -- mirrored from `_message_envelope.py`'s
#: `MEASURE_ENV_VAR` for the same import-free-module-scope reason as the
#: channel constants above. Per clause 9, the runner does NOT special-case
#: this variable: measurement mode is standalone-invocation-only.
MEASURE_ENV_VAR = "COORDINATOR_HOOK_MESSAGE_MEASURE"

#: Forbidden-construct grep patterns the conformance test
#: (coordinator/tests/test_guard_runner_contract.py) applies to every
#: enrolled guard's source text, per clauses 2-4 and 8. Each value is a
#: plain substring/regex fragment, not a compiled pattern -- kept as
#: strings here so this module stays import-free beyond stdlib (no `re`
#: dependency at module scope); the test compiles them itself.
FORBIDDEN_OS_EXIT = r"os\._exit"
FORBIDDEN_ATEXIT = r"atexit\."
FORBIDDEN_CHDIR = r"os\.chdir"
#: A `sys.path.insert` occurring AFTER the module's own import block is
#: forbidden (clause 8); one at TOP of a module, before other imports, is
#: the existing `_HOOKS_DIR` self-resolution idiom every guard in this
#: directory already uses and is exempt -- the conformance test locates
#: the import block's end and only flags a later occurrence.
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
        """Pure, import-free scope check. `target_path` is the raw
        (possibly `None`) path string extracted from the hook payload --
        this function does no filesystem I/O and imports nothing beyond
        what this module already imports at the top.

        `directory_substrings` are declared forward-slash-only (e.g.
        `"setup/"`), but `target_path` is a raw payload string that on
        Windows is backslash-separated (`...templates\\setup\\...`) -- a
        bare `in` check against the declared substring silently
        under-matched every Windows call, which is how a real Windows
        write to an in-scope directory produced a false "out of scope"
        and the guard never fired. Normalized to forward slashes for the
        directory-substring check only (host-neutral: a no-op on a POSIX
        path, which already uses `/`); `path_suffixes` needs no such
        normalization since `endswith` on a filename suffix does not
        depend on the separator.

        `basenames`, when declared, is checked FIRST and independently: a
        match there returns `True` immediately, regardless of
        `path_suffixes`/`directory_substrings` -- an OR, not an AND, with
        the suffix+directory pair (see the class docstring for why the
        existing two-field form cannot express this). The basename is
        extracted from the same separator-normalized path the
        directory-substring check uses, so a `coordinator.local.md` target
        matches on both POSIX and backslash-separated Windows payload
        strings.

        Residual, unclosed by this or any separator-normalization scheme:
        `PureWindowsPath` parses `\\` as a separator unconditionally, on
        every host, so a POSIX path whose leaf genuinely contains a literal
        backslash character (legal, if unusual, on POSIX) is still mangled
        here -- exactly as the bare `.replace("\\", "/")` this replaced
        was. This function does not claim to close that case; it only fixes
        the Windows-payload under-match described above.
        """
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


#: The enrolment list this contract's conformance test sources its guard
#: corpus from -- ONE home for the list (clause-adjacent housekeeping
#: named directly in the C1a chunk body: "source the enrolment list from
#: the contract module's own constant, not a hardcoded literal in the
#: test"). Filenames only (no directory prefix) -- each is a sibling of
#: this module under coordinator/hooks/scripts/. C2 registers three of
#: these guards onto the runner; this module states the contract they must
#: conform to, and the conformance test below enrolls exactly this set.
#: check-claude-md-size.py is included per C1a's own enumeration even
#: though its runner migration (protocol translation, not just residency)
#: is C3's separate concern -- the *contract clauses that apply to any
#: source file* (clauses 2-4, 8) still apply to it today.
#: guard-doctrine-changelog-prose.py (`6ae4b9391`) arrived AFTER this
#: plan's Port ledger was derived, as a fifth write-path `PreToolUse`
#: guard -- added here by C3b so its grep-conformance legs (clauses 2-4, 8)
#: run alongside the other four, and so C4 can enumerate a complete
#: enrolment set when it removes `hooks.json`'s residual registrations.
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

#: `guard-doctrine-changelog-prose.py`'s `GuardScopeDescriptor` (C3b). Lives
#: HERE, not in the guard's own body module (its real scope predicate,
#: `_doctrine_changelog_prose.is_in_scope`, needs `_doctrine_changelog_prose`
#: module constants -- importing that to build the descriptor would defeat
#: clause 12's whole point), and not in a test file either -- the three
#: C2-enrolled guards keep their descriptors in `_guard_runner.
#: REAL_GUARD_REGISTRY`, and a descriptor defined only in a test would mean
#: whoever wires the registry has to hand-copy a literal out of test code:
#: a mistyped or narrowed copy under-matches, the guard silently stops
#: firing, and every test still passes -- exactly the failure mode this
#: chunk's ordering discipline exists to prevent. This module is already
#: "one home for the enrolment facts" (see `ENROLLED_GUARD_MODULES` above)
#: and is import-free by construction, so it is the shared object: the test
#: that verifies it and the registry entry that (eventually, in C4) wires
#: it both import THIS constant, never a copy of it.
#: The guard's REAL scope is a `.md` file under one of five fixed
#: `_doctrine_changelog_prose.DOCTRINE_MD_DIRS` trees, or a `*.schema.json`
#: file directly inside `DOCTRINE_SCHEMAS_DIR` -- both reachable only by
#: importing that module, exactly the cost this descriptor exists to defer.
#: A bare `.md` suffix (the first-draft shape the `check-claude-md-size`
#: review found too wide) would match nearly every markdown write in a repo
#: that is mostly markdown, so this descriptor instead pairs
#: `path_suffixes` with `directory_substrings` built from the same six
#: governed trees `DOCTRINE_MD_DIRS`/`DOCTRINE_SCHEMAS_DIR` name -- still a
#: strict superset (it does not additionally exclude the
#: `tests/`/`fixtures/` subdirectory carve-out `is_in_scope` applies, nor
#: enforce `DOCTRINE_SCHEMAS_DIR`'s "direct children only" restriction), so
#: it can never under-match, at the cost of over-matching a handful of
#: paths the real predicate would reject once imported. Verified against
#: the LIVE `DOCTRINE_MD_DIRS`/`DOCTRINE_SCHEMAS_DIR` constants, read at
#: test time, by `coordinator/tests/test_inprocess_guard_runner.py::
#: test_changelog_prose_scope_descriptor_never_under_matches` -- not a
#: hardcoded path list, so a sixth governed tree added to either constant
#: fails that test loud instead of this descriptor silently ceasing to
#: fire on it.
#:
#: C3 (config-file-class plan): the guard also now governs a THIRD, disjoint
#: shape -- a repo-root `coordinator.local.md`, which carries no
#: `coordinator/`-prefixed directory segment and so can never satisfy
#: `directory_substrings` above however that tuple is widened (that AND
#: relationship, and why appending to `directory_substrings` is the wrong
#: fix, is `GuardScopeDescriptor.matches()`'s own docstring). Expressed via
#: the new `basenames` field rather than a second registry entry for this
#: guard: `_guard_runner.REAL_GUARD_REGISTRY` (out of this plan's file
#: scope) wires exactly ONE descriptor per `RegisteredGuard`, so a second
#: descriptor object would need a second registry entry the C1a/C3b
#: ordering discipline this contract documents does not provide a seam
#: for -- widening the one descriptor object already referenced there is
#: the change that reaches the runner without touching it.
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


#: `guard-doctrine-surface-ratio.py`'s `GuardScopeDescriptor` (C8,
#: docs/plans/2026-08-13-doctrinal-surface-weight-ratchet.md). Lives HERE,
#: not in the guard's own body module, for the identical reason
#: `DOCTRINE_CHANGELOG_PROSE_SCOPE_DESCRIPTOR` above does (contract clause
#: 12, "import-free and live OUTSIDE the guard's own body module") -- the
#: guard's real scope predicate, `_doctrine_changelog_prose.surface_of`,
#: needs that module's `DOCTRINE_MD_DIRS` constant, and building the
#: descriptor from it would defeat clause 12's lazy-import point.
#: The guard's REAL scope is a `.md` file under one of the five
#: `_doctrine_changelog_prose.DOCTRINE_MD_DIRS` trees (`.schema.json` is
#: NOT one of the five measured surfaces this guard prices, unlike the
#: changelog-prose guard's own scope, so it is deliberately absent from
#: `path_suffixes` here). This descriptor pairs `path_suffixes` with
#: `directory_substrings` built from the same five governed trees -- a
#: strict superset of `surface_of`'s real predicate (it does not
#: additionally exclude the `tests`/`fixtures` subdirectory carve-out
#: `surface_of` applies), so it can never under-match, at the cost of
#: over-matching a handful of paths the real predicate would reject once
#: imported.
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
#: inside that guard's own body module (C3), relocated HERE by C4 for the
#: identical reason `DOCTRINE_CHANGELOG_PROSE_SCOPE_DESCRIPTOR` above lives
#: here rather than in `guard-doctrine-changelog-prose.py`: `_guard_runner.
#: REAL_GUARD_REGISTRY` is a module-level tuple built at `_guard_runner.py`
#: IMPORT time -- which happens on every edit, before any scope match runs.
#: A descriptor referenced there but DEFINED inside the guard's own body
#: module would force THIS module to import that whole guard on every
#: single edit just to read its descriptor, regardless of whether the edit
#: is anywhere near a governed CLAUDE.md -- exactly the cost clause 12
#: exists to defer, reintroduced through the back door of registry
#: construction rather than through the descriptor's own match logic.
#: The guard's REAL scope is the UNION of two independent predicates,
#: neither reachable without importing what this descriptor exists to
#: defer: the SIZE-budget check (`coordinator_core.claude_md_budget.
#: is_governed_claude_md` -- basename `CLAUDE.md` at exactly two locations,
#: `~/.claude/CLAUDE.md` and a dev-repo-sentinel-marked `coordinator/
#: CLAUDE.md`) and the C7 admission-gate check (`_claude_md_ledger.
#: GOVERNED_AUTHORING_SURFACES` -- `global-doctrine/CLAUDE.md`, `CLAUDE.md`,
#: `coordinator/snippets/em-operating-doctrine.md`,
#: `coordinator/snippets/agent-role-dispatched.md`). Every one of those six
#: concrete paths ends with exactly one of THREE basenames -- `CLAUDE.md`,
#: `em-operating-doctrine.md`, `agent-role-dispatched.md` -- the tightest
#: sound superset available without importing either predicate's machinery
#: (a bare `.md` suffix, this descriptor's own first draft, matched nearly
#: every markdown write in a repo that is mostly markdown and was tightened
#: after review). Still a strict `endswith` superset (it also matches a
#: hypothetical `MY-CLAUDE.md`, the safe direction) -- can never under
#: -match, at the cost of over-matching a handful of paths the real
#: predicates would reject once imported. Verified against the LIVE
#: `_claude_md_ledger.GOVERNED_AUTHORING_SURFACES` constant, read at test
#: time, by `coordinator/tests/test_check_claude_md_size_runner_fold.py::
#: test_scope_descriptor_never_under_matches_governed_surfaces` -- not a
#: hardcoded path list, so a fifth governed surface with a fourth basename
#: fails that test loud instead of this descriptor silently ceasing to
#: fire on it.
#: This guard's verdict travels via captured STDERR, not the stdout-JSON
#: envelope the other four enrolled guards use (`check-claude-md-size.py`'s
#: own `verdict_from_exit`/`run_via_runner`, per the C3 PM ruling) --
#: `_guard_runner.REAL_GUARD_REGISTRY`'s entry for this guard uses
#: `RegisteredGuard.verdict_attr="run_via_runner"` rather than the generic
#: `entry_attr="main"` + `_invoke_guard_main` path the other four use, so
#: this descriptor's match still gates a real import, but the CALL it gates
#: is different -- see `RegisteredGuard`'s own docstring for that seam.
CHECK_CLAUDE_MD_SIZE_SCOPE_DESCRIPTOR = GuardScopeDescriptor(
    guard_module="check-claude-md-size.py",
    path_suffixes=frozenset(
        {"CLAUDE.md", "em-operating-doctrine.md", "agent-role-dispatched.md"}
    ),
)
