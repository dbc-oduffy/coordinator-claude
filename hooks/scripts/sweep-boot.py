#!/usr/bin/env python3
"""sweep-boot.py — doctrine-plane-resident trampoline over the control-plane engine's sweep-boot.py.

Purpose: `coordinator/bin/` (incl. `sweep-boot.py`) migrated to claude-klabauter
on 2026-07-22 (commit b644d5a9). `hooks.json`'s SessionStart entry invokes a
doctrine-plane-resident path via `${CLAUDE_PLUGIN_ROOT}/hooks/scripts/sweep-boot.py` — a
literal JSON string that cannot carry a resolution ladder (env → registry →
sibling walk). This trampoline lives at the JSON-referenced location instead,
resolves claude-klabauter via the shared `_engine_root` seam, and execs the
migrated copy, forwarding argv and the child's exit code/stdout untouched.

Fail-open on exit code, matching the SessionStart hook's own contract
(session start must never wedge): an unresolved claude-klabauter root, a missing/
incomplete claude-klabauter clone, a spawn failure, and a nonzero child exit each print
one stderr diagnostic line and print "0" on stdout (byte-parity with
sweep-boot.py's own transport-failure contract), then return 0 — never
raise, never block boot. That process-exit contract is unchanged.

Fail-LOUD to the housekeeping-failures log (2026-07-23, mirroring
Claude-klabauter's own C20): stdout/exit-code alone made a genuinely-dead
sweep byte-indistinguishable from a clean one — every failure path here
printed "0" and exited 0, identically to "nothing to archive", and
`async: true` discards stdout regardless. Each of the four failure paths
below now ALSO best-effort appends a `CHILD FAILED` record to the shared
`<repo>/state/housekeeping-failures.log` (the same log claude-klabauter's own
migrated `sweep-boot.py` already writes to via
`coordinator_core.ops.ceremony.detached_spawn.record_child_failure`, which
`coordinator_core.orientation.regenerate_cache` surfaces via the orientation
cache's `## Housekeeping` section at the next session start) — three of the
four paths reuse that exact writer (a claude-klabauter root is already resolved by
that point); the fourth (root itself unresolved) hand-rolls a
format-matched fallback line, since an unresolved root leaves no
`coordinator_core` to import in the first place. The failure-recording path
is itself defensive: a write failure is swallowed and never escalates past
this trampoline's own already-best-effort, fail-open contract.

Spec backlink: cross-repo unbreak pass following b644d5a9 (coordinator
bin/lib migration to claude-klabauter), verify-sweep survivor B.1.
Spec backlink: cross-repo/inbox/2026-07-23-claude-klabauter-em-wsc-tail-doe-ask-list.md
  § "Ready now" item 4 — the doctrine-plane-side half of the fail-loud fix.
Spec backlink: claude-klabauter commit 0822ea47 ("C20: make the boot-sweep
  transport fail loud instead of fail silent") — the child-side half this
  trampoline-level half is compatible with, not a second competing surface.

Orientation-cache self-heal (added 2026-07-29, orientation-cache-stale-by-
construction spinoff, leg 2): after the boot-sweep child above completes (or
fails — the two jobs are independent), this module ALSO best-effort checks
`state/orientation_cache.md` for staleness against current HEAD and, when
stale, invokes the cache regenerator with the `sweep-boot` invoker. This
pays the ~10-subprocess full-regen cost here, off the sync `SessionStart`
hot path (`project-orientation.py`, whose zero-spawn boot mandate this does
NOT reopen — see that file's own docstring), because THIS hook is already
registered async with stdout discarded, so the extra spawns cost zero
first-token latency regardless of count. Leg 1 (a sibling change to
`project-orientation.py`, not this file) makes a stale cache ANNOUNCE
itself at boot; this leg makes it STOP being stale, without any ceremony.

Concurrency: the regenerator (`coordinator_core.orientation.regenerate_cache
.build_cache`, invoked out-of-process below) already holds its own
cross-process `_OrientationCacheLock` around the cache write, so multiple
sessions self-healing concurrently serialize safely on the write side —
this module deliberately does NOT add a second lock around the invocation.
It DOES add a randomized jitter delay (`_SELFHEAL_JITTER_MAX_SECONDS`)
before invoking the regenerator: at fleet scale (~14 sessions booting near-
simultaneously against a 5s lock timeout and a ~1.17s real regen) an
unjittered herd concentrates every invocation into the very first lock
window, so most sessions lose the race and each loser logs a generic
failure record indistinguishable from a genuine regenerator bug. The
jitter spreads invocations across several lock windows instead; a nonzero
regenerator exit is still recorded, but the message now notes that benign
lock contention is a possible cause, not just a regenerator defect.

The regenerator is spawned via `_invoke_regenerator` (Popen, not
`subprocess.run`) specifically so a 60s timeout can kill the child's WHOLE
process group on POSIX (`start_new_session=True` + `os.killpg`), not just
the immediate child — `subprocess.run`'s own timeout handling only kills
the direct child and can leave one of the regenerator's own in-flight git
subprocesses orphaned. No-op on Windows, which has no equivalent process-
group-signal concept reachable from here.

Failure handling for this leg matches the boot-sweep leg's own contract
above exactly: one stderr diagnostic, a best-effort `_record_failure()`
call (the SAME shared writer, not a second log format), and the hook still
returns 0 — never changes this hook's exit code, and never prints anything
beyond the boot-sweep leg's existing "0"/count on stdout (async stdout is
discarded, but the boot-sweep count is still byte-parity-load-bearing per
that leg's own contract, so this leg stays silent on stdout regardless).

Opt-out: `COORDINATOR_ORIENTATION_SELFHEAL_OFF` (any non-empty value)
skips this leg entirely, leaving the boot sweep untouched — mirrors the
env-opt-out convention used elsewhere in this codebase (e.g.
`COORDINATOR_OVERRIDE_*` guard hatches).

Spec backlink: state/handoffs/2026-07-29-orientation-cache-stale-by-construction.md
Spec backlink: state/audits/2026-07-29-orientation-cache-boot-facts.md § "Proposed fix" item 2

Global-doctrine mirror fold-in (added 2026-08-01): a third, independent leg,
`_derive_global_doctrine_mirror()`, invokes
`derive-global-doctrine-live-copy.py`'s SessionStart derivation mode
IN-PROCESS (via `importlib.util.spec_from_file_location` -- that file's own
name is hyphenated, so it is not `import`-able by bare module name) rather
than by subprocess. That derivation hook was registered ONLY on
PostToolUse(Write|Edit|MultiEdit), so it was structurally blind to the most
common way its tracked source actually changes on this shared-branch repo:
`git pull`/`checkout`/`merge`/a peer session's commit landing between
sessions. Its own module already carries an inert SessionStart mode built
for exactly this gap -- this leg is what wires it up.

Deliberately NOT given its own `hooks.json` SessionStart entry: that block
carries a standing PM directive (2026-07-15, full-kill-keep-fast-
orientation) that removed boot-time guardrail/reminder/detector SessionStart
hooks to protect boot latency, and a lockdown test
(`test_guard_hook_generation_self_probe.py::
test_sessionstart_sibling_entries_unchanged_by_registration`) pins the
SessionStart entry count and sibling script order. Each `hooks.json` entry
is a separate `python3 -c ...` process spawn on EVERY session boot on EVERY
machine -- a P0 portability cost this repo treats seriously on Windows. This
module is ALREADY a registered SessionStart hook (the boot-sweep trampoline
above), so calling the derivation in-process from here costs zero additional
spawns; a dedicated hook entry would both reopen the 2026-07-15 directive
and break the lockdown test. Anyone tempted to "clean this up" into its own
hook entry should read this paragraph first.

Failure handling matches the two legs above: never allowed to affect this
module's exit code or the boot-sweep leg's byte-parity stdout contract,
never raises past `_derive_global_doctrine_mirror()` itself, and stays
silent on stdout in every case (the wrapped derivation module speaks only to
stderr, and only when it actually re-derives the live copy or hits a genuine
read/write failure -- see that module's own docstring; a clean, in-sync boot
prints nothing new here). Called LAST in `main()`, after both the boot-sweep
and orientation-selfheal legs, so a failure in this leg can never pre-empt
either of the higher-priority legs ahead of it.

Spec backlink: coordinator/hooks/scripts/derive-global-doctrine-live-copy.py
Spec backlink: coordinator/hooks/hooks.json (SessionStart block, 2026-07-15
  full-kill-keep-fast-orientation `_comment`)
Spec backlink: coordinator/tests/test_guard_hook_generation_self_probe.py::
  test_sessionstart_sibling_entries_unchanged_by_registration
"""

