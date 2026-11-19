"""coordinator/lib/percolate/import_closure.py — gate: every module actually
copied into a restricted publish tree must be able to resolve, INSIDE that
same tree, every `coordinator_core` top-level name it imports.

## The defect this closes

`coordinator/bin/publish-allowlist-generate.py`'s AC15 coverage assertion
(sibling gate, same row; declaration source of truth is
`setup/publish-allowlist-declarations.yaml`) verifies that every top-level
`coordinator_core` entry is a recorded decision — allowlisted, `!`-excluded,
or deny-declared. It does not verify that decision was the
RIGHT one: `chain_attribution.py` and `atomic_append.py` were both recorded
as acknowledged-private while `ops/review_trail_write.py` (published) does
`from coordinator_core import chain_attribution`, and
`install/resolution_journal.py` / `benchmarks/ambient_sampler.py`
(published) both import `atomic_append` — so the mirror shipped code whose
imports could never resolve, and `review_trail.write` died on import in
every klabauter-resolved session. This gate closes that wrong-decision case:
it builds the actual restricted tree and asserts import closure over it,
so an acknowledgement that contradicts what the payload imports fails loud
instead of shipping silently.
Spec: `docs/plans/2026-08-12-publish-allowlist-acknowledges-imported-modules.md`
chunk C2.

A second, distinct defect this module closes (2026-08-13): this grader
originally lived only inside a test file with zero production callers, so
`coordinator/bin/publish.py`'s `run_pre_sync_gates` never consulted it and
two broken mirror rounds shipped past a red detector. Promoted here so
`run_pre_sync_gates` can wire it in as a real fail-closed publish gate — see
that function's own docstring for the wiring.

## Scope (read before editing this file)

Subject is `coordinator_core` TOP-LEVEL names, plus (when `source_root` is
passed; docs/plans/2026-10-29-import-closure-provenance-and-publish-refusal.md
C3) a first-party module the source tree carries and the restricted tree
dropped. Never stdlib, never third-party, never a module another publish row
carries — those resolve in neither tree and stay out.

Only files PHYSICALLY INSIDE the restricted tree `build_allowlisted_source`
produces are walked. A module that is itself unpublished (e.g.
`telemetry/op_latency.py`, which imports `atomic_append`) never lands in
that tree, so its import is never inspected and never counted as a
violation. An unpublished module importing another unpublished module is
not this gate's business; only what actually ships must resolve.

## Guarded vs unguarded — the discriminator (2026-08-13 reversal)

Only UNGUARDED imports are graded (`_unguarded_import_nodes`). Guarded means
shielded by a `try/except` clause whose handler would actually catch an
`ImportError`; is written inside an `if TYPE_CHECKING:` block that never
executes at runtime; or sits inside a `with pytest.raises(<ImportError-ish>):`
block — a STRONGER guard than `try/except`, since `pytest.raises(X)` asserts
the body MUST raise `X`, so an import inside one is a negative assertion that
the target does NOT exist, not a dependency on it existing (`with
pytest.raises(ValueError):` is not this guard — a `ValueError` context does
not catch the `ImportError` an absent module actually raises). Guarded does
NOT mean "function-local" — a prior
version of this grader exempted every function-local import outright as "a
deliberate soft dependency that degrades gracefully". That rationale was
FALSE: `coordinator_core/ops/ceremony/commit_pipeline.py`'s reap helper does
a function-local `from coordinator_core.lock_preflight import
preflight_reap_stale_lock` with NO try/except — fatal at call time on the
scoped-commit hot path, and the function-local exemption laundered that
defect straight past this gate. The correct discriminator is guarded vs
unguarded, not module-level vs function-local: a function-local import with
no guard is exactly as load-bearing, and exactly as capable of killing its
caller, as a module-level one — it just fires on first call instead of on
import. `FunctionDef`/`AsyncFunctionDef` bodies are therefore descended into
and graded identically to module-level code.

The narrower, correct negative-spec this preserves is
`coordinator_core/ipc.py`'s two `coordinator_core.telemetry.op_latency`
imports: function-local AND wrapped in `try/except Exception`, a documented
fail-open contract, and exempted because they are GUARDED — not because
they are function-local.

Uses `ast.parse`, never text/grep matching — a commented-out or
string-literal import must never trip this gate. Text-matching this class
of thing is exactly the blind spot on record at
`state/bug-backlog/2026-08-08-the-drift-detector-cannot-see-the-defect-ee65978dd6d7.yaml`
(`_extract_functional_tokens`' shape-matching gap), which is why this gate
does not repeat it.

Negative-spec: this module never edits `coordinator/lib/percolate/allowlist.py`
beyond what an import requires, never adds a bare top-level `!name` to any
row's CSV, and never widens its subject past `coordinator_core` top-level
names — all three are this plan's Anti-scope, shared with
`coordinator/bin/publish-allowlist-generate.py`'s AC15 coverage assertion.
"""

from __future__ import annotations

import ast
import functools
import re
import sys
from collections.abc import Callable
from pathlib import Path

PACKAGE_NAME = "coordinator_core"
"""The package this gate closes over. Public because the production caller
(`publish.py`'s `run_pre_sync_gates`) must ask "is this row's restricted tree
the package itself?" before running the gate at all — the resolve-inside-this-
tree question is meaningless for a `bin/`or `lib/` row, whose files import
`coordinator_core` names that resolve from the separately published package
row."""


NEVER_PUBLISHED_ROOTS = frozenset({"scripts", "bin"})
"""First-party import roots that no publish row ever carries, so an import
rooted here is unresolvable in the published tree unconditionally — no
tree lookup needed, and no row-scoping question to get wrong.

WHY THESE TWO AND NOT `coordinator`/`lib`, measured 2026-08-29 rather than
reasoned: widening the graded set over `coordinator_core/` (3199 files)
newly grades 9 imports across 6 files. Four are `scripts.gen_*`. The other
five are `coordinator.lib.*`, and TWO of those files SHIP —
`tests/test_home_resolution_lint.py` and
`install/tests/test_fleet_env_publish_reachability.py` are both present in
published mirror `c587c774`, where `coordinator/lib/percolate/allowlist.py`,
`targets.py` and `home_resolution_lint.py` all resolve. `coordinator` and
`lib` are SEPARATELY PUBLISHED ROWS: their names resolve in the assembled
union and not in any single row's restricted tree, so grading them per-row
manufactures false positives — the same defect as the 372 measured on
`-coordinator-bin` (2026-08-13) that this gate's row scoping exists to
avoid.

`scripts/` publishes only `setup.py`/`setup.cmd` and `bin/` is not a
first-party import root in any row, so neither can produce that false
positive. These are exactly the roots the klabauter#3 orphans were rooted
in, and the reason a fail-closed gate passed them for three weeks."""


_IMPORT_ERROR_CATCHING_NAMES = frozenset(
    {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"}
)


def _exception_type_names(node: ast.expr) -> set[str]:
    """Return every bare exception-type name an `except` clause's type
    expression names, unwrapping tuple forms (`except (A, B):`). `Name`
    nodes (`except ImportError:`) and `Attribute` nodes (`except
    builtins.ImportError:`, `except somemod.Exception:`) are both matched
    on their final component — good enough to recognise the standard
    spellings without chasing arbitrary aliasing."""
    names: set[str] = set()
    if isinstance(node, ast.Tuple):
        for elt in node.elts:
            names |= _exception_type_names(elt)
    elif isinstance(node, ast.Name):
        names.add(node.id)
    elif isinstance(node, ast.Attribute):
        names.add(node.attr)
    return names


def _is_bare_reraise(body: list[ast.stmt]) -> bool:
    """True when `body` is nothing but a bare `raise` (no docstring/pass
    aside) — a handler that catches and immediately re-raises provides zero
    actual protection against the failure it appears to guard."""
    substantive = [
        stmt
        for stmt in body
        if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant))
        and not isinstance(stmt, ast.Pass)
    ]
    return (
        len(substantive) == 1
        and isinstance(substantive[0], ast.Raise)
        and substantive[0].exc is None
    )


