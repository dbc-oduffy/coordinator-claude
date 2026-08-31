# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
workflow-watch.py — CLI trampoline over claude-klabauter
coordinator_core.workflow_watch.main.

Purpose: give the watcher a settings-home launcher, so the `Monitor(...)`
command `postuse_advisory_dispatch :: _check_workflow_monitor_arm_sync`
emits can name an absolute, self-resolving entrypoint instead of a bare
`python3 -m coordinator_core.workflow_watch`. That bare form runs only where
`coordinator_core` is already importable — i.e. inside the engine's own
environment — and the hook that emits it runs there, which is exactly why its
failure was invisible to the code emitting it. In any consumer repo the EM
pasted it and got `ModuleNotFoundError: No module named 'coordinator_core'`,
exit 1, while the advisory's imperative wording ("arm the watcher instead of
hand-writing one") had already talked them out of their own monitor. A dead
watcher and a quiet run look identical.
(cross-repo/inbox/2026-08-30-doe-claude-em-workflow-watch-command-is-unrunnable-outside-the-engine.md,
relayed by doe-claude-em from project-rag-em.)

Cold path — a long-poll watcher process, not a daemon-RPC hot path. Direct
in-process import + call (the aggregate-chain-loe.py / coordinator-auto-push
trampoline shape), NOT cc_invoke()/route(): this process IS the watch loop, so
there is nothing for a JSON-RPC round trip to carry.

Negative-spec: this file holds no watch logic and no argv parsing. The poll
loop, the `--transcript/--journal/--task-id/--poll-interval/--cap` surface and
the exit-code contract a Monitor consumer reads all live in
`coordinator_core/workflow_watch/__init__.py`; a second copy here would be a
second source of truth for those exit codes.

Concurrency posture: read-only against the launching session's transcript and
  the run's `journal.jsonl`, both append-only. Safe under any number of
  concurrent watchers; no locking required; nothing written.
Idempotency posture: re-running against the same task id re-renders from the
  journal's current contents. No side effects.
Resume strategy: stateless — re-run with the same arguments. The wall-clock
  `--cap` bounds every invocation, so a re-run can never outlive the run it
  watches.
"""

from __future__ import annotations

import sys


def _import_main():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    require_dispatch_engine_on_path()
    from coordinator_core.workflow_watch import main as _op_main
    return _op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"workflow-watch.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 1
    except ImportError as exc:
        print(f"workflow-watch.py: coordinator_core.workflow_watch not importable: {exc}", file=sys.stderr)
        return 1
    return op_main((sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
