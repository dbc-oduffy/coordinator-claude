# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
refresh-plugin-live-install.py — Managed refresh for a registered plugin's live install.

Spec backlink: docs/plans/2026-05-21-plugin-source-live-mirror-doctrine.md §Chunk 2 [DEAD-CITATION: plan file never committed to this repo]
Spec backlink: docs/plans/2026-07-19-debash-coordinator-windows.md (Wave E2, chunk E2-e)
Port of: refresh-plugin-live-install.sh (DoE 9a00683c, 2026-07-21) — naked-Python
port, no bash in the middle: git/uv/pip are still invoked as subprocesses, which is
the genuine external-tool boundary, not a shell wrapper around this script's own logic.

Purpose: perform both propagation legs atomically — git-state (advance HEAD to
track_ref) and venv-state (re-run editable install when pyproject or MAPPING stale).
Refuses on unsafe pre-flight states unless --force is given.

Usage:
  refresh-plugin-live-install.py <plugin> [--force] [--interactive]

  <plugin>        Plugin name as registered under plugin.mirrors.<plugin> in the
                   settings-home registry ($COORDINATOR_SETTINGS_HOME/machine-local/
                   registry.local.toml, falling back to registry.toml) — NOT
                   ~/.claude/machine-local.
  --force          Override the pre-flight clean-tree refusal ONLY (use for
                   broken-install recovery). Does NOT skip snapshot or lock,
                   and does NOT override the post-flight drift probe — a
                   forced run that still ends dirty is restored from snapshot
                   and fails, by design.
  --interactive    Per-file approval gate BEFORE the atomic refresh executes.

SIGKILL leaves a stale lock. Operator recovery:
  rm -rf ~/.claude/plugins/.refresh-<plugin>.lock.d

Idempotency: safe to re-run. If already at target SHA and pyproject unchanged,
all steps are no-ops or trivial-verify.

Negative spec: does NOT auto-kill the MCP server (concurrent-EM-hostile).
Embed sidecar self-evicts at idle timeout (300s/1800s). __pycache__/ bytecode
is mtime-invalidated automatically on next import.

Propagation modes (registry `propagation_mode` field):
  (default / unset)     git-managed live checkout + editable venv install.
  source_is_live         live install IS the canonical source — structural no-op,
                          except a venv-currency probe when the plugin is an
                          editable-installed Python package (pip/importlib.metadata
                          can lag pyproject after a version bump nobody reinstalled).
  copy_install            refresh action = registry-supplied refresh_cmd, run from
                          source_path. Snapshot + REPLACE-semantics restore on failure.
  editable_sibling_venv   source_path (addon's own checkout) and live_path (the HOST
                          plugin whose .venv the addon installs into) are two
                          DIFFERENT plugins. See docs/plans/2026-05-30-editable-
                          sibling-venv-propagation-mode.md.
"""

from __future__ import annotations

import argparse  # noqa: F401  (kept for parity with sibling ports; CLI uses a hand
                  # -rolled loop below so --help matches the original script's shape)
import atexit
import ctypes
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

PROG = "refresh-plugin-live-install.py"

GENERATES = []  # writes live_path (a registered plugin's live checkout under the Claude plugins dir), the refresh audit log, and snapshot dirs — all under the operator's Claude home, outside claude-klabauter's own tree (abs-path-ok: descriptive prose, not a resolve site)


def _no_console_kwargs() -> dict:
    """Deferred coordinator_core import — matches this file's CLAUDE_KLABAUTER_ROOT
    bootstrap posture (see ``_import_registry_deps``) so ``--help``/usage
    paths never pay a CLAUDE_KLABAUTER_ROOT resolution cost. On any CLAUDE_KLABAUTER_ROOT
    resolution/import failure, falls back to the same suppression kwargs
    computed inline (zero imports beyond ``subprocess``) rather than
    silently dropping console suppression -- a resolution failure must
    never turn a quiet spawn into a visible console window.
    """
    try:
        from cc_invoke import _resolve_claude_klabauter_root

        claude_klabauter_root = _resolve_claude_klabauter_root()
        if claude_klabauter_root not in sys.path:
            sys.path.insert(0, claude_klabauter_root)
        from coordinator_core.win_portability import no_console_creationflags

        return no_console_creationflags()
    except Exception:  # noqa: BLE001 -- fail-open, matches this module's bootstrap posture
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}

_HELP_TEXT = """\
Usage: refresh-plugin-live-install.py <plugin> [--force] [--interactive]

Perform a managed two-leg refresh of a registered plugin's live install:
  Leg 1 (git-state)  — fetch origin and checkout track_ref
  Leg 2 (venv-state) — re-run editable install if pyproject or MAPPING is stale

Options:
  --force         Override the PRE-FLIGHT clean-tree refusal only (use for
                  broken-install recovery). Does NOT skip snapshot or
                  concurrency lock, and does NOT override the POST-FLIGHT
                  drift probe — a forced run that still ends dirty is
                  restored from snapshot and fails.
  --interactive   Per-file approval gate BEFORE the atomic refresh executes.
                  Prompts for each incoming file: y=mirror N=skip d=diff a=all s=skip-rest q=quit.
                  Per-plugin blast radius only. Complementary to the atomic refresh, not a replacement.
                  Not supported for copy_install plugins (no per-file diff available).

Pre-conditions:
  - Plugin must be registered under plugin.mirrors.<plugin> in the settings-home
    registry ($COORDINATOR_SETTINGS_HOME/machine-local/registry.local.toml,
    falling back to registry.toml) — NOT ~/.claude/machine-local.
  - Plugin must NOT have propagation_mode = "source_is_live" (no refresh needed)
  - Live checkout working tree must be clean (no uncommitted edits) unless --force

SIGKILL leaves a stale lock. Operator recovery:
  rm -rf ~/.claude/plugins/.refresh-<plugin>.lock.d

