"""coordinator/bin/scip-rebuild-at-ceremony.py -- best-effort ceremony hook into
project-rag's `scip-rebuild --ceremony NAME` verb.

Purpose: project-rag's ceremony-gated SCIP cadence arm fires only when a ceremony calls
it; this is that call, invoked from `handoff`, `workstream-complete`, and
`merging-to-main` after each ceremony's own commit lands.

Binary resolution is by `machine-local get project_rag.bin.project_rag_cli` ONLY -- no
cwd-relative fallback; this script never guesses a path. A missing key skips only
on a box without project-rag (`repos.project_rag` unset); with project-rag registered,
it -- like a key naming a file that no longer exists -- prints a `defect -- <reason>`
line instead, still exiting 0.

Detached, best-effort, ALWAYS exits 0. The detached child is now
`publish-repo-bundle-at-ceremony.py` (docs/plans/2026-09-26-wire-repo-index-bundle-verbs.md
Design SS Ceremony, row C3), a sequencer that runs the rebuild itself, waits on it, and
publishes the freshly-rebuilt structural index via project-rag's `publish-repo-bundle`
verb only after that rebuild exits 0 -- so the chain now publishes what it rebuilt, still
detached from this process, still best-effort, and still never a ceremony gate: this
script's own job ends at a successful spawn, not at the child's exit, exactly as before.
Never fails a ceremony: every reachable error path prints one `skipped -- <reason>` (or,
for a broken registry, `defect -- <reason>`) line and exits 0, including a resolution failure, a bad ceremony name, or a spawn failure.
It also skips when available memory is below the rebuild's floor (default 8 GB; a nan,
infinite or negative env floor falls back to the default); a host that cannot report
available memory spawns as before, but an absent engine prints a `defect` line and does not spawn.

`run()` additionally prints, as a second line, the `line` field of the PRIOR publish
attempt's record (`<git-common-dir>/coordinator-sessions/publish-repo-bundle-last.json`,
written by the sequencer) when one is present -- so an exit-4 fix reaches the next
ceremony's own transcript, not only a log file. This process never writes that record
itself; it only reads it, best-effort, and a missing/unreadable/malformed record simply
means no second line.

Negative-spec:
  - Does NOT invoke the bare `machine-local` wrapper (forbidden for consumers, see
    docs/wiki/hook-best-practices/machine-local-registry.md Sec8(a)) -- resolves `<settings-home>/bin/
    _machine_local.py` by path arithmetic and runs it under `sys.executable`, the same
    shape `claude_machine_local.py`'s `_reader_invocation` uses.
  - Does NOT wait on, poll, or report the outcome of the spawned rebuild/publish chain --
    watching is the sequencer's own job, not this script's.
  - Does NOT validate `--repo-root` beyond making it the child's cwd -- the CLI resolves
    its own project root from there and reports exit 1 for a repo with no project-rag
    index, which this script treats as an ordinary background-child outcome, never an
    error surfaced here.
  - Does NOT write the prior-publish record it reads -- read-only, best-effort, never
    raises on a missing or malformed record.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_THIS = Path(__file__).resolve()
_REPO_ROOT = _THIS.parent.parent.parent
#: Sibling lib/: coordinator/lib in this tree, lib/ in the published plugin layout.
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


# project-rag's own CLI enforces this grammar too, but refusing here keeps a
# malformed name from ever reaching a subprocess argv.
_CEREMONY_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
# The fleet's largest SCIP rebuild peaks near 4 GB resident (project-rag); the floor keeps 2x
# that free so the spawn never pushes a busy box toward the OOM reaper. Below it, skip.
_MIN_AVAILABLE_GB_DEFAULT = 8.0
_MIN_AVAILABLE_GB_ENV = "COORDINATOR_SCIP_REBUILD_MIN_AVAILABLE_GB"


class EngineUnavailable(RuntimeError):
    """The coordinator engine that supplies the memory sampler did not resolve."""


def available_memory_gb() -> float | None:
    """Physical memory available to a new process, in GB; None when this host can't say.

    Raises EngineUnavailable when the engine itself is absent -- the gate cannot run, which
    is a defect, not "can't say"."""
    try:
        bin_lib = str(Path(__file__).resolve().parent / "lib")
        if bin_lib not in sys.path:
            sys.path.insert(0, bin_lib)
        from cc_invoke import require_engine_on_path

        require_engine_on_path(__file__)
        from coordinator_core.telemetry import host_sampler
    except Exception as exc:  # noqa: BLE001
        raise EngineUnavailable(str(exc) or type(exc).__name__) from exc
    try:
        avail, _total = host_sampler.avail_mb()
    except Exception:  # noqa: BLE001 -- a sampler that cannot read means "can't say"
        return None
    return None if avail is None else avail / 1024


def _min_available_gb() -> float:
    """The floor from the env, else the default; a non-finite or negative value is nonsense."""
    raw = os.environ.get(_MIN_AVAILABLE_GB_ENV)
    try:
        value = float(raw) if raw else _MIN_AVAILABLE_GB_DEFAULT
    except ValueError:
        return _MIN_AVAILABLE_GB_DEFAULT
    return value if math.isfinite(value) and value >= 0 else _MIN_AVAILABLE_GB_DEFAULT


_PUBLISH_SEQUENCER = Path(__file__).resolve().parent / "publish-repo-bundle-at-ceremony.py"
_PUBLISH_RECORD_NAME = "publish-repo-bundle-last.json"


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


def _spawn_detached(argv: list[str], cwd: Path, log_path: Path) -> bool:
    """Launch argv as a detached background process, stdout/stderr to `log_path`.
    Returns True on a successful spawn (not a successful rebuild -- this never
    waits). False on any spawn failure, which the caller reports and still exits 0.
    """
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = open(log_path, "a", encoding="utf-8")
    except OSError:
        return False
    try:
        kwargs: dict = dict(
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=log_handle,
            cwd=str(cwd),
        )
        if os.name == "nt":
            create_new_process_group = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
            kwargs.update(no_console_creationflags())
            kwargs["creationflags"] = kwargs.get("creationflags", 0) | create_new_process_group
            subprocess.Popen(argv, **kwargs)
        else:
            subprocess.Popen(argv, start_new_session=True, **kwargs)
        return True
    except OSError:
        return False
    finally:
        log_handle.close()


def _git_common_dir(repo_root: Path) -> Path | None:
    """Walk `.git` (dir or worktree pointer-file) to the common dir, the same
    shape `track-dispatched-agents.py`'s local-log writers use -- so this
    script's logs land beside the rest of this repo's local, non-portable
    per-machine state rather than inventing a second convention.
    """
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


def _read_prior_publish_line(common_dir: Path) -> str | None:
    """Best-effort read of the sequencer's last-publish record's `line` field.
    Missing file, unreadable file, or malformed/non-dict JSON all read as
    "no prior line" -- never raises."""
    record_path = common_dir / "coordinator-sessions" / _PUBLISH_RECORD_NAME
    try:
        raw = record_path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    line = data.get("line")
    return line if isinstance(line, str) and line else None


def _default_repo_root() -> Path:
    """cwd's git toplevel -- the repo whose ceremony is running, never this
    script's own location. Falls back to cwd itself if no `.git` is found
    anywhere above it (a caller outside any repo gets a log dir under cwd,
    and the child CLI will fail loud on its own root resolution)."""
    cwd = Path.cwd().resolve()
    for candidate in (cwd, *cwd.parents):
        if (candidate / ".git").exists():
            return candidate
    return cwd


def run(ceremony: str, repo_root: Path) -> str:
    """Resolve, validate, and spawn. Returns the one line to print -- never
    raises; every failure path is a `skipped -- <reason>` string."""
    if not _CEREMONY_NAME_RE.match(ceremony):
        return f"scip-rebuild: skipped -- invalid --ceremony name {ceremony!r} (must match [a-z0-9][a-z0-9_-]*)"

    exe, reason = _resolve_registry_key("project_rag.bin.project_rag_cli")
    if exe is None:
        return _unresolved_cli_line("scip-rebuild", reason)
    exe_path = Path(exe).expanduser()
    if not exe_path.is_file():
        return f"scip-rebuild: defect -- registry key names a file that does not exist: {exe_path}"

    try:
        available = available_memory_gb()
    except EngineUnavailable as exc:
        return f"scip-rebuild: defect -- coordinator engine unavailable, memory gate cannot run: {exc}"
    floor = _min_available_gb()
    if available is not None and available < floor:
        return (
            f"scip-rebuild: skipped -- {available:.1f} GB available, below the {floor:.0f} GB a rebuild "
            f"needs (set {_MIN_AVAILABLE_GB_ENV} to change); run `scip-rebuild` on a quiet box"
        )

    common_dir = _git_common_dir(repo_root) or repo_root
    log_dir = common_dir / "coordinator-sessions" / "logs"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = log_dir / f"scip-rebuild-{ceremony}-{stamp}.log"

    argv = [
        _console_python(),
        str(_PUBLISH_SEQUENCER),
        "--ceremony",
        ceremony,
        "--repo-root",
        str(repo_root),
        "--cli",
        str(exe_path),
    ]
    if not _spawn_detached(argv, repo_root, log_path):
        return f"scip-rebuild: skipped -- failed to spawn {exe_path}"

    line = f"scip-rebuild: spawned ({ceremony}) -> {log_path}"
    prior_line = _read_prior_publish_line(common_dir)
    if prior_line:
        line = f"{line}\n{prior_line}"
    return line


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ceremony", required=True, help="ceremony name, e.g. handoff")
    parser.add_argument(
        "--repo-root",
        default=None,
        help="repo whose ceremony is running (default: git toplevel of cwd)",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve() if args.repo_root else _default_repo_root()
    try:
        print(run(args.ceremony, repo_root))
    except Exception as exc:  # best-effort: never fail the ceremony that called this
        print(f"scip-rebuild: skipped -- unexpected error: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
