"""AST-based detector for shell-shaped subprocess spawns.

The single source of truth for "is this call site a shell-shaped spawn,
and if so, what kind." The census, lint CLI, and write-time guard import
this module rather than re-deriving the rule.

Negative-spec — the spawn RATCHET is not one of those consumers, and this
file alone does not carry its cross-file transitive-wrapper resolution
(`coordinator_core/tests/test_no_new_spawning_tests.py` never imports this
module: it carries its own `_FunctionSpawnScanner` and per-run classification
policy). That resolution layer — walking a call target through an import
to another file and checking, transitively, whether IT resolves to a real
spawn — used to live only inside the ratchet, undetectable by a byte-identical
vendored copy of this file (confirmed against a sibling repo's copy: zero
widening carried, no signal that it was missing). It now lives in
`coordinator_core/spawn_policy/wrapper_resolution.py`, a sibling module in
this same package: `WrapperResolver`, generic over the caller's own
spawn-classification scanner via a `build_scanner` callable. A vendoring
refresh of the `spawn_policy/` package (not this file alone) carries it.
This file's own exported surface is unchanged by that split — `detect.py`
still has no opinion on cross-file wrapper resolution; consult
`wrapper_resolution.py`'s module docstring for that layer.

Negative-spec: this module reports CALL-SITES, never live costs. A site
being syntactically present says nothing about whether it executes. Do
not add reachability, hot-path, or cost vocabulary to any name, docstring,
or output field here.

See `tasks/shell-spawn-regrowth-gate/PINNED-API.md` for the frozen contract.
"""

from __future__ import annotations

import ast
import dataclasses
import enum
import hashlib
import pathlib
import re


class SpawnKind(str, enum.Enum):
    SHELL_BINARY = "shell-binary"
    SHELL_TRUE = "shell-true"
    SHELL_UNKNOWN = "shell-unknown"
    PLAIN_SPAWN = "plain-spawn"


@dataclasses.dataclass(frozen=True)
class SpawnSite:
    path: str
    enclosing: str
    argv0: str
    ordinal: int
    kind: SpawnKind
    argv_digest: str
    lineno: int  # informational only — never part of identity, never used for matching


class SpawnParseError(Exception):
    """Raised when a source file cannot be parsed.

    NEVER swallowed into a clean result. The bug this exists to not repeat is
    test_operator_cli_engine_contact.py's `except SyntaxError: return False`,
    which reports an unparseable file as clean.
    """

    def __init__(self, path: str, detail: str):
        self.path = path
        self.detail = detail
        super().__init__(f"{path}: failed to parse — {detail}")


@dataclasses.dataclass(frozen=True)
class ExcludedReport:
    paths: list[str]
    # Count of excluded FILES, not sites: an excluded file is never parsed
    # (parsing an excluded file just to count its sites would defeat the
    # point of skipping it — a syntactically invalid excluded file must not
    # crash the walk), so a per-site count is not knowable without parsing.
    suppressed_site_count: int


_DYNAMIC = "<dynamic>"

_SHELL_BINARY_NAMES = {
    "bash", "sh", "zsh", "dash", "ksh", "powershell", "pwsh", "cmd",
}

# (module, funcname) pairs this detector treats as spawn call-sites.
_RECOGNIZED = {
    ("subprocess", "run"),
    ("subprocess", "call"),
    ("subprocess", "check_call"),
    ("subprocess", "check_output"),
    ("subprocess", "Popen"),
    ("os", "system"),
    ("os", "popen"),
    ("os", "execv"),
    ("os", "execve"),
    ("os", "execvp"),
    ("os", "execl"),
    ("os", "execle"),
    ("os", "execlp"),
    ("os", "execlpe"),
    ("os", "execvpe"),
    ("os", "spawnl"),
    ("os", "spawnle"),
    ("os", "spawnlp"),
    ("os", "spawnlpe"),
    ("os", "spawnv"),
    ("os", "spawnve"),
    ("os", "spawnvp"),
    ("os", "spawnvpe"),
    ("os", "posix_spawn"),
    ("os", "posix_spawnp"),
    ("pty", "spawn"),
    ("asyncio", "create_subprocess_shell"),
    ("asyncio", "create_subprocess_exec"),
}

