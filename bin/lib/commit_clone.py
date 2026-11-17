"""Materialise the publisher-code closure of one commit into a per-sha directory and run an entry
from it, so a publish or percolate round never reads the live working tree. Stdlib only: callers
load this before the engine is bound.

The clone is not a full checkout: blobs go straight from the commit tree (`git ls-tree` plus one
`git cat-file --batch`) into `<cache>/<sha>`. A module outside that seed is filled from the same
commit on first import (`run_entry_from_clone` installs the filler), never read from the live tree.
Run as a script (`commit_clone.py materialise <sha>`) to build or repair a clone by hand."""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import json
import os
import re
import runpy
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_MARKER = "commit-clone-v2.json"
# Bumped when the clone's contents change shape: a clone of an older format is rebuilt, not reused.
_FORMAT = 5
_LEGACY_MARKER = "commit-clone.json"
_CACHE_DIRNAME = "claude-klabauter-commit-clone"
_RETENTION = 3
_IN_USE_GRACE_SECS = 3600
_FULL_SHA_RE = re.compile(r"[0-9a-f]{40}")
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_SPARSE_ROOTS = ("coordinator", "coordinator_core", "pyproject.toml")  # the tree roots the seed is drawn from
_SEED_FILES = frozenset(
    ("coordinator_core/__init__.py",)  # without it a `coordinator_core` elsewhere on sys.path wins
    # The engine-root probe (`engine_bootstrap._walk_up_to_checkout`) needs it beside
    # `coordinator_core/`; without it a child resolves the published engine, which has no publisher.
    + ("pyproject.toml",)
    # publish.py's end-of-run argv-parity gate reads this baseline; `_is_wanted` skips test dirs.
    + ("coordinator_core/tests/engine_cli_argv_parity_baseline.json",)
    # publish.py and percolate-round.py load it by path before bootstrap, which the import filler never sees.
    + ("coordinator_core/temp_layout.py",)
    # coordinator_core/__init__.py imports it eagerly; unseeded, every clone import dies at __init__.
    + ("coordinator_core/op_scopes.py",)
    + tuple(
        "coordinator/bin/" + name
        for name in (
            "publish.py", "coordinator-publish.py", "percolate-round.py", "percolate-gate.py",
            "percolate-push.py", "percolate-parse-dryrun.py", "publish-allowlist-generate.py",
            "check-version-consistency.py",
            "check-install-doc-payload.py", "percolate-published-unscanned-exceptions.yaml",
            "repo-key-literal-waivers.json",
        )
    )
)
_SEED_DIRS = ("coordinator/bin/lib/", "coordinator/lib/percolate/", "coordinator_core/percolate/")
_EXTRA_FILE = "seed-extra.json"
# Inside `<clone>/.git` so no clone root on sys.path can import it by accident.
_SITE_DIRNAME = "commit-clone-site"
_SITE_SOURCE = """\
# Written by commit_clone: every Python child of a round run from this clone fills repo modules
# from the commit, as the round's own process does, and records what it loaded.
import atexit, importlib.util, sys
from pathlib import Path
_clone = Path({clone!r})
_spec = importlib.util.spec_from_file_location("_commit_clone_site", {module!r})
_cc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cc)
sys.meta_path.append(_cc._CommitFill(_clone))
atexit.register(_cc._record_extra, _clone)
# Chain to the sitecustomize this one shadows (Homebrew's adds its site-packages: without it the
# child loses pyyaml). Our directory leaves sys.path; the child no longer needs it.
_here = Path(__file__).resolve().parent
sys.path[:] = [p for p in sys.path if not p or Path(p).resolve() != _here]
del sys.modules["sitecustomize"]
try:
    import sitecustomize  # noqa: F401
except ModuleNotFoundError as _exc:
    if _exc.name != "sitecustomize":
        raise
"""
# Import root -> clone-relative directories a dotted module name resolves under.
_FILL_ROOTS = {"coordinator_core": ("",), "coordinator": ("",), "percolate": ("coordinator/lib",)}


