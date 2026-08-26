"""
remove-claude-klabauter-precommit-hook — standalone remover for claude-klabauter's
registry-driven `.git/hooks/pre-commit` gate chain.

Purpose: `.git/hooks/` is untracked and per-clone — no commit this repo makes
can ever repair a hook already installed on another machine. When a future
change deletes the gate chain this hook calls out to (see
`coordinator_core.ops.install_claude_klabauter_precommit_hook`), every clone still
carrying an installed hook would BLOCK every commit with "missing script"
until this remover (or a re-run of the installer) runs. This script exists
so that remediation is always already on disk, in whatever commit deletes
the gate chain or earlier — see
`docs/plans/2026-08-25-the-staged-rollback-gate-dies-without-blocking-a-commit.md`
chunk C1.

Resolution axis (stated explicitly per that plan's Anti-scope): this module
is FULLY STANDALONE — no `coordinator_core` import, no engine-root
resolution, `pathlib`/`subprocess` only. It deliberately does NOT model its
root resolution on `coordinator/bin/check-registry-codename-leak.py`, whose
`_import_runner()` reaches the DISPATCH axis
(`require_dispatch_engine_on_path()`, the published-mirror resolver) — that
is the exact resolution that makes `install-claude-klabauter-precommit-hook.py`
unreachable from its own CLI today, and reproducing it here would leave this
remover exposed to the identical failure mode it exists to route around.

Idempotent, refuses to touch a foreign hook: only ever removes
`.git/hooks/pre-commit` when it carries the registry banner this repo's
installer stamps into every hook it writes
(`"Registry-driven (coordinator_core.ops.install_claude_klabauter_precommit_hook)"`).
An absent hook or a hook lacking that banner (operator-authored, or authored
by some other tool) is left alone — this script never blind-unlinks a hook
it did not write.

Resolves the git COMMON dir (`git rev-parse --git-common-dir`), not a bare
`.git/` join — `.git` is a file (not a directory) inside a linked worktree
or a submodule checkout, and the hooks directory for either lives at the
common dir, not at the per-worktree `.git` path.

Usage:
    remove-claude-klabauter-precommit-hook [target-repo-root]

    target-repo-root defaults to the current working directory.

Negative-spec:
    - Never imports `coordinator_core` or resolves an engine root — this
      script must keep running after both the installer op module and its
      CLI trampoline are deleted (see the plan chunk that deletes them).
    - Never removes a hook that does not carry the registry banner —
      an operator-authored or foreign-tool-authored hook is left in place,
      always, with a named stderr message.
    - Never assumes `.git` is a directory — resolves the git common dir via
      `git rev-parse --git-common-dir` so worktrees and submodules resolve
      correctly.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_PROG = "remove-claude-klabauter-precommit-hook"

#: The exact banner substring every hook `install_claude_klabauter_precommit_hook`
#: writes carries (see that module's `_hook_body`) — presence is the
#: authorship test this remover uses before ever touching a hook file.
_BANNER = "Registry-driven (coordinator_core.ops.install_claude_klabauter_precommit_hook)"


def _no_console_creationflags() -> int:
    """`CREATE_NO_WINDOW` on Windows, `0` elsewhere — avoids a flashing
    console window when this script is invoked from a GUI-launched parent.
    `getattr` guards the non-Windows case, where the attribute does not
    exist on the `subprocess` module at all."""
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _git_common_dir(target: str) -> Path | None:
    """Resolve `target`'s git COMMON directory via `git rev-parse
    --git-common-dir`, run with `cwd=target` (not `-C`, so a relative
    `target` resolves the same way a caller's own shell would resolve it).

    Returns None on any failure: git missing, `target` not a git repo, or a
    non-zero exit. The common dir is what a linked worktree or submodule
    ACTUALLY shares its hooks directory with — never assume `.git` is a
    directory to join `hooks/pre-commit` onto directly."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=target,
            capture_output=True,
            text=True,
            check=False,
            creationflags=_no_console_creationflags(),
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    raw = result.stdout.strip()
    if not raw:
        return None
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = Path(target) / candidate
    try:
        return candidate.resolve()
    except OSError:
        return None


_USAGE = f"""usage: {_PROG} [REPO_PATH]

Remove an installed .git/hooks/pre-commit that this coordinator installer
generated. REPO_PATH defaults to the current directory; the git common dir is
resolved from it, so worktrees and submodules land on the shared hooks dir.

Exits 0 and changes nothing when there is no hook, when REPO_PATH is not a git
repo, or when the installed hook does not carry the registry banner -- a hook
this installer did not generate is never unlinked. Exits 1 only on a real I/O
failure.

Note: removing the hook is the FIX for a stale installed gate, not the fastest
unblock. An operator who merely needs to commit can use `git commit
--no-verify` (which still runs prepare-commit-msg, so commit trailers survive).
See docs/reference/guard-override-keys.md.
"""


def main(argv: list[str]) -> int:
    if argv and argv[0] in ("-h", "--help"):
        print(_USAGE, file=sys.stdout)
        return 0
    target = argv[0] if argv else "."
    common_dir = _git_common_dir(target)
    if common_dir is None:
        print(f"{_PROG}: {target} is not in a git repo — skipping.", file=sys.stderr)
        return 0

    hook_path = common_dir / "hooks" / "pre-commit"
    if not hook_path.is_file():
        print(f"{_PROG}: no pre-commit hook at {hook_path} — nothing to remove.", file=sys.stderr)
        return 0

    try:
        text = hook_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"{_PROG}: could not read {hook_path}: {exc}", file=sys.stderr)
        return 1

    if _BANNER not in text:
        print(
            f"{_PROG}: {hook_path} does not carry the registry banner — "
            "leaving this operator-authored hook in place.",
            file=sys.stderr,
        )
        return 0

    try:
        hook_path.unlink()
    except OSError as exc:
        print(f"{_PROG}: could not remove {hook_path}: {exc}", file=sys.stderr)
        return 1

    print(f"{_PROG}: removed {hook_path}.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
