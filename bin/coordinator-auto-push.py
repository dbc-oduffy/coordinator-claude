# The generated git post-commit hook shim (git_hook_install.ensure_post_commit_hook)
# now execs this file directly and synchronously — `exec "$_PY" "$SCRIPT" "$@"`,
# no `nohup`, no `&`, no `command -v bash` gate. Async, when wanted, is owned by
# the invoked Python (auto_push.py self-detaches internally: os.fork() on POSIX,
# detached Popen respawn on Windows) — the shim never backgrounds anything itself.
"""
coordinator-auto-push — CLI trampoline over claude-klabauter coordinator_core.hooks.auto_push.

Finish-strangler port (DR-059): the bash implementation (git-hook post-commit
push helper — branch-case canonicalization, 9-class push-error classification,
retry/backoff, forensic stderr capture) has been fully ported to
coordinator_core/hooks/auto_push.py (619 lines, 22 tests in test_auto_push.py)
per state/handoffs/2026-07-15_164501_auto-push-naked-python-reimpl.md. This file
is now a thin DoE-side (contract) trampoline over that claude-klabauter (engine) module,
per DR-047 (DoE owns contract/generator, claude-klabauter owns engine).

Shebang note: the SHEBANG line above is `#!/usr/bin/env python3`, and correct
for this shape. On Windows, this file's co-located `.cmd` twin wins via
`PATHEXT` when invoked as a bareword, so the shebang is never read there; on
macOS/Linux `python3` is the right interpreter. Caution: callers must invoke
via the extensionless name or a resolved-interpreter prefix, never a bareword
`.py` through git-bash — git-bash DOES honor the shebang and would exec-127
with no `python3` present. See the carve-out in DoE-claude's
coordinator/docs/wiki/bash-on-windows-gotchas.md § Carve-out (cross-repo —
this wiki lives in the DoE-claude repo, not here).

Always exits 0 — auto-push must never block a commit. auto_push.main() already
enforces this internally (broad except + best-effort logging); this trampoline
does not add its own try/except around the call for that reason.

Performance-path classification: HOT — fires on every `work/*` commit. Chain is
git -> post-commit hook shim (sh) -> `exec "$_PY" coordinator-auto-push` (exec,
shell-doc-ok: the quoted line is the installed sh hook's own body.
no fork, replaces the sh process with python) -> in-process import + call of
auto_push.main() -> auto_push.py self-detaches internally when async is wanted
(os.fork() on POSIX / detached Popen respawn on Windows). Do NOT route this
through cc_invoke()/route()'s subprocess-spawn-and-JSON-RPC-envelope seam --
that would add a second subprocess hop on a per-commit hot path for no benefit;
direct in-process import + call is both correct-shaped (auto_push.main()
already IS the entrypoint, and its `--json`-less stdout/stderr contract doesn't
fit an RPC envelope) and strictly cheaper.

Both open items from the claude-klabauter side (auto_push.py's own docstring) are now
RESOLVED. The Windows+SSH spike returned VIABLE: native Windows Python spawning
native `git push` reaches the 1Password SSH agent with no PowerShell detour.
Per the 2026-08-06 no-shell-spawns PM ruling, the dead PowerShell fallback
branch and its `WINDOWS_SSH_POWERSHELL_FALLBACK` gating constant were deleted
outright from auto_push.py (native `git push` is now the sole, unconditional
transport on every platform) — see that module's "Transport history" note for
the preserved rationale. The async self-detach path
(os.fork on POSIX / detached Popen respawn on Windows) is Windows-verified live
(claude-klabauter commit e8b423b1). Caveat, carried forward rather than dropped: the real
Windows dependency is ssh-BINARY selection, not the retired PowerShell branch —
on a box with a bundled MSYS `ssh.exe` and no `core.sshCommand` pin, git can
select it and the push fails auth; see docs/wiki/bash-on-windows-gotchas.md for
the remedy (pin `core.sshCommand` to the Win32-OpenSSH binary). Do not read this
as "Windows SSH just works" unqualified.

Spec backlink: DoE-claude:pln-bash-to-naked-python-engine-mi-c09292 § T3a-g1b
Recipe: scratch/subagent-sandbox/bash-to-python-engine-migration/recipe-T3a-g1-cruft-sweep-auto-push.md § Script 2
Prior bash implementation: see git log (coordinator-auto-push, 223 lines, retired on this cutover)
"""
from __future__ import annotations

import os
import sys

def _import_main():
    """Resolve the engine root, put it on sys.path, and import the ported entrypoint.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it -- this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.

    Negative-spec: `lib.cc_invoke` is imported HERE, not at module scope. This
    file is reached both as a script (with `coordinator/bin` on `sys.path`) and
    in-process via `runpy.run_path` from the settings-home forwarder, where it
    is not — a module-scope import raises `ModuleNotFoundError` before `main`
    is ever called, and the module body must stay inert for warm serving.
    """
    bin_dir = os.path.dirname(os.path.abspath(__file__))
    if bin_dir not in sys.path:
        sys.path.insert(0, bin_dir)
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    require_dispatch_engine_on_path()
    from coordinator_core.hooks.auto_push import main as _op_main

    return _op_main