from __future__ import annotations

import importlib.util
import os
import random
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
try:
    from _engine_root import resolve_claude_klabauter_root
except Exception:
    # Defensive fallback -- a hook script copied/deployed WITHOUT its
    # sibling _engine_root.py (e.g. an isolated test harness, or a
    # partial deploy) must still fail-open rather than crash on import.
    def resolve_claude_klabauter_root() -> str | None:
        return None
try:
    from _git_root_walk import git_root_walk as _git_root_walk
except Exception:
    # Defensive fallback -- a deploy missing its sibling _git_root_walk.py
    # must still fail open to the subprocess rung below, not crash on import.
    def _git_root_walk() -> str | None:
        return None


# Windows: suppresses the console popup a subprocess.run(...) would otherwise
# trigger under the headless Claude Code Bash-tool parent. No-op (0) elsewhere.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# POSIX-only: os.setsid()/os.killpg() don't exist on Windows, which has no
# equivalent process-group-signal concept reachable from here. Guards the
# start_new_session=True + killpg path in _invoke_regenerator below.
_CAN_KILL_PROCESS_GROUP = hasattr(os, "setsid") and hasattr(os, "killpg")

# Fleet-scale numbers this bound is sized against (state/audits/2026-07-29-
# orientation-cache-boot-facts.md): ~14 concurrent sessions can boot near-
# simultaneously; the regenerator's own cross-process lock
# (`_OrientationCacheLock`, module docstring's "Concurrency" section) times
# out after 5s; a real regen run measures ~1.17s. Roughly 4 sessions fit
# inside one 5s lock window with zero spread, so with no jitter most of the
# remaining ~10 sessions race the lock and lose in the very first window.
# Spreading invocations across a several-second window instead lets losers
# from window 1 land in window 2, 3, etc., rather than all piling onto the
# same window. This hook is async with discarded stdout (module docstring),
# so the delay costs nothing user-visible.
_SELFHEAL_JITTER_MAX_SECONDS = 6.0

