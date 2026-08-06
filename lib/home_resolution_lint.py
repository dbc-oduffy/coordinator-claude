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
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
import json
import sys
from pathlib import Path
from typing import Iterable, Sequence

ENGINE_VERSION = "2026-07-28.1"

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
    }
)

RULE_NAMES: tuple[str, ...] = ("x_ok", "colon_join", "forward_slash", "bare_or")

RULE_LABELS: dict[str, str] = {
    "x_ok": "os.access(..., os.X_OK)",
    "colon_join": "literal ':' PATH-list join/split",
    "forward_slash": "forward-slash-only path split",
    "bare_or": "CLAUDE_HOME/HOME or-chain with no USERPROFILE rung",
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
    except SyntaxError:
        return None, None
    return tree, source.splitlines()


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
        for name in self.scan_roots:
            scan_root = self.repo_root / name
            if not scan_root.is_dir():
                continue
            for path in sorted(scan_root.rglob("*.py")):
                if _is_excluded(path.relative_to(scan_root), self.excluded_parts):
                    continue
                yield path

    def scanned_file_count(self) -> int:
        return sum(1 for _ in self.iter_py_files())

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
    def _chain_has_windows_rung(boolop: ast.BoolOp) -> bool:
        for value in boolop.values:
            dumped = ast.dump(value)
            if "USERPROFILE" in dumped or "expanduser" in dumped:
                return True
            if "Path" in dumped and "home" in dumped.lower():
                return True
        return False

    def find_bare_home_or_chains(self) -> list[Finding]:
        """AST: `os.environ.get("CLAUDE_HOME") or os.environ.get("HOME") or
        <fallback with no Windows rung>`. A chain is exempt if it -- or the
        three source lines immediately above/below the boolop -- mentions
        `USERPROFILE`, `Path.home()`, or `os.path.expanduser`."""
        findings: list[Finding] = []
        for path in self.iter_py_files():
            tree, lines = _parse(path)
            if tree is None:
                continue
            for node in ast.walk(tree):
                if not (isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or)):
                    continue
                if not any(self._is_environ_get_home(v) for v in node.values):
                    continue
                if self._chain_has_windows_rung(node):
                    continue
                end = node.end_lineno or node.lineno
                window_start = max(1, node.lineno - 3)
                window_end = min(len(lines), end + 3)
                nearby = "\n".join(lines[window_start - 1 : window_end])
                if "USERPROFILE" in nearby or "expanduser" in nearby or "Path.home" in nearby:
                    continue
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
# claude-klabauter itself has both after this CLI lands, and that is by
# design, not drift: the pytest shim's ratchet is enforced at test-collection
# time with per-rule ``warnings.warn`` visibility; the CLI's ledger is
# enforced at process-exit-code time for callers with no pytest tier at all.
# A repo is free to use either, or both, without them needing to agree on a
# baseline file format.
# ---------------------------------------------------------------------------

_DEFAULT_LEDGER_NAME = ".home_resolution_lint_baseline.json"


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
    ledger_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