def _handler_catches_import_error(handler: ast.ExceptHandler) -> bool:
    """True when `handler` would actually catch an `ImportError` raised in
    its `try` body — a bare `except:`, or an `except` naming
    `ImportError`/`ModuleNotFoundError`/`Exception`/`BaseException` (bare or
    in a tuple) — AND its body does not simply re-raise (`_is_bare_reraise`).
    `except SomeUnrelatedError:` returns False: the `ImportError` still
    propagates past it uncaught."""
    if handler.type is None:
        catches = True
    else:
        catches = bool(_exception_type_names(handler.type) & _IMPORT_ERROR_CATCHING_NAMES)
    if not catches:
        return False
    return not _is_bare_reraise(handler.body)


_STATEMENT_CHILD_FIELDS = ("body", "orelse", "finalbody", "handlers", "cases")


def _iter_statements(module: ast.Module):
    """Every statement node under `module`, descending only through statement
    containers. An `Import`/`ImportFrom` is a statement and no expression holds
    one, so this finds exactly what `ast.walk` would for them without visiting
    the expression subtrees (the bulk of the node count)."""
    stack: list[ast.AST] = [module]
    while stack:
        node = stack.pop()
        for field in _STATEMENT_CHILD_FIELDS:
            children = getattr(node, field, None)
            if children:
                stack.extend(children)
                yield from children


def _pytest_raises_aliases(module: ast.Module) -> tuple[set[str], set[str]]:
    """Return `(pytest_module_names, raises_func_names)` — every local name
    that resolves to the `pytest` module (`import pytest`, `import pytest as
    pt`) and every local name that resolves to `pytest.raises` imported
    directly (`from pytest import raises`, `from pytest import raises as
    raises_`), found anywhere in `module` via `ast.walk` (not just at
    module-level, since a test module may import inside a fixture or a
    conditional). Feeds `_is_pytest_raises_import_error_guard`, which needs
    to recognise both `pytest.raises(...)` and bare `raises(...)` spellings
    of the same guard."""
    pytest_names: set[str] = set()
    raises_names: set[str] = set()
    for node in _iter_statements(module):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "pytest":
                    pytest_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "pytest":
                for alias in node.names:
                    if alias.name == "raises":
                        raises_names.add(alias.asname or alias.name)
    return pytest_names, raises_names


def _is_pytest_raises_import_error_guard(
    item: ast.withitem, pytest_names: set[str], raises_names: set[str]
) -> bool:
    """True when `item` (one item of a `with`/`async with`) is a call to
    `pytest.raises(...)` (or a bare `raises(...)` resolved via
    `_pytest_raises_aliases`) whose exception argument would actually catch
    an `ImportError` — reusing `_exception_type_names`/
    `_IMPORT_ERROR_CATCHING_NAMES`, the same name-resolution the
    `try/except` guard uses, so a single `with pytest.raises(ModuleNotFoundError):`
    block around an import is treated as guarded exactly like an equivalent
    `try/except ModuleNotFoundError:` would be. This is a STRONGER guard than
    `try/except`, not merely an equivalent one: `pytest.raises(X)` asserts
    the body MUST raise `X`, so the imported name is asserted absent from the
    tree — grading it as unguarded would invert the test's own meaning (see
    this module's "Guarded vs unguarded" docstring section). `with
    pytest.raises(ValueError):` is NOT a guard: a `ValueError` context does
    not catch the `ImportError` an absent module actually raises, so it
    still propagates and the import stays unguarded."""
    call = item.context_expr
    if not isinstance(call, ast.Call) or not call.args:
        return False
    func = call.func
    is_raises_call = (
        isinstance(func, ast.Attribute)
        and func.attr == "raises"
        and isinstance(func.value, ast.Name)
        and func.value.id in pytest_names
    ) or (isinstance(func, ast.Name) and func.id in raises_names)
    if not is_raises_call:
        return False
    return bool(_exception_type_names(call.args[0]) & _IMPORT_ERROR_CATCHING_NAMES)


def _is_type_checking_guard(test: ast.expr) -> bool:
    """True for `if TYPE_CHECKING:` in both its bare-name form (`from typing
    import TYPE_CHECKING`) and its attribute form (`if
    typing.TYPE_CHECKING:`) — a typing-only import guarded this way never
    executes at runtime and cannot make a module dead on import."""
    if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
        return True
    if isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING":
        return True
    return False


def _unguarded_import_nodes(module: ast.Module) -> list[ast.stmt]:
    """Return every `Import`/`ImportFrom` node in `module` that is NOT
    shielded by a guard that would actually prevent it from killing its
    caller — the single property that decides whether a missing target
    kills the importing module (module-level) or the calling function
    (function-local), vs. degrading gracefully.

    Descends into `if`/`with`/`for`/`while`/class bodies AND into
    `FunctionDef`/`AsyncFunctionDef` bodies, grading imports found in either
    identically — a function-local import is unguarded exactly when a
    module-level one in the same position would be (see this module's own
    "Guarded vs unguarded" docstring section for why function-local is not
    itself a guard). A `Try` node's `body` is guarded ONLY when the `try`
    actually has a handler that would catch an `ImportError` on it — a bare
    `except:`, or an `except` naming `ImportError`, `ModuleNotFoundError`,
    `Exception`, or `BaseException` (bare or in a tuple form), AND that
    handler's body is not simply a re-raise (`except X: raise` with no
    argument provides zero real protection). `except SomeUnrelatedError:`
    does not shield the body (the `ImportError` still propagates uncaught),
    and a bare `try/finally` with no `except` at all shields nothing.
    `handlers`/`orelse`/`finalbody` are never themselves treated as guarded,
    regardless of what the `try` catches (an import in an `except` or
    `finally` clause, or in `orelse`, still runs unguarded relative to
    failures in the `try` body it belongs to). An `if TYPE_CHECKING:` body
    (bare `TYPE_CHECKING` name or `typing.TYPE_CHECKING` attribute form) is
    exempted entirely — it never executes at runtime and so can never make a
    module dead on import; its `else`/`elif` branch is still walked
    normally since that DOES run. A `with`/`async with` body is guarded when
    one of its items calls `pytest.raises(...)` (or a bare `raises(...)`
    imported via `from pytest import raises`, resolved per-module by
    `_pytest_raises_aliases`) with an exception argument that would catch
    `ImportError` (`_is_pytest_raises_import_error_guard`, reusing
    `_exception_type_names`/`_IMPORT_ERROR_CATCHING_NAMES`) — the import
    inside is a negative assertion the target module does NOT exist, so
    demanding the tree contain it would invert the test's own meaning; a
    `with` whose items name no such call is walked exactly like `for`/
    `while`, unguarded.

    Deliberately over-collects into "guarded" rather than under-collects
    into "unguarded" on any remaining ambiguity — this function feeds a
    publish gate, and a false negative here (treating a load-bearing import
    as guarded) is the dangerous direction, not a false positive. It is no
    longer unconditionally lenient about `try` bodies, though: only a
    handler that would actually catch the failure counts as a guard, and it
    is no longer unconditionally lenient about function-locality either."""
    collected: list[ast.stmt] = []
    aliases: list[tuple[set[str], set[str]]] = []

    def pytest_aliases() -> tuple[set[str], set[str]]:
        if not aliases:
            aliases.append(_pytest_raises_aliases(module))
        return aliases[0]

    def visit(nodes: list[ast.stmt], in_try_body: bool) -> None:
        for node in nodes:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visit(node.body, in_try_body)
            elif isinstance(node, ast.ClassDef):
                visit(node.body, in_try_body)
            elif isinstance(node, ast.Try):
                guards_import_error = any(
                    _handler_catches_import_error(handler) for handler in node.handlers
                )
                visit(node.body, in_try_body or guards_import_error)
                for handler in node.handlers:
                    visit(handler.body, in_try_body)
                visit(node.orelse, in_try_body)
                visit(node.finalbody, in_try_body)
            elif isinstance(node, ast.If):
                if _is_type_checking_guard(node.test):
                    visit(getattr(node, "orelse", []), in_try_body)
                else:
                    visit(node.body, in_try_body)
                    visit(getattr(node, "orelse", []), in_try_body)
            elif isinstance(node, (ast.With, ast.AsyncWith)):
                pytest_names, raises_names = pytest_aliases()
                guards_import_error = any(
                    _is_pytest_raises_import_error_guard(item, pytest_names, raises_names)
                    for item in node.items
                )
                visit(node.body, in_try_body or guards_import_error)
                visit(getattr(node, "orelse", []), in_try_body)
            elif isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
                visit(node.body, in_try_body)
                visit(getattr(node, "orelse", []), in_try_body)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                if not in_try_body:
                    collected.append(node)

    visit(module.body, False)
    return collected


