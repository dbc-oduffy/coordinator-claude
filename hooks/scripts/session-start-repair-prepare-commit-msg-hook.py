"""SessionStart hook — self-heals a stale `SCRIPT=` path in the native git
`prepare-commit-msg` hook this session's repo already has installed.

Purpose: the `coordinator-prepare-commit-msg` git-native hook
(`.git/hooks/prepare-commit-msg`, installed by an engine-side installer, NOT
tracked by git — `.git/hooks/` is never version-controlled) stamps the
`Session-Id:`/`Deliverable-Id:` commit trailers (see
`coordinator_core/contract/commit-trailer-producer-contract.md`) for every
PLAIN `git commit` a session runs directly (as opposed to a commit landed
through an engine ceremony op, which stamps trailers programmatically via
`coordinator_core.git.commit_trailers` and never touches this hook at all).

The installed shim hardcodes an ABSOLUTE literal path to the
`coordinator-prepare-commit-msg` script it execs, resolved at install time.
The 2026-07-22 executable-surface migration (`b644d5a9b`, "migrate the
executable surface + its tests to the engine repo (1135 files)") relocated
`coordinator/bin/coordinator-prepare-commit-msg` OUT of this doctrine repo
and into the engine repo — but did not repoint any shim installed BEFORE
that migration ran. A shim installed pre-migration hardcodes a path into
this doctrine repo that no longer holds the file; every one of its three
fallback rungs (the hardcoded path, the `.doe-root`-relative path, and the
installed-plugin path) also resolves inside this doctrine repo, so NONE of them reaches the
script's new home. The shim's own `[ -f "$SCRIPT" ] || exit 0` contract is
correctly fail-open — it does not error, it just silently never stamps a
trailer, on every plain `git commit` in the session, indistinguishable from
a healthy no-op. This is the root cause an EM's un-mechanized `git commit`
loses `Session-Id:`/`Deliverable-Id:` silently, breaking
`review_trail.write`'s foreign-session guard, the brightline gate's oracle
attribution, and `close-out-and-stamp`'s join — see
`docs/plans/2026-08-07-commit-trailer-non-optional.md` (if authored) for the
incident this hook closes.

**Why this is doctrine-plane-resident, not an engine-repo change.** Per DR-127 (no
standing cross-repo commit grant), and because the ACTUAL git-native hook
file lives under `.git/hooks/` of whichever repo this session is in — a
local, untracked, per-checkout artifact — repairing it is inherently a
same-repo, same-session action; there is no engine-plane file to edit that
would reach this stale-on-disk shim (it was already materialized before the
migration and nothing re-materializes it automatically). This hook is the
doctrine-plane-resident repair, following the identical self-heal shape as
`session-start-register-doe-claude-root.py` (read this file first if
editing this one; mirrors its structure, error handling, docstring style,
and fail-open contract byte-for-byte).

**Resolution reused, not reinvented.** The replacement path is found via
the SAME rung the shim itself already tries first (a coordinator/bin path
relative to `_repo_root()`), then via `resolve_claude_klabauter_root()` (imported
from the shared `_engine_root` seam ALL other hooks in this repo already
use for engine-root resolution — see that module's own docstring; this
hook adds no second resolution idiom). No new ladder is invented.

Contract:
  stdin   — SessionStart JSON payload (unused — resolves everything from
            `__file__`/cwd, never trusts payload fields for a path).
  stdout  — NOTHING (registered `async: true` — this hook's whole value is
            the file-repair side effect, not context-bound output; mirrors
            the boot-sweep / doe-claude-root-registration hooks' own
            "no context-bound stdout -> async is correct" reasoning).
  exit 0  — ALWAYS. FAIL OPEN at every step, unconditionally: a SessionStart
            hook that raises greets every session with a stack trace, worse
            than a silent no-op. Every failure mode (no git repo, no
            existing hook file, unrecognized hook content, unresolvable
            replacement, unwritable file) degrades to a silent no-op.

Idempotence: only rewrites when (a) the CURRENTLY installed hook file
exists and is recognizably OUR shim (contains the
"coordinator coordinator-prepare-commit-msg hook" marker line — never
touches a hook this repair does not recognize as ours), (b) none of its
existing SCRIPT candidates currently resolve to a file on disk, AND (c) a
replacement candidate DOES resolve to a file on disk. A healthy,
already-resolving shim is read-only touched (one stat per candidate,
nothing written).

Spec backlink: root-caused during the 2026-08-07 commit-trailer-
non-optional investigation (see this repo's own dispatch sidecar for that
session for the measurement: 219/400 recent commits carried `Session-Id:`,
0 of the un-mechanized ones did).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path, PureWindowsPath

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
try:
    from _engine_root import resolve_claude_klabauter_root as _resolve_claude_klabauter_root
except Exception:
    # Defensive fallback — see session-start-register-doe-claude-root.py's
    # identical precedent for why an import failure must degrade quietly
    # rather than crash a SessionStart hook.
    def _resolve_claude_klabauter_root():  # type: ignore[no-redef]
        return None


_SHIM_MARKER = "coordinator coordinator-prepare-commit-msg hook"
_SCRIPT_RELATIVE = "coordinator/bin/coordinator-prepare-commit-msg"


def _git_hooks_dir(cwd: str) -> str:
    """`git rev-parse --git-path hooks`, scoped to `cwd`. Returns "" on any
    failure (git missing, not a repo, spawn error, timeout) — fail-open,
    matching every other resolver in this hook.

    Windows console-subprocess discipline: `CREATE_NO_WINDOW` suppresses the
    focus-stealing console flash under this hook's headless SessionStart
    parent; `getattr` degrades to a harmless `0` on macOS/Linux.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-path", "hooks"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    out = result.stdout.strip()
    if not out:
        return ""
    out_path = Path(out)
    if not out_path.is_absolute():
        out_path = Path(cwd) / out_path
    return str(out_path)