# Reused by both the stderr diagnostic and the failure-log record on a
# nonzero regenerator exit so the two stay in sync (finding: a bare "exited
# N" is indistinguishable from a real regenerator bug in the housekeeping
# log; a nonzero exit here MAY be benign lock contention from another
# session that won the same jitter window, not a defect).
_LOCK_CONTENTION_NOTE = (
    "may be lock contention with a peer session, not necessarily a defect"
)


def _resolve_this_repo_root() -> str | None:
    """Resolve the repo THIS hook is running in (cwd-based) — the destination for the
    housekeeping-failures log, NOT the claude-klabauter root.

    Mirrors claude-klabauter's own `sweep-boot.py::_resolve_repo_root` fallback rung
    exactly (`git rev-parse --show-toplevel`) so a trampoline-level failure record lands
    in the SAME per-repo log the migrated child's own `record_child_failure` calls
    already write to — confirmed empirically: this repo's own
    `state/housekeeping-failures.log` already carries a child-side `CHILD FAILED` record
    from a prior session's transport timeout.

    Deliberately NOT `Path(__file__)`-based: this file's `__file__` lives under the
    doctrine-source tree regardless of which consumer repo's session invoked it (live
    `--plugin-dir` resolution — see repo CLAUDE.md § Architecture), so a `__file__`-based
    root would silently mis-file every session running from a different consumer repo's
    failure record into the doctrine-source repo's own `state/` tree instead of the
    session's actual repo.

    In-process parent walk (`_git_root_walk`, cwd-based like this function's own contract)
    first -- no subprocess on the routine path; `git rev-parse --show-toplevel` below is kept
    only as a fallback for the case the walk cannot resolve.
    """
    walked = _git_root_walk()
    if walked:
        return walked
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            creationflags=_NO_WINDOW,
        )
    except OSError:
        return None
    root = result.stdout.strip()
    if result.returncode != 0 or not root:
        return None
    return root