def _extract_top_level_imports(py_source: str, filename: str) -> tuple[set[str], set[str]]:
    """Parse `py_source` with `ast` and return `(bare_names, module_refs)` —
    every `coordinator_core` top-level name it imports via an UNGUARDED
    import (`_unguarded_import_nodes` — a `try/except`-wrapped import is a
    deliberate soft dependency, not a load-bearing one, and must not be
    graded the same way; a plain function-local import IS graded, see this
    module's "Guarded vs unguarded" docstring section), split by shape,
    because the two shapes resolve differently (see
    `find_import_closure_violations`):

      - `from coordinator_core import X`        -> bare_names += {"X"}
      - `from coordinator_core.X.Y import ...`   -> module_refs += {"X.Y"}
      - `import coordinator_core.X.Y`            -> module_refs += {"X.Y"}

    `module_refs` carries the FULL dotted remainder, not its first
    component. Truncating it (`remainder.split(".", 1)[0]`, the shape here
    until 2026-08-28) graded a missing submodule against its present parent
    package and passed.

    The first shape is ambiguous on its own: `X` may name a submodule
    (`from coordinator_core import chain_attribution` — the shape that
    broke `review_trail_write`) OR a plain attribute `coordinator_core/
    __init__.py` re-exports directly in its own namespace (e.g.
    `from coordinator_core import OP_KEY_SCOPE`, `compute_stamp` — PEP 562
    lazy re-exports, see that file's `_LAZY_REEXPORTS` / `__all__`). The
    two dotted shapes are unambiguous: `X` always names a real submodule
    path component, never a package attribute — `from
    coordinator_core.telemetry.op_latency import ...` requires BOTH
    `telemetry/` and `telemetry/op_latency.py` to exist as tree entries,
    full stop (when it appears unguarded — see above).

    A bare `import coordinator_core` (no dotted remainder) and a relative
    import (`level > 0`) name no `coordinator_core` top-level entry and are
    ignored."""
    bare_names, module_refs, _ = _extract_from_tree(ast.parse(py_source, filename=filename))
    return bare_names, module_refs


def _extract_from_tree(
    tree: ast.Module, nodes: list[ast.stmt] | None = None
) -> tuple[set[str], set[str], set[str]]:
    """`_extract_top_level_imports`'s body over an already-parsed module.

    Split out so the walk parses each file ONCE: this single walk populates
    all three return sets in one pass, including the never-published-roots
    collection below, rather than a second walk over the same tree.
    Re-parsing per grader took the walk from 7.4s to 14.5s over 3208 files
    (measured 2026-08-29) — the same answer for double the process time,
    on a gate the brightline governs; the folded single-walk shape measures
    8.2s.
    `_extract_top_level_imports` stays a source-taking wrapper returning
    only the first two, because its own regression pin calls it that way.

    The third set is every unguarded import rooted in
    `NEVER_PUBLISHED_ROOTS`, carried out of THIS walk rather than a second
    one: those entries ask nothing of the tree — the root is never
    published, so the import cannot resolve there whatever the tree holds,
    and there is no `_resolves_in_tree` call to make."""
    bare_names: set[str] = set()
    never_published: set[str] = set()
    module_refs: set[str] = set()
    for node in _unguarded_import_nodes(tree) if nodes is None else nodes:
        if isinstance(node, ast.ImportFrom):
            if node.level:
                continue
            if node.module == PACKAGE_NAME:
                for alias in node.names:
                    bare_names.add(alias.name)
            elif node.module and node.module.startswith(PACKAGE_NAME + "."):
                module_refs.add(node.module[len(PACKAGE_NAME) + 1 :])
            elif node.module and node.module.split(".", 1)[0] in NEVER_PUBLISHED_ROOTS:
                never_published.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == PACKAGE_NAME:
                    continue
                if alias.name.startswith(PACKAGE_NAME + "."):
                    module_refs.add(alias.name[len(PACKAGE_NAME) + 1 :])
                elif alias.name.split(".", 1)[0] in NEVER_PUBLISHED_ROOTS:
                    never_published.add(alias.name)
    return bare_names, module_refs, never_published


def _resolves_in_tree(tree_root: Path, entry: str) -> bool:
    """An import target resolves inside the restricted tree as a module file
    (`X.py`) or a package directory (`X/`) at the FULL dotted depth it names.

    Depth is load-bearing, not a refinement. Until 2026-08-28 both this
    function and `_extract_top_level_imports` truncated to the first
    component, so `coordinator_core.benchmarks.leaf_spawn_migration_verify`
    was graded as `benchmarks` — present — and passed while the module it
    actually names was absent from the published tree. That shipped for
    three weeks and was reported from outside (klabauter#3). A dotted entry
    is a real submodule path component by construction (see
    `_extract_top_level_imports`), so every component must exist.

    "Package present, module absent" and "package absent" are both
    violations and must stay distinguishable from "resolves": a resolver
    that answers True because some PREFIX of the path exists is the exact
    defect this replaced."""
    candidate = tree_root.joinpath(*entry.split("."))
    return candidate.with_suffix(".py").is_file() or candidate.is_dir()


def _package_init_attribute_names(tree_root: Path, cache=None) -> set[str]:
    """Names `coordinator_core/__init__.py` itself binds or declares
    exported, checked ONLY against `from coordinator_core import X` (the
    ambiguous bare shape — see `_extract_top_level_imports`). Two sources,
    both read from the restricted tree's OWN copy of `__init__.py` (never
    the real source) so a mirror missing the file, or shipping a stale one,
    is judged on what it actually ships:

      - every name bound by a module-level `import`/`from ... import` in
        `__init__.py` (covers the eager `OP_KEY_SCOPE`, `WORKTREE_SCOPED_OPS`
        re-export),
      - every string literal listed in a module-level `__all__` assignment
        (covers the PEP 562 `__getattr__` lazy re-exports, which bind no
        name until first access and so have no `import` node to see).

    Returns an empty set if `__init__.py` is absent from the tree (e.g. row
    1 someday stops publishing it) — a bare `from coordinator_core import X`
    then has nothing to resolve against but `_resolves_in_tree`, as it
    should.

    With `cache` (a `GateResultCache`), the names are served by the file's
    content sha256 and parsed only on a miss."""
    init_file = tree_root / "__init__.py"
    if not init_file.is_file():
        return set()
    raw = init_file.read_bytes()
    key = cache.key("", raw, _INIT_ATTRS_DIGEST) if cache is not None else None
    if key is not None:
        hit = cache.get(key)
        if isinstance(hit, list):
            return set(hit)
    names = _init_attribute_names(raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n"))
    if key is not None:
        cache.put(key, sorted(names))
    return names


_INIT_ATTRS_DIGEST = "import-closure-init-attrs"


def _init_attribute_names(source: str) -> set[str]:
    tree = ast.parse(source, filename="__init__.py")
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".", 1)[0])
        elif isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets
        ):
            if isinstance(node.value, (ast.List, ast.Tuple)):
                for elt in node.value.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        names.add(elt.value)
    return names


def _module_present(base: Path, dotted: str) -> bool:
    candidate = base.joinpath(*dotted.split("."))
    return candidate.with_suffix(".py").is_file() or (candidate / "__init__.py").is_file()