class CommitCloneError(RuntimeError):
    """The clone cannot be built or is not one; the message names the cause and a runnable retry."""


def _remediation(repo_root: Path, sha: str) -> str:
    script = Path(__file__).resolve()
    return f'python "{script}" materialise {sha} --repo "{repo_root}"'


def default_cache_root() -> Path:
    """`<managed temp>/claude-klabauter-commit-clone`; `temp_layout` is loaded by path (stdlib-only)."""
    path = Path(__file__).resolve().parents[3] / "coordinator_core" / "temp_layout.py"
    spec = importlib.util.spec_from_file_location("_commit_clone_temp_layout", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.managed_tempdir() / _CACHE_DIRNAME


def _read_marker(root: Path, name: str = _MARKER) -> dict | None:
    try:
        data = json.loads((root / ".git" / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _read_clone_marker(root: Path) -> dict | None:
    """The marker naming a clone's sha and source: this format's, else the legacy shared-clone one
    (read for `source_root` only; a legacy entry is never a warm hit, see `_usable_marker`)."""
    return _read_marker(root) or _read_marker(root, _LEGACY_MARKER)


def _alternates_target(clone: Path) -> Path | None:
    try:
        line = (clone / ".git" / "objects" / "info" / "alternates").read_text(encoding="utf-8").splitlines()[0]
    except (OSError, IndexError):
        return None
    return Path(line.strip()) if line.strip() else None


def _usable_marker(dest: Path, sha: str) -> dict | None:
    """The marker when `dest` is a usable clone of `sha`: this format's marker plus an alternates
    file naming an object directory that still exists, so every git read against it resolves."""
    marker = _read_marker(dest)
    if marker is None or marker.get("sha") != sha or marker.get("format") != _FORMAT:
        return None
    target = _alternates_target(dest)
    return marker if target is not None and target.is_dir() else None


def _objects_dir(repo_root: Path) -> Path:
    """The object store of `repo_root` (plain, linked-worktree or bare), found without a git spawn."""
    git = repo_root / ".git"
    if git.is_file():
        text = git.read_text(encoding="utf-8").strip()
        if not text.startswith("gitdir:"):
            raise RuntimeError(f"{git} is not a gitdir pointer")
        gitdir = Path(text[len("gitdir:"):].strip())
        gitdir = gitdir if gitdir.is_absolute() else repo_root / gitdir
        try:
            common = Path((gitdir / "commondir").read_text(encoding="utf-8").strip())
            gitdir = common if common.is_absolute() else gitdir / common
        except OSError:
            pass
        git = gitdir
    elif not git.is_dir():
        git = repo_root
    objects = git / "objects"
    if not objects.is_dir():
        raise RuntimeError(f"no object store at {objects}")
    return objects.resolve()


def is_commit_clone(root: Path) -> bool:
    """True when `root` is a clone this module materialised (marker inside its `.git`)."""
    return _read_clone_marker(Path(root)) is not None


def source_repo_root(root: Path) -> Path:
    """The live repo a commit clone was built from; `root` itself when it is not a clone."""
    marker = _read_clone_marker(Path(root))
    if marker and marker.get("source_root"):
        return Path(marker["source_root"])
    return Path(root)


def _git(repo_root: Path, *args: str, stdin: bytes | None = None) -> bytes:
    proc = subprocess.run(
        ["git", "--no-optional-locks", "-C", str(repo_root), *args], input=stdin,
        capture_output=True, creationflags=_NO_WINDOW,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {args[0]} failed: {proc.stderr.decode(errors='replace').strip()}")
    return proc.stdout


def _is_test(path: str) -> bool:
    return "/tests/" in path or path.rsplit("/", 1)[-1].startswith("test_")


def _is_wanted(path: str, extra: frozenset[str]) -> bool:
    if path in extra or path in _SEED_FILES:
        return True
    if _is_test(path):
        return False
    return path in _SEED_FILES or path.startswith(_SEED_DIRS)


def _package_of(path: str, packages: frozenset[str]) -> str | None:
    """The nearest directory above `path` holding an `__init__.py`, or None outside any package."""
    d = path.rpartition("/")[0]
    while d:
        if d in packages:
            return d
        d = d.rpartition("/")[0]
    return None


def _package_data(paths: list[str], owners: set[str]) -> list[str]:
    """The non-Python, non-test files of `paths` whose package is in `owners`: what a module reads
    beside itself (`Path(__file__).parent / "schemas"`), which no import ever asks the filler for."""
    packages = frozenset(p[: -len("/__init__.py")] for p in paths if p.endswith("/__init__.py"))
    return [
        p for p in paths
        if not p.endswith(".py") and not _is_test(p) and _package_of(p, packages) in owners
    ]


def _read_extra(cache_root: Path) -> frozenset[str]:
    """Clone-relative files earlier rounds imported beyond the static seed: a child process of the
    round cannot fill them on demand, so the next clone carries them from the start."""
    try:
        data = json.loads((cache_root / _EXTRA_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return frozenset()
    return frozenset(p for p in data if isinstance(p, str)) if isinstance(data, list) else frozenset()


def _record_extra(clone: Path) -> None:
    """Merge every module the round loaded from `clone` outside the static seed into the cache's
    `seed-extra.json`. Best effort: a lost write only costs the next clone a lazy fill."""
    prefix = str(clone).replace("\\", "/").rstrip("/") + "/"
    seen = set(_read_extra(clone.parent))
    for module in list(sys.modules.values()):
        name = (getattr(module, "__file__", None) or "").replace("\\", "/")
        if name.startswith(prefix) and not _is_wanted(name[len(prefix):], frozenset()):
            seen.add(name[len(prefix):])
    try:
        (clone.parent / _EXTRA_FILE).write_text(json.dumps(sorted(seen)), encoding="utf-8")
    except OSError:
        pass


def _seed_entries(repo_root: Path, sha: str, extra: frozenset[str]) -> list[tuple[str, str]]:
    """(blob id, path) for every seed file at `sha`, from one `git ls-tree`."""
    blobs = _ls_blobs(repo_root, sha, _SPARSE_ROOTS)
    wanted = {p for p in blobs if _is_wanted(p, extra)}
    packages = frozenset(p[: -len("/__init__.py")] for p in blobs if p.endswith("/__init__.py"))
    owners = {_package_of(p, packages) for p in wanted if p.endswith(".py")} - {None}
    wanted.update(_package_data(list(blobs), owners))
    return [(blobs[p], p) for p in sorted(wanted)]


def _ls_blobs(repo_root: Path, sha: str, roots: tuple[str, ...]) -> dict[str, str]:
    """{path: blob id} for every blob under `roots` at `sha`, from one `git ls-tree`."""
    raw = _git(repo_root, "ls-tree", "-r", "-z", sha, "--", *roots)
    out = {}
    for record in raw.split(b"\0"):
        meta, _, name = record.partition(b"\t")
        fields = meta.split()
        if len(fields) == 3 and fields[1] == b"blob":
            out[name.decode("utf-8", "surrogateescape")] = fields[2].decode()
    return out


def _read_blobs(repo_root: Path, queries: list[str]) -> list[bytes | None]:
    """Blob bytes for each `<object>` query (None when missing), from one `git cat-file --batch`."""
    out = _git(repo_root, "cat-file", "--batch", stdin=("\n".join(queries) + "\n").encode())
    blobs: list[bytes | None] = []
    pos = 0
    for _ in queries:
        nl = out.index(b"\n", pos)
        header = out[pos:nl].split()
        pos = nl + 1
        if header[-1] == b"missing" or header[1] != b"blob":
            blobs.append(None)
            continue
        size = int(header[2])
        blobs.append(out[pos:pos + size])
        pos += size + 1
    return blobs


def _write_files(root: Path, files: list[tuple[str, bytes]]) -> None:
    made: set[Path] = set()
    for rel, data in files:
        target = root / rel
        if target.parent not in made:
            target.parent.mkdir(parents=True, exist_ok=True)
            made.add(target.parent)
        target.write_bytes(data)


def materialise_commit_clone(repo_root: Path, sha: str, cache_root: Path) -> Path:
    """`cache_root/<sha>`: the seed closure of `repo_root` at `sha`, written from the commit tree
    (two git processes cold, none warm). `.git/objects/info/alternates` points at the source object
    store, so `git -C <clone>` reads of the sha resolve. A warm hit needs this format's marker and a
    live alternates target; any other entry at `dest` (an objectless shell, a legacy clone) is
    rebuilt. Raises CommitCloneError, naming a runnable retry, when `sha` is not a full commit hash
    in `repo_root` or git refuses."""
    repo_root, cache_root = Path(repo_root), Path(cache_root)
    dest = cache_root / sha
    if _usable_marker(dest, sha) is not None:
        try:
            os.utime(dest)  # `_prune` orders by mtime: a clone in use must not read as oldest
        except OSError:
            pass
        return dest
    try:
        if not _FULL_SHA_RE.fullmatch(sha):
            raise RuntimeError(f"{sha!r} is not a full commit hash")
        objects = _objects_dir(repo_root)
        entries = _seed_entries(repo_root, sha, _read_extra(cache_root))
        if not entries:
            raise RuntimeError(f"no publisher code found at {sha[:12]} in {repo_root}")
        blobs = _read_blobs(repo_root, [blob for blob, _ in entries])
        if any(b is None for b in blobs):
            raise RuntimeError(f"a seed blob of {sha[:12]} is missing from {repo_root}")
        cache_root.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f"{sha[:12]}-", dir=cache_root))
        try:
            _write_files(staging, [(path, data) for (_, path), data in zip(entries, blobs)])
            # A repo shell with no index: HEAD names the sha, alternates borrow the source objects.
            for sub in ("objects/info", "refs"):
                (staging / ".git" / sub).mkdir(parents=True)
            # Bytes, not text: git reads these files verbatim and a CR from text mode breaks them.
            (staging / ".git" / "HEAD").write_bytes(f"{sha}\n".encode())
            (staging / ".git" / "objects" / "info" / "alternates").write_bytes(
                f"{objects.as_posix()}\n".encode()
            )
            (staging / ".git" / _MARKER).write_text(
                json.dumps({"sha": sha, "source_root": str(repo_root), "format": _FORMAT}), encoding="utf-8"
            )
            if dest.exists() and _usable_marker(dest, sha) is None:
                shutil.rmtree(dest, ignore_errors=True)  # a shell or legacy entry would block the replace
            try:
                os.replace(staging, dest)
            except OSError:
                if _usable_marker(dest, sha) is None:
                    raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    except (RuntimeError, OSError) as exc:
        raise CommitCloneError(
            f"commit clone of {sha[:12]} refused, nothing ran from the live tree: {exc}. "
            f"Retry: {_remediation(repo_root, sha)}"
        ) from exc
    _prune(cache_root, keep=dest)
    return dest


def fill_paths(clone: Path, rels: list[str]) -> list[str]:
    """Write each clone-relative `rels` entry absent from `clone` out of the clone's commit, in one
    git process. Returns the entries the commit does not hold."""
    clone = Path(clone)
    marker = _read_clone_marker(clone)
    if marker is None:
        raise CommitCloneError(f"{clone} is not a commit clone")
    todo = [r for r in rels if not (clone / r).exists()]
    if not todo:
        return []
    source = Path(marker["source_root"])
    try:
        blobs = _read_blobs(source, [f"{marker['sha']}:{r}" for r in todo])
    except (RuntimeError, OSError) as exc:
        raise CommitCloneError(
            f"commit clone fill of {todo[0]} failed: {exc}. Retry: {_remediation(source, marker['sha'])}"
        ) from exc
    _write_files(clone, [(r, b) for r, b in zip(todo, blobs) if b is not None])
    return [r for r, b in zip(todo, blobs) if b is None]


def fill_package_data(clone: Path, package: str) -> None:
    """Write the data files of clone-relative `package` (see `_package_data`) out of the clone's
    commit: two git processes, paid once per package the round fills lazily."""
    marker = _read_clone_marker(Path(clone))
    if marker is None:
        raise CommitCloneError(f"{clone} is not a commit clone")
    try:
        paths = list(_ls_blobs(Path(marker["source_root"]), marker["sha"], (package,)))
    except (RuntimeError, OSError) as exc:
        raise CommitCloneError(
            f"commit clone fill of {package} data failed: {exc}. "
            f"Retry: {_remediation(Path(marker['source_root']), marker['sha'])}"
        ) from exc
    data = _package_data(paths, {package})
    if data:
        fill_paths(Path(clone), data)


def fill_tree(clone: Path, roots: tuple[str, ...]) -> None:
    """Write every non-test file under clone-relative `roots` out of the clone's commit (two git
    processes). For a reader that walks source by path, not by import (the allowlist generator's
    closure parse and contract-root checks), which the import filler never serves."""
    marker = _read_clone_marker(Path(clone))
    if marker is None:
        raise CommitCloneError(f"{clone} is not a commit clone")
    try:
        paths = list(_ls_blobs(Path(marker["source_root"]), marker["sha"], roots))
    except (RuntimeError, OSError) as exc:
        raise CommitCloneError(
            f"commit clone fill of {', '.join(roots)} failed: {exc}. "
            f"Retry: {_remediation(Path(marker['source_root']), marker['sha'])}"
        ) from exc
    fill_paths(Path(clone), [p for p in paths if not _is_test(p)])


class _CommitFill(importlib.abc.MetaPathFinder):
    """Last on `sys.meta_path`: a repo-owned module the clone lacks is written from its commit, then
    found by the normal path finder. Foreign names (stdlib, third-party) never spawn.
    Trap: a repo-owned name the commit lacks (an optional import guarded by `except ImportError`)
    costs one `git cat-file` spawn per probe; a module the round really needs is recorded by
    `_record_extra`, so only the first round after a new import pays."""

    def __init__(self, clone: Path) -> None:
        self._clone = clone
        self._data_filled: set[str] = set()

    def find_spec(self, fullname, path=None, target=None):
        base_dirs = _FILL_ROOTS.get(fullname.split(".", 1)[0])
        if base_dirs is None:
            return None
        rel = fullname.replace(".", "/")
        candidates = [
            f"{base}/{rel}{tail}".lstrip("/") for base in base_dirs for tail in (".py", "/__init__.py")
        ]
        missing = fill_paths(self._clone, candidates)
        found = [c for c in candidates if c not in missing]
        if found:
            package = found[0][: -len("/__init__.py")] if found[0].endswith("/__init__.py") else found[0].rpartition("/")[0]
            if package not in self._data_filled and (self._clone / package / "__init__.py").exists():
                self._data_filled.add(package)
                fill_package_data(self._clone, package)
        importlib.invalidate_caches()
        return importlib.machinery.PathFinder.find_spec(fullname, path)


def _prune(cache_root: Path, keep: Path) -> None:
    """Remove sha-named clones beyond the newest `_RETENTION`; `keep`, staging dirs and any clone
    touched within `_IN_USE_GRACE_SECS` stay (a round runs from its clone long after it started)."""
    try:
        clones = [
            p for p in cache_root.iterdir()
            if p != keep and _FULL_SHA_RE.fullmatch(p.name) and p.is_dir()
        ]
        clones.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        now = time.time()
        stale_clones = [p for p in clones[max(_RETENTION - 1, 0):] if now - p.stat().st_mtime > _IN_USE_GRACE_SECS]
    except OSError:
        return
    for stale in stale_clones:
        shutil.rmtree(stale, ignore_errors=True)


def _write_site(clone: Path) -> Path:
    """`<clone>/.git/commit-clone-site`, holding the `sitecustomize` that gives a child process the
    filler, then imports the `sitecustomize` it shadows."""
    site = clone / ".git" / _SITE_DIRNAME
    site.mkdir(exist_ok=True)
    (site / "sitecustomize.py").write_text(_SITE_SOURCE.format(clone=str(clone), module=str(Path(__file__).resolve())), encoding="utf-8")
    return site


def run_entry_from_clone(clone: Path, entry_rel: str, argv: list[str]) -> int:
    """Run `clone/entry_rel` as `__main__` with the clone's roots first on `sys.path` and no
    live-tree path or cached `coordinator_core` module left to shadow it. Returns the exit code.
    Raises CommitCloneError when `clone` is not a commit clone or the commit lacks the entry."""
    clone = Path(clone)
    if not is_commit_clone(clone):
        raise CommitCloneError(f"{clone} is not a commit clone; refusing to run from it")
    if fill_paths(clone, [entry_rel]):
        raise CommitCloneError(f"{entry_rel} is not in the commit {_read_clone_marker(clone)['sha'][:12]}")
    entry = clone / entry_rel
    live = {Path(sys.argv[0]).resolve().parent} if sys.argv and sys.argv[0] else set()
    live.add(source_repo_root(clone) / "coordinator" / "bin")
    live.add(source_repo_root(clone))
    live.add(Path(__file__).resolve().parents[1])
    live.add(Path(__file__).resolve().parents[3])
    drop = {str(p) for p in live}
    clone_bin = clone / "coordinator" / "bin"
    sys.path[:] = [p for p in sys.path if p not in drop]
    sys.path[:0] = [str(clone_bin), str(clone)]
    for name in [m for m in sys.modules if m == "coordinator_core" or m.startswith("coordinator_core.")]:
        del sys.modules[name]
    filler = _CommitFill(clone)
    sys.meta_path.append(filler)
    saved_pythonpath = os.environ.get("PYTHONPATH")
    os.environ["PYTHONPATH"] = os.pathsep.join(
        [str(_write_site(clone))] + ([saved_pythonpath] if saved_pythonpath else [])
    )
    print(f"running from commit clone {clone}", file=sys.stderr)
    saved_argv = sys.argv
    sys.argv = [str(entry), *argv[1:]] if argv else [str(entry)]
    try:
        runpy.run_path(str(entry), run_name="__main__")
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    finally:
        sys.argv = saved_argv
        if saved_pythonpath is None:
            os.environ.pop("PYTHONPATH", None)
        else:
            os.environ["PYTHONPATH"] = saved_pythonpath
        _record_extra(clone)
        if filler in sys.meta_path:
            sys.meta_path.remove(filler)
    return 0


def main(argv: list[str]) -> int:
    """`materialise <sha> [--repo ROOT] [--cache DIR]`: build the clone, print its path."""
    if len(argv) < 2 or argv[0] != "materialise":
        print("usage: commit_clone.py materialise <sha> [--repo ROOT] [--cache DIR]", file=sys.stderr)
        return 2
    opts = dict(zip(argv[2::2], argv[3::2]))
    if len(argv[2:]) % 2 or not set(opts) <= {"--repo", "--cache"}:
        print("usage: commit_clone.py materialise <sha> [--repo ROOT] [--cache DIR]", file=sys.stderr)
        return 2
    repo = Path(opts.get("--repo") or Path(__file__).resolve().parents[3])
    cache = Path(opts["--cache"]) if "--cache" in opts else default_cache_root()
    try:
        print(materialise_commit_clone(repo, argv[1], cache))
    except CommitCloneError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
