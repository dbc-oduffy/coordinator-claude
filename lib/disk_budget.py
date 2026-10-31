"""Disk-budget policy, roots and result types for the size-capped enforcer.

`~/.claude/projects` and `~/.cache` are bounded by size AND age at SessionStart. This module owns
the shared interface: `Policy` (caps, env overrides), `Roots`, `Unit`, `SweepReport`,
`resolve_roots()`, and the `prune_projects` / `prune_cache` entry points. The pruners live in
`disk_budget_projects.py` and `disk_budget_cache.py`; the entry points here delegate to them.

Pruners never delete: any `<project>/<session>.jsonl` main transcript of a live session, anything
under a `memory/` dir, any path containing `pm_turns`, or a workflow run that is non-terminal.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import math
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator, Mapping, Optional, Sequence

__all__ = [
    "ENV_PREFIX",
    "CHILD_MAX_WALL_S",
    "GiB",
    "LOCK_NAME",
    "MAX_SWEEP_S",
    "Policy",
    "Roots",
    "SweepReport",
    "TERMINAL_RUN_STATUSES",
    "Unit",
    "prune_cache",
    "prune_projects",
    "resolve_roots",
    "spawn_detached",
    "sweep_due",
    "sweep_lock",
]

GiB = 1024**3

LOCK_NAME = "sweep.lock"

# Seconds an unreadable lock file may exist before it counts as stale (the holder writes it right after creating it).
LOCK_WRITE_GRACE_S = 10.0

# Longest expected sweep; a lock older than twice this is stale even if its pid is alive.
MAX_SWEEP_S = 3600.0

# Hard wall-clock cap, in seconds, on a detached sweep child; the child stops itself at the cap.
CHILD_MAX_WALL_S = 1800

STAMP_NAME = "last-sweep.json"

ENV_PREFIX = "COORDINATOR_DISK_BUDGET_"

# A workflow run file whose top-level `status` is in this set is resolved and deleted on
# resolution. Missing, unreadable or unrecognised status is non-terminal (fail closed). The
# harness run-file schema is not a documented contract; this is the one place to update.
TERMINAL_RUN_STATUSES = frozenset({"completed", "failed", "cancelled"})


@dataclass(frozen=True)
class Policy:
    """Caps and ages. Each field's docstring-comment names the question it answers.

    Every field is overridable by env `COORDINATOR_DISK_BUDGET_<FIELD upper-case>`.
    """

    # How many bytes may ~/.claude/projects hold in total after a sweep?
    projects_cap: int = 4 * GiB
    # How many bytes may one session's prunable units hold before its oldest go?
    per_session_cap: int = 1 * GiB
    # How old must a unit's newest file be before size pressure may delete it?
    min_age_hours: float = 24
    # How long is a subagent transcript kept, even under the size cap?
    subagent_max_age_hours: float = 24
    # How many days is a non-live main transcript kept, even under the size cap?
    transcript_max_age_days: float = 7
    # How many bytes may ~/.cache hold in total after a sweep (oldest unrecognised dirs go first)?
    cache_total_cap: int = 8 * GiB
    # How many bytes may the uv cache hold before prune, then clean, runs?
    uv_cap: int = 3 * GiB
    # How many bytes may the huggingface cache hold before old snapshots/models go?
    hf_cap: int = 6 * GiB
    # How many codex-runtimes versions survive (newest first)?
    codex_keep: int = 2
    # How many hours must pass between two automatic sweeps?
    throttle_hours: float = 6
    # How many wall-clock seconds may one sweep spend before resuming next boot? None = unbounded.
    deadline_s: Optional[float] = 25
    # How many bytes must stay free on a volume after a bulk write or copy lands?
    volume_free_floor: int = 10 * GiB

    @classmethod
    def from_env(cls, environ: Optional[Mapping[str, str]] = None) -> "Policy":
        """Defaults overlaid by `COORDINATOR_DISK_BUDGET_<FIELD>`; a malformed value is ignored."""
        env = os.environ if environ is None else environ
        values = {}
        for f in dataclasses.fields(cls):
            raw = env.get(ENV_PREFIX + f.name.upper())
            if raw is None or not raw.strip():
                continue
            try:
                number = float(raw)
            except ValueError:
                continue
            if number < 0:
                continue
            values[f.name] = int(number) if f.type in (int, "int") else number
        return cls(**values)

    def deadline_at(self, start: Optional[float] = None) -> float:
        """Absolute `time.monotonic()` deadline for a sweep starting at `start`; `math.inf` when unbounded."""
        if self.deadline_s is None:
            return math.inf
        return (time.monotonic() if start is None else start) + self.deadline_s


@dataclass(frozen=True)
class Roots:
    """Resolved filesystem roots a sweep operates on."""

    projects: Path
    cache: Path
    uv_cache: Path
    huggingface: Path
    codex_runtimes: Path
    state_dir: Path
    repos: tuple = ()


@dataclass(frozen=True)
class Unit:
    """One atomic prunable thing: deleted together or not at all.

    kind is one of: subagent, workflow, workflow_script, tool_result, main_transcript.
    """

    kind: str
    paths: tuple
    size: int
    newest_mtime: float
    session: str = ""
    eligible: bool = True
    reason: str = ""


@dataclass
class SweepReport:
    """What one prune pass did; `per_root` maps a root label to bytes freed."""

    freed_bytes: int = 0
    per_root: dict = field(default_factory=dict)
    still_over: bool = False
    deleted: list = field(default_factory=list)
    log: list = field(default_factory=list)

    def record(self, root: str, freed: int) -> None:
        self.per_root[root] = self.per_root.get(root, 0) + freed
        self.freed_bytes += freed


Runner = Callable[[Sequence[str], Optional[float]], int]
FreeProbe = Callable[[Path], int]


def volume_free_bytes(path: Path) -> int:
    """Free bytes on the volume holding `path` (its nearest existing ancestor); `-1` when unreadable."""
    probe = Path(path)
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    try:
        return shutil.disk_usage(probe).free
    except OSError:
        return -1


def under_volume_pressure(policy: Policy, paths: Sequence[Path], free_probe: Optional[FreeProbe] = None) -> bool:
    """True when any volume holding `paths` has fewer free bytes than `policy.volume_free_floor`.

    An unreadable probe (-1) counts as no pressure: size-cap overage alone never reports pressure.
    """
    probe = free_probe or volume_free_bytes
    for path in paths:
        free = probe(Path(path))
        if 0 <= free < policy.volume_free_floor:
            return True
    return False


def spawn_detached(argv: Sequence[str]) -> int:
    """Start `argv` as a detached child that outlives the caller, with no console; returns its pid."""
    kwargs: dict = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = (
            getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        )
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(list(argv), **kwargs).pid


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _lock_is_stale(path: Path, wall: float) -> bool:
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
        pid, started = int(info["pid"]), float(info["started"])
    except (OSError, ValueError, KeyError, TypeError):
        # A holder creates the file (O_EXCL) before writing its body; a fresh unreadable lock is
        # mid-write, not stale.
        try:
            return time.time() - path.stat().st_mtime > LOCK_WRITE_GRACE_S
        except OSError:
            return True
    return wall - started > 2 * MAX_SWEEP_S or not _pid_alive(pid)


@contextlib.contextmanager
def sweep_lock(state_dir: Path, now: Optional[float] = None) -> Iterator[bool]:
    """Hold `<state_dir>/sweep.lock` for the block; yields False when another live sweep holds it.

    Created with O_CREAT|O_EXCL holding `{pid, started}`. A lock whose pid is gone, or older than
    2 x `MAX_SWEEP_S`, is stale and taken over. The lock is released only by its holder.
    Takeover of a stale lock is not atomic: two simultaneous takers can both proceed, which pruning
    tolerates because every deletion is idempotent.
    """
    path = Path(state_dir) / LOCK_NAME
    wall = time.time() if now is None else now
    path.parent.mkdir(parents=True, exist_ok=True)
    acquired = False
    for _ in range(2):
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if _lock_is_stale(path, wall):
                path.unlink(missing_ok=True)
                continue
            break
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"pid": os.getpid(), "started": wall}))
        acquired = True
        break
    try:
        yield acquired
    finally:
        if acquired:
            path.unlink(missing_ok=True)


def sweep_due(state_dir: Path, policy: Policy, wall: float) -> bool:
    """True when `<state_dir>/last-sweep.json` is missing, unreadable, or older than the throttle.

    One read, no lock; an unreadable or ts-less stamp counts as missing.
    """
    try:
        ts = json.loads((Path(state_dir) / STAMP_NAME).read_text(encoding="utf-8")).get("ts")
    except (OSError, ValueError, AttributeError):
        return True
    if isinstance(ts, bool) or not isinstance(ts, (int, float)):
        return True
    return wall - ts >= policy.throttle_hours * 3600


def resolve_roots(
    home: Optional[Path] = None,
    environ: Optional[Mapping[str, str]] = None,
    repos: Sequence[Path] = (),
) -> Roots:
    """Roots under `home` (default the user's home), honouring UV_CACHE_DIR, HF_HOME, XDG_CACHE_HOME."""
    env = os.environ if environ is None else environ
    base = Path(home) if home is not None else Path(os.path.expanduser("~"))
    cache = Path(env["XDG_CACHE_HOME"]) if env.get("XDG_CACHE_HOME") else base / ".cache"
    uv = Path(env["UV_CACHE_DIR"]) if env.get("UV_CACHE_DIR") else cache / "uv"
    hf = Path(env["HF_HOME"]) / "hub" if env.get("HF_HOME") else cache / "huggingface" / "hub"
    return Roots(
        projects=base / ".claude" / "projects",
        cache=cache,
        uv_cache=uv,
        huggingface=hf,
        codex_runtimes=cache / "codex-runtimes",
        state_dir=base / ".claude" / "disk-budget",
        repos=tuple(Path(r) for r in repos),
    )


def prune_projects(
    policy: Policy,
    deadline: float,
    *,
    roots: Optional[Roots] = None,
    now: Optional[float] = None,
    live_sessions: Sequence[str] = (),
    apply: bool = True,
    free_probe: Optional[FreeProbe] = None,
) -> SweepReport:
    """Prune ~/.claude/projects under `policy`; `deadline` is an absolute time.monotonic() value."""
    from disk_budget_projects import prune_projects as _impl  # lazy: that module imports this one

    return _impl(
        policy, deadline, roots=roots, now=now, live_sessions=live_sessions, apply=apply, free_probe=free_probe
    )


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
    """Prune uv, huggingface and codex-runtimes; `runner(argv, timeout_s) -> returncode` replaces subprocess."""
    from disk_budget_cache import prune_cache as _impl  # lazy: that module imports this one

    return _impl(
        policy, deadline, roots=roots, runner=runner, apply=apply, embedder_model=embedder_model,
        free_probe=free_probe,
    )
