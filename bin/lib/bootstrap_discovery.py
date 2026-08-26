"""bootstrap_discovery.py — AST-based discovery of `coordinator/bin/` CLIs that
import `coordinator_core` and need the engine-root bootstrap idiom.

Purpose: `test_engine_root_bootstrap_regression.py`'s `_FIXED_CLIS` list used to
be hand-typed — a newly added CLI with a missing bootstrap passed the suite
silently, because nothing ever looked at it. This module walks the `coordinator/
bin/` tree — every `.py` file, PLUS every extensionless file the settled
`coordinator_core.test_bin_launcher_parity` classifier recognizes as a bare
entrypoint (see `_bare_entrypoint_names`; the ~73-file `.py`-only gap this
closed included `coordinator-initiative`, found genuinely broken and fixed
alongside this change, plus the two files — `plan-tasks-resolve`,
`coordinator-lesson-add` — that originated this workstream) — parses each with
`ast` (not grep — grep on a top-level `import coordinator_core` under-reports:
the shape that actually bites is a transitive or function-scoped import, see
`plan-tasks-resolve`'s original defect), and reports which files import
`coordinator_core` anywhere in the file with no recognizable engine-root
bootstrap backing it up.

Spec backlink: state/handoffs/2026-08-12-engine-root-bootstrap-shared-seam.md
AC5/AC6 — "the regression test asserts over a discovered set of CLIs, not a
hand-typed list".

Design of the "needs bootstrap" predicate:
  needs_bootstrap = imports_coordinator_core AND NOT has_engine_root_bootstrap

`imports_coordinator_core` is True when an `ast.Import`/`ast.ImportFrom` node
anywhere in the parsed tree — module scope OR nested inside a function/class —
names `coordinator_core` or a `coordinator_core.*` submodule. Walking the WHOLE
tree (not just `tree.body`) is what catches a function-scoped or transitively
reached import; `ast.walk` already recurses into function bodies, so no extra
scope-tracking is needed for this half.

`has_engine_root_bootstrap` is NOT a bare "does the file mutate sys.path
anywhere" check — that was tried first and rejected as a false-negative trap.
Concretely: nearly every file under `coordinator/bin/` inserts a `_LIB_DIR`
(or `lib_dir`) path onto `sys.path` just to reach `cc_invoke.py` for its
OTHER imports, so "any sys.path.insert/append call present" is true almost
everywhere — including on a file that inserts only that lib-helper path and
STILL dies importing `coordinator_core`, because nothing ever inserted the
engine root itself. A bare "any insert" predicate misses that defect shape
entirely, which is precisely the vacuity trap this file exists to not
re-fall into.

The actual discriminator, confirmed by surveying every `sys.path.insert`/
`.append` call site in this tree by hand rather than assumed: a genuine
engine-root bootstrap's inserted expression is always named with `root`,
`engine`, or the engine-repo name somewhere in an identifier in its expression tree
(`claude_klabauter_root` is the dominant idiom, alongside `_ENGINE_ROOT`, `_REPO_ROOT`,
`_REPO_ROOT_GUESS`, `_CLAUDE_KLABAUTER_ROOT`, `engine_root`, `_claude_klabauter_root`, or a
`str(...)`-wrapped variant of any of those) — while a lib-helper-only insert
never is. So:

  has_engine_root_bootstrap = True if ANY of:
    (a) a call to `ensure_engine_on_path(...)`, `require_engine_on_path(...)`,
        or `require_colocated_engine_on_path(...)` anywhere — all three
        shared seam calls perform their own `sys.path.insert` INSIDE
        `cc_invoke.py`, invisible to the caller's own AST, so each is
        recognized by call name alone.
    (b) a `sys.path.insert(...)`/`sys.path.append(...)` call whose argument
        expression contains an identifier (`ast.Name.id`, `ast.Attribute
        .attr`, or a called function's name) matching `root`, `engine`, or
        the engine-repo name case-insensitively, anywhere in that expression (so
        `str(_REPO_ROOT)`, `coordinator_claude_klabauter_root()`, and a bare
        `claude_klabauter_root` Name all match the same way).

Negative-spec: does NOT flag a file whose only `coordinator_core` mention is
in a docstring, comment, or plain string literal — `ast.Import`/
`ast.ImportFrom` nodes never appear for those, so they are invisible to this
scan by construction, not by a special-cased exclusion. Does NOT require the
literal three named helper functions (`ensure_engine_on_path`,
`resolve_engine_root`, `resolve_colocated_claude_klabauter_root`) — the ~34 hand-rolled
sites named in the handoff's reconcile use their own local variable names and
never call those helpers at all; requiring the named calls would flag all of
them as false positives, which the "verify before flagging" instruction in
the handoff's Anti-scope explicitly forbids.
"""
from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass, replace
from pathlib import Path

