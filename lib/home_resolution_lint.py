"""Shared engine: four structural (AST-based) scans for the home-resolution
cross-platform-portability defect class -- code that resolves a user's home
directory, a PATH-list, or a settings/trusted-root path in a way that works
on the host its author sits at and quietly degrades on another.

The framing is portability, not "Windows-correctness", because macOS,
Windows and Linux are all first-class (P0): a resolution that degrades on
any one of the three is a correctness defect, not a platform nice-to-have.
Windows is where every rule below currently bites, and the rule bodies are
written against Windows behaviour precisely for that reason -- but the
defect class is "breaks on a host that is not yours", and a future rung for
a non-Windows host belongs in this same engine rather than a second one.

Concretely, today: PowerShell/cmd.exe set `USERPROFILE`, never `HOME`;
Windows uses `;` not `:` as its path-list separator; a raw drive-letter or
MSYS-mount path defeats a forward-slash-only split; and
`os.access(p, os.X_OK)` degrades to a meaningless `F_OK` check on Windows.

Spec backlink: extracted from the inline rule logic that first landed in
`coordinator_core/tests/test_home_resolution_lint.py` (commit `c1545206`,
2026-07-28), which found 98 live violations in this repo (70 X_OK, 18
bare-or-chain, 9 forward-slash, 1 colon-join). Extraction design:
`DoE-claude/docs/research/2026-07-28-fleet-lint-distribution-design.md`
(the DoE distribution blueprint). This module is a behavior-preserving
extraction -- same AST logic, same matching semantics -- not a rewrite.

**Why this file lives here and not vendored per-repo.** This path
(`claude-klabauter/coordinator/lib/`) is already covered by the `bin,lib`
multi-source percolation row (`DoE-claude/setup/publish-targets.portable`),
so it reaches the OSS mirror with zero new allowlist configuration, and it
respects the DoE-prose/claude-klabauter-engine plane split (a lint is executable
Python -- engine-subject, not doctrine). Every consuming repo (including
this one's own test suite, see the shim at
`coordinator_core/tests/test_home_resolution_lint.py`) imports this module
live rather than vendoring a copy: a fifth rule is one edit here, and every
repo picks it up on its next test run with no re-publish, no re-vendor, no
drift between copies.

**What is repo-local, never in this file.** Scan roots, exclusions, the
forward-slash scope list, and the debt ledger are all supplied by the
CALLER (the per-repo shim) via `HomeResolutionLintEngine`'s constructor
arguments -- this module carries no repo-specific paths or baseline data at
all. See `HomeResolutionLintEngine` docstring for the exact contract.

**Known miss -- `bare_or`'s ladder-extraction seam (`_iter_ladder_sites`),
declared rather than papered over.** The ternary-over-locally-bound-env-read
shape -- `claude_home = os.environ.get("CLAUDE_HOME")` on one line, then
`(Path(claude_home) if claude_home else Path.home())` on the next -- is NOT
extracted as a ladder site. The seam's standalone-ternary pass reasons only
over its own `test`/`body`/`orelse` nodes and does not resolve an
intra-function name binding back to the `os.environ.get(...)` call it was
assigned from. The `if`/`return` guard-ladder pass is NOT under this same
limit -- it DOES resolve a `test`/return value that is a bare `Name` bound
by a preceding top-level assignment in the same function body (the live
fleet's dominant guard-ladder shape actually needs this) -- see
`HomeResolutionLintEngine._extract_guard_ladder` for the exact, narrower-
than-general-data-flow rule it applies. Fixing the ternary form the same way
needs the same category of statement-level data-flow work already declined
for the `x_ok` rule's early-return guard-clause shape (see
`find_x_ok_checks`'s own "Explicitly NOT recognised" note).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
import json
import sys
from pathlib import Path
from typing import Iterable, Sequence

ENGINE_VERSION = "2026-08-08.3"

DEFAULT_EXCLUDED_PARTS: frozenset[str] = frozenset(
    {
        "__pycache__",
        ".venv",
        "venv",
        "node_modules",
        "archive",
        "state",
        "tasks",
        "scratch",
        "scratchpad",
        "cross-repo",
        "pip",
    }
)

RULE_NAMES: tuple[str, ...] = ("x_ok", "colon_join", "forward_slash", "bare_or", "rung_order")

RULE_LABELS: dict[str, str] = {
    "x_ok": "os.access(..., os.X_OK)",
    "colon_join": "literal ':' PATH-list join/split",
    "forward_slash": "forward-slash-only path split",
    "bare_or": "CLAUDE_HOME/HOME or-chain with no USERPROFILE rung",
    "rung_order": "home-resolution ladder rung out of master order",
}

RULE_REMEDIATION: dict[str, str] = {
    "x_ok": (
        "os.access(path, os.X_OK) degrades to F_OK on Windows -- use "
        "path.is_file() instead, or, where executability genuinely matters, "
        "gate the call on a guard that provably excludes Windows execution: "
        "`if os.name != \"nt\":`, `if os.name == \"posix\":`, or "
        "`if sys.platform != \"win32\":` (direct or nested inside the guard's "
        "body). A call reachable only through the inverted test -- "
        "`os.name == \"nt\"` / `sys.platform == \"win32\"` -- runs only on "
        "Windows and is still flagged, not exempted."
    ),
    "colon_join": (
        "A literal ':' PATH-list join/split is POSIX-only -- Windows uses "
        "';'. Use os.pathsep instead."
    ),
    "forward_slash": (
        "A forward-slash-only path split is invisible to POSIX-only test "
        "fixtures and mishandles a real Windows backslash path. Fold the "
        'backslash first (.replace("\\\\", "/")) before splitting, or split '
        "on os.sep."
    ),
    "bare_or": (
        "PowerShell/cmd.exe never set HOME, so a CLAUDE_HOME/HOME or-chain "
        "with no USERPROFILE rung degrades to '' on Windows and yields a "
        'cwd-relative path. Add os.environ.get("USERPROFILE") as a fallback '
        "rung, or delegate to Path.home(), which already honours "
        "USERPROFILE."
    ),
    "rung_order": (
        "A home-resolution ladder's rungs must appear as a subsequence of "
        "the master order CLAUDE_HOME -> HOME -> USERPROFILE -> "
        "Path.home() -- skipping a rung is fine (CLAUDE_HOME -> USERPROFILE "
        "-> Path.home() is valid and Windows-correct), but a transposed "
        "rung (e.g. USERPROFILE checked before HOME) or a literal '~' rung "
        "is a violation, and an unguarded os.path.expanduser(...) rung is "
        "a warn (see HomeResolutionLintEngine.find_rung_order_warnings). "
        "Reorder the ladder to the master order, or replace the "
        "'~'/expanduser rung with the correct os.environ.get(...) / "
        "Path.home() call."
    ),
}


@dataclass(frozen=True)
class Finding:
    """One matched site: repo-relative path, 1-based line, stripped source text."""

    path: str
    line: int
    text: str

    def key(self) -> tuple[str, str]:
        """Text-keyed identity used for baseline matching -- see
        `HomeResolutionLintEngine` docstring."""
        return (self.path, self.text)


def _relpath(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _is_excluded(rel: Path, excluded_parts: frozenset[str]) -> bool:
    return any(part in excluded_parts for part in rel.parts)


def _in_forward_slash_scope(relpath: str, scope: Sequence[str]) -> bool:
    return any(relpath == scoped or relpath.startswith(scoped + "/") for scoped in scope)


def _parse(path: Path):
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None, None
    try:
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, ValueError, RecursionError):
        # SyntaxError: the common case, and (on Python 3.13, this repo's dev
        # box) also what an embedded null byte raises. ValueError: what the
        # SAME null-byte input raises on Python 3.11, this repo's floor
        # (requires-python = ">=3.11", pyproject.toml:12) -- a single-version
        # read would miss this arm. RecursionError: ast.parse's documented
        # stack-depth path on adversarial input, reachable now that
        # `iter_py_files` widens discovery to shebang-sniffed files.
        return None, None
    return tree, source.splitlines()


def _shebang_names_python(path: Path) -> bool:
    """True if `path`'s first line is a `#!` shebang naming a Python
    interpreter (`python`, `python3`, `python3.11`, a venv-relative
    interpreter path, ...) -- anything containing `python` after the `#!`.
    Reads only the first 256 bytes, as raw bytes rather than decoded text, so
    a non-UTF-8 or huge file (a vendored blob, before `DEFAULT_EXCLUDED_PARTS`
    would exclude it) is a cheap "not a match" rather than a decode error."""
    try:
        with path.open("rb") as fh:
            head = fh.read(256)
    except OSError:
        return False
    first_line = head.split(b"\n", 1)[0]
    if not first_line.startswith(b"#!"):
        return False
    return b"python" in first_line


def _attr_or_name(node) -> str | None:
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return None


def _line_text(lines: list[str], lineno: int) -> str:
    return lines[lineno - 1].strip() if 0 < lineno <= len(lines) else ""


def _dotted_name(node: ast.AST) -> str | None:
    """`os.name` / `sys.platform`-shaped attribute access -> `"os.name"`.
    Returns None for anything else (a bare Name, a deeper chain, a call)."""
    if not isinstance(node, ast.Attribute) or not isinstance(node.value, ast.Name):
        return None
    return f"{node.value.id}.{node.attr}"


def _guard_polarity(test: ast.expr) -> str | None:
    """Classifies an `if <test>:` guard as one of two shapes the X_OK rule
    reasons about, or `None` if the shape is not one this engine recognises
    (recognised-shape inventory lives on `find_x_ok_checks`'s docstring;
    keep that list and this function in lockstep).

    - `"windows_excluded"` -- the guarded body provably cannot execute on
      Windows (`os.name != "nt"`, `os.name == "posix"`,
      `sys.platform != "win32"`). A call lexically inside this body is safe
      to exempt.
    - `"windows_only"` -- the guarded body provably executes ONLY on
      Windows (`os.name == "nt"`, `sys.platform == "win32"`) -- the
      deliberately-covered inversion (task step 2): never exempted, and its
      `else:` branch (if present) IS `"windows_excluded"` and so eligible.
    """
    if not isinstance(test, ast.Compare) or len(test.ops) != 1 or len(test.comparators) != 1:
        return None
    op = test.ops[0]
    comparator = test.comparators[0]
    if not (isinstance(comparator, ast.Constant) and isinstance(comparator.value, str)):
        return None
    left_name = _dotted_name(test.left)
    if left_name == "os.name":
        if isinstance(op, ast.NotEq) and comparator.value == "nt":
            return "windows_excluded"
        if isinstance(op, ast.Eq) and comparator.value == "posix":
            return "windows_excluded"
        if isinstance(op, ast.Eq) and comparator.value == "nt":
            return "windows_only"
    elif left_name == "sys.platform":
        if isinstance(op, ast.NotEq) and comparator.value == "win32":
            return "windows_excluded"
        if isinstance(op, ast.Eq) and comparator.value == "win32":
            return "windows_only"
    return None


class HomeResolutionLintEngine:
    """Constructed per-repo by a thin shim; owns no repo-specific state
    beyond what its constructor is handed.

    `repo_root` -- the repo to scan.
    `scan_roots` -- directories under `repo_root` to walk (e.g.
        `("coordinator_core", "coordinator", "bin", "scripts")`). A scan
        root that does not exist under `repo_root` is skipped silently --
        most repos will not have all of a generic default list.
    `excluded_parts` -- path-component names to skip anywhere in a
        candidate file's path (defaults to `DEFAULT_EXCLUDED_PARTS`).
    `forward_slash_scope` -- relative-path prefixes (files or directories)
        that Rule 3 (forward-slash-only split) is narrowed to. Empty by
        default -- a repo opts in explicitly only if it has its own
        settings-home/trusted-root resolution-code family; this scope list
        must never default to a wildcard (see module docstring's
        "Security" note in the distribution design: a repo should not
        silently inherit a scope tuned for a *different* repo's file
        layout).

    Every `find_*` method returns a fresh `list[Finding]` -- no caching
    across calls, since a single process may construct engines for
    multiple `repo_root`s (e.g. this repo's own test suite plus a parity
    check against a sibling repo in the same pytest session).
    """

    def __init__(
        self,
        repo_root: Path,
        scan_roots: Sequence[str],
        excluded_parts: frozenset[str] = DEFAULT_EXCLUDED_PARTS,
        forward_slash_scope: Sequence[str] = (),
    ) -> None:
        self.repo_root = Path(repo_root)
        self.scan_roots = tuple(scan_roots)
        self.excluded_parts = excluded_parts
        self.forward_slash_scope = tuple(forward_slash_scope)

    def iter_py_files(self) -> Iterable[Path]:
        """Yields both populations, `_is_excluded`-filtered and
        deduplicated: `*.py` files, and extensionless files whose first line
        is a Python shebang (`coordinator/bin/archive-stamp-cli`-shaped --
        see `state/lessons/2026-07-28-grep-include-py-hides-this-repo-s-extens-e85a40277f72.yaml`).
        Return order stays `sorted` so baseline keys do not churn."""
        for name in self.scan_roots:
            scan_root = self.repo_root / name
            if not scan_root.is_dir():
                continue
            candidates: set[Path] = set()
            for path in scan_root.rglob("*.py"):
                if not _is_excluded(path.relative_to(scan_root), self.excluded_parts):
                    candidates.add(path)
            for path in scan_root.rglob("*"):
                if path.suffix or not path.is_file():
                    continue
                if _is_excluded(path.relative_to(scan_root), self.excluded_parts):
                    continue
                if _shebang_names_python(path):
                    candidates.add(path)
            yield from sorted(candidates)

    def scanned_file_count(self) -> int:
        return sum(1 for _ in self.iter_py_files())

    def parse_failure_count(self) -> int:
        """Count of files under `iter_py_files()` that fail to parse --
        `_parse`'s `(OSError, UnicodeDecodeError)` read-failure arm plus its
        `(SyntaxError, ValueError, RecursionError)` `ast.parse` arm. A
        diagnostic independent of any rule's finding list, so a "clean" run
        (0 findings, 0 parse failures) is distinguishable from a run that
        silently gave up on part of the corpus. Never raises."""
        count = 0
        for path in self.iter_py_files():
            tree, _ = _parse(path)
            if tree is None:
                count += 1
        return count

    # -- Rule 1: os.access(path, os.X_OK) -- meaningless on Windows. -----

    @staticmethod
    def _is_x_ok_call(node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Call)
            and len(node.args) >= 2
            and _attr_or_name(node.func) == "access"
            and _attr_or_name(node.args[1]) == "X_OK"
        )

    def find_x_ok_checks(self) -> list[Finding]:
        """AST: `os.access(..., os.X_OK)` calls. AST, not regex: a regex on
        `os.access` also matches the legitimate `os.R_OK`/`os.W_OK` calls;
        AST inspects the second *argument* specifically.

        **Guard-exemption (deliberately narrow -- see `_guard_polarity`).**
        A call is exempt only when EVERY enclosing `if` on its lexical path
        from the module root includes at least one recognised
        `"windows_excluded"` guard on that path -- i.e. the call is
        reachable, directly or nested arbitrarily deep, only through a body
        that provably cannot execute on Windows. Recognised shapes:

          - `if os.name != "nt":` / `if os.name == "posix":` -- body exempt.
          - `if sys.platform != "win32":` -- body exempt.
          - `if os.name == "nt":` / `if sys.platform == "win32":` -- the
            INVERSE (task step 2): the guarded body executes only on
            Windows and is never exempt (still reported, same as an
            unguarded call); the guard's own `else:` branch, if present, IS
            exempt (it is `"windows_excluded"`).
          - Short-circuit operands of a single test:
            `os.name != "nt" and ... and os.access(p, os.X_OK)` -- exempt,
            and symmetrically `os.name == "nt" or os.access(...)`. Python
            guarantees `and` stops at the first falsey operand and `or` at
            the first truthy one, so a recognised guard exempts every
            operand to its RIGHT (never to its left). This is the same
            proof as lexical body containment, not a weaker approximation.

        **Explicitly NOT recognised** (a call guarded only by one of these
        shapes is still reported -- do not treat silence as safety):
        `sys.platform.startswith("win")`, `platform.system() == "Windows"`,
        `os.name != "posix"` (excludes `nt` but not every other non-posix
        name, so it is not provably Windows-safe), a guard stored in a variable
        and branched on later, and any early-return / guard-clause shape
        (`if os.name == "nt": return` / `pytest.skip(...)` followed by
        unguarded sibling statements) -- that shape needs flow analysis
        across sibling statements, not the single-`if`-body/`orelse` lexical
        containment this method checks, and is left unimplemented rather
        than approximated unsoundly.
        """
        findings: list[Finding] = []
        for path in self.iter_py_files():
            tree, lines = _parse(path)
            if tree is None:
                continue
            relpath = _relpath(self.repo_root, path)
            findings.extend(self._scan_x_ok_in_tree(tree, relpath, lines))
        return findings

    def _scan_x_ok_in_tree(self, tree: ast.AST, relpath: str, lines: list[str]) -> list[Finding]:
        findings: list[Finding] = []

        def visit(node: ast.AST, safe_depth: int) -> None:
            if self._is_x_ok_call(node):
                if safe_depth <= 0:
                    findings.append(Finding(relpath, node.lineno, _line_text(lines, node.lineno)))
                for child in ast.iter_child_nodes(node):
                    visit(child, safe_depth)
                return
            if isinstance(node, ast.BoolOp):
                # Short-circuit guard: an operand that provably excludes Windows exempts
                # every operand to its RIGHT, because Python guarantees `and` stops at the
                # first falsey operand and `or` at the first truthy one. Operands to the
                # left are unaffected -- depth accumulates strictly left-to-right.
                exempting = "windows_excluded" if isinstance(node.op, ast.And) else "windows_only"
                operand_depth = safe_depth
                for operand in node.values:
                    visit(operand, operand_depth)
                    if _guard_polarity(operand) == exempting:
                        operand_depth += 1
                return
            if isinstance(node, ast.If):
                polarity = _guard_polarity(node.test)
                visit(node.test, safe_depth)
                body_depth = safe_depth + 1 if polarity == "windows_excluded" else safe_depth
                for child in node.body:
                    visit(child, body_depth)
                orelse_depth = safe_depth + 1 if polarity == "windows_only" else safe_depth
                for child in node.orelse:
                    visit(child, orelse_depth)
                return
            for child in ast.iter_child_nodes(node):
                visit(child, safe_depth)

        visit(tree, 0)
        return findings

    # -- Rule 2: a literal ":" used to split/join a path-shaped variable. -

    def find_colon_path_joins(self) -> list[Finding]:
        """AST: `"<path-like var>".split(":")` -- the POSIX-only PATH-list
        separator. Windows uses `;`. Narrowed to receivers whose name
        contains "path" (case-insensitive) so an unrelated colon split
        (e.g. a `"key:value"` parse) does not fire."""
        findings: list[Finding] = []
        for path in self.iter_py_files():
            tree, lines = _parse(path)
            if tree is None:
                continue
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                    continue
                if node.func.attr != "split" or not node.args:
                    continue
                arg0 = node.args[0]
                if not (isinstance(arg0, ast.Constant) and arg0.value == ":"):
                    continue
                receiver_name = _attr_or_name(node.func.value)
                if not receiver_name or "path" not in receiver_name.lower():
                    continue
                findings.append(
                    Finding(_relpath(self.repo_root, path), node.lineno, _line_text(lines, node.lineno))
                )
        return findings

    # -- Rule 3: forward-slash-only path splitting, in a scoped family. --

    def find_forward_slash_only_splits(self) -> list[Finding]:
        """AST: `.rsplit("/", ...)` / `.split("/")` / `.endswith("/...")`
        calls whose enclosing function body never folds a backslash first.
        Scoped to `self.forward_slash_scope` (empty by default) --
        deliberately the loosest-confidence rule of the four (`/` splitting
        is often fine -- URLs, POSIX-only code), so it stays narrow rather
        than noisy. Returns `[]` immediately if the scope is empty."""
        if not self.forward_slash_scope:
            return []
        findings: list[Finding] = []
        for path in self.iter_py_files():
            relpath = _relpath(self.repo_root, path)
            if not _in_forward_slash_scope(relpath, self.forward_slash_scope):
                continue
            tree, lines = _parse(path)
            if tree is None:
                continue

            func_stack: list[ast.AST] = []
            local_findings = findings

            class _Visitor(ast.NodeVisitor):
                def visit_FunctionDef(self, node):  # noqa: N802
                    func_stack.append(node)
                    self.generic_visit(node)
                    func_stack.pop()

                visit_AsyncFunctionDef = visit_FunctionDef  # noqa: N815

                def visit_Call(self, node):  # noqa: N802
                    if isinstance(node.func, ast.Attribute):
                        attr = node.func.attr
                        hit = False
                        if attr in ("split", "rsplit") and node.args:
                            arg0 = node.args[0]
                            if isinstance(arg0, ast.Constant) and arg0.value == "/":
                                hit = True
                        elif attr == "endswith" and node.args:
                            arg0 = node.args[0]
                            if (
                                isinstance(arg0, ast.Constant)
                                and isinstance(arg0.value, str)
                                and arg0.value.startswith("/")
                            ):
                                hit = True
                        if hit:
                            enclosing = func_stack[-1] if func_stack else None
                            guarded = "replace" in ast.dump(enclosing) if enclosing is not None else False
                            if not guarded:
                                local_findings.append(
                                    Finding(relpath, node.lineno, _line_text(lines, node.lineno))
                                )
                    self.generic_visit(node)

            _Visitor().visit(tree)
        return findings

    # -- Rule 4 (highest value): CLAUDE_HOME/HOME or-chain, no USERPROFILE.

    @staticmethod
    def _is_environ_get_home(node: ast.AST) -> bool:
        if not isinstance(node, ast.Call):
            return False
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "get"):
            return False
        receiver_name = _attr_or_name(func.value)
        if receiver_name != "environ":
            return False
        if not node.args:
            return False
        arg0 = node.args[0]
        return isinstance(arg0, ast.Constant) and arg0.value in ("CLAUDE_HOME", "HOME")

    @staticmethod
    def _is_path_home_call(node: ast.AST) -> bool:
        """True only for a genuine no-arg `Path.home()` call -- an
        `Attribute(attr="home")` whose receiver dotted-names to `Path`.
        Structural, not textual: does not match `Path(home)` (a `Call`, not
        an `Attribute`) even though both contain the tokens `"Path"` and
        `"home"`."""
        if not isinstance(node, ast.Call) or node.args or node.keywords:
            return False
        func = node.func
        return isinstance(func, ast.Attribute) and func.attr == "home" and _attr_or_name(func.value) == "Path"

    @staticmethod
    def _contains_path_home_call(node: ast.AST) -> bool:
        """Structurally walks `node` for a genuine `Path.home()` call,
        recognising it reached through a wrapping call (`str(Path.home())`),
        a ternary (`Path(claude_home) if claude_home else Path.home()`), a
        path-join `BinOp` (`Path.home() / ".claude"`, both operands
        checked -- a real fleet idiom can put the call on either side, e.g.
        `".claude" if flag else Path.home() / suffix` nests it on the
        `right`), an attribute chain on top of the call
        (`Path.home().resolve()` -- `.attr` or `.method(...)` applied to a
        `Path.home()` receiver is still the same underlying call), or nested
        combinations of all of the above -- the shapes DoE-claude's fleet
        uses at its correct sites (guard-ladder `return Path.home() /
        ".claude"` reduces to this same expression-level check once C4
        extracts the returned value).

        Deliberately does NOT match on token/substring coincidence -- e.g.
        `Path(home).is_absolute()`, where `home` is an unrelated local
        variable name, is a `Call` to `.is_absolute()` wrapping a `Call` to
        `Path(home)`, neither of which is `Path.home()` itself, so this
        returns `False` for it. Likewise does not walk into `ast.Subscript`
        or arbitrary `ast.walk` -- only the specific wrapping shapes above,
        so a `Path.home()` mentioned merely somewhere inside an unrelated
        sibling subexpression is not mistaken for a terminal rung."""
        if HomeResolutionLintEngine._is_path_home_call(node):
            return True
        if isinstance(node, ast.Call):
            if HomeResolutionLintEngine._contains_path_home_call(node.func):
                return True
            return any(HomeResolutionLintEngine._contains_path_home_call(arg) for arg in node.args)
        if isinstance(node, ast.Attribute):
            return HomeResolutionLintEngine._contains_path_home_call(node.value)
        if isinstance(node, ast.BinOp):
            return HomeResolutionLintEngine._contains_path_home_call(
                node.left
            ) or HomeResolutionLintEngine._contains_path_home_call(node.right)
        if isinstance(node, ast.IfExp):
            return HomeResolutionLintEngine._contains_path_home_call(
                node.body
            ) or HomeResolutionLintEngine._contains_path_home_call(node.orelse)
        return False

    @staticmethod
    def _is_environ_get_userprofile(node: ast.AST) -> bool:
        """True only for a genuine `environ.get("USERPROFILE", ...)` call --
        mirrors `_is_environ_get_home`'s structural shape but gated on the
        `USERPROFILE` key specifically."""
        if not isinstance(node, ast.Call):
            return False
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "get"):
            return False
        if _attr_or_name(func.value) != "environ":
            return False
        if not node.args:
            return False
        arg0 = node.args[0]
        return isinstance(arg0, ast.Constant) and arg0.value == "USERPROFILE"

    @staticmethod
    def _contains_userprofile_rung(node: ast.AST) -> bool:
        """Structurally walks `node` for a genuine `environ.get("USERPROFILE",
        ...)` call, recognising EVERY wrapping shape `_contains_path_home_call`
        recognises for `Path.home()`: a wrapping call (`str(environ.get(
        "USERPROFILE"))`), a path-join `BinOp` (`environ.get("USERPROFILE") /
        ".claude"`, either operand), an attribute chain on top of the call
        (`environ.get("USERPROFILE").rstrip(...)`), a ternary, and nested
        combinations. Replaces the old raw-source-text `"USERPROFILE" in
        nearby` window match: a rung must structurally BE (or wrap) a
        USERPROFILE env read, not merely sit a few lines near one, to exempt
        a site.

        The `BinOp`/`Attribute` arms are the parity this docstring always
        claimed and the body did not carry: a site spelling its USERPROFILE
        rung as a path-join or a chained call went unrecognised and surfaced
        as a false-positive `bare_or` violation, while the byte-identical
        shape around `Path.home()` was accepted by the sibling walker."""
        if HomeResolutionLintEngine._is_environ_get_userprofile(node):
            return True
        if isinstance(node, ast.Call):
            if HomeResolutionLintEngine._contains_userprofile_rung(node.func):
                return True
            return any(HomeResolutionLintEngine._contains_userprofile_rung(arg) for arg in node.args)
        if isinstance(node, ast.Attribute):
            return HomeResolutionLintEngine._contains_userprofile_rung(node.value)
        if isinstance(node, ast.BinOp):
            return HomeResolutionLintEngine._contains_userprofile_rung(
                node.left
            ) or HomeResolutionLintEngine._contains_userprofile_rung(node.right)
        if isinstance(node, ast.IfExp):
            return HomeResolutionLintEngine._contains_userprofile_rung(
                node.body
            ) or HomeResolutionLintEngine._contains_userprofile_rung(node.orelse)
        return False

    @staticmethod
    def _is_environ_get_call(node: ast.AST) -> bool:
        """Any `<name>.environ.get(...)` call regardless of key -- used only
        to walk the NESTED default-arg rung of the shape-4 ladder
        (`os.environ.get('HOME', os.environ.get('USERPROFILE', ''))`). The
        outer call is gated by `_is_environ_get_home` (its own key must be
        CLAUDE_HOME/HOME); an inner default-arg call is picked up as a rung
        regardless of *its* key, so a USERPROFILE (or any other) fallback
        key still surfaces textually as part of the site."""
        if not isinstance(node, ast.Call):
            return False
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "get"):
            return False
        return _attr_or_name(func.value) == "environ"

    @staticmethod
    def _extract_guard_ladder(func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.expr] | None:
        """Shape 2 -- the `if`/`return` guard ladder, per the spike the
        DOMINANT shape in this fleet. Scans `func`'s OWN top-level body
        statements (not nested blocks) for `if <test>: return <value>`
        guards (no `elif`/`else`) and any plain `return <value>` statement,
        collecting each guard's `test` and return value, plus a bare
        return's value, as rung candidates in source order.

        Requires at least one `if`/`return` guard to qualify -- a bare
        `def f(): return X` with no guard at all is not ladder-shaped and is
        left to the BoolOp/ternary/default-arg passes instead, so a trivial
        single-expression return body is never double-counted as a
        function-level site (the spike's own double-report bug -- see
        `_iter_ladder_sites`).

        Each candidate rung expression (a guard's `test`, a guard's `return`
        value, and any bare `return` value) is run through `_extract_rungs`,
        which (a) resolves a bare `Name` bound by a preceding top-level
        `<name> = <expr>` statement in the SAME function body back to
        `<expr>`, recursively -- including a bound `Name` used as a `Call`
        argument (`os.path.join(home, ".claude")` where `home` was bound to
        an or-chain resolves the chain, not just the join call itself; the
        C5e fix -- previously only a bare-`Name` return/test was resolved,
        never a `Name` nested inside a `Call`'s arguments), and (b) flattens
        a resolved `BoolOp(Or, ...)` into its individual operands as
        separate rungs rather than one opaque expression, so an or-chain
        reached through a guard's return value (`if x: return x` then
        `return a or b or c`, or a locally-bound `home = a or b or c`
        followed by `return os.path.join(home, ...)`) is scored rung-by-rung
        the same way a top-level `bare_or` BoolOp site already is. This is
        deliberately narrower than general data-flow: only a direct
        single-`Name` assignment target, looked up by exact name, no
        re-assignment tracking, no resolution through any OTHER expression
        shape (a ternary's `test`/`body`/`orelse`, in particular, is NOT
        resolved this way -- see the module docstring's declared miss for
        the ternary-over-locally-bound-env-read shape, which this pass does
        not share the fix for).

        **Adjacent-duplicate collapse (the C5e `rung_order` false-positive
        fix).** A guard `if x: return x` (the dominant fleet shape) yields
        the SAME resolved expression for both its `test` and its `return`
        value -- appending both as distinct rungs made every such guard a
        same-rank "transposition" against itself
        (`_rung_order_is_violation`'s `order_seq[i] >= order_seq[i + 1]`
        treats equal ranks as a fail), flagging every correct guard-ladder
        alongside every genuinely transposed one. The full rung list is
        collapsed via `_collapse_adjacent_duplicates` (structural,
        `ast.dump`-keyed) before being returned, so a guard's test/return
        pair -- or two textually-identical `environ.get(...)` calls, bound
        or not -- contributes ONE rung, while a genuine transposition
        (different keys, different order) is untouched."""
        bindings: dict[str, ast.expr] = {}
        expanded: set[str] = set()

        rungs: list[ast.expr] = []
        saw_guard = False
        for stmt in func.body:
            if (
                isinstance(stmt, ast.Assign)
                and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
            ):
                bindings[stmt.targets[0].id] = stmt.value
                continue
            if (
                isinstance(stmt, ast.If)
                and not stmt.orelse
                and len(stmt.body) == 1
                and isinstance(stmt.body[0], ast.Return)
                and stmt.body[0].value is not None
            ):
                rungs.extend(HomeResolutionLintEngine._extract_rungs(stmt.test, bindings, expanded=expanded))
                rungs.extend(
                    HomeResolutionLintEngine._extract_rungs(
                        stmt.body[0].value, bindings, expanded=expanded
                    )
                )
                saw_guard = True
                continue
            if isinstance(stmt, ast.Return) and stmt.value is not None:
                rungs.extend(HomeResolutionLintEngine._extract_rungs(stmt.value, bindings, expanded=expanded))
        if not saw_guard:
            return None
        return HomeResolutionLintEngine._collapse_adjacent_duplicates(rungs)

    @staticmethod
    def _extract_rungs(
        node: ast.expr,
        bindings: dict[str, ast.expr],
        _seen: frozenset[str] = frozenset(),
        expanded: set[str] | None = None,
    ) -> list[ast.expr]:
        """Resolves `node` against `bindings` (a bare `Name`, anywhere in
        the expression -- including nested inside a `Call`'s arguments, not
        just a top-level bare return/test -- resolves to its bound
        expression) and flattens a `BoolOp(Or, ...)` reached this way into
        its individual operands, recursively, so a locally-bound or-chain
        wrapped in a formatting call (`os.path.join(home, ".claude")` where
        `home = a or b or c`) yields `[a, b, c, ".claude"]` rather than one
        opaque `Call` node the classifier cannot see into.

        A recognised rung-shape `Call` (`environ.get(...)`, `Path.home()`,
        an `expanduser(...)` call) is always returned as a single leaf --
        never decomposed further -- so `_classify_rung` still receives the
        exact node shapes it already knows how to classify. Any OTHER
        `Call` is treated as a transparent wrapper: its own arguments are
        recursively extracted (a bound `Name` argument resolves first), and
        if that yields nothing, the call itself is returned as an
        unclassifiable leaf (harmless -- `_classify_rung` returns `None` for
        it, same as before this method existed).

        `_seen` guards a genuine live-fleet shape (`resolve_subagent_identity`
        in `coordinator/lib/session/identity.py`): a self-shadowing rebind
        `agent_id = agent_id or ""`, where `bindings["agent_id"]`'s own
        value expression contains a `Name("agent_id")` referring to the
        parameter it shadows, not a cycle in the home-resolution sense.
        Resolving a `Name` a second time within the SAME top-level rung
        expression is refused (the `Name` is returned unresolved instead) --
        this is a self-scan-discovered infinite-recursion fix, not a
        speculative one; the self-scan test caught it live.

        `expanded` is the SITE-level once-only set (threaded from
        `_extract_guard_ladder`, which owns it for the whole function) --
        distinct from `_seen`, which is per-top-level-rung and exists only to
        stop self-shadowing recursion. One local binding names ONE ladder,
        evaluated once; a function that references it from more than one
        return path (`home = HOME or USERPROFILE or expanduser("~")` used by
        both a `.zshrc` and a `.bashrc` return) re-expanded that same ladder
        once per reference, and the concatenation put a low-rank rung after a
        high-rank one at the splice -- scoring `[HOME, USERPROFILE, HOME,
        USERPROFILE]` as a rung_order transposition on code that is correct.
        `_collapse_adjacent_duplicates` cannot reach it: the repeats are not
        adjacent (a return's own format constant sits between them). The
        second and later references therefore contribute NO rungs. This is
        why a `rung_order` finding kept reappearing in files a previous
        remediation wave had just fixed -- giving a site a correct
        multi-rung ladder referenced from several returns is precisely what
        manufactured the false transposition, so each fix wave created its
        own next wave. Literal repeated ladder EXPRESSIONS (not a
        re-referenced binding) are untouched and still scored, so a genuine
        transposition written out twice is still caught."""
        if isinstance(node, ast.Name) and node.id in bindings and node.id not in _seen:
            if expanded is not None:
                if node.id in expanded:
                    return []
                expanded.add(node.id)
            return HomeResolutionLintEngine._extract_rungs(
                bindings[node.id], bindings, _seen | {node.id}, expanded
            )
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
            rungs: list[ast.expr] = []
            for value in node.values:
                rungs.extend(
                    HomeResolutionLintEngine._extract_rungs(value, bindings, _seen, expanded)
                )
            return rungs
        if isinstance(node, ast.Call):
            if (
                HomeResolutionLintEngine._is_environ_get_home(node)
                or HomeResolutionLintEngine._is_environ_get_userprofile(node)
                or HomeResolutionLintEngine._is_path_home_call(node)
            ):
                return [node]
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "expanduser":
                return [node]
            wrapped: list[ast.expr] = []
            for arg in node.args:
                wrapped.extend(
                    HomeResolutionLintEngine._extract_rungs(arg, bindings, _seen, expanded)
                )
            return wrapped or [node]
        return [node]

    @staticmethod
    def _collapse_adjacent_duplicates(rungs: list[ast.expr]) -> list[ast.expr]:
        """Collapses consecutive structurally-identical rungs (`ast.dump`
        equality -- ignores `lineno`/`col_offset`, so two textually distinct
        but structurally identical `environ.get(...)` call sites, or a
        `Name` resolved to the same bound expression twice in a row, count
        as one rung) -- see `_extract_guard_ladder`'s "Adjacent-duplicate
        collapse" note for why this is required, not cosmetic."""
        collapsed: list[ast.expr] = []
        previous_dump: str | None = None
        for rung in rungs:
            dump = ast.dump(rung)
            if dump == previous_dump:
                continue
            collapsed.append(rung)
            previous_dump = dump
        return collapsed

    @staticmethod
    def _default_arg_ladder_rungs(node: ast.AST) -> list[ast.expr] | None:
        """Shape 4 (EM ruling -- in scope; see module docstring) -- the
        nested default-arg ladder `os.environ.get('HOME',
        os.environ.get('USERPROFILE', ''))`. Requires the OUTER call to
        itself be a CLAUDE_HOME/HOME `environ.get` (`_is_environ_get_home`);
        each nested default arg that is itself an `environ.get(...)` call
        (`_is_environ_get_call`, any key) is unwrapped one level at a time
        into its own rung; the innermost non-`environ.get` default value is
        the final rung. Returns `None` for anything that is not this shape."""
        if not (isinstance(node, ast.Call) and HomeResolutionLintEngine._is_environ_get_home(node)):
            return None
        if len(node.args) < 2:
            return None
        rungs: list[ast.expr] = [node]
        current = node.args[1]
        while HomeResolutionLintEngine._is_environ_get_call(current) and len(current.args) >= 2:
            rungs.append(current)
            current = current.args[1]
        rungs.append(current)
        return rungs

    def _iter_ladder_sites(self, tree: ast.AST) -> list[tuple[ast.AST, list[ast.expr]]]:
        """The single ladder-extraction seam: one `(representative_node,
        rungs)` pair per distinct home-resolution ladder site in `tree`,
        covering all four shapes (BoolOp `or`-chain, `if`/`return`
        guard-ladder, ternary, nested default-arg ladder) and deduplicated
        via a covered-node-id set so a guard-ladder function body and a
        BoolOp/ternary/default-arg expression nested inside it are never
        both yielded as separate sites for the same function (the spike's
        own double-report bug: the same function reported once as an
        expression and once as a function-body ladder).

        Both `find_bare_home_or_chains` (below) and C5's `rung_order` rule
        consume this seam, which is what keeps presence and order scoring
        the same ladders.

        Pass order is significant and coarsest-first: function-level
        guard-ladders are claimed FIRST ("one function yields one
        finding"), then BoolOp or-chains, then standalone ternaries, then
        default-arg ladders -- each pass skips any node a strictly earlier
        pass already claimed.

        **Declared miss (not extracted by this seam, by design -- state the
        limit rather than papering over it):** the
        ternary-over-locally-bound-env-read shape (`claude_home =
        os.environ.get("CLAUDE_HOME")` on one line, then `(Path(claude_home)
        if claude_home else Path.home())` on the next) is NOT covered -- the
        expression-level ternary pass below does not resolve intra-function
        name bindings, only the literal test/body/orelse it is built from.
        The guard-ladder pass has the same limit for the same reason (see
        `_extract_guard_ladder`'s own docstring)."""
        covered: set[int] = set()
        sites: list[tuple[ast.AST, list[ast.expr]]] = []

        def claim(node: ast.AST) -> None:
            for child in ast.walk(node):
                covered.add(id(child))

        for node in ast.walk(tree):
            if id(node) in covered or not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            rungs = self._extract_guard_ladder(node)
            if rungs is not None:
                sites.append((node, rungs))
                claim(node)

        for node in ast.walk(tree):
            if id(node) in covered:
                continue
            if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
                sites.append((node, list(node.values)))
                claim(node)

        for node in ast.walk(tree):
            if id(node) in covered:
                continue
            if isinstance(node, ast.IfExp):
                sites.append((node, [node.test, node.body, node.orelse]))
                claim(node)

        for node in ast.walk(tree):
            if id(node) in covered:
                continue
            rungs = self._default_arg_ladder_rungs(node)
            if rungs is not None:
                sites.append((node, rungs))
                claim(node)

        return sites

    def find_bare_home_or_chains(self) -> list[Finding]:
        """`_iter_ladder_sites`-driven: `os.environ.get("CLAUDE_HOME") or
        os.environ.get("HOME") or <fallback with no Windows rung>`, in any
        of that seam's four shapes. A site is considered only when one of
        its rungs is a genuine CLAUDE_HOME/HOME `environ.get` call
        (`_is_environ_get_home`) -- otherwise it is unrelated code, not a
        home-resolution ladder at all. A qualifying site is exempt only when
        one of its OWN rungs structurally contains a genuine `Path.home()`
        call (`_contains_path_home_call`) or a genuine `environ.get`
        USERPROFILE rung (`_contains_userprofile_rung`, an explicit fallback
        rung the ladder itself carries -- this is also how the shape-4
        default-arg ladder's own literal `'USERPROFILE'` key reads as
        exempt, with no shape-specific casing needed) -- a `USERPROFILE`
        mention merely nearby in the source (a comment, a docstring, an
        unrelated neighbouring statement) no longer exempts anything, only
        a rung that IS the ladder's own expression does. `expanduser` is
        not exempting either way: an unguarded `os.path.expanduser` call is
        the vulnerable site itself, not evidence the chain already guards
        against it."""
        findings: list[Finding] = []
        for path in self.iter_py_files():
            tree, lines = _parse(path)
            if tree is None:
                continue
            for node, rungs in self._iter_ladder_sites(tree):
                if not any(self._is_environ_get_home(rung) for rung in rungs):
                    continue
                if any(self._contains_path_home_call(rung) for rung in rungs):
                    continue
                if any(self._contains_userprofile_rung(rung) for rung in rungs):
                    continue
                findings.append(
                    Finding(_relpath(self.repo_root, path), node.lineno, _line_text(lines, node.lineno))
                )
        return findings

    # -- Rule 5: ladder rungs out of the master order (C5). --------------

    _RUNG_ORDER: dict[str, int] = {
        "CLAUDE_HOME": 0,
        "HOME": 1,
        "USERPROFILE": 2,
        "PATH_HOME": 3,
    }

    @staticmethod
    def _contains_environ_get_key(node: ast.AST) -> str | None:
        """Structurally walks `node` for a genuine `environ.get(<key>, ...)`
        call (any string key, not just CLAUDE_HOME/HOME/USERPROFILE),
        reached through a wrapping call or a ternary -- the same expression
        shapes `_contains_userprofile_rung` recognises, generalised to
        return the key itself rather than a boolean, so `rung_order` can
        classify a rung by WHICH key it reads rather than merely whether
        it reads one."""
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "get" and _attr_or_name(func.value) == "environ":
                if node.args:
                    arg0 = node.args[0]
                    if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                        return arg0.value
            for arg in node.args:
                found = HomeResolutionLintEngine._contains_environ_get_key(arg)
                if found is not None:
                    return found
            return None
        if isinstance(node, ast.IfExp):
            return HomeResolutionLintEngine._contains_environ_get_key(
                node.body
            ) or HomeResolutionLintEngine._contains_environ_get_key(node.orelse)
        return None

    @staticmethod
    def _contains_expanduser_call(node: ast.AST) -> bool:
        """Structurally walks `node` for an `expanduser(...)` call (e.g.
        `os.path.expanduser`), reached through a wrapping call or ternary --
        mirrors `_contains_path_home_call`'s shape, gated on the `expanduser`
        attribute name rather than `Path.home`."""
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "expanduser":
                return True
            return any(HomeResolutionLintEngine._contains_expanduser_call(arg) for arg in node.args)
        if isinstance(node, ast.IfExp):
            return HomeResolutionLintEngine._contains_expanduser_call(
                node.body
            ) or HomeResolutionLintEngine._contains_expanduser_call(node.orelse)
        return False

    @classmethod
    def _classify_rung(cls, node: ast.expr) -> str | None:
        """Classifies one ladder rung expression into a master-order key
        (`"CLAUDE_HOME"` / `"HOME"` / `"USERPROFILE"` / `"PATH_HOME"`), or
        one of the two non-order terminal-shape violations (`"TILDE"` for a
        literal `"~"`, `"EXPANDUSER"` for an unguarded
        `os.path.expanduser(...)` rung), or `None` for a rung this rule does
        not reason about at all (an empty-string default, an unrelated
        expression) -- a `None` rung is silently skipped for ordering
        purposes, same as C4's ladder-extraction seam treats an unrecognised
        terminal.

        **Key check runs BEFORE the `Path.home()` check (C5b fix).** A
        shape-4 default-arg ladder's OUTER rung is the whole
        `environ.get(key, default)` call node itself (see
        `_default_arg_ladder_rungs`'s `rungs: list[ast.expr] = [node]`) --
        when that key's own default arg nests a genuine `Path.home()` call
        (`os.environ.get("CLAUDE_HOME", str(Path.home()))`), checking
        `_contains_path_home_call` first mis-walked INTO that default arg
        and misclassified the whole outer CLAUDE_HOME rung as `PATH_HOME`,
        producing a same-rank "transposition" against the real terminal
        rung and a false-positive report on correct code. Checking the
        rung's own top-level `environ.get` key first (which short-circuits
        without recursing into the default-arg branch once matched) fixes
        the outer rung's classification without weakening the terminal
        `Path.home()` check for rungs that genuinely are not an
        `environ.get` call themselves. This "key first" short-circuit only
        holds for the names in `_RUNG_ORDER` -- a rung whose own key exists
        but is NOT one of those names (`environ.get('SOME_OTHER_VAR', ...)`)
        is an unrelated env read, not a home-resolution rung at all, and
        must return `None` rather than falling through to
        `_contains_path_home_call`, which has no such short-circuit and
        would re-walk the SAME node's default-arg branch and reintroduce
        the C5b misclassification for that rung. The fall-through below is
        reserved for rungs that are not an `environ.get` call at all."""
        key = cls._contains_environ_get_key(node)
        if key is not None:
            return key if key in cls._RUNG_ORDER else None
        if cls._contains_path_home_call(node):
            return "PATH_HOME"
        if isinstance(node, ast.Constant) and node.value == "~":
            return "TILDE"
        if cls._contains_expanduser_call(node):
            return "EXPANDUSER"
        return None

    def _rung_order_sites(self) -> Iterable[tuple[Path, ast.AST, list[str | None]]]:
        """Shared walk for `find_rung_order_violations` and
        `find_rung_order_warnings`: yields `(path, node, kinds)` for every
        `_iter_ladder_sites` site gated on the `bare_or` CLAUDE_HOME/HOME
        `environ.get` presence check, with each rung already classified via
        `_classify_rung`. Kept as one seam so the two accessors below can
        never disagree about which sites are in scope or how a rung
        classifies -- only how a classified site's kinds are judged."""
        for path in self.iter_py_files():
            tree, _lines = _parse(path)
            if tree is None:
                continue
            for node, rungs in self._iter_ladder_sites(tree):
                if not any(self._is_environ_get_home(rung) for rung in rungs):
                    continue
                yield path, node, [self._classify_rung(rung) for rung in rungs]

    @classmethod
    def _rung_order_is_violation(cls, kinds: list[str | None]) -> bool:
        """A literal `"~"` terminal, or a transposed rung (a later-order
        rung appearing before an earlier-order one), is a FAIL per spec
        (`docs/wiki/portability-gates-spec.md` spec_version 1.3.0, "Terminal
        rung": `"~"` -- violation; `Path.home()` -- correct). An unguarded
        `expanduser` rung is deliberately NOT judged here -- see
        `_rung_order_is_warn` -- the spec downgrades it to warn, a literal
        `"~"` stays a hard violation.

        **Declared limit -- cross-branch rung splice (latent, not live as of
        2026-08-08).** `kinds` is the CONCATENATION of every rung across a
        function's entire ladder-extraction (`_extract_guard_ladder` treats
        "one function yields one finding"), with no notion of a ladder
        boundary between sibling branches. Two DISTINCT, individually-correct
        literal ladders written out in sibling branches of the same function
        (e.g. one guard returning `CLAUDE_HOME or HOME`, a second guard
        returning `USERPROFILE`, and a trailing bare return repeating
        `CLAUDE_HOME or HOME`) still splice into one ordered sequence at
        classification time and can score a transposition where none exists
        in any single ladder -- the same false-positive family as C5b/C5c/C5f,
        just for two different literal ladders rather than a repeated or
        reused one. The correct fix is scoring per-ladder rather than
        per-function (a restructure of `_iter_ladder_sites`/
        `_extract_guard_ladder`), tracked as its own plan rather than patched
        here. Confirmed against the live corpus as of 2026-08-08: `rung_order`
        currently reports 0 findings, so no site hits this splice today -- it
        is a latent gap in the scoring logic, not a live false positive. See
        `test_rung_order_cross_branch_ladder_splice_false_positive_known_gap`
        (marked `designed_red`) for the reproducer."""
        if any(kind == "TILDE" for kind in kinds):
            return True
        order_seq = [cls._RUNG_ORDER[kind] for kind in kinds if kind in cls._RUNG_ORDER]
        # Collapse adjacent duplicate ranks before scoring order: the same
        # rung key can legitimately appear more than once in the raw
        # extracted sequence -- e.g. a guard-ladder site where a wrapper
        # call re-mentions the SAME resolved CLAUDE_HOME expression a
        # second time a few rungs later (`_require_rooted("CLAUDE_HOME",
        # claude_home)` -- the literal label argument classifies as `None`
        # and is already dropped above, but the resolved `claude_home` Name
        # argument re-contributes the same CLAUDE_HOME rank non-adjacently
        # in the RAW rung list, past `_extract_guard_ladder`'s own
        # adjacent-only collapse). A repeated identical rank is never a
        # transposition (a transposition is a rank going backwards, not the
        # same rank twice); only a genuinely lower rank following a higher
        # one is scored below.
        collapsed_seq: list[int] = []
        for rank in order_seq:
            if collapsed_seq and collapsed_seq[-1] == rank:
                continue
            collapsed_seq.append(rank)
        return any(collapsed_seq[i] >= collapsed_seq[i + 1] for i in range(len(collapsed_seq) - 1))

    @classmethod
    def _rung_order_is_warn(cls, kinds: list[str | None]) -> bool:
        """An unguarded `os.path.expanduser(...)` rung is a WARN per spec
        (same "Terminal rung" section), not a FAIL -- distinct from the
        literal `"~"` rung, which stays a violation. A site already judged a
        violation by `_rung_order_is_violation` (a literal `"~"`, or an
        order transposition, co-occurring with an `expanduser` rung) is NOT
        also surfaced here -- it is already reported via the violation
        channel, and this accessor's contract is "warn-only, never a
        superset of the fail list"."""
        return any(kind == "EXPANDUSER" for kind in kinds) and not cls._rung_order_is_violation(kinds)

    def find_rung_order_violations(self) -> list[Finding]:
        """`_iter_ladder_sites`-driven, ladder-kind-agnostic (per the spec:
        the bootstrap ladder is the contents ladder minus its first rung, so
        both are subsequences of one master ordering and this rule never
        branches on which kind a site is): CLAUDE_HOME -> HOME ->
        USERPROFILE -> Path.home(). A site is considered only when one of
        its rungs is a genuine CLAUDE_HOME/HOME `environ.get` call (the same
        `bare_or` gate -- otherwise it is not a home-resolution ladder at
        all). A skipped rung mid-ladder PASSES (`CLAUDE_HOME -> USERPROFILE
        -> Path.home()` is valid and Windows-correct) -- only a
        transposition (a later-order rung appearing before an
        earlier-order one) is a violation, plus the one non-order
        terminal-shape violation (a literal `"~"` rung). An unguarded
        `expanduser` rung is a WARN, not a violation -- see
        `find_rung_order_warnings` (spec: "Terminal rung", § Home-resolution
        gate family). Rung PRESENCE (whether a given key appears at all)
        stays `bare_or`'s concern, not this rule's -- this rule only scores
        the relative order of the rungs a site actually has."""
        findings: list[Finding] = []
        for path, node, kinds in self._rung_order_sites():
            if self._rung_order_is_violation(kinds):
                _tree, lines = _parse(path)
                findings.append(
                    Finding(_relpath(self.repo_root, path), node.lineno, _line_text(lines, node.lineno))
                )
        return findings

    def find_rung_order_warnings(self) -> list[Finding]:
        """WARN-tier counterpart to `find_rung_order_violations` -- an
        unguarded `os.path.expanduser(...)` terminal rung, per spec ("Terminal
        rung": "An unguarded `expanduser` is a **warn**"), on a site that is
        not ALSO a violation (a literal `"~"` or an order transposition,
        judged by the shared `_rung_order_is_violation`). Deliberately a
        SEPARATE accessor, not folded into `find_rung_order_violations`'s
        list or `run_all_rules()`'s dict -- `run_all_rules()`'s keys are a
        cross-repo contract DoE constructs against directly
        (`coordinator/tests/test_home_resolution_lint.py:125-127`) and every
        one of its per-rule lists is treated as gate-failing by both the
        pytest shim and this module's own CLI (`main`'s ledger loop below);
        a warn that is not gate-failing has no seat in either without
        breaking that contract. Call this accessor explicitly for warn
        visibility."""
        findings: list[Finding] = []
        for path, node, kinds in self._rung_order_sites():
            if self._rung_order_is_warn(kinds):
                _tree, lines = _parse(path)
                findings.append(
                    Finding(_relpath(self.repo_root, path), node.lineno, _line_text(lines, node.lineno))
                )
        return findings

    def run_all_rules(self) -> dict[str, list[Finding]]:
        return {
            "x_ok": self.find_x_ok_checks(),
            "colon_join": self.find_colon_path_joins(),
            "forward_slash": self.find_forward_slash_only_splits(),
            "bare_or": self.find_bare_home_or_chains(),
            "rung_order": self.find_rung_order_violations(),
        }


# ---------------------------------------------------------------------------
# Plain-CLI invocation -- ``python coordinator/lib/home_resolution_lint.py``.
#
# Purpose: the pytest shim (see module docstring) reaches only repos whose
# fast/full test tier collects the shim file. A repo with an unfamiliar or
# absent test story (fleet Python-file counts range from 0 to 3,568 -- see
# the distribution design's own survey) needs a lint reachable without
# pytest at all. This CLI is that path: it drives the same
# ``HomeResolutionLintEngine`` a pytest shim would, against a JSON ledger
# file instead of a Python baseline module, so a repo with zero existing
# test infrastructure can still adopt the gate with one command.
#
# This ledger is deliberately a SEPARATE artifact from a repo's pytest-shim
# baseline (``_home_resolution_lint_baseline.py``) where one exists --
# the engine repo itself has both after this CLI lands, and that is by
# design, not drift: the pytest shim's ratchet is enforced at test-collection
# time with per-rule ``warnings.warn`` visibility; the CLI's ledger is
# enforced at process-exit-code time for callers with no pytest tier at all.
# A repo is free to use either, or both, without them needing to agree on a
# baseline file format.
# ---------------------------------------------------------------------------

# Negative-spec: this JSON ledger is NOT claude-klabauter's enforced baseline. The
# enforced one is the pytest shim (coordinator_core/tests/_home_resolution_lint_baseline.py),
# checked at test time; nothing in this repo invokes the CLI below. A checked-in copy of
# this file therefore goes stale silently and then reports phantom NEW findings against
# rows the real gate has already accepted -- which is why the one that had accumulated
# here was deleted rather than re-seeded. Run --init immediately before a hand CLI check;
# never trust a copy found on disk.
_DEFAULT_LEDGER_NAME = ".home_resolution_lint_baseline.json"

#: Printed on every CLI exit path. The counts this engine reports are a floor by
#: construction -- `_iter_ladder_sites` claims a whole function for its guard-ladder
#: pass, so any nested ladder in that function is never scored. Stated on the output
#: rather than only in a docstring because DoE imports this engine live, and a caller
#: outside this repo reads "0 new" without ever reading the module.
_FLOOR_NOTE = (
    "home-resolution-lint: NOTE -- these counts are a known FLOOR, not a total, "
    "by construction (see _iter_ladder_sites's docstring for the declared seam misses)."
)


def _cli_default_ledger_path(root: Path) -> Path:
    """The JSON ledger this CLI reads/writes, distinct from any pytest
    shim's own baseline module -- see the CLI docstring block above."""
    return root / _DEFAULT_LEDGER_NAME


def _cli_load_ledger(ledger_path: Path) -> dict[str, list[list]]:
    """Returns ``{rule_name: [[relpath, line, text], ...]}``, or an empty
    ledger (every rule mapped to ``[]``) if the file does not yet exist --
    a repo that has never run ``--init`` is treated as having a zero-debt
    ledger, not as an error."""
    if not ledger_path.is_file():
        return {name: [] for name in RULE_NAMES}
    raw = json.loads(ledger_path.read_text(encoding="utf-8"))
    rules = raw.get("rules", {})
    return {name: rules.get(name, []) for name in RULE_NAMES}


def _cli_write_ledger(ledger_path: Path, findings_by_rule: dict[str, list[Finding]]) -> None:
    """Writes the ledger as pretty-printed, key-sorted JSON so a diff on a
    future ``--init`` re-run (after fixing debt down) is reviewable, matching
    the "greppable, per-rule literal" spirit of the pytest shim's own
    baseline module (see that file's own header)."""
    payload = {
        "engine_version": ENGINE_VERSION,
        "rules": {
            name: sorted(
                [[f.path, f.line, f.text] for f in findings_by_rule.get(name, [])],
                key=lambda row: (row[0], row[1]),
            )
            for name in RULE_NAMES
        },
    }
    ledger_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _cli_build_engine(root: Path) -> HomeResolutionLintEngine:
    """The CLI's own engine construction, deliberately generic rather than
    claude-klabauter-shaped: ``scan_roots=("",)`` walks ``root`` itself (a
    single empty path component is a `Path.__truediv__` no-op, so
    ``root / ""`` resolves to ``root``), because an arbitrary fleet repo has
    no fixed ``coordinator_core``/``coordinator``/``bin``/``scripts`` layout
    to assume -- that layout is specific to claude-klabauter's own pytest shim.
    ``forward_slash_scope`` stays empty (this rule is opt-in per the engine's
    own docstring -- a generic CLI invocation must not silently inherit a
    scope tuned for a different repo's resolution-code family)."""
    return HomeResolutionLintEngine(repo_root=root, scan_roots=("",))


def _cli_has_any_python(root: Path, excluded_parts: frozenset[str] = DEFAULT_EXCLUDED_PARTS) -> bool:
    """AC-3/AC-6 predicate: does this repo have ANY ``.py`` file under
    ``root`` (outside the standard exclusions)? A repo with none (e.g.
    example-os-repo) must exit clean without ever claiming "0 violations found" --
    that phrase implies a real scan happened and found nothing, which is a
    different, stronger claim than "there was nothing to scan"."""
    for path in root.rglob("*.py"):
        rel = path.relative_to(root)
        if not _is_excluded(rel, excluded_parts):
            return True
    return False


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="home_resolution_lint",
        description=(
            "Cross-platform home-resolution lint: os.access(X_OK) misuse, literal ':' PATH-list "
            "joins, forward-slash-only path splits (opt-in scope), and CLAUDE_HOME/HOME "
            "or-chains missing a USERPROFILE rung."
        ),
    )
    parser.add_argument(
        "--root",
        type=str,
        default=".",
        help="Repo root to scan (default: current directory).",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help=(
            "Write the ledger at the current violation count instead of checking it -- "
            "lands the repo GREEN at its own today's-count, rather than ambushing it "
            "with a pre-existing debt list it must retroactively baseline by hand."
        ),
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    ledger_path = _cli_default_ledger_path(root)

    if not _cli_has_any_python(root):
        print(
            f"home-resolution-lint: NOT SCANNED -- no Python source found under {root} "
            f"(excluding {sorted(DEFAULT_EXCLUDED_PARTS)}). This is a clean no-op, not a "
            f"'0 violations found' scan result -- there was nothing to scan."
        )
        return 0

    engine = _cli_build_engine(root)
    findings_by_rule = engine.run_all_rules()

    if args.init:
        _cli_write_ledger(ledger_path, findings_by_rule)
        total = sum(len(v) for v in findings_by_rule.values())
        print(
            f"home-resolution-lint: --init wrote {ledger_path} at today's count "
            f"({total} known site(s) across {len(RULE_NAMES)} rules) -- "
            f"engine_version={ENGINE_VERSION}."
        )
        for name in RULE_NAMES:
            print(f"  {name}: {len(findings_by_rule[name])}")
        print(_FLOOR_NOTE)
        return 0

    if not ledger_path.is_file():
        total = sum(len(v) for v in findings_by_rule.values())
        print(
            f"home-resolution-lint: NO LEDGER at {ledger_path} -- reporting {total} live "
            f"finding(s) as a fresh census, NOT as new debt. This is the expected state for "
            f"this repo: the enforced baseline is the pytest shim "
            f"(coordinator_core/tests/_home_resolution_lint_baseline.py), and no maintained "
            f"copy of this CLI's own JSON ledger is kept. Run --init first if you want a "
            f"delta; scoring these against an absent ledger would call the entire corpus new."
        )
        for name in RULE_NAMES:
            print(f"  {name}: {len(findings_by_rule[name])}")
        print(_FLOOR_NOTE)
        return 0

    ledger = _cli_load_ledger(ledger_path)
    exit_code = 0
    for name in RULE_NAMES:
        baseline_keys = {(row[0], row[2]) for row in ledger.get(name, [])}
        live = findings_by_rule[name]
        new = [f for f in live if f.key() not in baseline_keys]
        print(
            f"home-resolution-lint: rule={name} total={len(live)} "
            f"baseline={len(baseline_keys)} new={len(new)}"
        )
        for f in new:
            print(f"    NEW  {f.path}:{f.line}: {f.text}")
            exit_code = 1

    if exit_code == 0:
        print(f"home-resolution-lint: clean (engine_version={ENGINE_VERSION}, ledger={ledger_path}).")
    else:
        print(
            "home-resolution-lint: FAILED -- new violation(s) above the ledger ceiling. "
            "Fix the site(s), or run --init to accept them (only if this is a deliberate "
            "burn-down re-baseline, never to silently pass new debt)."
        )
    print(_FLOOR_NOTE)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
