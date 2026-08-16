"""SessionStart(startup|clear|compact) naked-Python thin stub — hook-generation
self-probe (the settings.json hooks-generation kill-switch re-armer).

Wires `coordinator_core.ops.session.guard_hook_generation_self_probe.run_self_probe`
into boot. The op existed fully built and tested with a registered
`session.self_probe_hook_generation` op name, but no `hooks.json` entry named it
and no other caller referenced it anywhere — an inert guard, one that runs
nowhere hides its own defects. This stub is the wiring.

The doctrine plane owns only this thin PLUMBING shim (DR-047 transport-seam carve-out, same
split guard-settings-integrity.py and guard-foreign-platform-paths.py already
use): resolve the claude-klabauter engine, call its guard function IN-PROCESS, relay its
returned text. Claude-klabauter owns the guard LOGIC.

Shape choice (in-process direct import, NOT a sweep-boot.py-style subprocess
exec): `run_self_probe`'s OWN module docstring states it mirrors "the fail-open
posture of the sibling guard_settings_integrity/guard_foreign_platform_paths
SessionStart guards" — both of which are wired via direct import + in-process
call (see those two hook stubs), not a subprocess re-spawn of a standalone
CLI. `run_self_probe` is explicitly documented as cheap-by-construction
("single os.environ.get read, at most two Path.is_file/is_dir stats, and a
best-effort small text write... no subprocess") specifically BECAUSE it fires
every boot — routing it through a `coordinator_core.invoke` subprocess spawn
(the sweep-boot.py shape, built for a standalone `bin/*.py` CLI target this op
does not have) would reintroduce exactly the per-boot process-spawn tax this
op's own docstring documents avoiding, and would fight the repo's own P0
bash/subprocess-kill campaign (`coordinator.local.md`). Registered as
`session.self_probe_hook_generation` for OTHER (IPC/JSON-RPC) callers; this
stub reaches the plain importable function directly instead, exactly as
guard-settings-integrity.py reaches its three sibling functions.

Fail-open on exit code, matching the SessionStart hook's own contract (session
start must never wedge) — EVERY failure path below (claude-klabauter root unresolved,
op module unimportable, op call raises, op call times out, op returns a
non-string/malformed value) exits 0 and emits nothing to stdout (no banner),
never propagating the failure into additionalContext.

Fail-LOUD to the housekeeping-failures log (mirrors sweep-boot.py's own
2026-07-23 fail-loud fix, same rationale: stdout/exit-code alone made a
genuinely-dead probe byte-indistinguishable from a healthy/silent one). Each
failure path below best-effort appends a `CHILD FAILED` record to the shared
`<repo>/state/housekeeping-failures.log` via
`coordinator_core.ops.ceremony.detached_spawn.record_child_failure` once a
Claude-klabauter root is resolved; the one failure path where no claude-klabauter root is
resolved (so `coordinator_core` cannot be imported at all) hand-rolls a
format-matched fallback line, mirroring sweep-boot.py's own
`_write_raw_failure_record`.

Soft in-process timeout: `run_self_probe` is documented cheap and is itself
fully wrapped in a blanket try/except (per its own module docstring), so it
should never hang — but this stub still bounds the call with a
`ThreadPoolExecutor(...).result(timeout=...)` rather than trusting that
contract unconditionally, so a future regression in the engine function
degrades to a fail-open no-op here instead of wedging SessionStart.

Making that timeout actually bind takes two non-obvious steps, both learned
by observation rather than reasoning — see the comment at the call site.
Python cannot hard-kill a thread, so a timed-out worker has to be ABANDONED,
and both the obvious spellings silently refuse to abandon it: a `with
ThreadPoolExecutor(...)` block joins the worker in `__exit__`, and even
without the context manager, `concurrent.futures` registers an
interpreter-shutdown hook that joins its workers. Either one turns the
timeout into a no-op and hangs the session outright. The escape is
`shutdown(wait=False)` plus `os._exit(0)`.

AC-3 note (side-effect scope): `run_self_probe` can write two things under
`~/.claude` (its own resolved config dir, honoring CLAUDE_CONFIG_DIR) — a
best-effort status sentinel (`.coordinator-content-root-last-seen`, always,
harmless) and, ONLY when `COORDINATOR_CONTENT_ROOT` is empty/unresolvable AND
the kill-switch marker (`.coordinator-hooks-disabled`) is not ALREADY present,
the kill-switch marker itself (re-arming it). This stub does not touch either
file itself and does not gate/skip the call to avoid them — that mutation is
entirely `run_self_probe`'s own designed side effect ("on its own terms"),
not something this trampoline adds, duplicates, or short-circuits.

Source (equivalent shim pair): coordinator/hooks/scripts/guard-settings-integrity.py,
    coordinator/hooks/scripts/guard-foreign-platform-paths.py
Engine: coordinator_core.ops.session.guard_hook_generation_self_probe.run_self_probe
    (claude-klabauter)
Spec backlink: doctrine-repo dispatch state/subagent-share/
    992e179e-735d-49f2-825f-7151aad850ea/coordinatorexecutor-1f3e8af6.md
    (2026-07-29) — wires the previously-inert self-probe guard into
    SessionStart.
"""

from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FutureTimeoutError
from pathlib import Path

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
try:
    from _engine_root import (  # noqa: E402
        arm_lazy_ops as _arm_lazy_ops,
        resolve_claude_klabauter_root as _resolve_claude_klabauter_root,
    )
except Exception:
    # Defensive fallback -- a hook script copied/deployed WITHOUT its
    # sibling _engine_root.py (e.g. an isolated test harness, or a
    # partial deploy) must still fail-open rather than crash on import.
    def _resolve_claude_klabauter_root() -> str | None:
        return None

    def _arm_lazy_ops() -> None:
        return None
