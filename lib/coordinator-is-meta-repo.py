"""coordinator-is-meta-repo.py — canonical boolean primitive: is a git root
the coordinator meta-repo?

Purpose: single definition of "is the current (or given) git repository the
coordinator meta-repo (~/.claude / CLAUDE_HOME)?" Replaces three diverging
hardcoded $HOME/.claude compares scattered across bin/lib scripts.

De-bash campaign port (docs/plans/2026-07-16-bash-clean-slate-residual-migration.md):
the retired bash oracle (coordinator/lib/coordinator-is-meta-repo.sh, a
sourced-lib boolean primitive) paid the bash-invocation tax on every call and
degrades Windows. This port preserves the bash original's SELF-CONTAINMENT
deliberately: the bash oracle resolved the meta-repo root by shelling out to
this repo's own `claude-home/claude-home dir` — a DoE-local resolver with no
CLAUDE_KLABAUTER_ROOT / engine-repo dependency — never the engine checkout. A
sibling native module exists on the engine side
(`coordinator_core.meta_repo_identity.is_meta_repo`, authored explicitly as
"the Python-native peer of DoE's coordinator-is-meta-repo.sh" for a future
gated adoption wave) but importing it here would introduce a bootstrap
coupling this primitive never had: CLAUDE_KLABAUTER_ROOT must already resolve to a
real engine checkout with `coordinator_core` importable just to
answer "is cwd the meta-repo?" — a question this file's own callers
(coordinator_state_root's Rule 5, and coordinator_doe_root's bootstrap
ladder) ask BEFORE CLAUDE_KLABAUTER_ROOT is necessarily known. Reusing the DoE-local
`claude-home` seam (this repo's own `coordinator/lib/claude-home/_claude_home.py`,
already the sourced-out implementation the bash oracle shelled to) avoids
that bootstrap-order hazard while still reusing an existing seam rather
than reimplementing the CLAUDE_HOME precedence ladder from scratch.

Design (mirrors the shell original):
  - CLAUDE_HOME-aware: resolves the meta-repo root via
    `claude_home.claude_home_dir()` (same precedence as the bash oracle's
    `claude-home dir` subprocess call, now an in-process import) —
    honours CLAUDE_HOME overrides for test sandboxes and CI.
  - Canonicalized: both sides go through `Path.resolve()` (realpath) before
    comparison, to survive symlinked paths and POSIX-vs-drive-letter mismatches.
  - Fail-loud: exits 2 + remediation message on stderr when git root is
    empty or unresolvable (detect-then-fail-loud, not detect-then-silently-
    pick).

Usage:
  coordinator-is-meta-repo.py [<git-root>]
    Exit 0 (true)  — <git-root> (or cwd's git root when omitted) IS the meta-repo.
    Exit 1 (false) — it is NOT the meta-repo.
    Exit 2 (error) — git root unresolvable OR detection itself failed; see stderr.

Public API (importable, mirrors the retired bash function's call shape):
    coordinator_is_meta_repo(git_root: str | None = None) -> bool
        Raises RuntimeError on any resolution failure (git root or home dir
        unresolvable). Callers that want the CLI's fail-loud exit-2 shape
        should invoke `main()` / the subprocess form instead.

Negative-spec:
  - Does NOT modify any global variables.
  - Does NOT call coordinator_claude_klabauter_root or resolve CLAUDE_KLABAUTER_ROOT — purely
    about meta-repo identity, deliberately self-contained (see rationale
    above).
  - Does NOT use GNU realpath — uses Path.resolve() for BSD/Windows-portable
    canonicalization.
  - Does NOT define any persistent process-global state (safe to import
    repeatedly without side-effects, mirroring the bash original's
    safe-to-source-multiple-times contract).

Spec backlink: pln-stop-the-rot-claude-klabauter-state-home-placement-4cc787 § C2 / AC2
Port of: coordinator-is-meta-repo.sh (DoE 6fb5fb37, 2026-07-22, bash sourced-lib oracle)
Reused seam: coordinator/lib/claude-home/_claude_home.py::claude_home_dir()
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional


def _claude_home_module():
    """Import this repo's own claude-home resolver module (DoE-local, no
    CLAUDE_KLABAUTER_ROOT dependency) — mirrors the bash oracle's own lib-relative
    resolution of `${_cimr_lib_dir}/claude-home/claude-home`."""
    _lib_dir = os.path.dirname(os.path.abspath(__file__))
    _claude_home_dir = os.path.join(_lib_dir, "claude-home")
    if _claude_home_dir not in sys.path:
        sys.path.insert(0, _claude_home_dir)
    import _claude_home  # noqa: E402

    return _claude_home


def _resolve_git_root(git_root: Optional[str]) -> str:
    """Resolve the git root from cwd if not provided by the caller.

    Raises RuntimeError (fail-loud) on an unresolvable/empty git root.
    """
    if git_root:
        return git_root

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
            # The "git.exe is GUI-subsystem" premise this escape used to rest
            # on was measured and refuted 2026-08-07 (see
            # state/audits/2026-08-07-git-console-allocation-measurement.md,
            # the engine repo): a console-subsystem git.exe from a
            # console-less parent allocates a visible ConsoleWindowClass
            # window in ~50ms, and pipe redirection does not suppress it.
            # Applying the real fix instead of the escape.
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        raise RuntimeError(
            "coordinator_is_meta_repo: git rev-parse --show-toplevel failed "
            f"to execute ({exc}) — is git installed and on PATH?\n"
            "  Remediation: run from within a git repository, or pass the "
            "git root as the first argument."
        ) from exc

    resolved = result.stdout.strip()
    if result.returncode != 0 or not resolved:
        raise RuntimeError(
            "coordinator_is_meta_repo: git rev-parse --show-toplevel failed "
            "or returned empty — not in a git repository?\n"
            "  Remediation: run from within a git repository, or pass the "
            "git root as the first argument."
        )
    return resolved


def _canonicalize(path: Path) -> str:
    """Canonicalize via realpath; falls back to the literal path if the
    directory does not exist on disk (mirrors the shell original's
    `cd ... && pwd -P || echo "$path"` fallback)."""
    try:
        return str(path.resolve(strict=False))
    except OSError:
        return str(path)


def coordinator_is_meta_repo(git_root: Optional[str] = None) -> bool:
    """Importable public API mirroring the retired bash function's call
    shape. Raises RuntimeError on any resolution failure (git root or
    CLAUDE_HOME/home-dir unresolvable)."""
    resolved_git_root = _resolve_git_root(git_root)

    claude_home = _claude_home_module()
    try:
        meta_repo_root = claude_home.claude_home_dir()
    except ValueError as exc:
        raise RuntimeError(
            f"coordinator_is_meta_repo: claude-home dir failed to resolve "
            f"meta-repo root: {exc}\n"
            "  Remediation: ensure CLAUDE_HOME / HOME / USERPROFILE resolve "
            "to a valid absolute path."
        ) from exc

    canon_git = _canonicalize(Path(resolved_git_root))
    canon_meta = _canonicalize(meta_repo_root)

    return canon_git == canon_meta


def main(argv: Optional[list] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    git_root = args[0] if args and args[0] else None

    try:
        result = coordinator_is_meta_repo(git_root)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    return 0 if result else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
