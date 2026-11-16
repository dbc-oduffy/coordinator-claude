#!/usr/bin/env python3
"""Add the Python annotations that can be inferred without guessing, or count those still missing.

Rewrite mode edits files in place using exact ast/token spans (no regex, no third-party dep):
  - `-> None` on functions with no value return (generators, abstract/overload/stub bodies,
    always-raising functions excluded)
  - `-> bool|str|int` when every return is a literal of that type and the body cannot fall through
  - literal-default parameter types (bool/int/float/str/bytes)
  - standard pytest fixture parameter types, on test functions and fixtures only
Needed imports are inserted. Everything else stays byte-identical; a second run is a no-op.

`--check` writes nothing, prints the missing-annotation count (returns plus parameters, excluding
self/cls) and exits 1 when it is above zero.
"""

from __future__ import annotations

import argparse
import ast
import io
import sys
import tokenize
from pathlib import Path

_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".tox", ".mypy_cache"}

_FIXTURE_TYPES = {
    "tmp_path": "Path",
    "tmp_path_factory": "pytest.TempPathFactory",
    "monkeypatch": "pytest.MonkeyPatch",
    "capsys": "pytest.CaptureFixture[str]",
    "capfd": "pytest.CaptureFixture[str]",
    "capsysbinary": "pytest.CaptureFixture[bytes]",
    "capfdbinary": "pytest.CaptureFixture[bytes]",
    "caplog": "pytest.LogCaptureFixture",
    "request": "pytest.FixtureRequest",
    "pytestconfig": "pytest.Config",
    "recwarn": "pytest.WarningsRecorder",
    "cache": "pytest.Cache",
}
_IMPORT_LINES = {"Path": "from pathlib import Path", "pytest": "import pytest"}
_LITERAL_DEFAULT_TYPES = {bool: "bool", int: "int", float: "float", str: "str", bytes: "bytes"}
_LITERAL_RETURN_TYPES = {bool: "bool", int: "int", str: "str"}


class _Source:
    """Text plus line-start offsets; converts ast (utf-8 byte column) positions to str offsets."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.lines = text.split("\n")
        self.starts: list[int] = []
        pos = 0
        for line in self.lines:
            self.starts.append(pos)
            pos += len(line) + 1

    def offset(self, line: int, byte_col: int) -> int:
        raw = self.lines[line - 1]
        col = byte_col if raw.isascii() else len(raw.encode("utf-8")[:byte_col].decode("utf-8"))
        return self.starts[line - 1] + col


def _functions(tree: ast.AST) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _all_params(args: ast.arguments) -> list[ast.arg]:
    params = [*args.posonlyargs, *args.args, *args.kwonlyargs]
    return params + [x for x in (args.vararg, args.kwarg) if x]


def count_missing(tree: ast.AST) -> int:
    """Missing annotations: unannotated returns plus unannotated params, excluding self/cls."""
    total = 0
    for fn in _functions(tree):
        params = [p for p in _all_params(fn.args) if p.arg not in ("self", "cls")]
        total += (fn.returns is None) + sum(p.annotation is None for p in params)
    return total


def _own_scope(fn: ast.AST):
    """Yield nodes of fn's own scope, not descending into nested defs, lambdas or classes."""
    stack = list(ast.iter_child_nodes(fn))
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
        ):
            stack.extend(ast.iter_child_nodes(node))


