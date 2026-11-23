#!/usr/bin/env python3
"""Verify a landing from the committed tree: name check, then the touched files' tests, there.

    landed-tree-test-verify.py --repo <root> --paths <rel> [<rel> ...] [--deleted <rel> ...]

The landed tree is HEAD plus `--paths` (worktree bytes), read from git objects through
`commit_source.post_commit_reader` -- no `git archive`, no git spawn. The touched modules, their
tests (`test_<stem>*.py` beside them, plus test files whose imports resolve to them) and the
intra-repo import closure of both are written to `<repo>/scratch/landed-tree-verify/<nonce>/`
(removed on exit). The name check (`landed_names`) runs first; one pytest child runs only when it
passes. Not an engine op: pytest cannot run inside the commit op's 500ms bar.

Exit codes: 0 pass, 1 refuse (names only the worktree has, or a test fails there), 2 could not run
(a guard that cannot run allows and says so).
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

PASS, REFUSE, COULD_NOT_RUN = 0, 1, 2
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_TREE_MODE = 0o40000
_CLOSURE_CAP = 600
_PYTEST_CONFIGS = ("pyproject.toml", "pytest.ini", "tox.ini", "setup.cfg")
_RAM_PER_WORKER_MB = 150


def _bootstrap_engine() -> None:
    sibling = Path(__file__).resolve().parents[2]
    if (sibling / "coordinator_core" / "ops" / "ceremony" / "landed_names.py").is_file():
        sys.path.insert(0, str(sibling))
        return
    try:
        import coordinator_core  # noqa: F401
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
        from cc_invoke import require_dispatch_engine_on_path

        require_dispatch_engine_on_path()


def _console_python() -> str:
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import lib  # noqa: F401
        from python_interp import resolve_console_python

        return resolve_console_python() or sys.executable
    except Exception:  # noqa: BLE001 -- fall back to the running interpreter
        return sys.executable


def _norm(path: str) -> str:
    out = path.replace("\\", "/")
    return out[2:] if out.startswith("./") else out


class _HeadDirs:
    """Directory listings of HEAD's tree, read from objects (no spawn)."""

    def __init__(self, root: Path, common_dir: Path) -> None:
        from coordinator_core.git.git_objects import _read_object, retry_past_stall
        from coordinator_core.git.git_state import _parse_tree_entries, head_tree_sha

        self._root, self._common = root, common_dir
        self._read = lambda sha: retry_past_stall(common_dir, lambda: _read_object(common_dir, sha))
        self._parse = _parse_tree_entries
        self._head_tree_sha = head_tree_sha
        self._dirs: Dict[str, Optional[Dict[str, Tuple[int, str]]]] = {}

    def entries(self, rel_dir: str) -> Dict[str, Tuple[int, str]]:
        if rel_dir not in self._dirs:
            self._dirs[rel_dir] = self._load(rel_dir)
        return self._dirs[rel_dir] or {}

    def _load(self, rel_dir: str) -> Optional[Dict[str, Tuple[int, str]]]:
        sha = self._head_tree_sha(self._root)
        if sha is None:
            return None
        for part in [p for p in rel_dir.split("/") if p]:
            obj = self._read(sha)
            ents = self._parse(obj[1]) if obj is not None and obj[0] == "tree" else None
            hit = ents.get(part) if ents else None
            if hit is None or hit[0] != _TREE_MODE:
                return None
            sha = hit[1]
        obj = self._read(sha)
        return self._parse(obj[1]) if obj is not None and obj[0] == "tree" else None

    def test_files(self, rel_dir: str) -> List[str]:
        out = []
        for name, (mode, _sha) in sorted(self.entries(rel_dir).items()):
            if mode != _TREE_MODE and name.startswith("test_") and name.endswith(".py"):
                out.append(f"{rel_dir}/{name}" if rel_dir else name)
        return out