# (module, funcname) pairs whose argv-bearing argument is NOT the first
# positional (`os.spawnv(mode, path, args)`-shaped: a `mode` int/attribute
# precedes the path). Every other recognized call's argv-bearing arg is its
# first positional (`os.execv(path, args)`, `os.posix_spawn(path, argv,
# env)`, `subprocess.run(argv, ...)`) — basename-normalization in
# `_resolve_argv0` already reduces a path-shaped first arg to the same
# argv0 a literal argv list would give.
_MODE_FIRST_SPAWN = {
    ("os", "spawnl"),
    ("os", "spawnle"),
    ("os", "spawnlp"),
    ("os", "spawnlpe"),
    ("os", "spawnv"),
    ("os", "spawnve"),
    ("os", "spawnvp"),
    ("os", "spawnvpe"),
}

# Calls that are shell-true by construction, independent of a `shell=` kwarg.
_INHERENT_SHELL_TRUE = {
    ("os", "system"),
    ("os", "popen"),
    ("asyncio", "create_subprocess_shell"),
}

_TRACKED_MODULES = {"subprocess", "os", "asyncio", "pty"}


def _normalize_argv0_token(token: str) -> str:
    token = token.strip()
    if not token:
        return _DYNAMIC
    token = token.split()[0]
    # A Windows drive prefix (e.g. a `C:\tools\bash.exe`-shaped argv0) needs no separate strip. abs-path-ok: illustrative argv0 shape in a comment, not a real host path
    # The `\\`-split below already isolates the basename, since the drive
    # letter and colon are never part of the last path segment.
    # (The marker above sits on the citation's OWN line deliberately -- the concrete-path
    # gate matches same-line only, so a reason wrapped onto the next line reads as a bare
    # marker and does not exempt anything.)
    for sep in ("/", "\\"):
        if sep in token:
            token = token.rsplit(sep, 1)[-1]
    return token or _DYNAMIC


def _raw_string_value(
    node: ast.AST | None,
    module_consts: dict[str, str],
    local_bindings: dict[str, str] | None,
) -> str | None:
    """Resolves `node` to its exact (un-normalized) string value, or None.

    Used only where the CALLER needs to concatenate substrings before
    basename-normalizing the result (`_resolve_argv0`'s BinOp/Add case) — a
    per-operand normalize-then-concatenate would silently corrupt a
    multi-segment token. Returns None (never a guess) when a component is
    not statically resolvable, so the caller can fail closed to `<dynamic>`.
    """
    if node is None:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        if local_bindings and node.id in local_bindings:
            return local_bindings[node.id]
        if node.id in module_consts:
            return module_consts[node.id]
        return None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _raw_string_value(node.left, module_consts, local_bindings)
        right = _raw_string_value(node.right, module_consts, local_bindings)
        if left is not None and right is not None:
            return left + right
        return None
    return None


def _resolve_argv0(
    node: ast.AST | None,
    module_consts: dict[str, str],
    local_bindings: dict[str, str] | None = None,
) -> str:
    if node is None:
        return _DYNAMIC

    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return _normalize_argv0_token(node.value)

    if isinstance(node, (ast.List, ast.Tuple)):
        if not node.elts:
            return _DYNAMIC
        return _resolve_argv0(node.elts[0], module_consts, local_bindings)

    if isinstance(node, ast.Name):
        if local_bindings and node.id in local_bindings:
            return _normalize_argv0_token(local_bindings[node.id])
        if node.id in module_consts:
            return _normalize_argv0_token(module_consts[node.id])
        return _DYNAMIC

    if isinstance(node, ast.JoinedStr):
        prefix_parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                prefix_parts.append(value.value)
            else:
                break
        prefix = "".join(prefix_parts)
        return _normalize_argv0_token(prefix) if prefix.strip() else _DYNAMIC

    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        if isinstance(node.left, (ast.List, ast.Tuple)):
            # List/tuple concat (`["bash"] + extra`): argv0 is the first
            # element of the LEFT operand regardless of what `extra` resolves
            # to — concatenating a list never changes its own first element.
            return _resolve_argv0(node.left, module_consts, local_bindings)
        # String concat (`"ba" + "sh"`): concatenate the exact operand
        # strings first, THEN basename-normalize the joined result —
        # resolving each operand independently (the prior bug) returned a
        # confidently wrong concrete substring (e.g. "ba" for "ba" + "sh")
        # instead of an honest <dynamic> when concatenation can't be fully
        # resolved.
        raw = _raw_string_value(node, module_consts, local_bindings)
        return _normalize_argv0_token(raw) if raw is not None else _DYNAMIC

    return _DYNAMIC


def _is_shell_binary(argv0: str) -> bool:
    if argv0 == _DYNAMIC:
        return False
    candidate = argv0.lower()
    if candidate.endswith(".exe"):
        candidate = candidate[: -len(".exe")]
    return candidate in _SHELL_BINARY_NAMES


