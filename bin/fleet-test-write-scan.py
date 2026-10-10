"""Static fleet scan for test code that writes outside its repo or scratch.

Contract: coordinator/docs/wiki/test-design-discipline/test-filesystem-containment.md.
AST-scans test files, conftest.py and tests/ helpers per repo and flags write
sites whose target is not provably under tmp_path / tempfile / a sandboxed HOME.

Severity: high = home, repo-parent or absolute target; medium = cwd-relative
target (no chdir into scratch in scope) or a literal fake path handed to code
under test; low = mkdtemp/mkstemp with no cleanup.

Invariants: a target of unknown provenance (parameter, attribute, call result)
is never flagged -- only provable danger is reported. Intra-function dataflow
is source-order and flow-insensitive across branches. Exit 1 iff a high finding.
"""
from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Sequence, Iterator, List, NamedTuple, Optional, Tuple

SEV_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3}

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".tox", "site-packages", "build", "dist",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "Intermediate", "Binaries",
    "DerivedDataCache", "Saved", "vendor", "scratch", "scratchpad", ".venv", "venv", "env", ".next",
}
MAX_FILE_BYTES = 2_000_000

HOME_VARS = {"HOME", "USERPROFILE", "HOMEPATH"}
SAFE_ABS_PREFIXES = (
    "/tmp", "/var/tmp", "/dev/", "/private/tmp", "/private/var/folders", "/var/folders",
    "\\\\.\\", "\\\\?\\",  # Windows device namespace (named pipes): never a directory
)
REPO_ROOT_NAME = re.compile(r"^(repo(_?root|_?dir)?|root|project_?root|repo_?path)$", re.I)
TMP_PARAM = re.compile(r"^(tmp|tmp_?path|tmpdir|tmp_?path_?factory|tmpdir_?factory|sandbox\w*|scratch\w*)$|^tmp_", re.I)
HOME_SANDBOX_PARAM = re.compile(r"home", re.I)
HOME_SANDBOX_QUAL = re.compile(r"sandbox|isolated|fake|tmp|temp|mock", re.I)
PATH_KW = re.compile(r"(^|_)(root|dir|path|home|cwd|workdir|dest|output|out)$", re.I)
PATH_FLAG = re.compile(r"^--?[\w-]*(root|dir|path|home|cwd|workspace|output|out)[\w-]*$", re.I)
CLEANUP_NAMES = {"rmtree", "remove", "unlink", "cleanup", "addfinalizer", "rmdir", "removedirs"}
TEMPFILE_FUNCS = {"mkdtemp", "mkstemp", "TemporaryDirectory", "NamedTemporaryFile",
                  "TemporaryFile", "SpooledTemporaryFile", "gettempdir"}
SUBPROCESS_FUNCS = {"run", "Popen", "check_call", "check_output", "call"}
POSITIONAL_IGNORE = {
    "Path", "PurePath", "PurePosixPath", "PureWindowsPath", "str", "repr", "len", "isinstance",
    "print", "getattr", "setattr", "setenv", "delenv", "raises", "warns", "join", "exists",
    "isdir", "isfile", "is_dir", "is_file", "read_text", "read_bytes", "parametrize", "mark",
    "dumps", "loads", "split", "startswith", "endswith", "format", "get", "replace", "strip",
    "lower", "upper", "sub", "match", "search", "compile", "fspath", "abspath", "normpath",
    "basename", "dirname", "samefile", "relpath", "commonpath", "splitext", "isabs",
    "expanduser", "fnmatch", "setdefault", "append", "extend", "add", "encode", "decode",
    "dict", "Mock", "MagicMock", "patch", "object", "assert_called_with",
    "assert_called_once_with", "assert_any_call", "which", "find", "index", "count",
    "write_text", "write_bytes",  # first argument is file CONTENT, the target is the receiver
}
# function name -> (allowed module qualifiers, target positional index)
NAMED_WRITES = {
    "open": ({"", "io", "codecs", "builtins"}, 0),
    "makedirs": ({"", "os"}, 0), "mkdir": ({"os"}, 0), "mkfifo": ({"os"}, 0),
    "symlink": ({"os"}, 1), "link": ({"os"}, 1), "rename": ({"os"}, 1), "replace": ({"os"}, 1),
    "copy": ({"shutil"}, 1), "copy2": ({"shutil"}, 1), "copyfile": ({"", "shutil"}, 1),
    "copytree": ({"", "shutil"}, 1), "move": ({"shutil"}, 1),
    "connect": ({"sqlite3"}, 0),
}
METHOD_WRITES = {"mkdir", "write_text", "write_bytes", "touch", "symlink_to", "hardlink_to"}
PASSTHROUGH_METHODS = {
    "resolve", "absolute", "expanduser", "joinpath", "with_name", "with_suffix", "with_stem",
    "as_posix", "__str__", "__fspath__", "normpath",
}
PASSTHROUGH_FUNCS = {"str", "Path", "PurePath", "fspath", "abspath", "realpath", "normpath",
                     "expanduser", "join", "PosixPath", "WindowsPath"}

# Value kinds; `up` is the climb count for file/rel/cwd kinds.
HOME, PARENT, ABS, ABSX, REL, CWD, FILE, SAFE, UNK = (
    "home", "parent", "abs", "absx", "rel", "cwd", "file", "safe", "unk")
Value = Tuple[str, int]
V_UNK: Value = (UNK, 0)
V_SAFE: Value = (SAFE, 0)
_RANK = {HOME: 7, PARENT: 6, ABS: 5, ABSX: 4.5, REL: 4, CWD: 4, FILE: 3, SAFE: 2, UNK: 1}