try:
    from _git_root_walk import git_root_walk as _git_root_walk  # noqa: E402
except Exception:
    # Defensive fallback -- a deploy missing its sibling _git_root_walk.py
    # must still fail open to the subprocess rung below, not crash on import.
    def _git_root_walk() -> str | None:
        return None


_SELF_PROBE_TIMEOUT_SECS = 5


def _resolve_this_repo_root() -> str | None:
    """Resolve the repo THIS hook is running in (cwd-based) — the destination
    for the housekeeping-failures log, NOT the claude-klabauter root. Mirrors
    sweep-boot.py's own `_resolve_this_repo_root` exactly (same rationale:
    `__file__` lives under the doctrine-plane source tree regardless of which
    consumer repo's session invoked it via live `--plugin-dir` resolution, so
    a `__file__`-based root would mis-file every non-doctrine-plane session's
    failure record).

    In-process parent walk (`_git_root_walk`, cwd-based like this function's own contract)
    first -- no subprocess on the routine path; `git rev-parse --show-toplevel` below is kept
    only as a fallback for the case the walk cannot resolve.
    """
    walked = _git_root_walk()
    if walked:
        return walked
    import subprocess

    no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            creationflags=no_window,
        )
    except OSError:
        return None
    root = result.stdout.strip()
    if result.returncode != 0 or not root:
        return None
    return root


def _write_raw_failure_record(repo_root: str, detail: str) -> None:
    """Hand-rolled fallback append, format-matched to
    `coordinator_core.ops.ceremony.detached_spawn.record_child_failure`'s own
    ``CHILD FAILED script=<path> :: <detail>`` line shape. Used only on the
    one failure path where that real writer is structurally unreachable: an
    unresolved claude-klabauter root means there is no known `coordinator_core` to
    import in the first place."""
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


def _record_failure(claude_klabauter_root: str | None, detail: str) -> None:
    """Best-effort, defensive-by-construction failure recorder shared by every
    fail-open path below. NEVER raises — a broken observability path must
    never become the thing that wedges SessionStart boot."""
    try:
        repo_root = _resolve_this_repo_root()
        if not repo_root:
            return
        if claude_klabauter_root:
            try:
                if claude_klabauter_root not in sys.path:
                    sys.path.insert(0, claude_klabauter_root)
                from coordinator_core.ops.ceremony.detached_spawn import (
                    record_child_failure,
                )

                record_child_failure(
                    repo_root,
                    os.path.abspath(__file__),
                    exc=RuntimeError(detail),
                )
                return
            except Exception:
                pass  # fall through to the hand-rolled writer below
        _write_raw_failure_record(repo_root, detail)
    except Exception:
        pass


def main() -> int:
    # --- Drain stdin (mirror the sibling guards' stdin-drain pattern). ---
    try:
        sys.stdin.read()
    except Exception:
        pass

    root = _resolve_claude_klabauter_root()
    if not root:
        _record_failure(None, "claude-klabauter root unresolved — skipping self-probe")
        return 0  # fail-open — claude-klabauter unresolvable on this machine

    if root not in sys.path:
        sys.path.insert(0, root)

    # Skip the ~80-module eager op-registry population; this stub reaches
    # exactly one engine function by direct import (see module docstring).
    _arm_lazy_ops()

    try:
        from coordinator_core.ops.session.guard_hook_generation_self_probe import (
            run_self_probe,
        )
    except Exception as exc:
        _record_failure(root, f"engine module unimportable — {exc}")
        return 0  # engine unimportable -> fail-open (never block SessionStart)

    # Path.home() (not os.path.expanduser) fails loud -- RuntimeError, not a
    # silent literal "~" -- when every home rung is unset. Caught here and
    # degraded to the same fail-open 0 this hook already returns for an
    # unimportable engine, matching its never-block-SessionStart posture.
    try:
        home = str(Path.home())
    except RuntimeError:
        _record_failure(root, "home directory unresolvable (no USERPROFILE/HOME)")
        return 0  # fail-open — home unresolvable on this machine
    config_dir_raw = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(home, ".claude")
    config_dir = Path(config_dir_raw)

    # NOT `with ThreadPoolExecutor(...)`, and NOT a plain `return` on timeout.
    # Both of those defeat the timeout completely, which was observed rather
    # than reasoned: the context manager's __exit__ calls shutdown(wait=True),
    # so after the timeout fires the process blocks forever on the very worker
    # the timeout just gave up on -- main() never returns at all. Even after
    # dropping the context manager, concurrent.futures registers an interpreter
    # -shutdown hook that JOINS its worker threads, so a normal `return`/
    # sys.exit would still wedge at process exit. os._exit is the only portable
    # way to leave a hung non-daemon worker behind. Wedging here is not a slow
    # boot -- this is a synchronous SessionStart hook, so it hangs the session.
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(run_self_probe, config_dir)
        try:
            text = future.result(timeout=_SELF_PROBE_TIMEOUT_SECS)
        except _FutureTimeoutError:
            _record_failure(
                root,
                f"run_self_probe timed out after {_SELF_PROBE_TIMEOUT_SECS}s",
            )
            executor.shutdown(wait=False)
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(0)  # fail-open — never block SessionStart on a hung probe
        executor.shutdown(wait=False)
    except Exception as exc:
        executor.shutdown(wait=False)
        # run_self_probe is itself blanket-wrapped and documented never to
        # raise, but this stub does not trust that contract unconditionally.
        _record_failure(root, f"run_self_probe raised — {exc}")
        return 0

    if not isinstance(text, str):
        _record_failure(
            root, f"run_self_probe returned non-string output type {type(text).__name__}"
        )
        return 0  # malformed output -> fail-open, nothing forwarded

    if text:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
