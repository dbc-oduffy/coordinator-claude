"""
_claude_home.py — canonical resolver for the Claude Central install location
and the coordinator settings home.

Single access point for every coordinator-side script and peer-repo install
script that needs to know where ~/.claude.json, ~/.claude/, and
~/.coordinator-claude-settings/ live. Honours CLAUDE_HOME as the $HOME
substitute and COORDINATOR_SETTINGS_HOME as the settings-home override so
test sandboxes, CI runners, and per-user-on-shared-machine setups can point
the entire resolution at an alternate root without polluting the operator's
real $HOME.

Filesystem layout (the resolved truth, not a target):
    $HOME/
      .claude.json        <-- Claude Code's config (a single file)
      .claude/            <-- Claude Central directory (Anthropic-owned)
        plugins/
        bin/
      .coordinator-claude-settings/   <-- coordinator settings home (durable substrate)
        machine-local/
        coordinator-whoami/
        .coordinator-venv/
        bin/
        setup/
        settings-manifest.md

CLAUDE_HOME is a $HOME *substitute*, not a .claude/ substitute. Setting
CLAUDE_HOME=/tmp/sandbox redirects:
    .claude.json   -> /tmp/sandbox/.claude.json
    .claude/       -> /tmp/sandbox/.claude/
    settings-home  -> /tmp/sandbox/.coordinator-claude-settings/

COORDINATOR_SETTINGS_HOME is a direct settings-home override (does not affect
.claude/ or .claude.json resolution).

This matches plugins/project-rag/scripts/_claude_config.py's semantics so the
two implementations stay coherent across the install chain.

Env-var precedence (most-specific first, matching machine-local-registry.md §4a):
  1. CLAUDE_HOME  — $HOME substitute (test sandboxes, CI, alt installs).
  2. HOME         — POSIX-canonical (Linux/macOS/git-bash/MSYS/WSL).
  3. USERPROFILE  — Windows-canonical fallback (native cmd.exe / PowerShell).
  4. Path.home()  — language-stdlib last resort.

Settings-home precedence:
  1. COORDINATOR_SETTINGS_HOME — direct settings-home override.
  2. ${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings — sibling to ~/.claude.

Note: MACHINE_LOCAL_REGISTRY_DIR is a DEEPER registry-dir override handled by
_machine_local.py::_registry_dir() (rung-1). settings_home() resolves the
HOME ROOT only — it does not read registry CONTENTS.

CLI usage (the form callers shell out to from bash/PowerShell/Node/etc.):

    claude-home home           # the $HOME analog (CLAUDE_HOME if set, else $HOME)
    claude-home path           # absolute path to ~/.claude.json
    claude-home dir            # absolute path to the ~/.claude directory
    claude-home machine-local  # absolute path to <settings-home>/machine-local/
                               #   (delegates to settings_home() seam — WORKING ALIAS)
    claude-home plugins        # absolute path to ~/.claude/plugins/
    claude-home settings-home  # absolute path to the coordinator settings home

Importable from Python callers that prefer not to shell out:

    from _claude_home import claude_home_dir, claude_config_path, settings_home
    base = claude_home_dir()          # the ~/.claude install directory
    cfg  = claude_config_path()       # ~/.claude.json
    sh   = settings_home()            # the coordinator settings home

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

Spec backlinks:
  coordinator/docs/wiki/machine-local-registry.md §4a
  docs/plans/2026-07-06-durable-substrate-to-settings-home.md § C1
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# One-time warning helpers for legacy machine-local homes
# ---------------------------------------------------------------------------

# Review: code-reviewer (F2) — split into two independent once-guards so that a divergence
# warning from _check_machine_local_divergence() cannot consume the once-guard for the
# legacy-fallback DEPRECATED warning emitted by machine_local_dir(). The two warning types
# have distinct semantics and must suppress independently.
_legacy_machine_local_divergence_warned: bool = False
_legacy_machine_local_deprecated_warned: bool = False


def _warn_machine_local_divergence_once(message: str) -> None:
    """Write *message* to stderr at most once per process lifetime.

    Used by _check_machine_local_divergence() to emit a loud-but-non-fatal
    warning when both machine-local homes exist with divergent realpaths.
    Silenced after the first call so repeated divergence checks do not flood
    stderr.

    Spec backlink: docs/plans/2026-07-06-durable-substrate-to-settings-home.md § C1
    """
    global _legacy_machine_local_divergence_warned
    if not _legacy_machine_local_divergence_warned:
        sys.stderr.write(message)
        _legacy_machine_local_divergence_warned = True


def _warn_machine_local_deprecated_once(message: str) -> None:
    """Write *message* to stderr at most once per process lifetime.

    Used by machine_local_dir() to emit a loud-but-non-fatal deprecation
    warning when the legacy ~/.claude/machine-local home is still in play.
    Silenced after the first call so repeated machine_local_dir() lookups
    do not flood stderr.

    Spec backlink: docs/plans/2026-07-06-durable-substrate-to-settings-home.md § C1
    """
    global _legacy_machine_local_deprecated_warned
    if not _legacy_machine_local_deprecated_warned:
        sys.stderr.write(message)
        _legacy_machine_local_deprecated_warned = True


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


def settings_home() -> Path:
    """Return the resolved coordinator settings home directory.

    This is the clone-independent directory that holds coordinator's durable
    per-machine substrate: machine-local registry, coordinator-whoami identity,
    .coordinator-venv, bin/ resolvers, setup/, and settings-manifest.md.

    It is a sibling to ~/.claude at the same directory level.

    Precedence (most-specific first):
      1. COORDINATOR_SETTINGS_HOME — explicit override (sandboxes/CI/XDG users).
         Must be non-empty and absolute; raises ValueError otherwise.
      2. ${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings — sibling to ~/.claude.

    Note: MACHINE_LOCAL_REGISTRY_DIR is a DEEPER registry-dir override handled
    by _machine_local.py::_registry_dir() (rung-1). This function resolves the
    settings HOME ROOT only — it does not read registry CONTENTS.

    Negative-spec:
      - Does NOT auto-honor XDG_CONFIG_HOME (breaks CLAUDE_HOME sandbox isolation;
        sibling-to-~/.claude semantics are deliberate — see design doc).
      - Does NOT read any file from the settings home (pure location lookup).

    Spec backlink: docs/plans/2026-07-06-durable-substrate-to-settings-home.md § C1
    """
    override = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if override is not None:
        if not override:
            raise ValueError(
                "COORDINATOR_SETTINGS_HOME is set but empty; "
                "unset it or provide an absolute path"
            )
        p = Path(override)
        if not p.is_absolute():
            raise ValueError(
                f"COORDINATOR_SETTINGS_HOME must be an absolute path; got {override!r}."
            )
        return p
    return home_dir() / ".coordinator-claude-settings"


def machine_local_dir() -> Path:
    """Return the resolved machine-local registry directory path.

    Prefers the new settings-home location; falls back to the legacy
    ~/.claude/machine-local path if only that location exists on disk.
    Never returns a non-existent legacy path — callers validate existence,
    as today.

    Resolution order (WORKING ALIAS with prefer-new-fallback-to-legacy):
      1. <settings-home>/machine-local (new)  — if it exists on disk.
      2. ~/.claude/machine-local (legacy)      — if it exists and new does not;
         emits a one-time deprecation warning naming both paths and the
         remediation script.
      3. <settings-home>/machine-local         — canonical, even if absent.

    The CLI path also runs a divergence check via _check_machine_local_divergence()
    before calling this function; on divergence (both exist, different realpaths)
    a warning is emitted there and this function then returns new (step 1).

    Use settings_home() for the settings-home root itself.

    Spec backlink: docs/plans/2026-07-06-durable-substrate-to-settings-home.md § C1
    """
    new = settings_home() / "machine-local"
    legacy = claude_home_dir() / "machine-local"
    if new.exists():
        return new
    if legacy.exists():
        _warn_machine_local_deprecated_once(
            "claude-home machine-local: DEPRECATED LEGACY HOME IN USE\n"
            "\n"
            "~/.claude/machine-local exists but <settings-home>/machine-local\n"
            "does not. This process is using the legacy home. Run the one-time\n"
            "migration to eliminate this warning:\n"
            "\n"
            "Remediation — run the one-time migration to consolidate both homes:\n"
            "    coordinator/lib/migrate-substrate-to-settings-home.sh\n"
            "\n"
            f"  Legacy path : {legacy}\n"
            f"  New    path : {new}\n"
        )
        return legacy
    return new


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
# Divergence guard for machine-local homes
# ---------------------------------------------------------------------------


def _check_machine_local_divergence() -> None:
    """Warn loud if both legacy and new machine-local homes exist with divergent realpaths.

    Checks two locations:
      Legacy: claude_home_dir() / "machine-local"   (~/.claude/machine-local)
      New:    settings_home()   / "machine-local"   (<settings-home>/machine-local)

    Returns silently when:
      - The legacy path does not exist, OR
      - The new path does not exist, OR
      - Both exist and Path.resolve() produces the same canonical path
        (compat-symlink case — not a divergent second home).

    Emits a one-time loud deprecation warning (via _warn_legacy_machine_local_once)
    when both exist AND their resolved (realpath) paths differ, then returns normally.
    The process continues and deterministically prefers the settings-home (new) path
    via machine_local_dir(). This replaces the former sys.exit(1) to accommodate
    mid-migration boxes where both homes exist but the registry is working fine.

    CRITICAL: comparison is by resolved path, not lexical path. A compat
    symlink at ~/.claude/machine-local → <settings-home>/machine-local resolves
    to the SAME realpath and MUST NOT trigger a warning.

    Spec backlink: docs/plans/2026-07-06-durable-substrate-to-settings-home.md § C1
    """
    legacy = claude_home_dir() / "machine-local"
    new = settings_home() / "machine-local"

    if not legacy.exists() or not new.exists():
        return  # one or both absent — no divergence possible

    rp_legacy = legacy.resolve()
    rp_new = new.resolve()

    if rp_legacy != rp_new:
        _warn_machine_local_divergence_once(
            "claude-home machine-local: DIVERGENT MACHINE-LOCAL HOMES"
            " — CONTINUING, preferring settings-home (new)\n"
            "\n"
            "Both ~/.claude/machine-local and <settings-home>/machine-local\n"
            "exist and point at different content homes. This process is\n"
            "continuing and will deterministically use the settings-home\n"
            "(new) location. Run the one-time migration to eliminate this\n"
            "warning:\n"
            "\n"
            "Remediation — run the one-time migration to consolidate both homes:\n"
            "    coordinator/lib/migrate-substrate-to-settings-home.sh\n"
            "\n"
            f"  Legacy realpath : {rp_legacy}\n"
            f"  New    realpath : {rp_new}\n"
        )


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
    "Usage: claude-home {home|path|dir|machine-local|plugins|coordinator-root|settings-home}\n"
    "  home             Absolute path to the $HOME analog (CLAUDE_HOME if set, else $HOME)\n"
    "  path             Absolute path to ~/.claude.json\n"
    "  dir              Absolute path to the ~/.claude directory\n"
    "  machine-local    Absolute path to <settings-home>/machine-local/\n"
    "                   (delegates to settings_home() seam — WORKING ALIAS)\n"
    "  plugins          Absolute path to ~/.claude/plugins/\n"
    "  coordinator-root For-content coordinator root (CLAUDE_PLUGIN_ROOT > COORDINATOR_ROOT >\n"
    "                   flat ~/.claude/plugins/coordinator-claude/coordinator).\n"
    "                   For full precedence including registry/cache, use:\n"
    "                   resolve-coordinator-clone.sh --for-content\n"
    "  settings-home    Absolute path to the coordinator settings home\n"
    "                   (COORDINATOR_SETTINGS_HOME > ${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings)\n"
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
        # Delegate to the settings-home seam with divergence guard.
        # Review: code-reviewer (F1) — updated to reflect post-softening behavior.
        # Warns loud and continues if both homes exist with different realpaths; deterministically prefers new.
        _check_machine_local_divergence()
        print(machine_local_dir())
        return 0
    if cmd == "plugins":
        print(plugins_dir())
        return 0
    if cmd == "coordinator-root":
        print(coordinator_root())
        return 0
    if cmd == "settings-home":
        print(settings_home())
        return 0
    sys.stderr.write(f"claude-home: unknown subcommand {cmd!r}\n")
    sys.stderr.write(_USAGE)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
