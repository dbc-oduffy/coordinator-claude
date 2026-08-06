#!/usr/bin/env python3
"""SessionStart hook: inject project orientation documents into context.

Naked-Python direct port of the former bash SessionStart hook, per the W4a-sessionstart
port recipe (scratch/subagent-sandbox/bash-to-python-migration/
W4a-sessionstart-recipe.md § 2.2). Convention-based discovery — reads what
exists, skips what doesn't.

Disposition (recipe § 2.2): naked-Python direct port. **No claude-klabauter op is
authored or called by this hook** — the boot-time `session.boot_sweep` /
`session.reap` claude-klabauter ops are NOT invoked here (this hook's zero-subprocess
boot mandate below forbids a cc_invoke claude-klabauter spawn on the boot path). Those
ops were historically driven by the separate `session-init.py` SessionStart
hook (deleted in the 2026-07-15 full-kill); `session.boot_sweep` is now
carried by its own async `bin/sweep-boot.py` SessionStart hook
(`hooks/hooks.json`, matcher `startup|compact`), whose archival side effect
imposes zero first-token latency because async SessionStart stdout is
discarded rather than injected. The bash predecessor of this hook never routed
through a claude-klabauter op on disk (confirmed:
no `session.orientation`-shaped op exists in `coordinator_core/ops/` on either
repo as of this port). Its only nexus to claude-klabauter at all is the rare case where
the current repo IS the coordinator meta-repo (`~/.claude`) — state-root then
redirects to claude-klabauter's `state/` dir, resolved via the fast local `.claude-klabauter-root`
pointer-FILE read only (AC8, recipe § 4), mirroring `session-init.py`'s
`_resolve_claude_klabauter_root_fast()` shape and `preuse-write-dispatch.py`'s
`_resolve_claude_klabauter_root()` "no bash, no probe chain" philosophy — no
env/registry/marker ladder, no subprocess re-spawn. The common case (any
sibling repo, e.g. DoE-claude itself) never touches claude-klabauter at all: state root
is a direct `<repo_root>/state` join, zero subprocess.

AC8 boot-race hook (recipe § 4): this hook and `session-init.py` are the ONLY
two SessionStart hooks whose stdout composes the FIRST-boot `additionalContext`
(`SessionStart:startup`, sync, per `hooks.json`). Latency here is boot latency.

Flags:
  --lightweight   THE production boot path — the SessionStart hook
                   registration in hooks.json always passes this flag; no
                   other caller exists (repo-wide grep, 2026-07-15). Skips
                   heavy operations (scc, git log, full-mode pointer docs)
                   AND, as of the 2026-07-15 PM directive below, skips ALL
                   subprocess spawns (git AND bash) on the common
                   cache-present path.

Boot fast-path, ZERO subprocess (PM directive 2026-07-15, tightened same
day): every subprocess spawn costs ~200-500ms on Windows, and this hook's
stdout gates first-token-to-context on every SessionStart (AC8 below) — so
the `--lightweight` boot path must reach zero process spawns of any kind on
its common (cache-present) branch. Concretely, relative to the pre-2026-07-15
port, THREE things moved off the boot path:
  1. `resolve_repo_root()`'s `git rev-parse --show-toplevel` → replaced by
     `resolve_repo_root_boot()` (env var `CLAUDE_PROJECT_DIR`, else a pure-
     Python upward walk for a `.git` marker).
  2. `handle_cache_present()`'s staleness banner — `git cat-file -t
     <cache_head>`, a `git diff --quiet <cache_head>..HEAD -- <pathspecs>`,
     and on a stale hit a second `git diff --name-only` — replaced by
     `handle_cache_present_boot()`, a pure read-and-echo of
     `orientation_cache.md` with no staleness check at all. Staleness
     detection is deferred to `/workday-start`, which unconditionally
     regenerates the cache each morning (stronger than a stale-banner: the
     cache becomes FRESH, not just flagged).
  3. `resolve_state_root()`'s rare meta-repo (`~/.claude`) fail-safe
     bash spawn into the former shell `coordinator-state-root` resolver
     (now `claude-klabauter coordinator/lib/coordinator-state-root.py`) — skipped on
     `boot=True` (see that function's docstring); non-boot callers keep it.
  4. `lightweight_branch()`'s cache-ABSENT fallback banner also dropped its
     `git rev-parse --abbrev-ref HEAD` call, reading `.git/HEAD` directly
     instead (`_read_current_branch_boot()`) — this branch is rare (fires
     only when no orientation cache exists yet) but still reachable on the
     `--lightweight` boot invocation, so it's in scope for the same
     zero-spawn mandate.
The two stat()-based staleness banners (`repomap_staleness_banner`,
`exec_summary_staleness_banner`) were ALREADY zero-subprocess (`Path.stat()`
mtime + `shutil.which`, no git/bash) and are kept as-is — near-free, and
dropping them would lose the repomap/exec-summary freshness nudge for no
boot-latency benefit.

Ordering (bash-oracle parity, restored per B-F4 review finding, adapted for
the boot fast-path above): the two staleness banners are emitted first
(matches the oracle — they run on every session path, cache present or
not), then the cache-present check, THEN the --lightweight gate as a
fallback only when no cache exists. An earlier draft of this port checked
--lightweight before opening/diffing the cache file, which meant
`--lightweight` fired even when a warm `orientation_cache.md` was present —
diverging from the oracle, whose cache-present block ALWAYS short-circuited
before reaching the lightweight check. That divergence has been removed;
see `lightweight_branch()`'s docstring for detail. The full-mode
(non-`--lightweight`) legacy path in `main()` is UNCHANGED — it still uses
`resolve_repo_root()`/`handle_cache_present()`'s git-verified staleness
banner; there is currently no production caller of that path (see Flags
above), but it is retained for direct/manual/debug invocation.

Windows stdout byte-parity (B-F3 review finding): every banner line is
written via `sys.stdout.buffer.write(text.encode("utf-8"))`, never
`print()`/`sys.stdout.write()` — Windows text-mode stdout silently rewrites
LF to CRLF, which would diverge byte-for-byte from the bash oracle's
LF-only output (golden-diff acceptance criterion). Mirrors the convention
in `ue-knowledge-distrust.py` (~142-147).

Contract: SessionStart hooks MUST exit 0 unconditionally (harness contract).
Any resolution/import error along non-essential paths degrades gracefully
(skips that section) rather than raising.
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Paths: this file is at <plugin_root>/hooks/scripts/project-orientation.py
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = Path(__file__).resolve().parent
_HOOKS_DIR = _SCRIPTS_DIR.parent
_PLUGIN_ROOT = _HOOKS_DIR.parent  # <plugin_root>/coordinator
_BIN_DIR = _PLUGIN_ROOT / "bin"

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _run(cmd: list, cwd: Optional[Path] = None, timeout: float = 5.0) -> subprocess.CompletedProcess:
    """Best-effort subprocess run; never raises — mirrors `... >/dev/null 2>&1 || true`.

    Mirrors session-init.py's `_run()` exactly (same CREATE_NO_WINDOW flag —
    no bare console-subprocess popup on Windows under the headless Bash-tool
    parent; the canonical fix is creationflags=CREATE_NO_WINDOW at the Python
    spawn site — see docs/wiki/windows-process-spawn-and-console.md §2).
    """
    try:
        return subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=_NO_WINDOW,
        )
    except Exception:
        return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="")


def _read_stdin(timeout: float = 2.0) -> str:
    """Bounded stdin read -- mirrors the bash oracle's `timeout 2 cat` hang
    guard (Windows Git-Bash stdin can block indefinitely otherwise). Ported
    verbatim from runtime-tripwire-stop-watcher.py::_read_stdin() (B-F2
    review finding — a bare `sys.stdin.read()` has no timeout and can hang
    this SessionStart hook indefinitely on Windows)."""
    box = {"data": ""}

    def _read() -> None:
        try:
            box["data"] = sys.stdin.read()
        except Exception:
            box["data"] = ""

    t = threading.Thread(target=_read, daemon=True)
    t.start()
    t.join(timeout)
    return box["data"]


def _w(text: str) -> None:
    """Write raw UTF-8 bytes to stdout -- NOT print()/sys.stdout.write().

    On Windows, text-mode stdout translates LF to CRLF, which would diverge
    byte-for-byte from the bash oracle's LF-only output (golden-diff parity
    requirement — B-F3 review finding). Mirrors ue-knowledge-distrust.py's
    convention (~142-147). Callers pass their own trailing "\\n" where the
    oracle's `echo` would add one; `handle_cache_present`'s raw `cache_text`
    re-emission passes no added newline, matching the oracle's `cat "$CACHE"`.
    """
    sys.stdout.buffer.write(text.encode("utf-8"))


# ---------------------------------------------------------------------------
# claude-klabauter-root / state-root resolution (AC8: fast local path, no probe chain)
# Mirrors session-init.py lines ~122-130, 419-427 verbatim (same shape,
# duplicated locally rather than imported — matches the sibling AC8 hook so
# both stubs degrade identically if `_claude_home.py` is ever unavailable).
# ---------------------------------------------------------------------------


def _claude_home() -> Path:
    # Review: coordinator:code-reviewer — Path.home() (not os.path.expanduser)
    # fails loud (RuntimeError) instead of silently returning the literal "~"
    # when every home rung is unset. Both call sites below degrade per this
    # hook's fail-open contract rather than letting the RuntimeError escape.
    v = os.environ.get("CLAUDE_HOME")
    if v:
        return Path(v)
    return Path.home()


def _settings_home() -> Path:
    v = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if v:
        return Path(v)
    return _claude_home() / ".coordinator-claude-settings"


def _resolve_claude_klabauter_root_native() -> Optional[str]:
    """Resolve the claude-klabauter repo root WITHOUT spawning bash/subprocess — mirrors
    `preuse-write-dispatch.py::_resolve_claude_klabauter_root()` (the Rung-1.5 pattern
    `cc_invoke.py` already establishes). Delegates to the shared
    `_engine_root.resolve_claude_klabauter_root()` seam (explicit env → machine-local
    registry, `registry.local.toml` checked before the tracked `registry.toml`
    baseline, under settings-home → sibling-dir marker), fail to None — never
    raises.

    Distinct from `_resolve_claude_klabauter_root_fast()` above: that one is a
    pointer-FILE read for the AC8 hot orientation-cache path; this one calls
    the fuller (still zero-subprocess) seam used ONLY by the rare meta-repo
    state-root fail-safe below, replacing what used to be a
    bash spawn into the shell `coordinator-state-root` resolver.
    """
    try:
        _hooks_dir = str(Path(__file__).resolve().parent)
        if _hooks_dir not in sys.path:
            sys.path.insert(0, _hooks_dir)
        from _engine_root import resolve_claude_klabauter_root as _seam_resolve

        return _seam_resolve()
    except Exception:
        # Defensive fallback -- a hook script copied/deployed WITHOUT its
        # sibling _engine_root.py (e.g. an isolated test harness, or a
        # partial deploy) must still fail-open rather than crash on import.
        return None


def _resolve_claude_klabauter_root_fast() -> Optional[str]:
    """Cheap claude-klabauter-root resolution — a pointer-FILE read only.

    Mirrors `session-init.py::_resolve_claude_klabauter_root_fast()` and
    `preuse-write-dispatch.py::_resolve_claude_klabauter_root()` rung 1.5 — deliberately
    does NOT walk the full env/registry/marker ladder or spawn any
    subprocess/bash. `session-init.py` runs BEFORE this hook on every
    SessionStart:startup registration (hooks.json row 2 ordering, recipe § 5),
    and self-heals this same pointer file if absent — so by the time this
    hook runs the pointer already exists in steady state; this stub does NOT
    duplicate that self-heal responsibility (single-owner, recipe § 2.1 #2b).
    """
    try:
        ptr = _settings_home() / "machine-local" / ".claude-klabauter-root"
        val = ptr.read_text(encoding="utf-8").strip()
    except (OSError, RuntimeError):
        # RuntimeError: home directory unresolvable (no USERPROFILE/HOME) --
        # fail-open, matching this stub's existing OSError degrade above.
        return None
    if val and Path(val).is_dir():
        return val
    return None


def resolve_repo_root() -> Optional[str]:
    proc = _run(["git", "rev-parse", "--show-toplevel"])
    if proc.returncode != 0:
        return None
    root = proc.stdout.strip()
    return root or None


def resolve_repo_root_boot() -> Optional[str]:
    """Subprocess-free repo-root resolution for the boot/lightweight fast-path.

    Boot latency directly gates first-token-to-context (module docstring,
    AC8) — `resolve_repo_root()`'s `git rev-parse --show-toplevel` spawn is
    one of the ~3 git subprocess calls this hook used to pay on EVERY
    SessionStart, even on the common cache-present path where nothing
    downstream needs a verified HEAD. This resolves the same value two ways,
    cheapest first, with zero process spawn either way:

    1. `CLAUDE_PROJECT_DIR` env var, if set and points at a real directory —
       the harness-provided project root (same convention already used by
       `plan-persistence-check.py`); trusted as-is, no `.git` re-verification
       (a hook running under a harness that sets this var is running inside
       a real project boot, not a probe).
    2. Pure-Python upward walk from `Path.cwd()` looking for a `.git` entry
       (directory for a normal clone, FILE for a worktree — `.exists()`
       covers both) — mirrors what `git rev-parse --show-toplevel` does
       internally, without paying for the subprocess spawn.

    Returns None (matching `resolve_repo_root()`'s fail shape) if neither
    resolves — callers treat a None repo_root as "operate relative to cwd",
    same fail-open contract as the git-based resolver.
    """
    env_root = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_root:
        p = Path(env_root)
        if p.is_dir():
            return str(p)

    try:
        cwd = Path.cwd()
    except Exception:
        return None

    for candidate in (cwd, *cwd.parents):
        try:
            if (candidate / ".git").exists():
                return str(candidate)
        except Exception:
            continue
    return None


def _canon(path: str) -> str:
    try:
        return str(Path(path).resolve())
    except Exception:
        return path


def resolve_state_root(repo_root: Optional[str], boot: bool = False) -> str:
    """Port of `coordinator_state_root` (Rule 5, default/no --central).

    Common case (any sibling repo, e.g. DoE-claude itself): zero-subprocess
    `<repo_root>/state` join — never touches claude-klabauter. Only when the current
    repo root IS the coordinator meta-repo (`~/.claude`) does this redirect
    to claude-klabauter's `state/` dir via the fast pointer-file read above — the rare
    branch the retired `session-init.py`'s own `coordinator_state_root` bash function
    also took. This is a deliberate zero-bash-subprocess IMPROVEMENT over
    `session-init.py::_state_root()` (which used to shell out to the
    shell `coordinator-state-root` resolver);
    as of the resolver-repoint pass (W3a), that fallback calls
    `coordinator_core.state_root.coordinator_state_root()` NATIVELY
    in-process instead — no bash, no `python3 -m` re-spawn — mirroring the
    Rung-1.5 pattern `preuse-write-dispatch.py::_resolve_claude_klabauter_root()` /
    `cc_invoke.py` already establish for claude-klabauter-root resolution. That native
    call is preserved here ONLY on the rare meta-repo branch, as a safety
    net if the fast pointer read comes up empty (e.g. genuinely first-ever
    boot before session-init's self-heal has run — should not happen given
    hook ordering, but fail-safe beats fail-closed on a boot-race hook) —
    EXCEPT on the boot fast-path (`boot=True`, i.e. called from `main()`'s
    `--lightweight` branch), where the PM directive (2026-07-15, tightened)
    is ZERO subprocess spawns of ANY kind, git or bash — the native call's
    own Rule-5 internals still spawn one `git rev-parse` subprocess, which
    is exactly the Windows-latency cost that directive targets. On
    `boot=True` this rare-branch fail-safe is skipped entirely; the fallback
    degrades to the plain `<repo_root>/state` join below instead of calling
    the native resolver. This only changes behavior in the doubly-rare case
    of (a) current repo root IS `~/.claude` AND (b) the claude-klabauter pointer-file
    fast read came up empty — non-boot callers (full/legacy mode) still get
    the native-resolver fail-safe.
    """
    if not repo_root:
        return str(Path(".") / "state")

    try:
        meta_dir = _claude_home() / ".claude"
        is_meta = _canon(repo_root) == _canon(str(meta_dir))
    except Exception:
        is_meta = False

    if not is_meta:
        return str(Path(repo_root) / "state")

    # Rare branch: current repo root IS ~/.claude — state lives in claude-klabauter.
    claude_klabauter_root = _resolve_claude_klabauter_root_fast()
    if claude_klabauter_root:
        return str(Path(claude_klabauter_root) / "state")

    if boot:
        # Boot fast-path: no bash-source fallback (would spawn a subprocess).
        return str(Path(repo_root) / "state")

    # Fail-safe fallback only (should not normally fire — see docstring):
    # call coordinator_core.state_root natively, in-process — no bash spawn.
    # The oracle bash spawn ran with `cwd=Path(repo_root)` (its internal
    # `git rev-parse --show-toplevel` resolved relative to repo_root, not
    # this hook process's actual cwd); coordinator_state_root() has no cwd
    # parameter — it always resolves against the CALLING process's cwd — so
    # a bounded chdir here preserves that contract instead of silently
    # resolving against whatever directory launched this hook.
    try:
        claude_klabauter_native_root = _resolve_claude_klabauter_root_native()
        if claude_klabauter_native_root:
            if claude_klabauter_native_root not in sys.path:
                sys.path.insert(0, claude_klabauter_native_root)
            from coordinator_core.state_root import (  # noqa: PLC0415
                StateRootError,
                coordinator_state_root as _native_coordinator_state_root,
            )

            prev_cwd = os.getcwd()
            out = ""
            try:
                os.chdir(repo_root)
                out = _native_coordinator_state_root()
            except (StateRootError, OSError):
                out = ""
            finally:
                try:
                    os.chdir(prev_cwd)
                except OSError:
                    pass
            if out:
                return out
    except Exception:
        pass

    return str(Path(repo_root) / "state")


# ---------------------------------------------------------------------------
# Staleness banners (repo map / exec summary)
# ---------------------------------------------------------------------------


def _resolve_generator(name: str, repo_root: Optional[str]) -> Optional[str]:
    """Locate a repomap/exec-summary generator CLI.

    Rung order: (1) this repo's own `coordinator/bin/<name>` — the pre-migration
    home; (2) `$PATH`; (3) `<repo_root>/bin/<name>`; (4) the migrated home —
    `<claude_klabauter_root>/coordinator/bin/<name>`, resolved zero-subprocess via
    `_resolve_claude_klabauter_root_native()`. Rung 4 exists because `generate-repomap.py`
    and `generate-exec-summary.py` were both migrated wholesale to
    claude-klabauter (commit b644d5a9) and no longer live under rung 1 in DoE-claude
    — without this rung the staleness banners below fail open (silently never
    fire) on every machine with a resolvable sibling checkout, which is worse
    than an error because nothing surfaces the gap. Returns None (loud-enough
    degrade is the CALLER's job — see `repomap_staleness_banner` /
    `exec_summary_staleness_banner`, which suppress the banner but the
    generator-unresolvable state is itself diagnosable by grepping for this
    function) when no rung resolves.

    Negative-spec: does NOT hardcode an absolute sibling path — rung 4 delegates
    entirely to `_resolve_claude_klabauter_root_native()`'s env/registry/marker ladder, so
    this degrades gracefully (returns None) on a machine with no claude-klabauter
    checkout, rather than crashing.
    """
    candidate = _BIN_DIR / name
    if candidate.is_file():
        return str(candidate)
    found = shutil.which(name)
    if found:
        return found
    if repo_root:
        candidate2 = Path(repo_root) / "bin" / name
        if candidate2.is_file():
            return str(candidate2)
    claude_klabauter_root = _resolve_claude_klabauter_root_native()
    if claude_klabauter_root:
        candidate3 = Path(claude_klabauter_root) / "coordinator" / "bin" / name
        if candidate3.is_file():
            return str(candidate3)
    return None


def _mtime_epoch(path: Path) -> Optional[int]:
    try:
        return int(path.stat().st_mtime)
    except Exception:
        return None


def repomap_staleness_banner(repo_root: Optional[str]) -> None:
    if os.environ.get("COORDINATOR_REPOMAP_STATUS_OFF"):
        print(
            "[coordinator] repomap staleness banner: disabled via "
            "COORDINATOR_REPOMAP_STATUS_OFF",
            file=sys.stderr,
        )
        return

    rm_repomap = Path(repo_root or ".") / ".claude" / "repomap.md"
    if not rm_repomap.is_file():
        return
    epoch = _mtime_epoch(rm_repomap)
    if epoch is None:
        return
    age_hours = (int(time.time()) - epoch) // 3600
    # Review: code-reviewer — _resolve_generator() is only worth its
    # is_file()/PATH/registry-read cost when a banner is actually owed;
    # gate it behind the cheap existence check above rather than paying it
    # unconditionally on every --lightweight boot.
    rm_gen = _resolve_generator("generate-repomap.py", repo_root)
    if not rm_gen:
        if age_hours >= 24:
            # The banner is suppressed (no generate-repomap.py CLI to point at),
            # but that suppression must not be SILENT — surface it to stderr so
            # the gap is diagnosable rather than reproducing the original bug
            # (generator migrated to claude-klabauter, banner quietly never fires).
            print(
                f"[coordinator] repomap staleness banner: repo map is "
                f"{age_hours}h old but generate-repomap.py is unresolvable "
                "(checked coordinator/bin/, $PATH, <repo>/bin/, and the "
                "claude-klabauter sibling) — see _resolve_generator() in "
                "project-orientation.py",
                file=sys.stderr,
            )
        return
    if age_hours >= 168:
        _w("\n")
        _w(
            f"── ⚠ Repo map VERY STALE: {age_hours}h old — regenerate: "
            f"{rm_gen} (or /update-docs) ──\n"
        )
    elif age_hours >= 24:
        _w(
            f"── Repo map stale: {age_hours}h old — refresh via "
            f"/update-docs or {rm_gen} ──\n"
        )


def exec_summary_staleness_banner(repo_root: Optional[str]) -> None:
    if os.environ.get("COORDINATOR_EXECSUMMARY_STATUS_OFF"):
        print(
            "[coordinator] exec-summary staleness banner: disabled via "
            "COORDINATOR_EXECSUMMARY_STATUS_OFF",
            file=sys.stderr,
        )
        return

    es_doc = Path(repo_root or ".") / "docs" / "exec-summary.md"
    if not es_doc.is_file():
        return
    epoch = _mtime_epoch(es_doc)
    if epoch is None:
        return
    age_hours = (int(time.time()) - epoch) // 3600
    # Review: code-reviewer — same hot-path gating rationale as
    # repomap_staleness_banner above.
    es_gen = _resolve_generator("generate-exec-summary.py", repo_root)
    if not es_gen:
        if age_hours >= 24:
            # Same diagnosable-suppression rationale as repomap_staleness_banner
            # above — do not vanish silently when the generator is unresolvable.
            print(
                f"[coordinator] exec-summary staleness banner: exec-summary is "
                f"{age_hours}h old but generate-exec-summary.py is unresolvable "
                "(checked coordinator/bin/, $PATH, <repo>/bin/, and the "
                "claude-klabauter sibling) — see _resolve_generator() in "
                "project-orientation.py",
                file=sys.stderr,
            )
        return
    if age_hours >= 168:
        _w("\n")
        _w(
            f"── ⚠ Exec-summary VERY STALE: {age_hours}h old — refresh: "
            f"{es_gen} ──\n"
        )
    elif age_hours >= 24:
        _w(
            f"── Exec-summary stale: {age_hours}h old — refresh via "
            f"{es_gen} (or /workweek-start) ──\n"
        )


def engine_resolution_banner() -> None:
    """One line naming WHICH engine this session's hooks will execute.

    DR-129: consumer engine resolution answers "which engine do I execute",
    and until this banner existed the answer was invisible — a consumer running
    a half-edited engine saw a guard behaving oddly, indistinguishable from
    that guard behaving correctly. Two days were lost to exactly that on a
    sibling plane. The `live-working-tree` line is the one that pays for
    itself: a live tree is a legitimate answer on a co-development machine,
    but it must be a visible state rather than an invisible default.

    Zero-spawn (this hook's 2026-07-15 boot mandate): delegates to
    `_engine_root.resolve_claude_klabauter_root_with_class`, which is a stat plus at most
    one small file read. Fail-open: any failure emits nothing.

    `unresolved` deliberately says nothing — a machine with no engine at all is
    the pre-existing silent degrade everywhere else in this file, and inventing
    a new boot-time failure mode for it is not this banner's job.

    Negative-spec — the class comes from the resolver, never re-derived here.
    The snapshot's `sha` is deliberately NOT named on this line: the resolver's
    public seam returns `(root, class)`, and re-reading `current.json` here to
    enrich the banner would put a second read on the boot path and a second
    copy of the pointer contract in a consumer. Which CLASS answered is the
    signal DR-129 asked for; which sha is a question for a surface that already
    parses the pointer.
    """
    try:
        _hooks_dir = str(Path(__file__).resolve().parent)
        if _hooks_dir not in sys.path:
            sys.path.insert(0, _hooks_dir)
        from _engine_root import (
            RESOLUTION_LIVE_WORKING_TREE,
            RESOLUTION_RESOLVED_ENGINE,
            resolve_claude_klabauter_root_with_class,
        )

        _root, klass = resolve_claude_klabauter_root_with_class()
    except Exception:
        return

    if klass == RESOLUTION_RESOLVED_ENGINE:
        # Review: code-reviewer — RESOLUTION_RESOLVED_ENGINE now means a
        # published engine mirror, not a committed snapshot.
        _w("── Engine: published engine mirror ──\n")
    elif klass == RESOLUTION_LIVE_WORKING_TREE:
        _w("── Engine: sibling LIVE working tree — uncommitted edits execute ──\n")


def _read_current_full_sha_boot(repo_root: Optional[str]) -> str:
    """Zero-subprocess full-HEAD-SHA resolution for the boot/`--lightweight` fast-path.

    Cost contract (spinoff acceptance criterion — see
    `state/audits/2026-07-29-orientation-cache-boot-facts.md`): the audit's own proposal was one
    `git status --porcelain=v2 --branch` spawn, parsed for the `# branch.oid` line. We do
    better than that on purpose. `git status` scans the ENTIRE working tree to produce that one
    field, which on a large dirty tree is far from free — and this hook's boot-time contract
    (module docstring, PM directive 2026-07-15) is zero spawns of any kind on the common path.
    Instead this reads `.git/HEAD` directly, mirroring `_read_current_branch_boot()`'s shape:

    1. Bare 40-hex-char `.git/HEAD` content → detached HEAD, that string IS the SHA.
    2. `ref: refs/heads/<branch>` → read `<repo_root>/.git/<ref>` for the loose-ref SHA.
    3. Loose ref file absent (ref has been packed) → scan `<repo_root>/.git/packed-refs` for a
       line ending in that ref name and take its leading SHA.

    Returns "" (never raises) on any resolution failure — callers fall back to the ONE-spawn
    `git rev-parse HEAD` in `orientation_cache_staleness_banner()`, never to `git status`.
    """
    if not repo_root:
        return ""
    try:
        head_text = (Path(repo_root) / ".git" / "HEAD").read_text(
            encoding="utf-8", errors="replace"
        ).strip()
    except Exception:
        return ""
    if not head_text:
        return ""

    if not head_text.startswith("ref:"):
        # Detached HEAD: a bare SHA (40 hex chars in a normal SHA-1 repo). Accept anything
        # hex-shaped rather than hard-coding 40 -- forward-tolerant of a SHA-256 repo without
        # this hook needing to know or care which object format is in play.
        candidate = head_text.strip()
        if candidate and all(c in "0123456789abcdefABCDEF" for c in candidate):
            return candidate
        return ""

    ref = head_text.split(":", 1)[1].strip()
    if not ref:
        return ""

    try:
        loose = (Path(repo_root) / ".git" / ref).read_text(
            encoding="utf-8", errors="replace"
        ).strip()
        if loose:
            return loose
    except Exception:
        pass

    # Loose ref file absent -- the ref has been packed (`git pack-refs`). Scan packed-refs for
    # a "<sha> <ref>" line naming this exact ref.
    try:
        packed_text = (Path(repo_root) / ".git" / "packed-refs").read_text(
            encoding="utf-8", errors="replace"
        )
    except Exception:
        return ""
    for line in packed_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("^"):
            continue
        parts = line.split(" ", 1)
        if len(parts) == 2 and parts[1].strip() == ref:
            return parts[0].strip()
    return ""


# Grace window (minutes) between a genuine HEAD drift and this banner actually firing on it.
# Measured on this branch (2026-07-29): 22 commits/hour across ~14 concurrent sessions, median
# gap 29s between commits -- with leg 2's async self-heal regenerating the cache on every boot,
# HEAD has essentially ALWAYS drifted since the cache's `generated_at`, so a bare drift check
# fired on effectively every boot (observed directly: leg 2 regenerated pinned to 16b9bba7e,
# and the very next boot -- HEAD already at d3c285d7e -- re-fired against a cache that was
# genuinely fine). A banner that always fires is read by nobody, which recreates this
# spinoff's own failure by a different route (silent-wrong vs. ignored-because-constant). 30
# minutes is comfortably longer than the self-heal loop's cadence (so a healthy loop stays
# quiet) and comfortably shorter than the failure case this banner exists to catch (a cache
# days old because nothing regenerated it -- age grows unbounded if the loop breaks, so the
# banner returns on its own). Tunable per-repo via COORDINATOR_ORIENTATION_STALENESS_GRACE_MINUTES
# for a quieter/noisier commit cadence without a code change.
_ORIENTATION_STALENESS_GRACE_MINUTES_DEFAULT = 30

_GENERATED_AT_FORMAT = "%Y-%m-%dT%H:%M:%SZ"  # matches the generator's actual on-disk value

# How many recent HEAD positions still count as SMALL drift for grace-window purposes. The grace
# window is age-AND-magnitude, not age-alone: a cache minutes old whose recorded HEAD has fallen
# far behind is exactly the "reader is currently being handed false facts" condition the banner
# exists to end, and on a high-cadence shared tree (several concurrent agents; ~22 commits/hour
# measured here) age alone stops discriminating -- ten commits inside the window is an ordinary
# morning, not a pathological case. Magnitude is resolved zero-spawn from the reflog tail (see
# `_head_drift_is_small_boot`), so this costs no process budget. Tunable per-repo via
# COORDINATOR_ORIENTATION_STALENESS_DRIFT_MAX_ENTRIES.
_ORIENTATION_STALENESS_DRIFT_MAX_ENTRIES_DEFAULT = 5

# Bytes of `.git/logs/HEAD` tail to read. The reflog is append-only and grows without bound on a
# busy tree (2MB+ observed), so this is a bounded seek-to-end read, never a whole-file slurp.
_REFLOG_TAIL_WINDOW_BYTES = 65536


def _orientation_staleness_grace_minutes() -> float:
    raw = os.environ.get("COORDINATOR_ORIENTATION_STALENESS_GRACE_MINUTES")
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return float(_ORIENTATION_STALENESS_GRACE_MINUTES_DEFAULT)


def _orientation_staleness_drift_max_entries() -> int:
    raw = os.environ.get("COORDINATOR_ORIENTATION_STALENESS_DRIFT_MAX_ENTRIES")
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    return int(_ORIENTATION_STALENESS_DRIFT_MAX_ENTRIES_DEFAULT)


def _head_drift_is_small_boot(repo_root: Optional[str], cache_head: str) -> Optional[bool]:
    """Is the cache's recorded HEAD within the last few HEAD positions? Zero subprocess.

    Answers the magnitude half of the grace window without the commit-*count* spawn
    (`git rev-list --count`) the banner's budget declined. The reflog (`.git/logs/HEAD`) is an
    ordered, append-only record of every HEAD position this clone has held, written by git itself
    on commit/checkout/reset/pull -- so "is `cache_head` among the most recent N positions" is a
    pure bounded file read, on the same budget as `_read_current_full_sha_boot()`.

    Reflog depth is a PROXY for commits-behind, not an equality: it also records non-commit HEAD
    moves, so depth >= true commits-behind. The inequality runs in the safe direction for a
    safety banner -- it can only make this fire slightly earlier than a true count would, never
    later, so a large real drift is never mistaken for a small one.

    Returns True (drift is small -- grace may apply), False (drift is large, or the recorded HEAD
    is not in recent history at all -- grace must not apply), or None when the reflog cannot be
    read or carries no usable entries. None means UNKNOWN, and callers fall back to the age-only
    behaviour rather than inventing a magnitude verdict from nothing: a missing reflog (a fresh
    clone, an expired reflog, a worktree layout this read does not understand) must not silently
    convert every drifted cache into a banner.
    """
    if not repo_root or not cache_head:
        return None
    path = Path(repo_root) / ".git" / "logs" / "HEAD"
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > _REFLOG_TAIL_WINDOW_BYTES:
                handle.seek(size - _REFLOG_TAIL_WINDOW_BYTES)
                handle.readline()  # discard the partial line the seek landed mid-way through
            chunk = handle.read()
    except Exception:
        return None

    # Each reflog line is "<old-sha> <new-sha> <who> <when>\t<what>". The NEW sha is the position
    # HEAD moved TO, which is what a cache's `git_head_at_generation` recorded.
    positions = []
    for line in chunk.decode("utf-8", errors="replace").splitlines():
        parts = line.split(" ", 2)
        if len(parts) >= 2 and len(parts[1]) >= len(cache_head):
            positions.append(parts[1])
    if not positions:
        return None

    # De-duplicate consecutive repeats so a burst of non-advancing HEAD moves does not consume
    # the window, then walk backwards from the newest position.
    recent = list(dict.fromkeys(reversed(positions)))
    max_entries = _orientation_staleness_drift_max_entries()
    for depth, sha in enumerate(recent):
        if sha.startswith(cache_head):
            return depth <= max_entries
    return False


def _cache_age_minutes(cache_text: str) -> Optional[float]:
    """Minutes since `generated_at`, or None if the field is absent/unparseable.

    Pure computation over already-in-hand text -- no spawn, no I/O. `generated_at` is written
    by the generator as UTC (`_GENERATED_AT_FORMAT`); parsed naive-then-tagged `tzinfo=utc`
    explicitly rather than left naive, so the subtraction against `datetime.now(timezone.utc)`
    below is an aware-aware comparison -- a naive/aware mismatch here is exactly the kind of
    comparison that raises at runtime (or worse, silently compares wrong) if only one side
    is tagged.
    """
    raw = _extract_cache_field(cache_text, "generated_at")
    if not raw:
        return None
    try:
        parsed = datetime.strptime(raw, _GENERATED_AT_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    delta = datetime.now(timezone.utc) - parsed
    return delta.total_seconds() / 60.0


def _render_age(minutes: float) -> str:
    """Compact age string -- `42s` / `3m` / `2h` / `4d`.

    The ONLY age renderer on this path; `_cache_age_minutes()` above is the only age
    computation. A negative value (cache `generated_at` in the future -- clock skew between
    the writing and reading host) renders `0s` rather than a negative age.
    """
    seconds = minutes * 60.0
    if seconds <= 0:
        return "0s"
    if seconds < 60:
        return f"{int(seconds)}s"
    if minutes < 60:
        return f"{int(minutes)}m"
    hours = minutes / 60.0
    if hours < 24:
        return f"{int(hours)}h"
    return f"{int(hours / 24)}d"


def cache_banner_line(cache_text: Optional[str]) -> str:
    """The `── Orientation (RAM cache) ──` banner, carrying a READ-TIME clock anchor.

    The reading model has no clock: nothing else in its context states the current time, so the
    cache's own `generated_at` is an uninterpretable absolute -- a cache regenerated three
    minutes ago at this session's own boot is indistinguishable from yesterday's. This line
    carries both halves of the fix: the absolute `now` stamp (the model's only clock anchor)
    and the relative age (what makes `generated_at` interpretable). BOTH are computed here, at
    read time -- the cache file cannot know when it will be read, so neither belongs in its
    frontmatter.

    Degrades rather than raising: an absent or unparseable `generated_at` still yields the
    `now` stamp with the age reported unknown, and any unexpected failure falls back to the
    bare banner. This runs on the session-boot path and must never break a session.
    """
    try:
        now = datetime.now(timezone.utc).strftime(_GENERATED_AT_FORMAT)
    except Exception:
        return "── Orientation (RAM cache) ──\n"
    try:
        age = _cache_age_minutes(cache_text) if cache_text else None
    except Exception:
        age = None
    if age is None:
        return f"── Orientation (RAM cache) — age unknown (no parseable generated_at) · now {now} ──\n"
    return f"── Orientation (RAM cache) — regenerated {_render_age(age)} ago · now {now} ──\n"


def orientation_cache_staleness_banner(repo_root: Optional[str], cache_text: Optional[str]) -> None:
    """Boot-time staleness signal for `orientation_cache.md` -- the third banner alongside
    `repomap_staleness_banner` / `exec_summary_staleness_banner`.

    Restores the signal the 2026-07-15 zero-spawn directive removed
    (`handle_cache_present_boot()`'s docstring): a stale cache used to announce itself via a
    git-verified diff; today's boot path re-emits it verbatim with no check at all. See
    `state/handoffs/2026-07-29-orientation-cache-stale-by-construction.md` for the full
    incident (measured 1,575 commits stale, silent).

    Spawn budget: primary resolution is `_read_current_full_sha_boot()`, zero subprocess. Only
    when that pure-Python read fails to produce a SHA does this fall back to a single
    `git rev-parse HEAD` (2.0s timeout) via `_run()` -- never `git status`, whose
    `--porcelain=v2 --branch` form the source audit proposed but which pays a full working-tree
    scan for the one `branch.oid` field this banner needs. This is a deliberate improvement on
    the audit's own costed proposal, not a deviation from it -- see this function's own spawn
    test (`test_orientation_cache_staleness_banner.py`) for the mechanical assertion.

    Comparison is a SHA prefix match: the cache stores `git_head_at_generation` as a short SHA
    (`git rev-parse --short HEAD` at generation time), so `current_full_sha.startswith(cache_head)`
    is the correct freshness test -- an exact-equality check would false-positive-stale on every
    boot. An empty/garbage `cache_head` must NOT match everything (`"".startswith("")` is True in
    Python), so an empty `cache_head` is routed to the UNVERIFIABLE branch below rather than
    ever being compared with `startswith()`.

    Two distinct triggers, two distinct banners -- collapsing them loses information a reader
    needs (PM override, 2026-07-29, reversing this function's original silent-on-unverifiable
    behaviour): **unverifiable** (the `git_head_at_generation` field is absent/empty -- we have
    no evidence either way) fires when `cache_head` is falsy; **stale** (the field is present
    and provably behind current HEAD) fires when it's present but doesn't prefix-match. Silence
    on the unverifiable case would recreate the exact defect this banner exists to close --
    "a cache presents as current when it cannot prove that" is the same failure whether the
    proof is *absent* or *contradicted*. This also matches the full/legacy path's own contract
    (`handle_cache_present()`'s "HEAD unverifiable" branch, several dozen lines above) and keeps
    this boot-time signal consistent with the async self-heal leg, which treats cannot-verify
    the same as stale (regenerates either way).

    Negative-spec -- dirty-tree / `git status` state is NOT part of this check and never will
    be: `state/` on this repo is a shared multi-agent bus (see the handoff above), so
    working-tree state has no meaningful lifetime past a single tool call. Caching or banner-ing
    it here would manufacture exactly the confidently-wrong state this banner exists to end.
    Any consumer needing live dirty-tree state computes it live, at the point of use -- never
    from this hook's boot-time read.

    Not attempted here: an "N commits behind" count. That needs a second spawn
    (`git rev-list --count <cache_head>..HEAD`) this banner's budget does not afford -- do not
    add it casually; naming HEAD drift by SHA + timestamp is enough to point at the remedy.

    Grace window (see `_ORIENTATION_STALENESS_GRACE_MINUTES_DEFAULT` for the measurement): a
    drifted-but-provable cache_head does NOT banner immediately. It only banners once the cache's
    own `generated_at` age exceeds the grace window -- a recently regenerated cache that has
    already drifted a few commits means the self-heal loop is working, and shouting about that is
    noise nobody reads. An unparseable/missing `generated_at` is treated as PAST the grace window
    (unknown age must not buy silence, same principle as the UNVERIFIABLE branch above) -- still
    zero additional spawn, since age comes from a field this function already has in hand. The
    UNVERIFIABLE branch itself is NOT subject to this grace window -- a cache with no
    `git_head_at_generation` at all banners immediately regardless of age.

    Grace is age AND magnitude, not age alone. A young cache buys silence only while its recorded
    HEAD is also still NEAR current HEAD (`_head_drift_is_small_boot`, zero subprocess). Age-only
    grace decouples from the reader's actual experience on a high-cadence shared tree: where
    several agents commit concurrently, ten commits inside the window is an ordinary morning, and
    for all of it the EM reads materially wrong facts with no signal -- which is precisely the
    condition this banner exists to end. "The self-heal loop is working" and "the human is right
    now reading something false" are both true in that window; age-only optimised for the first.
    Magnitude lets them come apart: silent when fresh AND close, banner when far however fresh.
    An UNKNOWN magnitude (no readable reflog) falls back to age-only rather than inventing a
    verdict -- see that helper's own contract.
    """
    if os.environ.get("COORDINATOR_ORIENTATION_STALENESS_OFF"):
        print(
            "[coordinator] orientation-cache staleness banner: disabled via "
            "COORDINATOR_ORIENTATION_STALENESS_OFF",
            file=sys.stderr,
        )
        return

    if not cache_text:
        return

    cache_head = _extract_cache_head(cache_text)

    if not cache_head:
        # Field absent/empty at generation time -- we cannot prove freshness OR staleness.
        # Emit a distinct banner rather than either "STALE" (a claim we can't back) or silence
        # (which would present the cache as current by omission -- see docstring).
        cli = _resolve_generator("regenerate-orientation-cache", repo_root)
        if not cli:
            cli = str(_settings_home() / "bin" / "regenerate-orientation-cache")
        _w("\n")
        _w(
            "── Orientation cache freshness UNVERIFIABLE — refresh: "
            f"{cli} --invoker workday-start ──\n"
        )
        return

    current_sha = _read_current_full_sha_boot(repo_root)
    if not current_sha and repo_root:
        proc = _run(["git", "rev-parse", "HEAD"], cwd=Path(repo_root), timeout=2.0)
        if proc.returncode == 0:
            current_sha = proc.stdout.strip()
    if not current_sha:
        return

    if current_sha.startswith(cache_head):
        return

    age_minutes = _cache_age_minutes(cache_text)
    grace_minutes = _orientation_staleness_grace_minutes()
    if age_minutes is not None and age_minutes < grace_minutes:
        # Drifted, but the cache is young enough that the self-heal loop (leg 2) is doing its
        # job -- see the grace-window docstring paragraph above. Silent, not a bug: this IS the
        # healthy state, distinct from both FRESH (no drift at all) and STALE (drifted past
        # grace, or age unknown).
        #
        # Age alone is not sufficient to earn that silence, though: "the self-heal loop is
        # working" and "the reader is right now being handed false facts" are both true at once
        # on a high-cadence tree, and age-only optimises for the first at the second's expense.
        # Grace therefore requires small drift as well -- an UNKNOWN magnitude (None) keeps the
        # age-only behaviour rather than manufacturing a banner.
        drift_is_small = _head_drift_is_small_boot(repo_root, cache_head)
        if drift_is_small is not False:
            return

    generated_at = _extract_cache_field(cache_text, "generated_at")
    short_head = current_sha[: len(cache_head)]
    cli = _resolve_generator("regenerate-orientation-cache", repo_root)
    if not cli:
        # Even an unresolvable CLI must not silence the banner -- point at the settings-home
        # forwarder path directly (same convention as the memo CLI reference,
        # CLAUDE.md § Cross-repo write discipline) so the remedy is still actionable.
        cli = str(_settings_home() / "bin" / "regenerate-orientation-cache")

    _w("\n")
    _w(
        f"── Orientation cache STALE: {cache_head}→{short_head} "
        f"({generated_at}) — refresh: {cli} --invoker workday-start ──\n"
    )


# ---------------------------------------------------------------------------
# Cache-present branch
# ---------------------------------------------------------------------------

_CACHE_RELEVANT_PATHSPEC_RAW = [
    "plugins/",
    "tasks/health-*.md",
    "docs/architecture/",
    ".github/",
    "CLAUDE.md",
    "DIRECTORY.md",
    "tasks/",
]


def _expand_pathspec(repo_root: str, item: str) -> list:
    if any(ch in item for ch in "*?["):
        matches = sorted(glob.glob(str(Path(repo_root) / item)))
        if matches:
            out = []
            for m in matches:
                try:
                    rel = str(Path(m).relative_to(repo_root)).replace(os.sep, "/")
                except Exception:
                    rel = m
                out.append(rel)
            return out
        return [item]
    return [item]


def _cache_relevant_pathspecs(repo_root: str) -> list:
    out: list = []
    for item in _CACHE_RELEVANT_PATHSPEC_RAW:
        out.extend(_expand_pathspec(repo_root, item))
    return out


def _extract_cache_field(cache_text: str, key: str) -> str:
    """Frontmatter-line scraper shared by every `<key>: <value>` read off the cache text.

    Deliberately line-oriented rather than a YAML parse — the cache frontmatter is a flat,
    single-line-per-field block by construction (schema table,
    `coordinator/pipelines/workday-start-internals.md`), and a full YAML dependency would be
    disproportionate to reading one scalar.
    """
    prefix = f"{key}:"
    for line in cache_text.splitlines():
        if line.startswith(prefix):
            val = line[len(prefix):]
            val = val.strip()
            val = val.strip("\"'")
            val = val.replace(" ", "")
            return val
    return ""


def _extract_cache_head(cache_text: str) -> str:
    return _extract_cache_field(cache_text, "git_head_at_generation")


def _git_cat_file_ok(repo_root: str, obj: str) -> bool:
    proc = _run(["git", "cat-file", "-t", obj], cwd=Path(repo_root))
    return proc.returncode == 0


def handle_cache_present(cache: Path, repo_root: Optional[str]) -> bool:
    """Returns True if handled (caller must stop processing / exit)."""
    if not cache.is_file():
        return False

    cache_text = cache.read_text(encoding="utf-8", errors="replace")
    cache_head = _extract_cache_head(cache_text)

    if cache_head and repo_root and _git_cat_file_ok(repo_root, cache_head):
        pathspecs = _cache_relevant_pathspecs(repo_root)
        diff_quiet = _run(
            ["git", "diff", "--quiet", f"{cache_head}..HEAD", "--", *pathspecs],
            cwd=Path(repo_root),
        )
        # fail-safe: treat as fresh on error, matches bash's `then` no-error path
        fresh = diff_quiet.returncode == 0

        if fresh:
            _w("\n")
            _w("── Orientation (RAM cache, structurally current) ──\n")
            _w(cache_text)
            _w("\n")
            _w("── Orientation: 1 document loaded (from cache) ──\n")
            return True

        changed = ""
        name_only = _run(
            ["git", "diff", "--name-only", f"{cache_head}..HEAD", "--", *pathspecs],
            cwd=Path(repo_root),
        )
        lines = [ln for ln in name_only.stdout.splitlines() if ln]
        if lines:
            changed = lines[0]

        _w("\n")
        _w("── Orientation (RAM cache, stale — run /workday-start to refresh) ──\n")
        _w(cache_text)
        _w("\n")
        _w(
            "── Orientation: 1 document loaded (stale cache — "
            f"{changed} and possibly others changed since generation) ──\n"
        )
        return True

    # CACHE_HEAD missing or invalid — emit cache without staleness guarantee
    _w("\n")
    _w("── Orientation (RAM cache, HEAD unverifiable) ──\n")
    _w(cache_text)
    _w("\n")
    _w("── Orientation: 1 document loaded (from cache, staleness unknown) ──\n")
    return True


def handle_cache_present_boot(cache: Path, cache_text: Optional[str] = None) -> bool:
    """Boot fast-path cache-present handler — pure read, ZERO git subprocess calls.

    This is the boot/`--lightweight` counterpart to `handle_cache_present()`
    above: that function's staleness banner (`git cat-file -t <cache_head>`,
    then a `git diff --quiet <cache_head>..HEAD -- <pathspecs>`, and on a
    stale hit a SECOND `git diff --name-only` to name the first changed
    file) was costing ~3 git subprocess spawns on every SessionStart boot,
    even though the overwhelmingly common case is "cache present, emit it."
    Staleness detection is deliberately NOT reproduced here as a git-diff check — that cost
    stays retired; a boot-time SIGNAL (not a regen) is now carried separately by
    `orientation_cache_staleness_banner()`, called by `main()` alongside this function.
    Full regeneration is still deferred to `/workday-start` and friends — see
    `commands/workday-start.md` around the orientation-cache regeneration step.

    `cache_text`: optional pre-read cache contents. `main()`'s lightweight branch reads the
    cache file exactly once (to feed both `orientation_cache_staleness_banner()` and this
    function) and threads the text through here rather than re-opening the file a second time
    on the same boot. Defaults to None, which preserves this function's original
    self-contained behaviour for any direct/legacy caller that doesn't pre-read.

    Returns True if handled (caller must stop processing / exit),
    False if no cache file exists (caller falls through to
    `lightweight_branch()`).
    """
    if cache_text is None:
        if not cache.is_file():
            return False
        cache_text = cache.read_text(encoding="utf-8", errors="replace")

    _w("\n")
    _w(cache_banner_line(cache_text))
    _w(cache_text)
    _w("\n")
    _w("── Orientation: 1 document loaded (from cache) ──\n")
    return True


# ---------------------------------------------------------------------------
# Lightweight branch (F18/C17)
# ---------------------------------------------------------------------------


def _read_current_branch_boot(repo_root: Optional[str]) -> str:
    """Pure-Python `.git/HEAD` read — no `git rev-parse` subprocess.

    PM directive (2026-07-15, tightened): the boot path spawns NOTHING, git
    or bash — every subprocess spawn costs ~200-500ms on Windows. This
    branch of `main()` is cache-absent (rare after first boot, but still
    reachable on the `--lightweight` boot invocation), so it must stay
    zero-subprocess too, not just the cache-present branch. `.git/HEAD`
    normally contains `ref: refs/heads/<branch>\\n` on a checked-out branch,
    or a bare 40-char SHA in detached-HEAD state — this returns the branch
    name in the former case and "" in the latter (matching the old
    `git rev-parse --abbrev-ref HEAD` failure-shape fallback of "", since a
    detached-HEAD short-SHA display wasn't the prior contract either).
    """
    if not repo_root:
        return ""
    try:
        head_text = (Path(repo_root) / ".git" / "HEAD").read_text(
            encoding="utf-8", errors="replace"
        ).strip()
    except Exception:
        return ""
    if head_text.startswith("ref:"):
        ref = head_text.split(":", 1)[1].strip()
        return ref.rsplit("/", 1)[-1] if ref else ""
    return ""


def lightweight_branch(repo_root: Optional[str] = None) -> None:
    """F18/C17 lightweight branch — cache-absent fallback only.

    B-F4 review finding (resolved): the bash oracle's cache-present block
    ALWAYS short-circuits BEFORE reaching the lightweight check — so
    `--lightweight` has
    ZERO effect whenever `orientation_cache.md` is present; a warm-cache
    /clear still gets the full cached-orientation content, never this
    two-line banner. An earlier draft of this port checked LIGHTWEIGHT
    before opening/diffing the cache file, which meant this branch also
    fired when a cache existed — a genuine divergence from the oracle. That
    has been fixed: `main()` now checks cache-present FIRST (via
    `handle_cache_present_boot()`/`handle_cache_present()`) and only falls
    through to this branch when no cache exists AND `--lightweight` was
    passed, exactly mirroring the oracle's control flow. No PM sign-off
    needed here — this restores oracle parity rather than changing behavior.

    Branch resolution is subprocess-free (`_read_current_branch_boot()`) —
    see that function's docstring for the zero-spawn boot-path rationale.
    """
    _w("\n")
    _w("── Orientation (lightweight — /clear) ──\n")
    branch = _read_current_branch_boot(repo_root)
    if branch:
        _w(f"  Branch: {branch}\n")
    _w("  Full orientation available on next fresh session start.\n")


# ---------------------------------------------------------------------------
# Full mode (cache absent, non-lightweight)
# ---------------------------------------------------------------------------


def _count_lines(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            return sum(1 for _ in fh)
    except Exception:
        return 0


def _pointer_doc(label: str, candidates: list) -> bool:
    for path_str in candidates:
        p = Path(path_str)
        if p.is_file():
            lines = _count_lines(p)
            _w(f"  {label}: {path_str} ({lines} lines) — read when needed\n")
            return True
    _w(f"  {label}: not found\n")
    return False


def _resolve_scc_cmd() -> Optional[str]:
    home = Path.home()
    candidates = ["scc", str(home / "bin" / "scc"), str(home / "bin" / "scc.exe")]
    for c in candidates:
        if shutil.which(c):
            return c
        p = Path(c)
        # os.access(..., os.X_OK) degrades to existence-only on Windows (no
        # POSIX exec bit) -- candidates already enumerate the .exe variant
        # explicitly above, so on Windows existence is the correct predicate.
        if os.name == "nt":
            if p.is_file():
                return str(p)
        elif p.is_file() and os.access(p, os.X_OK):
            return str(p)
    return None


def full_mode(repo_root: Optional[str], state_root: str) -> None:
    _w("\n")
    _w("── Orientation (no fresh cache — pointers only) ──\n")

    found = 0

    repomap = Path(repo_root or ".") / ".claude" / "repomap.md"
    if repomap.is_file():
        lines = _count_lines(repomap)
        _w(f"  Repo Map: .claude/repomap.md ({lines} lines) — read when needed\n")
        found += 1
    else:
        _w(
            "  Repo Map: not found — run /update-docs to create\n"
        )

    if _pointer_doc("Directory", ["DIRECTORY.md", "docs/DIRECTORY.md"]):
        found += 1

    _w("\n")
    _w("── Project Vitals ──\n")

    r = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    branch = r.stdout.strip() if r.returncode == 0 else ""

    if branch:
        _w(f"  Branch: {branch}\n")
        _w("  Recent commits:\n")
        log = _run(["git", "log", "--oneline", "-5"])
        if log.returncode == 0:
            for line in log.stdout.splitlines():
                _w(f"    {line}\n")

    # scc code stats — cached by git HEAD to avoid rescanning every session
    scc_cache = Path(state_root) / ".scc-cache"
    scc_cache_head = ""
    if scc_cache.is_file():
        try:
            with scc_cache.open("r", encoding="utf-8", errors="replace") as fh:
                scc_cache_head = fh.readline().strip()
        except Exception:
            scc_cache_head = ""

    r2 = _run(["git", "rev-parse", "HEAD"])
    current_head = r2.stdout.strip() if r2.returncode == 0 else ""

    scc_out = ""
    if scc_cache_head and current_head and scc_cache_head == current_head:
        try:
            with scc_cache.open("r", encoding="utf-8", errors="replace") as fh:
                lines = fh.readlines()
            scc_out = "".join(lines[1:]).rstrip("\n")
        except Exception:
            scc_out = ""
    else:
        scc_cmd = _resolve_scc_cmd()
        if scc_cmd:
            r3 = _run(
                [scc_cmd, "--no-complexity", "--no-cocomo", "--no-duplicates", "--sort", "code"]
            )
            if r3.returncode == 0:
                lines_out = r3.stdout.splitlines()[:20]
                scc_out = "\n".join(lines_out)
            if scc_out and current_head:
                try:
                    scc_cache.parent.mkdir(parents=True, exist_ok=True)
                    tmp_path = scc_cache.with_name(f"{scc_cache.name}.{os.getpid()}.tmp")
                    with tmp_path.open("w", encoding="utf-8") as fh:
                        fh.write(current_head + "\n")
                        fh.write(scc_out + "\n")
                    os.replace(tmp_path, scc_cache)
                except Exception:
                    pass

    if scc_out:
        _w("  Code stats (scc):\n")
        for line in scc_out.splitlines():
            _w(f"    {line}\n")

    # Active plan files
    plans = sorted(glob.glob(str(Path(repo_root or ".") / "tasks" / "*" / "todo.md")))
    if plans:
        _w("  Active plans:\n")
        for p in plans:
            _w(f"    {p}\n")

    # Pending handoffs
    handoffs = sorted(glob.glob(str(Path(state_root) / "handoffs" / "*.md")))
    if handoffs:
        _w("  Pending handoffs:\n")
        for h in handoffs:
            _w(f"    {h}\n")

    # Lessons entry count (per-entry YAML in state/lessons/)
    lessons_dir = Path(state_root) / "lessons"
    if lessons_dir.is_dir():
        try:
            lesson_count = sum(
                1
                for entry in lessons_dir.iterdir()
                if entry.is_file() and entry.name.endswith(".yaml")
            )
        except Exception:
            lesson_count = 0
        _w(f"  Lessons: {lesson_count} entries in state/lessons/\n")

    _w("\n")
    _w("No orientation cache. Run /update-docs or /workday-start to generate one.\n")
    _w(f"── Orientation: {found} document(s) available (not loaded — read on demand) ──\n")


def main(argv: list) -> int:
    lightweight = "--lightweight" in argv

    # B-F2: drain the SessionStart hook's stdin JSON defensively, bounded to
    # 2s. This hook doesn't need the JSON payload (unlike session-init.py,
    # which extracts session_id from it), but the harness may still write it
    # to this process's stdin — an un-drained pipe risks a hang on Windows.
    # Content is discarded; failures are fail-open (empty string, no raise).
    try:
        _read_stdin(2.0)
    except Exception:
        pass

    if lightweight:
        # Boot fast-path (the ONLY invocation shape in production — the
        # SessionStart hook registration in hooks.json always passes
        # --lightweight; confirmed by repo-wide grep, no other caller
        # exists). Repo-root resolution and the cache-present branch are
        # BOTH subprocess-free here — see resolve_repo_root_boot() and
        # handle_cache_present_boot() docstrings for what was removed and
        # why. The two staleness banners stay (stat()-based, non-git,
        # near-free) — dropping them would lose the repomap/exec-summary
        # freshness nudge for no boot-latency benefit.
        repo_root = resolve_repo_root_boot()
        state_root = resolve_state_root(repo_root, boot=True)
        cache = Path(state_root) / "orientation_cache.md"

        # Read the cache file at most ONCE on the boot path -- both the staleness banner and
        # the emitter below consume this same text rather than each opening the file
        # separately. None (not present / unreadable) propagates to both as "nothing to say."
        cache_text: Optional[str] = None
        try:
            if cache.is_file():
                cache_text = cache.read_text(encoding="utf-8", errors="replace")
        except Exception:
            cache_text = None

        try:
            repomap_staleness_banner(repo_root)
        except Exception:
            pass
        try:
            exec_summary_staleness_banner(repo_root)
        except Exception:
            pass
        try:
            orientation_cache_staleness_banner(repo_root, cache_text)
        except Exception:
            pass
        try:
            engine_resolution_banner()
        except Exception:
            pass

        try:
            if handle_cache_present_boot(cache, cache_text=cache_text):
                return 0
        except Exception:
            pass

        try:
            lightweight_branch(repo_root)
        except Exception:
            pass
        return 0

    # Full/legacy mode (non-lightweight): no current production caller (the
    # only registered invocation always passes --lightweight — see above),
    # retained for direct/manual/debug invocation and any future caller
    # that wants the git-verified staleness banner. Unchanged from the
    # pre-boot-fast-path behavior: git-based repo-root resolution and the
    # cache-present branch's git diff staleness check both still apply here.
    repo_root = resolve_repo_root()
    state_root = resolve_state_root(repo_root)
    cache = Path(state_root) / "orientation_cache.md"

    try:
        repomap_staleness_banner(repo_root)
    except Exception:
        pass
    try:
        exec_summary_staleness_banner(repo_root)
    except Exception:
        pass
    try:
        engine_resolution_banner()
    except Exception:
        pass

    try:
        if handle_cache_present(cache, repo_root):
            return 0
    except Exception:
        pass

    try:
        full_mode(repo_root, state_root)
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
