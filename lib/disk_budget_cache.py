"""Cache pruner for the disk-budget enforcer: uv, huggingface and codex-runtimes under ~/.cache.

`prune_cache` is the body behind `disk_budget.prune_cache`. Only those three owned subtrees are
ever modified, plus unrecognised top-level `~/.cache` dirs (oldest first) while the total exceeds
`cache_total_cap`; owned-elsewhere dirs are never touched. uv runs through an injectable runner
(default: subprocess with no console window on Windows; timeout bounded by the deadline, None
when the deadline is infinite); a missing uv logs `uv-absent` and is skipped.
"""

from __future__ import annotations

import math
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

from disk_budget import FreeProbe, Policy, Roots, SweepReport, resolve_roots, under_volume_pressure  # noqa: E402
from win_portability import no_console_creationflags  # noqa: E402

__all__ = ["prune_cache"]

Runner = Callable[[Sequence[str], Optional[float]], int]


class _DeadlineExceeded(Exception):
    pass


def _check(deadline: float) -> None:
    if time.monotonic() > deadline:
        raise _DeadlineExceeded


def _walk(path: Path, deadline: float):
    """Yield (size, mtime) per non-directory entry under `path`; symlinks are not followed."""
    stack = [path]
    while stack:
        _check(deadline)
        try:
            it = os.scandir(stack.pop())
        except OSError:
            continue
        with it:
            for entry in it:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(Path(entry.path))
                    else:
                        st = entry.stat(follow_symlinks=False)
                        yield st.st_size, st.st_mtime
                except OSError:
                    continue


def _size(path: Path, deadline: float) -> int:
    return sum(s for s, _ in _walk(path, deadline)) if path.is_dir() else 0


def _newest(path: Path, deadline: float) -> float:
    """Newest mtime of `path` itself or anything below it."""
    try:
        newest = path.lstat().st_mtime
    except OSError:
        return 0.0
    for _, mtime in _walk(path, deadline):
        newest = max(newest, mtime)
    return newest


def _rmtree(path: Path) -> None:
    def _retry(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)

    if path.is_symlink() or path.is_file():
        try:
            path.unlink()
        except PermissionError:
            os.chmod(path, stat.S_IWRITE)
            path.unlink()
        return
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_retry)
    else:
        shutil.rmtree(path, onerror=_retry)


def _default_runner(argv: Sequence[str], timeout_s: Optional[float]) -> int:
    return subprocess.run(
        list(argv),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=None if timeout_s is None else max(timeout_s, 1.0),
        check=False,
        **no_console_creationflags(),
    ).returncode


def _prune_uv(policy: Policy, deadline: float, roots: Roots, runner: Runner, apply: bool,
              report: SweepReport) -> None:
    uv_dir = roots.uv_cache
    before = _size(uv_dir, deadline)
    if before <= policy.uv_cap:
        return
    if not apply:
        report.log.append(f"uv: {before} bytes over cap {policy.uv_cap} (dry-run, prune/clean skipped)")
        return
    # `--cache-dir` is a global uv option, so the subcommand stays argv[-1].
    for sub in ("prune", "clean"):
        argv = ["uv", "--cache-dir", str(uv_dir), "cache", sub]
        try:
            rc = runner(argv, None if math.isinf(deadline) else max(deadline - time.monotonic(), 1.0))
        except FileNotFoundError:
            report.log.append("uv-absent: uv not found on PATH, uv cache not pruned")
            report.still_over = True
            return
        except subprocess.TimeoutExpired:
            report.log.append(f"uv cache {sub}: timed out")
            break
        if rc != 0:
            report.log.append(f"uv cache {sub}: exit {rc}")
        if _size(uv_dir, deadline) <= policy.uv_cap:
            break
    after = _size(uv_dir, deadline)
    report.record("uv", max(before - after, 0))
    report.log.append(f"uv: {before} -> {after} bytes")
    if after > policy.uv_cap:
        report.still_over = True


def _model_dir_name(model: str) -> str:
    return "models--" + model.replace("/", "--") if model else ""


def _snapshots(model_dir: Path) -> list:
    snaps = model_dir / "snapshots"
    try:
        return [Path(e.path) for e in os.scandir(snaps) if e.is_dir(follow_symlinks=False)]
    except OSError:
        return []


def _drop_orphan_blobs(model_dir: Path) -> None:
    """Delete blobs no remaining snapshot symlink points at (a snapshot holds only links)."""
    blobs = model_dir / "blobs"
    if not blobs.is_dir():
        return
    live = set()
    for snap in _snapshots(model_dir):
        for root, _dirs, files in os.walk(snap):
            for name in files:
                p = Path(root) / name
                if p.is_symlink():
                    live.add(os.path.realpath(p))
    with os.scandir(blobs) as it:
        orphans = [e.path for e in it if os.path.realpath(e.path) not in live]
    for path in orphans:
        _rmtree(Path(path))


