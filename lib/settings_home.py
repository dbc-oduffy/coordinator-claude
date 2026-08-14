# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""settings_home.py — coordinator settings-home resolution helpers.

Import this module (do NOT invoke it as a subprocess when an in-process
caller is available — the --print-home CLI mode below exists only for bash
callers that cannot import Python in-process). Consumed by
install-substrate.py, coordinator-doctor-sentinel.py, cruft-sweep, and any
other script that needs the settings-home path.

Provides:
  settings_home()                 — the absolute settings-home root
  settings_home_realpath(path)    — canonical (fully symlink-resolved) path
  check_machine_local_divergence() — raise if both machine-local homes exist
                                      with divergent realpaths

Precedence (most-specific first):
  COORDINATOR_SETTINGS_HOME  — explicit override (sandboxes/CI/XDG users)
  CLAUDE_HOME, falling back to the platform home directory (Path.home() —
    USERPROFILE on Windows, HOME or the passwd entry on POSIX), with
    `.coordinator-claude-settings` appended — sibling to ~/.claude

Both env overrides must name an absolute (rooted) path; a relative value is a
configuration error and raises ValueError rather than silently anchoring the
settings home at the process cwd.

Note: MACHINE_LOCAL_REGISTRY_DIR is a DEEPER registry-dir override handled by
_machine_local.py::_registry_dir() (rung-1). This module resolves the
settings HOME ROOT only — it does not read registry CONTENTS.

Spec backlink: DoE-claude:pln-relocate-durable-coordinator-s-d48415 § C1
RAG-bait: coordinator settings-home resolution seam; COORDINATOR_SETTINGS_HOME
          env var; machine-local divergence fail-loud guard

DR-072: durable, per-machine coordinator state lives in settings-home, not the
resettable/synced ~/.claude tree — see
docs/decisions/DR-072-durable-machine-local-coordinator-state-lives-in-settings-home-not-claude.md
and its predecessor DR-071-durable-coordinator-root-anchor-settings-home-registry-doe-root-demoted-to-cache.md.
See also docs/wiki/state-placement-law.md § Surfaces That Deliberately Stay in ~/.claude
and docs/wiki/machine-local-registry.md § 4e.

Port backlink: docs/plans/2026-07-19-debash-coordinator-windows.md (E3-e,
  naked-python port).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


class MachineLocalDivergence(Exception):
    """Raised when both machine-local homes exist and their realpaths diverge."""


def _require_rooted(var: str, raw: str) -> str:
    """Return *raw* unchanged, or raise ValueError if it would anchor at the cwd.

    A rooted path ('/srv/x', 'C:\\Users\\x', '\\\\server\\share') is accepted; a
    relative one ('foo', 'C:foo') is not. On Windows a drive letter alone is
    NOT absolute — 'C:foo' means "foo relative to the cwd on drive C:" — so the
    check is `is_absolute() or root`, which accepts a POSIX-style rooted path
    under a Windows interpreter while still rejecting the drive-relative form.

    Ported from lib/claude-home/_claude_home.py::home_dir/settings_home, which
    already validated both overrides. Empty is NOT an error here: an empty
    override is treated as unset by every caller of this module and is pinned
    that way by coordinator_core/tests/test_settings_home.py — that contract is
    deliberately left alone; only the cwd-relative foot-gun is closed.
    """
    p = Path(raw)
    if not (p.is_absolute() or p.root):
        raise ValueError(
            f"{var} must be an absolute path; got {raw!r}. "
            "(On Windows, a drive letter alone is insufficient — use 'C:\\...' form.)"
        )
    return raw


def home_dir() -> str:
    """Return the resolved $HOME analog: CLAUDE_HOME, else the platform home.

    Mirrors `coordinator_core._settings_home`'s semantics exactly, which resolve
    the platform home via `Path.home()` rather than reading `$HOME` directly.
    That distinction is the whole point: `$HOME` is a POSIX convention that
    native Windows shells (PowerShell, cmd.exe) do not set, so a literal
    `${CLAUDE_HOME:-$HOME}` transliteration resolves to the empty string there
    and yields a cwd-relative settings home. `Path.home()` consults USERPROFILE
    on Windows and HOME (then the passwd entry) on POSIX, so it is correct on
    both. See coordinator_core/trusted_root_guard.py::_home_from_env for the
    same trap fixed in the guard.
    """
    claude_home = os.environ.get("CLAUDE_HOME", "")
    if claude_home:
        return _require_rooted("CLAUDE_HOME", claude_home)
    return str(Path.home())