def _shell_signal_from_call(call: ast.Call) -> str:
    """Returns "true", "false", or "unknown" for the call's `shell=` posture.

    A `shell=` keyword with any value (literal or variable-bound) is a direct,
    visible signal — "true" (or "false" for a literal `shell=False`). Opaque
    `**kwargs` forwarding with no explicit `shell=` keyword at the call site
    is "unknown": a `shell=` value could be present but is not statically
    visible. Explicit `shell=` always takes priority over forwarding.
    """
    star_kwargs = False
    for kw in call.keywords:
        if kw.arg == "shell":
            if isinstance(kw.value, ast.Constant) and kw.value.value is False:
                return "false"
            return "true"
        elif kw.arg is None:
            star_kwargs = True
    return "unknown" if star_kwargs else "false"


def _explicit_shell_signal(call: ast.Call) -> str | None:
    """Like `_shell_signal_from_call`, but returns None (not "false") when the
    call states no `shell=` posture at all — the caller-not-specified case a
    `functools.partial`-bound call needs to distinguish from an explicit
    `shell=False`, so it can fall back to the partial's own bound posture.
    """
    star_kwargs = False
    for kw in call.keywords:
        if kw.arg == "shell":
            if isinstance(kw.value, ast.Constant) and kw.value.value is False:
                return "false"
            return "true"
        elif kw.arg is None:
            star_kwargs = True
    return "unknown" if star_kwargs else None


def _classify_kind(qualname: tuple[str, str], shell_signal: str, argv0: str) -> SpawnKind:
    if qualname in _INHERENT_SHELL_TRUE:
        return SpawnKind.SHELL_TRUE
    if shell_signal == "true":
        return SpawnKind.SHELL_TRUE
    if shell_signal == "unknown":
        return SpawnKind.SHELL_UNKNOWN
    if _is_shell_binary(argv0):
        return SpawnKind.SHELL_BINARY
    return SpawnKind.PLAIN_SPAWN


def _classify(qualname: tuple[str, str], call: ast.Call, argv0: str) -> SpawnKind:
    return _classify_kind(qualname, _shell_signal_from_call(call), argv0)


def _digest(node: ast.AST | None) -> str:
    text = ast.unparse(node) if node is not None else ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _first_arg(call: ast.Call) -> ast.AST | None:
    if call.args:
        return call.args[0]
    return None


def _argv_bearing_arg(
    qualname: tuple[str, str] | None, call: ast.Call
) -> ast.AST | None:
    """The call's argv-bearing positional arg, accounting for mode-first spawns."""
    if qualname in _MODE_FIRST_SPAWN:
        return call.args[1] if len(call.args) > 1 else None
    return _first_arg(call)


