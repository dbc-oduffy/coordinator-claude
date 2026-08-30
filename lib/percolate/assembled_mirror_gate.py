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

import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

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
    `TimeoutExpired` reports."""


def _tail(text: str, n_lines: int = 40) -> str:
    lines = text.splitlines()
    return "\n".join(lines[-n_lines:])


def _parse_collection_summary(stdout: str) -> "tuple[int, bool]":
    """Return `(collected_count, errored)` parsed from pytest's `-q
    --collect-only` stdout. `errored` is True whenever the summary reads as
    an interrupted/erroring collection rather than a clean (possibly
    zero-result) one — see `MirrorCollectionResult`'s own docstring for why
    the two zero-count shapes must stay distinguishable.

    Deliberately over-collects into `errored=True` on any summary shape
    this function does not recognise: this feeds a publish refusal gate,
    and misreading a genuine collection error as a clean empty collection
    is the dangerous direction, not the reverse (same asymmetry
    `import_closure.py`'s `_unguarded_import_nodes` documents for its own
    guard/unguarded split).

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
        return 0, True
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
            return int(m.group(1)), True
        return int(m.group(1)), False

    if _INTERRUPTED_RE.search(tail_line) or _ERROR_TAIL_RE.search(tail_line):
        return 0, True

    if _NO_TESTS_RE.search(tail_line):
        return 0, False

    # Unrecognised summary shape — fail closed into "errored" rather than
    # silently reporting a clean zero (see docstring).
    return 0, True


def _subprocess_env() -> "dict[str, str]":
    """A copy of the current environment with `PYTHONPATH` removed — the
    only generic vector by which claude-klabauter's own source tree could leak onto
    the child's `sys.path` via an explicit path entry. This closes ONE
    channel, not all of them: it does not and cannot prevent the child from
    resolving `coordinator_core` via an ambient editable install on the
    interpreter it runs under (see this module's own docstring, "What
    'isolated from claude-klabauter' actually means here"). Combined with
    `cwd=tree_root` in the caller (Python's own `-m pytest` invocation adds
    the CURRENT directory, not the parent process's, to `sys.path[0]`), the
    combination is sufficient in practice ONLY because `sys.path[0]`
    precedence lets `cwd` shadow a same-named ambient install — a reliance
    `_verify_isolation_precondition` checks rather than assumes. There is no
    portable way to positively assert an empty `sys.path` from outside the
    child process, so this function closes the one channel it directly
    controls: the environment it hands the child."""
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
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

    A `subprocess.TimeoutExpired` is caught and reported as
    `passed=False, errored=True, timed_out=True` rather than propagated —
    a gate that raises out of a caller's `run_pre_sync_gates` loop on a
    slow tree is a crash, not a refusal, and the parent plan's own budget
    note treats "exceeds ~60s" as an escalation signal for the WIRING
    caller (C3) to act on, not a reason for this function to blow up.
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
        )
    elapsed_s = time.perf_counter() - start

    collected_count, errored = _parse_collection_summary(result.stdout)
    passed = result.returncode == 0 and not errored

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
        shape = "ISOLATION UNVERIFIED — no subprocess run"
    elif result.timed_out:
        shape = f"TIMED OUT after {result.elapsed_s:.1f}s (budget {DEFAULT_TIMEOUT_S:.0f}s)"
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