Audit log: ~/.claude/plugins/.refresh-log
Snapshots: ~/.claude/plugins/_pre-refresh-snapshots/
"""


def eprint(*args, **kwargs) -> None:
    print(*args, file=sys.stderr, **kwargs)


# ---------------------------------------------------------------------------
# coordinator_core import bootstrap (CLAUDE_KLABAUTER_ROOT resolution) — deferred, not
# module-level, matching this tree's coordinator/bin/*.py convention (see e.g.
# check-em-environment.py) so `--help`/usage paths never pay a CLAUDE_KLABAUTER_ROOT
# resolution cost.
# ---------------------------------------------------------------------------

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from win_argv import win_safe_shlex_split  # noqa: E402


def _import_registry_deps():
    """Resolve CLAUDE_KLABAUTER_ROOT and import ``coordinator_core.machine_resolver`` —
    the canonical registry reader (``registry_get``) and the sole
    registry-directory ladder (``registry_dir``).

    Registry reads route through these rather than a hand-rolled
    ``~/.claude/machine-local``-only TOML parse — see ``_read_registry``'s
    docstring for the two defects that shape replaced.

    Negative-spec: this used to also return ``coordinator_core._settings_home``
    so ``main()`` could resolve the registry directory via
    ``machine_local_dir()``. That second resolver is what created the
    split-brain documented in ``_read_registry`` — do not reintroduce it here.
    """
    from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402

    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core import machine_resolver

    return machine_resolver


# ---------------------------------------------------------------------------
# Home / ~/.claude resolution, first hit wins: CLAUDE_HOME, then HOME, then
# USERPROFILE, then Path.home() —
# matches _claude_home.home_dir()'s precedence (coordinator/lib/claude-home/); a
# self-contained reimplementation rather than a cross-tree import so this bin/
# entrypoint has no lib/claude-home path-layout dependency.
# ---------------------------------------------------------------------------

def _resolve_claude_home() -> Path:
    override = os.environ.get("CLAUDE_HOME")
    if override:
        p = Path(override)
        if p.is_absolute():
            return p / ".claude"
    home = os.environ.get("HOME")
    if home:
        p = Path(home)
        if p.is_absolute():
            return p / ".claude"
    userprofile = os.environ.get("USERPROFILE")
    if userprofile:
        p = Path(userprofile)
        if p.is_absolute():
            return p / ".claude"
    return Path.home() / ".claude"


# ---------------------------------------------------------------------------
# Portable helpers: pid liveness, safe rmtree, timestamps, git, hashing.
# ---------------------------------------------------------------------------

def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            process_query_limited_information = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(  # type: ignore[attr-defined]
                process_query_limited_information, False, pid
            )
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore[attr-defined]
                return True
            return False
        except Exception:
            return True  # fail safe: assume alive if liveness can't be determined
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, just not ours
    except OSError:
        return False
    return True


def _safe_rmtree(path: Path) -> None:
    def _onerror(func, target_path, _exc_info):
        try:
            os.chmod(target_path, 0o777)
            func(target_path)
        except Exception:
            pass

    shutil.rmtree(path, onerror=_onerror)


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class ArgvCommandError(ValueError):
    """Raised when a configured command string cannot be parsed/resolved as argv.

    Argv-only contract: pipes, ``&&``/``||``, redirects, globs, and
    ``VAR=value`` prefixes are shell-only syntax and are not supported here —
    a wrapper script is the supported way to get shell semantics.
    """


def _parse_argv_command(
    cmd_str: str, source_desc: str, resolve_cwd: Path | None = None
) -> list[str]:
    """Parse a configured command string into argv, POSIX-shlex rules on every
    platform (portable token splitting only — no shell metacharacter support).

    Windows note: this uses ``win_argv.win_safe_shlex_split`` (posix-mode
    quote stripping/whitespace-splitting, with backslash escaping disabled)
    rather than bare ``shlex.split`` or ``posix=False`` — see that helper's
    docstring. Review: bare POSIX-mode ``shlex.split`` silently stripped
    backslashes from a Windows-authored value containing native ``\\`` path
    separators (e.g. a drive-letter path with backslash separators —
    abs-path-ok: illustrative example, not a real path), and the mangled
    path then surfaced verbatim in the ``ArgvCommandError`` diagnostic below
    — misattributing a path the operator never typed.
    ``win_argv.win_safe_shlex_split`` preserves the backslashes; quote
    stripping and unbalanced-quote detection match POSIX-mode
    ``shlex.split`` only for backslash-free input. Once a backslash is
    present the two diverge in both directions — see that helper's
    docstring for the mechanism and worked examples.

    ``resolve_cwd``, if given, is the directory the eventual ``subprocess.run``
    will actually execute under (its ``cwd=``) — used ONLY as a second
    resolution attempt for a relative first-token path, since this function is
    typically called from a different process cwd than the command will run
    in. Review: reviewer flagged a false-positive ``ArgvCommandError`` for a
    relative-path first token (e.g. ``./install.sh``) meant to resolve against
    the execution cwd rather than this validating process's cwd.

    Raises ``ArgvCommandError`` with a diagnostic naming ``source_desc`` (the
    config key or env var at fault) and the argv-only contract, on either a
    ``shlex.split`` failure (e.g. unbalanced quotes) or an empty/unresolvable
    first token.
    """
    try:
        argv = win_safe_shlex_split(cmd_str)
    except ValueError as exc:
        raise ArgvCommandError(
            f"{source_desc} is not a valid argv-only command ({exc}). "
            "Argv-only contract: pipes, &&/||, redirects, globs, and VAR=value "
            "prefixes are not supported — use a wrapper script for shell semantics."
        ) from exc
    if not argv:
        raise ArgvCommandError(
            f"{source_desc} is empty after argv parsing — nothing to execute."
        )
    resolvable = shutil.which(argv[0]) is not None or Path(argv[0]).exists()
    if not resolvable and resolve_cwd is not None:
        resolvable = (resolve_cwd / argv[0]).exists()
    if not resolvable:
        raise ArgvCommandError(
            f"{source_desc}: first token {argv[0]!r} is not an executable on PATH "
            "or a resolvable path. Argv-only contract: pipes, &&/||, redirects, "
            "globs, and VAR=value prefixes are not supported — use a wrapper "
            "script for shell semantics."
        )
    return argv


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        **_no_console_kwargs(),
    )


def _git_ref_exists(cwd: Path, ref: str) -> bool:
    return _git(["rev-parse", "--verify", ref], cwd).returncode == 0


def _git_rev_parse(cwd: Path, ref: str) -> str | None:
    r = _git(["rev-parse", ref], cwd)
    if r.returncode != 0:
        return None
    return r.stdout.strip()


def _pyproject_hash(path: Path) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    return hashlib.sha256(data).hexdigest()


def _last_recorded_hash(refresh_log: Path, plugin: str) -> str:
    if not refresh_log.exists():
        return ""
    last = ""
    try:
        text = refresh_log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    for line in text.splitlines():
        if f" {plugin} " not in line:
            continue
        m = re.search(r"pyproject_hash=([a-f0-9]*)", line)
        if m:
            last = m.group(1)
    return last


def _append_audit(refresh_log: Path, line: str) -> None:
    try:
        with open(refresh_log, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _read_mcp_pid(sentinel: Path) -> str:
    try:
        data = json.loads(sentinel.read_text(encoding="utf-8"))
    except Exception:
        return ""
    pid = data.get("mcp_server_pid", "")
    return str(pid) if pid else ""


# ---------------------------------------------------------------------------
# Venv-state helpers (shared by the default, editable_sibling_venv, and
# source_is_live_venv legs).
# ---------------------------------------------------------------------------

def _check_venv_state(live_path: Path, dist_name: str, pin_root: Path | None = None) -> bool:
    """True iff the editable install's direct_url.json + MAPPING (if present)
    still resolve to `pin_root` (defaults to `live_path`). Mirrors the venv
    freshness probe the bash oracle ran via a Python heredoc."""
    pin_root = pin_root or live_path
    venv = live_path / ".venv"
    if not venv.exists():
        return False

    sp_candidates = list(venv.glob("Lib/site-packages")) + list(venv.glob("lib/python*/site-packages"))
    if not sp_candidates:
        return False
    site_packages = sp_candidates[0]

    dist_info_dirs = list(site_packages.glob(f"{dist_name}-*.dist-info"))
    if not dist_info_dirs:
        return False
    dist_info = dist_info_dirs[0]

    direct_url_path = dist_info / "direct_url.json"
    if not direct_url_path.exists():
        return False
    try:
        direct_url = json.loads(direct_url_path.read_text(encoding="utf-8"))
    except Exception:
        return False

    url = direct_url.get("url", "")
    if url.startswith("file:///"):
        pinned_str = urllib.parse.unquote(urllib.parse.urlparse(url).path)
        if os.name == "nt" and len(pinned_str) > 2 and pinned_str[0] == "/" and pinned_str[2] == ":":
            pinned_str = pinned_str[1:]  # strip leading '/' before the Windows drive letter
        pinned_path = Path(pinned_str)
    else:
        pinned_path = Path(url)

    try:
        pin_resolved = pinned_path.resolve()
        pin_root_resolved = pin_root.resolve()
        if pin_resolved != pin_root_resolved:
            return False
    except Exception:
        return False

    finder_files = list(site_packages.glob("__editable__*_finder.py"))
    if finder_files:
        finder = finder_files[0]
        try:
            src = finder.read_text(encoding="utf-8")
            m = re.search(r"MAPPING\s*=\s*\{([^}]*)\}", src, re.DOTALL)
            if m:
                for path_match in re.finditer(r"'([^']+)'", m.group(1)):
                    candidate = Path(path_match.group(1))
                    if not candidate.exists():
                        return False
                    try:
                        candidate.resolve().relative_to(pin_root_resolved)
                    except ValueError:
                        return False
        except Exception:
            pass  # non-fatal — MAPPING check error doesn't block

    return True


def _venv_python_path(venv_dir: Path) -> Path:
    if os.name == "nt":
        candidate = venv_dir / "Scripts" / "python.exe"
    else:
        candidate = venv_dir / "bin" / "python"
    if candidate.exists():
        return candidate
    pyvenv_cfg = venv_dir / "pyvenv.cfg"
    if pyvenv_cfg.exists():
        home_line = None
        for line in pyvenv_cfg.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip().startswith("home"):
                home_line = line
                break
        if home_line:
            _, _, val = home_line.partition("=")
            home = val.strip()
            if home:
                for name in ("python.exe", "python"):
                    p = Path(home) / name
                    if p.exists():
                        return p
    return candidate


def _venv_created_by_pip(pyvenv_cfg: Path) -> bool:
    if not pyvenv_cfg.exists():
        return False
    text = pyvenv_cfg.read_text(encoding="utf-8", errors="replace").lower()
    return bool(re.search(r"virtualenv|pip", text)) and "uv" not in text


def _check_clean_tree(live_path: Path) -> bool | None:
    r = _git(["status", "--porcelain"], live_path)
    if r.returncode != 0:
        eprint(f"{PROG}: git status failed in {live_path}")
        return None
    return r.stdout.strip() == ""


# ---------------------------------------------------------------------------
# Snapshot / restore helpers.
# ---------------------------------------------------------------------------

def _snapshot_path(snapshots_dir: Path, plugin: str) -> Path:
    # DR-059 fix-in-port: the bash oracle's timestamp (1s granularity) collided
    # silently on same-second re-runs — `cp -r` onto an existing SNAPSHOT_PATH
    # nests LIVE_PATH inside it rather than erroring, corrupting the snapshot
    # without any signal. shutil.copytree fails loud on an existing dest, which
    # surfaced the latent bug during porting; disambiguate instead of crashing.
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    base = snapshots_dir / f"{plugin}-{ts}"
    if not base.exists():
        return base
    for suffix in range(1, 1000):
        candidate = snapshots_dir / f"{plugin}-{ts}-{suffix}"
        if not candidate.exists():
            return candidate
    return snapshots_dir / f"{plugin}-{ts}-{os.getpid()}"


def _take_snapshot(live_path: Path, snapshot_path: Path, label: str = "") -> bool:
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"{PROG}: {label}snapshotting {live_path} -> {snapshot_path}")
    try:
        shutil.copytree(live_path, snapshot_path)
    except Exception:
        eprint(f"{PROG}: snapshot failed — aborting for safety.")
        return False
    return True


def _overlay_restore(snapshot_path: Path, live_path: Path) -> bool:
    """Overlay (`cp -rf SNAPSHOT/. LIVE/`) restore — merges snapshot content into
    live, force-overwriting read-only dest files, WITHOUT deleting extraneous
    live files. Used only for the git-checkout-managed (default) restore path,
    where live IS a git checkout and a full wipe is unnecessary."""
    try:
        for root, _dirs, files in os.walk(snapshot_path):
            rel = Path(root).relative_to(snapshot_path)
            dest_dir = live_path / rel
            dest_dir.mkdir(parents=True, exist_ok=True)
            for fname in files:
                src_file = Path(root) / fname
                dest_file = dest_dir / fname
                if dest_file.exists():
                    try:
                        dest_file.chmod(0o644)
                    except OSError:
                        pass
                    try:
                        dest_file.unlink()
                    except OSError:
                        pass
                shutil.copy2(src_file, dest_file)
        return True
    except Exception:
        return False


def _replace_restore(snapshot_path: Path, live_path: Path) -> bool:
    """REPLACE (not overlay) restore for copy_install: stage-then-swap so
    LIVE_PATH stays intact until the copy succeeds — a failed install may have
    left orphaned files that an overlay restore would never clean up."""
    staging = live_path.parent / f"{live_path.name}.restore.{os.getpid()}"
    if staging.exists():
        _safe_rmtree(staging)
    try:
        shutil.copytree(snapshot_path, staging)
    except Exception:
        eprint(
            f"{PROG}: restore staging failed — {live_path} is intact. "
            f"Manual: copy from {snapshot_path}"
        )
        _safe_rmtree(staging)
        return False
    _safe_rmtree(live_path)
    try:
        staging.rename(live_path)
    except Exception:
        eprint(
            f"{PROG}: restore mv failed — both {live_path} and {staging} exist "
            "on disk. Manual recovery needed."
        )
        return False
    return True


# ---------------------------------------------------------------------------
# Lock (mkdir-based; atomic on POSIX and Windows — os.mkdir is atomic on both).
# ---------------------------------------------------------------------------

def _acquire_lock(lock_dir: Path) -> None:
    try:
        lock_dir.mkdir(parents=False)
    except FileExistsError:
        pid_file = lock_dir / "pid"
        stored_pid: int | None = None
        if pid_file.exists():
            try:
                stored_pid = int(pid_file.read_text(encoding="utf-8").strip())
            except (ValueError, OSError):
                stored_pid = None
        if stored_pid is not None and not _pid_alive(stored_pid):
            eprint(f"{PROG}: stale lock from dead PID {stored_pid} — clearing and retrying.")
            _safe_rmtree(lock_dir)
            try:
                lock_dir.mkdir(parents=False)
            except FileExistsError:
                eprint(f"{PROG}: could not acquire lock at {lock_dir}")
                eprint(f"  If stale, run: rm -rf '{lock_dir}'")
                sys.exit(1)
        else:
            eprint(
                f"{PROG}: refresh already in progress "
                f"(PID {stored_pid if stored_pid is not None else 'unknown'})."
            )
            eprint(f"  If this is stale, run: rm -rf '{lock_dir}'")
            sys.exit(1)

    (lock_dir / "pid").write_text(str(os.getpid()), encoding="utf-8")

    def _cleanup() -> None:
        _safe_rmtree(lock_dir)

    atexit.register(_cleanup)

    def _sig_handler(_signum, _frame):
        sys.exit(1)

    for sig_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            try:
                signal.signal(sig, _sig_handler)
            except (ValueError, OSError):
                pass


# ---------------------------------------------------------------------------
# Registry lookup (tomllib — requires Python >= 3.11, matches sibling ports'
# convention of failing loud rather than shipping a tomli fallback).
# ---------------------------------------------------------------------------

class RegistryExit(Exception):
    def __init__(self, code: int):
        super().__init__(f"registry lookup exit {code}")
        self.code = code


def _build_mirrors(data: dict) -> dict:
    # Build the mirrors dict from two sources (must match check-plugin-drift.py's
    # own resolution): (1) nested [plugin.mirrors.<name>] tables; (2) flat dotted-key
    # form "plugin.mirrors.<name>.<field>" = "..." written by `machine-local set`.
    # Both are valid registry writes; nested wins on collision.
    mirrors: dict = {}
    nested = data.get("plugin", {}).get("mirrors", {})
    if isinstance(nested, dict):
        for name, entry in nested.items():
            if isinstance(entry, dict):
                mirrors[name] = dict(entry)
    prefix = "plugin.mirrors."
    for raw_key, raw_val in data.items():
        if not isinstance(raw_key, str) or not raw_key.startswith(prefix):
            continue
        parts = raw_key[len(prefix):].split(".", 1)
        if len(parts) != 2:
            continue
        pname, field = parts
        mirrors.setdefault(pname, {})
        if field not in mirrors[pname]:
            mirrors[pname][field] = raw_val
    return mirrors


def _read_registry(registry_dir: Path, plugin: str, machine_resolver) -> dict:
    """Resolve a plugin's ``[plugin.mirrors.<plugin>]`` registry entry via the
    canonical settings-home registry reader
    (``coordinator_core.machine_resolver.registry_get``) — ``registry.local.toml``
    before ``registry.toml``, with an empty-string value treated as a miss.

    ``registry_dir`` is the resolved settings-home ``machine-local/`` directory
    (see ``main()``'s use of ``coordinator_core.machine_resolver.registry_dir()``),
    used ONLY for the existence/parse diagnostics below (RegistryExit 3/4) and
    for the table-presence check (RegistryExit 5) — the actual field VALUES are
    resolved through ``machine_resolver.registry_get``, which re-derives this
    same directory via that SAME ``registry_dir()`` ladder internally, so the
    two never disagree, override or no override.

    Negative-spec: do NOT resolve ``registry_dir`` via
    ``_settings_home.machine_local_dir()`` (which deliberately ignores
    ``MACHINE_LOCAL_REGISTRY_DIR``) while leaving ``registry_get`` on
    ``machine_resolver.registry_dir()`` (which honours it) — that split-brain
    previously let the gate checks above run against one registry while the
    field values below came from another, a real hazard given this CLI
    performs rm-rf-class operations on the resulting ``live_path``. Both
    legs MUST resolve through ``machine_resolver.registry_dir()``; there is
    exactly one override-aware ladder in this codebase and it lives there.

    Negative-spec: this function used to accept a single ``registry_path``
    pointing at ``<claude_home>/machine-local/registry.local.toml`` and parse
    ONLY that one file with a raw ``tomllib.loads`` — wrong directory (the
    registry lives under settings-home, i.e. ``$COORDINATOR_SETTINGS_HOME``,
    never under ``~/.claude``) AND ``.local``-only (never fell through to the
    tracked ``registry.toml``). Both defects were FAIL-LOUD (RegistryExit 3),
    which is how they were caught — but that also meant this function refused
    100% of the time on a settings-home-native machine. Do not re-introduce a
    single-file, `~/.claude`-rooted read here.

    A malformed registry FILE degrades to "not found" for that file only —
    matching ``machine_resolver.registry_get``'s ``_load_toml`` contract, so
    ``check_install_singularity.py`` (which delegates purely to
    ``registry_get``) never silently ignores a corrupt ``.local`` override
    while this CLI hard-fails on the identical file. This CLI still raises
    ``RegistryExit(4)`` fail-loud when the plugin is unresolvable AND a
    registry file failed to parse — a diagnosable install-integrity failure,
    not silently absorbed — but a plugin resolvable from the OTHER (parsing)
    file is returned normally, with the parse failure surfaced as a WARNING.
    """
    try:
        import tomllib
    except ImportError:
        eprint("ERROR: tomllib not available — requires Python >= 3.11")
        raise RegistryExit(2)

    local_path = registry_dir / "registry.local.toml"
    tracked_path = registry_dir / "registry.toml"
    if not local_path.exists() and not tracked_path.exists():
        eprint(f"ERROR: registry not found under {registry_dir}")
        raise RegistryExit(3)

    mirrors: dict = {}
    malformed_paths: list = []
    for path in (tracked_path, local_path):  # tracked first so .local's _build_mirrors merge wins on collision
        if not path.exists():
            continue
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            eprint(f"WARNING: failed to parse registry {path}: {exc} — degrading to 'not found' for this file")
            malformed_paths.append(path)
            continue
        for pname, entry in _build_mirrors(data).items():
            mirrors.setdefault(pname, {}).update(entry)

    if plugin not in mirrors:
        if malformed_paths:
            eprint(
                f"ERROR: '{plugin}' not resolvable — "
                f"{', '.join(str(p) for p in malformed_paths)} failed to parse "
                "and the surviving registry file(s) have no entry for it"
            )
            raise RegistryExit(4)
        raise RegistryExit(5)

    def _field(name: str) -> str:
        val = machine_resolver.registry_get(f"plugin.mirrors.{plugin}.{name}")
        return val if val is not None else ""

    prop_mode = _field("propagation_mode")

    if prop_mode == "source_is_live":
        # source_is_live is a structural no-op for CONTENT (the live install IS the
        # canonical source), but an editable-installed Python plugin can still carry
        # stale venv metadata — surface source_path + dist_name so the caller can run
        # a venv-currency probe; fall back to the bare sentinel when there is nothing
        # to probe (no source_path, or a non-Python plugin with no pyproject.toml).
        sil_source = _field("source_path")
        sil_dist = _field("dist_name") or plugin.replace("-", "_")
        if sil_source and (Path(sil_source) / "pyproject.toml").exists():
            return {"mode": "SOURCE_IS_LIVE_VENV", "source_path": sil_source, "dist_name": sil_dist}
        return {"mode": "SOURCE_IS_LIVE"}

    source_path = _field("source_path")
    live_path = _field("live_path")
    track_ref = _field("track_ref") or "origin/main"
    dist_name = _field("dist_name") or plugin.replace("-", "_")
    refresh_cmd = _field("refresh_cmd")

    if isinstance(refresh_cmd, str) and ("\n" in refresh_cmd or "\r" in refresh_cmd):
        eprint(f"ERROR: refresh_cmd for '{plugin}' contains a newline — single-line commands only")
        raise RegistryExit(7)

    if not source_path or not live_path:
        eprint(f"ERROR: registry entry for '{plugin}' missing source_path or live_path")
        raise RegistryExit(6)

    return {
        "mode": "NORMAL",
        "propagation_mode": prop_mode,
        "source_path": source_path,
        "live_path": live_path,
        "track_ref": track_ref,
        "dist_name": dist_name,
        "refresh_cmd": refresh_cmd,
    }


# ---------------------------------------------------------------------------
# MCP restart notices (never auto-kills the MCP server — concurrent-EM-hostile).
# ---------------------------------------------------------------------------

def _emit_default_mcp_notice(plugin: str, mcp_pid: str) -> None:
    bar = "=" * 72
    eprint(bar)
    eprint(f"NOTICE: refresh staged successfully; {plugin} MCP server must be restarted")
    if mcp_pid:
        eprint(f"       to take effect. Current MCP server PID: {mcp_pid} (kill it via")
        eprint("       /project-rag:doctor or restart Claude Code).")
    else:
        eprint("       to take effect.")
    eprint("       Embed sidecar will self-evict at idle timeout (300s/1800s).")
    eprint("       __pycache__/ bytecode is mtime-invalidated automatically.")
    eprint(bar)


def _emit_host_mcp_notice(plugin: str, mcp_pid: str) -> None:
    bar = "=" * 72
    eprint(bar)
    eprint(f"NOTICE: refresh staged successfully; {plugin} addon changes require the")
    eprint("       HOST MCP server (project-rag) to be restarted to take effect.")
    if mcp_pid:
        eprint(f"       Current HOST MCP server PID: {mcp_pid} (kill it via")
        eprint("       /project-rag:doctor or restart Claude Code).")
    eprint("       Embed sidecar will self-evict at idle timeout (300s/1800s).")
    eprint("       __pycache__/ bytecode is mtime-invalidated automatically.")
    eprint(bar)


# ---------------------------------------------------------------------------
# Interactive per-file approval gate.
# ---------------------------------------------------------------------------

def _tty_writer():
    if os.name == "nt":
        try:
            return open("CON", "w", encoding="utf-8", newline="")
        except OSError:
            return None
    try:
        return open("/dev/tty", "w", encoding="utf-8")
    except OSError:
        return None


def _interactive_gate(plugin: str, live_path: Path, checkout_ref: str):
    """Return (approved_paths, partial) on approval, or None if the operator
    quit / approved nothing (both cases: caller exits 0, nothing written)."""
    diff = _git(["diff", "--name-only", f"HEAD..{checkout_ref}"], live_path)
    incoming = [line for line in diff.stdout.splitlines() if line.strip()] if diff.returncode == 0 else []

    tty = _tty_writer()
    out = tty if tty is not None else sys.stderr

    def w(msg: str = "") -> None:
        out.write(msg + "\n")
        out.flush()

    try:
        if not incoming:
            w(f"{PROG}: [interactive] {plugin} already at {checkout_ref} — nothing to review.")
            return ([], False)

        w(f"{PROG}: [interactive] {plugin} — review incoming changes (y/N/d/a/s/q):")
        approved: list[str] = []
        skip_rest = 0  # 0=none, 1=skip-rest, 2=approve-rest
        for f in incoming:
            if skip_rest == 1:
                continue
            if skip_rest == 2:
                approved.append(f)
                continue
            while True:
                out.write(f"  {f}  [y=mirror N=skip d=diff a=all s=skip-rest q=quit]: ")
                out.flush()
                ans = sys.stdin.readline()
                ans = ans.strip() if ans else "q"
                if ans in ("y", "Y"):
                    approved.append(f)
                    break
                if ans in ("n", "N", ""):
                    break
                if ans in ("d", "D"):
                    dr = _git(["diff", f"HEAD..{checkout_ref}", "--", f], live_path)
                    out.write((dr.stdout or "") + (dr.stderr or ""))
                    out.flush()
                    continue
                if ans in ("a", "A"):
                    out.write("  Approve ALL remaining incoming files? [y/N]: ")
                    out.flush()
                    conf = sys.stdin.readline()
                    conf = conf.strip() if conf else "N"
                    if conf in ("y", "Y"):
                        approved.append(f)
                        skip_rest = 2
                        break
                    continue
                if ans in ("s", "S"):
                    skip_rest = 1
                    break
                if ans in ("q", "Q"):
                    eprint(f"{PROG}: [interactive] quit — no changes applied.")
                    return None
                out.write(f'  unrecognized "{ans}"\n')
                out.flush()

        total = len(incoming)
        approved_n = len(approved)
        if approved_n == 0:
            eprint(f"{PROG}: [interactive] nothing approved — exiting non-destructively.")
            return None
        if approved_n < total:
            eprint(f"{PROG}: [interactive] PARTIAL: {approved_n}/{total} files approved.")
            eprint("  Live install will be a MIXED state (HEAD not advanced; venv leg skipped for safety).")
            return (approved, True)
        print(f"{PROG}: [interactive] all {total} files approved — proceeding with full atomic refresh.")
        return ([], False)
    finally:
        if tty is not None:
            tty.close()


# ---------------------------------------------------------------------------
# Mode handlers.
# ---------------------------------------------------------------------------

def _handle_source_is_live_venv(plugin: str, sil_source: str, sil_dist: str, refresh_log: Path) -> int:
    """
    Deliberate isolation boundary — do not convert to an in-process
    import. This is a distinct interpreter/venv: version/drift checks run
    against the target plugin's own venv and its check-plugin-drift.py,
    which must execute under that target interpreter, not this process's.
    `COORDINATOR_REFRESH_VENV_INSTALL_CMD` is also an operator-configured
    escape hatch — an arbitrary command, not knowably Python. Reason
    recorded in
    state/audits/2026-08-06-self-spawn-isolation-boundary-classification.md.
    """
    sil_source_path = Path(sil_source)

    # pyproject version — the canonical source-of-truth version.
    src_ver = ""
    pyproject = sil_source_path / "pyproject.toml"
    if pyproject.exists():
        try:
            for line in pyproject.read_text(encoding="utf-8", errors="replace").splitlines():
                m = re.match(r'^\s*version\s*=\s*["\']?([^"\' ]+)["\']?', line)
                if m:
                    src_ver = m.group(1)
                    break
        except OSError:
            pass

    # Installed version from dist-info METADATA in the plugin's own .venv.
    venv = sil_source_path / ".venv"
    dist_info = None
    for sp_pattern in ("Lib/site-packages", "lib/python*/site-packages"):
        for sp in venv.glob(sp_pattern):
            matches = list(sp.glob(f"{sil_dist}-*.dist-info"))
            if matches:
                dist_info = matches[0]
                break
        if dist_info:
            break
    inst_ver = ""
    if dist_info is not None:
        metadata = dist_info / "METADATA"
        if metadata.exists():
            for line in metadata.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("Version:"):
                    inst_ver = line[len("Version:"):].strip()
                    break

    if not src_ver or not inst_ver:
        print(
            f"{PROG}: {plugin} propagation_mode=source_is_live — content canonical; "
            f"venv-currency not probeable (dist_name='{sil_dist or '?'}' "
            f"source='{src_ver or '?'}' installed='{inst_ver or '?'}'). No refresh needed."
        )
        return 0

    if src_ver == inst_ver:
        print(f"{PROG}: {plugin} propagation_mode=source_is_live — venv current (v{inst_ver}). No refresh needed.")
        return 0

    print(
        f"{PROG}: {plugin} propagation_mode=source_is_live — venv STALE: "
        f"installed=v{inst_ver}, source=v{src_ver}. Re-running editable install."
    )

    venv_py = _venv_python_path(venv)
    install_tool = "none"
    override_cmd = os.environ.get("COORDINATOR_REFRESH_VENV_INSTALL_CMD", "")
    if override_cmd:
        eprint(
            f"{PROG}: WARNING: COORDINATOR_REFRESH_VENV_INSTALL_CMD override active "
            "— skipping real editable install"
        )
        from cc_invoke import child_env  # noqa: E402 (path injected at module top)

        install_tool = "seam-override"
        env = child_env({"SIL_SOURCE": str(sil_source_path), "SIL_VENV_PY": str(venv_py)})
        # Inherited stdio, no creationflags: this is a network-bound editable install
        # the operator watches live. CREATE_NO_WINDOW + inherited stdio silently kills
        # the child on Windows (rc=1, no output) — a console flash beats that.
        # Argv-only contract: COORDINATOR_REFRESH_VENV_INSTALL_CMD is shlex.split
        # and exec'd directly as argv — no host shell is dispatched. Pipes,
        # &&/||, redirects, globs, and VAR=value prefixes are not supported;
        # use a wrapper script for shell semantics.
        try:
            override_argv = _parse_argv_command(
                override_cmd, "COORDINATOR_REFRESH_VENV_INSTALL_CMD"
            )
        except ArgvCommandError as exc:
            eprint(f"{PROG}: {exc}")
            return 1
        # Review: the resolution pre-check in _parse_argv_command only prevents the
        # common case — a TOCTOU race, a permission-denied file, or a non-executable
        # -format file still raises here. Loud, actionable WARN instead of a bare
        # traceback, matching coordinator-ceremony-hook.py's OSError handling.
        try:
            result = subprocess.run(override_argv, env=env)
        except OSError as exc:
            eprint(
                f"{PROG}: COORDINATOR_REFRESH_VENV_INSTALL_CMD failed to launch: "
                f"{override_argv!r} ({exc})."
            )
            return 1
        rc = result.returncode
    elif shutil.which("uv"):
        from cc_invoke import child_env  # noqa: E402 (path injected at module top)

        install_tool = "uv"
        result = subprocess.run(
            ["uv", "pip", "install", "-e", str(sil_source_path), "--python", str(venv_py)],
            env=child_env(),
        )
        rc = result.returncode
    elif venv_py.exists():
        from cc_invoke import child_env  # noqa: E402 (path injected at module top)

        install_tool = "pip"
        result = subprocess.run(
            [str(venv_py), "-m", "pip", "install", "-e", str(sil_source_path), "--quiet"],
            env=child_env(),
        )
        rc = result.returncode
    else:
        eprint(
            f"{PROG}: {plugin} source_is_live venv refresh — no uv on PATH and no "
            f"venv python at '{venv_py}'."
        )
        eprint(f"  Manual: uv pip install -e '{sil_source_path}' --python '{venv_py}'")
        return 1

    if rc != 0:
        eprint(f"{PROG}: {plugin} source_is_live venv refresh FAILED (exit {rc}).")
        eprint(f"  Manual retry: uv pip install -e '{sil_source_path}' --python '{venv_py}'")
        return 1

    _append_audit(
        refresh_log,
        f"{_now_iso()} {plugin} source_is_live venv-refresh v{inst_ver}->v{src_ver} install_tool={install_tool}",
    )
    print(f"{PROG}: {plugin} source_is_live venv refreshed to v{src_ver}.")
    return 0


def _resolve_contained_live_path(
    live_path_raw: str,
    source_path_raw: str,
    propagation_mode: str,
    plugins_dir: Path,
    plugin: str,
    leg_label: str,
) -> Path | None:
    """Containment guard for a registry-supplied ``live_path``, shared by every
    refresh leg that performs a destructive operation (rm-rf-class replace or
    ``git checkout``) against it. Resolve to the physical path (requires the dir
    to exist), require it live under the coordinator plugins dir — not merely
    contain a "/plugins/" substring — and require it NOT be the plugin's own
    source checkout (which would point a destructive refresh at a live source
    tree) unless the plugin is registered ``propagation_mode = "source_is_live"``.

    Fail loud, no fallback: any leg of this check that cannot be verified is a
    refusal (returns ``None``), never a "warn and continue". Callers must treat
    ``None`` as an abort signal and MUST NOT proceed.
    """
    try:
        live_path_resolved = Path(live_path_raw).resolve(strict=True)
    except (OSError, RuntimeError):
        live_path_resolved = None
    if live_path_resolved is None or not live_path_resolved.is_dir():
        eprint(
            f"{PROG}: ABORT: [{leg_label}] live_path '{live_path_raw}' for '{plugin}' is not "
            "an existing directory — refusing refresh."
        )
        return None

    try:
        plugins_dir_resolved = plugins_dir.resolve(strict=True)
    except (OSError, RuntimeError):
        plugins_dir_resolved = None

    if plugins_dir_resolved is None or not live_path_resolved.is_relative_to(plugins_dir_resolved):
        eprint(
            f"{PROG}: ABORT: [{leg_label}] resolved live_path '{live_path_resolved}' for "
            f"'{plugin}' is not under the coordinator plugins dir '{plugins_dir_resolved}' "
            "— refusing (rm-rf guard). live_path must point inside the managed plugins tree."
        )
        return None

    if propagation_mode != "source_is_live":
        try:
            source_path_resolved = Path(source_path_raw).resolve(strict=True)
        except (OSError, RuntimeError):
            eprint(
                f"{PROG}: ABORT: [{leg_label}] source_path '{source_path_raw}' for '{plugin}' "
                "does not resolve to an existing directory — refusing (cannot verify live_path "
                "is not the source checkout)."
            )
            return None

        try:
            same = os.path.samefile(live_path_resolved, source_path_resolved)
        except OSError:
            # Both already passed resolve(strict=True), so this is not expected, but
            # samefile can still raise on some platforms/filesystems — fall back to a
            # normalized-case comparison of the already-RESOLVED paths (never raw
            # strings), so Windows' case-insensitive filesystem doesn't slip a
            # differently-cased duplicate past the check.
            same = os.path.normcase(str(live_path_resolved)) == os.path.normcase(str(source_path_resolved))

        if same:
            eprint(
                f"{PROG}: ABORT: [{leg_label}] resolved live_path '{live_path_resolved}' for "
                f"'{plugin}' is the same directory as source_path — refusing to run a "
                "destructive refresh against a source checkout. Either point live_path at a "
                "separate managed mirror under the plugins dir, or register "
                "propagation_mode = 'source_is_live' if the live install IS meant to be the "
                "canonical source."
            )
            return None

    return live_path_resolved


def _handle_copy_install(
    plugin: str,
    source_path_raw: str,
    live_path_raw: str,
    refresh_cmd: str,
    interactive: bool,
    plugins_dir: Path,
    snapshots_dir: Path,
    refresh_log: Path,
    registry_local: Path,
) -> int:
    """
    Deliberate isolation boundary — do not convert to an in-process
    import. `refresh_cmd` is operator-set (machine-local key
    `plugin.mirrors.<plugin>.refresh_cmd`, shlex.split) and is an
    arbitrary, potentially non-Python command, not knowably Python — it
    must run as its own process. This is also a distinct interpreter/venv
    drift probe against the target install. Reason recorded in
    state/audits/2026-08-06-self-spawn-isolation-boundary-classification.md.
    """
    # --interactive is out of scope for copy_install: the refresh action is an opaque
    # registry-supplied refresh_cmd, not a git checkout — there is no per-file diff to gate.
    if interactive:
        eprint(
            f"{PROG}: --interactive is unsupported for copy_install plugins "
            "(no per-file diff available). Run without --interactive."
        )
        return 1

    source_path = Path(source_path_raw)

    live_path = _resolve_contained_live_path(
        live_path_raw, source_path_raw, "copy_install", plugins_dir, plugin, "copy_install",
    )
    if live_path is None:
        return 1

    # No refresh_cmd registered → cannot auto-refresh (the bare installer would hit
    # the standalone gate). Print the actionable manual path and exit non-zero.
    if not refresh_cmd:
        eprint(f"{PROG}: [copy_install] {plugin} has no refresh_cmd registered — cannot auto-refresh.")
        eprint(f"  Refresh manually, then re-run the probe (check-plugin-drift.py {plugin}):")
        eprint("    example-game-repo trio (umbrella):  /example-game-repo:install")
        eprint(
            f'    per-component (standalone): ( cd "{source_path}" && '
            "bash scripts/install-<component>-plugin.sh --allow-standalone --no-enable )"
        )
        eprint("  To enable automated refresh, register the invocation (run from source_path):")
        eprint(f"    machine-local set plugin.mirrors.{plugin}.refresh_cmd '<command>'")
        return 1

    # Snapshot live install for rollback insurance.
    snapshot_path = _snapshot_path(snapshots_dir, plugin)
    if not _take_snapshot(live_path, snapshot_path, label="[copy_install] "):
        return 1

    # Argv-only contract: `plugin.mirrors.<plugin>.refresh_cmd` is shlex.split
    # and exec'd directly as argv — no host shell is dispatched. Pipes,
    # &&/||, redirects, globs, and VAR=value prefixes are not supported; use a
    # wrapper script (e.g. "bash scripts/install-<component>-plugin.sh") for
    # shell semantics. A parse/resolve failure takes the same failure route as
    # a non-zero refresh_cmd return code, below — snapshot-restore-on-failure
    # still fires.
    refresh_failed = False
    try:
        # Review: resolve_cwd=source_path — the actual subprocess.run below runs
        # with cwd=source_path, not this validating process's cwd, so a relative
        # first-token path (e.g. "./install.sh") must be checked against that
        # execution cwd too, or it is wrongly rejected as unresolvable.
        refresh_argv = _parse_argv_command(
            refresh_cmd, f"plugin.mirrors.{plugin}.refresh_cmd", resolve_cwd=source_path
        )
    except ArgvCommandError as exc:
        eprint(f"{PROG}: {exc}")
        refresh_failed = True
    else:
        # Run the registry-supplied refresh command from source_path. Inherited
        # stdio, no creationflags: refresh_cmd is an arbitrary, potentially
        # long-running installer script the operator watches live —
        # CREATE_NO_WINDOW + inherited stdio silently kills the child on
        # Windows (rc=1, no output); a console flash beats that.
        print(f"{PROG}: [copy_install] running (cwd={source_path}): {refresh_cmd}")
        # Review: the resolution pre-check above only prevents the common case — a
        # TOCTOU race, a permission-denied file, or a non-executable-format file
        # still raises OSError here, which the snapshot-restore-on-failure route
        # below is meant to cover for ANY parse/resolve/launch failure — a bare
        # OSError propagating past this would leave the live install neither
        # refreshed nor restored.
        try:
            result = subprocess.run(refresh_argv, cwd=str(source_path))
        except OSError as exc:
            eprint(f"{PROG}: [copy_install] refresh_cmd failed to launch: {refresh_argv!r} ({exc}).")
            refresh_failed = True
        else:
            refresh_failed = result.returncode != 0

    if refresh_failed:
        eprint(f"{PROG}: copy-install refresh failed — restoring from snapshot.")
        if snapshot_path.is_dir():
            if _replace_restore(snapshot_path, live_path):
                eprint(f"{PROG}: restored from snapshot.")
        else:
            eprint(f"{PROG}: snapshot not found at {snapshot_path} — manual recovery required.")
        return 1

    # Post-flight drift probe — assert sentinel now matches source HEAD.
    drift_probe = Path(__file__).resolve().parent / "check-plugin-drift.py"
    post_flight_clean = True
    if drift_probe.exists():
        from cc_invoke import child_env  # noqa: E402 (path injected at module top)

        env = child_env({"MACHINE_LOCAL_REGISTRY_DIR": str(registry_local.parent)})
        r = subprocess.run(
            [sys.executable, str(drift_probe), plugin],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **_no_console_kwargs(),
        )
        if r.returncode != 0:
            post_flight_clean = False

    if not post_flight_clean:
        eprint(f"{PROG}: ERROR: post-flight drift probe failed for copy_install — restoring from snapshot.")
        if snapshot_path.is_dir():
            if not _replace_restore(snapshot_path, live_path):
                return 1
            eprint(f"{PROG}: restored from snapshot. Investigate and retry.")
        else:
            eprint(f"{PROG}: snapshot not found — manual recovery required.")
        return 1

    end_ts = _now_iso()
    _append_audit(refresh_log, f"{end_ts}  {plugin}  copy_install  refresh_cmd={refresh_cmd}")
    print(f"{PROG}: done (copy_install). Audit row appended to {refresh_log}")
    return 0


def _handle_editable_sibling_venv(
    plugin: str,
    source_path_raw: str,
    live_path_raw: str,
    track_ref: str,
    dist_name: str,
    force: bool,
    refresh_log: Path,
) -> int:
    """
    Deliberate isolation boundary — do not convert to an in-process
    import. This is a distinct interpreter/venv: pip/uv bootstrap and
    drift/version checks against the target sibling venv must run under
    that venv's own interpreter, not this process's. Reason recorded in
    state/audits/2026-08-06-self-spawn-isolation-boundary-classification.md.
    """
    source_path = Path(source_path_raw)
    live_path = Path(live_path_raw)
    old_sha = "unknown"
    new_sha = "unknown"

    if track_ref == "live":
        print(f"{PROG}: [editable_sibling_venv] git-state live (track_ref=live sentinel) — skipping git leg")
    else:
        print(f"{PROG}: [editable_sibling_venv] [git-leg] fetching origin in {source_path}")

        clean_ok = _check_clean_tree(source_path)
        if clean_ok is not True:
            if force:
                eprint(
                    f"{PROG}: [editable_sibling_venv] WARNING: addon source at {source_path} "
                    "has uncommitted edits (--force given, proceeding)."
                )
            else:
                eprint(f"{PROG}: [editable_sibling_venv] addon source at {source_path} has uncommitted edits.")
                eprint("  Resolve or stash local edits, then re-run.")
                eprint("  To override this pre-flight refusal only (broken-install recovery): add --force")
                eprint("  Note: --force does not affect the post-flight drift check — a run that still")
                eprint("  ends dirty is restored from snapshot and fails regardless.")
                return 1

        if _git(["fetch", "origin"], source_path).returncode != 0:
            eprint(f"{PROG}: [editable_sibling_venv] git fetch failed in {source_path}.")
            return 1

        if _git_ref_exists(source_path, f"refs/remotes/{track_ref}"):
            checkout_ref = track_ref
        elif _git_ref_exists(source_path, f"refs/tags/{track_ref}"):
            checkout_ref = track_ref
        elif _git_ref_exists(source_path, "FETCH_HEAD"):
            checkout_ref = "FETCH_HEAD"
        else:
            checkout_ref = track_ref

        old_sha = _git_rev_parse(source_path, "HEAD") or "unknown"
        print(f"{PROG}: [editable_sibling_venv] [git-leg] checking out {checkout_ref} in {source_path}")
        if checkout_ref.startswith("origin/"):
            local_branch = checkout_ref[len("origin/"):]
            r = _git(["checkout", "-B", local_branch, checkout_ref], source_path)
            if r.returncode != 0:
                eprint(
                    f"{PROG}: [editable_sibling_venv] git checkout -B {local_branch} "
                    f"{checkout_ref} failed."
                )
                return 1
        else:
            r = _git(["checkout", checkout_ref], source_path)
            if r.returncode != 0:
                eprint(f"{PROG}: [editable_sibling_venv] git checkout {checkout_ref} failed.")
                return 1
        new_sha = _git_rev_parse(source_path, "HEAD") or "unknown"
        print(f"{PROG}: [editable_sibling_venv] [git-leg] HEAD advanced: {old_sha[:12]}->{new_sha[:12]}")

    # Venv-state leg. pyproject hash reads SOURCE_PATH/pyproject.toml (NOT live_path).
    pyproject = source_path / "pyproject.toml"
    venv_refreshed = "n"
    install_tool = "none"
    pyproject_changed = "n"
    current_hash = _pyproject_hash(pyproject) if pyproject.exists() else ""
    last_hash = _last_recorded_hash(refresh_log, plugin)

    venv_state_ok = False
    if (live_path / ".venv").is_dir():
        venv_state_ok = _check_venv_state(live_path, dist_name, source_path)

    need_install = False
    if not current_hash:
        pass  # no pyproject.toml in source_path — skip venv install
    elif current_hash != last_hash:
        pyproject_changed = "y"
        need_install = True
        print(f"{PROG}: [editable_sibling_venv] [venv-leg] pyproject.toml changed (hash mismatch) — re-install needed.")
    elif not venv_state_ok:
        need_install = True
        print(f"{PROG}: [editable_sibling_venv] [venv-leg] venv state stale (direct_url or MAPPING) — re-install needed.")
    else:
        print(f"{PROG}: [editable_sibling_venv] [venv-leg] pyproject unchanged and venv state OK — skipping re-install.")

    if need_install:
        pyvenv_cfg = live_path / ".venv" / "pyvenv.cfg"
        venv_created_by_pip = _venv_created_by_pip(pyvenv_cfg)
        venv_python = _venv_python_path(live_path / ".venv")

        if shutil.which("uv"):
            install_tool = "uv"
        elif venv_created_by_pip:
            print(f"{PROG}: [editable_sibling_venv] [venv-leg] venv created by pip; using pip for editable install.")
            install_tool = "pip"
        else:
            print(f"{PROG}: [editable_sibling_venv] [venv-leg] uv not on PATH — bootstrapping via pip install uv (180s timeout)")
            from cc_invoke import child_env  # noqa: E402 (path injected at module top)

            # Inherited stdio, no creationflags: network-bound bootstrap the operator
            # watches live. CREATE_NO_WINDOW + inherited stdio silently kills the
            # child on Windows (rc=1, no output) — a console flash beats that.
            boot = subprocess.run(
                [sys.executable, "-m", "pip", "install", "uv", "--timeout", "180", "--quiet"],
                env=child_env(),
            )
            if boot.returncode == 0:
                install_tool = "uv"
            else:
                eprint(f"{PROG}: [editable_sibling_venv] FATAL: uv bootstrap failed.")
                eprint("  Install uv manually: https://docs.astral.sh/uv/getting-started/installation/")
                return 1

        print(
            f"{PROG}: [editable_sibling_venv] [venv-leg] running {install_tool} pip install -e "
            f"'{source_path}' --python '{venv_python}'"
        )
        # Inherited stdio, no creationflags on both branches below: network-bound
        # editable install the operator watches live (see bootstrap comment above).
        from cc_invoke import child_env  # noqa: E402 (path injected at module top)

        if install_tool == "uv":
            r = subprocess.run(
                ["uv", "pip", "install", "-e", str(source_path), "--python", str(venv_python)],
                env=child_env(),
            )
            if r.returncode != 0:
                eprint(f"{PROG}: [editable_sibling_venv] uv pip install -e failed.")
                eprint(f"  Manual retry: uv pip install -e '{source_path}' --python '{venv_python}'")
                return 1
        else:
            r = subprocess.run(
                [str(venv_python), "-m", "pip", "install", "-e", str(source_path), "--quiet"],
                env=child_env(),
            )
            if r.returncode != 0:
                eprint(f"{PROG}: [editable_sibling_venv] pip install -e failed.")
                eprint(f"  Manual retry: '{venv_python}' -m pip install -e '{source_path}'")
                return 1
        venv_refreshed = "y"
        print(f"{PROG}: [editable_sibling_venv] [venv-leg] editable install complete (tool: {install_tool}).")

    # MCP NOTICE — targets live_path (the host), not plugins_dir/plugin.
    doctor_sentinel = live_path / "data" / "doctor-last-run.json"
    if doctor_sentinel.exists():
        _emit_host_mcp_notice(plugin, _read_mcp_pid(doctor_sentinel))

    end_ts = _now_iso()
    _append_audit(
        refresh_log,
        f"{end_ts}  {plugin}  editable_sibling_venv  pyproject_changed={pyproject_changed}  "
        f"venv_refreshed={venv_refreshed}  install_tool={install_tool}  pyproject_hash={current_hash}",
    )
    print(f"{PROG}: [editable_sibling_venv] done. Audit row appended to {refresh_log}")

    drift_probe = Path(__file__).resolve().parent / "check-plugin-drift.py"
    post_flight_clean = True
    if drift_probe.exists():
        from cc_invoke import child_env  # noqa: E402 (path injected at module top)

        env = child_env({"CURRENT_PYPROJECT_HASH_OVERRIDE": current_hash})
        r = subprocess.run(
            [sys.executable, str(drift_probe), plugin],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **_no_console_kwargs(),
        )
        if r.returncode != 0:
            post_flight_clean = False

    if not post_flight_clean:
        eprint(f"{PROG}: [editable_sibling_venv] WARNING: post-flight drift probe reported drift.")
        eprint("  The venv-leg completed but drift remains. Investigate manually:")
        eprint(f"    check-plugin-drift.py {plugin}")
        eprint("  No snapshot rollback in editable_sibling_venv mode (source tree is a git repo).")
        return 1

    return 0


def _handle_default(
    plugin: str,
    source_path_raw: str,
    live_path_raw: str,
    propagation_mode: str,
    track_ref: str,
    dist_name: str,
    force: bool,
    interactive: bool,
    plugins_dir: Path,
    snapshots_dir: Path,
    refresh_log: Path,
) -> int:
    """
    Deliberate isolation boundary — do not convert to an in-process
    import. This is a distinct interpreter/venv: pip/uv bootstrap and
    drift probe against a target venv must run under that venv's own
    interpreter, not this process's. Reason recorded in
    state/audits/2026-08-06-self-spawn-isolation-boundary-classification.md.
    """
    live_path = _resolve_contained_live_path(
        live_path_raw, source_path_raw, propagation_mode, plugins_dir, plugin, "git-managed",
    )
    if live_path is None:
        return 1
    drift_probe = Path(__file__).resolve().parent / "check-plugin-drift.py"

    # Step: drift probe / working-tree cleanliness check.
    clean_tree_ok = True
    if drift_probe.exists():
        from cc_invoke import child_env  # noqa: E402 (path injected at module top)

        r = subprocess.run(
            [sys.executable, str(drift_probe), plugin, "--check-clean-only"],
            env=child_env(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **_no_console_kwargs(),
        )
        if r.returncode != 0:
            clean_tree_ok = False
    else:
        if _check_clean_tree(live_path) is not True:
            clean_tree_ok = False

    if not clean_tree_ok:
        if force:
            eprint(f"{PROG}: WARNING: live checkout has uncommitted edits (--force given, proceeding).")
        else:
            eprint(f"{PROG}: live checkout at {live_path} has uncommitted edits.")
            eprint("  Resolve or stash local edits, then re-run.")
            eprint("  To override this pre-flight refusal only (broken-install recovery): add --force")
            eprint("  Note: --force does not affect the post-flight drift check — a run that still")
            eprint("  ends dirty is restored from snapshot and fails regardless.")
            return 1

    old_sha = _git_rev_parse(live_path, "HEAD") or "unknown"

    print(f"{PROG}: [git-leg] fetching origin in {live_path}")
    if _git(["fetch", "origin"], live_path).returncode != 0:
        eprint(f"{PROG}: git fetch failed.")
        return 1

    if _git_ref_exists(live_path, f"refs/remotes/{track_ref}"):
        checkout_ref = track_ref
    elif _git_ref_exists(live_path, f"refs/tags/{track_ref}"):
        checkout_ref = track_ref
    elif _git_ref_exists(live_path, "FETCH_HEAD"):
        checkout_ref = "FETCH_HEAD"
    else:
        checkout_ref = track_ref

    interactive_approved: list[str] = []
    interactive_partial = False
    if interactive:
        gate_result = _interactive_gate(plugin, live_path, checkout_ref)
        if gate_result is None:
            return 0  # quit / nothing approved — no snapshot written, nothing changed
        interactive_approved, interactive_partial = gate_result

    snapshot_path = _snapshot_path(snapshots_dir, plugin)
    if not _take_snapshot(live_path, snapshot_path):
        return 1

    if interactive_partial:
        print(f"{PROG}: [git-leg] PARTIAL checkout of approved files only (HEAD will NOT advance).")
        for f in interactive_approved:
            r = _git(["checkout", checkout_ref, "--", f], live_path)
            if r.returncode != 0:
                eprint(f"{PROG}: git checkout of '{f}' failed.")
                return 1
        new_sha = _git_rev_parse(live_path, "HEAD") or "unknown"
        print(f"{PROG}: [git-leg] PARTIAL checkout complete. HEAD stayed at {new_sha[:12]}.")
    else:
        print(f"{PROG}: [git-leg] checking out {checkout_ref}")
        r = _git(["checkout", checkout_ref], live_path)
        if r.returncode != 0:
            eprint(f"{PROG}: git checkout {checkout_ref} failed.")
            return 1
        new_sha = _git_rev_parse(live_path, "HEAD") or "unknown"
        print(f"{PROG}: [git-leg] HEAD advanced: {old_sha[:12]}->{new_sha[:12]}")

    if interactive_partial:
        eprint(f"{PROG}: [venv-leg] SKIPPED — partial-interactive mode. Live install is now in a MIXED state.")
        eprint(f"  Run: refresh-plugin-live-install.py {plugin}")
        eprint("  A plain (non-interactive) refresh will converge to the full atomic state.")

    pyproject = live_path / "pyproject.toml"
    venv_refreshed = "n"
    install_tool = "none"
    pyproject_changed = "n"
    current_hash = _pyproject_hash(pyproject) if pyproject.exists() else ""
    last_hash = _last_recorded_hash(refresh_log, plugin)

    venv_state_ok = False
    if (live_path / ".venv").is_dir():
        venv_state_ok = _check_venv_state(live_path, dist_name)

    need_install = False
    if not current_hash:
        pass  # no pyproject.toml — skip venv install
    elif current_hash != last_hash:
        pyproject_changed = "y"
        need_install = True
        print(f"{PROG}: [venv-leg] pyproject.toml changed (hash mismatch) — re-install needed.")
    elif not venv_state_ok:
        need_install = True
        print(f"{PROG}: [venv-leg] venv state stale (direct_url or MAPPING) — re-install needed.")
    else:
        print(f"{PROG}: [venv-leg] pyproject unchanged and venv state OK — skipping re-install.")

    if interactive_partial:
        # A partial source checkout against an unchanged HEAD is not a coherent
        # editable-install state — skip the venv leg entirely.
        need_install = False

    if need_install:
        pyvenv_cfg = live_path / ".venv" / "pyvenv.cfg"
        venv_created_by_pip = _venv_created_by_pip(pyvenv_cfg)
        venv_python = _venv_python_path(live_path / ".venv")

        if shutil.which("uv"):
            install_tool = "uv"
        elif venv_created_by_pip:
            print(
                f"{PROG}: [venv-leg] venv created by pip; using pip for editable install "
                "(audit: tool-switch avoided to preserve dist-info shape)."
            )
            install_tool = "pip"
        else:
            # No bare pip fallback — bypasses [tool.uv.sources] and PEP 440 local pins.
            print(f"{PROG}: [venv-leg] uv not on PATH — bootstrapping via pip install uv (180s timeout)")
            from cc_invoke import child_env  # noqa: E402 (path injected at module top)

            # Inherited stdio, no creationflags: network-bound bootstrap the operator
            # watches live. CREATE_NO_WINDOW + inherited stdio silently kills the
            # child on Windows (rc=1, no output) — a console flash beats that.
            boot = subprocess.run(
                [sys.executable, "-m", "pip", "install", "uv", "--timeout", "180", "--quiet"],
                env=child_env(),
            )
            if boot.returncode == 0:
                install_tool = "uv"
            else:
                eprint(f"{PROG}: FATAL: uv bootstrap failed.")
                eprint("  Bare 'pip install -e .' is not a safe fallback — bypasses [tool.uv.sources] and PEP 440 local pins.")
                eprint("  Install uv manually: https://docs.astral.sh/uv/getting-started/installation/")
                return 1

        print(f"{PROG}: [venv-leg] running {install_tool} pip install -e . (python: {venv_python})")
        # Inherited stdio, no creationflags on both branches below: network-bound
        # editable install the operator watches live (see bootstrap comment above).
        from cc_invoke import child_env  # noqa: E402 (path injected at module top)

        if install_tool == "uv":
            r = subprocess.run(
                ["uv", "pip", "install", "-e", ".", "--python", str(venv_python)],
                cwd=str(live_path),
                env=child_env(),
            )
            if r.returncode != 0:
                eprint(f"{PROG}: uv pip install -e . failed.")
                return 1
        else:
            r = subprocess.run(
                [str(venv_python), "-m", "pip", "install", "-e", ".", "--quiet"],
                cwd=str(live_path),
                env=child_env(),
            )
            if r.returncode != 0:
                eprint(f"{PROG}: pip install -e . failed.")
                return 1
        venv_refreshed = "y"
        print(f"{PROG}: [venv-leg] editable install complete (tool: {install_tool}).")

    # Post-flight drift probe — assert zero items.
    post_flight_clean = True
    if interactive_partial:
        # HEAD is intentionally behind track_ref in partial mode — drift is expected;
        # do NOT restore from snapshot (that would undo the operator-approved partial
        # checkout). Force-pass so the audit row is written and the run exits cleanly.
        eprint(f"{PROG}: [post-flight] SKIPPED for partial-interactive mode — drift is expected (HEAD behind track_ref).")
        eprint(f"  Run: refresh-plugin-live-install.py {plugin}  (plain refresh to converge)")
    else:
        if drift_probe.exists():
            from cc_invoke import child_env  # noqa: E402 (path injected at module top)

            env = child_env({"CURRENT_PYPROJECT_HASH_OVERRIDE": current_hash})
            r = subprocess.run(
                [sys.executable, str(drift_probe), plugin],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **_no_console_kwargs(),
            )
            if r.returncode != 0:
                post_flight_clean = False
        else:
            if _check_clean_tree(live_path) is not True:
                post_flight_clean = False

    if not post_flight_clean:
        eprint(f"{PROG}: ERROR: post-flight drift check failed — restoring from snapshot.")
        eprint(f"  Snapshot: {snapshot_path}")
        if snapshot_path.is_dir():
            # .git safety guard: refuse destructive restore when live_path is not a git
            # repo — guards against a misconfigured live_path pointing at a broad dir.
            # copy_install entries never reach here (own branch above); this guard
            # applies only to the default (git-checkout-managed) restore.
            if not (live_path / ".git").is_dir():
                eprint(f"{PROG}: ABORT: {live_path} is not a git repo — refusing rm -rf for safety.")
                eprint(f"  Manual recovery: restore from {snapshot_path}")
                return 1
            if not _overlay_restore(snapshot_path, live_path):
                eprint(
                    f"{PROG}: overlay restore failed — {live_path} may be partially "
                    f"restored. Manual: copy from {snapshot_path}"
                )
                return 1
            eprint(f"{PROG}: restored from snapshot. Investigate and retry.")
        else:
            eprint(f"{PROG}: snapshot not found at {snapshot_path} — manual recovery required.")
        return 1

    # MCP server NOTICE.
    doctor_sentinel = plugins_dir / plugin / "data" / "doctor-last-run.json"
    if doctor_sentinel.exists():
        _emit_default_mcp_notice(plugin, _read_mcp_pid(doctor_sentinel))

    end_ts = _now_iso()
    _append_audit(
        refresh_log,
        f"{end_ts}  {plugin}  {old_sha[:12]}->{new_sha[:12]}  pyproject_changed={pyproject_changed}  "
        f"venv_refreshed={venv_refreshed}  install_tool={install_tool}  pyproject_hash={current_hash}",
    )
    print(f"{PROG}: done. Audit row appended to {refresh_log}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str]) -> tuple[str, bool, bool]:
    plugin: str | None = None
    force = False
    interactive = False
    for arg in argv:
        if arg == "--force":
            force = True
        elif arg == "--interactive":
            interactive = True
        elif arg in ("--help", "-h"):
            print(_HELP_TEXT, end="")
            sys.exit(0)
        elif arg.startswith("-"):
            eprint(f"{PROG}: unknown flag: {arg}")
            eprint("Run with --help for usage.")
            sys.exit(1)
        else:
            if plugin is None:
                plugin = arg
            else:
                eprint(f"{PROG}: unexpected argument: {arg}")
                eprint("Run with --help for usage.")
                sys.exit(1)

    if not plugin:
        eprint(f"{PROG}: <plugin> argument required.")
        eprint("Run with --help for usage.")
        sys.exit(1)

    return plugin, force, interactive


def main(argv: list[str]) -> int:
    plugin, force, interactive = _parse_args(argv)

    claude_home = _resolve_claude_home()
    plugins_dir = claude_home / "plugins"
    machine_resolver = _import_registry_deps()
    registry_dir = machine_resolver.registry_dir()
    registry_local = registry_dir / "registry.local.toml"
    refresh_log = plugins_dir / ".refresh-log"
    snapshots_dir = plugins_dir / "_pre-refresh-snapshots"

    plugins_dir.mkdir(parents=True, exist_ok=True)
    lock_dir = plugins_dir / f".refresh-{plugin}.lock.d"
    _acquire_lock(lock_dir)

    try:
        registry = _read_registry(registry_dir, plugin, machine_resolver)
    except RegistryExit as exc:
        if exc.code == 5:
            eprint(f"{PROG}: plugin '{plugin}' is not registered under {registry_dir}")
            eprint(f"  Add a [plugin.mirrors.{plugin}] entry to register it.")
        else:
            eprint(f"{PROG}: registry lookup failed (exit {exc.code})")
        return exc.code

    mode = registry["mode"]

    if mode == "SOURCE_IS_LIVE":
        print(
            f"{PROG}: {plugin} has propagation_mode=source_is_live — live install IS "
            "the canonical source. No refresh needed."
        )
        return 0

    if mode == "SOURCE_IS_LIVE_VENV":
        return _handle_source_is_live_venv(plugin, registry["source_path"], registry["dist_name"], refresh_log)

    propagation_mode = registry["propagation_mode"]
    source_path = registry["source_path"]
    live_path = registry["live_path"]
    track_ref = registry["track_ref"]
    dist_name = registry["dist_name"]
    refresh_cmd = registry["refresh_cmd"]

    if propagation_mode == "copy_install":
        return _handle_copy_install(
            plugin, source_path, live_path, refresh_cmd, interactive,
            plugins_dir, snapshots_dir, refresh_log, registry_local,
        )

    if propagation_mode == "editable_sibling_venv":
        return _handle_editable_sibling_venv(
            plugin, source_path, live_path, track_ref, dist_name, force, refresh_log,
        )

    return _handle_default(
        plugin, source_path, live_path, propagation_mode, track_ref, dist_name, force, interactive,
        plugins_dir, snapshots_dir, refresh_log,
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