def _import_record_child_failure(claude_klabauter_root: str | None):
    """Best-effort import of the shared `record_child_failure` writer
    (`coordinator_core.ops.ceremony.detached_spawn`) from an already-resolved claude-klabauter
    root. Returns None on any resolution/import failure — reused across three of the
    four failure paths below rather than each hand-rolling its own log-append.
    """
    if not claude_klabauter_root:
        return None
    try:
        if claude_klabauter_root not in sys.path:
            sys.path.insert(0, claude_klabauter_root)
        from coordinator_core.ops.ceremony.detached_spawn import record_child_failure
    except Exception:
        return None
    return record_child_failure


def _write_raw_failure_record(repo_root: str, detail: str) -> None:
    """Hand-rolled fallback append, format-matched to
    `coordinator_core.ops.ceremony.detached_spawn.record_child_failure`'s own
    ``CHILD FAILED script=<path> :: <detail>`` line shape.

    Used ONLY on the one failure path where the sibling's writer is structurally
    unreachable: an unresolved claude-klabauter root means there is no known `coordinator_core` to
    import in the first place. Every other failure path below resolves a claude-klabauter root
    successfully and calls the real `record_child_failure` instead — this is the
    documented one-off, not a second competing log format. Swallows every failure of its
    own; a broken observability path must never wedge boot.
    """
    from datetime import datetime, timezone

    try:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        line = f"[{timestamp}] CHILD FAILED script={os.path.abspath(__file__)} :: {detail}\n"
        log_path = Path(repo_root, "state", "housekeeping-failures.log")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception:
        pass


def _record_failure(
    claude_klabauter_root: str | None,
    detail: str,
    *,
    exit_code: int | None = None,
) -> None:
    """Best-effort, defensive-by-construction failure recorder shared by all four
    fail-open paths below. NEVER raises — a broken observability path must never become
    the thing that wedges SessionStart boot.
    """
    try:
        repo_root = _resolve_this_repo_root()
        if not repo_root:
            return
        record_child_failure = _import_record_child_failure(claude_klabauter_root)
        if record_child_failure is not None:
            record_child_failure(
                repo_root,
                os.path.abspath(__file__),
                exc=None if exit_code is not None else RuntimeError(detail),
                exit_code=exit_code,
            )
        else:
            _write_raw_failure_record(repo_root, detail)
    except Exception:
        pass


_FRONTMATTER_KV_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*?)\s*$")