class _ImportResolver:
    """Resolves module aliases and direct-callable aliases from imports."""

    def __init__(self, tree: ast.Module):
        self.module_alias: dict[str, str] = {}
        self.direct_alias: dict[str, tuple[str, str]] = {}
        self.shutil_module_alias: dict[str, str] = {}  # local name -> "shutil"
        self.which_direct_alias: set[str] = set()  # local names bound to shutil.which
        self.functools_module_alias: dict[str, str] = {}  # local name -> "functools"
        self.partial_direct_alias: set[str] = set()  # local names bound to functools.partial
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    real = alias.name.split(".")[0]
                    if real in _TRACKED_MODULES:
                        self.module_alias[alias.asname or alias.name] = real
                    if real == "shutil":
                        self.shutil_module_alias[alias.asname or real] = "shutil"
                    if real == "functools":
                        self.functools_module_alias[alias.asname or real] = "functools"
            elif isinstance(node, ast.ImportFrom):
                module = node.module
                if module in _TRACKED_MODULES:
                    for alias in node.names:
                        local = alias.asname or alias.name
                        self.direct_alias[local] = (module, alias.name)
                if module == "shutil":
                    for alias in node.names:
                        if alias.name == "which":
                            self.which_direct_alias.add(alias.asname or "which")
                if module == "functools":
                    for alias in node.names:
                        if alias.name == "partial":
                            self.partial_direct_alias.add(alias.asname or "partial")

    def resolve_which_call(self, call: ast.Call) -> ast.AST | None:
        """Returns the first-arg node of a `shutil.which(...)` (or aliased) call, else None."""
        func = call.func
        if isinstance(func, ast.Attribute) and func.attr == "which" and isinstance(
            func.value, ast.Name
        ):
            if self.shutil_module_alias.get(func.value.id) == "shutil":
                return call.args[0] if call.args else None
            return None
        if isinstance(func, ast.Name) and func.id in self.which_direct_alias:
            return call.args[0] if call.args else None
        return None

    def resolve_call_target(self, func: ast.AST) -> tuple[str, str] | None:
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            base = func.value.id
            module = self.module_alias.get(base)
            if module is not None:
                candidate = (module, func.attr)
                if candidate in _RECOGNIZED:
                    return candidate
            return None
        if isinstance(func, ast.Name):
            candidate = self.direct_alias.get(func.id)
            if candidate is not None and candidate in _RECOGNIZED:
                return candidate
            return None
        if isinstance(func, ast.Call) and isinstance(func.func, ast.Name) and func.func.id == "getattr":
            # `getattr(MODULE, "attr")(...)` dynamic-dispatch — resolved only
            # when both the module and the attribute name are literal, static
            # values; a genuinely dynamic attribute name (a variable, an
            # expression) is not statically resolvable and stays unresolved
            # (None) rather than guessed — same fail-closed posture as every
            # other unresolvable shape here, not a special-case for `os`.
            if len(func.args) >= 2:
                base_node, attr_node = func.args[0], func.args[1]
                if (
                    isinstance(base_node, ast.Name)
                    and isinstance(attr_node, ast.Constant)
                    and isinstance(attr_node.value, str)
                ):
                    module = self.module_alias.get(base_node.id)
                    if module is not None:
                        candidate = (module, attr_node.value)
                        if candidate in _RECOGNIZED:
                            return candidate
            return None
        return None

    def resolve_partial_call(
        self, call: ast.Call
    ) -> tuple[tuple[str, str], ast.AST | None, str] | None:
        """Resolves a `functools.partial(TARGET, ...)` (or aliased) call.

        Returns `(target_qualname, bound_argv_node, bound_shell_signal)` when
        `TARGET` is itself a recognized spawn call target, else None.
        `bound_argv_node` is the partial's first BOUND positional arg after
        the target (the argv `functools.partial(subprocess.run, ["ls"])`
        would forward) — None when no positional args are bound, meaning the
        argv comes from the eventual call site instead.
        """
        func = call.func
        is_partial_call = (
            isinstance(func, ast.Attribute)
            and func.attr == "partial"
            and isinstance(func.value, ast.Name)
            and self.functools_module_alias.get(func.value.id) == "functools"
        ) or (isinstance(func, ast.Name) and func.id in self.partial_direct_alias)
        if not is_partial_call or not call.args:
            return None

        target_qualname = self.resolve_call_target(call.args[0])
        if target_qualname is None or target_qualname not in _RECOGNIZED:
            return None

        bound_argv_node = call.args[1] if len(call.args) > 1 else None
        bound_shell_signal = _shell_signal_from_call(call)
        return target_qualname, bound_argv_node, bound_shell_signal


def _module_level_constants(tree: ast.Module) -> dict[str, str]:
    consts: dict[str, str] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            consts[node.targets[0].id] = node.value.value
    return consts


@dataclasses.dataclass
class _PartialInfo:
    qualname: tuple[str, str]
    bound_argv_node: ast.AST | None
    bound_shell_signal: str


def _module_level_partials(
    tree: ast.Module, resolver: _ImportResolver
) -> dict[str, _PartialInfo]:
    """Resolves `NAME = functools.partial(TARGET, ...)`-shaped module-level
    bindings (`functools.partial(subprocess.run, shell=True)` and similar) —
    the evasion class the detector's `_RECOGNIZED` call-target resolution and
    `_local_helpers` (which only recognizes `def`/`async def`) both miss
    entirely: `NAME(...)` calls are invisible spawn sites otherwise, not a
    downgrade to SHELL_UNKNOWN.

    One-hop, module-level only — matches `_local_helpers`'s scope, not
    general dataflow.
    """
    partials: dict[str, _PartialInfo] = {}
    for node in tree.body:
        if not (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Call)
        ):
            continue
        resolved = resolver.resolve_partial_call(node.value)
        if resolved is None:
            continue
        qualname, bound_argv_node, bound_shell_signal = resolved
        partials[node.targets[0].id] = _PartialInfo(
            qualname=qualname,
            bound_argv_node=bound_argv_node,
            bound_shell_signal=bound_shell_signal,
        )
    return partials


@dataclasses.dataclass
class _HelperInfo:
    param_index: int
    shell_true: bool


