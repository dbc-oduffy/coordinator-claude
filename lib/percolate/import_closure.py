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

Subject is `coordinator_core` TOP-LEVEL names only — never stdlib, never
third-party. Widening this to any other import would turn a publish gate
into a general dependency audit and make it red for reasons this plan does
not own (Anti-scope).

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
from pathlib import Path

PACKAGE_NAME = "coordinator_core"
"""The package this gate closes over. Public because the production caller
(`publish.py`'s `run_pre_sync_gates`) must ask "is this row's restricted tree
the package itself?" before running the gate at all — the resolve-inside-this-
tree question is meaningless for a `bin/`or `lib/` row, whose files import
`coordinator_core` names that resolve from the separately published package
row."""


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
    for node in ast.walk(module):
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
    pytest_names, raises_names = _pytest_raises_aliases(module)

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
      - `from coordinator_core.X import ...`     -> module_refs += {"X"}
      - `import coordinator_core.X`              -> module_refs += {"X"}

    The first shape is ambiguous on its own: `X` may name a submodule
    (`from coordinator_core import chain_attribution` — the shape that
    broke `review_trail_write`) OR a plain attribute `coordinator_core/
    __init__.py` re-exports directly in its own namespace (e.g.
    `from coordinator_core import OP_KEY_SCOPE`, `compute_stamp` — PEP 562
    lazy re-exports, see that file's `_LAZY_REEXPORTS` / `__all__`). The
    two dotted shapes are unambiguous: `X` always names a real submodule
    path component, never a package attribute — `from
    coordinator_core.telemetry.op_latency import ...` always requires
    `telemetry/` to exist as a tree entry, full stop (when it appears
    unguarded — see above).

    A bare `import coordinator_core` (no dotted remainder) and a relative
    import (`level > 0`) name no `coordinator_core` top-level entry and are
    ignored."""
    tree = ast.parse(py_source, filename=filename)
    bare_names: set[str] = set()
    module_refs: set[str] = set()
    for node in _unguarded_import_nodes(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                continue
            if node.module == PACKAGE_NAME:
                for alias in node.names:
                    bare_names.add(alias.name)
            elif node.module and node.module.startswith(PACKAGE_NAME + "."):
                remainder = node.module[len(PACKAGE_NAME) + 1 :]
                module_refs.add(remainder.split(".", 1)[0])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == PACKAGE_NAME:
                    continue
                if alias.name.startswith(PACKAGE_NAME + "."):
                    remainder = alias.name[len(PACKAGE_NAME) + 1 :]
                    module_refs.add(remainder.split(".", 1)[0])
    return bare_names, module_refs


def _resolves_in_tree(tree_root: Path, entry: str) -> bool:
    """An import target resolves inside the restricted tree either as a
    top-level module file (`X.py`) or a top-level package directory
    (`X/`)."""
    return (tree_root / f"{entry}.py").is_file() or (tree_root / entry).is_dir()


def _package_init_attribute_names(tree_root: Path) -> set[str]:
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
    should."""
    init_file = tree_root / "__init__.py"
    if not init_file.is_file():
        return set()
    tree = ast.parse(init_file.read_text(encoding="utf-8"), filename="__init__.py")
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


def find_import_closure_violations(tree_root: Path) -> list[tuple[str, str]]:
    """Walk every `.py` file physically inside `tree_root` and return
    `(restricted-tree-relative path, unresolved entry)` pairs for each
    `coordinator_core` top-level import that does not resolve inside
    `tree_root`. A file that never landed in `tree_root` (because its own
    top-level module is not allowlisted) is never walked, so its imports
    are never inspected — this is the structural reason an unpublished
    module importing another unpublished module cannot trip this gate.

    A `from coordinator_core import X` name is a violation only if it
    resolves as neither a tree entry NOR a name `__init__.py` itself
    exports (`_package_init_attribute_names`) — the dotted shapes
    (`from coordinator_core.X import ...`, `import coordinator_core.X`)
    get no such exemption, since `X` there always names a real submodule
    path component."""
    violations: list[tuple[str, str]] = []
    init_attrs = _package_init_attribute_names(tree_root)
    for py_file in sorted(tree_root.rglob("*.py")):
        rel = py_file.relative_to(tree_root).as_posix()
        source = py_file.read_text(encoding="utf-8")
        try:
            bare_names, module_refs = _extract_top_level_imports(source, filename=rel)
        except SyntaxError:
            continue
        for entry in sorted(bare_names):
            if not _resolves_in_tree(tree_root, entry) and entry not in init_attrs:
                violations.append((rel, entry))
        for entry in sorted(module_refs):
            if not _resolves_in_tree(tree_root, entry):
                violations.append((rel, entry))
    return violations