def _claude_home() -> Path:
    """Resolves the $HOME analog for this hook's own settings-home lookup.

    Sources from the engine's canonical resolver (`resolve_home_base()` in the
    `_claude_home` module, reached via the importable `claude_home_shim` seam
    at the resolved engine root — that module's own directory is hyphenated
    and not import-able directly) when the engine is reachable, so this hook
    shares ONE canonical HOME/USERPROFILE/CLAUDE_HOME precedence chain with
    the rest of the fleet instead of a second hand-maintained ladder.

    Falls back to the local two-rung ladder below (CLAUDE_HOME env var, else
    `Path.home()`) on ANY resolution failure — the engine root unresolved,
    the engine clone missing that module, or the shim raising on import (e.g.
    malformed CLAUDE_HOME, which the canonical resolver treats as a hard
    `ValueError` rather than a silent fallthrough). This hook is a fail-open
    SessionStart hook (module docstring) and must never raise or block boot
    on a settings-home lookup; the local fallback is the documented
    degradation path, not dead code to delete once the shim exists.

    Was previously a documented verbatim copy of
    `project-orientation.py::_claude_home()` (own local ladder, no shared
    source) — superseded now that the engine exports a canonical resolver
    reachable without spawning a subprocess. `project-orientation.py` is
    being converged onto the same seam by a separate, concurrent change; this
    function stays self-contained (no cross-import of that sibling file)
    since each SessionStart hook script resolves its own settings-home
    independently.
    """
    try:
        claude_klabauter_root = resolve_claude_klabauter_root()
        if claude_klabauter_root:
            lib_dir = os.path.join(claude_klabauter_root, "coordinator", "lib")
            if lib_dir not in sys.path:
                sys.path.insert(0, lib_dir)
            from claude_home_shim import resolve_home_base

            return resolve_home_base()
    except Exception:
        pass

    v = os.environ.get("CLAUDE_HOME")
    if v:
        return Path(v)
    return Path.home()


def _settings_home() -> Path:
    """Mirrors `project-orientation.py::_settings_home()` exactly."""
    v = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if v:
        return Path(v)
    return _claude_home() / ".coordinator-claude-settings"


def _read_cache_head(repo_root: str) -> Optional[str]:
    """Best-effort read of `git_head_at_generation` from
    `<repo_root>/state/orientation_cache.md`'s YAML frontmatter.

    Returns the raw (short) sha string, or None on any read/parse failure OR when the
    cache file is missing OR when the field is absent/empty — all three collapse to
    "cannot verify freshness", which the caller treats as stale (a cache that cannot
    prove it is fresh is not fresh; see `_cache_is_stale`'s docstring).
    """
    cache_path = Path(repo_root, "state", "orientation_cache.md")
    try:
        text = cache_path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    frontmatter = parts[1]
    for line in frontmatter.splitlines():
        match = _FRONTMATTER_KV_RE.match(line)
        if match and match.group(1) == "git_head_at_generation":
            value = match.group(2).strip()
            return value or None
    return None