def _first_party_candidates(nodes: list[ast.stmt]) -> set[str]:
    """Dotted module names the unguarded absolute imports in `nodes` name, minus
    `coordinator_core` and `NEVER_PUBLISHED_ROOTS`. Pure content: the stdlib
    filter is applied by `_dropped_first_party_modules` at use, because the
    stdlib name set belongs to the running interpreter, not to the file."""
    names: set[str] = set()
    for node in nodes:
        if isinstance(node, ast.ImportFrom):
            if node.level or not node.module:
                continue
            found = [node.module]
        else:
            found = [alias.name for alias in node.names]
        for name in found:
            top = name.split(".", 1)[0]
            if top != PACKAGE_NAME and top not in NEVER_PUBLISHED_ROOTS:
                names.add(name)
    return names


def _dropped_first_party_modules(
    candidates: "set[str] | list[str]",
    rel: str,
    tree_root: Path,
    source_root: Path,
    present: dict[tuple[Path, str], bool],
) -> set[str]:
    """Dotted modules among `candidates` (`_first_party_candidates`) that the
    source tree carries and the restricted tree dropped.

    Candidate bases, same rule as the landing detector: the tree root, the
    importer's own directory, and `src/`. A module resolving under any base
    inside `tree_root` is present; one resolving only under `source_root` is
    dropped. stdlib, `coordinator_core`, `NEVER_PUBLISHED_ROOTS` and names
    found in neither tree (third-party, other publish rows) are never
    reported — cross-row resolution stays out of scope. `present` memoizes
    `_module_present` for one call (the same base/name pair recurs across
    files)."""

    def is_present(base: Path, name: str) -> bool:
        key = (base, name)
        if key not in present:
            present[key] = _module_present(base, name)
        return present[key]

    importer_dir = Path(rel).parent
    bases = (Path(), importer_dir, Path("src"))
    dropped: set[str] = set()
    for name in candidates:
        if name.split(".", 1)[0] in sys.stdlib_module_names:
            continue
        if any(is_present(tree_root / base, name) for base in bases):
            continue
        if any(is_present(source_root / base, name) for base in bases):
            dropped.add(name)
    return dropped


_FACTS_DIGEST = "import-closure-facts"
"""Partition of the shared `GateResultCache` this gate's per-file facts live in;
the content hash is the rest of the key, so the facts are path-independent."""


def _file_facts(raw: bytes, rel: str, cache) -> dict:
    """Import facts of one file's bytes: `{"bare", "refs", "never", "ext"}` as
    sorted lists, or `{"syntax_error": True}`. Served from `cache` (a
    `GateResultCache`, keyed by the content sha256) when present; parsed and
    stored otherwise. Never reads the filesystem, so a verdict built from it
    still resolves every entry against the live tree."""
    key = cache.key("", raw, _FACTS_DIGEST) if cache is not None else None
    if key is not None:
        hit = cache.get(key)
        if isinstance(hit, dict) and (
            hit.get("syntax_error") is True or all(isinstance(hit.get(k), list) for k in _FACT_FIELDS)
        ):
            return hit
    # read_text's universal-newline translation, so a cold parse matches the pre-cache path.
    source = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    try:
        tree = ast.parse(source, filename=rel)
    except SyntaxError:
        facts: dict = {"syntax_error": True}
    else:
        nodes = _unguarded_import_nodes(tree)
        bare_names, module_refs, never_published = _extract_from_tree(tree, nodes)
        facts = dict(
            zip(
                _FACT_FIELDS,
                (
                    sorted(bare_names),
                    sorted(module_refs),
                    sorted(never_published),
                    sorted(_first_party_candidates(nodes)),
                ),
            )
        )
    if key is not None:
        cache.put(key, facts)
    return facts


_FACT_FIELDS = ("bare", "refs", "never", "ext")


def find_import_closure_violations(
    tree_root: Path,
    source_root: Path | None = None,
    cache=None,
    progress: Callable[[int, int], None] | None = None,
) -> tuple[int, list[tuple[str, str]]]:
    """Walk every `.py` file physically inside `tree_root` and return
    `(examined_count, violations)`, where each violation is a
    `(restricted-tree-relative path, unresolved entry)` pair for each
    `coordinator_core` import that does not resolve inside `tree_root` at
    the full dotted depth it names. A file that never landed in `tree_root` (because its own
    top-level module is not allowlisted) is never walked, so its imports
    are never inspected — this is the structural reason an unpublished
    module importing another unpublished module cannot trip this gate.

    A `from coordinator_core import X` name is a violation only if it
    resolves as neither a tree entry NOR a name `__init__.py` itself
    exports (`_package_init_attribute_names`) — the dotted shapes
    (`from coordinator_core.X import ...`, `import coordinator_core.X`)
    get no such exemption, since `X` there always names a real submodule
    path component.

    With `source_root` given, a non-`coordinator_core` first-party import is
    also a violation when the source tree carries its module file and
    `tree_root` does not (`_dropped_first_party_modules`); None keeps the
    `coordinator_core`-only subject exactly.

    NEGATIVE SPEC: do not extend the bare-shape exemption to dotted
    entries. `_package_init_attribute_names` exists because `from
    coordinator_core import X` is ambiguous between a submodule and a
    re-exported attribute; a dotted path is not ambiguous, and exempting it
    would restore the hole this gate closed.

    `cache` (a `GateResultCache`, or None) serves each file's import facts by
    content sha256, so unchanged bytes are never re-parsed across calls or
    fresh staging copies; resolution against `tree_root` is never cached. The
    caller keys the cache on this module's source hash and flushes it.
    `progress(done, total)` is called after each file."""
    violations: list[tuple[str, str]] = []
    examined = 0
    init_attrs = _package_init_attribute_names(tree_root, cache)
    resolved: dict[str, bool] = {}
    present: dict[tuple[Path, str], bool] = {}

    def resolves(entry: str) -> bool:
        if entry not in resolved:
            resolved[entry] = _resolves_in_tree(tree_root, entry)
        return resolved[entry]

    py_files = sorted(tree_root.rglob("*.py"))
    for done, py_file in enumerate(py_files, 1):
        if progress is not None:
            progress(done, len(py_files))
        rel = py_file.relative_to(tree_root).as_posix()
        facts = _file_facts(py_file.read_bytes(), rel, cache)
        if facts.get("syntax_error"):
            continue
        examined += 1
        for entry in facts["bare"]:
            if not resolves(entry) and entry not in init_attrs:
                violations.append((rel, entry))
        for entry in facts["refs"]:
            if not resolves(entry):
                violations.append((rel, entry))
        for entry in facts["never"]:
            violations.append((rel, entry))
        if source_root is not None:
            for entry in sorted(
                _dropped_first_party_modules(facts["ext"], rel, tree_root, source_root, present)
            ):
                violations.append((rel, entry))
    return examined, violations


COMMIT_NAME_ROOTS = ("coordinator_core", "coordinator/bin")
"""Published roots `find_commit_from_import_name_violations` reads importers
from, relative to the repo toplevel."""

_COMMIT_FROM_IMPORT_RE = re.compile(r"^\s*from\s+" + PACKAGE_NAME + r"[\w.]*\s+import\s", re.MULTILINE)
_TEST_DIR_NAMES = frozenset({"tests", "test"})


_CAT_FILE_CHUNK = 100
"""Blobs per `cat-file --batch` spawn in `_read_commit_py_blobs`."""


class CommitReadError(RuntimeError):
    """A git object read for the published commit failed; the gate fails closed."""


def _git_bytes(repo: Path, args: list[str], stdin: bytes | None = None) -> bytes:
    from coordinator_core.git.run import run_git

    r = run_git(args, cwd=str(repo), input=stdin, binary=True)
    # One transient stall (pack contention mid-publish) must not refuse the whole row: these reads are
    # read-only, so re-run once on a timeout. A second timeout, or any non-timeout failure, fails closed.
    if r.timed_out:
        r = run_git(args, cwd=str(repo), input=stdin, binary=True)
    if not r.ok:
        why = "timed out" if r.timed_out else f"({r.returncode}): {r.stderr.strip()}"
        raise CommitReadError(f"git {' '.join(args[:2])} failed {why}")
    return r.stdout_bytes