def _decorator_names(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    names = set()
    for dec in fn.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(target, ast.Attribute):
            names.add(target.attr)
        elif isinstance(target, ast.Name):
            names.add(target.id)
    return names


def _is_stub(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    body = fn.body
    if all(
        isinstance(s, ast.Pass)
        or (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant)
            and (isinstance(s.value.value, str) or s.value.value is Ellipsis))
        for s in body
    ):
        return True
    rest = body[1:] if (
        isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ) else body
    if len(rest) == 1 and isinstance(rest[0], ast.Raise) and rest[0].exc is not None:
        exc = rest[0].exc.func if isinstance(rest[0].exc, ast.Call) else rest[0].exc
        return isinstance(exc, ast.Name) and exc.id == "NotImplementedError"
    return False


def _terminates(stmts: list[ast.stmt]) -> bool:
    """True when control cannot fall off the end of stmts (conservative)."""
    if not stmts:
        return False
    last = stmts[-1]
    if isinstance(last, (ast.Return, ast.Raise)):
        return True
    if isinstance(last, ast.If):
        return _terminates(last.body) and _terminates(last.orelse)
    if isinstance(last, (ast.With, ast.AsyncWith)):
        return _terminates(last.body)
    if isinstance(last, ast.Try):
        if last.finalbody and _terminates(last.finalbody):
            return True
        body_ok = _terminates(last.orelse) if last.orelse else _terminates(last.body)
        return body_ok and all(_terminates(h.body) for h in last.handlers)
    return False


def _literal_kind(node: ast.expr | None) -> type | None:
    if isinstance(node, ast.JoinedStr):
        return str
    if isinstance(node, ast.Constant) and type(node.value) in _LITERAL_RETURN_TYPES:
        return type(node.value)
    return None


def _infer_return(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    if fn.returns is not None:
        return None
    decorators = _decorator_names(fn)
    if decorators & {"abstractmethod", "overload"}:
        return None
    returns: list[ast.Return] = []
    for node in _own_scope(fn):
        if isinstance(node, (ast.Yield, ast.YieldFrom)):
            return None
        if isinstance(node, ast.Return):
            returns.append(node)

    def is_none(r: ast.Return) -> bool:
        return r.value is None or (isinstance(r.value, ast.Constant) and r.value.value is None)

    if all(is_none(r) for r in returns):
        if _is_stub(fn):
            return None
        if not returns and (
            isinstance(fn.body[-1], ast.Raise)
            or (isinstance(fn.body[-1], ast.While)
                and isinstance(fn.body[-1].test, ast.Constant) and fn.body[-1].test.value is True)
        ):
            return None
        return "None"
    kinds = {_literal_kind(r.value) for r in returns}
    if len(kinds) == 1 and None not in kinds and _terminates(fn.body):
        return _LITERAL_RETURN_TYPES[kinds.pop()]
    return None


def _literal_default_type(default: ast.expr | None) -> str | None:
    if isinstance(default, ast.UnaryOp) and isinstance(default.op, (ast.USub, ast.UAdd)):
        inner = default.operand
        if isinstance(inner, ast.Constant) and type(inner.value) in (int, float):
            return _LITERAL_DEFAULT_TYPES[type(inner.value)]
        return None
    if isinstance(default, ast.Constant):
        return _LITERAL_DEFAULT_TYPES.get(type(default.value))
    return None


def _bound_names(body: list[ast.stmt], out: dict[str, str]) -> None:
    """Map module-level names to 'ok' (the import we would add) or 'conflict'."""
    for stmt in body:
        if isinstance(stmt, ast.Import):
            for a in stmt.names:
                bound = a.asname or a.name.split(".")[0]
                out[bound] = "ok" if (bound == "pytest" and a.name == "pytest") else "conflict"
        elif isinstance(stmt, ast.ImportFrom):
            for a in stmt.names:
                bound = a.asname or a.name
                ok = bound == "Path" and stmt.module == "pathlib" and a.name == "Path"
                out[bound] = "ok" if ok else "conflict"
        elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out[stmt.name] = "conflict"
        elif isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
            for t in targets:
                for n in ast.walk(t):
                    if isinstance(n, ast.Name):
                        out[n.id] = "conflict"
        elif isinstance(stmt, (ast.If, ast.With, ast.AsyncWith, ast.For, ast.While)):
            _bound_names(stmt.body, out)
            _bound_names(getattr(stmt, "orelse", []), out)
        elif isinstance(stmt, ast.Try):
            for part in (stmt.body, stmt.orelse, stmt.finalbody, *[h.body for h in stmt.handlers]):
                _bound_names(part, out)


def _import_insert_line(tree: ast.Module) -> int:
    """1-based count of lines after which new imports go (0 = top of file)."""
    body = tree.body
    idx = 0
    after = 0
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        after = body[0].end_lineno or 0
        idx = 1
    for stmt in body[idx:]:
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            after = stmt.end_lineno or after
        else:
            break
    return after


def _is_test_scope(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return fn.name.startswith("test") or "fixture" in _decorator_names(fn)


def _leading_header_lines(src: _Source) -> int:
    """Lines of shebang / coding cookie that must stay first."""
    n = 0
    for line in src.lines[:2]:
        if line.startswith("#!") or ("coding" in line and line.lstrip().startswith("#")):
            n += 1
        else:
            break
    return n


def rewrite_text(text: str) -> tuple[str, int]:
    """Return (new_text, annotations_added). Raises SyntaxError when text does not parse."""
    tree = ast.parse(text)
    src = _Source(text)
    tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    tok_at = {t.start: i for i, t in enumerate(tokens)}
    bound: dict[str, str] = {}
    _bound_names(tree.body, bound)
    needed: set[str] = set()
    edits: list[tuple[int, int, str]] = []  # offset, delete_length, insert
    added = 0

    def need(name: str) -> bool:
        state = bound.get(name)
        if state == "conflict":
            return False
        if state is None:
            needed.add(name)
        return True

    for fn in _functions(tree):
        if "overload" in _decorator_names(fn):
            continue
        args = fn.args
        positional = [*args.posonlyargs, *args.args]
        pairs: list[tuple[ast.arg, ast.expr | None]] = list(
            zip(positional, [None] * (len(positional) - len(args.defaults)) + list(args.defaults))
        ) + list(zip(args.kwonlyargs, args.kw_defaults))
        test_scope = _is_test_scope(fn)
        for param, default in pairs:
            if param.annotation is not None or param.arg in ("self", "cls"):
                continue
            ann = _literal_default_type(default)
            if ann is None and test_scope:
                ann = _FIXTURE_TYPES.get(param.arg)
                if ann is not None:
                    root = "Path" if ann == "Path" else "pytest"
                    if not need(root):
                        ann = None
            if ann is None:
                continue
            end = src.offset(param.end_lineno, param.end_col_offset)
            if default is not None:
                dstart = src.offset(default.lineno, default.col_offset)
                if text[end:dstart] == "=":
                    edits.append((end, dstart - end, f": {ann} = "))
                    added += 1
                    continue
            edits.append((end, 0, f": {ann}"))
            added += 1
        ret = _infer_return(fn)
        if ret is not None:
            i = tok_at[(fn.lineno, _char_col(src, fn.lineno, fn.col_offset))]
            while tokens[i].string != "def":
                i += 1
            i += 2  # name
            if tokens[i].string == "[":
                depth = 0
                while True:
                    depth += tokens[i].string == "["
                    depth -= tokens[i].string == "]"
                    i += 1
                    if depth == 0:
                        break
            depth = 0
            while True:
                depth += tokens[i].string == "("
                depth -= tokens[i].string == ")"
                if depth == 0:
                    break
                i += 1
            line, col = tokens[i].end
            edits.append((src.starts[line - 1] + col, 0, f" -> {ret}"))
            added += 1

    if not edits:
        return text, 0
    if needed:
        nl = "\r\n" if "\r\n" in text else "\n"
        block = nl.join(_IMPORT_LINES[n] for n in sorted(needed, key=_import_order))
        after = _import_insert_line(tree)
        if after == 0:
            after = _leading_header_lines(src)
        if after < len(src.lines):
            edits.append((src.starts[after], 0, block + nl))
        else:
            edits.append((len(text), 0, nl + block))
    out = text
    for offset, delete, insert in sorted(edits, key=lambda e: e[0], reverse=True):
        out = out[:offset] + insert + out[offset + delete:]
    return out, added


def _import_order(name: str) -> int:
    return 0 if name == "Path" else 1


def _char_col(src: _Source, line: int, byte_col: int) -> int:
    return src.offset(line, byte_col) - src.starts[line - 1]


def _iter_py(paths: list[Path]):
    for path in paths:
        if path.is_dir():
            for p in sorted(path.rglob("*.py")):
                if not (_SKIP_DIRS & set(p.relative_to(path).parts)):
                    yield p
        else:
            yield path


def _decode(raw: bytes) -> tuple[str, bool]:
    bom = raw.startswith(b"\xef\xbb\xbf")
    return raw.decode("utf-8-sig" if bom else "utf-8"), bom


def _parse(raw: bytes) -> ast.Module | None:
    try:
        return ast.parse(_decode(raw)[0])
    except (SyntaxError, UnicodeDecodeError, ValueError):
        return None


def run_check(paths: list[Path], verbose: bool = False, out=None) -> int:
    out = out or sys.stdout
    total = files = skipped = 0
    for path in _iter_py(paths):
        tree = _parse(path.read_bytes())
        if tree is None:
            skipped += 1
            print(f"skipped (unparseable): {path}", file=sys.stderr)
            continue
        n = count_missing(tree)
        if n:
            files += 1
            total += n
            if verbose:
                print(f"{n:7} {path}", file=out)
    print(f"missing: {total} in {files} files (skipped {skipped})", file=out)
    return 1 if total else 0


def run_rewrite(paths: list[Path], out=None) -> int:
    out = out or sys.stdout
    added = changed = skipped = remaining = 0
    for path in _iter_py(paths):
        raw = path.read_bytes()
        try:
            text, bom = _decode(raw)
            new, n = rewrite_text(text)
            new_tree = ast.parse(new)
        except (SyntaxError, UnicodeDecodeError, ValueError):
            skipped += 1
            print(f"skipped (unparseable): {path}", file=sys.stderr)
            continue
        if n:
            data = new.encode("utf-8")
            path.write_bytes((b"\xef\xbb\xbf" + data) if bom else data)
            changed += 1
            added += n
        remaining += count_missing(new_tree)
    print(
        f"added: {added} in {changed} files; still missing: {remaining} (skipped {skipped})",
        file=out,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Add safely inferable annotations to Python files, or count those still missing."
    )
    parser.add_argument("paths", nargs="+", type=Path, help="files or directories")
    parser.add_argument(
        "--check", action="store_true",
        help="write nothing; print the missing-annotation count and exit 1 when above zero",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="--check: per-file counts")
    ns = parser.parse_args(argv)
    for p in ns.paths:
        if not p.exists():
            parser.error(f"no such file or directory: {p}")
    if ns.check:
        return run_check(ns.paths, ns.verbose)
    return run_rewrite(ns.paths)


if __name__ == "__main__":
    sys.exit(main())