def _local_helpers(
    tree: ast.Module, resolver: _ImportResolver
) -> dict[str, _HelperInfo]:
    """Resolve one hop of local-helper indirection.

    `def _run(a): subprocess.run(a)` called as `_run(['bash', script])`
    is recognized; a helper is only recorded if it forwards exactly one
    recognized spawn call whose argv expression is a bare parameter Name.
    Ambiguous (multiple candidate calls) or unresolvable helpers are
    skipped, never crashed on.
    """
    helpers: dict[str, _HelperInfo] = {}
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        arg_names = [a.arg for a in node.args.args]
        candidates: list[_HelperInfo] = []
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Call):
                continue
            qualname = resolver.resolve_call_target(inner.func)
            if qualname is None:
                continue
            argv_expr = _argv_bearing_arg(qualname, inner)
            if isinstance(argv_expr, ast.Name) and argv_expr.id in arg_names:
                candidates.append(
                    _HelperInfo(
                        param_index=arg_names.index(argv_expr.id),
                        shell_true=(
                            qualname in _INHERENT_SHELL_TRUE
                            or _shell_signal_from_call(inner) == "true"
                        ),
                    )
                )
        if len(candidates) == 1:
            helpers[node.name] = candidates[0]
    return helpers


def _iter_own_scope(node: ast.AST):
    """Yields descendant nodes without crossing into a nested function/lambda/class scope."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            continue
        yield child
        yield from _iter_own_scope(child)


def _resolve_binding_value(
    value_node: ast.AST, resolver: _ImportResolver, module_consts: dict[str, str]
) -> str | None:
    if isinstance(value_node, ast.Constant) and isinstance(value_node.value, str):
        return value_node.value

    if isinstance(value_node, ast.Call):
        which_arg = resolver.resolve_which_call(value_node)
        if which_arg is not None:
            return _resolve_binding_value(which_arg, resolver, module_consts)

        func = value_node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "get"
            and isinstance(func.value, ast.Attribute)
            and func.value.attr == "environ"
            and isinstance(func.value.value, ast.Name)
            and func.value.value.id == "os"
            and len(value_node.args) >= 2
        ):
            return _resolve_binding_value(value_node.args[1], resolver, module_consts)
        return None

    if isinstance(value_node, ast.Name):
        if value_node.id in module_consts:
            return module_consts[value_node.id]
        return None

    if isinstance(value_node, ast.BinOp) and isinstance(value_node.op, ast.Add):
        left = _resolve_binding_value(value_node.left, resolver, module_consts)
        right = _resolve_binding_value(value_node.right, resolver, module_consts)
        if left is not None and right is not None:
            return left + right
        return None

    return None


def _single_static_bindings(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    resolver: _ImportResolver,
    module_consts: dict[str, str],
) -> dict[str, str]:
    """Resolves local names with exactly one statically-knowable binding.

    Bounded and conservative: a name with two-or-more bindings, a loop target,
    an augmented assignment, a function parameter, or a global/nonlocal
    declaration is excluded — a wrong concrete answer is worse than <dynamic>.
    Only bindings within `func_node`'s own body are considered; this is
    single-static-binding lookup within one function body, not general
    dataflow, and it does not cross into a nested function/lambda scope.
    """
    args = func_node.args
    param_names = {a.arg for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)}
    if args.vararg:
        param_names.add(args.vararg.arg)
    if args.kwarg:
        param_names.add(args.kwarg.arg)

    disqualified: set[str] = set(param_names)
    binding_counts: dict[str, int] = {}
    binding_values: dict[str, str | None] = {}

    for stmt in _iter_own_scope(func_node):
        if isinstance(stmt, (ast.Global, ast.Nonlocal)):
            disqualified.update(stmt.names)
        elif isinstance(stmt, ast.AugAssign) and isinstance(stmt.target, ast.Name):
            disqualified.add(stmt.target.id)
        elif isinstance(stmt, (ast.For, ast.AsyncFor)):
            for target in ast.walk(stmt.target):
                if isinstance(target, ast.Name):
                    disqualified.add(target.id)
        elif isinstance(stmt, ast.Assign):
            if len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
                name = stmt.targets[0].id
                binding_counts[name] = binding_counts.get(name, 0) + 1
                binding_values[name] = _resolve_binding_value(
                    stmt.value, resolver, module_consts
                )
            else:
                for target in stmt.targets:
                    for sub in ast.walk(target):
                        if isinstance(sub, ast.Name):
                            disqualified.add(sub.id)

    resolved: dict[str, str] = {}
    for name, count in binding_counts.items():
        if name in disqualified or count != 1:
            continue
        value = binding_values.get(name)
        if value is not None:
            resolved[name] = value
    return resolved


class _SiteCollector(ast.NodeVisitor):
    def __init__(
        self,
        path: str,
        module_consts: dict[str, str],
        resolver: _ImportResolver,
        helpers: dict[str, _HelperInfo],
        partials: dict[str, _PartialInfo],
    ):
        self.path = path
        self.module_consts = module_consts
        self.resolver = resolver
        self.helpers = helpers
        self.partials = partials
        self.scope_stack: list[str] = []
        self.local_bindings_stack: list[dict[str, str]] = []
        self.sites: list[SpawnSite] = []
        self._ordinals: dict[str, int] = {}

    @property
    def _enclosing(self) -> str:
        return ".".join(self.scope_stack) if self.scope_stack else "<module>"

    @property
    def _current_locals(self) -> dict[str, str]:
        return self.local_bindings_stack[-1] if self.local_bindings_stack else {}

    def _next_ordinal(self) -> int:
        key = self._enclosing
        ordinal = self._ordinals.get(key, 0)
        self._ordinals[key] = ordinal + 1
        return ordinal

    def _emit(self, argv_node: ast.AST | None, kind: SpawnKind, lineno: int) -> None:
        argv0 = _resolve_argv0(argv_node, self.module_consts, self._current_locals)
        self.sites.append(
            SpawnSite(
                path=self.path,
                enclosing=self._enclosing,
                argv0=argv0,
                ordinal=self._next_ordinal(),
                kind=kind,
                argv_digest=_digest(argv_node),
                lineno=lineno,
            )
        )

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.scope_stack.append(node.name)
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_func(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_func(node)

    def _visit_func(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.scope_stack.append(node.name)
        self.local_bindings_stack.append(
            _single_static_bindings(node, self.resolver, self.module_consts)
        )
        self.generic_visit(node)
        self.local_bindings_stack.pop()
        self.scope_stack.pop()

    def visit_Call(self, node: ast.Call) -> None:
        qualname = self.resolver.resolve_call_target(node.func)
        if qualname is not None:
            argv_node = _argv_bearing_arg(qualname, node)
            argv0 = _resolve_argv0(argv_node, self.module_consts, self._current_locals)
            kind = _classify(qualname, node, argv0)
            self._emit(argv_node, kind, node.lineno)
        elif isinstance(node.func, ast.Name) and node.func.id in self.partials:
            partial = self.partials[node.func.id]
            argv_node = (
                partial.bound_argv_node
                if partial.bound_argv_node is not None
                else _argv_bearing_arg(partial.qualname, node)
            )
            argv0 = _resolve_argv0(argv_node, self.module_consts, self._current_locals)
            signal = _explicit_shell_signal(node)
            if signal is None:
                signal = partial.bound_shell_signal
            kind = _classify_kind(partial.qualname, signal, argv0)
            self._emit(argv_node, kind, node.lineno)
        elif isinstance(node.func, ast.Name) and node.func.id in self.helpers:
            helper = self.helpers[node.func.id]
            argv_node = (
                node.args[helper.param_index]
                if helper.param_index < len(node.args)
                else None
            )
            argv0 = _resolve_argv0(argv_node, self.module_consts, self._current_locals)
            kind = SpawnKind.SHELL_TRUE if helper.shell_true else _classify(
                ("", ""), node, argv0
            )
            self._emit(argv_node, kind, node.lineno)
        self.generic_visit(node)


def sites_in_source(text: str, path: str) -> list[SpawnSite]:
    """Core API. Pure — text in, sites out. No disk access.

    Raises SpawnParseError if `text` will not parse.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        raise SpawnParseError(path, str(exc)) from exc

    resolver = _ImportResolver(tree)
    module_consts = _module_level_constants(tree)
    helpers = _local_helpers(tree, resolver)
    partials = _module_level_partials(tree, resolver)
    collector = _SiteCollector(path, module_consts, resolver, helpers, partials)
    collector.visit(tree)
    return collector.sites