def _list_commit_py_entries(
    repo: Path, commit: str, roots: tuple[str, ...]
) -> tuple[list[tuple[str, str]], set[str]]:
    """`([(path, blob_sha)], dirs)`: every `.py` blob under `roots` in `commit`
    and every directory any tracked entry sits in. One `ls-tree` spawn."""
    listing = _git_bytes(repo, ["ls-tree", "-r", "-z", commit, "--", *roots])
    parents: set[str] = set()
    wanted: list[tuple[str, str]] = []
    for entry in listing.split(b"\0"):
        if not entry:
            continue
        meta, _, raw_path = entry.partition(b"\t")
        mode, kind, sha = meta.decode("ascii").split()
        path = raw_path.decode("utf-8", "surrogateescape")
        parents.add(path.rpartition("/")[0])
        if kind == "blob" and mode != "120000" and path.endswith(".py"):
            wanted.append((path, sha))
    dirs: set[str] = set()
    for parent in parents:
        while parent and parent not in dirs:
            dirs.add(parent)
            parent = parent.rpartition("/")[0]
    return wanted, dirs


_FULL_SHA_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
# Last full-sha listing plus its loaded blobs, so the commit gates of one publish round share them.
_blob_read_memo: dict[tuple[str, str, tuple[str, ...]], tuple["_CommitBlobs", set[str]]] = {}


class _CommitBlobs:
    """Read-only mapping of a commit's `.py` entries; a blob's text is read only
    when asked for (`prefetch` batches the asks), so a gate whose parse facts are
    cached by blob sha reads none. Text is held by blob sha: duplicates read once."""

    def __init__(self, repo: Path, entries: list[tuple[str, str]]):
        self._repo = repo
        self._entries = dict(entries)
        self._text: dict[str, str] = {}
        self.reads = 0
        self.key_memo: dict[tuple[int, str, str], str] = {}

    def __contains__(self, path):
        return path in self._entries

    def __iter__(self):
        return iter(self._entries)

    def __len__(self):
        return len(self._entries)

    def __getitem__(self, path):
        sha = self._entries[path]
        if sha not in self._text:
            self.prefetch([path])
        return self._text[sha]

    def blob_key(self, path: str) -> bytes:
        """Content identity of `path`'s blob: its git object id."""
        return b"git-blob:" + self._entries[path].encode("ascii")

    def prefetch(self, paths) -> None:
        """Read every not-yet-loaded blob of `paths` in `cat-file --batch` chunks."""
        todo = list(dict.fromkeys(s for s in (self._entries[p] for p in paths) if s not in self._text))
        # Trap: one cat-file over every blob (~11500 at 2026-11) measured 1.6-1.8s per ~2400 and timed
        # out at 19s under publish load against run_git's 2s local budget, refusing the engine row.
        # Chunks keep each spawn inside that budget; the budget is never widened. 400 (0.66s idle) timed out
        # twice at 100% box CPU on 11-15, refusing the engine row; 100 keeps a 4x margin.
        for start in range(0, len(todo), _CAT_FILE_CHUNK):
            chunk = todo[start : start + _CAT_FILE_CHUNK]
            stream = _git_bytes(self._repo, ["cat-file", "--batch"], "".join(f"{s}\n" for s in chunk).encode("ascii"))
            pos = 0
            self.reads += len(chunk)
            for sha in chunk:
                eol = stream.index(b"\n", pos)
                header = stream[pos:eol].split()
                if len(header) != 3 or header[1] != b"blob":
                    raise CommitReadError(f"cat-file returned {stream[pos:eol]!r} for {sha}")
                size = int(header[2])
                self._text[sha] = stream[eol + 1 : eol + 1 + size].decode("utf-8", "replace")
                pos = eol + 1 + size + 1


def _read_commit_py_blobs(repo: Path, commit: str, roots: tuple[str, ...]) -> tuple["_CommitBlobs", set[str]]:
    """`(py_sources, dirs)` for `commit`: a mapping of every `.py` blob under
    `roots` keyed by repo-relative posix path, and every directory any tracked
    entry sits in. One `ls-tree` spawn; blob text is read lazily and in chunks.
    The worktree is never read. A full-sha read is remembered (one entry), so a
    second gate over the same commit lists and reads nothing twice; callers must
    not mutate the result. A ref name is never memoized: it can move."""
    if not _FULL_SHA_RE.match(commit):
        return _read_commit_py_blobs_uncached(repo, commit, roots)
    key = (str(repo), commit, tuple(roots))
    hit = _blob_read_memo.get(key)
    if hit is None:
        hit = _read_commit_py_blobs_uncached(repo, commit, roots)
        _blob_read_memo.clear()
        _blob_read_memo[key] = hit
    return hit


def commit_blob_reads(repo: Path, commit: str) -> int | None:
    """Blobs read so far from `commit`'s shared listing (0 when every parse fact was cached);
    None when that full sha was never listed."""
    for (memo_repo, memo_commit, _roots), (blobs, _dirs) in _blob_read_memo.items():
        if memo_repo == str(repo) and memo_commit == commit:
            return blobs.reads
    return None


def _read_commit_py_blobs_uncached(
    repo: Path, commit: str, roots: tuple[str, ...]
) -> tuple["_CommitBlobs", set[str]]:
    """The `ls-tree` listing behind `_read_commit_py_blobs`."""
    wanted, dirs = _list_commit_py_entries(repo, commit, roots)
    return _CommitBlobs(repo, wanted), dirs


@functools.lru_cache(maxsize=None)
def _is_test_path(path: str) -> bool:
    parts = path.split("/")
    name = parts[-1]
    return (
        any(p in _TEST_DIR_NAMES for p in parts[:-1])
        or name.startswith("test_")
        or name.endswith("_test.py")
        or name == "conftest.py"
    )


def _bound_target_names(target: ast.expr, into: set[str]) -> None:
    if isinstance(target, ast.Name):
        into.add(target.id)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            _bound_target_names(elt, into)
    elif isinstance(target, ast.Starred):
        _bound_target_names(target.value, into)


