"""coordinator/lib/percolate/assembled_mirror_gate.py — gate: the ASSEMBLED
published mirror (the union of every row that composes it) must reach a
verdict on its own documented fast-tier command.

## The defect this closes

`pytest -m 'not cadence and not pending_fix and not designed_red'
--collect-only -q`, run from a fresh clone of the published mirror, aborted
with "Interrupted: 8 errors during collection" — zero tests ran, so
`/coordinator:validate` (which resolves its command from `fast_test_cmd`)
could never return a pass on that clone. `coordinator/lib/percolate/
import_closure.py` (C1, same plan) is a PER-ROW gate: it proves each row's
own restricted tree resolves its own `coordinator_core` imports. Nine rows
compose the published mirror, each closed within itself while their union
is not — classes 2 (a dropped registry entry) and 3 (a dropped data file)
are invisible to import analysis at any depth, on any row. This gate does
not analyse imports; it runs the actual, documented command against the
actual assembled tree, so it is blind to none of the three orphan classes
the parent plan enumerates.

Spec: docs/plans/2026-08-28-a-dropped-module-must-not-leave-its-test-behind.md
chunk C2.

## BLOCKING PRECONDITION discharged: (i), POST-SYNC bytes — never pre-sync

The parent plan's C2 body requires this module to pick, explicitly, between
running the check on POST-SYNC bytes (i) or demonstrating that the identity
transform (`claude-klabauter`/`claude_klabauter` -> `claude_klabauter`) cannot change
import resolution (ii) — and forbids abstaining.

(ii) is not available. `coordinator_core/percolate/substitute.py`'s own
module docstring documents a whole-file, `tokenize`-based, `.py`-aware
identifier-context pass that exists SPECIFICALLY so a content rewrite can
land inside Python source without producing a `SyntaxError` at the call
site the rewritten line becomes source for. A mechanism built to rewrite
identifiers inside `.py` files without breaking their syntax is, by
construction, a mechanism that can rewrite a token appearing inside an
`import X` / `from X import Y` statement — exactly the shape the parent
plan's option (ii) names as a falsifier ("a rename that touches a module
path or a `from X import` target falsifies this"). This is a measurement
over the transform's own rule set (its docstring's stated purpose), not an
argument that the transform "only touches strings".

Therefore: this module's entry point, `run_assembled_mirror_gate`, MUST be
invoked with `tree_root` pointing at the destination tree AFTER
`sync_mirror`/`sync_flat_mirror` has both copied files and applied the
row's copy-time content transform — never at the pre-sync restricted tree
`build_allowlisted_source` produces. A caller that points `tree_root` at
pre-sync bytes is answering a materially easier question than the one the
parent plan's prime exit criterion asks, and this module has no way to
detect that misuse from inside `tree_root` alone — the wiring caller owns
that precondition. (Recorded here, per the parent plan's instruction to
name the choice in this chunk's commit message: BLOCKING PRECONDITION
discharged as (i).)

## Scope

This module owns MECHANISM only: build the subprocess invocation, clear
`PYTHONPATH` and set `cwd=tree_root` on it, verify `tree_root` actually
carries the package directory that isolation relies on before trusting the
run, run it, and parse its own reported collected-count / error shape. It
does not decide WHEN in the publish pipeline to call
`run_assembled_mirror_gate`, and does not itself read `setup/publish-
allowlist-declarations.yaml` or any exemption ledger — that wiring is
`coordinator/bin/publish.py`'s job (C3, same plan, not this chunk).

## The third verdict: NOT-APPLICABLE

`_verify_isolation_precondition` reads one bit off `tree_root`'s contents —
whether a `coordinator_core/` directory is there. That bit reads identically
for two different destinations: one that structurally never carries the
engine (this gate has nothing to say about it, by construction) and one
that is SUPPOSED to carry the engine but whose sync silently dropped it this
round (the exact truncated-mirror defect this gate exists to catch). Absence
alone cannot tell those apart, and this module — MECHANISM ONLY, per
`## Scope` above — is forbidden from reading `setup/publish-targets.
portable` or any ledger to tell them apart itself.

So the caller (`publish.py`'s `dispatch_end_of_run_assembled_mirror_gate`)
resolves the discriminator — is `coordinator_core` part of this
destination's DECLARED scope, read from the UNFILTERED target row set, never
from `tree_root`'s own contents (circular) and never from the current
invocation's possibly `--target`-filtered row subset (narrow-door regression,
see `docs/plans/2026-08-31-the-mirror-gate-collects-the-whole-tree.md`) —
and passes the answer in as `run_assembled_mirror_gate`'s
`coordinator_core_in_declared_scope` keyword. This module accepts that fact;
it does not compute it.

Only when BOTH agree — the tree lacks the directory AND the destination's
declared scope never claimed it — does this function return
`not_applicable=True`. Declared-scope-includes-it-but-tree-lacks-it keeps
refusing via the pre-existing `isolation_unverified` path, unchanged: NOT-
APPLICABLE never absolves a truncated engine mirror.

## What "isolated from claude-klabauter" actually means here (measured 2026-08-29)

This module does NOT run the child in a separate interpreter and does NOT
prevent it from resolving `coordinator_core` via claude-klabauter's own editable
install. What it enforces directly: `PYTHONPATH` is cleared
(`_subprocess_env`) and `cwd` is set to `tree_root`. What it RELIES ON:
Python's own import-path ordering puts `sys.path[0]` (derived from `cwd`
for a `-m pytest` invocation) ahead of any same-named distribution an
ambient interpreter has installed — including claude-klabauter's own
`coordinator_core`, which IS `pip install -e`'d into the default
interpreter this module runs under (`__editable__.coordinator_core-
0.1.0.pth` maps it to the claude-klabauter repo root's own `coordinator_core/`
directory). Measured with
`cwd` at a fresh clone of the published mirror: `sys.path[0]` is `''`, cwd
precedes the editable finder, and `coordinator_core` resolves to the
CLONE's own copy — so a module missing from the mirror is not silently
supplied by claude-klabauter.

That reliance is INCIDENTAL to the tree, not enforced by this module,
unless checked: it holds only because the tree happens to carry a
`coordinator_core/` directory at its root for cwd to shadow the ambient
install with. A tree that does not carry that directory (or a box running
more editable installs of the same package name) would get a different
answer with no signal that isolation had quietly stopped applying — the
exact abstention this whole plan exists to kill. `_verify_isolation_
precondition` below turns that reliance into a checked precondition:
absent, this function refuses rather than running an unverified subprocess.

Negative spec: never runs the full suite. `--collect-only` answers the
prime exit criterion; execution does not (parent plan Anti-scope, "Do not
run the full suite to check this").

## C6: `find_modules_missing_tests` — the inverse gap, WARN-shaped

`run_assembled_mirror_gate` above answers "does the tree collect", and is
blind to a shipped module whose test silently did not ship alongside it
(measured 2026-08-28: a fix published while its two new test files did
not) — tests participate in no import closure, so neither the deny-list
filter nor C1's closure gate can see the absence. `find_modules_missing_
tests` walks the assembled tree AND the source tree it was assembled
from, and reports only the subjects whose test exists in the source but
did not ship — a module that never had a test anywhere is not reported
(comparing the mirror against itself, as an earlier version of this
function did, conflated the two and made the WARN print ~80% of the
tree on every round). WARN, never refuse: this remains a WARN even
though the reported set should now normally be zero. See that function's
own docstring for the matching rule and `format_test_coverage_warning`
for the denominator-carrying, capped render.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

_NESTED_ENV_SCRUB_SOURCE = (
    Path(__file__).resolve().parents[2] / "bin" / "tests" / "test_zero_test_module_ratchet.py"
)
"""This module already spawns pytest as a nested subprocess and already
solved scrubbing the outer run's own pytest env vars out of that child's
environment (`_NESTED_PYTEST_ENV_SCRUB`) — a peer's `PYTEST_ADDOPTS`
turning xdist worker death under memory pressure into a partial-collection
summary this gate would otherwise misread as a tree defect. Reused by
file-path import (this file lives outside any package `bin/` or `bin/tests`
participates in from here) rather than duplicated into a second list that
could drift from the one actually exercised by that suite."""


def _load_nested_pytest_env_scrub() -> "tuple[str, ...]":
    spec = importlib.util.spec_from_file_location(
        "_zero_test_module_ratchet_env_scrub", _NESTED_ENV_SCRUB_SOURCE
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"could not build a module spec for {_NESTED_ENV_SCRUB_SOURCE}")
    module = importlib.util.module_from_spec(spec)
    # That module imports from `coordinator_core`, so executing it requires
    # the repo root on `sys.path`. Under pytest the rootdir supplies it and
    # this is invisible; a caller importing THIS module standalone (the
    # exit-criterion falsifier does exactly that) gets a ModuleNotFoundError
    # from a line that reads like a pure constant lookup. The reuse is
    # deliberate -- one scrub list, not two that drift -- but reuse across a
    # package boundary owes its own import precondition rather than
    # inheriting one by luck.
    repo_root = str(_NESTED_ENV_SCRUB_SOURCE.parents[3])
    added = repo_root not in sys.path
    if added:
        sys.path.insert(0, repo_root)
    try:
        spec.loader.exec_module(module)
    finally:
        if added:
            sys.path.remove(repo_root)
    return module._NESTED_PYTEST_ENV_SCRUB


_PYTEST_ENV_SCRUB = _load_nested_pytest_env_scrub()

MARKER_EXPRESSION = "not cadence and not pending_fix and not designed_red"
"""The tree's own documented fast-tier marker expression (parent plan's
prime exit criterion, verbatim) — never widened or narrowed here; a tree
that changes its own marker vocabulary changes what this gate runs, not
the other way around."""

DEFAULT_TIMEOUT_S = 60.0
"""Parent plan's own budget note: "one pytest collection per publish, not
per op ... If it exceeds ~60s, run C1 first and escalate to the full
collection only when C1 is clean". This module DOES enforce this number as
a literal `subprocess.run(..., timeout=timeout_s)` value — a run that
exceeds it is killed and reported as `timed_out=True`. What this module
does NOT enforce is the ESCALATION that number is meant to signal ("run C1
first"): that decision belongs to the wiring caller (C3), which sees
`timed_out=True` and decides whether to escalate. The default here is the
same number so a caller that does not override `timeout_s` inherits the
documented budget rather than an arbitrary one."""

_NO_CONSOLE = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
# See coordinator/lib/percolate/publish_sync.py's identical constant for the
# rationale: a console-subsystem child with no console of its own opens a
# visible window on Windows; every subprocess this module spawns is
# short-lived and output-captured. 0 on POSIX, where the flag does not exist.

_COLLECTED_COUNT_RE = re.compile(r"(\d+)(?:/\d+)?\s+tests?\s+collected\b")
_ERROR_TAIL_RE = re.compile(r"\berror(?:s)?\b", re.IGNORECASE)
_INTERRUPTED_RE = re.compile(r"\binterrupted\b", re.IGNORECASE)
_NO_TESTS_RE = re.compile(r"\bno tests (?:ran|collected)\b", re.IGNORECASE)

_SUMMARY_ERROR_CLAUSE_RE = re.compile(r",\s*\d+\s+errors?\b", re.IGNORECASE)
"""The `, N errors` clause pytest appends to its own collection summary line.
Anchored on the comma-and-count shape, never a bare `error` substring: that
line's tally is pytest's own verdict on the collection, and a gate that reads
it as prose reports the tree it just refused as clean."""


@dataclass(frozen=True)
class MirrorCollectionResult:
    """The verdict `run_assembled_mirror_gate` reaches. `passed` is the sole
    field a caller needs to decide refuse-vs-proceed; everything else is
    for the refusal message / diagnostics.

    `collected_count` and `errored` are reported SEPARATELY and must never
    be collapsed into one number — the parent plan is explicit: "A
    collection that errors and one that finds nothing must not read
    alike." `collected_count == 0, errored == False` (marker deselected
    everything, or the tree genuinely has no tests) reads differently from
    `collected_count == 0, errored == True` (collection was interrupted
    before it could report a count at all) — both are `passed == False`
    (any non-zero exit refuses, per the parent plan body), but a refusal
    message built from this result can and must say which happened.

    `errored == True` does NOT imply `collected_count == 0`. pytest's
    partial-collection summary carries both a count and an error tally on
    one line ("22938/39613 tests collected (16675 deselected), 5 errors"):
    22938 files did collect and 5 did not, and the count is the honest
    denominator for the errors rather than evidence against them. Reading
    that shape as a clean collection is the defect
    `_SUMMARY_ERROR_CLAUSE_RE` exists to close.
    """

    passed: bool
    collected_count: int
    errored: bool
    exit_code: "int | None"
    timed_out: bool
    elapsed_s: float
    command: tuple[str, ...]
    tree_root: str
    stdout_tail: str
    stderr_tail: str
    isolation_unverified: bool = False
    """True only when `run_assembled_mirror_gate` refused BEFORE spawning a
    subprocess because `_verify_isolation_precondition` found `tree_root`
    missing the `coordinator_core/` directory its cwd-shadowing isolation
    relies on — see that function's own docstring. `passed` is always
    False alongside this; no subprocess ran, so `exit_code` is None and
    `collected_count`/`errored` carry the same fail-closed values a
    `TimeoutExpired` reports.

    Mutually exclusive with `not_applicable` below: both are reached from
    the SAME `_verify_isolation_precondition` failure, but the caller's
    `coordinator_core_in_declared_scope` argument decides which one — never
    both, and never this one without a subprocess having been skipped."""

    not_applicable: bool = False
    """True only when `run_assembled_mirror_gate` was told (via its
    `coordinator_core_in_declared_scope` argument) that `coordinator_core`
    is NOT part of this destination's DECLARED scope, and
    `_verify_isolation_precondition` independently found it absent from
    `tree_root` too — the two facts agreeing that this gate structurally
    has nothing to say about this tree, by construction, rather than by an
    unmet-but-expected precondition. No subprocess ran; `passed` is False
    alongside this the same way it is for `isolation_unverified`, but a
    caller MUST read `not_applicable` before `passed` — this is not a
    refusal (see `dispatch_end_of_run_assembled_mirror_gate` in
    `publish.py`, which proceeds the round rather than gating on it).

    Deliberately excluded from `is_incomplete`/`is_load_indeterminate`
    below: those predicates answer "does this result carry a claim worth
    an operator's exemption", and a structurally-inapplicable tree carries
    no claim to exempt — there is nothing here for a declared exemption to
    waive, the same way there is nothing for it to waive on a clean PASS.
    A caller that reaches this field via `is_incomplete=False` would
    otherwise misread it as a clean CONTENT verdict claiming "found 0
    tests" (see `verdict_obtained`'s own docstring for why that collapse is
    exactly the one this whole result shape exists to keep apart) — reading
    `not_applicable` first, before either `passed` or `is_incomplete`, is
    how a caller keeps the three cases (result / INCOMPLETE / NOT-
    APPLICABLE) distinguishable. See this module's own docstring, "The
    third verdict", for the caller-side discriminator that produces this
    field's argument in the first place: whether `coordinator_core` sits in
    the destination's DECLARED scope, read from the UNFILTERED target row
    set — never from `tree_root`'s contents (that would be circular, since
    `_verify_isolation_precondition` already reads `tree_root`'s contents)
    and never from the current invocation's possibly `--target`-filtered
    row subset (a single non-engine row filtered in against an
    engine-declaring destination must still refuse, not read as
    not-applicable — see `docs/plans/2026-08-31-the-mirror-gate-collects-
    the-whole-tree.md`'s narrow-door regression)."""

    timeout_s: float = DEFAULT_TIMEOUT_S
    """The budget actually enforced for the run that produced this result —
    i.e. the `timeout_s` value passed to `run_assembled_mirror_gate`, never
    the module default read cold. `format_refusal`'s TIMED OUT and
    INCOMPLETE renderings read this field, not `DEFAULT_TIMEOUT_S`, so a
    caller overriding the budget gets a refusal naming the number that was
    actually enforced rather than one that was never in effect."""

    verdict_obtained: bool = False
    """True only where `run_assembled_mirror_gate` positively established
    that a CONTENT verdict about the tree WAS reached — a recognised
    `_parse_collection_summary` shape from a child that exited on its own.
    Set False for: empty or unrecognised stdout (a pytest child killed
    without writing a recognisable summary — memory pressure, an
    OS/job-object kill, a plugin segfault), a negative `returncode` even
    alongside stdout that happens to parse (signal death means the run
    never finished on its own), a spawn `OSError`, a timeout, and the
    isolation refusal.

    THE DEFAULT IS FALSE, AND THE DIRECTION IS THE WHOLE POINT. It was
    True on landing, reasoned as backwards compatibility: a fixture that
    had never heard of this field would keep the `is_incomplete` reading
    the old `timed_out or isolation_unverified` gave it. That is the wrong
    axis for a fail-closed gate. A default of True makes OMISSION an
    ASSERTION that a verdict was obtained, so a future construction site
    that forgets this field reads as a clean CONTENT verdict — which a
    declared exemption may then waive, which is precisely the shape
    `is_incomplete` was widened to close, reintroduced through a default
    instead of through an enumeration. False costs a content site one
    explicit keyword and costs a forgetful one nothing but a refusal.
    Note the sibling `isolation_unverified: bool = False` already defaults
    the safe way; this now matches it. See `is_incomplete` for why this
    must feed the predicate rather than be enumerated as a third named
    cause, and `is_load_indeterminate` for why a forgotten flag here would
    have been exemptible."""

    @property
    def is_incomplete(self) -> bool:
        """True iff this result carries NO claim about the tree's content at
        all — the predicate is "was a verdict obtained", never an
        enumeration of the causes that can produce one. `timed_out` and
        `isolation_unverified` are two SPECIFIC named causes; `verdict_
        obtained=False` is the general case, covering every other way a
        subprocess can exit without reaching a recognised CONTENT verdict
        (a pytest child killed without writing a summary, a signal-killed
        child, a `subprocess.OSError` from process creation itself). Prior
        to this field, this property was `timed_out or isolation_
        unverified` — an enumeration of two known causes that a killed
        child with empty stdout satisfied neither of, so it silently read
        as a clean CONTENT verdict a declared exemption could then waive.
        Distinct from `errored`: a collection that ran to completion,
        parsed, and reported collection errors DID reach a verdict about
        the tree (a bad one) and is a CONTENT result, `is_incomplete
        =False`. An INCOMPLETE result must never be treated as evidence
        about the tree by any caller.

        NOT the predicate a caller should gate an exemption lookup on —
        see `is_load_indeterminate` for that, and its docstring for why the
        two came apart.

        Excludes `not_applicable`: that field marks a tree this gate has
        NOTHING to say about, by construction (see its own docstring) —
        distinct from a tree this gate tried and failed to reach a verdict
        on. A caller checking `is_incomplete` after already reading
        `not_applicable` (as `dispatch_end_of_run_assembled_mirror_gate`
        does) never observes the two overlap, but this predicate is kept
        correct standalone regardless of call order."""
        return (
            not self.not_applicable
            and (self.timed_out or self.isolation_unverified or not self.verdict_obtained)
        )

    @property
    def is_load_indeterminate(self) -> bool:
        """True iff this result reached no content verdict for a reason that
        is a function of the BOX rather than of the tree — the subset of
        `is_incomplete` a declared exemption can never legitimately waive.

        `dispatch_end_of_run_assembled_mirror_gate` gates its exemption
        lookup on THIS, not on `is_incomplete`. The two are not the same
        predicate and conflating them closed a real publish lane:
        `isolation_unverified` is a pure function of `tree_root`'s
        contents (`_verify_isolation_precondition` asks whether a
        `coordinator_core/` directory is there, and asks nothing else), so
        it is deterministic, load-independent, and reproducible — a mirror
        that structurally never carries the engine refuses this way on
        every round, on an idle box, forever. That is exactly the standing,
        named tradeoff the exemption ledger exists to let an operator
        declare. A timeout is the opposite: it says nothing about the tree,
        it says the box was busy, and waiving it would let load reach the
        verdict — the prime exit criterion's own negation
        (`docs/plans/2026-08-31-the-mirror-gate-collects-the-whole-tree.md`).

        Defined as a subtraction rather than an enumeration, so every
        further no-verdict cause added to `is_incomplete` is
        non-exemptible by default and only a deliberate edit here can make
        one waivable."""
        return self.is_incomplete and not self.isolation_unverified


def _tail(text: str, n_lines: int = 40) -> str:
    lines = text.splitlines()
    return "\n".join(lines[-n_lines:])


def _parse_collection_summary(stdout: str) -> "tuple[int, bool, bool]":
    """Return `(collected_count, errored, recognized)` parsed from pytest's
    `-q --collect-only` stdout. `errored` is True whenever the summary reads
    as an interrupted/erroring collection rather than a clean (possibly
    zero-result) one — see `MirrorCollectionResult`'s own docstring for why
    the two zero-count shapes must stay distinguishable. `recognized` is
    True only when `stdout` matched one of the summary shapes this function
    actually understands (a collected-count line, an interrupted/error
    tail line, or a "no tests" tail line); empty stdout and any OTHER
    unrecognised shape set `recognized=False` — the caller (`run_assembled_
    mirror_gate`) reads that as NO CONTENT VERDICT was obtained (`is_
    incomplete=True`), never as a claim that the tree is bad. A pytest
    child killed without writing a summary (memory pressure, an OS/job-
    object kill, a plugin segfault) produces exactly this shape: empty
    stdout used to collapse into the same `errored=True` a genuine
    collection error produces, which let a declared exemption waive a run
    that never reached a verdict at all.

    Deliberately still over-collects into `errored=True` (alongside
    `recognized=False`) on any summary shape this function does not
    recognise: this feeds a publish refusal gate, and misreading a genuine
    collection error as a clean empty collection is the dangerous
    direction, not the reverse (same asymmetry `import_closure.py`'s
    `_unguarded_import_nodes` documents for its own guard/unguarded
    split). `errored=True, recognized=False` still refuses via `passed`;
    it now ALSO refuses as INCOMPLETE via `is_incomplete`, rather than
    being read as a bad-tree CONTENT verdict an exemption ledger could
    waive.

    Ordering dependency: the "N tests collected" match is checked BEFORE
    the tail-line error/interrupted check, which is only safe because this
    module's own `run_assembled_mirror_gate` never passes
    `--continue-on-collection-errors` to pytest. Without that flag, pytest
    aborts collection on the first error before ever printing a partial
    "N tests collected" summary line — so a collected-count match, when one
    occurs, cannot itself be masking an in-progress error the tail-line
    check would otherwise have caught. If this module ever adds that flag
    (or any flag that lets pytest print a count alongside an error it
    doesn't also embed in the same summary line via `_SUMMARY_ERROR_CLAUSE_
    RE`), this ordering must be re-verified against a real partial-
    collection run, not assumed."""
    stripped = stdout.rstrip()
    if not stripped:
        return 0, True, False
    tail_line = stripped.splitlines()[-1]

    m = _COLLECTED_COUNT_RE.search(stdout)
    if m:
        # A recognised "N (of M) tests collected" summary line wins over the
        # word "error" appearing anywhere ELSE in the body (e.g. a deselected
        # test's id containing "error_handling") -- but never over an error
        # clause pytest wrote into that same summary line. pytest reports a
        # partial collection as "22938/39613 tests collected (16675
        # deselected), 5 errors in 11.20s": a count AND an error tally, on one
        # line. Reading that as a clean collection made this gate refuse a
        # publish while printing "collection completed cleanly" -- the exact
        # collapse `MirrorCollectionResult` forbids, with the operator told
        # the tree collects by the same sentence that refused it.
        line_start = stdout.rfind("\n", 0, m.start()) + 1
        line_end = stdout.find("\n", m.start())
        summary_line = stdout[line_start:] if line_end == -1 else stdout[line_start:line_end]
        if _SUMMARY_ERROR_CLAUSE_RE.search(summary_line) or _INTERRUPTED_RE.search(stdout):
            return int(m.group(1)), True, True
        return int(m.group(1)), False, True

    if _INTERRUPTED_RE.search(tail_line) or _ERROR_TAIL_RE.search(tail_line):
        return 0, True, True

    if _NO_TESTS_RE.search(tail_line):
        return 0, False, True

    # Unrecognised summary shape — fail closed into "errored" rather than
    # silently reporting a clean zero (see docstring), AND report it as
    # unrecognised so the caller treats this as INCOMPLETE, not as a
    # content verdict about the tree.
    return 0, True, False


def _subprocess_env() -> "dict[str, str]":
    """A copy of the current environment with `PYTHONPATH` and every var in
    `_PYTEST_ENV_SCRUB` removed. `PYTHONPATH` is the only generic vector by
    which claude-klabauter's own source tree could leak onto the child's `sys.path`
    via an explicit path entry — this closes ONE channel, not all of them:
    it does not and cannot prevent the child from resolving
    `coordinator_core` via an ambient editable install on the interpreter
    it runs under (see this module's own docstring, "What 'isolated from
    claude-klabauter' actually means here"). Combined with `cwd=tree_root` in the
    caller (Python's own `-m pytest` invocation adds the CURRENT directory,
    not the parent process's, to `sys.path[0]`), the combination is
    sufficient in practice ONLY because `sys.path[0]` precedence lets `cwd`
    shadow a same-named ambient install — a reliance
    `_verify_isolation_precondition` checks rather than assumes. There is no
    portable way to positively assert an empty `sys.path` from outside the
    child process, so this function closes the one channel it directly
    controls: the environment it hands the child.

    `_PYTEST_ENV_SCRUB` closes a second, load-shaped channel: a peer
    session's `PYTEST_ADDOPTS` (e.g. `-n auto`) reaches this child
    unscrubbed, an xdist worker dies under memory pressure, and the
    resulting partial-collection summary with an error clause gets
    misread as a verdict about THIS tree rather than about a setting this
    module never asked for. `--continue-on-collection-errors` in
    particular would also break `_parse_collection_summary`'s own ordering
    assumption (see that function's docstring) — this module never passes
    that flag itself, but an inherited `PYTEST_ADDOPTS` could add it
    unseen."""
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    for var in _PYTEST_ENV_SCRUB:
        env.pop(var, None)
    return env


def _verify_isolation_precondition(tree_root: Path) -> bool:
    """Return whether `tree_root` carries the package directory that
    `run_assembled_mirror_gate`'s isolation reliance depends on shadowing.

    The gate's isolation is NOT interpreter-level (see module docstring);
    it depends on `cwd=tree_root` giving `sys.path[0]` precedence over an
    ambient editable install of the same package name (measured
    2026-08-29: claude-klabauter's own interpreter has exactly this install). That
    precedence only produces the intended answer if `tree_root` itself
    contains a `coordinator_core/` directory for `cwd` to shadow the
    ambient install with — a tree missing that directory would still run
    collection, but a resolved `import coordinator_core` inside it could
    silently come from claude-klabauter instead, with no signal that isolation had
    stopped applying. This function turns that reliance into a checked
    precondition instead of an assumed one: callers must refuse rather
    than trust a run made without it."""
    return (tree_root / "coordinator_core").is_dir()


def run_assembled_mirror_gate(
    tree_root: "Path | str",
    *,
    python_executable: "str | None" = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    coordinator_core_in_declared_scope: bool = True,
) -> MirrorCollectionResult:
    """Run the tree's own documented fast-tier command, in `--collect-only
    -q` form, as a subprocess with `cwd=tree_root` and `PYTHONPATH`
    stripped from its environment (`_subprocess_env`). This does NOT run
    the child in a separate interpreter and does NOT, by itself, prevent
    the child from resolving `coordinator_core` via an ambient editable
    install on the interpreter it runs under — see this module's own
    docstring, "What 'isolated from claude-klabauter' actually means here", for the
    measured basis of what IS enforced (PYTHONPATH cleared, cwd set) versus
    what is RELIED ON (cwd's `sys.path[0]` precedence shadowing an ambient
    install). That reliance is checked, not assumed:
    `_verify_isolation_precondition` runs before the subprocess, and a
    `tree_root` missing the `coordinator_core/` directory the shadowing
    depends on refuses immediately (`passed=False, isolation_unverified
    =True`) rather than running an unverified subprocess.

    `tree_root` MUST be POST-SYNC bytes — see this module's own docstring,
    "BLOCKING PRECONDITION discharged: (i)"; this function does not and
    cannot verify that from inside `tree_root` alone.

    `python_executable` defaults to `sys.executable` — the interpreter this
    gate itself runs under, per every other subprocess-spawning site in
    this plan's family (no separate interpreter resolution invented here).

    `coordinator_core_in_declared_scope` — the caller-supplied fact this
    module's own MECHANISM-only scope forbids it from computing itself (see
    module docstring, "The third verdict"): whether `coordinator_core` is
    part of this destination's DECLARED scope, read by the caller from the
    UNFILTERED target row set. Defaults to `True` so a caller that does not
    pass it gets EXACTLY today's behaviour — a missing `coordinator_core/`
    directory always refuses as `isolation_unverified`, never silently
    reads as not-applicable by omission. Only when this is explicitly
    `False`, AND `_verify_isolation_precondition` independently finds
    `tree_root` missing the directory too, does this function return
    `not_applicable=True` instead of refusing.

    A `subprocess.TimeoutExpired` is caught and reported as
    `passed=False, errored=True, timed_out=True` (so `is_incomplete=True`)
    rather than propagated — a gate that raises out of a caller's
    `run_pre_sync_gates` loop on a slow tree is a crash, not a refusal, and
    the parent plan's own budget note treats "exceeds ~60s" as an
    escalation signal for the WIRING caller (C3) to act on, not a reason
    for this function to blow up. An `OSError` from process creation
    itself (a saturated box refusing a new process) is caught the same
    way, reported `verdict_obtained=False` (so `is_incomplete=True`),
    never propagated: this function Never Raises.
    """
    tree_root = Path(tree_root)
    executable = python_executable or sys.executable
    command = (
        executable,
        "-m",
        "pytest",
        "-m",
        MARKER_EXPRESSION,
        "--collect-only",
        "-q",
    )

    if not _verify_isolation_precondition(tree_root):
        if not coordinator_core_in_declared_scope:
            return MirrorCollectionResult(
                passed=False,
                collected_count=0,
                errored=False,
                exit_code=None,
                timed_out=False,
                elapsed_s=0.0,
                command=command,
                tree_root=str(tree_root),
                stdout_tail="",
                stderr_tail=(
                    "assembled-mirror-gate: NOT APPLICABLE — coordinator_core "
                    "is not part of this destination's declared scope and is "
                    "absent from tree_root; this gate has nothing to say "
                    "about this tree, by construction. No subprocess run."
                ),
                not_applicable=True,
                timeout_s=timeout_s,
                verdict_obtained=False,
            )
        return MirrorCollectionResult(
            passed=False,
            collected_count=0,
            errored=True,
            exit_code=None,
            timed_out=False,
            elapsed_s=0.0,
            command=command,
            tree_root=str(tree_root),
            stdout_tail="",
            stderr_tail=(
                "assembled-mirror-gate: refused before running — tree_root "
                "carries no coordinator_core/ directory for cwd to shadow "
                "the ambient editable install with, so the subprocess's "
                "sys.path isolation cannot be trusted (see "
                "_verify_isolation_precondition)."
            ),
            isolation_unverified=True,
            timeout_s=timeout_s,
            verdict_obtained=False,
        )

    start = time.perf_counter()
    try:
        result = subprocess.run(
            command,
            cwd=str(tree_root),
            env=_subprocess_env(),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
            **_NO_CONSOLE,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed_s = time.perf_counter() - start
        return MirrorCollectionResult(
            passed=False,
            collected_count=0,
            errored=True,
            exit_code=None,
            timed_out=True,
            elapsed_s=elapsed_s,
            command=command,
            tree_root=str(tree_root),
            stdout_tail=_tail(exc.stdout or ""),
            stderr_tail=_tail(exc.stderr or ""),
            timeout_s=timeout_s,
            verdict_obtained=False,
        )
    except OSError as exc:
        # Process creation itself failed (e.g. a saturated box refusing a
        # new process) -- this function's own docstring promises "Never
        # raises"; propagating an OSError out of a caller with no
        # try/except turns a refusal into a crash. Reported the same way a
        # TimeoutExpired is: no subprocess ran to completion, so this
        # carries no claim about the tree's content.
        elapsed_s = time.perf_counter() - start
        return MirrorCollectionResult(
            passed=False,
            collected_count=0,
            errored=True,
            exit_code=None,
            timed_out=False,
            elapsed_s=elapsed_s,
            command=command,
            tree_root=str(tree_root),
            stdout_tail="",
            stderr_tail=f"assembled-mirror-gate: refused — process creation failed: {exc}",
            timeout_s=timeout_s,
            verdict_obtained=False,
        )
    elapsed_s = time.perf_counter() - start

    collected_count, errored, recognized = _parse_collection_summary(result.stdout)
    # A negative returncode means the child died to a signal rather than
    # exiting on its own -- e.g. an OS/job-object kill under memory
    # pressure. Whatever stdout it managed to write before that, even if it
    # happens to match a recognised summary shape, is not evidence the
    # collection actually finished; treat it the same as an unrecognised
    # summary. `returncode < 0` is POSIX-only signal-death signalling;
    # Windows job-object kills report a large positive code instead, which
    # this branch does not claim to catch -- the unrecognised-summary path
    # above is what closes that shape.
    signal_killed = result.returncode is not None and result.returncode < 0
    verdict_obtained = recognized and not signal_killed
    if not verdict_obtained:
        errored = True
    passed = verdict_obtained and result.returncode == 0 and not errored

    return MirrorCollectionResult(
        passed=passed,
        collected_count=collected_count,
        errored=errored,
        exit_code=result.returncode,
        timed_out=False,
        elapsed_s=elapsed_s,
        command=command,
        tree_root=str(tree_root),
        stdout_tail=_tail(result.stdout),
        stderr_tail=_tail(result.stderr),
        timeout_s=timeout_s,
        verdict_obtained=verdict_obtained,
    )


_TEST_STEM_PREFIX = "test_"
_TEST_STEM_SUFFIX = "_test"
_NON_SUBJECT_STEMS = frozenset({"__init__", "conftest"})


@dataclass(frozen=True)
class ModuleTestCoverageReport:
    """The verdict `find_modules_missing_tests` reaches. WARN-shaped, never
    a refusal — `missing` is reported alongside `examined_count` so a
    caller (and this module's own `format_test_coverage_warning`) can
    always print the denominator: "0 modules missing tests" over
    `examined_count == 0` is the abstention this plan exists to kill, and
    must never read the same as "0 modules missing tests" over a real
    population (parent plan Anti-scope, "Every leg must report its
    denominator")."""

    examined_count: int
    missing: "tuple[str, ...]"

    @property
    def missing_count(self) -> int:
        return len(self.missing)


def _is_test_file(stem: str) -> bool:
    return stem.startswith(_TEST_STEM_PREFIX) or stem.endswith(_TEST_STEM_SUFFIX)


def _test_subject_stem(stem: str) -> str:
    """Strip the test-naming convention off `stem` so a subject module's
    own stem can be looked up against it — `test_foo` and `foo_test` both
    reduce to `foo`. Only one of the two affixes is ever present (a file
    already matched `_is_test_file` to get here), so stripping both in
    sequence is safe and idempotent."""
    if stem.startswith(_TEST_STEM_PREFIX):
        stem = stem[len(_TEST_STEM_PREFIX) :]
    if stem.endswith(_TEST_STEM_SUFFIX):
        stem = stem[: -len(_TEST_STEM_SUFFIX)]
    return stem


def _is_vendored_path(path: Path) -> bool:
    """True iff any component of `path` marks it as third-party dependency
    source rather than a subject this gate's coverage question is about.

    This gate answers "did a module WE ship leave its own test behind" —
    a vendored dependency (a venv's copy of `numpy`, `torch`, `pytest`
    itself, ...) is neither a subject we own nor one whose tests we would
    ever land alongside it, so it belongs in neither `examined_count` nor
    `missing`. Left unfiltered (measured 2026-08-29 against the live
    claude-klabauter<->klabauter pair): 53778 of the assembled mirror's 57754 `.py`
    files sit under a vendored tree, so an unfiltered `examined_count` is
    ~93% other people's code, and every stem-collision false positive in
    `missing` traced back to that same vendored population (e.g. a venv's
    `setup.py`/`terminal.py`/`manifest.py` coincidentally sharing a stem
    with an unrelated `test_<stem>.py` living in claude-klabauter's own source
    tree) — a denominator and a WARN list neither one describes the
    payload this gate exists to check.

    Deliberately NOT delegated to `percolate/ignore.py`'s
    `PercolateIgnoreMatcher`: that module matches a `.percolate-ignore`
    FILE's patterns against publish-payload inclusion (a different,
    file-driven, security-load-bearing question — see its own module
    docstring), not a hardcoded "is this a dependency tree" predicate: no
    `.percolate-ignore` is guaranteed to exist for an arbitrary tree_root/
    source_root this function is asked to walk. A component-name check is
    the smallest correct mechanism for the specific two shapes this gate
    needs to exclude.

    Matches ANY path component named exactly `site-packages`, or any
    component whose name STARTS WITH `.fleet-env` (the fleet's own
    generated-venv naming convention carries a trailing per-run suffix,
    e.g. `.fleet-env.gen-72332-47c78a42/` — a startswith check catches
    every instance, an exact-match check would not)."""
    for part in path.parts:
        if part == "site-packages":
            return True
        if part.startswith(".fleet-env"):
            return True
    return False


def _test_stems_under(root: Path) -> "set[str]":
    """Walk `root` and return the set of subject stems that have a test
    file somewhere under it, matched the same STEM-not-adjacency way
    `find_modules_missing_tests` matches within a single tree (see that
    function's docstring). Vendored paths (`_is_vendored_path`) are
    excluded from the walk — a vendored test file must never make a
    vendored (or first-party, via stem collision) subject look covered
    or missing."""
    stems: set[str] = set()
    for py_file in root.rglob("*.py"):
        if _is_vendored_path(py_file):
            continue
        stem = py_file.stem
        if _is_test_file(stem):
            stems.add(_test_subject_stem(stem))
    return stems


def find_modules_missing_tests(
    tree_root: "Path | str", source_root: "Path | str | Iterable[Path | str]"
) -> ModuleTestCoverageReport:
    """Walk every `.py` file physically inside `tree_root` (the assembled,
    POST-SYNC mirror — same tree, same walk shape `find_import_closure_
    violations` uses over a restricted row) and report, for each SHIPPED
    first-party module, whether that module's test STAYED HOME: its test
    file exists in `source_root` (the pre-sync SOURCE tree the mirror was
    assembled from) but did not ship alongside it in `tree_root`. This is
    klabauter#3's exact inverse: C1/C2 catch a module a test still reaches
    for after it was dropped; this catches a module that shipped while ITS
    test did not (parent plan body, "a fix published to the mirror while
    its two new test files did not, silently").

    Comparing `tree_root` against ITSELF (an earlier version of this
    function) conflates two different claims: "this module's test stayed
    home" (a real, actionable percolate-payload gap) and "this module
    never had a test anywhere" (true of the large majority of any
    repository's modules, and not this gate's business). Reading `source_
    root` as the ground truth for "does a test exist at all" is what keeps
    the two apart — a module absent from `source_test_stems` never had a
    test to leave behind, and is never reported regardless of whether it
    has one in `tree_root`.

    Matching is by STEM, not by directory adjacency, deliberately —
    `test_foo.py` counts as `foo.py`'s test wherever in either tree it
    landed. The assembled mirror routinely ships a module and its test at
    different depths (row `coordinator_core` ships `foo.py` at the tree
    root while its test lives under `tests/`), and a directory-adjacency
    requirement would misreport every one of those as missing. This is
    the same READERS-not-CALLERS posture C1's docstring names: the walk
    asks "does some test file's stem name this module", not "does this
    exact directory contain one".

    `examined_count` still counts SHIPPED subjects in `tree_root` (the
    same denominator the pre-C6-inverse-fix version reported) — this
    function still answers "of what shipped, how many left their test
    behind", not "how many source modules have tests". `__init__.py` and
    `conftest.py` are excluded from that population: neither is a
    "module" with an independently-expected test file by convention, and
    counting them would inflate `missing` with entries no author would
    ever action.

    WARN, never refuse — this function returns a report, not a
    pass/fail verdict; a hard gate here would be un-landable on day one
    (parent plan C6 body, "plenty of modules legitimately have no test").

    A file that fails to parse its own STEM (impossible — stems come from
    `Path.stem`, never from source content) is not a concern here; unlike
    `find_import_closure_violations`, this function never reads file
    CONTENTS, only names, so it has no `SyntaxError` case to skip.

    Vendored paths (`_is_vendored_path` — a `site-packages` or
    `.fleet-env*` path component) are excluded from BOTH `tree_root` and
    every `source_root`, in both the examined population and the test-stem
    lookup: this gate answers a question about the payload WE ship, and a
    third-party dependency is neither a subject we own nor one whose tests
    we would ever land, on either side of the comparison."""
    tree_root = Path(tree_root)
    if isinstance(source_root, (str, Path)):
        source_roots = [Path(source_root)]
    else:
        source_roots = [Path(root) for root in source_root]
    py_files = sorted(p for p in tree_root.rglob("*.py") if not _is_vendored_path(p))

    assembled_test_stems = _test_stems_under(tree_root)
    source_test_stems: "set[str]" = set()
    for root in source_roots:
        source_test_stems |= _test_stems_under(root)

    examined_count = 0
    missing: list[str] = []
    for py_file in py_files:
        stem = py_file.stem
        if _is_test_file(stem) or stem in _NON_SUBJECT_STEMS:
            continue
        examined_count += 1
        if stem in source_test_stems and stem not in assembled_test_stems:
            missing.append(py_file.relative_to(tree_root).as_posix())

    return ModuleTestCoverageReport(examined_count=examined_count, missing=tuple(sorted(missing)))


_MAX_LISTED_MISSING = 50
"""Cap on paths printed by `format_test_coverage_warning`. `report.missing`
is now source-vs-mirror "test stayed home" entries, not the whole
never-had-a-test population — the set this function prints should
normally be zero or near it (a real, actionable percolate-payload gap
per entry), but a cap still guards against a genuinely large sync
failure flooding the log the way the never-had-a-test census used to
unconditionally."""


def format_test_coverage_warning(report: ModuleTestCoverageReport) -> str:
    """Render `report` as the WARN line a wiring caller prints — never a
    refusal. Always states the denominator (`examined_count`) alongside
    the count, per the parent plan's "0 modules missing tests" abstention
    warning: a caller that prints only `missing_count` cannot distinguish
    a clean tree from one this function never walked.

    `report.missing` now names subjects whose test exists in the SOURCE
    tree but did not ship with the assembled mirror — a shipped-test-left-
    behind gap, not "this module never had a test" (see `find_modules_
    missing_tests`'s docstring for why those are no longer conflated).
    The full list still prints, capped at `_MAX_LISTED_MISSING` with an
    elision count stated rather than silently dropped — this set should
    normally be zero or near it, so a cap is a guard against a genuine
    sync failure, not an expected steady-state truncation."""
    lines = [
        "assembled-mirror-gate: WARN — "
        f"{report.missing_count} module(s) shipped without the test their "
        f"source carries, over {report.examined_count} module(s) examined"
    ]
    if report.missing:
        shown = report.missing[:_MAX_LISTED_MISSING]
        lines.extend(f"  - {path}" for path in shown)
        elided = report.missing_count - len(shown)
        if elided > 0:
            lines.append(f"  ... and {elided} more (elided)")
    return "\n".join(lines)


def format_refusal(result: MirrorCollectionResult) -> str:
    """Render `result` as the refusal message a wiring caller (C3) prints
    when `result.passed` is False. Reports the denominator explicitly (the
    parent plan's Anti-scope: "Do not build a gate that can abstain ...
    Every leg must report its denominator") — a caller that only prints
    "assembled mirror gate failed" without the collected count and the
    errored/clean-zero distinction reproduces the abstention defect this
    plan exists to close."""
    if result.isolation_unverified:
        shape = (
            "INCOMPLETE — ISOLATION UNVERIFIED, no subprocess run "
            f"(budget {result.timeout_s:.0f}s)"
        )
    elif result.timed_out:
        shape = (
            f"INCOMPLETE — TIMED OUT after {result.elapsed_s:.1f}s "
            f"(budget {result.timeout_s:.0f}s)"
        )
    elif result.is_incomplete:
        shape = (
            "INCOMPLETE — NO VERDICT OBTAINED (unrecognised collection "
            f"summary, signal-killed child, or a spawn failure), exit="
            f"{result.exit_code}"
        )
    elif result.errored:
        shape = (
            f"collection ERRORED (exit={result.exit_code}), "
            f"{result.collected_count} test(s) collected before the errors"
        )
    else:
        shape = (
            f"collection completed cleanly (exit={result.exit_code}) but found "
            f"{result.collected_count} test(s)"
        )
    return (
        "assembled-mirror-gate: REFUSED — "
        f"{shape} — tree_root={result.tree_root} "
        f"command={' '.join(result.command)!r} "
        f"({result.elapsed_s:.2f}s)\n"
        f"stdout (tail):\n{result.stdout_tail}\n"
        f"stderr (tail):\n{result.stderr_tail}"
    )