def _candidate_script_paths(repo_root: str) -> list[str]:
    """Same-shape candidates the shim itself already tries, PLUS
    `resolve_claude_klabauter_root()` as a new rung — the repair this hook exists to
    make. Order matters: the repo-local candidate is preferred (keeps a
    dev checkout self-contained when it genuinely has the file), the engine
    root is the fix for the post-migration case, and the installed-plugin
    path is the last resort — identical preference order to the shim's own
    three original rungs, with the engine-root rung inserted before the plugin
    rung (a live engine checkout is a better answer than a possibly-stale
    installed plugin mirror).
    """
    candidates = [str(Path(repo_root) / _SCRIPT_RELATIVE)]

    doe_root_pointer = Path.home() / ".claude" / ".doe-root"
    try:
        doe_root = doe_root_pointer.read_text(encoding="utf-8").strip()
    except Exception:
        doe_root = ""
    if doe_root:
        candidates.append(str(Path(doe_root) / _SCRIPT_RELATIVE))

    claude_klabauter_root = None
    try:
        claude_klabauter_root = _resolve_claude_klabauter_root()
    except Exception:
        claude_klabauter_root = None
    if claude_klabauter_root:
        candidates.append(str(Path(claude_klabauter_root) / _SCRIPT_RELATIVE))

    candidates.append(
        str(
            Path.home()
            / ".claude"
            / "plugins"
            / "coordinator-claude"
            / _SCRIPT_RELATIVE
        )
    )
    return candidates


def _first_existing(paths: list[str]) -> str:
    for p in paths:
        try:
            if Path(p).is_file():
                return p
        except Exception:
            continue
    return ""


def main() -> int:
    cwd = os.getcwd()

    hooks_dir = _git_hooks_dir(cwd)
    if not hooks_dir:
        return 0
    hook_path = Path(hooks_dir) / "prepare-commit-msg"

    try:
        if not hook_path.is_file():
            return 0
        text = hook_path.read_text(encoding="utf-8")
    except Exception:
        return 0

    if _SHIM_MARKER not in text:
        return 0  # not our shim — never touch a hook we don't recognize

    try:
        repo_root_result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        repo_root = (
            repo_root_result.stdout.strip()
            if repo_root_result.returncode == 0
            else ""
        )
    except Exception:
        repo_root = ""
    if not repo_root:
        return 0

    candidates = _candidate_script_paths(repo_root)

    # If the currently-embedded SCRIPT already resolves, do nothing — this
    # covers both "healthy shim, no drift" and "already repaired".
    import re

    existing_scripts = re.findall(r'SCRIPT="([^"]+)"', text)
    if any(_first_existing([p]) for p in existing_scripts):
        return 0

    replacement = _first_existing(candidates)
    if not replacement:
        return 0  # nothing resolves anywhere — fail open, leave as-is

    replacement = PureWindowsPath(replacement).as_posix()
    new_first_line_pattern = re.compile(r'SCRIPT="[^"]+"\n')
    new_text, count = new_first_line_pattern.subn(
        f'SCRIPT="{replacement}"\n', text, count=1
    )
    if count != 1:
        return 0

    try:
        hook_path.write_text(new_text, encoding="utf-8")
        current_mode = hook_path.stat().st_mode
        hook_path.chmod(current_mode | 0o111)
    except Exception:
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
