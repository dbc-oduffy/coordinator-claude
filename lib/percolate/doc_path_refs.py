"""coordinator/lib/percolate/doc_path_refs.py -- gate: every `lib/...` / `bin/...` file path the
plugin's INSTALL.md and commands/*.md tell the operator (or an agent) to run must exist in the
resolved publish payload.

Defect closed (2026-10-02): the published plugin's `/coordinator:install` doc points at
`lib/install/coordinator_install.py`, but the publish row sources `bin,lib` from this repo's
coordinator tree while the file lived only in the DoE tree, so the published plugin shipped a doc
naming a file it did not carry. Nothing compared the two.

The plugin docs may live in a different tree than the payload (DoE vs. Claude-klabauter), so the docs root
is a parameter. `payload_root` is the directory holding `bin/` and `lib/` (the resolved payload).

Second check: `find_unresolved_imports` -- every top-level `import X` / `from X import ...` in a
Python file under `hooks/`, `skills/` or `bin/` that puts a `lib` dir on `sys.path` must resolve to
stdlib, a sibling / other-sys.path-insert dir of that file, a pyproject-declared dep, or
`lib/X.py` / `lib/X/` in the payload. Third gate: `run_install_plan` runs
`lib/install/coordinator_install.py --plan` under an empty HOME; an "error" key (manifest/step
drift) fails. All checks are fail-closed (`main` exits 1; publish.py refuses the row) -- no
warn-only mode.

Scope: concrete file refs only -- a path with an extension and no placeholder/glob characters,
rooted at `lib/` or `bin/` and ANCHORED to the plugin via `coordinator/`, `<plugin-root>/`,
`<engine-root>/coordinator/` or the plugin-root environment-variable prefix (bare `bin/x` is a consuming-repo path).
Refs on a line/sentence saying "if present" / "if it exists" / "absent: skip" are exempt. Directory refs, globs and `<placeholders>` are not graded.
"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

# Only paths anchored to the PLUGIN are graded: the `<plugin-root>` placeholder, the plugin-root environment-variable prefix,
# `coordinator/` or `<engine-root>/coordinator/`. A bare `bin/x.sh` is the consuming repo's own
# optional extension point (e.g. `bin/check-fixture-sync.sh`), not a plugin file.
_REF = re.compile(
    r"(?:<plugin-root>/|\$\{CLAUDE_PLUGIN_ROOT\}/|<engine-root>/coordinator/|(?<![\w./\-])coordinator/)"
    r"((?:lib|bin)/[A-Za-z0-9_.\-/]*[A-Za-z0-9_\-]\.[A-Za-z0-9]+)(?![\w/<*{$])"
)
# A ref whose line or sentence says it is optional is not a promise the payload carries it.
# A ref the doc itself locates "under the resolved engine root" lives in the separately published
# engine checkout, not in this payload.
_OPTIONAL = re.compile(
    r"if present|if it exists|absent[\w\s]{0,20}:\s*skip|under the resolved engine root", re.IGNORECASE
)


def _graded_refs(text: str) -> list[str]:
    refs: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        for line in para.splitlines():
            for m in _REF.finditer(line):
                if _OPTIONAL.search(line):
                    continue
                sentence = next(
                    (x for x in re.split(r"(?<=[.!?])\s+", para) if m.group(0) in x), ""
                )
                if _OPTIONAL.search(sentence):
                    continue
                refs.append(m.group(1))
    return refs


def _doc_files(docs_root: Path) -> list[Path]:
    files = [docs_root / "INSTALL.md"]
    for sub in (docs_root / "commands", docs_root / "coordinator" / "commands"):
        if sub.is_dir():
            files.extend(sorted(sub.glob("*.md")))
    return [f for f in files if f.is_file()]


def find_missing_doc_refs(docs_root: Path, payload_root: Path) -> list[tuple[str, str]]:
    """Return sorted (doc-relative-path, ref) pairs whose ref is absent from payload_root."""
    missing: set[tuple[str, str]] = set()
    for doc in _doc_files(Path(docs_root)):
        text = doc.read_text(encoding="utf-8", errors="replace")
        for ref in _graded_refs(text):
            if not (Path(payload_root) / ref).is_file():
                missing.add((doc.relative_to(docs_root).as_posix(), ref))
    return sorted(missing)


_PAYLOAD_PY_DIRS = ("hooks", "skills", "bin")
#: Top-level names carried by a SEPARATELY published row / resolved engine checkout at runtime
#: (the `coordinator_core` package), not by the plugin payload's own lib/. Grading them here is the
#: cross-row false positive import_closure.py documents (372 on the bin row, all false).
EXTERNAL_PACKAGES = frozenset({"coordinator_core"})
#: pyproject distribution name (normalised) -> import name, where they differ.
_DIST_TO_IMPORT = {"pyyaml": "yaml", "tree_sitter_pwsh": "tree_sitter_powershell"}


def declared_third_party(pyproject: Path | None) -> set[str]:
    """Import names of every dep in pyproject [project].dependencies + optional-dependencies."""
    if pyproject is None or not Path(pyproject).is_file():
        return set()
    data = tomllib.loads(Path(pyproject).read_text(encoding="utf-8")).get("project", {})
    specs = list(data.get("dependencies", []))
    for extra in data.get("optional-dependencies", {}).values():
        specs.extend(extra)
    names: set[str] = set()
    for spec in specs:
        m = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._\-]*)", spec)
        if m:
            dist = re.sub(r"[-.]+", "_", m.group(1)).lower()
            names.add(_DIST_TO_IMPORT.get(dist, dist))
            names.add(dist)
    return names


class _PathEval:
    """Symbolic evaluator for the path expressions scripts feed to sys.path.

    Values are normalised absolute path strings, or None when not statically knowable.
    """

    def __init__(self, tree: ast.AST, file: Path):
        self.file = os.path.normpath(str(file))
        self.env: dict[str, ast.expr] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                self.env.setdefault(node.targets[0].id, node.value)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
                self.env.setdefault(node.target.id, node.value)

    def ev(self, n: ast.expr, depth: int = 0) -> str | None:
        if depth > 12:
            return None
        e = lambda x: self.ev(x, depth + 1)  # noqa: E731
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            return n.value
        if isinstance(n, ast.Name):
            if n.id == "__file__":
                return self.file
            return e(self.env[n.id]) if n.id in self.env else None
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div):
            l, r = e(n.left), e(n.right)
            return None if l is None or r is None else os.path.normpath(os.path.join(l, r))
        if isinstance(n, ast.Subscript) and isinstance(n.value, ast.Attribute) and n.value.attr == "parents":
            base = e(n.value.value)
            idx = n.slice
            if base is not None and isinstance(idx, ast.Constant) and isinstance(idx.value, int):
                for _ in range(idx.value + 1):
                    base = os.path.dirname(base)
                return base
            return None
        if isinstance(n, ast.Attribute):
            if n.attr == "parent":
                b = e(n.value)
                return None if b is None else os.path.dirname(b)
            return None
        if isinstance(n, ast.Call):
            f, args = n.func, n.args
            if isinstance(f, ast.Attribute) and f.attr in ("resolve", "absolute", "expanduser") and not args:
                return e(f.value)
            if isinstance(f, ast.Attribute) and f.attr == "joinpath":
                b = e(f.value)
                parts = [e(a) for a in args]
                return None if b is None or None in parts else os.path.normpath(os.path.join(b, *parts))
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
            if name in ("Path", "str", "fspath", "abspath", "realpath", "normpath") and len(args) == 1:
                v = e(args[0])
                return None if v is None else os.path.normpath(v)
            if name == "dirname" and len(args) == 1:
                v = e(args[0])
                return None if v is None else os.path.dirname(v)
            if name == "join" and args:
                parts = [e(a) for a in args]
                return None if None in parts else os.path.normpath(os.path.join(*parts))
        return None


def _sys_path_inserts(tree: ast.AST, ev: _PathEval) -> list[str]:
    """Statically resolvable dirs the file inserts/appends on sys.path."""
    dirs: list[str] = []
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ("insert", "append")):
            continue
        v = n.func.value
        if not (isinstance(v, ast.Attribute) and v.attr == "path" and isinstance(v.value, ast.Name) and v.value.id == "sys"):
            continue
        d = ev.ev(n.args[-1]) if n.args else None
        if d is not None:
            dirs.append(d)
    return dirs


def _guarded_import_nodes(tree: ast.AST) -> set[int]:
    """ids of Import/ImportFrom nodes inside a `try` whose handlers tolerate ImportError."""
    guarded: set[int] = set()
    for t in ast.walk(tree):
        if not isinstance(t, ast.Try):
            continue
        tolerant = False
        for h in t.handlers:
            ty = h.type
            names = [ty] if not isinstance(ty, ast.Tuple) else list(ty.elts)
            if ty is None or any(
                getattr(x, "id", "") in ("ImportError", "ModuleNotFoundError", "Exception", "BaseException")
                for x in names
            ):
                tolerant = True
        if tolerant:
            for stmt in t.body:
                for sub in ast.walk(stmt):
                    if isinstance(sub, (ast.Import, ast.ImportFrom)):
                        guarded.add(id(sub))
    return guarded


def _resolves_in(d: str, name: str) -> bool:
    if os.path.isfile(os.path.join(d, name + ".py")) or os.path.isdir(os.path.join(d, name)):
        return True
    return os.path.isdir(d) and any(f.startswith(name + ".") and f.endswith((".so", ".pyd")) for f in os.listdir(d))


def find_unresolved_imports(
    payload_root: Path, pyproject: Path | None = None, third_party: set[str] | None = None
) -> list[tuple[str, str]]:
    """Return sorted (payload-relative file, top-level import name) pairs that cannot resolve.

    Only files that put a dir named `lib` (inside the payload) on sys.path, statically, are graded.
    A name resolves if it is stdlib, declared third-party, or present as `X.py`/`X/` in the file's
    own dir or any dir the file statically adds to sys.path. Imports in a `try` that tolerates
    ImportError, relative imports, and `__future__` are not graded.
    """
    root = Path(payload_root).resolve()
    tp = (declared_third_party(pyproject) if third_party is None else set(third_party)) | EXTERNAL_PACKAGES
    out: set[tuple[str, str]] = set()
    for top in _PAYLOAD_PY_DIRS:
        base = root / top
        if not base.is_dir():
            continue
        for f in sorted(base.rglob("*.py")):
            if "__pycache__" in f.parts:
                continue
            try:
                tree = ast.parse(f.read_text(encoding="utf-8", errors="replace"), filename=str(f))
            except SyntaxError:
                continue
            dirs = _sys_path_inserts(tree, _PathEval(tree, f))
            if not any(os.path.basename(d) == "lib" and d.startswith(str(root) + os.sep) for d in dirs):
                continue
            search = [str(f.parent), *dirs]
            guarded = _guarded_import_nodes(tree)
            # `import lib  # bootstraps coordinator/bin/lib onto sys.path`: a package whose
            # __init__.py inserts dirs on sys.path extends this file's search path.
            for d in list(search):
                for pkg in sorted(Path(d).glob("*/__init__.py")) if os.path.isdir(d) else ():
                    pname = pkg.parent.name
                    if any(
                        isinstance(x, (ast.Import, ast.ImportFrom))
                        and pname in ([a.name.split(".")[0] for a in x.names] if isinstance(x, ast.Import) else [(x.module or "").split(".")[0]])
                        for x in ast.walk(tree)
                    ):
                        try:
                            itree = ast.parse(pkg.read_text(encoding="utf-8", errors="replace"))
                        except SyntaxError:
                            continue
                        search.extend(_sys_path_inserts(itree, _PathEval(itree, pkg)))
            for n in ast.walk(tree):
                if id(n) in guarded:
                    continue
                if isinstance(n, ast.Import):
                    names = [a.name.split(".")[0] for a in n.names]
                elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
                    names = [n.module.split(".")[0]]
                else:
                    continue
                for name in names:
                    if name == "__future__" or name in sys.stdlib_module_names or name in tp:
                        continue
                    if not any(_resolves_in(d, name) for d in search):
                        out.add((f.relative_to(root).as_posix(), name))
    return sorted(out)


def default_pyproject() -> Path:
    return Path(__file__).resolve().parents[3] / "pyproject.toml"


_INSTALL_SCRIPT = Path("lib") / "install" / "coordinator_install.py"


def _payload_python_argv(root: Path, script: str, *args: str) -> list[str]:
    """argv via the payload's own bin/lib/python_interp, so the gate runs the installer the way users do."""
    sys.path.insert(0, str(root / "bin" / "lib"))
    try:
        from python_interp import python_argv
        argv = python_argv(script, *args)
    except ImportError:
        argv = None
    finally:
        sys.path.pop(0)
    interpreter = sys.executable
    return argv or [interpreter, script, *args]


