"""
_claude_home.py — canonical resolver for the Claude Central install location.

Single access point for every coordinator-side script and peer-repo install
script that needs to know where ~/.claude.json and ~/.claude/ live. Honours
the CLAUDE_HOME environment variable as the deliberate audited override so
test sandboxes, CI runners, and per-user-on-shared-machine setups can point
the entire resolution at an alternate root without polluting the operator's
real $HOME.

Filesystem layout (the resolved truth, not a target):
    $HOME/
      .claude.json        <-- Claude Code's config (a single file)
      .claude/            <-- Claude Central directory
        machine-local/
        plugins/
        bin/

CLAUDE_HOME is a $HOME *substitute*, not a .claude/ substitute. Setting
CLAUDE_HOME=/tmp/sandbox redirects:
    .claude.json  -> /tmp/sandbox/.claude.json
    .claude/      -> /tmp/sandbox/.claude/
    machine-local -> /tmp/sandbox/.claude/machine-local/
    plugins       -> /tmp/sandbox/.claude/plugins/

This matches plugins/project-rag/scripts/_claude_config.py's semantics so the
two implementations stay coherent across the install chain.

Env-var precedence (most-specific first, matching machine-local-registry.md §4a):
  1. CLAUDE_HOME  — $HOME substitute (test sandboxes, CI, alt installs).
  2. HOME         — POSIX-canonical (Linux/macOS/git-bash/MSYS/WSL).
  3. USERPROFILE  — Windows-canonical fallback (native cmd.exe / PowerShell).
  4. Path.home()  — language-stdlib last resort.

CLI usage (the form callers shell out to from bash/PowerShell/Node/etc.):

    claude-home home           # the $HOME analog (CLAUDE_HOME if set, else $HOME)
    claude-home path           # absolute path to ~/.claude.json
    claude-home dir            # absolute path to the ~/.claude directory
    claude-home machine-local  # absolute path to ~/.claude/machine-local/
    claude-home plugins        # absolute path to ~/.claude/plugins/

Importable from Python callers that prefer not to shell out:

    from _claude_home import claude_home_dir, claude_config_path
    base = claude_home_dir()          # the ~/.claude install directory
    cfg = claude_config_path()        # ~/.claude.json

JSON read/write helpers for ~/.claude.json (generic primitives for any
install script that touches the config; atomic-write semantics + BOM-tolerant
read + JSONDecodeError enriched with file path):

    from _claude_home import read_config, write_config
    data = read_config()              # {} if file absent
    data["mcpServers"]["my-server"] = {...}
    write_config(data)                # atomic; tempfile + rename

Higher-level shape-specific helpers (e.g., updating a specific mcpServers
entry under global vs per-project) stay in the consumer — they do not
generalize and belong with the install script that owns them.

Spec backlink: coordinator/docs/wiki/machine-local-registry.md §4a
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def home_dir() -> Path:
    """Return the resolved $HOME analog.

    This is the directory that CONTAINS both .claude.json and .claude/.
    See module docstring for the precedence chain.

    Each env-var candidate must be an absolute path. CLAUDE_HOME is the
    deliberate operator override and a malformed value is a configuration
    error — we fail loud rather than silently treat it as relative-to-cwd.
    HOME / USERPROFILE come from the OS; a relative value (rare, but
    possible with adversarial or broken parent processes) is ignored and
    the next candidate is tried. This prevents an env-derived relative
    path from anchoring later joins like ``home_dir() / ".claude" / ...``
    at the process cwd instead of a true home directory.
    """
    claude_home = os.environ.get("CLAUDE_HOME")
    if claude_home is not None:
        # Review: code-reviewer — empty-string CLAUDE_HOME (e.g. from `CLAUDE_HOME=` in CI)
        # is set-but-malformed; treat as config error, not silent fallthrough.
        if not claude_home:
            raise ValueError(
                "CLAUDE_HOME is set but empty; unset it or provide an absolute path"
            )
        p = Path(claude_home)
        if not p.is_absolute():
            # Review: code-reviewer — drive-relative paths (e.g. "C:foo") are not
            # absolute on Windows; mention explicitly for operator clarity.
            raise ValueError(
                f"CLAUDE_HOME must be an absolute path; got {claude_home!r}. "
                "(On Windows, drive letter alone is insufficient — use 'C:\\\\...' form.)"
            )
        return p

    home = os.environ.get("HOME")
    if home:
        p = Path(home)
        if p.is_absolute():
            return p

    userprofile = os.environ.get("USERPROFILE")
    if userprofile:
        p = Path(userprofile)
        if p.is_absolute():
            return p

    return Path.home()


def claude_home_dir() -> Path:
    """Return the resolved ~/.claude/ directory (Claude Central install)."""
    return home_dir() / ".claude"


def claude_config_path() -> Path:
    """Return the resolved ~/.claude.json path (Claude Code config file)."""
    return home_dir() / ".claude.json"


def machine_local_dir() -> Path:
    """Return the resolved ~/.claude/machine-local/ path."""
    return claude_home_dir() / "machine-local"


def plugins_dir() -> Path:
    """Return the resolved ~/.claude/plugins/ path."""
    return claude_home_dir() / "plugins"


def coordinator_root() -> Path:
    """Return the for-content coordinator root (highest-precedence readable payload).

    Mirrors the precedence chain of resolve-coordinator-clone.sh --for-content
    but without the registry/cache tiers that require external tooling. This
    subset is safe to call from any Python context without spawning bash.

    Precedence (Python-accessible tiers only):
      1. CLAUDE_PLUGIN_ROOT env var — harness / test sandbox injection wins.
      2. COORDINATOR_ROOT env var — explicit content-root override.
      3. Flat layout: ~/.claude/plugins/coordinator-claude/coordinator

    For full precedence (including registry live_path and versioned-cache glob),
    use the bash CLI: resolve-coordinator-clone.sh --for-content

    Primary Python consumer: coordinator/whoami/.../probes.py (coordinator root
    discovery for session-init and doctor probes).

    Spec backlink: docs/plans/2026-06-23-coordinator-install-surface-dogfood-hardening.md § C2a

    Negative-spec:
      - Does NOT read the registry (avoids spawning a subprocess from Python).
      - Does NOT glob the versioned cache (the bash CLI owns that logic).
      - Does NOT fail-loud — returns the flat-layout path even if it does not
        exist on disk; callers validate existence when they need to.
    """
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin_root:
        return Path(plugin_root)

    coordinator_root_env = os.environ.get("COORDINATOR_ROOT")
    if coordinator_root_env:
        return Path(coordinator_root_env)

    return plugins_dir() / "coordinator-claude" / "coordinator"


# ---------------------------------------------------------------------------
# JSON read / write for ~/.claude.json
# ---------------------------------------------------------------------------
#
# These are generic primitives that any install script touching ~/.claude.json
# needs (atomic write, BOM-tolerant read, JSONDecodeError enriched with the
# file path). They live here, not in each consumer, so the read/write contract
# stays consistent across the coordinator install chain.
#
# Higher-level operations (e.g., updating a specific mcpServers entry) stay
# in the consumer — they have shape-specific logic (global vs per-project,
# key-collision policy) that doesn't generalize.


def read_config() -> dict[str, Any]:
    """Read and parse ~/.claude.json; return empty dict if the file is absent.

    UTF-8 BOM is tolerated (common from Windows editors that prepend U+FEFF).

    Raises:
        json.JSONDecodeError: if the file exists but contains malformed JSON.
            The exception message is enriched with the file path to aid
            diagnosis — the stdlib error alone names line+column but not file.
    """
    cfg = claude_config_path()
    if not cfg.exists():
        return {}
    try:
        with cfg.open(encoding="utf-8-sig") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise json.JSONDecodeError(
            f"~/.claude.json at {cfg} is not valid JSON: {exc.msg}",
            exc.doc,
            exc.pos,
        ) from exc


def write_config(data: dict[str, Any]) -> None:
    """Atomically write *data* to ~/.claude.json via tempfile + rename.

    The parent directory is created if it does not exist. The write is
    atomic on POSIX (os.replace is rename(2)); on Windows the same call
    replaces the destination atomically when both paths are on the same
    volume (which they always are here — both live in the same directory).

    Temp files are cleaned up on failure so no `.claude.json.*.tmp` files
    accumulate from interrupted writes.

    Args:
        data: The complete config dict to serialise as JSON. Whole-file
            overwrite — the caller is responsible for read-modify-write
            if preserving existing keys matters.
    """
    cfg = claude_config_path()
    cfg.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp = tempfile.mkstemp(dir=str(cfg.parent), prefix=".claude.json.", suffix=".tmp")
    os.close(fd)
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, str(cfg))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


_USAGE = (
    "Usage: claude-home {home|path|dir|machine-local|plugins|coordinator-root}\n"
    "  home             Absolute path to the $HOME analog (CLAUDE_HOME if set, else $HOME)\n"
    "  path             Absolute path to ~/.claude.json\n"
    "  dir              Absolute path to the ~/.claude directory\n"
    "  machine-local    Absolute path to ~/.claude/machine-local/\n"
    "  plugins          Absolute path to ~/.claude/plugins/\n"
    "  coordinator-root For-content coordinator root (CLAUDE_PLUGIN_ROOT > COORDINATOR_ROOT >\n"
    "                   flat ~/.claude/plugins/coordinator-claude/coordinator).\n"
    "                   For full precedence including registry/cache, use:\n"
    "                   resolve-coordinator-clone.sh --for-content\n"
)


def _main(argv: list[str]) -> int:
    if len(argv) != 2:
        sys.stderr.write(_USAGE)
        return 2
    cmd = argv[1]
    if cmd == "home":
        print(home_dir())
        return 0
    if cmd == "path":
        print(claude_config_path())
        return 0
    if cmd == "dir":
        print(claude_home_dir())
        return 0
    if cmd == "machine-local":
        print(machine_local_dir())
        return 0
    if cmd == "plugins":
        print(plugins_dir())
        return 0
    if cmd == "coordinator-root":
        print(coordinator_root())
        return 0
    sys.stderr.write(f"claude-home: unknown subcommand {cmd!r}\n")
    sys.stderr.write(_USAGE)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