def _git_dirs() -> "tuple[str, str] | None":
    """Return ``(gitdir, common_dir)`` for the repo containing the cwd, or None.

    Stdlib only, no spawn, and deliberately NOT reusable from
    ``coordinator_core.git.git_dir.resolve_git_common_dir``: this runs on the
    path where importing ``coordinator_core`` is the thing that just failed, so
    reaching for the engine's own resolver would fail for the same reason it is
    being called. Duplicated on purpose; the negative-spec is the duplication's
    justification.

    ``gitdir`` holds HEAD (per-worktree); ``common_dir`` holds the shared
    ``push-failures.log``. They differ in a linked worktree and in a
    ``--separate-git-dir`` clone, which is why both are returned rather than
    one join.
    """
    cur = os.path.abspath(os.getcwd())
    while True:
        cand = os.path.join(cur, ".git")
        if os.path.isdir(cand):
            gitdir = cand
            break
        if os.path.isfile(cand):
            try:
                with open(cand, encoding="utf-8") as fh:
                    head = fh.read().strip()
            except OSError:
                return None
            if not head.startswith("gitdir:"):
                return None
            gitdir = head.split(":", 1)[1].strip()
            if not os.path.isabs(gitdir):
                gitdir = os.path.abspath(os.path.join(cur, gitdir))
            break
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent

    common = gitdir
    commondir_file = os.path.join(gitdir, "commondir")
    if os.path.isfile(commondir_file):
        try:
            with open(commondir_file, encoding="utf-8") as fh:
                rel = fh.read().strip()
        except OSError:
            rel = ""
        if rel:
            common = rel if os.path.isabs(rel) else os.path.abspath(os.path.join(gitdir, rel))
    return gitdir, common


def _current_branch(gitdir: str) -> "str | None":
    """Branch name off ``<gitdir>/HEAD``, or None when detached/unreadable."""
    try:
        with open(os.path.join(gitdir, "HEAD"), encoding="utf-8") as fh:
            head = fh.read().strip()
    except OSError:
        return None
    if not head.startswith("ref: refs/heads/"):
        return None
    return head[len("ref: refs/heads/") :]


def _log_preflight_failure(err_class: str, detail: str) -> None:
    """Append one conforming row to the git common dir's ``push-failures.log``.

    This is the whole point of the function: a failure RAISED BEFORE
    ``auto_push.main()`` runs cannot reach ``auto_push.log_failure``, so until
    now it wrote nothing anywhere. The hook exits 0 by contract and its stderr
    goes to a log nobody opens, which is how an engine-unresolvable
    auto-push stayed invisible fleet-wide across two separate outages. Writing
    the SAME file the working path writes gives this class the three readers
    that file already has -- orientation's ``emit_auto_push_health``,
    ``workday-start-advisory-counters push-failures``, and the DoE-side
    Stop-time tripwire -- instead of standing up a fourth channel.

    Row format is ``log_failure``'s, byte-for-byte in the fields those readers
    parse: the ``[ISO-8601 UTC]`` stamp they window on, ``on <branch> (`` for
    attribution, and a ``<route>/<class> after <n>`` triple. Route is
    ``trampoline`` -- honest about where it died, and distinct from the two
    push routes so a reader never mistakes this for a rejected push. There is
    no forensic stderr file to point at (nothing was sent to a remote), so the
    ``stderr=`` field is ``<none>``, not a path that would 404.

    Gated to ``work/`` branches to match ``emit_auto_push_health``'s own gate:
    off a work branch auto-push would not have pushed anyway, so a row there
    would inflate counts that are read as "unrecovered failures".

    Never raises and never blocks -- every failure mode returns quietly. The
    commit has already landed; the worst outcome available here is losing the
    breadcrumb, never the commit.
    """
    try:
        dirs = _git_dirs()
        if dirs is None:
            return
        gitdir, common_dir = dirs
        branch = _current_branch(gitdir)
        if branch is None or not branch.startswith("work/"):
            return
        from datetime import datetime, timezone

        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        first = " ".join(detail.split())[:200] or "<empty>"
        line = (
            f"[{stamp}] PUSH FAILED on {branch} (trampoline/{err_class} after 1) "
            f":: {first} :: stderr=<none>\n"
        )
        with open(
            os.path.join(common_dir, "push-failures.log"), "a", encoding="utf-8", newline="\n"
        ) as fh:
            fh.write(line)
    except Exception:
        return


def main(argv: "list[str] | None" = None) -> int:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        # CLAUDE_KLABAUTER_ROOT resolution failed. Auto-push must never block a commit,
        # so this is a loud stderr note, not a nonzero exit.
        print(f"coordinator-auto-push: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        _log_preflight_failure("claude-klabauter-unresolved", str(exc))
        return 0
    except ImportError as exc:
        print(
            f"coordinator-auto-push: coordinator_core.hooks.auto_push not importable: {exc}",
            file=sys.stderr,
        )
        _log_preflight_failure("engine-unimportable", str(exc))
        return 0

    # auto_push.main() always returns 0 internally (broad except + best-effort
    # log on any internal error) -- no additional try/except needed here.
    return op_main((sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
