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

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _import_main():
    """Resolve the engine root, put it on sys.path, and import the ported entrypoint.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it -- this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.hooks.auto_push import main as _op_main

    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        # CLAUDE_KLABAUTER_ROOT resolution failed. Auto-push must never block a commit,
        # so this is a loud stderr note, not a nonzero exit.
        print(f"coordinator-auto-push: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(0)
    except ImportError as exc:
        print(
            f"coordinator-auto-push: coordinator_core.hooks.auto_push not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(0)

    # auto_push.main() always returns 0 internally (broad except + best-effort
    # log on any internal error) -- no additional try/except needed here.
    sys.exit(op_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
