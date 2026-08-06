#!/usr/bin/env python3
# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""resolve-coordinator-clone.py — unified coordinator install-root resolver.

Unified resolver for the coordinator install-root (2026-07-21 de-bash
campaign, Wave E2 chunk E2-c). Two verbs, selected via
--clone-root/--content-root (legacy aliases --for-git-ops/--for-content,
retained for the live cross-repo contract — see "Public contract surface"
below):

  --clone-root (alias: --for-git-ops)
                  The .git-backed clone directory. Required for operations
                  that must address the git history (drift probe, git log,
                  refresh-plugin-live-install.py). Fails loud if no clone
                  with a .git directory can be located.

  --content-root (alias: --for-content)
                  Highest-precedence readable payload directory. Preferred
                  for loading libs, agents, snippets, query-records.js, etc.
                  A contributor's live dev-loop clone wins over any cache so
                  in-progress edits stay authoritative; the versioned cache is
                  the fallback for fleet/CI installs.

Precedence — mirrors the retired bash oracle exactly (both verbs share the
Rung-0 dev-vs-oss source-mode selector; each verb keeps its own mode-specific
rung bodies, since git-ops gates oss on .git while content gates oss on the
.claude-plugin/plugin.json manifest marker):

  --clone-root (dev/passthrough mode):
    1. COORDINATOR_CLONE env var (non-empty, must have .git/)
    2. registry repos.doe_claude (canonical), then
       plugin.mirrors.coordinator-claude.live_path (fallback)
    3. Pointer file (settings-home durable, then legacy ~/.claude/.doe-root)
       -> DoE repo root, gated on -d <root>/.git
    4. Flat layout: ~/.claude/plugins/coordinator-claude, gated on .git/
    5. FAIL-LOUD

  --clone-root (oss mode): ONLY the flat marketplace clone IF it has .git/;
    a byte-copy marketplace install has no .git and legitimately fails loud
    here (does NOT fall through to the dev rungs above).

  --content-root (dev/passthrough mode):
    1. CLAUDE_PLUGIN_ROOT env var
    2. COORDINATOR_ROOT env var
    3. registry plugin.mirrors.coordinator-claude.live_path
    4. Versioned cache: newest semver dir under
       ~/.claude/plugins/cache/coordinator-claude/coordinator/*/
    5. Pointer file -> <root>/coordinator, gated on -d <root>/coordinator
    6. Flat layout: ~/.claude/plugins/coordinator-claude, gated on the
       .claude-plugin/plugin.json manifest marker
    7. FAIL-LOUD

  --content-root (oss mode): versioned cache rung then the flat manifest
    rung only; fails loud if neither resolves (does NOT fall through to the
    dev rungs).

Dev-vs-oss selector (shared Rung-0, run before either verb's ladder):
  1. PASSTHROUGH — an existing public env override pinned (COORDINATOR_CLONE
     for git-ops; CLAUDE_PLUGIN_ROOT or COORDINATOR_ROOT for content) wins
     unconditionally, regardless of COORDINATOR_SOURCE_MODE.
  2. Explicit COORDINATOR_SOURCE_MODE=dev|oss (any other value fails loud).
  3. Marker auto-discovery: a resolvable candidate clone (pointer file, then
     registry repos.doe_claude, then registry live_path) carrying
     .coordinator-dev-repo -> dev, unconditionally. A resolvable candidate
     WITHOUT the marker AND a co-present OSS install (flat
     .claude-plugin/plugin.json) -> fail-loud ambiguity (set
     COORDINATOR_SOURCE_MODE to disambiguate). OSS install present, no
     ambiguity -> oss. Resolvable candidate, no OSS present -> dev
     (unmarked-but-sole-candidate; nothing to disambiguate against). Neither
     resolves -> fail-loud no-source.

CLI usage: prints the resolved path to stdout, exits non-zero (loud message
on stderr) on resolution failure.

Retired scope: the bash oracle's SOURCED mode (setting
COORDINATOR_CLONE/COORDINATOR_CONTENT_ROOT directly in a caller's shell
scope) has no callers left post-port — its in-tree bash sourcers were
repointed to invoke this CLI directly in the same commit that ported this
file. This CLI-only shape needed no trusted-root-guard carry-over: that guard
in the bash oracle applied ONLY to the sourced-mode CLAUDE_PLUGIN_ROOT
restore step, never to standalone CLI-mode resolution — it retired with
sourced mode, not silently dropped.

Public contract surface: CLI entrypoint (this file) and env-var overrides
are stable. Peer repos (project-rag, project-rag-ue-addon,
Example-game-workbench-repo) bind here via an out-of-tree entry shim rather than
each vendoring a cache-glob fallback.
Spec backlink: docs/plans/2026-07-09-resolver-unification-v3split-01.md § C2
Spec backlink: docs/plans/2026-07-19-debash-coordinator-windows.md § Wave E2 (E2-c)
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ImportError:  # pragma: no cover - older interpreter fallback
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:  # pragma: no cover - tomllib unavailable
        tomllib = None  # type: ignore[assignment]

# coordinator_core import bootstrap — this script runs as a subprocess-invoked
# CLI (not an in-process library import), so plain `import coordinator_core`
# fails: sys.path[0] is this file's own directory, not the repo root a pip -e
# install or pytest rootdir would put on sys.path. Mirrors
# check-install-singularity.py's identical bootstrap.
_LIB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin", "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)


def _import_registry_get():
    """Resolve CLAUDE_KLABAUTER_ROOT and import the canonical settings-home registry
    reader. Returns None (not raises) on any resolution failure — this is an
    advisory fallback rung (see `_registry_live_path`), never a hard
    dependency."""
    try:
        from cc_invoke import _resolve_claude_klabauter_root
    except ImportError:
        return None
    try:
        claude_klabauter_root = _resolve_claude_klabauter_root()
    except Exception:
        return None
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    try:
        from coordinator_core.machine_resolver import registry_get
    except ImportError:
        return None
    return registry_get


class ResolutionError(Exception):
    """Raised with the fail-loud message(s) to print to stderr."""


# ---------------------------------------------------------------------------
# Home / settings-home resolution — mirrors _rcc_claude_home_dir and
# settings_home.py::_coordinator_settings_home.
# ---------------------------------------------------------------------------

def _claude_home_dir() -> str:
    home = os.environ.get("CLAUDE_HOME") or os.environ.get("HOME") or os.environ.get("USERPROFILE")
    if not home:
        return ""
    return str(Path(home) / ".claude")


def _settings_home_dir() -> str:
    override = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if override:
        return override
    home = os.environ.get("CLAUDE_HOME") or os.environ.get("HOME") or os.environ.get("USERPROFILE")
    if not home:
        return ""
    return str(Path(home) / ".coordinator-claude-settings")


# ---------------------------------------------------------------------------
# Registry access — mirrors _rcc_registry_path / _rcc_registry_doe_claude /
# _rcc_registry_live_path. Shells out to `claude-home`/`machine-local` on
# PATH exactly like the bash oracle did (test fixture parity:
# test_resolve_coordinator_clone.py::test_t3 stubs `claude-home` on PATH,
# not a Python registry reader).
# ---------------------------------------------------------------------------

def _registry_path() -> str:
    """Resolve registry.local.toml via `claude-home machine-local` (external
    tool, preserved for test-fixture parity — test_resolve_coordinator_clone.py::test_t3
    stubs this binary on PATH, not a Python registry reader). Returns "" when
    the tool is unavailable — `_registry_live_path` then falls through to
    `coordinator_core.machine_resolver.registry_get` rather than re-deriving
    settings-home here.

    Negative-spec: this used to also carry an inline settings-home fallback
    (`<settings-home>/machine-local/registry.local.toml`, hand-built and
    `.local`-only) for when `claude-home` was absent. That fallback silently
    missed the tracked `registry.toml` and treated an empty-string tracked
    declaration as a real value's absence rather than a genuine miss. Do not
    re-introduce a hand-rolled settings-home path here — `registry_get` is
    the single canonical resolver for that rung.
    """
    claude_home_bin = shutil.which("claude-home")
    if claude_home_bin:
        try:
            result = subprocess.run(
                [claude_home_bin, "machine-local"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            reg_dir = result.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            reg_dir = ""
        if reg_dir:
            return str(Path(reg_dir) / "registry.local.toml")
    return ""


def _registry_doe_claude() -> str:
    machine_local_bin = shutil.which("machine-local")
    if not machine_local_bin:
        return ""
    try:
        result = subprocess.run(
            [machine_local_bin, "get", "repos.doe_claude"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip()


def _registry_live_path() -> str:
    """coordinator-claude live_path, preferring the `claude-home`-resolved
    registry.local.toml (test-fixture-parity rung, see `_registry_path`),
    falling through to the canonical settings-home registry
    (`coordinator_core.machine_resolver.registry_get` — registry.local.toml
    before registry.toml, empty-string is a miss) when that rung is
    unavailable or yields no value."""
    reg_path = _registry_path()
    if reg_path and tomllib is not None and Path(reg_path).is_file():
        try:
            data = tomllib.loads(Path(reg_path).read_text(encoding="utf-8"))
        except Exception:
            data = None
        if data is not None:
            nested = data.get("plugin", {}).get("mirrors", {}).get("coordinator-claude", {})
            if isinstance(nested, dict):
                live = nested.get("live_path", "")
                if live:
                    return live

            key = "plugin.mirrors.coordinator-claude.live_path"
            val = data.get(key, "")
            if val:
                return val

    registry_get = _import_registry_get()
    if registry_get is None:
        return ""
    return registry_get("plugin.mirrors.coordinator-claude.live_path") or ""


# ---------------------------------------------------------------------------
# Doe-root pointer — mirrors read_doe_root_pointer.py::coordinator_read_doe_root_pointer.
# Durable-first (DR-072): settings-home pointer, falling back to the legacy
# ~/.claude/.doe-root during the transition window.
# ---------------------------------------------------------------------------

def _read_doe_root_pointer() -> str:
    settings_home = _settings_home_dir()
    if settings_home:
        try:
            root = (Path(settings_home) / "machine-local" / ".doe-root").read_text(encoding="utf-8").strip()
            if root:
                return root
        except OSError:
            pass

    claude_home = _claude_home_dir()
    if claude_home:
        try:
            root = (Path(claude_home) / ".doe-root").read_text(encoding="utf-8").strip()
            if root:
                return root
        except OSError:
            pass

    return ""


# ---------------------------------------------------------------------------
# Versioned cache — mirrors _rcc_newest_cache. Numeric (not lexicographic)
# semver compare so 2.10.0 beats 2.9.0 — DR-148 parity with the bash loop.
# ---------------------------------------------------------------------------

_VERSION_RE = re.compile(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?")


def _version_key(dirname: str) -> tuple[int, int, int]:
    m = _VERSION_RE.match(dirname)
    if not m:
        return (0, 0, 0)
    a, b, c = m.groups()
    return (int(a or 0), int(b or 0), int(c or 0))


def _newest_cache() -> str:
    claude_home = _claude_home_dir()
    if not claude_home:
        return ""
    cache_parent = Path(claude_home) / "plugins" / "cache" / "coordinator-claude" / "coordinator"
    if not cache_parent.is_dir():
        return ""

    best_dir = ""
    best_key = (0, 0, 0)
    for entry in cache_parent.iterdir():
        if not entry.is_dir():
            continue
        key = _version_key(entry.name)
        # Strict '>' mirrors the bash loop's cascading -gt semantics: a
        # 0.0.0 (or unparseable) dirname never wins.
        if key > best_key:
            best_dir = str(entry)
            best_key = key
    return best_dir


# ---------------------------------------------------------------------------
# Dev-vs-oss source-mode selector — mirrors _rcc_resolve_source_mode.
# ---------------------------------------------------------------------------

def _resolve_source_mode(verb: str) -> str:
    if verb == "git-ops":
        if os.environ.get("COORDINATOR_CLONE"):
            return "passthrough"
    elif verb == "content":
        if os.environ.get("CLAUDE_PLUGIN_ROOT") or os.environ.get("COORDINATOR_ROOT"):
            return "passthrough"
    else:  # pragma: no cover - defense in depth, both call sites are literals
        raise ResolutionError(f'resolve-coordinator-clone: internal error — unknown verb "{verb}"')

    source_mode = os.environ.get("COORDINATOR_SOURCE_MODE")
    if source_mode:
        if source_mode in ("dev", "oss"):
            return source_mode
        raise ResolutionError(
            f'resolve-coordinator-clone: COORDINATOR_SOURCE_MODE is set to "{source_mode}" but must be "dev" or "oss"'
        )

    candidate = _read_doe_root_pointer() or _registry_doe_claude() or _registry_live_path()
    candidate_resolved = bool(candidate) and Path(candidate).is_dir()

    dev_marker_present = candidate_resolved and (Path(candidate) / ".coordinator-dev-repo").is_file()

    claude_home = _claude_home_dir()
    oss_present = bool(claude_home) and (
        Path(claude_home) / "plugins" / "coordinator-claude" / ".claude-plugin" / "plugin.json"
    ).is_file()

    if dev_marker_present:
        return "dev"

    if candidate_resolved and oss_present:
        raise ResolutionError(
            f'resolve-coordinator-clone: ambiguous coordinator source — an unmarked candidate clone '
            f'was found at "{candidate}" (no .coordinator-dev-repo marker) AND an OSS install was '
            f'found at "{Path(claude_home) / "plugins" / "coordinator-claude"}".\n'
            "  Set COORDINATOR_SOURCE_MODE=dev or COORDINATOR_SOURCE_MODE=oss to disambiguate."
        )

    if oss_present:
        return "oss"

    if candidate_resolved:
        return "dev"

    raise ResolutionError(
        "resolve-coordinator-clone: no coordinator source found (no dev marker, no OSS install); "
        "set COORDINATOR_SOURCE_MODE or run coordinator:install."
    )


# ---------------------------------------------------------------------------
# --clone-root / --for-git-ops
# ---------------------------------------------------------------------------

def resolve_git_ops() -> str:
    mode = _resolve_source_mode("git-ops")

    if mode == "oss":
        claude_home = _claude_home_dir()
        if claude_home:
            flat = Path(claude_home) / "plugins" / "coordinator-claude"
            if (flat / ".git").is_dir():
                return str(flat)
        raise ResolutionError(
            "resolve-coordinator-clone --for-git-ops: OSS mode selected but no git-backed OSS clone "
            "found (a marketplace byte-copy install has no .git).\n"
            "  Run: coordinator:install OR set COORDINATOR_CLONE to a git-backed clone path."
        )

    # mode is "dev" or "passthrough" — run the existing ladder unchanged.

    coordinator_clone = os.environ.get("COORDINATOR_CLONE")
    if coordinator_clone:
        if (Path(coordinator_clone) / ".git").is_dir():
            return coordinator_clone
        raise ResolutionError(
            f'resolve-coordinator-clone: COORDINATOR_CLONE is set to "{coordinator_clone}" but it has no .git directory'
        )

    live = _registry_doe_claude() or _registry_live_path()
    if live and (Path(live) / ".git").is_dir():
        return live

    doe_root = _read_doe_root_pointer()
    if doe_root and (Path(doe_root) / ".git").is_dir():
        return doe_root

    claude_home = _claude_home_dir()
    if claude_home:
        flat = Path(claude_home) / "plugins" / "coordinator-claude"
        if (flat / ".git").is_dir():
            return str(flat)

    raise ResolutionError(
        "resolve-coordinator-clone --for-git-ops: no git-backed coordinator clone found.\n"
        "  Tried: COORDINATOR_CLONE env, registry repos.doe_claude (canonical),\n"
        "         registry plugin.mirrors.coordinator-claude.live_path (fallback),\n"
        "         durable/.doe-root pointer, flat ~/.claude/plugins/coordinator-claude\n"
        "  (no .git in any tried location)\n"
        "  Run: coordinator:install OR set COORDINATOR_CLONE to the clone path."
    )


# ---------------------------------------------------------------------------
# --content-root / --for-content
# ---------------------------------------------------------------------------

def resolve_content() -> str:
    mode = _resolve_source_mode("content")

    if mode == "oss":
        newest = _newest_cache()
        if newest:
            return newest
        claude_home = _claude_home_dir()
        if claude_home:
            flat = Path(claude_home) / "plugins" / "coordinator-claude"
            if (flat / ".claude-plugin" / "plugin.json").is_file():
                return str(flat)
        raise ResolutionError(
            "resolve-coordinator-clone --for-content: OSS mode selected but no readable OSS content "
            "root found (tried versioned cache, flat marketplace manifest).\n"
            "  Run: coordinator:install OR set COORDINATOR_ROOT to the coordinator directory."
        )

    # mode is "dev" or "passthrough" — run the existing ladder unchanged.

    claude_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if claude_plugin_root:
        if Path(claude_plugin_root).is_dir():
            return claude_plugin_root
        raise ResolutionError(
            f'resolve-coordinator-clone: CLAUDE_PLUGIN_ROOT is set to "{claude_plugin_root}" but it does not exist'
        )

    coordinator_root = os.environ.get("COORDINATOR_ROOT")
    if coordinator_root:
        if Path(coordinator_root).is_dir():
            return coordinator_root
        raise ResolutionError(
            f'resolve-coordinator-clone: COORDINATOR_ROOT is set to "{coordinator_root}" but it does not exist'
        )

    live = _registry_live_path()
    if live and Path(live).is_dir():
        return live

    newest = _newest_cache()
    if newest:
        return newest

    doe_root = _read_doe_root_pointer()
    if doe_root and (Path(doe_root) / "coordinator").is_dir():
        return str(Path(doe_root) / "coordinator")

    claude_home = _claude_home_dir()
    if claude_home:
        flat = Path(claude_home) / "plugins" / "coordinator-claude"
        if (flat / ".claude-plugin" / "plugin.json").is_file():
            return str(flat)

    raise ResolutionError(
        "resolve-coordinator-clone --for-content: no readable coordinator content root found.\n"
        "  Tried: CLAUDE_PLUGIN_ROOT, COORDINATOR_ROOT, registry live_path,\n"
        "         versioned cache glob, durable/.doe-root pointer,\n"
        "         flat ~/.claude/plugins/coordinator-claude\n"
        "  Run: coordinator:install OR set COORDINATOR_ROOT to the coordinator directory."
    )


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

_USAGE = "Usage: resolve-coordinator-clone.py --clone-root|--content-root (aliases: --for-git-ops|--for-content)\n"


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        sys.stderr.write(_USAGE)
        return 2

    flag = argv[0]
    if flag in ("--clone-root", "--for-git-ops"):
        resolver = resolve_git_ops
    elif flag in ("--content-root", "--for-content"):
        resolver = resolve_content
    else:
        sys.stderr.write(f'resolve-coordinator-clone: unknown flag "{flag}"\n')
        sys.stderr.write(_USAGE)
        return 2

    try:
        result = resolver()
    except ResolutionError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 1

    sys.stdout.write(result)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