def _module_defined_names(tree: ast.Module) -> tuple[set[str], bool]:
    """`(names, opaque)`: names bound at module scope (def/class/assign/import,
    descending through if/try/with/for/while, plus `__all__` literals).
    `opaque` is True when the module defines `__getattr__` or star-imports, so
    its namespace cannot be enumerated and nothing imported from it flags."""
    names: set[str] = set()
    opaque = False
    stack: list[ast.stmt] = list(tree.body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
            if node.name == "__getattr__":
                opaque = True
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                _bound_target_names(target, names)
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                names.add(elt.value)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            _bound_target_names(node.target, names)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    opaque = True
                else:
                    names.add(alias.asname or alias.name)
        else:
            if isinstance(node, (ast.For, ast.AsyncFor)):
                _bound_target_names(node.target, names)
            elif isinstance(node, (ast.With, ast.AsyncWith)):
                for item in node.items:
                    if item.optional_vars is not None:
                        _bound_target_names(item.optional_vars, names)
            for field in _STATEMENT_CHILD_FIELDS:
                for child in getattr(node, field, None) or []:
                    if isinstance(child, ast.stmt):
                        stack.append(child)
                    elif isinstance(child, ast.ExceptHandler):
                        stack.extend(child.body)
    return names, opaque


def find_commit_from_import_name_violations(
    repo: Path, commit: str, roots: tuple[str, ...] = COMMIT_NAME_ROOTS, cache=None
) -> tuple[int, list[tuple[str, str]]]:
    """Check every level-0, unguarded `from coordinator_core[.X] import a` in a
    non-test `.py` under `roots` against the blobs of `commit` (never the
    worktree). Returns `(examined_importer_count, violations)`; each violation
    is `(importer_path, "coordinator_core.X.a")`, or `(importer_path,
    "coordinator_core.X")` when module X itself is absent from the commit.

    `a` resolves when X's top-level namespace defines it or X is a package
    holding submodule `a`. A namespace package (directory without
    `__init__.py`) and a module defining `__getattr__` or star-importing never
    flag. Raises `CommitReadError` on a failed git read: callers fail closed.
    `cache` (a `GateResultCache`, or None) serves each blob's parse facts by
    its content hash; resolution still runs against `commit` every time."""
    sources, dirs = _read_commit_py_blobs(repo, commit, roots)
    return _from_import_violations(sources, dirs, sorted(sources), cache)


# Textual pre-filter: a blob with no import line naming the package (and no line continuation that
# could hide one) binds no alias, so its parse is skipped.
_MAY_IMPORT_PACKAGE = re.compile(r"\b(?:from|import)\b[^\n]*\bcoordinator_core\b")
_ATTR_NS_DIGEST = "commit-module-attr-namespace"
_ATTR_IMPORTER_DIGEST = "commit-module-attr-importer"
# Own digests, not the attr gate's: that namespace also counts `global`-declared names, and
# sharing it would loosen this gate's verdict.
_FROM_NS_DIGEST = "commit-from-import-namespace"
_FROM_IMPORTER_DIGEST = "commit-from-import-importer"


def _facts_key(cache, sources, path: str, digest: str):
    """`cache`'s key for `path`'s blob: its git object id when `sources` knows it, else its text."""
    memo = getattr(sources, "key_memo", None)
    memo_key = (id(cache), digest, path)
    if memo is not None and memo_key in memo:
        return memo[memo_key]
    blob_key = getattr(sources, "blob_key", None)
    material = blob_key(path) if blob_key is not None else sources[path].encode("utf-8")
    key = cache.key("", material, digest)
    if memo is not None:
        memo[memo_key] = key
    return key


def _attr_cached(cache, sources, path: str, digest: str, build):
    """`build()` served from `cache` keyed on the blob's identity; a malformed hit is rebuilt."""
    key = _facts_key(cache, sources, path, digest) if cache is not None else None
    if key is not None:
        hit = cache.get(key)
        if isinstance(hit, dict):
            return hit
    facts = build()
    if key is not None:
        cache.put(key, facts)
    return facts


def _prefetch_uncached(cache, sources, importers: list[str], digest: str, include_tests: bool = False) -> None:
    """Read, in chunks, the blobs of `importers` (non-test unless `include_tests`) whose `digest` facts `cache` lacks."""
    prefetch = getattr(sources, "prefetch", None)
    if prefetch is None:
        return
    prefetch(
        [
            p
            for p in importers
            if p in sources
            and (include_tests or not _is_test_path(p))
            and not (cache is not None and isinstance(cache.get(_facts_key(cache, sources, p, digest)), dict))
        ]
    )


def _attr_namespace_facts(source: str, path: str) -> dict:
    """`{"names": sorted, "opaque": bool}` of a module blob's top-level namespace."""
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return {"names": [], "opaque": True}
    names, opaque = _module_defined_names(tree)
    if "global" in source:
        for node in ast.walk(tree):
            if isinstance(node, ast.Global):
                names.update(node.names)
    return {"names": sorted(names), "opaque": opaque}


def _attr_importer_facts(source: str, path: str) -> dict:
    """Everything the attr check needs from one importer blob, resolution-free:
    `imports` ([`from`, module, name, asname] / [`as`, dotted, asname]), `rebound`,
    `probed` and `reads` ([alias, attr] for every non-dunder attribute load)."""
    if not _MAY_IMPORT_PACKAGE.search(source) and "\\\n" not in source and "\\\r" not in source:
        return {"imports": [], "rebound": [], "probed": [], "reads": []}
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return {"syntax_error": True}
    imports: list[list] = []
    for node in _unguarded_import_nodes(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level or not node.module:
                continue
            if node.module != PACKAGE_NAME and not node.module.startswith(PACKAGE_NAME + "."):
                continue
            imports.extend(["from", node.module, a.name, a.asname] for a in node.names)
        elif isinstance(node, ast.Import):
            imports.extend(
                ["as", a.name, a.asname]
                for a in node.names
                if a.asname and a.name.startswith(PACKAGE_NAME + ".")
            )
    if not imports:
        return {"imports": [], "rebound": [], "probed": [], "reads": []}
    rebound: set[str] = set()
    probed: set[tuple[str, str]] = set()
    reads: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Load):
            rebound.add(node.id)
        elif isinstance(node, ast.arg):
            rebound.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            rebound.add(node.name)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            rebound.add(node.name)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in ("hasattr", "getattr")
            and len(node.args) >= 2
            and isinstance(node.args[0], ast.Name)
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            probed.add((node.args[0].id, node.args[1].value))
        elif (
            isinstance(node, ast.Attribute)
            and isinstance(node.ctx, ast.Load)
            and isinstance(node.value, ast.Name)
            and not (node.attr.startswith("__") and node.attr.endswith("__"))
        ):
            reads.add((node.value.id, node.attr))
    return {
        "imports": imports,
        "rebound": sorted(rebound),
        "probed": sorted(map(list, probed)),
        "reads": sorted(map(list, reads)),
    }


def find_commit_module_attr_violations(
    repo: Path,
    commit: str,
    roots: tuple[str, ...] = COMMIT_NAME_ROOTS,
    cache=None,
    progress: Callable[[int, int], None] | None = None,
) -> tuple[int, list[tuple[str, str]]]:
    """Check every `<alias>.<attr>` read in a non-test `.py` under `roots`, where
    `alias` is bound by an unguarded level-0 `from coordinator_core[.X] import
    mod [as alias]` or `import coordinator_core.X.mod as alias` naming a module
    of `commit`, against that module's blob in `commit` (never the worktree).
    Returns `(examined_importer_count, violations)`; each violation is
    `(importer_path, "coordinator_core.X.mod.attr")`.

    `attr` resolves when the module's top-level namespace (or a `global`
    declaration in it) defines it, or the module is a package holding submodule
    `attr`. Dunder attrs, store/delete targets, `hasattr`/`getattr`-probed
    attrs, aliases rebound by any non-import binding in the importer or bound
    to two different modules in it, and modules defining `__getattr__` or
    star-importing never flag. Raises `CommitReadError` on a failed git read.
    Reads are one `ls-tree` plus batched `cat-file` of the blobs `cache` lacks. `cache` (a
    `GateResultCache`, or None) serves each blob's parse facts by its content
    hash, so an unchanged blob is never re-parsed; resolution runs against
    `commit` every time. The caller keys the cache on this module's source hash
    and flushes it. `progress(done, total)` is called after each importer."""
    sources, dirs = _read_commit_py_blobs(repo, commit, roots)
    return _module_attr_violations(sources, dirs, sorted(sources), cache, progress)


def _module_attr_violations(
    sources,
    dirs: set[str],
    importers: list[str],
    cache=None,
    progress: Callable[[int, int], None] | None = None,
) -> tuple[int, list[tuple[str, str]]]:
    """Shared resolution: `importers` checked against the `sources` mapping
    (`in` / `[]` by repo-relative path) and `dirs`."""
    namespace_cache: dict[str, tuple[set[str], bool]] = {}

    def namespace_of(path: str) -> tuple[set[str], bool]:
        if path not in namespace_cache:
            facts = _attr_cached(
                cache, sources, path, _ATTR_NS_DIGEST, lambda: _attr_namespace_facts(sources[path], path)
            )
            namespace_cache[path] = (set(facts.get("names", ())), bool(facts.get("opaque", True)))
        return namespace_cache[path]

    module_files: dict[str, tuple[str, bool] | None] = {}

    def module_file(dotted: str) -> tuple[str, bool] | None:
        if dotted in module_files:
            return module_files[dotted]
        base = dotted.replace(".", "/")
        if f"{base}/__init__.py" in sources:
            found: tuple[str, bool] | None = (f"{base}/__init__.py", True)
        elif f"{base}.py" in sources:
            found = (f"{base}.py", False)
        else:
            found = None
        module_files[dotted] = found
        return found

    violations: set[tuple[str, str]] = set()
    examined = 0
    _prefetch_uncached(cache, sources, importers, _ATTR_IMPORTER_DIGEST)

    def importer_facts(importer: str) -> dict:
        return _attr_cached(
            cache, sources, importer, _ATTR_IMPORTER_DIGEST, lambda: _attr_importer_facts(sources[importer], importer)
        )

    namespace_paths: list[str] = []
    for importer in importers:
        if _is_test_path(importer) or importer not in sources:
            continue
        facts = importer_facts(importer)
        read_aliases = {alias_name for alias_name, _attr in facts.get("reads", ())}
        for kind, module, *rest in facts.get("imports", ()):
            if kind == "from":
                name, asname = rest
                target = module_file(f"{module}.{name}")
                if name == "*" or target is None:
                    continue
                parent = module_file(module)
                if parent is not None:
                    namespace_paths.append(parent[0])
                if (asname or name) in read_aliases:
                    namespace_paths.append(target[0])
            else:
                target = module_file(module)
                if target is not None and rest[0] in read_aliases:
                    namespace_paths.append(target[0])
    _prefetch_uncached(cache, sources, namespace_paths, _ATTR_NS_DIGEST, include_tests=True)
    for path in dict.fromkeys(namespace_paths):
        namespace_of(path)
    for done, importer in enumerate(importers, 1):
        if progress is not None:
            progress(done, len(importers))
        if _is_test_path(importer) or importer not in sources:
            continue
        facts = importer_facts(importer)
        if facts.get("syntax_error"):
            continue
        aliases: dict[str, str] = {}
        ambiguous: set[str] = set()

        def bind(name: str, dotted: str) -> None:
            if aliases.setdefault(name, dotted) != dotted:
                ambiguous.add(name)

        for kind, module, *rest in facts.get("imports", ()):
            if kind == "from":
                name, asname = rest
                parent = module_file(module)
                dotted = f"{module}.{name}"
                if name == "*" or module_file(dotted) is None:
                    continue
                if parent is not None and name in namespace_of(parent[0])[0]:
                    continue
                bind(asname or name, dotted)
            elif module_file(module):
                bind(rest[0], module)
        if not aliases:
            continue
        rebound = set(facts.get("rebound", ()))
        probed = {tuple(p) for p in facts.get("probed", ())}
        live = {a: d for a, d in aliases.items() if a not in rebound and a not in ambiguous}
        if not live:
            continue
        examined += 1
        for alias_name, attr in facts.get("reads", ()):
            if alias_name not in live or (alias_name, attr) in probed:
                continue
            dotted = live[alias_name]
            module_path, is_package = module_file(dotted)
            defined, opaque = namespace_of(module_path)
            if opaque or attr in defined:
                continue
            base = dotted.replace(".", "/")
            if is_package and (
                f"{base}/{attr}.py" in sources
                or f"{base}/{attr}/__init__.py" in sources
                or f"{base}/{attr}" in dirs
            ):
                continue
            violations.add((importer, f"{dotted}.{attr}"))
    return examined, sorted(violations)


class _OverlayBlobs:
    """Read-only mapping over a commit's `.py` entries with `overlay` bytes laid
    on top (`None` = deleted); a blob is read through `reader(sha)` only when
    the resolver asks for it."""

    def __init__(self, entries, overlay, reader):
        self._entries = dict(entries)
        self._overlay = overlay
        self._reader = reader

    def __contains__(self, path):
        if path in self._overlay:
            return self._overlay[path] is not None
        return path in self._entries

    def __getitem__(self, path):
        if path in self._overlay and self._overlay[path] is not None:
            return self._overlay[path]
        if path not in self._overlay and path in self._entries:
            raw = self._reader(self._entries[path])
            return (raw or b"").decode("utf-8", "replace")
        raise KeyError(path)


def find_would_be_tree_from_import_violations(
    repo: Path, base_commit: str, overlay: dict, reader, roots: tuple[str, ...] = COMMIT_NAME_ROOTS
) -> tuple[int, list[tuple[str, str]]]:
    """`find_commit_from_import_name_violations`'s resolution over the tree
    `base_commit` would become with `overlay` applied (`{path: source | None}`,
    `None` = deleted), judged for the overlay's non-test `.py` importers only.
    `reader(blob_sha) -> bytes | None` reads base blobs; only the importers'
    targets are read. One git spawn. Raises `CommitReadError` on a failed listing."""
    sources, dirs, importers = _would_be_tree(repo, base_commit, overlay, reader, roots)
    return _from_import_violations(sources, dirs, importers)


def _from_namespace_facts(tree: ast.Module | None) -> dict:
    """`{"names": sorted, "opaque": bool}` of a module blob's top-level namespace."""
    if tree is None:
        return {"names": [], "opaque": True}
    names, opaque = _module_defined_names(tree)
    return {"names": sorted(names), "opaque": opaque}


def _from_importer_facts(tree: ast.Module | None) -> dict:
    """`{"imports": [[module, [name, ...]], ...]}`, one row per unguarded level-0 package from-import."""
    if tree is None:
        return {"syntax_error": True}
    imports: list[list] = []
    for node in _unguarded_import_nodes(tree):
        if not isinstance(node, ast.ImportFrom) or node.level or not node.module:
            continue
        if node.module != PACKAGE_NAME and not node.module.startswith(PACKAGE_NAME + "."):
            continue
        imports.append([node.module, [a.name for a in node.names]])
    return {"imports": imports}


def find_would_be_tree_violations(
    repo: Path, base_commit: str, overlay: dict, reader, roots: tuple[str, ...] = COMMIT_NAME_ROOTS
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """`(from_import_violations, module_attr_violations)` over one would-be tree
    and one listing spawn."""
    sources, dirs, importers = _would_be_tree(repo, base_commit, overlay, reader, roots)
    return (
        _from_import_violations(sources, dirs, importers)[1],
        _module_attr_violations(sources, dirs, importers)[1],
    )


def _would_be_tree(repo: Path, base_commit: str, overlay: dict, reader, roots: tuple[str, ...]):
    """`(sources, dirs, importers)` for `base_commit` with `overlay` applied."""
    entries, dirs = _list_commit_py_entries(repo, base_commit, roots)
    for path, source in overlay.items():
        if source is not None:
            parts = path.split("/")
            dirs.update("/".join(parts[:i]) for i in range(1, len(parts)))
    sources = _OverlayBlobs(entries, overlay, reader)
    importers = sorted(
        p for p, s in overlay.items()
        if s is not None and p.endswith(".py") and any(p.startswith(r + "/") for r in roots)
    )
    return sources, dirs, importers


def _from_import_violations(
    sources, dirs: set[str], importers: list[str], cache=None
) -> tuple[int, list[tuple[str, str]]]:
    """Shared resolution: `importers` checked against the `sources` mapping
    (`in` / `[]` by repo-relative path) and `dirs`. Parse facts are keyed on blob
    bytes, so a hit is valid for any commit; only resolution is per-commit."""
    # On a cache miss a module that is both importer and target is parsed once for this call;
    # the AST is read-only and never outlives it.
    parsed_cache: dict[str, ast.Module | None] = {}
    namespace_cache: dict[str, tuple[set[str], bool]] = {}

    def parsed(path: str) -> ast.Module | None:
        if path not in parsed_cache:
            try:
                parsed_cache[path] = ast.parse(sources[path], filename=path)
            except SyntaxError:
                parsed_cache[path] = None
        return parsed_cache[path]

    def namespace_of(path: str) -> tuple[set[str], bool]:
        if path not in namespace_cache:
            facts = _attr_cached(cache, sources, path, _FROM_NS_DIGEST, lambda: _from_namespace_facts(parsed(path)))
            namespace_cache[path] = (set(facts.get("names", ())), bool(facts.get("opaque", True)))
        return namespace_cache[path]

    violations: list[tuple[str, str]] = []
    examined = 0

    def importer_facts(path: str) -> dict:
        if not _COMMIT_FROM_IMPORT_RE.search(sources[path]):
            return {"unmatched": True}
        return _from_importer_facts(parsed(path))

    _prefetch_uncached(cache, sources, importers, _FROM_IMPORTER_DIGEST)
    for importer in importers:
        if _is_test_path(importer) or importer not in sources:
            continue
        facts = _attr_cached(cache, sources, importer, _FROM_IMPORTER_DIGEST, lambda: importer_facts(importer))
        if facts.get("unmatched") or facts.get("syntax_error"):
            continue
        examined += 1
        for module, names in facts.get("imports", ()):
            base = module.replace(".", "/")
            init_path, file_path = f"{base}/__init__.py", f"{base}.py"
            if init_path in sources:
                module_path, is_package = init_path, True
            elif file_path in sources:
                module_path, is_package = file_path, False
            elif base in dirs:
                continue
            else:
                violations.append((importer, module))
                continue
            defined, opaque = namespace_of(module_path)
            if opaque:
                continue
            for name in names:
                if name == "*" or name in defined:
                    continue
                if is_package and (
                    f"{base}/{name}.py" in sources
                    or f"{base}/{name}/__init__.py" in sources
                    or f"{base}/{name}" in dirs
                ):
                    continue
                violations.append((importer, f"{module}.{name}"))
    return examined, violations


_UNION_IMPORT_LINE_RE = re.compile(r"^\s*(?:from|import)\s.*" + PACKAGE_NAME, re.MULTILINE)
"""Cheap prefilter for `find_union_closure_violations`: a single compiled
`re.MULTILINE` pattern run once over a file's raw text (no `str.splitlines()`
materialization — that step alone measured 70-84ms of the 243-255ms full
pipeline on the real klabauter mirror, per
`docs/research/spike-verdicts/2026-09-22-publish-union-closure.md` (b)). Only
files an import-shaped line naming `coordinator_core` reach `ast.parse`;
everything else (comments, string literals, unrelated code) is skipped
without parsing. This is a SPEED cut only — every candidate this regex lets
through still gets full AST extraction below, so no violation shape this
module reports depends on the regex seeing a specific dotted needle
contiguous in the text (the shape a naive full-dotted-needle substring
prefilter would miss, per this function's own AC review note)."""


def find_union_closure_violations(assembled_root: Path) -> tuple[int, list[tuple[str, str]]]:
    """Walk every `.py` file physically inside `assembled_root` that is NOT
    itself under a `coordinator_core/` directory, and return
    `(examined_count, violations)` in `find_import_closure_violations`'s
    shape — each violation a `(assembled-root-relative path, unresolved
    entry)` pair.

    This is the CROSS-ROW grader `find_import_closure_violations` cannot be:
    that gate only ever sees one row's own restricted tree, so a file
    shipped by a DIFFERENT row that imports a `coordinator_core` name absent
    from the union (`docs/plans/2026-09-22-publish-integrity-union-and-
    anchor-spike.md` § Problem, Leg U — 24 violations over 21 files at
    authoring) is invisible to it. `assembled_root` is the union: the
    already-assembled destination tree carrying every row's output side by
    side, with `coordinator_core/` as one sibling directory among the rest.
    A name resolves here exactly when it resolves inside
    `assembled_root/coordinator_core` — never against any other row's tree,
    and never against this repo's own unassembled source.

    Files under `coordinator_core/` are never walked: grading whether
    `coordinator_core` resolves against itself is the per-row gate's job
    (`find_import_closure_violations`), not this one's — reusing this
    module's existing depth/guard/ambiguity rules over that specific
    self-referential case would just repeat that gate's own answer.

    Reuses `_unguarded_import_nodes`, `_resolves_in_tree`, and
    `_package_init_attribute_names` UNCHANGED (per this row's own file-scope
    note) — this function only orchestrates them differently, over a wider
    walk, because the union case has one shape the per-row gate's
    `_extract_from_tree` does not need to resolve on its own: `from
    coordinator_core.<present package> import <name>` only ever checked that
    `<present package>`'s dotted path resolves, never whether `<name>` itself
    names an existing nested submodule vs. an attribute the package's own
    `__init__.py` exports — an ambiguity structurally identical to the bare
    `from coordinator_core import X` case (`_package_init_attribute_names`),
    just one level deeper. This function resolves that ambiguity per nested
    package instead of leaving it unchecked, which is what lets it catch a
    `from <present top-level package> import <absent submodule>` pair the
    per-row gate's own dotted-shape handling does not check for by design
    (see AC review note on this row).

    Every import shape graded (bare, dotted-module, dotted-attribute,
    `import a.b.c`) is decided by `ast.parse`, never by the prefilter regex
    below — the regex only decides which files are WORTH parsing at all, so
    no violation depends on a needle appearing contiguous in the raw text.
    Guarded imports (`try/except`, `TYPE_CHECKING`, `pytest.raises(...)`) are
    never reported, via `_unguarded_import_nodes`. No subprocess is spawned:
    the walk, every read, and every parse are in-process."""
    coordinator_core_root = assembled_root / PACKAGE_NAME
    init_attrs = _package_init_attribute_names(coordinator_core_root)
    violations: list[tuple[str, str]] = []
    examined = 0
    for py_file in sorted(assembled_root.rglob("*.py")):
        rel = py_file.relative_to(assembled_root).as_posix()
        if rel == PACKAGE_NAME or rel.startswith(PACKAGE_NAME + "/"):
            continue
        examined += 1
        source = py_file.read_text(encoding="utf-8")
        if PACKAGE_NAME not in source or not _UNION_IMPORT_LINE_RE.search(source):
            continue
        try:
            tree = ast.parse(source, filename=rel)
        except SyntaxError:
            continue
        for node in _unguarded_import_nodes(tree):
            if isinstance(node, ast.ImportFrom):
                if node.level:
                    continue
                if node.module == PACKAGE_NAME:
                    for alias in node.names:
                        if not _resolves_in_tree(coordinator_core_root, alias.name) and (
                            alias.name not in init_attrs
                        ):
                            violations.append((rel, alias.name))
                elif node.module and node.module.startswith(PACKAGE_NAME + "."):
                    submodule_path = node.module[len(PACKAGE_NAME) + 1 :]
                    if not _resolves_in_tree(coordinator_core_root, submodule_path):
                        violations.append((rel, submodule_path))
                        continue
                    nested_root = coordinator_core_root.joinpath(*submodule_path.split("."))
                    if not nested_root.is_dir():
                        # A resolved FILE, not a package: every imported
                        # name is necessarily an attribute defined inside
                        # it, never a further nested submodule — nothing
                        # left to check (see docstring's nested-ambiguity
                        # note, which only applies to package directories).
                        continue
                    nested_attrs = _package_init_attribute_names(nested_root)
                    for alias in node.names:
                        nested_entry = f"{submodule_path}.{alias.name}"
                        if not _resolves_in_tree(coordinator_core_root, nested_entry) and (
                            alias.name not in nested_attrs
                        ):
                            violations.append((rel, nested_entry))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == PACKAGE_NAME:
                        continue
                    if alias.name.startswith(PACKAGE_NAME + "."):
                        entry = alias.name[len(PACKAGE_NAME) + 1 :]
                        if not _resolves_in_tree(coordinator_core_root, entry):
                            violations.append((rel, entry))
    return examined, violations

# Every function and constant a cached per-blob fact is built from. Trap: a builder that
# gains a new helper must list it here, or an edit to that helper serves stale facts.
_FACT_BUILDERS = (
    _exception_type_names, _is_bare_reraise, _handler_catches_import_error, _iter_statements,
    _pytest_raises_aliases, _is_pytest_raises_import_error_guard, _is_type_checking_guard,
    _unguarded_import_nodes, _extract_from_tree, _first_party_candidates, _init_attribute_names,
    _file_facts, _bound_target_names, _module_defined_names, _attr_namespace_facts,
    _attr_importer_facts, _from_namespace_facts, _from_importer_facts,
)


def facts_version() -> str:
    """Cache identity of the per-blob facts: the builders' source, not the whole module, so an
    edit to resolution or reporting code keeps every cached parse (a cold pass is minutes)."""
    import hashlib
    import inspect

    digest = hashlib.sha256()
    for fn in _FACT_BUILDERS:
        digest.update(inspect.getsource(fn).encode("utf-8"))
    for const in (PACKAGE_NAME, _FACT_FIELDS, _MAY_IMPORT_PACKAGE.pattern, _COMMIT_FROM_IMPORT_RE.pattern):
        digest.update(repr(const).encode("utf-8"))
    return digest.hexdigest()
