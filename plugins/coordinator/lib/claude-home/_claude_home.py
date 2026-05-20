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
    """
    claude_home = os.environ.get("CLAUDE_HOME")
    if claude_home:
        return Path(claude_home)

    home = os.environ.get("HOME")
    if home:
        return Path(home)

    userprofile = os.environ.get("USERPROFILE")
    if userprofile:
        return Path(userprofile)

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
    "Usage: claude-home {home|path|dir|machine-local|plugins}\n"
    "  home           Absolute path to the $HOME analog (CLAUDE_HOME if set, else $HOME)\n"
    "  path           Absolute path to ~/.claude.json\n"
    "  dir            Absolute path to the ~/.claude directory\n"
    "  machine-local  Absolute path to ~/.claude/machine-local/\n"
    "  plugins        Absolute path to ~/.claude/plugins/\n"
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
    sys.stderr.write(f"claude-home: unknown subcommand {cmd!r}\n")
    sys.stderr.write(_USAGE)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