class Finding(NamedTuple):
    repo: str
    file: str
    line: int
    severity: str
    rule: str
    reason: str
    snippet: str


def dotted(node: ast.AST) -> str:
    parts: List[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def walk_scope(node: ast.AST) -> Iterator[ast.AST]:
    """Yield nodes of a scope without descending into nested defs/classes."""
    stack = list(ast.iter_child_nodes(node))
    while stack:
        n = stack.pop()
        yield n
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        stack.extend(ast.iter_child_nodes(n))


_PATH_LIST = re.compile(r"^/[^:\s]*:/")


def _is_abs_literal(s: str) -> bool:
    # Absolute on every fleet OS only. `X:/foo` and `\\host\share` are relative on POSIX
    # (they create an `X:` / `\\host` dir in cwd), and every test runs on POSIX somewhere.
    if not s.startswith(("/", "\\\\.\\", "\\\\?\\")) or "\n" in s or "\r" in s:
        return False
    return not _PATH_LIST.match(s)  # `/usr/bin:/bin` is a PATH value, never a directory


def _dotdots(s: str) -> int:
    return sum(1 for seg in re.split(r"[\\/]", s) if seg == "..")


def _segments(s: str) -> int:
    return sum(1 for seg in re.split(r"[\\/]", s) if seg and seg not in (".", ".."))


def _norm_abs(x: str) -> str:
    return os.path.normcase(x).replace("\\", "/").rstrip("/")


def _under_real_home(s: str) -> bool:
    """A non-root user can create entries only under their own home (or scratch)."""
    h, n = _norm_abs(str(Path.home())), _norm_abs(s)
    return n == h or n.startswith(h + "/")


def _rel_value(s: str) -> "Value":
    """Relative literal: up encodes dotdots*100 + descending segments (capped at 99)."""
    return (REL, _dotdots(s) * 100 + min(_segments(s), 99))


def _climbs(v: "Value") -> bool:
    return v[0] in (REL, CWD) and v[1] >= 100


def _abs_value(s: str) -> "Value":
    """Absolute literal: writable only where a non-root user can create entries."""
    if s.startswith(SAFE_ABS_PREFIXES):
        return (SAFE, 0)
    return (ABS, 0) if _under_real_home(s) else (ABSX, 0)


_DECOY_TOKENS = {"tmp", "temp", "fake", "nonexistent", "doesnotexist", "definitely", "missing",
                 "bogus", "dummy", "nowhere"}
_DECOY_SUBSTR = ("non-existent", "does-not-exist", "no-such", "not-a-real", "nonexistent", "doesnotexist")


_PATHLIKE = re.compile(r"^(?:[A-Za-z]:)?[~\w.\-+@\\/]+$")


def has_file_suffix(s: str) -> bool:
    """A trailing .ext marks a file (a read of a missing file), not a directory a test could litter."""
    last = re.split(r"[\\/]", s.rstrip("\\/"))[-1]
    return bool(re.search(r"[^.]\.[A-Za-z0-9]{1,5}$", last))


def is_decoy(s: str) -> bool:
    """True when any path component of a literal carries a decoy-vocabulary word."""
    if len(s) > 200 or s.startswith("-") or not _PATHLIKE.match(s):
        return False
    comps = [c for c in re.split(r"[\\/]", s.lower()) if c]
    if len(comps) == 1 and "/" not in s and "\\" not in s:
        first = re.split(r"[-_.]+", comps[0])[0]
        return first in _DECOY_TOKENS or any(x in comps[0] for x in _DECOY_SUBSTR)
    for comp in comps:
        if any(x in comp for x in _DECOY_SUBSTR):
            return True
        if any(t in _DECOY_TOKENS for t in re.split(r"[-_.]+", comp)):
            return True
    return False


class Flags(NamedTuple):
    sandbox_home: bool
    chdir_ok: bool


def scope_flags(node: ast.AST, params: Sequence[str] = ()) -> Flags:
    sandbox = any(HOME_SANDBOX_PARAM.search(p) and HOME_SANDBOX_QUAL.search(p) for p in params)
    chdir = False
    for n in walk_scope(node):
        if not isinstance(n, ast.Call):
            continue
        name = dotted(n.func)
        last = name.split(".")[-1] if name else (n.func.attr if isinstance(n.func, ast.Attribute) else "")
        if last == "chdir":
            chdir = True
        if re.search(r"sandbox_home|home_sandbox", name):
            sandbox = True
        if last == "setenv" and n.args and isinstance(n.args[0], ast.Constant) \
                and n.args[0].value in HOME_VARS:
            sandbox = True
        if last == "setattr" and any(isinstance(a, ast.Constant) and a.value in ("home", "expanduser")
                                     for a in n.args):
            sandbox = True
        if name.endswith("patch.dict") or last == "dict" and "patch" in name:
            for a in n.args:
                if isinstance(a, ast.Dict) and any(
                        isinstance(k, ast.Constant) and k.value in HOME_VARS for k in a.keys):
                    sandbox = True
    return Flags(sandbox, chdir)


def _is_autouse_fixture(fn: ast.AST) -> bool:
    for d in getattr(fn, "decorator_list", []):
        if isinstance(d, ast.Call) and "fixture" in dotted(d.func):
            for kw in d.keywords:
                if kw.arg == "autouse" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                    return True
    return False


def autouse_flags(tree: ast.AST) -> Flags:
    sandbox = chdir = False
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_autouse_fixture(n):
            f = scope_flags(n, [a.arg for a in n.args.args])
            sandbox |= f.sandbox_home
            chdir |= f.chdir_ok
    return Flags(sandbox, chdir)


# ---- callee inertness ----------------------------------------------------
# A POSIX-absolute literal handed to a function is only a leak if that function can write under it.
# Resolve the callee by name across the repo and follow the parameter; anything unresolvable,
# ambiguous or too deep is treated as a writer, so only a PROVEN reader/formatter drops out.
NO_RESOLVE_HEADS = {"subprocess", "os", "shutil", "sys", "json", "re", "pathlib", "tempfile", "io",
                    "builtins", "sqlite3", "socket", "importlib", "logging", "argparse", "pytest"}
PURE_CALLS = POSITIONAL_IGNORE | {
    "sorted", "list", "tuple", "set", "frozenset", "int", "bool", "bytes", "bytearray", "float",
    "min", "max", "sum", "any", "all", "enumerate", "zip", "map", "filter", "reversed", "type", "hasattr",
    "resolve", "absolute", "realpath", "stat", "lstat", "iterdir", "glob", "rglob",
    "relative_to", "is_relative_to", "as_posix", "joinpath", "with_name", "with_suffix", "rstrip",
    "lstrip", "items", "keys", "values", "pop", "update", "insert", "copy", "parse_args",
    "parse_known_args", "debug", "info", "warning", "error", "exception", "critical", "write", "flush",
    "partition", "rpartition", "splitlines", "casefold", "title", "zfill", "ljust", "rjust", "sha256",
    "md5", "hexdigest", "getenv", "ArgumentParser", "add_argument", "Counter", "OrderedDict",
    "defaultdict", "deque", "cast", "getLogger", "isoformat", "ValueError", "KeyError", "TypeError",
    "RuntimeError", "OSError", "Exception", "SystemExit", "FileNotFoundError",
    "normcase", "splitdrive", "getsize", "getmtime", "lexists", "islink", "ismount", "request",
    "getresponse", "putrequest", "putheader", "endheaders", "send",
}
_WRITE_MODE = re.compile(r"[wax+]")
_EFFECT_CALLS = {"system", "Popen", "popen", "rmtree", "remove", "unlink", "rmdir", "chmod", "utime"}
MAX_CALLEE_DEPTH = 4
MAX_CALLEE_CANDIDATES = 6


def _callee_last(call: ast.Call) -> str:
    name = dotted(call.func)
    return name.split(".")[-1] if name else (call.func.attr if isinstance(call.func, ast.Attribute) else "")


class Callees:
    """Repo-wide `def name -> files` index; callee bodies are parsed lazily."""

    def __init__(self, root: Path):
        self.defs: Dict[str, List[Path]] = {}
        self._ast: Dict[Path, Optional[ast.AST]] = {}
        rx = re.compile(r"^[ \t]*(?:async[ \t]+)?def[ \t]+(\w+)", re.M)
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS
                           and not os.path.exists(os.path.join(dirpath, d, "pyvenv.cfg"))]
            for f in filenames:
                if not f.endswith(".py"):
                    continue
                p = Path(dirpath) / f
                try:
                    if p.stat().st_size > MAX_FILE_BYTES:
                        continue
                    text = p.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for name in set(rx.findall(text)):
                    self.defs.setdefault(name, []).append(p)

    def _tree(self, p: Path) -> Optional[ast.AST]:
        if p not in self._ast:
            parsed = _parse(p)
            self._ast[p] = parsed[0] if parsed else None
        return self._ast[p]

    def _candidates(self, name: str, home: Optional[Path]) -> List[ast.AST]:
        files = self.defs.get(name, [])
        if home is not None and home in files:
            files = [home]  # a same-file def shadows every other of that name
        if not files or len(files) > MAX_CALLEE_CANDIDATES:
            return []
        out: List[ast.AST] = []
        for p in files:
            tree = self._tree(p)
            if tree is None:
                return []
            for n in ast.walk(tree):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
                    n.home = p  # a call inside this body resolves against ITS file first
                    out.append(n)
        return out

    def param_inert(self, call: ast.Call, pos: Optional[int], kw: Optional[str], home: Optional[Path],
                    depth: int = 0) -> bool:
        """True only when every candidate callee provably never writes under the argument."""
        last = _callee_last(call)
        if not last or dotted(call.func).split(".")[0] in NO_RESOLVE_HEADS or depth >= MAX_CALLEE_DEPTH:
            return False
        fns = self._candidates(last, home)
        return bool(fns) and all(self._fn_inert(fn, pos, kw, home, depth) for fn in fns)

    def _fn_inert(self, fn, pos: Optional[int], kw: Optional[str], home: Optional[Path], depth: int) -> bool:
        home = getattr(fn, "home", home)
        a = fn.args
        params = [x.arg for x in a.posonlyargs + a.args]
        if params and params[0] in ("self", "cls"):
            params = params[1:]
        if kw is not None:
            if kw in params or kw in [x.arg for x in a.kwonlyargs]:
                target = kw
            elif a.kwarg:
                target = a.kwarg.arg
            else:
                return False
        elif pos is not None and pos < len(params):
            target = params[pos]
        elif a.vararg:
            target = a.vararg.arg
        else:
            return False
        return not self._reaches_writer(fn, target, home, depth)

    def _reaches_writer(self, fn, param: str, home: Optional[Path], depth: int) -> bool:
        tainted = {param}

        def mentions(e: ast.AST) -> bool:
            return any(isinstance(n, ast.Name) and n.id in tainted for n in ast.walk(e))

        def names(e: ast.AST) -> List[str]:
            return [x.id for x in ast.walk(e) if isinstance(x, ast.Name)]

        body = list(ast.walk(fn))
        for _ in range(2):  # two passes settle aliases assigned out of source order
            for n in body:
                if isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr)) \
                        and n.value is not None and mentions(n.value):
                    targets = n.targets if isinstance(n, ast.Assign) else [n.target]
                    for t in targets:
                        base = t
                        while isinstance(base, ast.Subscript):
                            base = base.value  # `obj[k] = v` fills a local container
                        if isinstance(base, ast.Attribute):
                            return True  # escapes into object state this scan cannot follow
                        tainted.update(names(base))
                elif isinstance(n, (ast.For, ast.AsyncFor)) and mentions(n.iter):
                    tainted.update(names(n.target))
                elif isinstance(n, ast.withitem) and n.optional_vars is not None \
                        and mentions(n.context_expr):
                    tainted.update(names(n.optional_vars))
        for n in body:
            if not isinstance(n, ast.Call):
                continue
            last = _callee_last(n)
            fq = dotted(n.func)
            recv = n.func.value if isinstance(n.func, ast.Attribute) else None
            args = list(n.args) + [k.value for k in n.keywords]
            if not any(mentions(x) for x in args) and not (recv is not None and mentions(recv)):
                continue
            if last in METHOD_WRITES:
                if recv is not None and mentions(recv):
                    return True
                continue  # the tainted value is only the written CONTENT
            if dotted(n.func) in ("open", "io.open"):
                mode = n.args[1] if len(n.args) > 1 else next(
                    (k.value for k in n.keywords if k.arg == "mode"), None)
                if mode is not None and not (isinstance(mode, ast.Constant) and isinstance(mode.value, str)
                                             and not _WRITE_MODE.search(mode.value)):
                    return True
                continue
            qual = fq.split(".")[-2] if "." in fq else ("" if fq else "?")
            if last in NAMED_WRITES and qual in NAMED_WRITES[last][0] or last in TEMPFILE_FUNCS \
                    or last in _EFFECT_CALLS:
                return True
            if last in SUBPROCESS_FUNCS and qual in ("", "subprocess"):
                # argv and cwd name what the child touches; env=/input= only carry values to it
                if any(mentions(x) for x in n.args[:1]) \
                        or any(k.arg == "cwd" and mentions(k.value) for k in n.keywords):
                    return True
                continue
            if last[:1].isupper():
                continue  # a data constructor (NamedTuple, dataclass, exception)
            if last in PURE_CALLS:
                continue
            if recv is not None and mentions(recv):
                return True  # method called ON the value: unknown type, unknown effect
            idxs = [i for i, x in enumerate(n.args) if mentions(x)]
            kws = [k.arg for k in n.keywords if mentions(k.value)]
            if not all(self.param_inert(n, i, None, home, depth + 1) for i in idxs) or \
                    not all(k is not None and self.param_inert(n, None, k, home, depth + 1) for k in kws):
                return True
        return False