#: Directories under `coordinator/bin/` that are never CLI entrypoints, so are
#: excluded from discovery outright rather than flagged as missing a bootstrap:
#:   - lib/       — shared internals, including the seam itself (cc_invoke.py).
#:                  The seam "must be importable without the seam" (property 1
#:                  of the spec) — cc_invoke.py's own function-scoped
#:                  coordinator_core imports are the seam's OWN implementation,
#:                  not a caller that forgot to bootstrap.
#:   - tests/     — pytest already has the engine root on sys.path via its own
#:                  conftest/rootdir machinery; these are not standalone CLIs.
#:   - fixtures/, test-fixtures/ — literal test fixture payloads, not CLIs.
#:   - __pycache__/ — compiled artifacts, not source.
_EXCLUDED_DIR_NAMES = frozenset({
    "lib",
    "tests",
    "fixtures",
    "test-fixtures",
    "__pycache__",
})

_COORDINATOR_CORE_ROOT = "coordinator_core"

#: Case-insensitive substring match for an engine-root-shaped identifier —
#: see module docstring for the empirical survey backing this list.
_ROOT_IDENTIFIER_RE = re.compile(r"root|engine|claude-klabauter", re.IGNORECASE)

#: The `cc_invoke.py` seam calls `_has_engine_root_bootstrap` recognizes by
#: call NAME alone (see that function's docstring for why name, not argument
#: analysis) — `ensure_engine_on_path` (best-effort, swallows),
#: `require_engine_on_path` (env-first, fail-loud),
#: `require_colocated_engine_on_path` (self-location-first, fail-loud), and
#: `require_dispatch_engine_on_path`.
#:
#: The fourth name was MISSING until 2026-08-25, and its absence read as ~175
#: simultaneously-broken CLIs. It is the collapse target for the inline
#: `_resolve_claude_klabauter_root()` + `sys.path.insert` preamble that population
#: carried verbatim, so every one of them bootstraps correctly and every one
#: of them was reported as having no bootstrap at all. A discovery gate that
#: names 175 files at once is describing its own name list, not the tree.
_ENGINE_ROOT_BOOTSTRAP_CALL_NAMES = frozenset({
    "ensure_engine_on_path",
    "require_engine_on_path",
    "require_colocated_engine_on_path",
    "require_dispatch_engine_on_path",
    # `lib/op_trampoline.py`'s wrapper: resolves the engine root through the
    # checked ladder, puts it on sys.path, and returns an exit code instead of
    # raising (its module never exits the process). It delegates to
    # `require_dispatch_engine_on_path` — a caller that uses it HAS bootstrapped,
    # and the surviving `query-*` CLIs all reach the seam only through it.
    "resolve_claude_klabauter_root_or_exit",
})

#: Resolver-family classification for the AST family-map gate (AC4,
#: `test_engine_root_bootstrap_regression.py`'s
#: `test_resolver_family_map_no_family_drift` /
#: `test_no_self_location_family_call_below_top_level`). Two families, keyed
#: by call name:
#:   env-first family     — `resolve_engine_root`, `ensure_engine_on_path`,
#:                           `require_engine_on_path`.
#:   self-location family  — `resolve_colocated_claude_klabauter_root`,
#:                           `require_colocated_engine_on_path`.
FAMILY_ENV_FIRST = "env_first"
FAMILY_SELF_LOCATION = "self_location"