DEFAULT_EXCLUDE: tuple[str, ...] = (
    "scratch",
    "scratchpad",
    ".venv",
    "venv",
    "node_modules",
    "build",
    ".git",
    "__pycache__",
)
"""Directory names never walked by default.

Two distinct reasons, both meaning "not claude-klabauter's source":

- `scratch`/`scratchpad` hold committed snapshot copies of engine files, which
  carry their own spawn sites and would be double-counted against the originals.
- `.venv`/`venv`/`node_modules`/`build` are vendored or generated third-party
  trees. Their spawn sites are real but are not ours to convert or to sanction, and
  a register entry naming one would be re-blessed on every dependency bump.

`dist` is deliberately NOT in this list. In this repo `dist/` holds claude-klabauter's
own git-tracked percolate publish-mirror output (`dist/mirror-native/...`) —
real, committed production source, not a vendored/generated third-party tree.
A bare-directory-name exclude cannot distinguish "vendored" from "our own
staged-for-publish output" that happens to share a conventional dirname; the
9df7d16ba commit that added `dist` here matched on name alone and silently
hid real subprocess call sites from the census, gate, and guard. If a
genuinely vendored tree ever needs excluding, name it explicitly by path
(vendored-tree list) rather than reintroducing a bare `dist`/`build`-shaped
name match that a real source directory could collide with again.
"""