HOOK_CALL = re.compile(r"hook|guard|compute_context", re.I)
PAYLOAD_KEY = re.compile(r"^(cwd|project_dir|workspace)$|(_path|_dir|root)$", re.I)
NOT_A_FILESYSTEM_KEY = re.compile(r"^(hook|url|route|http|request)_path$", re.I)  # a URL route, never a directory


def runs_hook(tree: ast.AST, relfile: str) -> bool:
    """A test file that drives a hook feeds it a payload whose paths the hook may act on."""
    if re.search(r"hook|guard", relfile.rsplit("/", 1)[-1], re.I):
        return True
    return any(isinstance(n, ast.Call) and HOOK_CALL.search(_callee_last(n)) for n in ast.walk(tree))


class Analyzer:
    def __init__(self, tree: ast.AST, lines: List[str], repo: str, relfile: str,
                 depth: int, inherited: Flags, callees: Optional[Callees] = None,
                 home: Optional[Path] = None):
        self.lines, self.repo, self.relfile, self.depth = lines, repo, relfile, depth
        self.callees, self.home = callees, home
        self.runs_hook = runs_hook(tree, relfile)
        self.findings: List[Finding] = []
        self._seen: Dict[int, int] = {}
        self.tree = tree
        self.inherited = inherited

    def run(self) -> List[Finding]:
        self._scope(self.tree, {}, self.inherited, [])
        return self.findings

    def _scope(self, node: ast.AST, env: Dict[str, Value], inherited: Flags, params: List[str]):
        own = scope_flags(node, params)
        sc = _Scope(self, dict(env), Flags(inherited.sandbox_home or own.sandbox_home,
                                            inherited.chdir_ok or own.chdir_ok))
        for p in params:
            sc.env[p] = V_SAFE if TMP_PARAM.search(p) else V_UNK
        for stmt in getattr(node, "body", []):
            sc.visit(stmt)
        sc.finish()

    def add(self, node: ast.AST, sev: str, rule: str, reason: str):
        """One finding per source line: the highest severity wins, first rule on ties."""
        line = getattr(node, "lineno", 0)
        snip = self.lines[line - 1].strip() if 0 < line <= len(self.lines) else ""
        new = Finding(self.repo, self.relfile, line, sev, rule, reason, snip[:140])
        idx = self._seen.get(line)
        if idx is None:
            self._seen[line] = len(self.findings)
            self.findings.append(new)
        elif SEV_RANK[sev] > SEV_RANK[self.findings[idx].severity]:
            self.findings[idx] = new