def _read_current_head(repo_root: str) -> Optional[str]:
    """Full-length current HEAD sha, via `git rev-parse HEAD`. This module already
    runs on the async, stdout-discarded SessionStart path (module docstring), so the
    extra spawn here costs zero first-token latency — unlike `project-orientation.py`'s
    sync boot path, which is under a zero-spawn mandate this file does not share.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5.0,
            creationflags=_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    head = result.stdout.strip()
    return head or None


def _cache_is_stale(repo_root: str) -> bool:
    """True when the orientation cache should be regenerated: HEAD has moved past the
    cache's recorded generation point, OR freshness cannot be verified at all (missing
    cache file, missing/empty `git_head_at_generation`, or an unresolvable current
    HEAD). Cannot-verify defaults to stale on purpose — the spinoff's own acceptance
    criterion is a cache that PROVES freshness, not one that is merely un-disproven
    stale; an empty/missing cache-head field must not match everything by accident of
    `str.startswith("")` being trivially true.
    """
    cache_head = _read_cache_head(repo_root)
    if not cache_head:
        return True
    current_head = _read_current_head(repo_root)
    if not current_head:
        return True
    return not current_head.startswith(cache_head)


def _resolve_regenerator_path(claude_klabauter_root: Optional[str]) -> Optional[str]:
    """Preferred path: the settings-home forwarder. Fallback: the claude-klabauter-resident CLI
    directly, using the SAME resolved `claude_klabauter_root` this module's own trampoline logic
    in `main()` already obtained — no second `resolve_claude_klabauter_root()` call.
    """
    forwarder = _settings_home() / "bin" / "regenerate-orientation-cache"
    if forwarder.is_file():
        return str(forwarder)
    if claude_klabauter_root:
        fallback = os.path.join(claude_klabauter_root, "coordinator", "bin", "regenerate-orientation-cache")
        if os.path.isfile(fallback):
            return fallback
    return None


def _invoke_regenerator(cmd: list, repo_root: str, timeout: float) -> subprocess.CompletedProcess:
    """Spawn the regenerator CLI via `Popen` (not the `subprocess.run` convenience
    wrapper) so a timeout can kill the child's WHOLE process group, not just the
    immediate child. `subprocess.run`'s own `TimeoutExpired` handling only ever calls
    `Popen.kill()` on the direct child it started internally, and never exposes that
    `Popen` object to the caller — so a grandchild the regenerator itself spawned (one
    of its ~10 internal git subprocess calls, module docstring) can survive as an
    orphan reparented off this hook's exit. `start_new_session=True` makes the child
    its own process-group leader on POSIX so `os.killpg` can reach the whole tree; it
    is guarded by `_CAN_KILL_PROCESS_GROUP` because Windows has no equivalent concept
    reachable from here, and this is layered on top of (not a replacement for) the
    existing `_NO_WINDOW` creationflag handling, which stays untouched.

    `cmd` is passed in fully-formed by the caller (which owns the `sys.executable`
    prefix decision) so this stays a thin, directly-monkeypatchable spawn seam rather
    than a place that also decides what to run.
    """
    popen_kwargs: dict = dict(
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=_NO_WINDOW,
    )
    if _CAN_KILL_PROCESS_GROUP:
        popen_kwargs["start_new_session"] = True

    process = subprocess.Popen(cmd, **popen_kwargs)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        if _CAN_KILL_PROCESS_GROUP:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except OSError:
                process.kill()
        else:
            process.kill()
        # Reap the now-killed process so it doesn't linger as a zombie; the
        # original TimeoutExpired is what callers below actually handle.
        process.communicate()
        raise
    return subprocess.CompletedProcess(cmd, process.returncode, stdout, stderr)


def _selfheal_orientation_cache(claude_klabauter_root: Optional[str]) -> None:
    """Best-effort: regenerate `state/orientation_cache.md` when stale. Never raises,
    never affects this hook's exit code or stdout contract — see module docstring's
    "Orientation-cache self-heal" section for the full failure-handling contract.
    """
    if os.environ.get("COORDINATOR_ORIENTATION_SELFHEAL_OFF"):
        return

    repo_root = _resolve_this_repo_root()
    if not repo_root:
        print(
            "sweep-boot.py: WARN: repo root unresolved — skipping orientation "
            "cache self-heal",
            file=sys.stderr,
        )
        _record_failure(claude_klabauter_root, "repo root unresolved — skipping orientation cache self-heal")
        return

    try:
        stale = _cache_is_stale(repo_root)
    except Exception as exc:
        print(
            f"sweep-boot.py: WARN: orientation cache staleness check raised — {exc}",
            file=sys.stderr,
        )
        _record_failure(claude_klabauter_root, f"orientation cache staleness check raised — {exc}")
        return

    if not stale:
        return

    regenerator = _resolve_regenerator_path(claude_klabauter_root)
    if not regenerator:
        print(
            "sweep-boot.py: WARN: orientation cache stale but no regenerator "
            "CLI resolved (forwarder and claude-klabauter fallback both missing) -- "
            "skipping self-heal",
            file=sys.stderr,
        )
        _record_failure(
            claude_klabauter_root,
            "orientation cache stale but no regenerator CLI resolved",
        )
        return

    # Thundering-herd mitigation: ~14 sessions can boot near-simultaneously and each
    # independently decides the cache is stale, so spread invocations across a
    # jitter window before racing the regenerator's own lock (see
    # _SELFHEAL_JITTER_MAX_SECONDS's docstring-adjacent comment for the numbers this
    # bound is sized against). Harmless here: this leg runs off the async,
    # stdout-discarded SessionStart path, never the sync zero-spawn boot hot path.
    jitter_seconds = random.uniform(0.0, _SELFHEAL_JITTER_MAX_SECONDS)
    if jitter_seconds:
        time.sleep(jitter_seconds)

    # sys.executable prefix is mandatory, not cosmetic: the regenerator CLI is an
    # extensionless naked-Python script (shebang, no .exe/.bat wrapper). A bare-path
    # exec works on POSIX via the shebang + exec bit, but Windows' CreateProcess
    # (what subprocess/Popen use under shell=False) does not consult shebang lines
    # and cannot launch an extensionless script at all without this prefix — do not
    # "simplify" this back to a bare path.
    cmd = [sys.executable, regenerator, "--invoker", "sweep-boot"]

    try:
        result = _invoke_regenerator(cmd, repo_root, timeout=60.0)
    except subprocess.TimeoutExpired:
        # 60s is generous headroom over the ~10-spawn full regen this CLI pays
        # (module docstring; ~10 git subprocesses, each well under a second on a
        # warm repo) while still bounding a hung child so it cannot leave an
        # orphan process attached past this hook's own lifetime.
        print(
            "sweep-boot.py: WARN: orientation cache regenerator timed out after 60s",
            file=sys.stderr,
        )
        _record_failure(claude_klabauter_root, "orientation cache regenerator timed out after 60s")
        return
    except OSError as exc:
        print(
            f"sweep-boot.py: WARN: failed to exec orientation cache regenerator — {exc}",
            file=sys.stderr,
        )
        _record_failure(claude_klabauter_root, f"failed to exec orientation cache regenerator — {exc}")
        return

    if result.returncode != 0:
        print(
            f"sweep-boot.py: WARN: orientation cache regenerator exited "
            f"{result.returncode} — cache stays stale until next self-heal "
            f"({_LOCK_CONTENTION_NOTE})",
            file=sys.stderr,
        )
        _record_failure(
            claude_klabauter_root,
            f"orientation cache regenerator exited {result.returncode} ({_LOCK_CONTENTION_NOTE})",
            exit_code=result.returncode,
        )


def _run_boot_sweep(root: Optional[str]) -> None:
    """The original single-job body of this trampoline (module docstring, pre-2026-07-29):
    resolve claude-klabauter, exec its `sweep-boot.py`, fail-open + fail-loud-to-log on every leg.
    Extracted verbatim out of `main()` so the orientation self-heal leg below can run
    unconditionally afterward — the two jobs are independent (module docstring's
    "Orientation-cache self-heal" section) and neither leg's early-return may skip the
    other.
    """
    if not root:
        print(
            "sweep-boot.py: WARN: claude-klabauter root unresolved — skipping boot sweep",
            file=sys.stderr,
        )
        _record_failure(None, "claude-klabauter root unresolved — skipping boot sweep")
        print("0")
        return

    target = os.path.join(root, "coordinator", "bin", "sweep-boot.py")
    if not os.path.isfile(target):
        print(
            f"sweep-boot.py: WARN: '{target}' missing -- stale/incomplete "
            "claude-klabauter clone, skipping boot sweep",
            file=sys.stderr,
        )
        _record_failure(
            root,
            f"'{target}' does not exist — stale or incomplete claude-klabauter clone",
        )
        print("0")
        return

    try:
        result = subprocess.run(
            [sys.executable, target] + sys.argv[1:],
            creationflags=_NO_WINDOW,
        )
    except OSError as exc:
        print(
            f"sweep-boot.py: WARN: failed to exec claude-klabauter sweep-boot.py — {exc}",
            file=sys.stderr,
        )
        _record_failure(root, f"failed to exec claude-klabauter sweep-boot.py — {exc}")
        print("0")
        return

    if result.returncode != 0:
        # Review: code-reviewer — fail-open per this module's own stated
        # contract (docstring above): a completed-but-nonzero child run must
        # not wedge SessionStart boot. Surface the real exit code as a
        # diagnostic, but never forward it.
        print(
            f"sweep-boot.py: WARN: claude-klabauter sweep-boot.py exited "
            f"{result.returncode} — boot proceeds anyway (fail-open)",
            file=sys.stderr,
        )
        _record_failure(
            root,
            f"claude-klabauter sweep-boot.py exited {result.returncode}",
            exit_code=result.returncode,
        )


def _load_global_doctrine_mirror_module():
    """Best-effort in-process import of `derive-global-doctrine-live-copy.py`
    (sibling script, same directory). Its filename is hyphenated, so it is
    not `import`-able by bare module name -- resolved via
    `importlib.util.spec_from_file_location` from `Path(__file__)`, matching
    the pattern this repo's own hook tests already use for the same reason
    (e.g. `coordinator/tests/test_sweep_boot_orientation_selfheal.py`'s
    `_load_module` helper, and the sibling hook-scripts test suite's own
    equivalent).

    Returns None on ANY import failure (missing sibling file, syntax error,
    partial deploy) -- the caller below treats that identically to "nothing
    to do", per this leg's own never-break-the-sweep contract.
    """
    hook_path = Path(__file__).resolve().parent / "derive-global-doctrine-live-copy.py"
    spec = importlib.util.spec_from_file_location(
        "global_doctrine_mirror_inline", hook_path
    )
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        # Review: code-reviewer -- Finding 2: exec_module() can raise
        # FileNotFoundError (missing sibling) or SyntaxError (broken sibling),
        # neither of which the spec/loader check above catches. Contain them
        # here so the docstring's "returns None on ANY import failure" claim
        # is actually true, rather than relying implicitly on the caller's
        # own try/except.
        spec.loader.exec_module(module)
    except Exception:
        return None
    return module


def _derive_global_doctrine_mirror() -> None:
    """Best-effort, in-process SessionStart re-derivation of the global-doctrine
    live copy -- see module docstring's "Global-doctrine mirror fold-in" section
    for why this lives here instead of its own `hooks.json` entry, and for the
    failure-handling contract this function exists to enforce.

    Deliberately does NOT go through the sibling module's own `main()` (which
    parses a JSON stdin payload to decide SessionStart-vs-Write|Edit mode) --
    this call site already KNOWS it is the SessionStart case, so it drives the
    sibling module's own building-block functions directly: the OSS-clobber
    dev-repo gate first (load-bearing, not defense-in-depth, exactly as that
    module's own docstring requires), then the tracked-source existence check,
    then the shared read/compare/write path. Any exception anywhere in that
    chain -- including the import itself -- is swallowed here and reported to
    stderr only; it must never propagate past this function.

    Review: code-reviewer -- Finding 6: the containment scope here is
    `Exception` subclasses only, not `BaseException` -- a `SystemExit` or
    `KeyboardInterrupt` raised anywhere in this chain would still propagate.
    No path in this module currently raises either, so this is not
    exploitable today; deliberately not widened to `except BaseException`,
    since swallowing those at a boot hook would be worse than the gap it
    closes.
    """
    try:
        module = _load_global_doctrine_mirror_module()
        if module is None:
            return
        if not module._is_dev_repo():
            return
        tracked = module._tracked_path()
        if tracked.is_file():
            module._derive_live_copy(tracked, module._live_path())
        for rules_tracked in module._tracked_rules_files():
            rules_live = module._live_rules_dir() / rules_tracked.name
            module._derive_live_copy(rules_tracked, rules_live)
    except Exception as exc:
        print(
            f"sweep-boot.py: WARN: global-doctrine mirror derivation raised — {exc}",
            file=sys.stderr,
        )


def main() -> int:
    root = resolve_claude_klabauter_root()
    _run_boot_sweep(root)
    _selfheal_orientation_cache(root)
    _derive_global_doctrine_mirror()
    return 0


if __name__ == "__main__":
    sys.exit(main())