_SHEBANG_PYTHON_RE = re.compile(r"\bpython[0-9.]*\b", re.IGNORECASE)

_SHEBANG_PROBE_BYTES = 256


def _has_python_shebang(file_path: pathlib.Path) -> bool:
    """True if `file_path`'s first line is a `#!` line naming a Python interpreter.

    Reads at most `_SHEBANG_PROBE_BYTES` bytes — enough to see the shebang
    line, never the whole file. Never raises: an unreadable file (permission
    error, vanished mid-walk, etc.) is treated as "not Python" rather than
    crashing the walk, matching `walk_repo`'s existing skip-safely posture
    for excluded directories.
    """
    try:
        with file_path.open("rb") as f:
            head = f.read(_SHEBANG_PROBE_BYTES)
    except OSError:
        return False

    newline = head.find(b"\n")
    first_line = head if newline == -1 else head[:newline]
    if not first_line.startswith(b"#!"):
        return False

    text = first_line.decode("utf-8", errors="replace")
    return bool(_SHEBANG_PYTHON_RE.search(text))


_PYTHON_PREAMBLE_STARTS = (b'"""', b"'''")


def _has_python_preamble(file_path: pathlib.Path) -> bool:
    """True if `file_path`'s first line opens a module docstring
    (`\"\"\"`/`'''`) or is a `#`-prefixed comment that is not a `#!` shebang.

    Same bounded-read shape as `_has_python_shebang` — a preamble check, not
    a parse. This is the naked-Python-CLI convention used under `coordinator/
    bin/` for scripts invoked as `python3 coordinator/bin/<name>` rather than
    executed directly, so they carry neither a `.py` suffix nor a shebang.
    """
    try:
        with file_path.open("rb") as f:
            head = f.read(_SHEBANG_PROBE_BYTES)
    except OSError:
        return False

    newline = head.find(b"\n")
    first_line = head if newline == -1 else head[:newline]
    stripped = first_line.strip()
    if stripped.startswith(_PYTHON_PREAMBLE_STARTS):
        return True
    return stripped.startswith(b"#") and not stripped.startswith(b"#!")


def _parses_as_python(file_path: pathlib.Path) -> bool:
    """True if `file_path`'s full contents parse as Python source.

    Only reached for an already-preamble-matched extensionless `bin/` file
    (see `_is_python_source`) — a non-Python config file that merely opens
    with a `#` comment, e.g. `bin/.percolate-ignore`, would otherwise be
    admitted by `_has_python_preamble` alone and then blow up as a
    `SpawnParseError` once `walk_repo` tried to actually parse it. This is
    the final gate, not a preview: never raises, treats an unreadable or
    unparseable file as "not Python" the same way the shebang path does.
    """
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    try:
        ast.parse(text)
    except SyntaxError:
        return False
    return True


def _is_python_source(file_path: pathlib.Path, rel: pathlib.Path | None = None) -> bool:
    """True for a `*.py` file, an extensionless/non-`.py` file with a
    `#!...python` shebang, or — when `rel` places it under a `bin/`
    directory — an extensionless file whose head has a Python module
    preamble (docstring or non-shebang comment) AND whose full contents
    parse as Python.

    The `bin/`-only carve-out bounds the preamble/parse pair to the naked-
    Python-CLI convention it exists for, rather than running it (and
    risking a false-positive admit, or an expensive parse) against every
    extensionless file in the repo. The parse step is what tells a real
    naked-Python CLI apart from a non-Python file that merely starts with
    `#`, like a `.percolate-ignore` list.
    """
    if file_path.suffix == ".py":
        return True
    if _has_python_shebang(file_path):
        return True
    if rel is not None and file_path.suffix == "" and "bin" in rel.parts:
        return _has_python_preamble(file_path) and _parses_as_python(file_path)
    return False