class _Scope(ast.NodeVisitor):
    def __init__(self, an: Analyzer, env: Dict[str, Value], flags: Flags):
        self.an, self.env, self.flags = an, env, flags
        self.leaks: List[Tuple[ast.AST, str]] = []
        self.cleanup = False
        self.with_calls = set()

    def finish(self):
        if not self.cleanup:
            for node, what in self.leaks:
                self.an.add(node, "low", "temp-leak", f"{what} with no cleanup (rmtree/finalizer/context manager)")

    # ---- scoping -------------------------------------------------------
    def _def(self, node):
        params = [a.arg for a in node.args.args + node.args.kwonlyargs] if hasattr(node, "args") else []
        self.an._scope(node, self.env, self.flags, params)

    visit_FunctionDef = visit_AsyncFunctionDef = _def

    def visit_ClassDef(self, node):
        self.an._scope(node, self.env, self.flags, [])

    # ---- hook payloads -------------------------------------------------
    def visit_Dict(self, node):
        if self.an.runs_hook:
            for k, v in zip(node.keys, node.values):
                if isinstance(k, ast.Constant) and isinstance(k.value, str) and PAYLOAD_KEY.search(k.value) \
                        and not NOT_A_FILESYSTEM_KEY.match(k.value) \
                        and isinstance(v, ast.Constant) and isinstance(v.value, str) \
                        and _is_abs_literal(v.value) and not v.value.startswith(SAFE_ABS_PREFIXES):
                    self.an.add(v, "high", "hook-payload-path",
                                f"payload {k.value!r}: {v.value!r} is POSIX-absolute; a hook run in this test "
                                "may write under it (on Windows, the drive root)")
        self.generic_visit(node)

    # ---- binding -------------------------------------------------------
    def visit_Assign(self, node):
        self.visit(node.value)
        v = self.classify(node.value)
        for t in node.targets:
            if isinstance(t, ast.Name):
                self.env[t.id] = v
            else:
                for n in ast.walk(t):
                    if isinstance(n, ast.Name):
                        self.env[n.id] = V_UNK

    def visit_AnnAssign(self, node):
        if node.value is not None:
            self.visit(node.value)
            if isinstance(node.target, ast.Name):
                self.env[node.target.id] = self.classify(node.value)

    def visit_AugAssign(self, node):
        self.visit(node.value)
        if isinstance(node.target, ast.Name) and isinstance(node.op, ast.Div):
            self.env[node.target.id] = self._join(self.classify(node.target), self.classify(node.value))

    def _with(self, node):
        for item in node.items:
            if isinstance(item.context_expr, ast.Call):
                self.with_calls.add(id(item.context_expr))
            self.visit(item.context_expr)
            if isinstance(item.optional_vars, ast.Name):
                self.env[item.optional_vars.id] = self.classify(item.context_expr)
        for s in node.body:
            self.visit(s)

    visit_With = visit_AsyncWith = _with

    # ---- classification ------------------------------------------------
    def classify(self, node: ast.AST) -> Value:
        v = self._classify(node)
        if v[0] == FILE and v[1] > self.an.depth + 1:
            return (PARENT, 0)
        if v[0] == HOME and self.flags.sandbox_home:
            return V_SAFE
        return v

    def _join(self, left: Value, right: Value) -> Value:
        if right[0] in (HOME, ABS, ABSX, PARENT):
            return right
        dd, sg = (right[1] // 100, right[1] % 100) if right[0] == REL else (0, 0)
        if left[0] in (SAFE, UNK, HOME, ABS, ABSX, PARENT):
            return left
        if left[0] == FILE:
            if right[0] == UNK:
                sg = 1
            return (FILE, left[1] + dd - sg)
        if left[0] in (REL, CWD):
            return (PARENT, 0) if dd else left
        return left

    def _worst(self, vals: List[Value]) -> Value:
        return max(vals, key=lambda v: _RANK[v[0]]) if vals else V_UNK

    def _classify(self, node: ast.AST) -> Value:
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, str):
                return V_UNK
            s = node.value
            if s.startswith("~"):
                return (HOME, 0)
            if _is_abs_literal(s):
                return _abs_value(s)
            return _rel_value(s)
        if isinstance(node, ast.Name):
            if node.id in self.env:
                return self.env[node.id]
            if node.id == "__file__":
                return (FILE, 0)
            if node.id == "tmp_path" or TMP_PARAM.search(node.id):
                return V_SAFE
            if REPO_ROOT_NAME.match(node.id):
                return (FILE, self.an.depth + 1)
            return V_UNK
        if isinstance(node, ast.Attribute):
            if node.attr == "parent":
                return self._parent(self.classify(node.value))
            return V_UNK
        if isinstance(node, ast.Subscript):
            if isinstance(node.value, ast.Attribute) and node.value.attr == "parents":
                base = self.classify(node.value.value)
                n = node.slice.value if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, int) else None
                if base[0] == FILE and n is not None:
                    return (FILE, base[1] + n + 1)
                if base[0] == CWD and n is not None:
                    return (PARENT, 0)
                return base
            if dotted(node.value).endswith("environ") and isinstance(node.slice, ast.Constant) \
                    and node.slice.value in HOME_VARS:
                return (HOME, 0)
            return V_UNK
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Div, ast.Add)):
            l, r = self.classify(node.left), self.classify(node.right)
            if isinstance(node.op, ast.Add):
                return l
            return self._join(l, r)
        if isinstance(node, ast.IfExp):
            return self._worst([self.classify(node.body), self.classify(node.orelse)])
        if isinstance(node, ast.BoolOp):
            return self._worst([self.classify(v) for v in node.values])
        if isinstance(node, ast.JoinedStr):
            if not node.values:
                return V_UNK
            head = node.values[0]
            first = self.classify(head.value if isinstance(head, ast.FormattedValue) else head)
            return first if first[0] != REL or isinstance(head, ast.Constant) else V_UNK
        if isinstance(node, ast.Call):
            return self._classify_call(node)
        return V_UNK

    def _parent(self, v: Value) -> Value:
        if v[0] == FILE:
            return (FILE, v[1] + 1)
        if v[0] == CWD:
            return (PARENT, 0)
        return v

    def _classify_call(self, node: ast.Call) -> Value:
        func = node.func
        name = dotted(func)
        last = func.attr if isinstance(func, ast.Attribute) else (func.id if isinstance(func, ast.Name) else "")
        if name.endswith("Path.home") or name == "home" and not node.args:
            return (HOME, 0)
        if name.endswith("Path.cwd") or name in ("os.getcwd", "getcwd"):
            return (CWD, 0)
        if last == "expanduser" and name.endswith("path.expanduser") or name == "expanduser":
            v = self.classify(node.args[0]) if node.args else V_UNK
            return (HOME, 0) if v[0] in (HOME,) else v
        if (name.endswith("environ.get") or name.endswith("getenv")) and node.args \
                and isinstance(node.args[0], ast.Constant) and node.args[0].value in HOME_VARS:
            return (HOME, 0)
        if last in TEMPFILE_FUNCS:
            for kw in node.keywords:
                if kw.arg == "dir":
                    return self.classify(kw.value)
            if last in ("mkdtemp", "mkstemp") and len(node.args) >= 3:
                return self.classify(node.args[2])
            return V_SAFE
        if name.endswith("path.dirname") or name == "dirname":
            return self._parent(self.classify(node.args[0])) if node.args else V_UNK
        if name.endswith("path.join") or name == "join" and "path" in name:
            vals = [self.classify(a) for a in node.args]
            out = vals[0] if vals else V_UNK
            for v in vals[1:]:
                out = self._join(out, v)
            return out
        if isinstance(func, ast.Attribute):
            recv = self.classify(func.value)
            if last in PASSTHROUGH_METHODS or recv[0] == SAFE:
                out = recv
                if last == "joinpath":
                    for a in node.args:
                        out = self._join(out, self.classify(a))
                return out
            return V_UNK
        if last in PASSTHROUGH_FUNCS and node.args:
            vals = [self.classify(a) for a in node.args]
            out = vals[0]
            for v in vals[1:]:
                out = self._join(out, v)
            return out
        return V_UNK

    # ---- detection -----------------------------------------------------
    def _judge(self, v: Value, node: ast.AST, what: str):
        kind = v[0]
        if kind == HOME:
            self.an.add(node, "high", "home-write", f"{what} targets the real home directory")
        elif kind == PARENT or _climbs(v):
            self.an.add(node, "high", "parent-write", f"{what} targets a path climbing out of the repo/scratch (.. / parent)")
        elif kind == ABS:
            self.an.add(node, "high", "absolute-write", f"{what} targets an absolute path under a user-writable location")
        elif kind == ABSX:
            self.an.add(node, "high", "drive-root-write", f"{what} targets a POSIX-absolute path; on Windows it resolves to the current drive root and creates real folders there")
        elif kind in (REL, CWD) and not self.flags.chdir_ok:
            self.an.add(node, "medium", "relative-write", f"{what} is cwd-relative and no chdir into scratch in scope")

    def _write_mode(self, call: ast.Call, idx: int) -> bool:
        mode = call.args[idx] if len(call.args) > idx else None
        for kw in call.keywords:
            if kw.arg == "mode":
                mode = kw.value
        return isinstance(mode, ast.Constant) and isinstance(mode.value, str) \
            and any(c in mode.value for c in "wax+")

    def visit_Call(self, node: ast.Call):
        func = node.func
        name = dotted(func)
        last = func.attr if isinstance(func, ast.Attribute) else (func.id if isinstance(func, ast.Name) else "")
        module = name.rsplit(".", 1)[0] if "." in name else ""
        module = module.split(".")[-1] if module else ""
        targets: List[Tuple[ast.AST, str]] = []

        if last in CLEANUP_NAMES:
            self.cleanup = True

        if isinstance(func, ast.Attribute) and not (name and module in ("os", "shutil", "tempfile")):
            recv = func.value
            if last in METHOD_WRITES:
                targets.append((recv, f".{last}()"))
            elif last == "rename" and node.args:
                targets.append((node.args[0], ".rename()"))
            elif last == "open" and self._write_mode(node, 0):
                targets.append((recv, ".open(write)"))

        spec = NAMED_WRITES.get(last)
        if spec and module in spec[0] and (name or last == "open"):
            idx = spec[1]
            if last == "open":
                if self._write_mode(node, 1) and node.args:
                    targets.append((node.args[0], "open(write)"))
            elif len(node.args) > idx:
                targets.append((node.args[idx], f"{module + '.' if module else ''}{last}()"))

        if last in TEMPFILE_FUNCS and module in ("", "tempfile") and last != "gettempdir":
            dir_node = None
            for kw in node.keywords:
                if kw.arg == "dir":
                    dir_node = kw.value
            if dir_node is None and last in ("mkdtemp", "mkstemp") and len(node.args) >= 3:
                dir_node = node.args[2]
            if dir_node is not None:
                targets.append((dir_node, f"tempfile.{last}(dir=)"))
            elif id(node) not in self.with_calls and last in ("mkdtemp", "mkstemp", "TemporaryDirectory") \
                    or last == "NamedTemporaryFile" and any(
                        kw.arg == "delete" and isinstance(kw.value, ast.Constant) and kw.value.value is False
                        for kw in node.keywords):
                self.leaks.append((node, f"tempfile.{last}()"))

        for expr, what in targets:
            v = self.classify(expr)
            self._judge(v, node, what)
            self._decoy(expr, v, node, what, write=True)

        self._scan_args(node, last)
        self.generic_visit(node)

    def _scan_args(self, node: ast.Call, last: str):
        if last in ("setenv", "delenv", "setattr", "chdir") or last in TEMPFILE_FUNCS:
            return
        for kw in node.keywords:
            if kw.arg and PATH_KW.search(kw.arg) and not self._inert_abs(node, kw.value, kw=kw.arg):
                self._root_arg(kw.value, node, f"kwarg {kw.arg}=")
        for a in list(node.args) + [kw.value for kw in node.keywords]:
            if isinstance(a, (ast.List, ast.Tuple)):
                els = a.elts
                for i, e in enumerate(els):
                    if isinstance(e, ast.Constant) and isinstance(e.value, str):
                        s = e.value
                        if "=" in s and PATH_FLAG.match(s.split("=", 1)[0]):
                            self._root_arg(ast.Constant(value=s.split("=", 1)[1], lineno=e.lineno), node, f"flag {s.split('=')[0]}")
                        elif PATH_FLAG.match(s) and i + 1 < len(els):
                            self._root_arg(els[i + 1], node, f"flag {s}")
        if last in SUBPROCESS_FUNCS and not self.flags.chdir_ok and not any(
                kw.arg == "cwd" and self.classify(kw.value)[0] in (SAFE, FILE) for kw in node.keywords):
            for a in node.args[:1]:
                if isinstance(a, (ast.List, ast.Tuple)):
                    for e in a.elts:
                        if isinstance(e, ast.Constant) and isinstance(e.value, str) \
                                and not _is_abs_literal(e.value) and is_decoy(e.value) \
                                and not has_file_suffix(e.value):
                            self.an.add(node, "high", "decoy-path",
                                        f"subprocess argv carries relative decoy path {e.value!r}; resolves against the pytest cwd")
        if last in POSITIONAL_IGNORE:
            return
        for i, a in enumerate(node.args):
            prev = node.args[i - 1] if i else None
            if isinstance(prev, ast.Constant) and isinstance(prev.value, str) and prev.value.startswith("-") \
                    and not PATH_FLAG.match(prev.value) and isinstance(a, ast.Constant) \
                    and isinstance(a.value, str) and _is_abs_literal(a.value):
                continue  # `--tool-cli /x/tool`: the value of a flag not named for a directory
            if self._inert_abs(node, a, pos=i):
                continue
            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                s = a.value
                if is_decoy(s) and ("/" in s or "\\" in s) and not s.startswith(SAFE_ABS_PREFIXES) \
                        and not has_file_suffix(s):
                    if _is_abs_literal(s):
                        sev = "high"
                    else:
                        sev = None if self.flags.chdir_ok else "high"
                    if sev:
                        self.an.add(node, sev, "fake-path-arg",
                                    f"literal fake path {s!r} passed to code under test; may be created")
                elif _is_abs_literal(s) and not s.startswith(SAFE_ABS_PREFIXES) \
                        and re.search(r"main|run|init|create|setup|make|build|write|save|install|scaffold|mkdir", last, re.I):
                    self.an.add(node, "high", "absolute-arg", f"absolute literal {s!r} passed positionally to {last}()")
            elif isinstance(a, ast.Name) and re.search(r"root|dir|path|home", a.id, re.I):
                v = self.env.get(a.id, V_UNK)
                if v[0] in (ABS, ABSX):
                    self.an.add(node, "high", "absolute-arg",
                                f"{a.id} holds an absolute literal passed positionally to {last or 'call'}()")

    def _inert_abs(self, node: ast.Call, value: ast.AST, pos: Optional[int] = None,
                   kw: Optional[str] = None) -> bool:
        """A POSIX-absolute argument whose callee provably never writes under it (see Callees)."""
        if self.an.callees is None or self.classify(value)[0] != ABSX:
            return False
        return self.an.callees.param_inert(node, pos, kw, self.an.home)

    def _root_arg(self, value: ast.AST, node: ast.Call, what: str):
        v = self.classify(value)
        if what == "kwarg cwd=" and (v[0] == PARENT or _climbs(v)):
            self.an.add(node, "info", "root-arg", "subprocess cwd outside the repo; relative writes land there")
        elif v[0] in (HOME, PARENT, ABS) or _climbs(v):
            self.an.add(node, "high", "root-arg", f"{what} is {'home' if v[0] == HOME else 'parent/absolute'}-rooted; code under test may create it")
        elif v[0] == ABSX:
            self.an.add(node, "high", "root-arg", f"{what} is a POSIX-absolute path; on Windows it resolves to the drive root")
        else:
            self._decoy(value, v, node, what)

    def _decoy(self, expr: ast.AST, v: Value, node: ast.Call, what: str, write: bool = False):
        if v[0] not in (REL, CWD, HOME, PARENT, ABS, ABSX):
            return
        relative = v[0] in (REL, CWD)
        if relative and self.flags.chdir_ok:
            return
        for n in ast.walk(expr):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and is_decoy(n.value) \
                    and (write or not has_file_suffix(n.value)):
                self.an.add(node, "high", "decoy-path",
                            f"{what} uses decoy-named path {n.value!r} (code under test may create it)")
                return


