"""coordinator/bin/publish-repo-bundle-at-ceremony.py -- detached sequencer chained
after `scip-rebuild --ceremony NAME`: waits on the rebuild, then publishes the
freshly-rebuilt structural index via project-rag's `publish-repo-bundle` verb.

Spawned (never invoked directly by a ceremony) as the detached argv of
`scip-rebuild-at-ceremony.py::run`, so its own contract is the mirror of that
script's: best-effort, ALWAYS exits 0, every reachable error path is one
`publish-repo-bundle: skipped -- <reason>`, `publish-repo-bundle: refused --
<fix>`, or (for a broken registry, as in that script) `publish-repo-bundle: defect --
<reason>` line, never an exception surfaced to the caller.

Contract references, read-only in project-rag at 3c6d730fe (work/machine-a/2026-09-25,
unreleased): `project_rag_cli.py` (`cmd_publish_repo_bundle` / `cmd_scip_rebuild` exit
codes) and `project_rag_core/repo_bundle/publish.py` (exit-4 refusal text used for the
fix map below). Both verbs are stub-tested here; an unmatched refusal string is echoed
verbatim rather than raising, so drift in project-rag's wording degrades this script's
output rather than breaking it.

docs/plans/2026-09-26-wire-repo-index-bundle-verbs.md -- Design SS Ceremony, row C2.

Negative-spec:
  - Does NOT leave a rebuild or publish child running past this process: the 3600s wait
    expiring kills the child tree, a Windows kill-on-close job covers this process dying,
    and a lease (`coordinator-sessions/scip-rebuild-lease.json`) lets the next sequencer
    reap a dead one's rebuild and dedupes a concurrent one. Neither case publishes.
  - Does NOT publish unless the rebuild it just ran exited 0 -- exit 1, 2, or 3
    (rebuild lock held elsewhere) all skip the publish call.
  - Does NOT blind-retry a publish exit 4 at the same HEAD -- checks the last written
    record before running the publish verb again.
  - Does NOT infer `--repo` from a git remote or re-derive project-rag's slug
    resolution -- `--repo` is passed through only when the operator supplied it.
  - No bash, no `shell=True`, no string-built argv.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_THIS = Path(__file__).resolve()
_REPO_ROOT = _THIS.parent.parent.parent
# bin/ and lib/ are siblings in both the claude-klabauter tree (coordinator/) and the OSS mirror (root).
_LIB_DIR = _THIS.parent.parent / "lib"


def no_console_creationflags() -> dict:
    """`win_portability.no_console_creationflags`, imported on first call so a bare
    import of this module leaves `sys.path` untouched."""
    if str(_LIB_DIR) not in sys.path:
        sys.path.insert(0, str(_LIB_DIR))
    from win_portability import no_console_creationflags as _impl

    return _impl()


def _console_python() -> str:
    """A real console CPython for a child argv. `sys.executable` alone is the running image,
    which under an installed forwarder exe is not an interpreter (bin/lib/python_interp.py)."""
    bin_lib = str(_THIS.parent / "lib")
    if bin_lib not in sys.path:
        sys.path.insert(0, bin_lib)
    from python_interp import resolve_console_python

    return resolve_console_python() or sys.executable


_CEREMONY_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_REBUILD_WAIT_SECONDS = 3600
_RECORD_NAME = "publish-repo-bundle-last.json"
_REBUILD_ADMIT_KEY = "scip-rebuild"
_REBUILD_PEAK_GIB = 4.0
_ADMISSION_PREFIX = "admission: "

_FIX_MAP: tuple[tuple[str, str], ...] = (
    ("older than head", "reindex --incremental"),
    ("not reachable from any remote-tracking ref", "push HEAD"),
    ("dirty", "commit or stash"),
    ("uncommitted", "commit or stash"),
    ("no target github repo resolved", "register repos.<slug>.publish_repo"),
)


def _settings_home() -> Path:
    """Same two-rung precedence every settings-home reader in this repo uses:
    COORDINATOR_SETTINGS_HOME, else ${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings.
    Pure path arithmetic -- never reads a file to resolve this.
    """
    override = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if override:
        return Path(override)
    home = os.environ.get("CLAUDE_HOME") or str(Path.home())
    return Path(home) / ".coordinator-claude-settings"


def _resolve_registry_key(key: str) -> tuple[str | None, str | None]:
    """Resolve `key` via `<settings-home>/bin/_machine_local.py get <key>`.

    Returns (value, None) on success, (None, reason) on any failure -- a missing
    reader, a missing/unset key, or a non-zero exit are all reported the same way:
    a reason string this script's caller turns into a `skipped -- <reason>` line.
    Never raises; never shells through the bare `machine-local` wrapper.
    """
    reader = _settings_home() / "bin" / "_machine_local.py"
    if not reader.is_file():
        return None, f"machine-local reader not found at {reader}"
    try:
        result = subprocess.run(
            [_console_python(), str(reader), "get", key],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
            **no_console_creationflags(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"machine-local reader invocation failed: {exc}"
    value = result.stdout.strip()
    if result.returncode != 0 or not value:
        stderr = result.stderr.strip()
        return None, f"registry key {key!r} unresolved ({stderr or 'no value'})"
    return value, None


def _unresolved_cli_line(prefix: str, reason: str | None) -> str:
    """The line for an unresolved CLI key. A box with `repos.project_rag`
    registered has project-rag installed, so the key not resolving there is a
    broken registry or a scrubbed publish -- a defect. Only a box without
    project-rag skips."""
    _, absent = _resolve_registry_key("repos.project_rag")
    if absent is None:
        return f"{prefix}: defect -- {reason}, but repos.project_rag is registered"
    return f"{prefix}: skipped -- {reason}"


def _git_common_dir(repo_root: Path) -> Path | None:
    """Walk `.git` (dir or worktree pointer-file) to the common dir -- same shape
    `scip-rebuild-at-ceremony.py::_git_common_dir` uses, so records from both
    scripts land beside each other under `coordinator-sessions/`."""
    marker = repo_root / ".git"
    if marker.is_dir():
        git_dir = marker
    elif marker.is_file():
        raw = marker.read_text(encoding="utf-8", errors="replace")
        if not raw.startswith("gitdir:"):
            return None
        pointer = Path(raw[len("gitdir:"):].strip())
        git_dir = pointer if pointer.is_absolute() else (repo_root / pointer).resolve()
    else:
        return None

    commondir_file = git_dir / "commondir"
    if commondir_file.is_file():
        raw_common = commondir_file.read_text(encoding="utf-8", errors="replace").strip()
        if not raw_common:
            return git_dir
        common_path = Path(raw_common)
        return common_path if common_path.is_absolute() else (git_dir / common_path).resolve()
    return git_dir


def _current_head(repo_root: Path) -> str | None:
    """`git rev-parse HEAD`, bounded and console-hidden. None on any failure --
    a repo with no commits yet, or no git at all, never raises here."""
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from coordinator_core.git.run import run_git

    result = run_git(["rev-parse", "HEAD"], cwd=str(repo_root))
    if result.returncode != 0:
        return None
    head = result.stdout.strip()
    return head or None


def _read_last_record(record_path: Path) -> dict | None:
    """Best-effort read of the last publish record. Any read/parse failure
    (missing file, truncated write, bad JSON) reads as "no record" -- never raises."""
    try:
        raw = record_path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _write_record(record_path: Path, exit_code: int, head: str | None, line: str) -> None:
    """Atomic tmp-file + os.replace write -- never leaves a torn record behind
    for the next attempt (or scip-rebuild-at-ceremony.py's own reader) to see."""
    record_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "exit_code": exit_code,
        "head": head,
        "line": line,
        "finished_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    fd, tmp_name = tempfile.mkstemp(
        dir=str(record_path.parent), prefix=record_path.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        os.replace(tmp_name, str(record_path))
    finally:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass


_LEASE_NAME = "scip-rebuild-lease.json"
_DEDUPE_PREFIX = "dedupe: "
#: Keeps the Windows job handle alive for the sequencer's lifetime; closing it kills the job.
_JOB_HANDLES: list = []


def _pid_alive(pid) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        import psutil

        return psutil.pid_exists(pid)
    except ImportError:
        if os.name == "nt":  # os.kill(pid, 0) terminates the process on Windows
            return False
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True


def _proc_started(pid: int) -> float | None:
    try:
        import psutil

        return psutil.Process(pid).create_time()
    except Exception:  # noqa: BLE001 -- gone, denied, or no psutil: unknown
        return None


def _kill_tree(pid: int) -> None:
    """Kill `pid` and every descendant; never raises."""
    try:
        import psutil

        try:
            root = psutil.Process(pid)
            victims = root.children(recursive=True) + [root]
        except psutil.Error:
            return
        for victim in victims:
            try:
                victim.kill()
            except psutil.Error:
                pass
    except ImportError:
        try:
            os.kill(pid, 9)
        except OSError:
            pass


def _bind_child_to_caller(proc) -> None:
    """Windows: put the child in a kill-on-close job so it dies with this sequencer. Elsewhere
    the lease sweep is the backstop. Best-effort, never raises."""
    if os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return

        class _Basic(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class _IoCounters(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint64) for n in (
                "ReadOps", "WriteOps", "OtherOps", "ReadBytes", "WriteBytes", "OtherBytes")]

        class _Extended(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", _Basic), ("IoInfo", _IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        info = _Extended()
        info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        if not kernel32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
            kernel32.CloseHandle(job)
            return
        if not kernel32.AssignProcessToJobObject(job, int(proc._handle)):  # noqa: SLF001
            kernel32.CloseHandle(job)
            return
        _JOB_HANDLES.append(job)
    except Exception:  # noqa: BLE001
        pass


def _read_lease(path: Path) -> dict | None:
    return _read_last_record(path)


def _claim_lease(path: Path) -> str | None:
    """Take the single-rebuild lease. None on success; else a one-line dedupe reason.

    A lease whose sequencer is dead is swept: its orphaned rebuild tree is killed, the file
    removed, and the claim retried once. O_EXCL makes two racing sequencers pick one winner."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps({"sequencer_pid": os.getpid(), "child_pid": None, "child_started": None})
    for _attempt in range(2):
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            held = _read_lease(path) or {}
            owner = held.get("sequencer_pid")
            if _pid_alive(owner) and owner != os.getpid():
                return f"a rebuild is already running (sequencer pid {owner})"
            _sweep_lease(path, held)
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(body)
        return None
    return "lease contended"


def _sweep_lease(path: Path, held: dict) -> None:
    """Reap the rebuild of a dead sequencer (pid-reuse guarded by create_time) and drop the lease."""
    child = held.get("child_pid")
    started = held.get("child_started")
    if _pid_alive(child):
        actual = _proc_started(child)
        if started is None or actual is None or abs(actual - started) < 2.0:
            _kill_tree(child)
    try:
        path.unlink()
    except OSError:
        pass


def _record_lease_child(path: Path, pid: int) -> None:
    payload = {"sequencer_pid": os.getpid(), "child_pid": pid, "child_started": _proc_started(pid)}
    try:
        path.write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        pass


def _release_lease(path: Path) -> None:
    held = _read_lease(path)
    if held is not None and held.get("sequencer_pid") != os.getpid():
        return
    try:
        path.unlink()
    except OSError:
        pass


def _run_and_wait(
    argv: list[str], cwd: Path, timeout: int
) -> tuple[int | None, str, str]:
    """Runs argv, waiting up to `timeout` seconds. Returns (returncode, stdout,
    stderr); returncode is None on timeout expiry, after the child's tree is killed so
    nothing outlives this sequencer.
    A `scip-rebuild` argv takes the single-rebuild lease first (a live holder returns
    (None, "", "dedupe: ...") without spawning), is admitted on measured memory (a hold
    returns (None, "", "admission: HOLD ...")), and is bound to this process: a kill-on-close
    job on Windows, the lease sweep by the next sequencer elsewhere."""
    rebuild = len(argv) > 1 and argv[1] == "scip-rebuild"
    admission = None
    lease = None
    if rebuild:
        common = _git_common_dir(cwd) or cwd
        lease = common / "coordinator-sessions" / _LEASE_NAME
        duplicate = _claim_lease(lease)
        if duplicate:
            return None, "", f"{_DEDUPE_PREFIX}{duplicate}"
        if str(_REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(_REPO_ROOT))
        from coordinator_core.bash_guards._heavy_command_class import admit_before_spawn

        admission = admit_before_spawn(_REBUILD_ADMIT_KEY, _REBUILD_PEAK_GIB)
        if not admission.admitted:
            _release_lease(lease)
            return None, "", f"{_ADMISSION_PREFIX}{admission.reason}"
    proc = None
    try:
        try:
            proc = subprocess.Popen(
                argv,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                **no_console_creationflags(),
            )
        except OSError as exc:
            return None, "", f"failed to spawn {argv!r}: {exc}"
        if rebuild:
            _bind_child_to_caller(proc)
            _record_lease_child(lease, proc.pid)
        if admission is not None:
            from coordinator_core.bash_guards._heavy_command_class import register_spawn

            register_spawn(admission.key, admission.peak_gib, proc.pid)
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            return None, "", ""
        return proc.returncode, stdout or "", stderr or ""
    finally:
        poll = getattr(proc, "poll", None)
        if poll is not None and getattr(proc, "pid", None) and poll() is None:
            _kill_tree(proc.pid)
        if lease is not None:
            _release_lease(lease)


def _first_stderr_line(stderr: str) -> str:
    for line in stderr.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _map_exit4_fix(stderr: str) -> str:
    """Substring-match project-rag's exit-4 refusal text to a named next step.
    Case-insensitive; the first match in `_FIX_MAP` order wins. No match ->
    the refusal text itself carries the fix (echoed verbatim by the caller)."""
    lowered = stderr.lower()
    for needle, fix in _FIX_MAP:
        if needle in lowered:
            return fix
    return ""


def run(
    ceremony: str,
    repo_root: Path,
    cli_override: str | None = None,
    repo_slug: str | None = None,
) -> str:
    """Resolve, run scip-rebuild, then (conditionally) publish-repo-bundle.
    Returns the one line to print -- never raises; every failure path is a
    `publish-repo-bundle: skipped -- <reason>` or `... refused -- <fix>` string."""
    if not _CEREMONY_NAME_RE.match(ceremony):
        return (
            f"publish-repo-bundle: skipped -- invalid --ceremony name {ceremony!r} "
            "(must match [a-z0-9][a-z0-9_-]*)"
        )

    if cli_override:
        exe_path = Path(cli_override).expanduser()
        if not exe_path.is_file():
            return f"publish-repo-bundle: skipped -- --cli names a file that does not exist: {exe_path}"
    else:
        exe, reason = _resolve_registry_key("project_rag.bin.project_rag_cli")
        if exe is None:
            return _unresolved_cli_line("publish-repo-bundle", reason)
        exe_path = Path(exe).expanduser()
        if not exe_path.is_file():
            return f"publish-repo-bundle: defect -- registry key names a file that does not exist: {exe_path}"

    common_dir = _git_common_dir(repo_root) or repo_root
    record_path = common_dir / "coordinator-sessions" / _RECORD_NAME

    rebuild_argv = [str(exe_path), "scip-rebuild", "--ceremony", ceremony]
    rebuild_code, _rebuild_out, rebuild_err = _run_and_wait(
        rebuild_argv, repo_root, _REBUILD_WAIT_SECONDS
    )
    if rebuild_code is None and rebuild_err.startswith(_DEDUPE_PREFIX):
        return f"publish-repo-bundle: skipped -- scip-rebuild deduped ({rebuild_err[len(_DEDUPE_PREFIX):]}), no publish"
    if rebuild_code is None and rebuild_err.startswith(_ADMISSION_PREFIX):
        return f"publish-repo-bundle: skipped -- scip-rebuild not admitted ({rebuild_err[len(_ADMISSION_PREFIX):]}), no publish"
    if rebuild_code is None:
        return "publish-repo-bundle: skipped -- scip-rebuild timed out, no publish"
    if rebuild_code == 3:
        return "publish-repo-bundle: skipped -- scip-rebuild exited 3 (rebuild lock held elsewhere), no publish"
    if rebuild_code != 0:
        detail = _first_stderr_line(rebuild_err)
        suffix = f", {detail}" if detail else ""
        return f"publish-repo-bundle: skipped -- scip-rebuild exited {rebuild_code}{suffix}, no publish"

    current_head = _current_head(repo_root)
    last_record = _read_last_record(record_path)
    if (
        last_record is not None
        and last_record.get("exit_code") == 4
        and current_head is not None
        and last_record.get("head") == current_head
    ):
        return "publish-repo-bundle: skipped -- last publish exited 4 at this HEAD, not retried"

    publish_argv = [
        str(exe_path),
        "publish-repo-bundle",
        "--project-root",
        str(repo_root),
        "--json",
    ]
    if repo_slug:
        publish_argv.extend(["--repo", repo_slug])

    publish_code, _publish_out, publish_err = _run_and_wait(publish_argv, repo_root, _REBUILD_WAIT_SECONDS)
    if publish_code is None:
        return "publish-repo-bundle: skipped -- publish-repo-bundle timed out"

    first_line = _first_stderr_line(publish_err)

    if publish_code == 2 and "invalid choice: 'publish-repo-bundle'" in publish_err:
        return "publish-repo-bundle: skipped -- verb absent (installed CLI lacks publish-repo-bundle)"

    if publish_code == 0:
        line = "publish-repo-bundle: published"
    elif publish_code == 4:
        fix = _map_exit4_fix(publish_err)
        fix_text = fix or first_line or "refused (no reason given)"
        line = f"publish-repo-bundle: refused -- {fix_text} ({first_line})" if fix else f"publish-repo-bundle: refused -- {fix_text}"
    else:
        suffix = f", {first_line}" if first_line else ""
        line = f"publish-repo-bundle: skipped -- exited {publish_code}{suffix}"

    _write_record(record_path, publish_code, current_head, line)
    return line


def _default_repo_root() -> Path:
    """cwd's git toplevel -- the repo whose ceremony is running, never this
    script's own location. Falls back to cwd itself if no `.git` is found."""
    cwd = Path.cwd().resolve()
    for candidate in (cwd, *cwd.parents):
        if (candidate / ".git").exists():
            return candidate
    return cwd


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ceremony", required=True, help="ceremony name, e.g. handoff")
    parser.add_argument(
        "--repo-root",
        default=None,
        help="repo whose ceremony is running (default: git toplevel of cwd)",
    )
    parser.add_argument(
        "--cli",
        default=None,
        help="explicit project-rag CLI path (skips the registry read when given)",
    )
    parser.add_argument(
        "--repo",
        default=None,
        help="owner/name to pass through to publish-repo-bundle as --repo (operator override only)",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve() if args.repo_root else _default_repo_root()
    try:
        print(run(args.ceremony, repo_root, cli_override=args.cli, repo_slug=args.repo))
    except Exception as exc:
        print(f"publish-repo-bundle: skipped -- unexpected error: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