def settings_home() -> str:
    """Return the absolute settings-home root path. No side effects.

    Precedence:
      COORDINATOR_SETTINGS_HOME (if non-empty) -> use verbatim
      else <home_dir()>/.coordinator-claude-settings
    """
    override = os.environ.get("COORDINATOR_SETTINGS_HOME", "")
    if override:
        return _require_rooted("COORDINATOR_SETTINGS_HOME", override)
    return os.path.join(home_dir(), ".coordinator-claude-settings")


def settings_home_realpath(path: str) -> str:
    """Resolve a path to its canonical (fully symlink-resolved) form."""
    return os.path.realpath(path)


def _is_absent_or_empty_husk(path: str) -> bool:
    """True when `path` carries no machine-local state — absent, or a directory
    left behind empty by a completed migration.

    An empty directory is not a second content home: nothing can be read from
    it, so treating it as one turns a finished migration into a fail-loud.
    An unreadable directory counts as no-state too — it yields no content to
    diverge over.
    """
    try:
        if not os.path.exists(path):
            return True
        return not os.listdir(path)
    except OSError:
        return True


def check_machine_local_divergence() -> None:
    """Fail loud if BOTH machine-local homes exist AND their realpaths differ.

    No-op (returns) in all safe states:
      - Legacy ~/.claude/machine-local absent or an empty post-migration husk, OR
      - New <settings-home>/machine-local absent or an empty husk, OR
      - Both exist AND realpaths are equal (compat symlink — NOT a second home).

    Raises MachineLocalDivergence when both exist AND realpaths diverge. Never
    silently picks one; the operator must run the migration to resolve.

    CRITICAL: realpath comparison prevents a false positive on the compat
    layer (C3): a symlink at ~/.claude/machine-local -> <settings-home>/machine-local
    resolves to the same realpath and MUST NOT trigger fail-loud.
    """
    legacy = os.path.join(home_dir(), ".claude", "machine-local")
    new = os.path.join(settings_home(), "machine-local")

    # Fast path: if either side holds no state there is no divergence.
    if _is_absent_or_empty_husk(legacy) or _is_absent_or_empty_husk(new):
        return

    rp_legacy = settings_home_realpath(legacy)
    rp_new = settings_home_realpath(new)

    if rp_legacy != rp_new:
        msg = (
            "coordinator-settings-home: DIVERGENT MACHINE-LOCAL HOMES — cannot safely resolve.\n"
            "\n"
            "Both ~/.claude/machine-local and <settings-home>/machine-local exist and point\n"
            "at different content homes. Reading from either risks using stale or incomplete\n"
            "registry data.\n"
            "\n"
            "Remediation — re-run /coordinator:install (the substrate->settings-home\n"
            "migration is now performed natively by the coordinator install step).\n"
            "\n"
            "Or, if you know which home is authoritative, set COORDINATOR_SETTINGS_HOME to\n"
            "point at the desired settings home and then remove or symlink the other:\n"
            "    export COORDINATOR_SETTINGS_HOME=/path/to/settings-home\n"
            f"  Legacy realpath : {rp_legacy}\n"
            f"  New    realpath : {rp_new}\n"
        )
        raise MachineLocalDivergence(msg)


def _cli(argv: list[str]) -> int:
    if not argv or argv[0] == "--print-home":
        print(settings_home())
        return 0
    if argv[0] == "--check-divergence":
        try:
            check_machine_local_divergence()
        except MachineLocalDivergence as exc:
            print(str(exc), file=sys.stderr)
            return 1
        return 0
    if argv[0] == "--realpath":
        if len(argv) < 2:
            print("usage: settings_home.py --realpath <path>", file=sys.stderr)
            return 1
        print(settings_home_realpath(argv[1]))
        return 0
    print(f"unknown mode: {argv[0]}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