#: Negative-spec: `require_dispatch_engine_on_path` is deliberately ABSENT.
#: The two families here are both on the LOCATOR axis ("where is the source
#: checkout"), and the map exists to catch a file moving between them and to
#: police the fixed-depth `parents[2]` trap. That seam answers a different
#: question on a different axis ("which engine executes", a property of the
#: box) and takes NO script path at all — see its docstring in `cc_invoke.py`,
#: which is emphatic that it is a second seam, not a duplicate of the first.
#: With no path argument it has no depth sensitivity, so it has nothing for
#: either gate to assert. It IS a recognized bootstrap (see
#: `_ENGINE_ROOT_BOOTSTRAP_CALL_NAMES` above); it is simply not a locator.
_RESOLVER_CALL_FAMILY: dict[str, str] = {
    "resolve_engine_root": FAMILY_ENV_FIRST,
    "ensure_engine_on_path": FAMILY_ENV_FIRST,
    "require_engine_on_path": FAMILY_ENV_FIRST,
    "resolve_colocated_claude_klabauter_root": FAMILY_SELF_LOCATION,
    "require_colocated_engine_on_path": FAMILY_SELF_LOCATION,
}

#: Directories excluded from the family-map scan (`scan_resolver_call_sites`)
#: — deliberately narrower than `_EXCLUDED_DIR_NAMES` above: the family-map
#: gate must see `lib/` and `tests/` (the depth-trap invariant is precisely
#: about calls found THERE), so only compiled artifacts and literal test
#: payload directories are skipped.
_FAMILY_MAP_EXCLUDED_DIR_NAMES = frozenset({
    "__pycache__",
    "fixtures",
    "test-fixtures",
    "goldens",
})


@dataclass(frozen=True)
class BootstrapCandidate:
    """One `coordinator/bin/` `.py` file that imports `coordinator_core`
    somewhere in its own AST, with no recognizable engine-root bootstrap
    anywhere in the same file to back that import up.

    `module_scope_import` is True when at least one of the offending imports
    sits directly in the file's top-level `Module.body` — i.e. it executes
    unconditionally the moment the file is loaded, so ANY invocation (even
    `--help`, before argparse ever runs) reaches it. False means every
    offending import is nested inside a function/class body and reaching it
    needs an invocation that actually calls into that code path — a bare
    `--help` proves nothing for these (this is the precise vacuity trap AC6
    guards against).
    """

    rel_path: str
    module_scope_import: bool


def _is_coordinator_core_name(dotted: str | None) -> bool:
    if not dotted:
        return False
    return dotted == _COORDINATOR_CORE_ROOT or dotted.startswith(_COORDINATOR_CORE_ROOT + ".")


def _imports_coordinator_core(node: ast.AST) -> bool:
    if isinstance(node, ast.Import):
        return any(_is_coordinator_core_name(alias.name) for alias in node.names)
    if isinstance(node, ast.ImportFrom):
        return _is_coordinator_core_name(node.module)
    return False