def discover_source_files(
    root: pathlib.Path,
    *,
    exclude: tuple[str, ...] = DEFAULT_EXCLUDE,
) -> tuple[list[tuple[str, pathlib.Path]], ExcludedReport]:
    """Discovery half of the walk: which files are Python, and what was excluded.

    Split out from `walk_repo` so a parallelising consumer (`coordinator/bin/
    spawn-census`) can reuse the traversal instead of mirroring it. That mirror
    is how the census and the gate came to disagree about scope twice — once on
    the exclude list, once on shebang-dispatched extensionless scripts — so the
    single definition this plan enforces for the *rule* has to extend to the
    *traversal* too, or the two drift apart again on the next change here.

    Returns `[(repo_relative_posix_path, absolute_path), ...]` in sorted order,
    plus the exclusion report. Ordering is part of the contract: the census
    pins byte-identical output between its serial and parallel paths.
    """
    root = pathlib.Path(root)
    discovered: list[tuple[str, pathlib.Path]] = []
    excluded_dirs: set[str] = set()
    suppressed_count = 0

    for file_path in sorted(root.rglob("*")):
        if not file_path.is_file():
            continue

        rel = file_path.relative_to(root)
        parts = rel.parts
        excluded_at: str | None = None
        for idx, part in enumerate(parts):
            if part in exclude:
                excluded_at = "/".join(parts[: idx + 1])
                break

        if excluded_at is not None:
            excluded_dirs.add(excluded_at)
            # suppressed_site_count counts excluded *.py files only, matching
            # the pre-existing contract (an excluded file is never opened to
            # check for a shebang either — this is directory-level skip, not
            # per-file classification).
            if file_path.suffix == ".py":
                suppressed_count += 1
            continue

        if not _is_python_source(file_path, rel):
            continue

        discovered.append((rel.as_posix(), file_path))

    return discovered, ExcludedReport(
        paths=sorted(excluded_dirs), suppressed_site_count=suppressed_count
    )


def walk_repo(
    root: pathlib.Path,
    *,
    exclude: tuple[str, ...] = DEFAULT_EXCLUDE,
) -> tuple[list[SpawnSite], ExcludedReport]:
    """Walker over `*.py` files AND shebang-dispatched naked-Python scripts
    (no `.py` suffix, `#!.../python[0-9.]*` first line) under `root`,
    delegating to `sites_in_source`.
    """
    discovered, excluded = discover_source_files(root, exclude=exclude)

    included: list[SpawnSite] = []
    for rel_posix, file_path in discovered:
        text = file_path.read_text(encoding="utf-8")
        included.extend(sites_in_source(text, rel_posix))

    return included, excluded


def site_key(obj) -> tuple[str, str, str, int]:
    """Structural identity: (path, enclosing, argv0, ordinal). Excludes argv_digest and lineno."""
    return (obj.path, obj.enclosing, obj.argv0, obj.ordinal)


def is_test_tree_site(path: str | pathlib.Path) -> bool:
    """True if `path` is in the test tree: a `tests/` directory component, or a `test_*` basename.

    POST-WALK predicate ONLY. `walk_repo`'s `exclude` filters by directory
    NAME and has no basename-prefix concept, so this predicate must never be
    passed to `walk_repo` as an `exclude` entry — the `test_*`-basename half
    of the rule would silently match nothing there, misclassifying the whole
    test tree as production. Apply it after the walk, per site, the way
    `discover_source_files`'s own docstring warns: re-deriving traversal or
    classification logic instead of importing the single shared definition is
    exactly how the census and the gate drifted apart twice before (the
    exclude list once, shebang-dispatched scripts once).

    Relocated from `test_no_unsanctioned_shell_spawn.py`'s private
    `_is_test_tree_site`: True when a `tests` directory appears anywhere
    except the final path component, or the basename starts with `test_`.

    Superset-safe addition over the relocated version: this public copy
    normalizes `\\` to `/` before splitting, since the exported signature now
    accepts a `pathlib.Path` (which the private original never did). All real
    callers already pass posix-normalized strings, so this is not a
    classification change for them — but a caller passing a genuinely
    mixed-separator or backslash-only string will classify differently than
    the original private predicate did.

    Residual limitation, not just an unusual-input edge case: `PureWindowsPath`
    is a pure parser and treats `\\` as a separator unconditionally, on every
    host, regardless of the OS this code actually runs on. This fix removes
    the separator-blindness that mangled genuine mixed-separator input on the
    main path — but it does not, and cannot, make the predicate able to
    represent a POSIX filename that legitimately contains a literal backslash;
    such a filename is still misclassified after this fix, on every host.
    """
    normalized = pathlib.PureWindowsPath(str(path)).as_posix()
    parts = pathlib.PurePosixPath(normalized).parts
    if "tests" in parts[:-1]:
        return True
    basename = parts[-1] if parts else ""
    return basename.startswith("test_")