def _imported_files(rel: str, data: bytes, read: Callable[[str], Optional[bytes]]) -> Set[str]:
    """Landed files `data` (at `rel`) imports: modules, their parent packages, from-imported submodules."""
    try:
        tree = ast.parse(data)
    except (SyntaxError, ValueError, RecursionError):
        return set()
    here = rel.split("/")[:-1]
    found: Set[str] = set()

    def add_module(parts: List[str], roots: Iterable[List[str]]) -> bool:
        hit = False
        for root in roots:
            base = root + parts
            for cand in ("/".join(base) + ".py", "/".join(base) + "/__init__.py"):
                if read(cand) is not None:
                    found.add(cand)
                    hit = True
            if hit:
                for i in range(1, len(base)):
                    init = "/".join(base[:i]) + "/__init__.py"
                    if read(init) is not None:
                        found.add(init)
                return True
        return False

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                add_module(alias.name.split("."), ([], here))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                keep = len(here) - (node.level - 1)
                if keep < 0:
                    continue
                roots: List[List[str]] = [here[:keep]]
            else:
                roots = [[], here]
            base = node.module.split(".") if node.module else []
            if base:
                add_module(base, roots)
            for alias in node.names:
                if alias.name != "*":
                    add_module(base + [alias.name], roots)
    return found


def _norm_stem(stem: str) -> str:
    return stem.replace("-", "_")


def _select_tests(
    modules: List[str], dirs: _HeadDirs, read: Callable[[str], Optional[bytes]], touched: Set[str]
) -> List[str]:
    """Test files covering `modules`: name-matched beside them, or importing them (AST)."""
    tests: List[str] = [m for m in modules if Path(m).name.startswith("test_")]
    seen: Set[str] = set(tests)
    for module in modules:
        if Path(module).name.startswith("test_"):
            continue
        parent = module.rsplit("/", 1)[0] if "/" in module else ""
        stem = _norm_stem(Path(module).stem)
        grand = parent.rsplit("/", 1)[0] if "/" in parent else ""
        join = lambda d, n: f"{d}/{n}" if d else n  # noqa: E731
        cand_dirs = {parent, join(parent, "tests"), join(grand, "tests")}
        for d in sorted(cand_dirs):
            for rel in dirs.test_files(d):
                if rel in seen:
                    continue
                if Path(rel).name.startswith(f"test_{stem}"):
                    seen.add(rel)
                    tests.append(rel)
                    continue
                data = read(rel)
                if data is None or stem.encode() not in data.replace(b"-", b"_"):
                    continue
                if module in _imported_files(rel, data, read):
                    seen.add(rel)
                    tests.append(rel)
    for rel in sorted(touched):
        if Path(rel).name.startswith("test_") and rel.endswith(".py") and rel not in seen:
            seen.add(rel)
            tests.append(rel)
    return tests


def _closure(seeds: List[str], read: Callable[[str], Optional[bytes]]) -> Tuple[List[str], bool]:
    """Seeds plus the intra-repo import closure, ancestor `__init__.py`/`conftest.py`, and pytest config."""
    order: List[str] = []
    seen: Set[str] = set()
    queue = list(seeds)
    for name in _PYTEST_CONFIGS:
        if read(name) is not None:
            queue.append(name)
    truncated = False
    while queue:
        rel = queue.pop(0)
        if rel in seen or read(rel) is None:
            continue
        if len(seen) >= _CLOSURE_CAP:
            truncated = True
            break
        seen.add(rel)
        order.append(rel)
        parts = rel.split("/")[:-1]
        for i in range(len(parts) + 1):
            prefix = "/".join(parts[:i])
            for extra in ("__init__.py", "conftest.py"):
                cand = f"{prefix}/{extra}" if prefix else extra
                if cand not in seen and read(cand) is not None:
                    queue.append(cand)
        if rel.endswith(".py"):
            queue.extend(sorted(_imported_files(rel, read(rel) or b"", read) - seen))
    return order, truncated