def _collect_sys_aliases(tree: ast.AST) -> frozenset[str]:
    """Names bound to the `sys` module anywhere in `tree` — always includes
    the literal `sys`, plus any `import sys as X` alias (the documented
    `import sys as _sys` shape `_is_path_mutation_call` must still accept).
    Module-scope-only is sufficient: every real bootstrap site in this tree
    imports `sys` at module scope."""
    aliases = {"sys"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "sys" and alias.asname:
                    aliases.add(alias.asname)
    return frozenset(aliases)


def _is_path_mutation_call(node: ast.Call, sys_aliases: frozenset[str] = frozenset({"sys"})) -> bool:
    """True if `node` is a `sys.path.insert(...)` / `sys.path.append(...)`
    call (or the same shape via a `sys` alias, e.g. `import sys as _sys` —
    see `_collect_sys_aliases`). Confirming the base resolves to `sys` (not
    just the `<expr>.path.insert/.append` attribute-chain SHAPE) avoids a
    false positive on an unrelated object literally named `path` whose
    argument happens to contain a root-shaped identifier — review finding,
    2026-08-12."""
    func = node.func
    if not (isinstance(func, ast.Attribute) and func.attr in ("insert", "append")):
        return False
    target = func.value
    if not (isinstance(target, ast.Attribute) and target.attr == "path"):
        return False
    base = target.value
    return isinstance(base, ast.Name) and base.id in sys_aliases


def _unwrap_str_call(expr: ast.AST) -> ast.AST:
    """Unwrap a single `str(EXPR)` wrapper (the `str(_REPO_ROOT)` shape seen
    at real sys.path.insert call sites in this tree) to `EXPR`; returns
    `expr` unchanged otherwise. Only one level — every real site this scan
    has needed to cover wraps at most once."""
    if (
        isinstance(expr, ast.Call)
        and isinstance(expr.func, ast.Name)
        and expr.func.id == "str"
        and len(expr.args) == 1
    ):
        return expr.args[0]
    return expr


def _expr_has_root_identifier(expr: ast.AST) -> bool:
    """True if any `Name.id` / `Attribute.attr` / called-function-name token
    inside `expr` matches `_ROOT_IDENTIFIER_RE`."""
    for node in ast.walk(expr):
        if isinstance(node, ast.Name) and _ROOT_IDENTIFIER_RE.search(node.id):
            return True
        if isinstance(node, ast.Attribute) and _ROOT_IDENTIFIER_RE.search(node.attr):
            return True
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and _ROOT_IDENTIFIER_RE.search(func.id):
                return True
            if isinstance(func, ast.Attribute) and _ROOT_IDENTIFIER_RE.search(func.attr):
                return True
    return False


def _for_loop_feeds_root_shaped_insert(for_node: ast.For, sys_aliases: frozenset[str]) -> bool:
    """Handle the one indirection shape actually seen in this tree:
    ``for _rung in (_LIB_DIR, _REPO_ROOT): sys.path.insert(0, str(_rung))``.
    The insert call's own argument is the generic loop variable, not
    `_REPO_ROOT` itself, so `_expr_has_root_identifier` on the call site alone
    is a false negative for an already-correctly-bootstrapped file. True only
    when: the loop target is a plain Name, the loop body contains a path-
    mutation call whose (str()-unwrapped) argument IS that same Name, AND the
    loop's iterable is a literal Tuple/List/Set containing at least one
    root-shaped element."""
    if not isinstance(for_node.target, ast.Name):
        return False
    loop_var = for_node.target.id
    feeds_insert = False
    for node in ast.walk(ast.Module(body=for_node.body, type_ignores=[])):
        if isinstance(node, ast.Call) and _is_path_mutation_call(node, sys_aliases):
            for arg in node.args:
                unwrapped = _unwrap_str_call(arg)
                if isinstance(unwrapped, ast.Name) and unwrapped.id == loop_var:
                    feeds_insert = True
    if not feeds_insert:
        return False
    iterable = for_node.iter
    if isinstance(iterable, (ast.Tuple, ast.List, ast.Set)):
        return any(_expr_has_root_identifier(elt) for elt in iterable.elts)
    return _expr_has_root_identifier(iterable)


def _has_engine_root_bootstrap(tree: ast.AST) -> bool:
    """True if the file calls `ensure_engine_on_path`, or mutates `sys.path`
    via an insert call that is (directly, or through the one for-loop
    indirection shape this tree exhibits) engine-root-shaped.

    Deliberately NOT a bare "any sys.path mutation present" check (the
    near-universal `_LIB_DIR`/`lib_dir` insert present in most files here is
    NOT an engine-root bootstrap by itself — a file that inserts only that
    and nothing else still dies importing `coordinator_core`), and
    deliberately NOT a bare "a root-shaped identifier exists anywhere in the
    file" check either — `repo_root` (the target repo's own root, orthogonal
    to the engine-root token this predicate cares about) is a near-universal
    local/parameter name across this tree's CLIs, so that check produces
    pervasive false negatives. The predicate stays tied to the actual
    `sys.path` mutation call site (directly, or one for-loop hop away).
    """
    sys_aliases = _collect_sys_aliases(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in _ENGINE_ROOT_BOOTSTRAP_CALL_NAMES:
                return True
            if isinstance(func, ast.Attribute) and func.attr in _ENGINE_ROOT_BOOTSTRAP_CALL_NAMES:
                return True
            if _is_path_mutation_call(node, sys_aliases):
                if any(_expr_has_root_identifier(_unwrap_str_call(arg)) for arg in node.args):
                    return True
        elif isinstance(node, ast.For):
            if _for_loop_feeds_root_shaped_insert(node, sys_aliases):
                return True
    return False


def _module_scope_import_present(tree: ast.Module) -> bool:
    return any(_imports_coordinator_core(node) for node in tree.body)


def _any_import_present(tree: ast.AST) -> bool:
    return any(_imports_coordinator_core(node) for node in ast.walk(tree))


def scan_file(path: Path) -> BootstrapCandidate | None:
    """Parse a single `.py` file; return a `BootstrapCandidate` if it imports
    `coordinator_core` anywhere with no engine-root bootstrap anywhere to back
    it up, else None (not a candidate — either no coordinator_core import at
    all, or one already backed by a bootstrap)."""
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return None
    if not _any_import_present(tree):
        return None
    if _has_engine_root_bootstrap(tree):
        return None
    return BootstrapCandidate(
        rel_path=path.name,
        module_scope_import=_module_scope_import_present(tree),
    )


def _should_skip_dir(dirname: str) -> bool:
    return dirname in _EXCLUDED_DIR_NAMES or dirname.startswith(".")


def _bare_entrypoint_names() -> frozenset[str] | None:
    """The settled set of extensionless `coordinator/bin/` entrypoint names,
    reused from `coordinator_core.test_bin_launcher_parity` rather than
    re-derived here.

    That module already owns the entrypoints-by-construction vs mixed-root
    `__main__`-guard discriminator (`SCAN_ROOTS`, `_is_entrypoint`) — the
    exact "which extensionless file is a real CLI" question this predicate
    needs, also reused by `coordinator_core/percolate/engine.py::
    enumerate_gate_entrypoints` for the analogous "every bare shipped
    entrypoint" question. Reusing `_entrypoints(BIN_ROOT)` here means an
    extensionless-payload sibling (a data file, not a script) is excluded by
    the SAME rule everywhere in this repo, not a second hand-rolled
    heuristic that could quietly drift out of parity with it.

    Deliberately NOT the git-bound `enumerate_gate_entrypoints` path (built
    for an arbitrary PUBLISHED `target_root`, closed over ITS OWN top-level-
    name enumeration precisely so it does not depend on this source tree's
    `REPO_ROOT`) — this scanner always runs against the live checkout that
    IS `test_bin_launcher_parity`'s own `REPO_ROOT`, so its git-ls-files-
    bound `BIN_ROOT`/`_entrypoints` apply directly with no path mismatch to
    reconcile.

    Returns None (not an exception) when `coordinator_core` is not
    importable — the discovery module's own callers may run in a context
    where the engine is not yet on `sys.path` (this module's whole reason to
    exist); callers fall back to `.py`-only scanning rather than erroring
    out on their own bootstrap dependency.
    """
    try:
        from coordinator_core import test_bin_launcher_parity as _parity
    except ImportError:
        return None
    return frozenset(_parity._entrypoints(_parity.BIN_ROOT))


def _should_skip_file(filename: str, bare_names: frozenset[str] | None) -> bool:
    if filename.startswith("."):
        # A dotfile (`.wsc-inline-budget-baseline`, `.gitignore`-shaped
        # entries, etc.) is never a CLI entrypoint.
        return True
    if filename == "test_engine_root_bootstrap_regression.py":
        # The regression test itself is the gate, not a CLI the gate covers —
        # excluding it here is belt-and-braces against a degenerate
        # self-referential entry in its own parametrization.
        return True
    if filename.startswith("test_") or filename.endswith("_test.py") or filename == "conftest.py":
        return True
    if filename.endswith(".py"):
        return False
    # Extensionless: admit only names the settled classifier recognizes as a
    # real bare entrypoint (see `_bare_entrypoint_names`). When the
    # classifier is unavailable (`coordinator_core` not yet importable),
    # fall back to skipping every extensionless file — the pre-existing,
    # narrower `.py`-only behavior — rather than guessing.
    if bare_names is None:
        return True
    return filename not in bare_names


def discover_bootstrap_candidates(bin_dir: str | os.PathLike) -> list[BootstrapCandidate]:
    """Walk `bin_dir` (expected: `coordinator/bin/`) and return every
    `BootstrapCandidate` — a `.py` file, OR an extensionless file the settled
    `coordinator_core.test_bin_launcher_parity` classifier recognizes as a
    bare entrypoint (see `_bare_entrypoint_names`), that imports
    `coordinator_core` somewhere with no engine-root bootstrap anywhere in
    the same file to back it up. Sorted by `rel_path` for a stable, diffable
    parametrization order.
    """
    root = Path(bin_dir)
    bare_names = _bare_entrypoint_names()
    candidates: list[BootstrapCandidate] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not _should_skip_dir(d))
        for filename in sorted(filenames):
            if _should_skip_file(filename, bare_names):
                continue
            file_path = Path(dirpath) / filename
            candidate = scan_file(file_path)
            if candidate is None:
                continue
            # `scan_file` sets `rel_path` to the bare filename (it is
            # directly unit-testable in isolation, with no `bin_dir` root to
            # relativize against) -- `replace()` here overwrites it with the
            # real walk-relative path rather than reconstructing the whole
            # dataclass by hand (review finding, 2026-08-12: kept as a
            # `replace()` one-liner rather than pushing `bin_dir` into
            # `scan_file` itself, to avoid touching a module three gate tests
            # now depend on).
            rel_path = str(file_path.relative_to(root))
            candidates.append(replace(candidate, rel_path=rel_path))
    candidates.sort(key=lambda c: c.rel_path)
    return candidates


@dataclass(frozen=True)
class ResolverCallSite:
    """One `ast.Call` site under `coordinator/bin/` invoking a resolver
    named in `_RESOLVER_CALL_FAMILY`, for the AC4 family-map gate. `rel_path`
    uses POSIX separators regardless of host OS, so a checked-in expected map
    is stable across platforms. `lineno` is the call's own source line,
    included so a site that changes which resolver it calls (a family flip)
    is distinguishable from an unrelated new call landing on an adjacent
    line."""

    rel_path: str
    lineno: int
    call_name: str
    family: str


def _resolver_call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _should_skip_family_map_dir(dirname: str) -> bool:
    return dirname in _FAMILY_MAP_EXCLUDED_DIR_NAMES or dirname.startswith(".")


def scan_resolver_call_sites(bin_dir: str | os.PathLike) -> list[ResolverCallSite]:
    """Walk `bin_dir` (expected: `coordinator/bin/`) — INCLUDING `lib/` and
    `tests/`, unlike `discover_bootstrap_candidates` above — and return every
    `ResolverCallSite` where an `ast.Call` invokes a name in
    `_RESOLVER_CALL_FAMILY`. Every `.py` file plus every extensionless file
    the settled `test_bin_launcher_parity` classifier recognizes as a bare
    entrypoint is parsed (dotfiles, compiled artifacts, and literal test-
    payload directories are skipped — see `_FAMILY_MAP_EXCLUDED_DIR_NAMES`).
    A file that fails to parse (or isn't UTF-8) contributes no sites rather
    than raising, matching `scan_file`'s tolerance above. Sorted by
    `(rel_path, lineno, call_name)` for a stable, diffable order.

    Like `discover_bootstrap_candidates` above, extensionless-file admission
    depends on `_bare_entrypoint_names()`: when `coordinator_core` is not
    importable it returns `None` and this scan silently falls back to
    `.py`-only, dropping every extensionless entrypoint from `sites` with no
    error raised -- see that function's docstring and `_should_skip_file`'s
    comment for the same warning at its other two call sites.
    """
    root = Path(bin_dir)
    bare_names = _bare_entrypoint_names()
    sites: list[ResolverCallSite] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not _should_skip_family_map_dir(d))
        for filename in sorted(filenames):
            if filename.startswith("."):
                continue
            if not filename.endswith(".py"):
                if bare_names is None or filename not in bare_names:
                    continue
            file_path = Path(dirpath) / filename
            try:
                source = file_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            try:
                tree = ast.parse(source, filename=str(file_path))
            except SyntaxError:
                continue
            rel_path = file_path.relative_to(root).as_posix()
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = _resolver_call_name(node)
                if name is None:
                    continue
                family = _RESOLVER_CALL_FAMILY.get(name)
                if family is None:
                    continue
                sites.append(
                    ResolverCallSite(
                        rel_path=rel_path,
                        lineno=node.lineno,
                        call_name=name,
                        family=family,
                    )
                )
    sites.sort(key=lambda s: (s.rel_path, s.lineno, s.call_name))
    return sites