# ---- discovery -----------------------------------------------------------
def is_test_file(rel: Path) -> bool:
    n = rel.name
    if not n.endswith(".py"):
        return False
    if fnmatch.fnmatch(n, "test_*.py") or n.endswith("_test.py") or n == "conftest.py":
        return True
    return any(p in ("tests", "test") for p in rel.parts[:-1])


def iter_test_files(root: Path) -> Iterator[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS
                       and not os.path.exists(os.path.join(dirpath, d, "pyvenv.cfg"))]
        for f in filenames:
            p = Path(dirpath) / f
            if is_test_file(p.relative_to(root)):
                yield p


def _parse(path: Path) -> Optional[Tuple[ast.AST, List[str]]]:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        text = path.read_text(encoding="utf-8", errors="replace")
        return ast.parse(text), text.splitlines()
    except (SyntaxError, ValueError, OSError):
        return None


def scan_repo(name: str, root: Path) -> Tuple[List[Finding], int]:
    findings: List[Finding] = []
    parse_errors = 0
    conftest_cache: Dict[Path, Flags] = {}
    callees = Callees(root)

    def conftest_flags(d: Path) -> Flags:
        if d not in conftest_cache:
            parsed = _parse(d / "conftest.py") if (d / "conftest.py").is_file() else None
            conftest_cache[d] = autouse_flags(parsed[0]) if parsed else Flags(False, False)
        return conftest_cache[d]

    for path in sorted(iter_test_files(root)):
        parsed = _parse(path)
        if parsed is None:
            parse_errors += 1
            continue
        tree, lines = parsed
        rel = path.relative_to(root)
        sandbox = chdir = False
        d = path.parent
        while True:
            f = conftest_flags(d)
            sandbox |= f.sandbox_home
            chdir |= f.chdir_ok
            if d == root or d == d.parent:
                break
            d = d.parent
        own = autouse_flags(tree)
        inherited = Flags(sandbox or own.sandbox_home, chdir or own.chdir_ok)
        try:
            findings.extend(Analyzer(tree, lines, name, rel.as_posix(), len(rel.parts) - 1, inherited,
                                     callees, path).run())
        except RecursionError:
            parse_errors += 1
    findings.sort(key=lambda f: (f.file, f.line))
    return findings, parse_errors