def _worker_cap() -> int:
    """min(physical cores / 2, usable RAM MB / 150), at least 1; 1 when load cannot be read."""
    try:
        from coordinator_core.telemetry.host_sampler import read_load

        avail = read_load().get("mem_avail_mb")
        cores = max(1, (os.cpu_count() or 2) // 2)
        if avail is None:
            return 1
        return max(1, min(cores, int(avail) // _RAM_PER_WORKER_MB))
    except Exception:  # noqa: BLE001 -- cannot sample: stay serial
        return 1


def _write_tree(tree: Path, files: List[str], read: Callable[[str], Optional[bytes]]) -> None:
    for rel in files:
        dest = tree / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(read(rel) or b"")


def verify(
    repo: Path, paths: List[str], deleted: List[str], *, timeout: float, workers: Optional[int], out=print
) -> int:
    """Name check, then pytest over the touched files' tests in a materialised landed tree."""
    from coordinator_core.git.git_dir import resolve_git_common_dir
    from coordinator_core.ops.ceremony.commit_source import post_commit_reader
    from coordinator_core.ops.ceremony.landed_names import uncommitted_name_refusals

    paths = [_norm(p) for p in paths]
    common = resolve_git_common_dir(repo)
    read = post_commit_reader(repo, common, paths=paths, deleted_paths=[_norm(p) for p in deleted])
    py_paths = [p for p in paths if p.endswith(".py") and read(p) is not None]
    dirs = _HeadDirs(repo, common)
    tests = _select_tests(py_paths, dirs, read, set(paths))

    refusals = uncommitted_name_refusals(repo, sorted(set(py_paths) | set(tests)), read)
    if refusals is None:
        out("landed-tree-verify: name check could not decide; continuing to tests (unverified)")
    elif refusals:
        for line in refusals:
            out(f"landed-tree-verify: REFUSE {line}")
        return REFUSE
    if not tests:
        out("landed-tree-verify: no covering tests found; name check only")
        return PASS
    if importlib.util.find_spec("pytest") is None:
        out("landed-tree-verify: pytest not importable; tests not run (allowed)")
        return COULD_NOT_RUN

    files, truncated = _closure(list(dict.fromkeys(py_paths + tests)), read)
    if truncated:
        out(f"landed-tree-verify: import closure capped at {_CLOSURE_CAP} files")
    tree = repo / "scratch" / "landed-tree-verify" / uuid.uuid4().hex[:12]
    try:
        _write_tree(tree, files, read)
        cap = workers if workers is not None else _worker_cap()
        argv = [
            _console_python(), "-m", "pytest", "-q", "-p", "no:cacheprovider",
            "--rootdir", str(tree), "-o", "addopts=",
        ]
        if cap > 1 and len(tests) > 1 and importlib.util.find_spec("xdist") is not None:
            argv += ["-n", str(min(cap, len(tests)))]
        argv += tests
        env = {**os.environ, "PYTHONPATH": str(tree), "PYTHONDONTWRITEBYTECODE": "1", "PYTEST_ADDOPTS": ""}
        try:
            proc = subprocess.run(
                argv, cwd=tree, env=env, capture_output=True, text=True, timeout=timeout,
                creationflags=_NO_WINDOW,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            out(f"landed-tree-verify: pytest could not run ({type(exc).__name__}); allowed")
            return COULD_NOT_RUN
        tail = (proc.stdout or "").splitlines()[-40:]
        if proc.returncode in (0, 5):
            out(f"landed-tree-verify: PASS {len(tests)} test file(s) from the landed tree")
            return PASS
        if proc.returncode in (1, 2):
            out("landed-tree-verify: REFUSE tests fail in the landed tree")
            for line in tail + (proc.stderr or "").splitlines()[-10:]:
                out(line)
            return REFUSE
        out(f"landed-tree-verify: pytest rc={proc.returncode}; tests not judged (allowed)")
        for line in (proc.stderr or "").splitlines()[-10:]:
            out(line)
        return COULD_NOT_RUN
    finally:
        shutil.rmtree(tree, ignore_errors=True)
        try:
            tree.parent.rmdir()
        except OSError:
            pass


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Run the name check and touched files' tests against the committed tree.")
    ap.add_argument("--repo", required=True, help="repository root")
    ap.add_argument("--paths", nargs="+", required=True, help="repo-relative paths the land would commit")
    ap.add_argument("--deleted", nargs="*", default=[], help="repo-relative paths the land deletes")
    ap.add_argument("--timeout", type=float, default=600.0, help="pytest child timeout, seconds")
    ap.add_argument("--workers", type=int, default=None, help="xdist workers (default: derived from cores and free RAM)")
    args = ap.parse_args(argv)
    repo = Path(args.repo).resolve()
    if not (repo / ".git").exists():
        print(f"landed-tree-verify: {repo} is not a git repo root; not run (allowed)")
        return COULD_NOT_RUN
    try:
        _bootstrap_engine()
        return verify(repo, args.paths, args.deleted, timeout=args.timeout, workers=args.workers)
    except Exception as exc:  # noqa: BLE001 -- a guard that cannot run allows and says so (DR-402)
        print(f"landed-tree-verify: could not run ({type(exc).__name__}: {exc}); allowed")
        return COULD_NOT_RUN


if __name__ == "__main__":
    sys.exit(main())