def _prune_hf(policy: Policy, deadline: float, roots: Roots, apply: bool, embedder_model: str,
              report: SweepReport) -> None:
    hf = roots.huggingface
    before = _size(hf, deadline)
    if before <= policy.hf_cap:
        return
    if not apply:
        report.log.append(f"huggingface: {before} bytes over cap {policy.hf_cap} (dry-run)")
        return
    protected = _model_dir_name(embedder_model)
    try:
        models = [Path(e.path) for e in os.scandir(hf) if e.is_dir(follow_symlinks=False)
                  and e.name.startswith("models--")]
    except OSError:
        return
    current = before

    # Pass 1: every model's non-newest snapshots, oldest first.
    stale = []
    for model in models:
        snaps = sorted(((_newest(s, deadline), s) for s in _snapshots(model)), key=lambda t: (t[0], t[1].name))
        stale.extend((mtime, snap, model) for mtime, snap in snaps[:-1])
    for _mtime, snap, model in sorted(stale, key=lambda t: (t[0], str(t[1]))):
        if current <= policy.hf_cap:
            break
        _check(deadline)
        _rmtree(snap)
        _drop_orphan_blobs(model)
        current = _size(hf, deadline)

    # Pass 2: least-recently-used whole models, never the embedder's.
    if current > policy.hf_cap:
        lru = sorted(
            ((_newest(m, deadline), m) for m in models if m.exists() and m.name != protected),
            key=lambda t: (t[0], t[1].name),
        )
        for _mtime, model in lru:
            if current <= policy.hf_cap:
                break
            _check(deadline)
            _rmtree(model)
            current = _size(hf, deadline)

    report.record("huggingface", max(before - current, 0))
    report.log.append(f"huggingface: {before} -> {current} bytes")
    if current > policy.hf_cap:
        report.still_over = True


def _prune_codex(policy: Policy, deadline: float, roots: Roots, apply: bool, report: SweepReport) -> None:
    base = roots.codex_runtimes
    try:
        versions = [Path(e.path) for e in os.scandir(base) if e.is_dir(follow_symlinks=False)]
    except OSError:
        return
    ranked = sorted(((_newest(v, deadline), v) for v in versions), key=lambda t: (t[0], t[1].name))
    doomed = ranked[: max(len(ranked) - policy.codex_keep, 0)]
    freed = 0
    for _mtime, version in doomed:
        _check(deadline)
        size = _size(version, deadline)
        if not apply:
            report.log.append(f"codex-runtimes: would delete {version.name} ({size} bytes)")
            continue
        _rmtree(version)
        freed += size
    if freed:
        report.record("codex-runtimes", freed)
        report.log.append(f"codex-runtimes: freed {freed} bytes, kept newest {policy.codex_keep}")


_OWNED_ELSEWHERE_NAMES = frozenset({"experiments-1d"})
_OWNED_ELSEWHERE_PREFIXES = ("claude-klabauter", "retest")


def _owned_elsewhere(name: str) -> bool:
    low = name.lower()
    return low in _OWNED_ELSEWHERE_NAMES or low.startswith(_OWNED_ELSEWHERE_PREFIXES)


def _prune_cache_total(policy: Policy, deadline: float, roots: Roots, apply: bool,
                       report: SweepReport) -> None:
    """Bring `~/.cache` under `cache_total_cap` by deleting unrecognised top-level dirs, oldest first.

    The three per-tool subtrees (uv, huggingface, codex-runtimes) and owned-elsewhere dirs are
    never candidates; whatever stays over the cap afterwards sets `still_over`.
    """
    total = _size(roots.cache, deadline)
    if total <= policy.cache_total_cap:
        return
    recognised = set()
    for p in (roots.uv_cache, roots.huggingface, roots.codex_runtimes):
        try:
            recognised.add(p.resolve())
        except OSError:
            recognised.add(p)
    try:
        entries = [Path(e.path) for e in os.scandir(roots.cache) if e.is_dir(follow_symlinks=False)]
    except OSError:
        entries = []
    candidates = []
    for d in entries:
        if _owned_elsewhere(d.name) or d.resolve() in recognised:
            continue
        # A recognised subtree nested below this dir (e.g. a custom UV_CACHE_DIR) keeps it alive.
        if any(r == d.resolve() or d.resolve() in r.parents for r in recognised):
            continue
        candidates.append((_newest(d, deadline), d))
    candidates.sort(key=lambda t: (t[0], t[1].name))
    if not apply:
        report.log.append(f"cache total {total} bytes over cap {policy.cache_total_cap} (dry-run)")
        report.still_over = True
        return
    current = total
    freed = 0
    for _mtime, d in candidates:
        if current <= policy.cache_total_cap:
            break
        _check(deadline)
        size = _size(d, deadline)
        _rmtree(d)
        freed += size
        current -= size
    if freed:
        report.record("cache-other", freed)
        report.log.append(f"cache total: freed {freed} bytes from unrecognised dirs")
    if current > policy.cache_total_cap:
        report.still_over = True
        report.log.append(f"cache total {current} bytes over cap {policy.cache_total_cap}")


def prune_cache(
    policy: Policy,
    deadline: float,
    *,
    roots: Optional[Roots] = None,
    runner: Optional[Runner] = None,
    apply: bool = True,
    embedder_model: str = "",
    free_probe: Optional[FreeProbe] = None,
) -> SweepReport:
    """Prune uv (prune, then clean if still over), huggingface and codex-runtimes.

    `deadline` is an absolute `time.monotonic()` value; a sweep that hits it logs and returns
    what it freed so far. `still_over` is set when uv or huggingface remain over their caps or
    the whole `~/.cache` exceeds `cache_total_cap`, AND a volume holding those roots has fewer
    free bytes than `policy.volume_free_floor` (`free_probe(path) -> bytes`).
    """
    roots = roots or resolve_roots()
    runner = runner or _default_runner
    report = SweepReport()
    try:
        _prune_uv(policy, deadline, roots, runner, apply, report)
        _prune_hf(policy, deadline, roots, apply, embedder_model, report)
        _prune_codex(policy, deadline, roots, apply, report)
        _prune_cache_total(policy, deadline, roots, apply, report)
    except _DeadlineExceeded:
        report.log.append("deadline reached; sweep resumes next boot")
    if report.still_over and not under_volume_pressure(
        policy, [roots.cache, roots.uv_cache, roots.huggingface], free_probe
    ):
        report.still_over = False
    return report