# ---- fleet roster --------------------------------------------------------
def _settings_home() -> Path:
    env = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if env:
        return Path(env)
    return Path(os.environ.get("CLAUDE_HOME") or Path.home()) / ".coordinator-claude-settings"


def _machine_local(*args: str) -> str:
    bindir = _settings_home() / "bin"
    exe = bindir / ("machine-local.cmd" if os.name == "nt" else "machine-local")
    r = subprocess.run([str(exe), *args], capture_output=True, text=True, timeout=60,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode != 0:
        raise RuntimeError(f"machine-local {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def fleet_repos() -> Dict[str, Path]:
    out: Dict[str, Path] = {}
    try:
        registry = json.loads(_machine_local("dump"))
    except (RuntimeError, ValueError):
        # `dump` exits non-zero when any one key is unresolvable; ask per key so
        # only that key is skipped.
        registry = {}
        for key in _machine_local("keys").splitlines():
            key = key.strip()
            if not key.startswith("repos."):
                continue
            try:
                registry[key] = _machine_local("get", key)
            except RuntimeError:
                continue
    for key, val in registry.items():
        if not key.startswith("repos.") or not isinstance(val, str):
            continue
        if val and Path(val).is_dir() and Path(val).resolve() not in {p.resolve() for p in out.values()}:
            out[key[len("repos."):]] = Path(val)
    return out


# ---- output --------------------------------------------------------------
def counts(findings: List[Finding]) -> Dict[str, int]:
    c = {"high": 0, "medium": 0, "low": 0, "info": 0}
    for f in findings:
        c[f.severity] += 1
    return c


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--repo", action="append", help="limit to a repo key (repeatable)")
    ap.add_argument("--path", action="append", help="scan a directory directly (repeatable)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--min-severity", choices=list(SEV_RANK), default="low")
    args = ap.parse_args(argv)
    sys.setrecursionlimit(max(sys.getrecursionlimit(), 5000))

    repos: Dict[str, Path] = {}
    if args.path:
        for p in args.path:
            repos[Path(p).name] = Path(p)
    else:
        repos = fleet_repos()
        if args.repo:
            unknown = [r for r in args.repo if r not in repos]
            if unknown:
                print(f"unknown or missing repo key(s): {', '.join(unknown)}", file=sys.stderr)
            repos = {k: v for k, v in repos.items() if k in args.repo}

    floor = SEV_RANK[args.min_severity]
    report = {}
    any_high = False
    for name, root in repos.items():
        found, perr = scan_repo(name, root)
        found = [f for f in found if SEV_RANK[f.severity] >= floor]
        any_high |= any(f.severity == "high" for f in found)
        report[name] = {"path": str(root), "counts": counts(found), "parse_errors": perr,
                        "findings": [f._asdict() for f in found]}

    if args.json:
        print(json.dumps({"repos": report}, indent=2))
    else:
        for name, r in report.items():
            c = r["counts"]
            print(f"\n== {name} ({r['path']})  high={c['high']} medium={c['medium']} low={c['low']}"
                  f" parse_errors={r['parse_errors']}")
            for f in sorted(r["findings"], key=lambda f: (-SEV_RANK[f["severity"]], f["file"], f["line"])):
                print(f"  {f['file']}:{f['line']}  [{f['severity']}] {f['rule']}: {f['reason']}")
                print(f"      {f['snippet']}")
    return 1 if any_high else 0


if __name__ == "__main__":
    sys.exit(main())