def run_install_plan(payload_root: Path, timeout: float = 120) -> str | None:
    """Run `lib/install/coordinator_install.py --plan` in the payload under an empty HOME.

    Returns None when the plan is clean, else a one-line failure reason (script missing, crash,
    non-JSON output, or an "error" key such as "manifest/step drift").
    """
    root = Path(payload_root).resolve()
    if not (root / _INSTALL_SCRIPT).is_file():
        return f"{_INSTALL_SCRIPT.as_posix()} not in payload"
    with tempfile.TemporaryDirectory() as home:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "COORDINATOR"))}
        env.update(HOME=home, USERPROFILE=home, CLAUDE_HOME=home)
        try:
            proc = subprocess.run(
                _payload_python_argv(root, str(_INSTALL_SCRIPT), "--plan"),
                cwd=str(root), env=env, capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return f"--plan timed out after {timeout}s"
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        return f"--plan exit {proc.returncode}, output not JSON: {(proc.stderr or proc.stdout).strip()[:300]}"
    if isinstance(data, dict) and "error" in data:
        return f"--plan reported error: {data['error']}"
    if proc.returncode != 0:
        return f"--plan exit {proc.returncode}: {proc.stderr.strip()[:300]}"
    return None


def check_payload(
    docs_root: Path, payload_root: Path, pyproject: Path | None = None
) -> tuple[list[tuple[str, str]], list[tuple[str, str]], str | None]:
    """Run all three gates. (missing_doc_refs, unresolved_imports, install_plan_error); any truthy FAILS."""
    return (
        find_missing_doc_refs(docs_root, payload_root),
        find_unresolved_imports(payload_root, pyproject if pyproject is not None else default_pyproject()),
        run_install_plan(payload_root),
    )


def format_failures(docs, imports, plan_err) -> list[str]:
    lines = [f"{d}: {r} not in payload" for d, r in docs]
    lines += [f"{f}: import {n} unresolved (not stdlib, sibling, sys.path insert, or declared dep)" for f, n in imports]
    if plan_err:
        lines.append(f"install --plan: {plan_err}")
    return lines


def main(argv: list[str]) -> int:
    if len(argv) not in (3, 4):
        print("usage: doc_path_refs.py <docs_root> <payload_root> [pyproject.toml]", file=sys.stderr)
        return 2
    docs, imports, plan_err = check_payload(Path(argv[1]), Path(argv[2]), Path(argv[3]) if len(argv) == 4 else None)
    for line in format_failures(docs, imports, plan_err):
        print(line)
    return 1 if docs or imports or plan_err else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
