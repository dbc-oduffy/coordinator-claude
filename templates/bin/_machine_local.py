#!/usr/bin/env python3
"""
_machine_local.py — implementation of the machine-local registry reader.

Spec backlink: docs/plans/2026-05-19-machine-local-registry.md §4.3
              docs/plans/2026-07-06-durable-substrate-to-settings-home.md § C2a
Purpose: Read per-machine key/value config from <settings-home>/machine-local/
TOML files, following a strict resolution order so operator-set machine-specific
values always outrank shared baselines and env-var escape hatches.

Settings-home seam: the machine-local directory is no longer hardcoded to
~/.claude/machine-local. It resolves through the C1 settings-home seam
(_settings_home()) with full precedence:
  MACHINE_LOCAL_REGISTRY_DIR (rung-1, test isolation / explicit dir override)
  → COORDINATOR_SETTINGS_HOME/machine-local (rung-2, home-root override)
  → ${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings/machine-local (default)

Underscore prefix is intentional — discourages direct invocation.
Users should call `machine-local` (the shell wrapper), not this file.

Resolution order (most-specific first):
  1. <concern>.local.toml  — per-machine concern override
  2. <concern>.toml        — tracked concern baseline
  3. registry.local.toml   — per-machine top-level overrides
  4. registry.toml         — tracked top-level baseline
  5. MACHINE_LOCAL_<KEY>   — env escape hatch (dots → underscores, uppercased)
  6. --default             — caller-supplied fallback
  7. exit 1                — key cleanly absent (read path)
  7a. exit 2               — operational failure (broken reader: version guard,
                             malformed TOML) — NOT absence (read path)

Read-path exit-code contract (get / has): a consumer MUST be able to tell a
cleanly-absent key from a reader that could not produce an answer at all — else a
shell-out that swallows non-zero (`get X || fallback`) silently masks an
operational failure as absence. That ambiguity is the 2026-06-24 daemon bug
(cross-repo memo: a stripped-PATH daemon ran the wrapper under system Python 3.9,
tripping the version guard, and rc=1 was read as "key absent"). Codes:
  0  — success (value found / has: present)
  1  — clean absence (get: key not found; has: key not set)
  2  — operational failure (Python < 3.11 version guard, malformed TOML)
  3  — require: key not set; a typed refusal, never a fallback
  4  — timeout: a read or child outlived the deadline; never an absence
The write commands (set / array-*) have no "absent" concept; they keep the
simpler 0 = success / non-zero = refused-or-failed convention.

Negative-spec: env does NOT outrank registry layers (the Director of Engineering F1 inversion).
Negative-spec: missing .local files are not errors — treated as empty.
Negative-spec: no regex fallback, no PyYAML, no tomli — stdlib tomllib only.
Negative-spec: reader is read-only for GET path; bare SET writes only registry.local.toml
              (or registry.toml with --global) and never touches concern files — UNLESS
              --concern <name> is passed, the explicit concern-file write path
              (cmd_set_concern: edits only the key's line and its [provenance.<key>] in
              <name>.local.toml; a co-writer's tables stay byte-identical). The registry path and the concern
              path are disjoint: bare set still refuses concern-namespace keys.

All consumers — including the ergonomic wrapper ``claude_machine_local.py`` —
shell out to the ``machine-local`` CLI. Direct in-process import is the
dual-identity anti-pattern (coordinator-content-repo coordinator/docs/wiki/skills-corpus/dual-identity-module-hazard.md and
Coordinator-content-repo coordinator/docs/wiki/hook-best-practices/machine-local-registry.md §8(a)); shell-out is the only contract.
"""

from __future__ import annotations

import sys
import os
import contextlib
import json
import argparse
import re
import stat
import subprocess
import datetime
import difflib
import threading
import time
from collections.abc import Generator
from pathlib import Path

EXIT_OK = 0
EXIT_NOT_FOUND = 1
EXIT_OPERATIONAL = 2
EXIT_KEY_REQUIRED = 3
EXIT_TIMEOUT = 4

# Hard requirement: fail loud on Python < 3.11 rather than silently degrade.
# coordinator requires Python 3.11+ for TOML parsing via stdlib tomllib.
# Exits OPERATIONAL (not NOT_FOUND): a guard trip is a broken reader, not absence.
if sys.version_info < (3, 11):
    print(
        "coordinator requires Python 3.11+ for TOML parsing; "
        "upgrade Python or pin tomli backport in coordinator's dev deps.",
        file=sys.stderr,
    )
    sys.exit(EXIT_OPERATIONAL)

import tomllib

_NO_CONSOLE = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}

# Armed only by the CLI entry point (never when main() is driven in-process).
# _SCAN_BUDGET_S bounds autodiscovery (listings + git) only, never declared rungs
# whose target stat may legitimately be slow; _BACKSTOP_S is the process-wide
# watchdog, kept under callers' 10s timeouts. MACHINE_LOCAL_DEADLINE_S overrides
# the backstop; 0 disables it.
_SCAN_BUDGET_S = 0.8
_BACKSTOP_S = 8.0
_scan_budget_s: float | None = None
_GIT_SPAWN_CAP_S = 5.0
_MAX_TOML_BYTES = 16 * 1024 * 1024
_deadline_at: float | None = None
_toml_memo: dict | None = None


class ResolutionDeadlineExceeded(Exception):
    pass


def _remaining(cap: float) -> float:
    """Seconds a blocking step may still take: `cap`, clipped to the overall deadline."""
    if _deadline_at is None:
        return cap
    left = _deadline_at - time.monotonic()
    if left <= 0:
        raise ResolutionDeadlineExceeded(
            "machine-local: resolution deadline exceeded while scanning search-roots / "
            "spawning git (the drive or git is stalled). Declare the key to skip the scan: "
            "`machine-local set repos.<slug> <path>` or set REPO_<SLUG>."
        )
    return min(cap, left)


def _arm_deadline(seconds: float) -> None:
    """Arm a watchdog that exits EXIT_TIMEOUT with a typed `machine-local-timeout:`
    error if a blocking syscall (stalled drive read) outlives `seconds`."""
    if seconds <= 0:
        return

    def _expire() -> None:
        try:
            sys.stderr.write(
                f"machine-local-timeout: deadline of {seconds:g}s exceeded -- a registry/file read "
                "or child process is blocked (stalled drive). Retry; if it persists check "
                "disk health. Override: MACHINE_LOCAL_DEADLINE_S.\n"
            )
            sys.stderr.flush()
        finally:
            os._exit(EXIT_TIMEOUT)

    timer = threading.Timer(seconds, _expire)
    timer.daemon = True
    timer.start()

SCHEMA_EXPECTED = 1


def _settings_home() -> str:
    """Return the coordinator settings-home root path.

    Inline mirror of the C1 seam (settings-home.sh::_coordinator_settings_home
    and _claude_home.py::settings_home) — same two-rung precedence ladder.
    Implemented inline here so _machine_local.py remains a single-file module
    at source level (the two files are co-installed in <settings-home>/bin/ at
    runtime; an import would require a sys.path hack in the source tree).

    Precedence (most-specific first):
      1. COORDINATOR_SETTINGS_HOME — explicit override (sandboxes/CI/XDG users).
         Non-empty; malformed/empty values are treated as unset.
      2. ${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings — sibling to ~/.claude.

    Note: MACHINE_LOCAL_REGISTRY_DIR is a DEEPER registry-dir override handled
    in _registry_dir() (rung-1, above this function). This function resolves the
    settings HOME ROOT only — it does not read registry CONTENTS.

    Negative-spec: does NOT auto-honor XDG_CONFIG_HOME.
    Negative-spec: does NOT read any file from the settings home (pure location).

    Spec backlink: docs/plans/2026-07-06-durable-substrate-to-settings-home.md § C1/C2a
    RAG-bait: settings-home inline seam; COORDINATOR_SETTINGS_HOME; CLAUDE_HOME redirect
    """
    override = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if override:
        return override
    # Path.home(), not os.path.expanduser("~") -- both honour USERPROFILE on
    # Windows, but expanduser silently returns the literal string "~" when
    # every rung (USERPROFILE, HOMEDRIVE+HOMEPATH, HOME) is unset, which
    # yields a cwd-relative settings-home and writes artifacts at the drive
    # root. Path.home() raises RuntimeError in that case instead.
    home = os.environ.get("CLAUDE_HOME") or str(Path.home())
    return os.path.join(home, ".coordinator-claude-settings")


class AmbiguousRepoMatch(Exception):
    pass


def _registry_dir() -> str:
    """Return the path to the machine-local registry directory.

    Resolution order (most-specific first):
      1. MACHINE_LOCAL_REGISTRY_DIR env var — test isolation / explicit registry-dir
         override; bypasses settings-home resolution entirely. ~16 test files +
         4 production readers (list-reverse-drift-cmds.py, check-plugin-drift.py,
         detect-hardware.sh, refresh-plugin-live-install.sh) depend on this rung;
         it MUST remain as the highest-priority rung.
      2. <settings-home>/machine-local — resolved via _settings_home() (the C1
         settings-home seam inline mirror), which itself follows:
             COORDINATOR_SETTINGS_HOME, else <home>/.coordinator-claude-settings
             (<home> being CLAUDE_HOME when set, else the user home)

    Spec backlink: docs/plans/2026-07-06-durable-substrate-to-settings-home.md § C2a
                   project-rag/docs/wiki/cross-machine-path-resolution-contract.md
                   § The 4-Rung Resolution Ladder
    """
    override = os.environ.get("MACHINE_LOCAL_REGISTRY_DIR")
    if override:
        return override
    return os.path.join(_settings_home(), "machine-local")


def _read_toml_bytes_bounded(path: str) -> bytes:
    size = os.path.getsize(path)
    if size > _MAX_TOML_BYTES:
        print(
            f"machine-local: {path} is {size} bytes (> {_MAX_TOML_BYTES}); refusing to load.\n"
            "Remediation: truncate or repair the file.",
            file=sys.stderr,
        )
        sys.exit(EXIT_OPERATIONAL)
    return _read_bytes_shared(path)


def _load_toml(path: str) -> dict:
    if _toml_memo is not None and path in _toml_memo:
        return _toml_memo[path]
    if not os.path.exists(path):
        return {}
    try:
        data = tomllib.loads(_read_toml_bytes_bounded(path).decode("utf-8"))
        if _toml_memo is not None:
            _toml_memo[path] = data
        return data
    except tomllib.TOMLDecodeError as exc:
        print(
            f"machine-local: malformed TOML in {path}: {exc}\n"
            "Remediation: fix the TOML syntax in the file above.",
            file=sys.stderr,
        )
        sys.exit(EXIT_OPERATIONAL)


def _load_toml_isolated(path: str) -> dict | None:
    if not os.path.exists(path):
        return {}
    try:
        return tomllib.loads(_read_toml_bytes_bounded(path).decode("utf-8"))
    except tomllib.TOMLDecodeError as exc:
        print(
            f"machine-local: malformed TOML in {path}: {exc}\n"
            f"Remediation: fix the TOML syntax in {path}. "
            "This concern's keys are unavailable until fixed; other concerns "
            "and the registry resolve normally.",
            file=sys.stderr,
        )
        return None


def _load_search_roots(reg_dir: str) -> dict[str, list[str]]:
    """Read <reg_dir>/search-roots.toml and return its contents.

    Returns a dict keyed by sys.platform values (e.g. {"darwin": ["~/X"], ...}).
    Returns {} if the file is absent — caller treats absence as no roots configured.
    Uses _load_toml which exits OPERATIONAL on malformed TOML (no silent degradation).

    Spec backlink: project-rag/docs/wiki/cross-machine-path-resolution-contract.md
                   § The 4-Rung Resolution Ladder
    """
    path = os.path.join(reg_dir, "search-roots.toml")
    return _load_toml(path)


def _scan_marketplace_marker(candidate_dir: str) -> str | None:
    """Scan a candidate directory for its .claude-plugin/marketplace.json identity marker.

    Checks two placements in order per the identity-marker convention:
      1. <candidate_dir>/.claude-plugin/marketplace.json  (repo-root placement)
      2. <candidate_dir>/plugin/.claude-plugin/marketplace.json  (one-level-nested)

    The one-level-nested placement is not an edge case — it is the sole placement
    used by example-game-repo (verified 2026-06-30: no repo-root marker).

    For the first placement found, reads the TOP-LEVEL "name" field (NOT plugins[].name —
    they diverge for example-game-repo) and returns name.replace("-", "_") as the registry slug.

    Returns None if neither placement exists, the file is unreadable, or "name" is absent.
    """
    placements = [
        os.path.join(candidate_dir, ".claude-plugin", "marketplace.json"),
        os.path.join(candidate_dir, "plugin", ".claude-plugin", "marketplace.json"),
    ]
    for marker_path in placements:
        if not os.path.exists(marker_path):
            continue
        try:
            with open(marker_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        name = data.get("name")
        if name and isinstance(name, str):
            return name.replace("-", "_")
    return None


def _scan_dev_repo_marker(candidate_dir: str) -> str | None:
    marker_path = os.path.join(candidate_dir, ".coordinator-dev-repo")
    if not os.path.isfile(marker_path):
        return None
    try:
        with open(marker_path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if stripped.startswith("slug:"):
                    slug = stripped[len("slug:"):].strip()
                    return slug.replace("-", "_") if slug else None
    except OSError:
        return None
    return None


def _scan_marker(candidate_dir: str) -> str | None:
    marketplace_slug = _scan_marketplace_marker(candidate_dir)
    dev_repo_slug = _scan_dev_repo_marker(candidate_dir)

    if marketplace_slug is not None and dev_repo_slug is not None:
        return None
    if marketplace_slug is not None:
        return marketplace_slug
    return dev_repo_slug


def _autodiscover_repo(slug: str, reg_dir: str) -> str | None:
    """Autodiscover a repo directory by scanning configured search-roots for a marker match.

    For sys.platform, reads roots from _load_search_roots(reg_dir). For each root,
    expands ~ and iterates its IMMEDIATE child directories (one level, not recursive).

    Calls `_scan_marketplace_marker`/`_scan_dev_repo_marker` directly on each
    candidate — NOT `_scan_marker` — because a both-present candidate needs the
    raw marketplace/dev-repo pair held for AC4, and `_scan_marker`'s `str | None`
    contract collapses that pair away to a single None. A candidate whose
    marketplace or dev-repo slug matches the requested `slug` is a normal
    candidate; a candidate carrying BOTH marker kinds where EITHER derived slug
    matches `slug` is instead recorded as a contradiction candidate (held, not
    raised immediately — see below).

    Clean candidates are deduplicated by realpath, then further collapsed so a
    primary working tree and any of its linked git worktrees (which inherit the
    same marketplace.json marker) count as ONE candidate — see
    _collapse_git_worktree_duplicates.

      0 matches, 0 contradictions → returns None (rung-2 miss; caller falls
                                     through to rung 3/4).
      1 clean match, 0 contradictions → returns the candidate directory path.
      ≥2 clean matches, OR ≥1 contradiction → raises AmbiguousRepoMatch naming
                                     the slug (and, for a contradiction, both
                                     marker kinds + the candidate path) and the
                                     ways to disambiguate. The caller DEFERS
                                     this raise until rungs 3 and 4 have been
                                     consulted (an ambiguous OR contradictory
                                     scan is a rung-2 non-result, not a
                                     ladder-terminating error) — see
                                     resolve_sibling_repo. A both-present
                                     candidate is an identity contradiction,
                                     not a precedence question — it is held
                                     the same way a multi-candidate ambiguity
                                     is held, reusing this exact mechanism
                                     rather than a parallel one, so a request
                                     for that slug still fails loud instead of
                                     silently missing.

    Spec backlink: project-rag/docs/wiki/cross-machine-path-resolution-contract.md
                   § The 4-Rung Resolution Ladder
    Spec backlink: docs/plans/2026-08-03-coordinator-content-repo-as-a-first-class-installation.md § C2
    """
    roots_by_platform = _load_search_roots(reg_dir)
    platform_roots = roots_by_platform.get(sys.platform, [])
    if not isinstance(platform_roots, list):
        print(
            f"machine-local: search-roots.toml: platform key '{sys.platform}' must be a list "
            f"of paths, not a bare string. Got: {platform_roots!r}\n"
            "Remediation: wrap the value in brackets, e.g. darwin = [\"~/X\"].",
            file=sys.stderr,
        )
        sys.exit(EXIT_OPERATIONAL)

    candidates: list[str] = []
    contradictions: list[tuple[str, str, str]] = []
    for root in platform_roots:
        expanded_root = os.path.expanduser(str(root))
        if not os.path.isdir(expanded_root):
            continue
        try:
            child_names = os.listdir(expanded_root)
        except OSError:
            continue
        for child in sorted(child_names):
            _remaining(_GIT_SPAWN_CAP_S)
            child_path = os.path.join(expanded_root, child)
            if not os.path.isdir(child_path):
                continue
            marketplace_slug = _scan_marketplace_marker(child_path)
            dev_repo_slug = _scan_dev_repo_marker(child_path)
            if marketplace_slug is not None and dev_repo_slug is not None:
                if slug in (marketplace_slug, dev_repo_slug):
                    contradictions.append((os.path.realpath(child_path), marketplace_slug, dev_repo_slug))
                continue
            found_slug = marketplace_slug if marketplace_slug is not None else dev_repo_slug
            if found_slug == slug:
                candidates.append(child_path)

    distinct: list[str] = []
    seen_real: set[str] = set()
    for c in candidates:
        real = os.path.realpath(c)
        if real not in seen_real:
            seen_real.add(real)
            distinct.append(c)

    representatives = _collapse_git_worktree_duplicates(distinct)

    if contradictions:
        contradiction_lines = "\n".join(
            f"    {path} (marketplace marker: '{mp}', dev-repo sentinel: '{dev}')"
            for path, mp, dev in contradictions
        )
        also_clean = (
            f"\n  Also found {len(representatives)} clean candidate(s) for the same slug: "
            f"{', '.join(representatives)}"
            if representatives
            else ""
        )
        raise AmbiguousRepoMatch(
            f"Identity contradiction for repo slug '{slug}': found {len(contradictions)} "
            f"candidate directory/directories carrying BOTH a marketplace marker and a "
            f"dev-repo sentinel — a candidate cannot claim two installation shapes at once, "
            f"so neither of its derived slugs is a valid rung-2 hit, and no explicit "
            f"declaration (path-exceptions.toml, registry.local.toml repos.{slug}) resolves "
            f"it either.\n"
            f"  Candidates:\n{contradiction_lines}{also_clean}\n"
            f"  To fix: remove whichever marker is wrong for that directory, or "
            f"set REPO_{slug.upper()}, or `machine-local set repos.{slug} /absolute/path`."
        )

    if len(representatives) >= 2:
        raise AmbiguousRepoMatch(
            f"Ambiguous match for repo slug '{slug}': found {len(representatives)} candidate "
            f"directories across configured search-roots, and no explicit declaration "
            f"(path-exceptions.toml, registry.local.toml repos.{slug}) resolves it either.\n"
            f"  Candidates: {', '.join(representatives)}\n"
            f"  To fix: set REPO_{slug.upper()}, or "
            f"`machine-local set repos.{slug} /absolute/path`, or remove the stray copy."
        )
    if len(representatives) == 1:
        return representatives[0]
    return None


def _git_common_dir(cand: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", cand, "rev-parse", "--git-common-dir"],
            capture_output=True,
            text=True,
            timeout=_remaining(_GIT_SPAWN_CAP_S),
            **_NO_CONSOLE,
        )
    except subprocess.TimeoutExpired:
        _remaining(0.0)
        return None
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    common_dir = proc.stdout.strip()
    if not common_dir:
        return None
    if not os.path.isabs(common_dir):
        common_dir = os.path.join(cand, common_dir)
    return os.path.realpath(common_dir)


def _collapse_git_worktree_duplicates(distinct: list[str]) -> list[str]:
    groups: dict[str, list[str]] = {}
    order: list[str] = []
    for cand in distinct:
        common_dir = _git_common_dir(cand)
        key = common_dir if common_dir is not None else f"__standalone__:{os.path.realpath(cand)}"
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(cand)

    representatives: list[str] = []
    for key in order:
        members = groups[key]
        if len(members) == 1:
            representatives.append(members[0])
            continue
        primaries = [m for m in members if os.path.isdir(os.path.join(m, ".git"))]
        if len(primaries) == 1:
            representatives.append(primaries[0])
        else:
            if len(primaries) > 1:
                print(
                    f"machine-local: warning: {len(primaries)} primary working trees "
                    f"share one git common-dir ({key}) — this is structurally "
                    "unexpected (possibly a corrupted or hand-crafted .git). "
                    "Falling back to deterministic first-sorted pick.",
                    file=sys.stderr,
                )
            representatives.append(sorted(members)[0])
    return representatives


def _load_path_exceptions(reg_dir: str) -> dict:
    """Read <reg_dir>/path-exceptions.toml and return the OS-keyed exception dict.

    Structure: {sys.platform: {slug: path_str}}. Returns {} if the file is absent.
    Exits OPERATIONAL (via _load_toml) on malformed TOML — no silent degradation.

    Spec backlink: project-rag/docs/wiki/cross-machine-path-resolution-contract.md
                   § Exceptions-Table Format  (rung 3 of the 4-rung ladder)
    """
    path = os.path.join(reg_dir, "path-exceptions.toml")
    return _load_toml(path)


def _to_native_drive_path(s: str) -> str:
    if os.name != "nt":
        return s
    m = re.match(r"^/(?:cygdrive/)?([A-Za-z])(/.*)?$", s)
    if m:
        return m.group(1).upper() + ":" + (m.group(2) or "/")
    return s


class SiblingRepoNotFoundError(Exception):
    pass


def resolve_sibling_repo(name: str) -> "Path | None":
    slug = name
    env_var = f"REPO_{slug.upper()}"
    reg_dir = _registry_dir()

    env_val = os.environ.get(env_var)
    if env_val is not None:
        p = Path(env_val)
        if p.exists():
            return p
        raise EnvironmentError(
            f"{env_var} is set to {env_val!r} but that path does not exist. "
            f"Fix or unset {env_var} to allow autodiscovery to proceed."
        )

    # Explicit declarations (path-exceptions, registry.local.toml) resolve before any
    # directory scan or git spawn: a declared key must not pay for, or be blocked by,
    # autodiscovery.
    exceptions = _load_path_exceptions(reg_dir)
    platform_exc = exceptions.get(sys.platform, {})
    if isinstance(platform_exc, dict):
        exc_path_str = platform_exc.get(slug)
        if exc_path_str is not None:
            exc_path = Path(os.path.expanduser(str(exc_path_str)))
            if exc_path.exists():
                return exc_path

    reg_local_path = os.path.join(reg_dir, "registry.local.toml")
    reg_local_data = _load_toml(reg_local_path)
    if reg_local_data:
        flat = _flatten_nested(reg_local_data)
        key = f"repos.{slug}"
        val = flat.get(key)
        if val is not None and str(val) != "":
            return Path(str(val))

    # Search-roots autodiscovery: the only rung that scans directories and spawns git.
    # An ambiguous scan is a non-result; it is re-raised only if nothing resolved.
    global _deadline_at
    if _scan_budget_s is not None:
        _deadline_at = time.monotonic() + _scan_budget_s
    deferred_ambiguity: AmbiguousRepoMatch | None = None
    try:
        discovered = _autodiscover_repo(slug, reg_dir)
    except AmbiguousRepoMatch as exc:
        deferred_ambiguity = exc
        discovered = None
    if discovered is not None:
        return Path(discovered)

    if deferred_ambiguity is not None:
        raise deferred_ambiguity

    return None


def resolve_sibling_repo_required(name: str) -> "Path":
    result = resolve_sibling_repo(name)
    if result is None:
        slug = name
        raise SiblingRepoNotFoundError(
            f"Cannot locate sibling repo '{name}'.\n"
            f"  Tried: REPO_{slug.upper()} env var, search-roots autodiscovery, path-exceptions table,\n"
            f"         registry.local.toml repos.{slug}.\n"
            f"  To fix: machine-local set repos.{slug} /absolute/path/to/{name.replace('_', '-')}\n"
            f"  Then re-run the failing command."
        )
    return result


def _warn_schema(data: dict, path: str) -> None:
    schema_val = data.get("schema")
    if schema_val is not None and schema_val != SCHEMA_EXPECTED:
        print(
            f"machine-local: warning: {path} declares schema={schema_val}, "
            f"reader expects schema={SCHEMA_EXPECTED}. "
            "Some keys may not be read correctly.",
            file=sys.stderr,
        )


def _flatten_nested(data: dict, _prefix: str = "") -> dict:
    result = {}
    for k, v in data.items():
        if k in ("schema", "concerns"):
            continue
        full_key = f"{_prefix}{k}"
        if isinstance(v, dict):
            result.update(_flatten_nested(v, _prefix=f"{full_key}."))
        else:
            result[full_key] = v
    return result


def _flatten_concern(concern_name: str, data: dict, _prefix: str = "") -> dict:
    result = {}
    effective_prefix = _prefix if _prefix != "\x00" else ""
    base = f"{concern_name}.{effective_prefix}" if effective_prefix else f"{concern_name}."
    for k, v in data.items():
        if k == "schema":
            continue
        if not _prefix and isinstance(v, dict) and k == concern_name:
            result.update(_flatten_concern(concern_name, v, _prefix="\x00"))
            continue
        full_key = f"{base}{k}"
        if isinstance(v, dict):
            result.update(_flatten_concern(concern_name, v, _prefix=f"{effective_prefix}{k}." if effective_prefix else f"{k}."))
        else:
            result[full_key] = v
    return result


def _build_resolution_layers(
    reg_dir: str,
    _registry_local_data: dict | None = None,
    warn_unprovisioned: bool = False,
    shadowed: list | None = None,
) -> list[dict]:
    """Build the resolution layers. Registry keys under a concern namespace are
    dropped; pass `shadowed` to collect them as (key, source, namespace). The
    unprovisioned-concern stderr warning is opt-in via `warn_unprovisioned`."""
    reg_path = os.path.join(reg_dir, "registry.toml")
    reg_local_path = os.path.join(reg_dir, "registry.local.toml")

    registry = _load_toml(reg_path)
    registry_local = (
        _registry_local_data if _registry_local_data is not None else _load_toml(reg_local_path)
    )

    if registry:
        _warn_schema(registry, reg_path)
    if registry_local:
        _warn_schema(registry_local, reg_local_path)

    concerns_list = registry.get("concerns", [])
    if not isinstance(concerns_list, list):
        concerns_list = []

    concern_prefixes = {c.lower() for c in concerns_list}

    def _clean_registry(data: dict, source_label: str) -> dict:
        flat = _flatten_nested(data)
        cleaned = {}
        for k, v in flat.items():
            first_seg = k.split(".")[0].lower()
            if first_seg in concern_prefixes:
                if shadowed is not None:
                    shadowed.append((k, source_label, first_seg))
                continue
            cleaned[k] = v
        return cleaned

    concern_local_layers = []
    concern_base_layers = []

    for concern in concerns_list:
        concern = str(concern)
        c_path = os.path.join(reg_dir, f"{concern}.toml")
        c_local_path = os.path.join(reg_dir, f"{concern}.local.toml")

        c_data = _load_toml_isolated(c_path)
        c_local_data = _load_toml_isolated(c_local_path)
        c_data_malformed = c_data is None
        c_local_data_malformed = c_local_data is None
        if c_data is None:
            c_data = {}
        if c_local_data is None:
            c_local_data = {}

        if c_data:
            _warn_schema(c_data, c_path)
        if c_local_data:
            _warn_schema(c_local_data, c_local_path)

        if not c_data and not c_local_data and not c_data_malformed and not c_local_data_malformed:
            if warn_unprovisioned:
                print(
                    f"machine-local: warning: concern '{concern}' is registered in "
                    f"concerns=[...] but neither '{concern}.toml' nor "
                    f"'{concern}.local.toml' could be loaded from {reg_dir} "
                    "(missing/unreadable/empty) — its keys will resolve not-found. "
                    "Refresh the install or remove it from concerns.",
                    file=sys.stderr,
                )
            continue

        if c_local_data:
            concern_local_layers.append(_flatten_concern(concern, c_local_data))
        if c_data:
            concern_base_layers.append(_flatten_concern(concern, c_data))

    reg_local_clean = _clean_registry(registry_local, "registry.local.toml")
    reg_clean = _clean_registry(registry, "registry.toml")

    layers = concern_local_layers + concern_base_layers + [reg_local_clean, reg_clean]
    return layers


def _resolve_key(key: str, layers: list[dict]) -> str | None:
    for layer in layers:
        if key in layer:
            val = layer[key]
            if isinstance(val, list):
                return "\n".join(str(i) for i in val)
            return str(val)
    return None


def _env_key(key: str) -> str:
    return "MACHINE_LOCAL_" + key.upper().replace(".", "_")


def _all_keys(layers: list[dict]) -> list[str]:
    seen = {}
    for layer in layers:
        for k in layer:
            if k not in seen:
                seen[k] = True
    return list(seen.keys())


def _normalize_key_separators(key: str) -> str:
    return key.translate(str.maketrans({"-": "_", ".": "_"})).lower()


def _did_you_mean(key: str, candidates: list[str]) -> list[str]:
    normalized_key = _normalize_key_separators(key)
    others = [c for c in candidates if c != key]
    sep_matches = sorted(c for c in others if _normalize_key_separators(c) == normalized_key)
    if sep_matches:
        return sep_matches
    return sorted(difflib.get_close_matches(key, others, n=3, cutoff=0.6))


def _print_key_miss(key: str, layers: list[dict]) -> None:
    """Print the standard key-miss message plus a stderr-only 'did you mean' hint.

    Hard constraint: the hint is STDERR ONLY -- stdout must stay empty on a
    miss, and callers across the fleet branch on `get`'s clean
    exit-1-empty-stdout contract. This helper never touches stdout or the
    return code; callers still return EXIT_NOT_FOUND themselves.

    A key DECLARED empty in the tracked baseline (`repos.foo = ""`) is not a miss
    in the "no such key" sense -- it is registered but not provisioned on this
    machine, and saying "not found in registry" would send the caller hunting for
    a spelling error. It gets its own message naming the provisioning command.

    If `key` is a namespace prefix of other candidates (e.g. `repos`, which
    contains `repos.<slug>` entries), print a namespace-not-a-key hint instead
    of a near-miss suggestion -- at minimum, a pointer to `machine-local keys`.
    """
    if _resolve_key(key, layers) == "":
        print(
            f"machine-local: key '{key}' is declared but not set on this machine -- "
            f"provision it with `machine-local set {key} <value>`",
            file=sys.stderr,
        )
        return
    candidates = _all_keys(layers)
    print(f"machine-local: key '{key}' not found in registry", file=sys.stderr)
    prefix = f"{key}."
    if any(c.startswith(prefix) for c in candidates):
        print(
            f"  '{key}' is a namespace, not a key -- try `machine-local keys --prefix {key}`",
            file=sys.stderr,
        )
        return
    suggestions = _did_you_mean(key, candidates)
    if len(suggestions) == 1:
        print(f"  did you mean '{suggestions[0]}'?", file=sys.stderr)
    elif len(suggestions) > 1:
        joined = ", ".join(f"'{s}'" for s in suggestions)
        print(f"  did you mean one of: {joined}?", file=sys.stderr)


# compat-fallback: the content-root key and its pre-rename name answer for each other,
# mirroring coordinator_core.machine_resolver._CONTENT_ROOT_KEY_PAIR.
_CONTENT_ROOT_KEY_PAIR = {
    "repos.content_root": "repos.doe_claude",  # private-name-ok: compat-fallback
    "repos.doe_claude": "repos.content_root",  # private-name-ok: compat-fallback
}


# A stored value of the form `${other.key}` or `${other.key}/rel/tail` names another
# key's root plus a relative tail; readers expand it so a root is spelled once.
_KEYREF_RE = re.compile(r"^\$\{([A-Za-z0-9_][A-Za-z0-9_.\-]*)\}((?:[/\\].*)?)$", re.DOTALL)
_KEYREF_MAX_DEPTH = 8


def resolve_one(
    key: str, layers: list[dict] | None = None, _chain: tuple[str, ...] = ()
) -> tuple[int, str | None]:
    """Resolve `key`, expanding a leading `${other.key}` reference (chained, cycle-checked)."""
    rc, val = _resolve_one_exact(key, layers)
    if rc == EXIT_NOT_FOUND and key in _CONTENT_ROOT_KEY_PAIR:
        rc, val = _resolve_one_exact(_CONTENT_ROOT_KEY_PAIR[key], layers)
    if rc != EXIT_OK or val is None:
        return rc, val
    m = _KEYREF_RE.match(val)
    if m is None:
        return rc, val
    ref, tail = m.group(1), m.group(2)
    chain = _chain + (key,)
    if ref in chain or len(chain) >= _KEYREF_MAX_DEPTH:
        return EXIT_OPERATIONAL, (
            f"machine-local: key '{key}' = {val!r} has a reference cycle "
            f"({' -> '.join(chain + (ref,))})"
        )
    ref_rc, base = resolve_one(ref, layers, chain)
    if ref_rc in (EXIT_OPERATIONAL, EXIT_TIMEOUT):
        return ref_rc, base
    if ref_rc != EXIT_OK or not base:
        return EXIT_OPERATIONAL, (
            f"machine-local: key '{key}' = {val!r} references '{ref}', which is not set "
            f"on this machine -- provision it with `machine-local set {ref} <value>`"
        )
    if not tail:
        return EXIT_OK, base
    return EXIT_OK, base.rstrip("/\\") + "/" + tail.lstrip("/\\")


def _resolve_one_exact(key: str, layers: list[dict] | None = None) -> tuple[int, str | None]:
    key_parts = key.split(".")
    if len(key_parts) == 2 and key_parts[0] == "repos":
        slug = key_parts[1]
        try:
            resolved = resolve_sibling_repo(slug)
        except ResolutionDeadlineExceeded as exc:
            # The only bound that fires in-process: a stall, never an absence.
            return EXIT_TIMEOUT, f"machine-local-timeout: {exc}"
        except (AmbiguousRepoMatch, EnvironmentError) as exc:
            # AmbiguousRepoMatch = detect-then-silently-pick footgun (misconfig).
            # EnvironmentError   = REPO_<SLUG> set but path absent (misconfig).
            # Both are EXIT_OPERATIONAL: the reader could not produce a clean answer.
            return EXIT_OPERATIONAL, f"machine-local: {exc}"

        if resolved is not None:
            return EXIT_OK, _to_native_drive_path(resolved.as_posix())

        reg_local_path = os.path.join(_registry_dir(), "registry.local.toml")
        reg_local_data = _load_toml(reg_local_path)
        if reg_local_data:
            flat_local = _flatten_nested(reg_local_data)
            if key in flat_local:
                return EXIT_OK, str(flat_local[key])

        return EXIT_NOT_FOUND, None

    if layers is None:
        layers = _build_resolution_layers(_registry_dir())

    val = _resolve_key(key, layers)

    if val is None:
        val = os.environ.get(_env_key(key))

    if val is not None:
        return EXIT_OK, val
    return EXIT_NOT_FOUND, None


def cmd_get(args: argparse.Namespace) -> int:
    """Implement: machine-local get <key> [--default <v>]

    Operational failures (version guard, malformed TOML) exit 2 via sys.exit(EXIT_OPERATIONAL)
    inside _load_toml / the version guard at module top, BEFORE reaching this return.
    So a `return EXIT_NOT_FOUND` here is always a clean absence — never a broken reader.

    repos.<slug> keys are routed through resolve_sibling_repo (the 4-rung ladder)
    before the generic resolution stack.  That routing, and the resolution itself,
    live in resolve_one — shared with cmd_dump so single and batch reads cannot
    diverge.
    """
    key = args.key
    reg_dir = _registry_dir()

    key_parts = key.split(".")
    is_repos_key = len(key_parts) == 2 and key_parts[0] == "repos"
    layers = None if is_repos_key else _build_resolution_layers(reg_dir)

    rc, val = resolve_one(key, layers=layers)

    if rc in (EXIT_OPERATIONAL, EXIT_TIMEOUT):
        print(val, file=sys.stderr)
        return rc

    if rc == EXIT_OK:
        print(val)
        return EXIT_OK

    if args.default is not None:
        print(args.default)
        return EXIT_OK

    if layers is None:
        layers = _build_resolution_layers(reg_dir)
    _print_key_miss(key, layers)
    return EXIT_NOT_FOUND


def cmd_require(args: argparse.Namespace) -> int:
    """Implement: machine-local require <key>

    Same resolution as `get`, with no `--default`: a miss is the typed refusal
    EXIT_KEY_REQUIRED (stdout empty, stderr `settings-key-missing: <key>`), distinct
    from `get`'s absence code so a caller can tell a required key from an optional one.
    """
    key = args.key
    reg_dir = _registry_dir()
    key_parts = key.split(".")
    is_repos_key = len(key_parts) == 2 and key_parts[0] == "repos"
    layers = None if is_repos_key else _build_resolution_layers(reg_dir)

    rc, val = resolve_one(key, layers=layers)
    if rc in (EXIT_OPERATIONAL, EXIT_TIMEOUT):
        print(val, file=sys.stderr)
        return rc
    if rc == EXIT_OK:
        print(val)
        return EXIT_OK

    print(f"settings-key-missing: {key}", file=sys.stderr)
    if layers is None:
        layers = _build_resolution_layers(reg_dir)
    _print_key_miss(key, layers)
    return EXIT_KEY_REQUIRED


def _repos_shell_var_name(key: str) -> str | None:
    parts = key.split(".")
    if len(parts) != 2 or parts[0] != "repos":
        return None
    var = "REPO_" + re.sub(r"[.\-]", "_", parts[1]).upper()
    if not re.match(r"^[A-Z_][A-Z0-9_]*$", var):
        return None
    return var


def _shell_single_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def cmd_dump(args: argparse.Namespace) -> int:
    """Implement: machine-local dump [--prefix <p>] [--format json|sh] — resolve
    EVERY key in one process.

    Emits a single JSON object of key → resolved value on stdout.  Exists because the
    enumerate-then-read pattern (`machine-local keys`, then one `machine-local get`
    per key) costs 1+N processes for what is one file read: on Windows that measured
    ~40 processes and tens of seconds for a whole-registry read, several times a day,
    on a machine already saturated by concurrent sessions.  `dump` is the batch read
    that pattern should have been.

    Values are resolved through resolve_one — the same kernel `get` uses — so a
    dumped value is byte-identical to what `get` would print for that key, repos
    4-rung ladder and env-override layer included.

    Keys that are cleanly absent (rc=1: unset, or a tracked-baseline `repos.x = ""`
    sentinel that `get` correctly reports not-found) are OMITTED from the object.
    Membership therefore means exactly "`get` would succeed" — a consumer never has
    to re-check a key it found here.

    `--prefix` narrows the OUTPUT, never the process: the registry is read and the
    interpreter started either way, and interpreter start is the whole cost (measured
    ~459ms median on Windows against ~34ms to compile this file). A consumer wanting
    several namespaces takes ONE unprefixed dump and filters it in-process; repeated
    prefixed dumps are the `keys`+`get` mistake one level up, and cost one process per
    namespace for a single file read.

    `--include-unset` emits those absent keys as JSON `null` instead of omitting
    them, so DECLARED-but-unresolvable stays distinguishable from UNREGISTERED in
    ONE process. Without it, a consumer needing that distinction reads `keys`
    alongside `dump` and pays the second process this verb exists to remove. It is
    a flag rather than a change of default because the omitting contract is the
    right one for the common case. `null` is deliberate over `""`: empty-string is
    itself a stored value here (the `repos.x = ""` sentinel), so reusing it would
    make the two states indistinguishable again inside the payload.

    A per-key operational failure (rc=2: an ambiguous autodiscovery match, a
    REPO_<SLUG> pointing at a missing path) does NOT abort the dump: every other key
    still resolves and the object is still emitted, the failing key is named on
    stderr, and the exit code is EXIT_OPERATIONAL so a caller checking rc learns the
    batch was not fully answerable. Stdout stays pipe-clean JSON on every path.

    `--format sh` is the batch-`eval` sibling of the default JSON: it prints one
    guarded `export` statement per resolved repos.<slug> key instead of a JSON
    object, so claude-machine-local.sh can replace its own enumerate-then-read
    (`keys` + one `get` per key) loop with a single `eval "$(... dump --prefix
    repos --format sh)"`. It exists only for repos.<slug> keys -- the shell
    exporters' sole consumer. (`claude-machine-local.ps1` deliberately stays
    on the JSON path instead: PowerShell cannot safely `eval` shell export
    syntax, and it re-implements the idempotency guard itself via
    `[Environment]::GetEnvironmentVariable`. -- Review: coordinator:code-reviewer,
    slice4) It reproduces the JSON path's four per-key
    states, moved to the stream a shell `eval` can tolerate:
      - resolved, non-empty            -> `[ -n "${VAR:-}" ] || export VAR='...'` (shell-doc-ok: the emitted bash line)
        (the guard preserves the caller's own idempotency contract: a
        pre-set, non-empty $VAR is a deliberate operator override and must
        keep winning over the ladder -- see DR-087. `dump` cannot see the
        calling shell's environment, so the guard has to travel WITH the
        emitted line rather than living in the caller's loop.)
      - resolved, declared-but-empty (AC14) -> nothing on stdout, warning on stderr
      - cleanly absent (rc=1)                -> nothing on stdout, warning on stderr
      - operational failure (rc=2)           -> nothing on stdout, error on stderr
    Every value is single-quote-escaped for `eval` safety (see
    `_shell_single_quote`). Non-repos keys, or repos keys whose normalized name
    is not a valid shell identifier, are skipped with a stderr warning -- see
    `_repos_shell_var_name`. Stdout stays `eval`-clean on every path, exactly as
    it stays JSON-clean on every path for the default format.

    `--format sh --include-unset` is a usage error (exit 2): the sh form
    conveys absence by emitting nothing for that key, so `--include-unset`
    (whose only effect is emitting JSON `null`) has no shell equivalent.
    """
    fmt = args.format
    if fmt == "sh" and args.include_unset:
        print(
            "machine-local dump: --format sh --include-unset is a usage error -- "
            "the sh emitter conveys absence by emitting nothing for that key, so "
            "--include-unset (JSON null) has no shell equivalent.",
            file=sys.stderr,
        )
        return 2

    show_origin = getattr(args, "show_origin", False)
    if fmt == "sh" and show_origin:
        print("machine-local dump: --format sh --show-origin is a usage error -- "
              "the sh emitter has no field to carry the layer.", file=sys.stderr)
        return 2

    global _toml_memo
    _toml_memo = {}
    reg_dir = _registry_dir()
    layers = _build_resolution_layers(reg_dir)
    all_keys = _all_keys(layers)

    prefix = args.prefix
    if prefix:
        all_keys = [k for k in all_keys if k == prefix or k.startswith(f"{prefix}.")]

    values: dict[str, str | None] = {}
    failures: list[str] = []
    sh_lines: list[str] = []
    for k in all_keys:
        rc, val = resolve_one(k, layers)

        if fmt == "sh":
            var = _repos_shell_var_name(k)
            if var is None:
                print(
                    f"claude-machine-local: warning: skipping key '{k}' — not a "
                    "repos.<slug> key, or produces a non-conformant shell "
                    "identifier",
                    file=sys.stderr,
                )
                continue
            if rc == EXIT_OK and val is not None:
                if val == "":
                    print(
                        f"claude-machine-local: warning: '{k}' declared but has "
                        f"no value — ${var} not exported",
                        file=sys.stderr,
                    )
                else:
                    sh_lines.append(
                        f'[ -n "${{{var}:-}}" ] || export {var}='
                        f'{_shell_single_quote(val)}'
                    )
            elif rc in (EXIT_OPERATIONAL, EXIT_TIMEOUT):
                failures.append(f"  {k}: {val}")
                print(
                    f"claude-machine-local: error: machine-local reader failed "
                    f"for '{k}' (rc={rc}) — ${var} not exported",
                    file=sys.stderr,
                )
            else:
                print(
                    f"claude-machine-local: warning: '{k}' not resolved by "
                    f"ladder — ${var} not exported",
                    file=sys.stderr,
                )
            continue

        if rc == EXIT_OK and val is not None:
            values[k] = {"value": val, "layer": _origin_layer(k, layers)} if show_origin else val
        elif rc in (EXIT_OPERATIONAL, EXIT_TIMEOUT):
            failures.append(f"  {k}: {val}")
        elif args.include_unset:
            values[k] = None

    if fmt == "sh":
        for line in sh_lines:
            print(line)
    else:
        print(json.dumps(values, indent=2, sort_keys=True))

        if failures:
            print(
                "machine-local dump: {} key(s) could not be resolved (values above are "
                "complete for every other key):".format(len(failures)),
                file=sys.stderr,
            )
            for line in failures:
                print(line, file=sys.stderr)

    if failures:
        return EXIT_OPERATIONAL

    return EXIT_OK


def _origin_layer(key: str, layers: list[dict]) -> str:
    """Name the layer `resolve_one` answered `key` from. Layer order is
    `_build_resolution_layers`'s: concern layers, then registry.local.toml,
    then registry.toml (the tracked defaults) last."""
    parts = key.split(".")
    if len(parts) == 2 and parts[0] == "repos":
        return "repos-ladder"
    for i, layer in enumerate(layers):
        if key in layer:
            if i == len(layers) - 1:
                return "registry.toml (defaults)"
            if i == len(layers) - 2:
                return "registry.local.toml"
            return "concern"
    return "env"


def cmd_has(args: argparse.Namespace) -> int:
    reg_dir = _registry_dir()
    layers = _build_resolution_layers(reg_dir)
    key = args.key

    val = _resolve_key(key, layers)
    if val is None:
        val = os.environ.get(_env_key(key))

    return EXIT_OK if val is not None else EXIT_NOT_FOUND


def cmd_keys(args: argparse.Namespace) -> int:
    """Implement: machine-local keys [--prefix <p>] — list all known keys, one per line.

    stdout is the machine-parseable contract (one key per line), and stderr stays
    silent on success. The listing is every DECLARED key, including tracked-baseline
    empty declarations (`repos.foo = ""`) that `get` reports not-found — callers
    (cross-repo-memo's publish-mirror guard among them) depend on that full set.

    Negative-spec: the default listing does not annotate declared-but-unset keys.
    That asymmetry is explained where it bites — `get` on such a key names it as
    declared but not set (see _print_key_miss) — not on every enumeration, where it
    was per-call noise in every agent loop that lists `repos.*`.

    `--set-only` (optional) narrows the listing to keys `get` would answer with a
    non-empty value (same resolution as `get`): declared-but-unset keys are absent.
    The default listing is unchanged; callers asking "is X registered?" use this.

    `--prefix` (optional) filters the listing to keys equal to, or nested under
    (dot-separated), the given prefix -- the one-step "what lives under `repos.`?"
    companion to `get`'s namespace-hit hint (`_print_key_miss`), so a caller that
    lands on a namespace instead of a leaf key has a next step other than a blind
    directory guess.
    """
    reg_dir = _registry_dir()
    layers = _build_resolution_layers(reg_dir, warn_unprovisioned=True)
    all_keys = _all_keys(layers)
    prefix = args.prefix
    if prefix:
        all_keys = [k for k in all_keys if k == prefix or k.startswith(f"{prefix}.")]
    if getattr(args, "set_only", False):
        kept = []
        for k in all_keys:
            rc, val = resolve_one(k, layers)
            if rc == EXIT_TIMEOUT:
                print(val, file=sys.stderr)
                return EXIT_TIMEOUT
            if rc == EXIT_OK and val:
                kept.append(k)
        all_keys = kept
    for k in all_keys:
        print(k)
    return 0


_EXTERNAL_NS = "external_workspaces"
_EXTERNAL_FIELDS = ("path", "kind", "vcs", "p4_client")


def _canon_path(p: str) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(p)))


def _path_inside(p: str, root: str) -> bool:
    """True when canonical `p` equals canonical `root` or lies under it."""
    return p == root or p.startswith(root.rstrip(os.sep) + os.sep)


def _external_workspaces(layers: list[dict]) -> dict[str, dict]:
    """Registered `external_workspaces.<key>.*` entries, resolved in layer order
    (first layer to define a leaf wins). An entry needs a non-empty `path`; an
    absent or unknown `kind` reads as `external-readonly` (fail closed)."""
    raw: dict[str, dict] = {}
    prefix = _EXTERNAL_NS + "."
    for layer in layers:
        for flat_key, val in layer.items():
            if not flat_key.startswith(prefix) or isinstance(val, (list, dict)):
                continue
            name, _, leaf = flat_key[len(prefix):].rpartition(".")
            if not name or leaf not in _EXTERNAL_FIELDS:
                continue
            raw.setdefault(name, {}).setdefault(leaf, str(val))
    entries: dict[str, dict] = {}
    for name, fields in raw.items():
        if not fields.get("path", "").strip():
            continue
        entries[name] = {
            "path": fields["path"],
            "kind": "external-readonly",
            "vcs": fields.get("vcs") or "none",
        }
    return entries


def _external_workspace_containing(path: str, entries: dict[str, dict]) -> str | None:
    """Key of the registered workspace whose root equals or contains `path`."""
    target = _canon_path(path)
    for name, entry in entries.items():
        if _path_inside(target, _canon_path(entry["path"])):
            return name
    return None


def cmd_external_workspace(args: argparse.Namespace) -> int:
    """Implement: machine-local external-workspace <name-or-path> | --list.

    Prints `key<TAB>path<TAB>kind<TAB>vcs`; exit 0 when the argument is a
    registered key or a path equal to or under a registered root, 1 when not
    registered, 2 on operational failure (malformed registry).
    """
    entries = _external_workspaces(_build_resolution_layers(_registry_dir()))

    def _line(name: str) -> str:
        e = entries[name]
        return f"{name}\t{e['path']}\t{e['kind']}\t{e['vcs']}"

    if args.list:
        for name in entries:
            print(_line(name))
        return EXIT_OK
    if not args.target:
        print("machine-local: external-workspace needs <name-or-path> or --list", file=sys.stderr)
        return EXIT_OPERATIONAL
    name = args.target if args.target in entries else _external_workspace_containing(args.target, entries)
    if name is None:
        return EXIT_NOT_FOUND
    print(_line(name))
    return EXIT_OK


_STORES_NS = "stores"
_STORE_FIELDS = ("path", "path_key", "owner", "purpose")
_STORE_FORBIDDEN_PATH_KEY_PREFIXES = ("repos.", "external_workspaces.", "publish.mirrors.", "stores.")


def _stores(layers: list[dict]) -> dict[str, dict]:
    """Declared `stores.<name>.*` entries, resolved in layer order (first layer to
    define a leaf wins). Each entry carries `path`, `path_key`, `owner`, `purpose`
    (strings, "" when absent), `dependents` (list of str) and `effective_path`:
    `path`, else the value of the key `path_key` names, else "". An entry whose
    path does not exist is KEPT: a store that vanished is the finding."""
    raw: dict[str, dict] = {}
    prefix = _STORES_NS + "."
    for layer in layers:
        for flat_key, val in layer.items():
            if not flat_key.startswith(prefix):
                continue
            name, _, leaf = flat_key[len(prefix):].rpartition(".")
            if not name:
                continue
            if leaf == "dependents":
                items = val if isinstance(val, list) else [val]
                raw.setdefault(name, {}).setdefault("dependents", [str(i) for i in items])
            elif leaf in _STORE_FIELDS and not isinstance(val, (list, dict)):
                raw.setdefault(name, {}).setdefault(leaf, str(val))
    entries: dict[str, dict] = {}
    for name, fields in raw.items():
        entry = {f: fields.get(f, "").strip() for f in _STORE_FIELDS}
        entry["dependents"] = [d for d in fields.get("dependents", []) if d.strip()]
        effective = entry["path"]
        if not effective and entry["path_key"]:
            effective = (_resolve_key(entry["path_key"], layers) or "").strip()
        entry["effective_path"] = effective
        entries[name] = entry
    return entries


def _store_containing(path: str, entries: dict[str, dict]) -> str | None:
    """Name of the store whose canonical root equals or contains `path`; the
    deepest root wins. A store with no resolved path holds nothing."""
    target = _canon_path(path)
    best: tuple[int, str] | None = None
    for name, entry in entries.items():
        if not entry["effective_path"]:
            continue
        root = _canon_path(entry["effective_path"])
        if _path_inside(target, root) and (best is None or len(root) > best[0]):
            best = (len(root), name)
    return best[1] if best else None


_REPARSE_ALLOWLIST_KEY = "reparse_allowlist"
# Windows constants spelled literally: `stat.IO_REPARSE_TAG_*` exists only on nt CPython, and a
# forced-nt test on POSIX must still reach the classifier.
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400
_TAG_MOUNT_POINT = 0xA0000003
_TAG_SYMLINK = 0xA000000C
_REPARSE_SKIP_DIRS = frozenset({".git"})

#: Test-injectable platform predicate for the nt-vs-POSIX branch of the reparse classifier.
_host_is_nt_override = None


def _host_is_nt() -> bool:
    return _host_is_nt_override() if _host_is_nt_override is not None else os.name == "nt"


def _classify_stat(st, path: str) -> "tuple[str | None, str]":
    """(kind, target) for an lstat result: kind is "volume-mount" | "junction" | "symlink" | None.
    nt keys on `st_reparse_tag` (never islink(): a junction reads as a plain directory), the same
    discriminator as coordinator_core/install/junction.py `is_junction`. A `\\??\\Volume{` target
    is a volume mount (Dev Drive, folder-mounted volume) and shares the junction tag."""
    if _host_is_nt():
        if not getattr(st, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT:
            return None, ""
        tag = getattr(st, "st_reparse_tag", 0)
        if tag not in (_TAG_MOUNT_POINT, _TAG_SYMLINK):
            return None, ""
    elif not stat.S_ISLNK(st.st_mode):
        return None, ""
    else:
        tag = _TAG_SYMLINK
    try:
        target = os.readlink(path)
    except OSError:
        target = ""
    if tag == _TAG_MOUNT_POINT:
        is_volume = target.lower().lstrip("\\?.").startswith("volume{")
        return ("volume-mount" if is_volume else "junction"), target
    return "symlink", target


def classify_reparse(path: str) -> "str | None":
    """"volume-mount" | "junction" | "symlink" for a reparse point at `path`, else None
    (absent, ordinary, or an nt reparse tag this guard does not govern)."""
    try:
        st = os.lstat(path)
    except OSError:
        return None
    return _classify_stat(st, path)[0]


def _norm_link(p: str) -> str:
    """Normalized `p` with the final component left unresolved."""
    if p.startswith("\\\\?\\"):
        p = p[4:]
    return os.path.normcase(os.path.abspath(p))


def _reparse_builtin_pass(path: str, kind: str, target: str) -> bool:
    """True for a generation-swap link the engine creates on purpose
    (install/ensure_venv.py `_swap_in_new_venv`, fleet env publication): `X` -> sibling `X.gen-*`."""
    link = Path(_norm_link(path))
    if kind in ("junction", "symlink") and target:
        t = Path(_norm_link(target if os.path.isabs(target) else os.path.join(os.path.dirname(path), target)))
        if t.parent == link.parent and t.name.startswith(link.name + ".gen-"):
            return True
    return False


def _reparse_allowlist(layers: list[dict]) -> "set[str]":
    raw = _resolve_key(_REPARSE_ALLOWLIST_KEY, layers) or ""
    return {_norm_link(line.strip()) for line in raw.split("\n") if line.strip()}


def scan_reparse_points(roots, allowlist, skip_relpaths=frozenset(), judge_roots=False) -> "list[tuple[str, str]]":
    """(path, target) for every junction or symlink under `roots` that is neither a volume mount,
    a built-in engine link, nor in `allowlist` (paths). os.scandir only, no spawn; a reparse point
    is judged and never descended into; `.git` is skipped, as is any directory whose
    forward-slash path relative to its root is in `skip_relpaths`. The roots themselves are judged
    only when `judge_roots` (a flagged root is reported and not walked). Only directory and
    symlink entries are stat'ed."""
    allowed = {_norm_link(a) for a in allowlist}
    skip_names = {r.rsplit("/", 1)[-1] for r in skip_relpaths}  # relpath only for a basename that can match
    found: list[tuple[str, str]] = []
    stack = []
    for r in roots:
        r = str(r)
        if judge_roots:
            try:
                kind, target = _classify_stat(os.lstat(r), r)
            except OSError:
                continue
            if kind is not None and not (
                    kind == "volume-mount" or _norm_link(r) in allowed
                    or _reparse_builtin_pass(r, kind, target)):
                found.append((r, target))
                continue
        stack.append((r, r))
    while stack:
        cur, root = stack.pop()
        try:
            it = os.scandir(cur)
        except OSError:
            continue
        with it:
            for entry in it:
                try:
                    if not (entry.is_dir(follow_symlinks=False) or entry.is_symlink()):
                        continue
                    st = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                kind, target = _classify_stat(st, entry.path)
                if kind is None:
                    if entry.name in _REPARSE_SKIP_DIRS or not stat.S_ISDIR(st.st_mode):
                        continue
                    if entry.name in skip_names and os.path.relpath(entry.path, root).replace("\\", "/") in skip_relpaths:
                        continue
                    stack.append((entry.path, root))
                    continue
                if (kind == "volume-mount" or _norm_link(entry.path) in allowed
                        or _reparse_builtin_pass(entry.path, kind, target)):
                    continue
                found.append((entry.path, target))
    return sorted(found)


def _reparse_findings(entries: dict[str, dict], layers: list[dict]) -> list[tuple[str, str, str]]:
    allow = _reparse_allowlist(layers)
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for name, e in entries.items():
        eff = e["effective_path"]
        if not eff or not os.path.isdir(eff):
            continue
        for path, target in scan_reparse_points([eff], allow, judge_roots=True):
            if path not in seen:
                seen.add(path)
                out.append(("reparse", name, f"{path} -> {target}"))
    return out


def _store_findings(entries: dict[str, dict], layers: list[dict]) -> list[tuple[str, str, str]]:
    """(type, name, detail) for every missing / orphan / incomplete / dead-dependent / reparse finding."""
    out: list[tuple[str, str, str]] = []
    for name, e in entries.items():
        if not e["purpose"]:
            out.append(("incomplete", name, "purpose"))
        if bool(e["path"]) == bool(e["path_key"]):
            out.append(("incomplete", name, "path/path_key"))
        elif e["path_key"] and e["path_key"].startswith(_STORE_FORBIDDEN_PATH_KEY_PREFIXES):
            out.append(("incomplete", name, "path_key"))
        eff = e["effective_path"]
        if not eff or not os.path.exists(eff):
            out.append(("missing", name, eff))
        if not e["owner"] or not (_resolve_key("repos." + e["owner"], layers) or "").strip():
            out.append(("orphan", name, e["owner"]))
        for dep in e["dependents"]:
            if not os.path.exists(dep):
                out.append(("dead-dependent", name, dep))
    out.extend(_reparse_findings(entries, layers))
    return out


def cmd_store(args: argparse.Namespace) -> int:
    """Implement: machine-local store <name-or-path> | --list | --check.

    Prints `name<TAB>path<TAB>owner<TAB>purpose`; exit 0 when the argument is a
    declared store or a path equal to or under a store root, 1 when not
    registered, 2 on operational failure. `--check` is the existence probe: one
    `<type><TAB>name<TAB>detail` line per finding, exit 1 when any. Never writes.
    """
    layers = _build_resolution_layers(_registry_dir())
    entries = _stores(layers)

    def _line(name: str) -> str:
        e = entries[name]
        purpose = " ".join(e["purpose"].split())
        return f"{name}\t{e['effective_path']}\t{e['owner']}\t{purpose}"

    if args.check:
        findings = _store_findings(entries, layers)
        for kind, name, detail in findings:
            print(f"{kind}\t{name}\t{detail}")
        return EXIT_NOT_FOUND if findings else EXIT_OK
    if args.list:
        for name in entries:
            print(_line(name))
        return EXIT_OK
    if not args.target:
        print("machine-local: store needs <name-or-path>, --list or --check", file=sys.stderr)
        return EXIT_OPERATIONAL
    name = args.target if args.target in entries else _store_containing(args.target, entries)
    if name is None:
        return EXIT_NOT_FOUND
    print(_line(name))
    eff = entries[name]["effective_path"]
    if not eff or not os.path.exists(eff):
        print(f"machine-local: store '{name}' path does not exist: {eff or '(unresolved)'}", file=sys.stderr)
    return EXIT_OK


_STORAGE_RECORD_KEY = "storage_registry.path"
_STORAGE_RECORD_RELPATH = ("docs", "fleet", "storage-roots.toml")


def _storage_record_path(layers: list[dict]) -> str:
    """Cross-box record location: key `storage_registry.path`, else
    `<~/.claude/.content-root>/docs/fleet/storage-roots.toml`. "" when neither resolves."""
    explicit = (_resolve_key(_STORAGE_RECORD_KEY, layers) or "").strip()
    if explicit:
        return os.path.expanduser(explicit)
    home = os.environ.get("CLAUDE_HOME") or str(Path.home())
    try:
        root = Path(home, ".claude", ".content-root").read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return os.path.join(root, *_STORAGE_RECORD_RELPATH) if root else ""


def _load_storage_record(layers: list[dict]) -> dict[str, dict]:
    """Roots of the tracked cross-box record, keyed by name. Raises OSError when
    the record is absent and ValueError when it is not valid TOML."""
    path = _storage_record_path(layers)
    if not path:
        raise OSError("no storage record: set `storage_registry.path` or write ~/.claude/.content-root")
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"malformed toml in {path}: {exc}") from exc
    except FileNotFoundError as exc:
        raise OSError(f"no storage record at {path}: set `storage_registry.path`, or check out a "
                      f"coordinator-content-repo branch carrying docs/fleet/storage-roots.toml") from exc
    roots = data.get("roots", {})
    return {n: r for n, r in roots.items() if isinstance(r, dict)} if isinstance(roots, dict) else {}


def _locate_row(name: str, root: dict, box_id: str) -> tuple[str, str, str, str]:
    """(name, box, path, reachable) judged from the calling box only; no network probe."""
    kind = str(root.get("kind", "path")).strip()
    if kind == "url":
        return name, "-", str(root.get("url", "")).strip() or "-", "unprobed"
    box = str(root.get("box", "")).strip()
    path = str(root.get("path", "")).strip()
    if box.casefold() == "nas":
        mounts = root.get("mounts", {})
        path = ""
        if box_id and isinstance(mounts, dict):
            folded = {str(k).casefold(): v for k, v in mounts.items()}
            path = str(folded.get(box_id.casefold(), "")).strip()
        on_this_box = bool(box_id)
    else:
        on_this_box = bool(box_id) and box.casefold() == box_id.casefold()
    if not box_id:
        reach = "unknown"
    elif on_this_box and path:
        reach = "true" if os.path.exists(path) else "false"
    else:
        reach = "false"
    return name, box or "-", path or "-", reach


def cmd_locate(args: argparse.Namespace) -> int:
    """Implement: machine-local locate <root-name> | --list.

    Prints `name<TAB>box<TAB>path<TAB>reachable` from the cross-box record;
    reachable is true/false (judged from this box via `box.id`), `unprobed` for a
    url root, `unknown` when `box.id` is unset. Exit 0 found, 1 unknown root, 2
    record missing/malformed or operational failure. Never writes.
    """
    if not args.list and not args.target:
        print("machine-local: locate needs <root-name> or --list", file=sys.stderr)
        return EXIT_OPERATIONAL
    layers = _build_resolution_layers(_registry_dir())
    try:
        roots = _load_storage_record(layers)
    except (OSError, ValueError) as exc:
        print(f"machine-local: locate: {exc}", file=sys.stderr)
        return EXIT_OPERATIONAL
    box_id = (_resolve_key("box.id", layers) or "").strip()
    if not box_id and any(str(r.get("kind", "path")).strip() != "url" for r in roots.values()):
        print("machine-local: box.id is unset; reachability is unknown. Run: machine-local set box.id <name>",
              file=sys.stderr)
    if args.list:
        for name, root in roots.items():
            print("\t".join(_locate_row(name, root, box_id)))
        return EXIT_OK
    if args.target not in roots:
        print(f"machine-local: locate: no root named {args.target!r}; run `machine-local locate --list`",
              file=sys.stderr)
        return EXIT_NOT_FOUND
    print("\t".join(_locate_row(args.target, roots[args.target], box_id)))
    return EXIT_OK


def _stale_dependents(entry: dict, old_path: str) -> list[str]:
    """Declared dependents that exist and still spell `old_path` (as stored, `/`,
    `\\`, or JSON-escaped `\\\\`). Read-only: no dependent is opened for writing."""
    old = old_path.rstrip("/\\") or old_path
    if not old:
        return []
    back = old.replace("/", "\\")
    spellings = {old, old.replace("\\", "/"), back, back.replace("\\", "\\\\")}
    fold = os.path.normcase("A") != "A"
    if fold:
        spellings = {s.casefold() for s in spellings}
    stale: list[str] = []
    for dep in entry["dependents"]:
        try:
            text = _read_bytes_shared(dep).decode("utf-8", errors="replace")
        except OSError:
            continue
        if fold:
            text = text.casefold()
        if any(s in text for s in spellings):
            stale.append(dep)
    return stale


def cmd_relocate_store(args: argparse.Namespace) -> int:
    """Implement: machine-local relocate-store <name> <new-path> [--dry-run] [--allow-missing].

    Rewrites the store's registry location through `cmd_set` (`stores.<name>.path`,
    or the key `path_key` names), then prints `stale-dependent<TAB>name<TAB>file`
    for each declared dependent still spelling the old location. Never moves data
    and never writes a dependent file. Exit 0 done, 2 refused or operational failure.
    """
    reg_dir = _registry_dir()
    layers = _build_resolution_layers(reg_dir)
    entries = _stores(layers)
    name = args.name
    entry = entries.get(name)
    if entry is None:
        print(f"machine-local: relocate-store: unknown store '{name}'", file=sys.stderr)
        return EXIT_OPERATIONAL
    new_path = os.path.abspath(args.new_path)
    if not os.path.exists(new_path) and not args.allow_missing:
        print(
            f"machine-local: relocate-store: '{new_path}' does not exist "
            "(pass --allow-missing to record a location not yet created)",
            file=sys.stderr,
        )
        return EXIT_OPERATIONAL
    if entry["path"]:
        key = f"{_STORES_NS}.{name}.path"
    elif entry["path_key"]:
        key = entry["path_key"]
        if key.startswith(_STORE_FORBIDDEN_PATH_KEY_PREFIXES):
            print(
                f"machine-local: relocate-store: store '{name}' adopts '{key}', which a store "
                "never relocates (a peer repo, workspace, mirror or another store)",
                file=sys.stderr,
            )
            return EXIT_OPERATIONAL
        if _check_concern_namespace(reg_dir, key) != 0:
            print(
                f"machine-local: relocate-store: '{key}' lives in a concern file; "
                f"relocate it with `machine-local set --concern <name> {key} <path>`",
                file=sys.stderr,
            )
            return EXIT_OPERATIONAL
    else:
        print(f"machine-local: relocate-store: store '{name}' declares neither path nor path_key", file=sys.stderr)
        return EXIT_OPERATIONAL
    old_path = entry["effective_path"]
    rc = cmd_set(argparse.Namespace(
        key=key, value=new_path, write_global=False, dry_run=args.dry_run, concern=None,
    ))
    if rc != 0:
        return EXIT_OPERATIONAL
    if not old_path or _canon_path(old_path) == _canon_path(new_path):
        return EXIT_OK
    for dep in _stale_dependents(entry, old_path):
        print(f"stale-dependent\t{name}\t{dep}")
    return EXIT_OK


def _external_collision_refusal(reg_dir: str, key: str, value: str) -> str | None:
    """Reason `set` must refuse (None when it may proceed): a `repos.*` path
    inside an external workspace, or an external-workspace root that is already
    a `repos.*` path."""
    is_repo = key.startswith("repos.")
    is_ext_path = key.startswith(_EXTERNAL_NS + ".") and key.endswith(".path")
    if not (is_repo or is_ext_path) or not value.strip():
        return None
    layers = _build_resolution_layers(reg_dir)
    target = _canon_path(value)
    if is_repo:
        name = _external_workspace_containing(value, _external_workspaces(layers))
        if name is None:
            return None
        return (
            f"refusing `set {key}`: '{value}' is inside registered external "
            f"workspace '{_EXTERNAL_NS}.{name}' (someone else's code is never a peer repo)"
        )
    for layer in layers:
        for other, val in layer.items():
            if other.startswith("repos.") and isinstance(val, str) and val.strip():
                if _path_inside(target, _canon_path(val)):
                    return (
                        f"refusing `set {key}`: '{value}' is the peer repo "
                        f"'{other}' or inside it (a repo is never an external workspace, "
                        "and a workspace never lives under a repo's tree)"
                    )
    return None


_DRIVE_ROOT_RE = re.compile(r"^[A-Za-z]:[\\/]*$")
_DRIVE_PREFIX_RE = re.compile(r"^[A-Za-z]:")


def _spelled_path(p: str) -> tuple[str, str]:
    """(display, compare) forms of a path: `~` expanded, `\\` -> `/`, no trailing `/`;
    compare is case-folded when it is drive-lettered (drive paths are case-insensitive)."""
    if p.startswith("~"):
        p = os.path.expanduser(p)
    disp = p.replace("\\", "/")
    disp = disp.rstrip("/") or "/"
    cmp_ = disp.casefold() if _DRIVE_PREFIX_RE.match(disp) else disp
    return disp, cmp_


def _looks_absolute(v: str) -> bool:
    return v.startswith(("~", "/", "\\")) or bool(_DRIVE_PREFIX_RE.match(v))


def _absolute_path_refusal(reg_dir: str, key: str, value: str) -> str | None:
    """Reason a write of `value` to `key` must be refused (None when it may proceed): the
    value spells a bare drive root, or an absolute path under a `repos.*` root, where a
    `${repos.<slug>}/tail` key reference names the same place without spelling the root.
    `repos.*` root keys and external-workspace roots are where a root is spelled, so exempt."""
    if key.startswith("repos.") or key.startswith(_EXTERNAL_NS + "."):
        return None
    v = value.strip()
    if not v or v.startswith("${") or not _looks_absolute(v):
        return None
    if _DRIVE_ROOT_RE.match(v) or v in ("/", "\\"):
        return (
            f"refusing `set {key}`: '{value}' is a bare drive root. Name a key's root "
            f"instead (`machine-local set {key} '${{repos.<slug>}}/<relative tail>'`)."
        )
    disp, cmp_ = _spelled_path(v)
    best: tuple[str, str] | None = None
    for layer in _build_resolution_layers(reg_dir):
        for other, root in layer.items():
            if not other.startswith("repos.") or not isinstance(root, str):
                continue
            root = root.strip()
            if not root or root.startswith("${") or not _looks_absolute(root):
                continue
            r_disp, r_cmp = _spelled_path(root)
            if len(r_cmp) <= 3 or r_cmp == "/":
                continue
            if cmp_ == r_cmp or cmp_.startswith(r_cmp + "/"):
                if best is None or len(r_cmp) > len(best[1]):
                    best = (other, r_cmp)
    if best is None:
        return None
    tail = disp[len(best[1]):].lstrip("/")
    ref = "${" + best[0] + "}" + (f"/{tail}" if tail else "")
    return (
        f"refusing `set {key}`: '{value}' spells an absolute path under the root of "
        f"'{best[0]}', so it breaks when that repo moves. Use the key reference: "
        f"`machine-local set {key} '{ref}'`."
    )


def cmd_check(args: argparse.Namespace) -> int:
    """Implement: machine-local check — report registry keys shadowed by a concern file.

    Read-only. Exit 0 when clean, 1 when any shadowed key is found.
    """
    reg_dir = _registry_dir()
    shadowed: list = []
    _build_resolution_layers(reg_dir, shadowed=shadowed)
    if not shadowed:
        print("machine-local check: ok")
        return 0
    for key, source, ns in shadowed:
        print(
            f"shadowed: key '{key}' in {source} belongs to concern namespace "
            f"'{ns}'; the concern file wins and this entry is ignored."
        )
        print(
            f"  remedy: remove '{key}' from {source}; {ns}.local.toml owns it."
        )
    return 1


def cmd_path(args: argparse.Namespace) -> int:
    reg_dir = _registry_dir()
    abs_path = os.path.abspath(os.path.join(reg_dir, "registry.toml"))
    print(abs_path)
    return 0


def cmd_dir(args: argparse.Namespace) -> int:
    """Implement: machine-local dir — print absolute path to machine-local directory.

    Returns <settings-home>/machine-local as an absolute path. This is the
    sanctioned dir-resolution primitive for concern-file readers (e.g. project-rag)
    to bind to, replacing any direct or hardcoded reads of ~/.claude/machine-local/.

    Always resolves through the settings-home seam (_settings_home()), which
    honours COORDINATOR_SETTINGS_HOME, else <home>/.coordinator-claude-settings.
    MACHINE_LOCAL_REGISTRY_DIR (test-isolation override) does NOT affect this
    subcommand — it overrides where reads happen (registry dir), not where the
    canonical settings-home-based machine-local directory is.

    Differs from 'path': 'path' returns the registry.toml FILE path inside the
    directory; 'dir' returns the DIRECTORY path itself.

    Spec backlink: docs/plans/2026-07-06-durable-substrate-to-settings-home.md § C2
    RAG-bait: machine-local dir; sanctioned dir-resolution primitive; concern-file
              readers bind here; replaces hardcoded ~/.claude/machine-local reads
    """
    abs_dir = os.path.abspath(os.path.join(_settings_home(), "machine-local"))
    print(abs_dir)
    return 0


def _build_header_pats(prefix_parts: list[str]) -> tuple[re.Pattern[str], re.Pattern[str]]:
    table_path = ".".join(prefix_parts)
    quoted_segs = r'\s*\.\s*'.join(f'"{re.escape(p)}"' for p in prefix_parts)
    h_pat = re.compile(
        r"^\[\s*(?:" + re.escape(table_path) + r"|" + quoted_segs + r")\s*\][ \t]*(?:#[^\n]*)?$",
        re.MULTILINE,
    )
    aot_pat = re.compile(
        r"^\[\[\s*(?:" + re.escape(table_path) + r"|" + quoted_segs + r")\s*\]\][ \t]*(?:#[^\n]*)?$",
        re.MULTILINE,
    )
    return h_pat, aot_pat


def _locate_existing_definition(content: str, key: str) -> dict | None:

    flat_pat = re.compile(
        r'^(\s*"' + re.escape(key) + r'"\s*=\s*)(?:"[^"]*"|\'[^\']*\')([ \t]*(?:#[^\n]*)?)',
        re.MULTILINE,
    )
    fm = flat_pat.search(content)
    if fm:
        return {"kind": "flat", "match": fm}

    if "." not in key:
        next_section_pat_preamble = re.compile(r"^\[", re.MULTILINE)
        nm_preamble = next_section_pat_preamble.search(content)
        preamble_end = nm_preamble.start() if nm_preamble else len(content)
        preamble = content[:preamble_end]
        bare_pat = re.compile(
            r'^(\s*' + re.escape(key) + r'\s*=\s*)(?:"[^"]*"|\'[^\']*\')([ \t]*(?:#[^\n]*)?)',
            re.MULTILINE,
        )
        bm = bare_pat.search(preamble)
        if bm:
            return {"kind": "flat", "match": bm}

    parts = key.split(".")
    next_section_pat = re.compile(r"^\[", re.MULTILINE)


    for i in range(len(parts) - 1, 0, -1):
        prefix_parts = parts[:i]
        leaf_path = ".".join(parts[i:])
        h_pat, aot_pat = _build_header_pats(prefix_parts)
        if aot_pat.search(content):
            return {"kind": "array-of-tables-detected", "table_path": ".".join(prefix_parts)}
        hm = h_pat.search(content)
        if not hm:
            continue
        section_start = hm.end()
        nm = next_section_pat.search(content, section_start)
        section_end = nm.start() if nm else len(content)
        section_body = content[section_start:section_end]
        leaf_pat = re.compile(
            r"^([ \t]*" + re.escape(leaf_path) + r"[ \t]*=[ \t]*)(?:\"[^\"]*\"|'[^']*')([ \t]*(?:#[^\n]*)?)",
            re.MULTILINE,
        )
        leaf_m = leaf_pat.search(section_body)
        if leaf_m:
            return {
                "kind": "table-leaf",
                "leaf_match": leaf_m,
                "abs_start": section_start + leaf_m.start(),
                "abs_end": section_start + leaf_m.end(),
            }

    for i in range(len(parts) - 1, 0, -1):
        prefix_parts = parts[:i]
        leaf_path = ".".join(parts[i:])
        h_pat, _aot = _build_header_pats(prefix_parts)
        hm = h_pat.search(content)
        if not hm:
            continue
        section_start = hm.end()
        nm = next_section_pat.search(content, section_start)
        section_end = nm.start() if nm else len(content)
        return {
            "kind": "table-header-only",
            "section_start": section_start,
            "section_end": section_end,
            "leaf_path": leaf_path,
        }

    return None


def _locate_existing_array_span(content: str, key: str) -> dict | None:
    parts = key.split(".")

    for i in range(len(parts), 0, -1):
        prefix_parts = parts[:i]
        _, aot_pat = _build_header_pats(prefix_parts)
        if aot_pat.search(content):
            return {"kind": "array-of-tables-detected", "table_path": ".".join(prefix_parts)}

    array_open_pat = re.compile(
        r'^(\s*"' + re.escape(key) + r'"\s*=\s*\[)',
        re.MULTILINE,
    )
    m = array_open_pat.search(content)
    if not m:
        return None

    open_pos = m.start() + m.group(0).index("[")
    depth = 0
    close_pos = None
    for i, ch in enumerate(content[open_pos:], start=open_pos):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                close_pos = i
                break
    if close_pos is None:
        return None

    span_start = m.start()
    span_end = close_pos + 1
    if span_end < len(content) and content[span_end] == "\n":
        span_end += 1

    comment_start = None
    line_before_start = content.rfind("\n", 0, m.start())
    if line_before_start != -1:
        prev_line_start = content.rfind("\n", 0, line_before_start)
        if prev_line_start == -1:
            prev_line_start = 0
        else:
            prev_line_start += 1
        prev_line = content[prev_line_start:line_before_start]
        if prev_line.strip().startswith("#"):
            comment_start = prev_line_start

    return {
        "kind": "flat-array",
        "span_start": span_start,
        "span_end": span_end,
        "comment_start": comment_start,
    }


def _reject_single_quote_element(element: str) -> bool:
    return "'" in element


def _build_array_content(key: str, elements: list[str], date_tag: str,
                         provenance_comment: str | None = None) -> str:
    comment = provenance_comment if provenance_comment is not None else f"# array-append {date_tag}"
    rows = "".join(f"  '{e}',\n" for e in elements)
    return f'{comment}\n"{key}" = [\n{rows}]\n'


def _read_bytes_shared(path: str) -> bytes:
    """Read a whole file without blocking a concurrent replace of it.

    Trap: CPython open() omits FILE_SHARE_DELETE on Windows, so a reader holding
    the handle makes every replace of the file fail (WinError 5). Opens with
    share R|W|D, reads fully and closes before the caller parses. Missing file
    raises FileNotFoundError like open(). Stays local: this template is
    stdlib-only and cannot import coordinator_core.
    """
    if os.name == "nt":
        try:
            import _winapi
            import msvcrt
        except ImportError:
            _winapi = None
        if _winapi is not None:
            handle = _winapi.CreateFile(
                os.fspath(path), 0x80000000, 0x7, 0, 3, 0, 0  # GENERIC_READ, share R|W|D, OPEN_EXISTING
            )
            try:
                fd = msvcrt.open_osfhandle(int(handle), os.O_RDONLY)
            except BaseException:
                _winapi.CloseHandle(handle)
                raise
            with os.fdopen(fd, "rb") as f:
                return f.read()
    with open(path, "rb") as f:
        return f.read()


def _read_text_shared(path: str) -> str:
    return _read_bytes_shared(path).decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")


def _replace_posix_windows(src: str, dst: str) -> bool:
    """Rename src over dst with POSIX semantics (lands against open readers).

    Returns False on any failure so the caller falls to the os.replace ladder
    (non-NTFS, pre-1607, or a reader outside the share-delete chokepoints).
    """
    try:
        import ctypes
        import struct
        import _winapi
    except ImportError:
        return False
    try:
        handle = _winapi.CreateFile(os.path.abspath(src), 0x00010000, 0x7, 0, 3, 0, 0)  # DELETE
    except OSError:
        return False
    try:
        name = os.path.abspath(dst).encode("utf-16-le")
        # FILE_RENAME_INFO: Flags(DWORD) pad, RootDirectory(HANDLE), FileNameLength(DWORD), FileName[]
        # flags 0x1 REPLACE_IF_EXISTS | 0x2 POSIX_SEMANTICS
        buf = struct.pack("@IPI", 0x3, 0, len(name)) + name + b"\0\0"
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.SetFileInformationByHandle.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32,
        ]
        k32.SetFileInformationByHandle.restype = ctypes.c_int
        return bool(k32.SetFileInformationByHandle(int(handle), 22, buf, len(buf)))  # FileRenameInfoEx
    finally:
        _winapi.CloseHandle(handle)


def _replace_with_retry(src: str, dst: str) -> None:
    """os.replace that survives concurrent readers on Windows.

    Trap: classic os.replace onto a file any other process holds open raises
    PermissionError (WinError 5/32), FILE_SHARE_DELETE readers included; a
    bounded backoff cannot converge under polling readers. Tries the
    POSIX-semantics rename first (lands against share-delete readers), then
    the bounded ladder (~1s, 11 tries) as the residual for plain-open readers
    and non-NTFS; the final failure is re-raised for the caller to clean up.
    Stays local: this template is stdlib-only and cannot import coordinator_core.
    """
    import time

    if os.name == "nt" and _replace_posix_windows(src, dst):
        return
    delay = 0.01
    for attempt in range(11):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if os.name != "nt" or attempt == 10:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 0.16)


def _write_registry_file(target_path: str, new_content: str, is_new: bool) -> int:
    tmp_path = target_path + f".tmp.{os.getpid()}"
    try:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(new_content)
        if not is_new:
            try:
                os.chmod(tmp_path, os.stat(target_path).st_mode)
            except OSError:
                pass
        _replace_with_retry(tmp_path, target_path)
    except Exception as exc:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        print(f"machine-local: write failed: {exc}", file=sys.stderr)
        return 1
    return 0


def _load_registry_target(reg_dir: str, write_global: bool) -> tuple[str, str, str, bool]:
    target_file = "registry.toml" if write_global else "registry.local.toml"
    target_path = os.path.join(reg_dir, target_file)
    if os.path.exists(target_path):
        content = _read_text_shared(target_path)
        is_new = False
    else:
        is_new = True
        content = (
            f"# {target_file}  (created by `machine-local`)\n"
            "#\n"
            "# WARNING: Use `machine-local set <key> <value>` to add or change values.\n"
            "# Direct hand-edits are fragile: they do not reproduce on reinstall and\n"
            "# will not transfer automatically to a new machine.\n"
            "schema = 1\n"
        )
    return target_file, target_path, content, is_new


def _check_concern_namespace(reg_dir: str, key: str) -> int:
    reg_path = os.path.join(reg_dir, "registry.toml")
    reg_local_path = os.path.join(reg_dir, "registry.local.toml")
    concerns_set = set()
    for p in (reg_path, reg_local_path):
        if os.path.exists(p):
            d = _load_toml(p)
            for c in d.get("concerns", []):
                concerns_set.add(str(c).lower())
    if concerns_set:
        first_seg = key.split(".")[0].lower()
        if first_seg in concerns_set:
            c_match = first_seg
            print(
                f"machine-local: key '{key}' belongs to concern namespace '{c_match}'. "
                f"Write to {c_match}.local.toml instead (that concern file owns this namespace).",
                file=sys.stderr,
            )
            return 1
    return 0


def cmd_array_append(args: argparse.Namespace) -> int:
    reg_dir = _registry_dir()

    rc = _check_concern_namespace(reg_dir, args.key)
    if rc != 0:
        return rc

    key = args.key
    element = args.element
    dry_run = args.dry_run

    if _reject_single_quote_element(element):
        print(
            f"machine-local: refusing to write element containing single quote: {element!r}. "
            "Literal-string TOML has no escape for single quote.",
            file=sys.stderr,
        )
        return 1

    refusal = _absolute_path_refusal(reg_dir, key, element)
    if refusal:
        print(f"machine-local: {refusal}", file=sys.stderr)
        return 1

    _target_file, target_path, content, is_new = _load_registry_target(reg_dir, args.write_global)
    date_tag = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


    try:
        pre_raw = tomllib.loads(content)
        _cursor = pre_raw
        for seg in key.split("."):
            if isinstance(_cursor, dict) and seg in _cursor:
                _cursor = _cursor[seg]
            else:
                if isinstance(_cursor, dict) and key in _cursor:
                    _cursor = _cursor[key]
                    break
                _cursor = None
                break
        raw_existing = _cursor
        if raw_existing is None and key in pre_raw:
            raw_existing = pre_raw[key]
    except tomllib.TOMLDecodeError:
        raw_existing = None

    if isinstance(raw_existing, str):
        print(
            f"machine-local: '{key}' is a scalar; refusing to append — "
            "hand-edit or use `array-set`.",
            file=sys.stderr,
        )
        return 1

    if isinstance(raw_existing, dict):
        print(
            f"machine-local: '{key}' is defined as an inline table; "
            "cannot use array-append. Hand-edit the file to update it.",
            file=sys.stderr,
        )
        return 1

    array_span = _locate_existing_array_span(content, key)
    if array_span is not None and array_span["kind"] == "array-of-tables-detected":
        print(
            f"machine-local: '{key}' is defined as an array-of-tables ([[{array_span['table_path']}]]); "
            "cannot use array-append. Hand-edit the file to update it.",
            file=sys.stderr,
        )
        return 1

    current_elements: list[str] = []
    provenance_comment: str | None = None

    if array_span is not None and array_span["kind"] == "flat-array":
        try:
            parsed_existing = tomllib.loads(content)
            flat_raw = _get_raw_list(parsed_existing, key)
            if isinstance(flat_raw, list):
                current_elements = [str(e) for e in flat_raw]
        except tomllib.TOMLDecodeError:
            pass

        if array_span["comment_start"] is not None:
            cstart = array_span["comment_start"]
            cend = content.find("\n", cstart)
            if cend == -1:
                cend = len(content)
            provenance_comment = content[cstart:cend]

    if element in current_elements:
        if dry_run:
            print(f"[dry-run] '{key}': element already present (no-op): {element!r}")
        else:
            print(f"machine-local: '{key}': element already present (no-op): {element!r}")
        return 0

    new_elements = current_elements + [element]
    array_block = _build_array_content(key, new_elements, date_tag, provenance_comment)

    if array_span is not None and array_span["kind"] == "flat-array":
        replace_start = array_span["comment_start"] if array_span["comment_start"] is not None else array_span["span_start"]
        replace_end = array_span["span_end"]
        new_content = content[:replace_start] + array_block + content[replace_end:]
        action = "updated"
    else:
        section_pat = re.compile(r"^\[", re.MULTILINE)
        m = section_pat.search(content)
        if m:
            insert_at = m.start()
            new_content = content[:insert_at].rstrip("\n") + "\n" + array_block + "\n" + content[insert_at:]
        else:
            new_content = content.rstrip("\n") + "\n" + array_block
        action = "added"

    try:
        parsed_new = tomllib.loads(new_content)
    except tomllib.TOMLDecodeError as exc:
        print(
            f"machine-local: refusing to write — post-build TOML is malformed: {exc}. "
            "This is a bug in machine-local array-append. File a report and edit by hand.",
            file=sys.stderr,
        )
        return 1

    roundtrip_list = _get_raw_list(parsed_new, key)
    if not isinstance(roundtrip_list, list) or element not in roundtrip_list:
        print(
            f"machine-local: refusing to write — post-build round-trip of '{key}' "
            f"did not contain the appended element {element!r}. "
            "Likely cause: key scoped into a table rather than at top level. "
            "File a report and edit the registry by hand.",
            file=sys.stderr,
        )
        return 1

    if dry_run:
        print(f"[dry-run] would have {action} array '{key}' (append {element!r}) in {target_path}")
        return 0

    rc = _write_registry_file(target_path, new_content, is_new)
    if rc != 0:
        return rc

    print(f"machine-local: {action} array '{key}' (appended {element!r}) in {target_path}")
    return 0


def cmd_array_set(args: argparse.Namespace) -> int:
    reg_dir = _registry_dir()

    rc = _check_concern_namespace(reg_dir, args.key)
    if rc != 0:
        return rc

    key = args.key
    elements = args.elements
    dry_run = args.dry_run

    for element in elements:
        if _reject_single_quote_element(element):
            print(
                f"machine-local: refusing to write element containing single quote: {element!r}. "
                "Literal-string TOML has no escape for single quote.",
                file=sys.stderr,
            )
            return 1
        refusal = _absolute_path_refusal(reg_dir, key, element)
        if refusal:
            print(f"machine-local: {refusal}", file=sys.stderr)
            return 1

    _target_file, target_path, content, is_new = _load_registry_target(reg_dir, args.write_global)
    date_tag = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        pre_raw = tomllib.loads(content)
        _cursor = pre_raw
        for seg in key.split("."):
            if isinstance(_cursor, dict) and seg in _cursor:
                _cursor = _cursor[seg]
            else:
                if isinstance(_cursor, dict) and key in _cursor:
                    _cursor = _cursor[key]
                    break
                _cursor = None
                break
        raw_existing = _cursor
        if raw_existing is None and key in pre_raw:
            raw_existing = pre_raw[key]
    except tomllib.TOMLDecodeError:
        raw_existing = None

    if isinstance(raw_existing, str):
        print(
            f"machine-local: '{key}' is a scalar; refusing to set array — "
            "hand-edit or use `set`.",
            file=sys.stderr,
        )
        return 1

    if isinstance(raw_existing, dict):
        print(
            f"machine-local: '{key}' is defined as an inline table; "
            "cannot use array-set. Hand-edit the file to update it.",
            file=sys.stderr,
        )
        return 1

    array_span = _locate_existing_array_span(content, key)
    if array_span is not None and array_span["kind"] == "array-of-tables-detected":
        print(
            f"machine-local: '{key}' is defined as an array-of-tables ([[{array_span['table_path']}]]); "
            "cannot use array-set. Hand-edit the file to update it.",
            file=sys.stderr,
        )
        return 1

    seen: set[str] = set()
    deduped: list[str] = []
    for e in elements:
        if e not in seen:
            seen.add(e)
            deduped.append(e)

    provenance_comment: str | None = None
    if array_span is not None and array_span["kind"] == "flat-array":
        if array_span["comment_start"] is not None:
            cstart = array_span["comment_start"]
            cend = content.find("\n", cstart)
            if cend == -1:
                cend = len(content)
            provenance_comment = content[cstart:cend]

    array_block = _build_array_content(key, deduped, date_tag, provenance_comment)

    if array_span is not None and array_span["kind"] == "flat-array":
        replace_start = array_span["comment_start"] if array_span["comment_start"] is not None else array_span["span_start"]
        replace_end = array_span["span_end"]
        new_content = content[:replace_start] + array_block + content[replace_end:]
        action = "replaced"
    else:
        section_pat = re.compile(r"^\[", re.MULTILINE)
        m = section_pat.search(content)
        if m:
            insert_at = m.start()
            new_content = content[:insert_at].rstrip("\n") + "\n" + array_block + "\n" + content[insert_at:]
        else:
            new_content = content.rstrip("\n") + "\n" + array_block
        action = "created"

    try:
        parsed_new = tomllib.loads(new_content)
    except tomllib.TOMLDecodeError as exc:
        print(
            f"machine-local: refusing to write — post-build TOML is malformed: {exc}. "
            "This is a bug in machine-local array-set. File a report and edit by hand.",
            file=sys.stderr,
        )
        return 1

    roundtrip_list = _get_raw_list(parsed_new, key)
    if not isinstance(roundtrip_list, list) or list(roundtrip_list) != deduped:
        print(
            f"machine-local: refusing to write — post-build round-trip of '{key}' "
            f"returned {roundtrip_list!r}, expected {deduped!r}. "
            "Likely cause: key scoped into a table rather than at top level. "
            "File a report and edit the registry by hand.",
            file=sys.stderr,
        )
        return 1

    if dry_run:
        print(f"[dry-run] would have {action} array '{key}' = {deduped!r} in {target_path}")
        return 0

    rc = _write_registry_file(target_path, new_content, is_new)
    if rc != 0:
        return rc

    print(f"machine-local: {action} array '{key}' = {deduped!r} in {target_path}")
    return 0


def _get_raw_list(parsed: dict, key: str) -> object:
    if key in parsed:
        return parsed[key]
    cursor: object = parsed
    for seg in key.split("."):
        if isinstance(cursor, dict) and seg in cursor:
            cursor = cursor[seg]
        else:
            return None
    return cursor


def _emit_concern_scalar(key: str, value: object) -> str:
    """Emit one TOML scalar line for a concern file, PRESERVING the value type.

    bool MUST be tested before int (bool subclasses int in Python). This mirrors
    the addon concern-file serializer's ``_emit_scalar_line`` so a co-writer's
    non-string scalar round-trips type-intact instead of being coerced to a
    quoted string. The load-bearing case is the DR-CONTRACT-001 contract-witness
    integer ``unreal.emit_shape_version = 1`` stamped by project-rag-ue-addon:
    coercing it to ``'1'`` is a value-shape (type) change DR-CONTRACT-001
    classifies as a breaking cross-repo ABI change requiring a paired memo, so a
    --concern read-merge of an addon-seeded file MUST NOT mangle it. Fails loud on
    a non-scalar (list/datetime) rather than silently corrupting it.

    Known limitation (code-reviewer F5): a non-finite float co-writer value
    (``nan``/``inf``) emits Python's bare repr, which most but not all TOML readers
    accept. No current concern writer emits floats (the DR-CONTRACT-001 surface is
    int-only), so this stays a documented edge rather than a guard.
    """
    if isinstance(value, str):
        return f"{key} = '{value}'"
    if isinstance(value, bool):
        return f"{key} = {str(value).lower()}"
    if isinstance(value, (int, float)):
        return f"{key} = {value}"
    raise ValueError(
        f"cannot serialize non-scalar concern value for key {key!r}: "
        f"{value!r} (type {type(value).__name__})"
    )


def _serialize_concern_file(concern_name: str, body: dict, provenance: dict,
                            schema_val: object = 1) -> str:
    """Deterministically serialize a concern file (<name>.local.toml).

    Layout: a managed-header comment, a `schema` line, the self-named
    ``[<concern_name>]`` table holding the user keys (nested dotted bare keys
    become ``[<concern_name>.<sub>]`` sub-tables), then one
    ``[provenance.<bare_key>]`` table per recorded key. Writing under the
    self-named table is required: the reader's `_flatten_concern` elides
    ``[<concern_name>]`` so ``samples_root`` resolves as
    ``<concern_name>.samples_root`` — a flat ``"unreal.samples_root"`` key would
    double-prefix and fail to resolve (see test_doubled_prefix_does_not_resolve).

    Scalar values are emitted type-preserving via ``_emit_concern_scalar`` (str →
    literal-quote, bool → lowercase, int/float → bare) so a co-writer's non-string
    scalar (the DR-CONTRACT-001 ``emit_shape_version`` int) round-trips intact; the
    caller rejects values/keys containing a single quote (literal TOML has no
    escape). Only a NEW concern file is built here; an existing one is edited in place by
    ``_concern_text_edit``, because its co-writer's tables must survive byte-identical.
    """
    def _emit_table(header: str, table: dict) -> str:
        scalars = {k: v for k, v in table.items() if not isinstance(v, dict)}
        subtables = {k: v for k, v in table.items() if isinstance(v, dict)}
        out = [f"[{header}]"]
        for k in sorted(scalars):
            out.append(_emit_concern_scalar(k, scalars[k]))
        chunks = ["\n".join(out)]
        for k in sorted(subtables):
            chunks.append(_emit_table(f"{header}.{k}", subtables[k]))
        return "\n\n".join(chunks)

    lines = [
        f"# {concern_name}.local.toml  (managed by `machine-local set --concern`)",
        "#",
        "# WARNING: Use `machine-local set --concern <name> <key> <value>` to add or",
        "# change values. Direct hand-edits are fragile: they do not reproduce on",
        "# reinstall and will not transfer automatically to a new machine.",
        f"schema = {schema_val}",
        "",
        _emit_table(concern_name, body),
        "",
    ]
    for bare in sorted(provenance):
        p = provenance[bare]
        lines.append(f"[provenance.{bare}]")
        for pk in ("written_by", "written_at", "source"):
            if pk in p:
                lines.append(f"{pk} = '{p[pk]}'")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


_TOML_HEADER_RE = re.compile(r"^[ \t]*(\[\[?)[ \t]*([^\[\]#]*?)[ \t]*\]\]?[ \t]*(?:#.*)?$")


def _toml_sections(lines: list) -> list:
    """[(header, is_array, start, end)] over raw lines; the preamble is ("", False, 0, first header)."""
    out = []
    header, is_array, start = "", False, 0
    for i, raw in enumerate(lines):
        m = _TOML_HEADER_RE.match(raw.rstrip("\r"))
        if m:
            out.append((header, is_array, start, i))
            header = ".".join(seg.strip().strip("'\"") for seg in m.group(2).split("."))
            is_array, start = m.group(1) == "[[", i
    out.append((header, is_array, start, len(lines)))
    return out


def _toml_find_key(lines: list, table: str, key: str) -> tuple:
    """(line index | None, (start, end) | None) of `key = ...` directly under `[table]`."""
    k = re.escape(key)
    rx = re.compile(rf"^[ \t]*(?:{k}|'{k}'|\"{k}\")[ \t]*=")
    for header, is_array, start, end in _toml_sections(lines):
        if header == table and not is_array:
            for i in range(start + 1 if table else start, end):
                if rx.match(lines[i]):
                    return i, (start, end)
            return None, (start, end)
    return None, None


def _toml_set_key(lines: list, table: str, key: str, line: str, cr: str) -> list:
    lines = list(lines)
    idx, sect = _toml_find_key(lines, table, key)
    if idx is not None:
        lines[idx] = line + cr
        return lines
    if sect is None:
        return _toml_append_section(lines, table, [line], cr)
    start, end = sect
    at = start + 1 if table else start
    for i in range(end - 1, at - 1, -1):
        text = lines[i].strip()
        if text and not text.startswith("#"):
            at = i + 1
            break
    lines.insert(at, line + cr)
    return lines


def _toml_drop_section(lines: list, table: str) -> list:
    for header, is_array, start, end in _toml_sections(lines):
        if table and header == table and not is_array:
            return lines[:start] + lines[end:]
    return list(lines)


def _toml_append_section(lines: list, table: str, body: list, cr: str) -> list:
    lines = list(lines)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines + ([cr] if lines else []) + [f"[{table}]{cr}"] + [b + cr for b in body] + [""]


def _toml_foreign(parsed: dict, name: str, segs: list) -> dict:
    """`parsed` minus the one key an edit owns (its concern-table, top-level and provenance
    homes), empty tables pruned: what an in-place concern edit must leave equal."""
    import copy

    out = copy.deepcopy(parsed)
    for path in ([name, *segs], list(segs), ["provenance", *segs]):
        cur = out
        for seg in path[:-1]:
            cur = cur.get(seg) if isinstance(cur, dict) else None
        if isinstance(cur, dict):
            cur.pop(path[-1], None)

    def prune(d: object) -> object:
        if not isinstance(d, dict):
            return d
        kept = {k: prune(v) for k, v in d.items()}
        return {k: v for k, v in kept.items() if v != {}}

    return prune(out)


def _concern_text_edit(text: str, parsed: dict, name: str, bare: str, value, prov_row) -> str | None:
    """Set (`value` a str) or remove (`value` None) one key in an existing concern file IN PLACE.

    Concern files are co-written: project-rag-cli owns the top-level scalars, [env],
    [provenance] and [bin] of project_rag.local.toml, and its serve reads only data["env"].
    So only the key's own line and its `[provenance.<bare>]` section change; every other byte
    stays. None when no in-place edit both resolves as intended and leaves every other key
    equal -- the caller refuses rather than reserializing the file.
    """
    cr = "\r" if "\r\n" in text else ""
    segs = bare.split(".")
    leaf = segs[-1]
    own, top = ".".join([name, *segs[:-1]]), ".".join(segs[:-1])
    lines = text.split("\n")
    table = own
    if _toml_find_key(lines, own, leaf)[0] is None and _toml_find_key(lines, top, leaf)[0] is not None:
        table = top
    if value is None:
        idx, _ = _toml_find_key(lines, table, leaf)
        if idx is None:
            return None
        candidates = ["\n".join(_toml_drop_section(lines[:idx] + lines[idx + 1:], f"provenance.{bare}"))]
    else:
        lines = _toml_set_key(lines, table, leaf, _emit_concern_scalar(leaf, value), cr)
        prov = [f"{k} = '{v}'" for k, v in prov_row.items()]
        with_prov = _toml_append_section(
            _toml_drop_section(lines, f"provenance.{bare}"), f"provenance.{bare}", prov, cr
        )
        candidates = ["\n".join(with_prov), "\n".join(lines)]
    key = f"{name}.{bare}"
    for cand in candidates:
        try:
            new = tomllib.loads(cand)
        except tomllib.TOMLDecodeError:
            continue
        got = _flatten_concern(name, new).get(key)
        if (got is not None) if value is None else (str(got) != str(value)):
            continue
        if _toml_foreign(parsed, name, segs) == _toml_foreign(new, name, segs):
            return cand
    return None


def _cmd_set_concern(args: argparse.Namespace) -> int:
    reg_dir = _registry_dir()
    raw_concern = args.concern.strip()
    name = raw_concern.lower()
    key = args.key
    value = args.value

    if args.write_global:
        print(
            "machine-local: --concern and --global are mutually exclusive — concern "
            "files are per-machine (<name>.local.toml). Drop --global.",
            file=sys.stderr,
        )
        return 1

    # Concern names AND keys are lowercase by contract (the reader's self-named-table
    # resolution and the addon serializer both use lowercase). Reject mixed-case
    # fail-loud rather than silently normalizing it — detect-then-fail-loud
    # (coordinator doctrine) applied UNIFORMLY to both the --concern arg and the key
    # (code-reviewer F2: silently lowercasing the concern while rejecting the key was
    # an inconsistent footgun). Avoids a confusing round-trip-None refusal on a write
    # the operator believes is valid.
    if raw_concern != name:
        print(
            f"machine-local: concern names must be lowercase — got '{raw_concern}'. "
            f"Retry with '{name}'.",
            file=sys.stderr,
        )
        return 1
    if key != key.lower():
        print(
            f"machine-local: concern keys must be lowercase — got '{key}'. "
            f"Retry with '{key.lower()}'.",
            file=sys.stderr,
        )
        return 1

    first_seg = key.split(".")[0].lower()
    if first_seg != name:
        print(
            f"machine-local: key '{key}' is not under concern namespace '{name}'. "
            f"A `--concern {name}` write requires a key prefixed '{name}.' "
            f"(e.g. {name}.some_key). Refusing cross-concern write.",
            file=sys.stderr,
        )
        return 1

    bare = key[len(name) + 1:]
    if not bare:
        print(
            f"machine-local: key '{key}' has no sub-key after the concern prefix "
            f"'{name}.'. Provide a full key, e.g. {name}.some_key.",
            file=sys.stderr,
        )
        return 1

    if "'" in value:
        print(
            f"machine-local: refusing to write value containing single quote: {value!r}. "
            "Literal-string TOML has no escape for single quote.",
            file=sys.stderr,
        )
        return 1
    if "'" in bare:
        print(
            f"machine-local: refusing to write key containing single quote: {bare!r}.",
            file=sys.stderr,
        )
        return 1

    refusal = _absolute_path_refusal(reg_dir, key, value)
    if refusal:
        print(f"machine-local: {refusal}", file=sys.stderr)
        return 1

    registered = set()
    for p in (os.path.join(reg_dir, "registry.toml"),
              os.path.join(reg_dir, "registry.local.toml")):
        if os.path.exists(p):
            for c in _load_toml(p).get("concerns", []):
                registered.add(str(c).lower())
    if registered and name not in registered:
        print(
            f"machine-local: note: concern '{name}' is not in the `concerns` array — "
            f"'{key}' will be written to {name}.local.toml but will NOT resolve via "
            f"`machine-local get` until '{name}' is registered (add it to `concerns` "
            "in registry.toml).",
            file=sys.stderr,
        )

    target_path = os.path.join(reg_dir, f"{name}.local.toml")

    date_tag = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    prov_row = {"written_by": "machine-local", "written_at": date_tag, "source": "cli:--concern"}
    if not os.path.exists(target_path):
        is_new = True
        body: dict = {}
        cursor = body
        segs = bare.split(".")
        for seg in segs[:-1]:
            cursor = cursor.setdefault(seg, {})
        cursor[segs[-1]] = value
        new_content = _serialize_concern_file(name, body, {bare: prov_row})
    else:
        is_new = False
        existing_content = _read_bytes_shared(target_path).decode("utf-8")  # keep its newlines
        try:
            existing = tomllib.loads(existing_content)
        except tomllib.TOMLDecodeError as exc:
            print(
                f"machine-local: cannot parse existing {target_path}: {exc}. "
                "Fix or remove it by hand.",
                file=sys.stderr,
            )
            return 1
        new_content = _concern_text_edit(existing_content, existing, name, bare, value, prov_row)
        if new_content is None:
            print(
                f"machine-local: refusing to write — {target_path} holds {key!r} in a shape "
                f"this writer cannot edit in place without changing other keys. Set {key!r} by hand.",
                file=sys.stderr,
            )
            return 1

    try:
        parsed = tomllib.loads(new_content)
    except tomllib.TOMLDecodeError as exc:
        print(
            f"machine-local: refusing to write — post-build TOML is malformed: {exc}. "
            "This is a bug in machine-local set --concern, not your input. "
            "File a report and edit the concern file by hand for now.",
            file=sys.stderr,
        )
        return 1
    resolved = _flatten_concern(name, parsed).get(key)
    # str() both sides intentionally (code-reviewer F7): `value` is always a str
    # from argparse, while `resolved` may come back typed (e.g. an int the reader
    # parsed). This check validates the key we just WROTE landed; type-fidelity of
    # PRESERVED co-writer scalars is covered by _emit_concern_scalar, not here.
    if str(resolved) != str(value):
        print(
            f"machine-local: refusing to write — round-trip read of {key!r} returned "
            f"{resolved!r}, expected {value!r}. File a report and edit by hand for now.",
            file=sys.stderr,
        )
        return 1

    if args.dry_run:
        print(f"[dry-run] would set {key!r} = {value!r} in {target_path}")
        return 0

    if _write_registry_file(target_path, new_content, is_new) != 0:
        return 1

    print(f"machine-local: set {key!r} = {value!r} in {target_path}")
    return 0


def cmd_set(args: argparse.Namespace) -> int:

    if getattr(args, "concern", None):
        return _cmd_set_concern(args)

    reg_dir = _registry_dir()
    target_file = "registry.toml" if args.write_global else "registry.local.toml"
    target_path = os.path.join(reg_dir, target_file)

    key = args.key
    value = args.value
    dry_run = args.dry_run

    if args.write_global and key.startswith("repos."):
        print(
            f"machine-local: refusing `set --global {key}`: repos.* is resolved only from "
            "registry.local.toml (the local scope), so a --global write would be invisible "
            f"to `get`. Re-run without --global: `machine-local set {key} <path>`.",
            file=sys.stderr,
        )
        return 1

    rc = _check_concern_namespace(reg_dir, key)
    if rc != 0:
        return rc

    refusal = _external_collision_refusal(reg_dir, key, value)
    if refusal:
        print(f"machine-local: {refusal}", file=sys.stderr)
        return EXIT_OPERATIONAL

    refusal = _absolute_path_refusal(reg_dir, key, value)
    if refusal:
        print(f"machine-local: {refusal}", file=sys.stderr)
        return 1

    if os.path.exists(target_path):
        content = _read_text_shared(target_path)
        is_new = False
    else:
        is_new = True
        content = (
            f"# {target_file}  (created by `machine-local set`)\n"
            "#\n"
            "# WARNING: Use `machine-local set <key> <value>` to add or change values.\n"
            "# Direct hand-edits are fragile: they do not reproduce on reinstall and\n"
            "# will not transfer automatically to a new machine.\n"
            "schema = 1\n"
        )

    date_tag = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if "'" in value:
        print(
            f"machine-local: refusing to write value containing single quote: {value!r}. "
            "Literal-string TOML has no escape for single quote.",
            file=sys.stderr,
        )
        return 1

    value_literal = f"'{value}'"

    update_result = _locate_existing_definition(content, key)

    try:
        _pre_parsed_for_guard = tomllib.loads(content)
        _pre_flat_for_guard = _flatten_nested(_pre_parsed_for_guard)
        _pre_val_for_guard = _pre_flat_for_guard.get(key)
    except tomllib.TOMLDecodeError:
        _pre_val_for_guard = None

    if isinstance(_pre_val_for_guard, list):
        _raw_for_guard = _get_raw_list(_pre_parsed_for_guard, key)
        if isinstance(_raw_for_guard, list):
            print(
                f"machine-local: '{key}' is an array; use `array-append`/`array-set`, not `set`.",
                file=sys.stderr,
            )
            return 1

    if update_result is not None and update_result["kind"] == "array-of-tables-detected":
        print(
            f"machine-local: key '{key}' resolves in '{target_path}' but its "
            "definition shape (inline table, array-of-tables, or other) is not "
            "modifiable by this writer. Hand-edit the file to update it.",
            file=sys.stderr,
        )
        return 1

    if update_result is None:
        try:
            pre_parsed = tomllib.loads(content)
            pre_resolved = _flatten_nested(pre_parsed).get(key)
        except tomllib.TOMLDecodeError:
            pre_resolved = None

        if pre_resolved is not None:
            print(
                f"machine-local: key '{key}' resolves in '{target_path}' but its "
                "definition shape (inline table, array-of-tables, or other) is not "
                "modifiable by this writer. Hand-edit the file to update it.",
                file=sys.stderr,
            )
            return 1

        section_pat = re.compile(r"^\[", re.MULTILINE)
        m = section_pat.search(content)
        new_line = f'"{key}" = {value_literal}  # set {date_tag}\n'
        if m:
            insert_at = m.start()
            new_content = content[:insert_at].rstrip("\n") + "\n" + new_line + "\n" + content[insert_at:]
        else:
            new_content = content.rstrip("\n") + "\n" + new_line
        action = "added"
    else:
        kind = update_result["kind"]
        if kind == "flat":
            m = update_result["match"]
            new_content = (
                content[:m.start()]
                + m.group(1) + value_literal + m.group(2)
                + content[m.end():]
            )
            action = "updated"
        elif kind == "table-leaf":
            abs_start = update_result["abs_start"]
            abs_end = update_result["abs_end"]
            leaf_m = update_result["leaf_match"]
            new_content = (
                content[:abs_start]
                + leaf_m.group(1) + value_literal + leaf_m.group(2)
                + content[abs_end:]
            )
            action = "updated"
        elif kind == "table-header-only":
            section_start = update_result["section_start"]
            section_end = update_result["section_end"]
            leaf_path = update_result["leaf_path"]
            section_body = content[section_start:section_end]
            indent_match = re.search(r"^([ \t]+)\S", section_body, re.MULTILINE)
            indent = indent_match.group(1) if indent_match else ""
            trimmed = section_body.rstrip("\n")
            suffix = section_body[len(trimmed):]
            new_section = (
                trimmed
                + f"\n{indent}{leaf_path} = {value_literal}  # set {date_tag}\n"
                + suffix
            )
            new_content = content[:section_start] + new_section + content[section_end:]
            action = "added"
        else:  # pragma: no cover — defensive
            print(f"machine-local: internal error: unknown match kind {kind!r}", file=sys.stderr)
            return 1

    try:
        parsed = tomllib.loads(new_content)
    except tomllib.TOMLDecodeError as exc:
        print(
            f"machine-local: refusing to write — post-build TOML is malformed: {exc}. "
            "This is a bug in machine-local set, not in your input. "
            "File a report and edit the registry by hand for now.",
            file=sys.stderr,
        )
        return 1

    resolved = _flatten_nested(parsed).get(key)
    if resolved != value:
        print(
            f"machine-local: refusing to write — post-build round-trip read of "
            f"{key!r} returned {resolved!r}, expected {value!r}. "
            "Likely cause: the registry contains a definition shape this writer "
            "does not yet handle, leaving a stale value still in scope. "
            "File a report and edit the registry by hand for now.",
            file=sys.stderr,
        )
        return 1

    if dry_run:
        print(f"[dry-run] would have {action} {key!r} = {value!r} in {target_path}")
        return 0

    if _write_registry_file(target_path, new_content, is_new) != 0:
        return 1

    print(f"machine-local: {action} {key!r} = {value!r} in {target_path}")
    return 0


def _remove_key(content: str, key: str) -> tuple[str, str | None]:
    try:
        parsed = tomllib.loads(content)
        flat = _flatten_nested(parsed)
        old_value = flat.get(key)
    except tomllib.TOMLDecodeError:
        return content, None

    if old_value is None:
        return content, None
    if not isinstance(old_value, str):
        return content, None

    locate = _locate_existing_definition(content, key)
    if locate is None:
        return content, None

    kind = locate["kind"]

    def _excise(line_start: int, match_end: int) -> str:
        line_end_pos = content.find("\n", match_end)
        line_end = line_end_pos + 1 if line_end_pos != -1 else len(content)
        remove_start = line_start
        if line_start > 0:
            prev_nl = content.rfind("\n", 0, line_start - 1)
            prev_line_start = 0 if prev_nl == -1 else prev_nl + 1
            prev_line = content[prev_line_start : line_start - 1]
            if prev_line.strip().startswith("#"):
                remove_start = prev_line_start
        return content[:remove_start] + content[line_end:]

    if kind == "flat":
        m = locate["match"]
        # MULTILINE ^ matched at line_start; m.start() IS the start of the key's line.
        return _excise(m.start(), m.end()), old_value

    if kind == "table-leaf":
        # abs_start = section_start + leaf_m.start(). leaf_pat's leading
        # whitespace class is [ \t]* (horizontal only, never \s*) so MULTILINE
        # ^ + leaf_m.start() lands on the first character of the leaf's own
        # line — never on the newline terminating the [section] header above
        # it, which \s* would have swallowed for a leaf immediately after the
        # header (the first-leaf-under-a-header corruption case).
        abs_start = locate["abs_start"]
        abs_end = locate["abs_end"]
        return _excise(abs_start, abs_end), old_value

    return content, None


def _unset_concern_key(name: str, key: str, dry_run: bool, explicit: bool) -> int | None:
    """Remove `key` from `<name>.local.toml` together with its provenance row (if any).

    Returns None when the concern file does not hold the key and the caller was not
    explicit, so the registry path can answer; otherwise an exit code, with a named
    reason and the concern file path on every non-zero return."""
    reg_dir = _registry_dir()
    path = os.path.join(reg_dir, f"{name}.local.toml")
    bare = key[len(name) + 1:] if key.lower().startswith(f"{name}.") else ""
    if not os.path.exists(path):
        if not explicit:
            return None
        print(f"machine-local: unset: {key!r} not set — concern file {path} does not exist.", file=sys.stderr)
        return EXIT_NOT_FOUND
    try:
        existing_text = _read_bytes_shared(path).decode("utf-8")  # keep its newlines
        existing = tomllib.loads(existing_text)
    except tomllib.TOMLDecodeError as exc:
        if not explicit:
            return None
        print(
            f"machine-local: unset: refusing — concern file {path} is malformed TOML: "
            f"{exc}. Fix the file's syntax before unsetting from it.",
            file=sys.stderr,
        )
        return EXIT_OPERATIONAL
    key = f"{name}.{bare}" if bare else key
    held = bool(bare) and _flatten_concern(name, existing).get(key) is not None
    if not held:
        if not explicit:
            return None
        print(f"machine-local: unset: {key!r} not set in concern file {path}; nothing removed.", file=sys.stderr)
        return EXIT_NOT_FOUND

    old_value = _flatten_concern(name, existing).get(key)
    new_content = _concern_text_edit(existing_text, existing, name, bare, None, None)
    if new_content is None:
        print(
            f"machine-local: unset: {key!r} is held in concern file {path} in a shape this "
            f"writer does not remove in place. Hand-edit {path}.",
            file=sys.stderr,
        )
        return EXIT_OPERATIONAL
    if dry_run:
        print(f"[dry-run] would remove {key!r} (was {old_value!r}) from {path}")
        return EXIT_OK
    if _write_registry_file(path, new_content, False) != 0:
        print(f"machine-local: unset: could not write concern file {path}.", file=sys.stderr)
        return EXIT_OPERATIONAL
    print(f"machine-local: removed {key!r} (was {old_value!r}) from {path}")
    _note_other_layer(key, path)
    return EXIT_OK


def cmd_unset(args: argparse.Namespace) -> int:
    reg_dir = _registry_dir()
    concern = getattr(args, "concern", None)
    if concern:
        raw = concern.strip()
        if raw != raw.lower() or not re.fullmatch(r"[a-z0-9_-]+", raw):
            print(
                f"machine-local: unset: concern names must be lowercase names — got "
                f"'{concern}'. Retry with e.g. --concern {raw.lower()}.",
                file=sys.stderr,
            )
            return EXIT_OPERATIONAL
        if args.write_global:
            print("machine-local: unset: --concern and --global are mutually exclusive.", file=sys.stderr)
            return EXIT_OPERATIONAL
        if args.key.split(".")[0].lower() != raw:
            print(
                f"machine-local: unset: key {args.key!r} is not under concern namespace "
                f"'{raw}' ({os.path.join(reg_dir, raw + '.local.toml')}). "
                f"A `--concern {raw}` unset needs a key prefixed '{raw}.'.",
                file=sys.stderr,
            )
            return EXIT_OPERATIONAL
        return _unset_concern_key(raw, args.key, args.dry_run, True)
    if not args.write_global:
        first = args.key.split(".")[0]
        if "." in args.key and re.fullmatch(r"[a-z0-9_-]+", first):
            rc = _unset_concern_key(first, args.key, args.dry_run, False)
            if rc is not None:
                return rc
    target_file = "registry.toml" if args.write_global else "registry.local.toml"
    target_path = os.path.join(reg_dir, target_file)
    key = args.key

    if not os.path.exists(target_path):
        print(f"machine-local: unset: {key!r} not set — {target_path} does not exist.", file=sys.stderr)
        _note_other_layer(key, target_path)
        return EXIT_NOT_FOUND

    content = _read_text_shared(target_path)

    try:
        parsed = tomllib.loads(content)
    except tomllib.TOMLDecodeError as exc:
        print(
            f"machine-local: unset: refusing — {target_path} is malformed TOML: "
            f"{exc}. Fix the file's syntax before unsetting from it.",
            file=sys.stderr,
        )
        return EXIT_OPERATIONAL

    flat = _flatten_nested(parsed)
    current = flat.get(key)
    if current is None:
        print(f"machine-local: unset: {key!r} not set in {target_path}; nothing removed.", file=sys.stderr)
        _note_other_layer(key, target_path)
        return EXIT_NOT_FOUND

    if isinstance(current, list):
        raw = _get_raw_list(parsed, key)
        if isinstance(raw, list):
            print(
                f"machine-local: unset: '{key}' is an array; use `array-set` to "
                "replace or clear it, not `unset`.",
                file=sys.stderr,
            )
            return EXIT_OPERATIONAL

    if not isinstance(current, str):
        print(
            f"machine-local: unset: '{key}' resolves to a {type(current).__name__}, "
            "not a string scalar; unset only handles string scalars. "
            f"Hand-edit {target_path} to remove it.",
            file=sys.stderr,
        )
        return EXIT_OPERATIONAL

    new_content, old_value = _remove_key(content, key)
    if old_value is None:
        print(
            f"machine-local: unset: '{key}' resolves in {target_path} but its "
            "definition shape (inline table, array-of-tables, or other) is not "
            f"surgically removable by this writer. Hand-edit {target_path} to remove it.",
            file=sys.stderr,
        )
        return EXIT_OPERATIONAL

    empty_header_note = False
    removed_kind = (_locate_existing_definition(content, key) or {}).get("kind")
    if removed_kind == "table-leaf":
        key_pos = content.find(key)
        preceding_headers = list(re.finditer(r"^\[[^\]]+\]\s*$", content[:key_pos], re.MULTILINE))
        if preceding_headers:
            header_line = preceding_headers[-1].group(0)
            header_pos_new = new_content.find(header_line)
            if header_pos_new != -1:
                body_start = header_pos_new + len(header_line)
                next_header = re.search(r"^\[[^\]]+\]\s*$", new_content[body_start:], re.MULTILINE)
                body_end = body_start + next_header.start() if next_header else len(new_content)
                body = new_content[body_start:body_end]
                empty_header_note = all(
                    (not line.strip()) or line.strip().startswith("#")
                    for line in body.splitlines()
                )

    try:
        reparsed = tomllib.loads(new_content)
    except tomllib.TOMLDecodeError as exc:
        print(
            f"machine-local: unset: refusing to write — post-removal TOML is "
            f"malformed: {exc}. This is a bug in machine-local unset, not in "
            "your input. File a report and edit the registry by hand for now.",
            file=sys.stderr,
        )
        return EXIT_OPERATIONAL

    if _flatten_nested(reparsed).get(key) is not None:
        print(
            f"machine-local: unset: refusing to write — post-removal round-trip "
            f"read of {key!r} still resolves in {target_path}. Likely cause: a "
            "duplicate definition this writer did not detect. File a report and "
            "edit the registry by hand for now.",
            file=sys.stderr,
        )
        return EXIT_OPERATIONAL

    if args.dry_run:
        print(f"[dry-run] would remove {key!r} (was {old_value!r}) from {target_path}")
        return EXIT_OK

    rc = _write_registry_file(target_path, new_content, False)
    if rc != 0:
        return EXIT_OPERATIONAL

    print(f"machine-local: removed {key!r} (was {old_value!r}) from {target_path}")
    if empty_header_note:
        print(
            f"machine-local: Note: an empty [<section>] header may remain in "
            f"{target_path} — this is harmless valid TOML; remove it manually "
            "if desired."
        )
    _note_other_layer(key, target_path)
    return EXIT_OK


def _remove_string_array_key(content: str, key: str) -> tuple[str, str | None]:
    """Excise a flat string array `key` (`leaf = [ ... ]` under its `[parent]`
    header, or `parent.leaf = [ ... ]` at the top level). `(content, None)` when
    the definition is in any other shape — the caller refuses rather than guesses."""
    parent, _, leaf = key.rpartition(".")
    candidates = []
    header = re.search(rf"^\[{re.escape(parent)}\]\s*$", content, re.MULTILINE)
    if header:
        nxt = re.search(r"^\[", content[header.end():], re.MULTILINE)
        end = header.end() + nxt.start() if nxt else len(content)
        candidates.append((header.end(), end, re.escape(leaf)))
    first = re.search(r"^\[", content, re.MULTILINE)
    candidates.append((0, first.start() if first else len(content), re.escape(key)))
    for start, end, name in candidates:
        m = re.search(rf"^[ \t]*{name}[ \t]*=[ \t]*\[[^\[\]]*\][ \t]*(#[^\n]*)?\n?",
                      content[start:end], re.MULTILINE)
        if m:
            return content[:start + m.start()] + content[start + m.end():], m.group(0).strip()
    return content, None


def _drop_empty_publisher_headers(content: str) -> str:
    """Remove `[publish...]` headers whose body is only blank lines. A header
    whose body holds a comment is kept: the comment may be the operator's."""
    pattern = re.compile(r"^\[publish(\.[^\]]*)?\][ \t]*(?:\n|\Z)(?:[ \t]*\n)*(?=\[|\Z)", re.MULTILINE)
    while True:
        new = pattern.sub("", content)
        if new == content:
            return content
        content = new


def _note_other_layer(key: str, target_path: str) -> None:
    """Name the value `key` still resolves to after an unset of `target_path`.

    Trap: unset is target-file-scoped; a lower layer (registry.toml defaults, a
    concern file, an env override) can still answer `get`/`dump`, which reads as
    if the unset did not take."""
    try:
        rc, value = resolve_one(key)
    except Exception:  # noqa: BLE001 - advisory only
        return
    if rc == EXIT_OK and value is not None:
        print(
            f"machine-local: note: {key!r} still resolves to {value!r} from another "
            f"layer (not {target_path}); `get`/`dump` show that value. "
            "Use --global to unset it from registry.toml.",
            file=sys.stderr,
        )


#: Publisher-only namespace; a consumer box carries none of it.
_PUBLISHER_KEY_PREFIX = "publish."


def cmd_retire_publisher(args: argparse.Namespace) -> int:
    """Implement: machine-local retire-publisher [--global] [--dry-run] — remove
    every `publish.*` key from one registry file in one write."""
    reg_dir = _registry_dir()
    target_path = os.path.join(reg_dir, "registry.toml" if args.write_global else "registry.local.toml")
    if not os.path.exists(target_path):
        print(f"machine-local: retire-publisher: {target_path} does not exist; no publisher config to retire.")
        return EXIT_OK
    content = _read_text_shared(target_path)
    try:
        parsed = tomllib.loads(content)
    except tomllib.TOMLDecodeError as exc:
        print(f"machine-local: retire-publisher: refusing — {target_path} is malformed TOML: {exc}.", file=sys.stderr)
        return EXIT_OPERATIONAL
    keys = sorted(k for k in _flatten_nested(parsed) if k.startswith(_PUBLISHER_KEY_PREFIX))
    if not keys:
        print(f"machine-local: retire-publisher: no publish.* keys in {target_path}; nothing to retire.")
        return EXIT_OK
    removed: list[str] = []
    for key in keys:
        new_content, old_value = _remove_key(content, key)
        if old_value is None:
            new_content, old_value = _remove_string_array_key(content, key)
        if old_value is None:
            print(
                f"machine-local: retire-publisher: {key!r} is not surgically removable; "
                f"hand-edit {target_path}. Nothing written.",
                file=sys.stderr,
            )
            return EXIT_OPERATIONAL
        content = new_content
        removed.append(key)
    content = _drop_empty_publisher_headers(content)
    try:
        leftover = [k for k in _flatten_nested(tomllib.loads(content)) if k.startswith(_PUBLISHER_KEY_PREFIX)]
    except tomllib.TOMLDecodeError as exc:
        print(f"machine-local: retire-publisher: refusing to write — post-removal TOML is malformed: {exc}.", file=sys.stderr)
        return EXIT_OPERATIONAL
    if leftover:
        print(f"machine-local: retire-publisher: refusing to write — {leftover} still resolve after removal.", file=sys.stderr)
        return EXIT_OPERATIONAL
    if args.dry_run:
        for key in removed:
            print(f"[dry-run] would remove {key!r} from {target_path}")
        return EXIT_OK
    if _write_registry_file(target_path, content, False) != 0:
        return EXIT_OPERATIONAL
    for key in removed:
        print(f"machine-local: removed {key!r} from {target_path}")
    print(f"machine-local: retired publisher config ({len(removed)} key(s)).")
    return EXIT_OK


def _insert_mirror_path(content: str, mirror_key: str, path_value: str,
                        date_tag: str) -> str:
    if "'" in path_value:
        raise ValueError(
            f"_insert_mirror_path: path_value {path_value!r} contains a single quote; "
            "TOML literal strings (single-quoted) have no escape for single quote. "
            "Use a path without single quotes."
        )
    full_key = f"publish.mirrors.{mirror_key}.path"
    value_literal = f"'{path_value}'"
    locate = _locate_existing_definition(content, full_key)

    if locate is None:
        block = (
            f"\n[publish.mirrors.{mirror_key}]\n"
            f"path = {value_literal}  # migrate-publish-mirrors {date_tag}\n"
        )
        return content.rstrip("\n") + "\n" + block

    kind = locate["kind"]

    if kind == "flat":
        m = locate["match"]
        return content[:m.start()] + m.group(1) + value_literal + m.group(2) + content[m.end():]

    if kind == "table-leaf":
        abs_start = locate["abs_start"]
        abs_end = locate["abs_end"]
        leaf_m = locate["leaf_match"]
        return (
            content[:abs_start]
            + leaf_m.group(1) + value_literal + leaf_m.group(2)
            + content[abs_end:]
        )

    if kind == "table-header-only":
        section_start = locate["section_start"]
        section_end = locate["section_end"]
        leaf_path = locate["leaf_path"]
        section_body = content[section_start:section_end]
        indent_m = re.search(r"^([ \t]+)\S", section_body, re.MULTILINE)
        indent = indent_m.group(1) if indent_m else ""
        trimmed = section_body.rstrip("\n")
        suffix = section_body[len(trimmed):]
        new_section = (
            trimmed
            + f"\n{indent}{leaf_path} = {value_literal}  # migrate-publish-mirrors {date_tag}\n"
            + suffix
        )
        return content[:section_start] + new_section + content[section_end:]

    block = (
        f"\n[publish.mirrors.{mirror_key}]\n"
        f"path = {value_literal}  # migrate-publish-mirrors {date_tag}\n"
    )
    return content.rstrip("\n") + "\n" + block


_MIRROR_SOURCES = [
    ("repos.coordinator_claude",   "coordinator_claude",   False),
    ("repos.deep_research_claude", "deep_research_claude", False),
    ("repos.deep_research",        "deep_research_claude", True),
]

_ARRAY_TOKEN_REPLACEMENTS = [
    ("repo:coordinator_claude",   "publish-mirror:coordinator_claude"),
    ("repo:deep_research_claude", "publish-mirror:deep_research_claude"),
    ("repo:deep_research",        "publish-mirror:deep_research_claude"),
]


def cmd_migrate_publish_mirrors(args: argparse.Namespace) -> int:
    reg_dir = _registry_dir()
    local_path = os.path.join(reg_dir, "registry.local.toml")

    if not os.path.exists(local_path):
        print("machine-local migrate-publish-mirrors: registry.local.toml absent — nothing to migrate.")
        return EXIT_OK

    content = _read_text_shared(local_path)

    if not content.strip():
        print("machine-local migrate-publish-mirrors: registry.local.toml is empty — nothing to migrate.")
        return EXIT_OK

    date_tag = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    changed = False

    # Migration table: see module-level _MIRROR_SOURCES (hoisted F6).
    # Processed in order: canonical keys first so the legacy alias sees the target
    # already set and only removes the stale key (not overwriting the canonical value).
    for old_key, mirror_key, is_alias in _MIRROR_SOURCES:
        target_path_key = f"publish.mirrors.{mirror_key}.path"

        try:
            cur_parsed = tomllib.loads(content)
            cur_flat = _flatten_nested(cur_parsed)
        except tomllib.TOMLDecodeError as exc:
            print(
                f"machine-local: migrate-publish-mirrors: TOML parse error: {exc}",
                file=sys.stderr,
            )
            return EXIT_OPERATIONAL

        old_value = cur_flat.get(old_key)
        if old_value is None:
            continue

        if is_alias:
            print(
                f"machine-local: DEPRECATION: {old_key!r} is the legacy alias for "
                f"'repos.deep_research_claude'; migrating its value to {target_path_key!r}."
            )

        target_already = cur_flat.get(target_path_key)

        if target_already is not None:
            new_content, _ = _remove_key(content, old_key)
            if new_content != content:
                content = new_content
                changed = True
                print(
                    f"machine-local: removed stale {old_key!r} "
                    f"({target_path_key!r} already set)."
                )
            else:
                print(
                    f"machine-local: {old_key!r} present but could not be removed "
                    f"(shape not handled); edit registry.local.toml by hand.",
                    file=sys.stderr,
                )
        else:
            new_content, removed_val = _remove_key(content, old_key)
            if removed_val is not None:
                content = _insert_mirror_path(new_content, mirror_key, removed_val, date_tag)
                changed = True
                print(
                    f"machine-local: migrated {old_key!r} → "
                    f"{target_path_key!r} = {removed_val!r}"
                )
            else:
                print(
                    f"machine-local: {old_key!r} present but could not be removed "
                    f"(shape not handled); edit registry.local.toml by hand.",
                    file=sys.stderr,
                )

    # --- Rewrite repo:<mirror> → publish-mirror:<key> in publish.targets array ---
    # Machines that registered publish topology via the registry array keep stale
    # 'repo:coordinator_claude' / 'repo:deep_research_claude' rows after D3 removes
    # those keys from repos.*.  Rewrite them now so they resolve via publish.mirrors.*.
    # Token replacements defined at module-level as _ARRAY_TOKEN_REPLACEMENTS (hoisted F6).
    try:
        arr_parsed = tomllib.loads(content)
        current_array = _get_raw_list(arr_parsed, "publish.targets")
    except tomllib.TOMLDecodeError:
        current_array = None

    if isinstance(current_array, list):
        new_array = []
        rows_rewritten = 0
        for element in current_array:
            new_elem = str(element)
            for old_tok, new_tok in _ARRAY_TOKEN_REPLACEMENTS:
                if old_tok in new_elem:
                    new_elem = new_elem.replace(old_tok, new_tok)
            if new_elem != str(element):
                rows_rewritten += 1
            new_array.append(new_elem)

        if rows_rewritten > 0:
            array_span = _locate_existing_array_span(content, "publish.targets")
            provenance_comment: str | None = None
            if array_span is not None and array_span["kind"] == "flat-array":
                if array_span["comment_start"] is not None:
                    cstart = array_span["comment_start"]
                    cend = content.find("\n", cstart)
                    cend = cend if cend != -1 else len(content)
                    provenance_comment = content[cstart:cend]
                array_block = _build_array_content(
                    "publish.targets", new_array, date_tag, provenance_comment
                )
                replace_start = (
                    array_span["comment_start"]
                    if array_span["comment_start"] is not None
                    else array_span["span_start"]
                )
                replace_end = array_span["span_end"]
                content = content[:replace_start] + array_block + content[replace_end:]
                changed = True
                print(
                    f"machine-local: rewritten {rows_rewritten} publish.targets row(s): "
                    "repo:<mirror> → publish-mirror:<key>."
                )
            else:
                span_kind = array_span["kind"] if array_span is not None else "not found"
                print(
                    f"machine-local: WARNING: {rows_rewritten} publish.targets row(s) "
                    f"need repo:<mirror> → publish-mirror:<key> rewriting, but the array span "
                    f"could not be located or is not in the expected flat-array form "
                    f"(span kind: {span_kind!r}). "
                    "Edit registry.local.toml by hand to replace repo:<mirror> tokens.",
                    file=sys.stderr,
                )
                return EXIT_OPERATIONAL

    repo_root = os.path.dirname(os.path.abspath(reg_dir))
    legacy_sh = os.path.join(repo_root, "setup", "publish-targets.sh")
    if os.path.exists(legacy_sh):
        print(
            f"\nmachine-local: WARNING — legacy publish-targets.sh found:\n"
            f"  {legacy_sh}\n"
            "  This file is gitignored and per-machine; auto-edit is not safe.\n"
            "  Manual remediation required — open the file and replace:\n"
            "    'repo:coordinator_claude'   → 'publish-mirror:coordinator_claude'\n"
            "    'repo:deep_research_claude' → 'publish-mirror:deep_research_claude'\n"
            "    'repo:deep_research'        → 'publish-mirror:deep_research_claude'\n"
            "  Example:\n"
            "    Before: coordinator-claude|mirror|repo:coordinator_claude|...\n"
            "    After:  coordinator-claude|mirror|publish-mirror:coordinator_claude|..."
        )

    if not changed:
        print(
            "machine-local migrate-publish-mirrors: no changes needed "
            "(already migrated or no mirror keys present)."
        )
        return EXIT_OK

    try:
        tomllib.loads(content)
    except tomllib.TOMLDecodeError as exc:
        print(
            f"machine-local: migrate-publish-mirrors: refusing to write — "
            f"post-migration TOML is malformed: {exc}. "
            "This is a bug in migrate-publish-mirrors; edit registry.local.toml by hand.",
            file=sys.stderr,
        )
        return EXIT_OPERATIONAL

    rc = _write_registry_file(local_path, content, False)
    if rc != 0:
        return rc

    print(f"machine-local: migrate-publish-mirrors: updated {local_path}")
    print(
        "machine-local: Note: an empty [repos] header may remain in registry.local.toml "
        "after migration — this is harmless valid TOML; remove it manually if desired."
    )
    return EXIT_OK


_MUTATING_COMMANDS = frozenset({"set", "unset", "retire-publisher", "array-append", "array-set", "migrate-publish-mirrors", "relocate-store"})


@contextlib.contextmanager
def _registry_write_lock(timeout_s: float = 10.0) -> Generator[None, None, None]:
    """Serialize registry read-modify-write across processes.

    Trap: every mutating verb reads the whole file, edits, and os.replace()s it. Two sessions
    setting different keys at once each write a copy lacking the other's key, so one entry
    silently vanishes. An O_EXCL lock file is portable (no fcntl on Windows); a lock older than
    60 s is a crashed writer's and is broken. Residual race: two waiters breaking the same stale
    lock can remove each other's fresh lock; accepted because breaks follow a crash, not contention.
    """
    lock_path = os.path.join(_registry_dir(), ".registry-write.lock")
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            break
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(lock_path) > 60:
                    os.remove(lock_path)
                    continue
            except FileNotFoundError:
                continue
            except OSError:
                pass
            if time.monotonic() > deadline:
                raise SystemExit(f"machine-local: registry is locked by another writer ({lock_path}); retry")
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            os.remove(lock_path)
        except OSError:
            pass


def main() -> int:
    # Windows: Python text-mode stdout translates '\n' -> '\r\n', so a captured
    # `$(machine-local get repos.x)` carries a trailing '\r'. That stray CR
    # silently breaks downstream string/path comparisons — notably claude-author's
    # regen grep-gate (friction F6: the CR made `grep -qF "$DOE_COORDINATOR/hooks"`
    # never match settings.json, forcing a full hook-block regen + "clobbered"
    # noise on every launch). Emit LF-only output on every platform. Guarded for
    # stream objects that don't expose reconfigure (non-TextIOWrapper).
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(newline="\n", encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(
        prog="machine-local",
        description="Read per-machine config from <settings-home>/machine-local/",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    get_p = subparsers.add_parser("get", help="Print value for a key")
    get_p.add_argument("key", help="Dotted key name (e.g. repos.claude_unreal_holodeck)")
    get_p.add_argument("--default", metavar="VALUE", default=None,
                       help="Value to print if key is missing (always exits 0)")

    req_p = subparsers.add_parser(
        "require", help="Print value for a key; exit 3 (typed refusal) if not set")
    req_p.add_argument("key", help="Dotted key name (e.g. paths.cache_root)")

    has_p = subparsers.add_parser("has", help="Exit 0 if key is set, 1 if not set, 2 on operational failure (see machine-local-registry.md §4.1)")
    has_p.add_argument("key", help="Dotted key name")

    ew_p = subparsers.add_parser(
        "external-workspace",
        help=(
            "Is <name-or-path> a registered external workspace (external_workspaces.*)? "
            "Prints key<TAB>path<TAB>kind<TAB>vcs; exit 0 registered, 1 not, 2 operational failure"
        ),
    )
    ew_p.add_argument("target", nargs="?", default=None, help="Registered key, or a path equal to or under a registered root")
    ew_p.add_argument("--list", action="store_true", help="Print every registered entry")

    store_p = subparsers.add_parser(
        "store",
        help=(
            "Resolve a declared data store (stores.*) by name or by a path inside it. "
            "Prints name<TAB>path<TAB>owner<TAB>purpose; exit 0 found, 1 not, 2 operational failure"
        ),
    )
    store_p.add_argument("target", nargs="?", default=None, help="Store name, or a path equal to or under a store root")
    store_mode = store_p.add_mutually_exclusive_group()
    store_mode.add_argument("--list", action="store_true", help="Print every declared store")
    store_mode.add_argument(
        "--check", action="store_true",
        help="Existence probe: one missing/orphan/incomplete/dead-dependent/reparse line per finding; exit 1 when any",
    )

    loc_p = subparsers.add_parser(
        "locate",
        help=(
            "Resolve a cross-box storage root by name from the tracked record (docs/fleet/storage-roots.toml). "
            "Prints name<TAB>box<TAB>path<TAB>reachable; exit 0 found, 1 unknown, 2 record missing or operational failure"
        ),
    )
    loc_p.add_argument("target", nargs="?", default=None, help="Root name")
    loc_p.add_argument("--list", action="store_true", help="Print every root in the record")

    rs_p = subparsers.add_parser(
        "relocate-store",
        help=(
            "Point a declared store (stores.*) at its new location after the data was moved. "
            "Prints stale-dependent<TAB>name<TAB>file for each declared dependent still "
            "spelling the old path; never moves data or writes a dependent. Exit 0 done, 2 refused"
        ),
    )
    rs_p.add_argument("name", help="Declared store name")
    rs_p.add_argument("new_path", help="The store's new location")
    rs_p.add_argument("--dry-run", action="store_true", help="Print what would be written without making changes")
    rs_p.add_argument("--allow-missing", action="store_true", help="Accept a new path that does not exist yet")

    keys_p = subparsers.add_parser("keys", help="List all known keys, one per line")
    keys_p.add_argument(
        "--prefix", metavar="PREFIX", default=None,
        help="Only list keys equal to, or nested under (dotted), PREFIX (e.g. repos)",
    )
    keys_p.add_argument(
        "--set-only", action="store_true", dest="set_only",
        help="Only list keys holding a non-empty value (omit declared-but-unset keys)",
    )

    dump_p = subparsers.add_parser(
        "dump",
        help=(
            "Resolve EVERY key in ONE process and print a JSON object of key → value. "
            "The batch read: use instead of `keys` followed by one `get` per key, which "
            "costs 1+N processes for one file read."
        ),
    )
    dump_p.add_argument(
        "--prefix", metavar="PREFIX", default=None,
        help=(
            "Only dump keys equal to, or nested under (dotted), PREFIX (e.g. repos). "
            "Narrows the OUTPUT, not the process: each dump is a fresh interpreter "
            "start, which dominates the cost. Wanting several namespaces? Take ONE "
            "unprefixed dump and filter it in-process -- N prefixed dumps is the "
            "`keys`+`get` mistake one level up."
        ),
    )
    dump_p.add_argument(
        "--include-unset", action="store_true",
        help=(
            "Also emit declared-but-unresolvable keys, as JSON null. Keeps "
            "DECLARED-but-unset distinguishable from UNREGISTERED without a second "
            "`keys` process. Incompatible with --format sh (exit 2)."
        ),
    )
    dump_p.add_argument(
        "--show-origin", action="store_true",
        help=(
            "Emit each key as {\"value\": ..., \"layer\": ...} naming the layer that "
            "answered it (registry.local.toml, registry.toml (defaults), concern, env, "
            "repos-ladder) -- shows when an unset key re-surfaces from defaults. "
            "Incompatible with --format sh (exit 2)."
        ),
    )
    dump_p.add_argument(
        "--format", choices=["json", "sh"], default="json",
        help=(
            "Output format. 'json' (default): a JSON object of key -> value, "
            "unchanged contract. 'sh': one guarded `export VAR=...` line per "
            "resolved repos.<slug> key, for `eval` by claude-machine-local.sh."
        ),
    )

    subparsers.add_parser(
        "check",
        help="Report registry keys shadowed by a concern file (read-only; exit 1 if any)",
    )

    subparsers.add_parser("path", help="Print absolute path to active registry.toml")

    subparsers.add_parser(
        "dir",
        help=(
            "Print absolute path to the machine-local directory "
            "(<settings-home>/machine-local). Sanctioned dir-resolution primitive "
            "for concern-file readers — use instead of hardcoding ~/.claude/machine-local."
        ),
    )

    set_p = subparsers.add_parser(
        "set",
        help="Write a key=value pair to the registry (prefer over hand-editing)",
    )
    set_p.add_argument("key", help="Dotted key (e.g. repos.project_rag)")
    set_p.add_argument("value", help="String value to set")
    set_p.add_argument(
        "--concern",
        metavar="NAME",
        default=None,
        help="Write the namespaced key into the <NAME>.local.toml concern file "
             "(e.g. --concern unreal unreal.samples_root /path) instead of the "
             "registry — the path the bare registry writer refuses by namespace.",
    )
    set_p.add_argument(
        "--global",
        dest="write_global",
        action="store_true",
        help="Write to registry.toml (tracked/shared) instead of registry.local.toml (gitignored/per-machine)",
    )
    set_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be written without making changes",
    )

    unset_p = subparsers.add_parser(
        "unset",
        help="Remove a key from ONE target file (registry.local.toml by default, "
             "registry.toml with --global). Exit 0 = removed, 1 = already absent "
             "(clean no-op), 2 = operational failure. Target-file-scoped, not "
             "resolution-stack-scoped — see machine-local-registry.md.",
    )
    unset_p.add_argument("key", help="Dotted key to remove")
    unset_p.add_argument(
        "--global",
        dest="write_global",
        action="store_true",
        help="Remove from registry.toml (tracked/shared) instead of registry.local.toml (gitignored/per-machine)",
    )
    unset_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be removed without making changes",
    )
    unset_p.add_argument(
        "--concern",
        metavar="NAME",
        default=None,
        help="Remove the key from <NAME>.local.toml (and its provenance row). Without "
             "it, a key held in its concern's .local.toml is still found and removed.",
    )

    rp_p = subparsers.add_parser(
        "retire-publisher",
        help="Remove every publish.* key from ONE target file in one write — for a box "
             "that is no longer a publisher.",
    )
    rp_p.add_argument("--global", dest="write_global", action="store_true",
                      help="Retire from registry.toml instead of registry.local.toml")
    rp_p.add_argument("--dry-run", action="store_true", help="Print what would be removed")

    aa_p = subparsers.add_parser(
        "array-append",
        help="Append an element to a TOML array key (idempotent; current sole consumer: publish.targets)",
    )
    aa_p.add_argument("key", help="Dotted key for the array (e.g. publish.targets)")
    aa_p.add_argument("element", help="String element to append")
    aa_p.add_argument(
        "--global",
        dest="write_global",
        action="store_true",
        help="Write to registry.toml (tracked/shared) instead of registry.local.toml",
    )
    aa_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be written without making changes",
    )

    as_p = subparsers.add_parser(
        "array-set",
        help="Replace a TOML array key with the given elements (order-preserving dedup; current sole consumer: publish.targets)",
    )
    as_p.add_argument("key", help="Dotted key for the array (e.g. publish.targets)")
    as_p.add_argument("elements", nargs="+", help="String elements to set (replaces current array)")
    as_p.add_argument(
        "--global",
        dest="write_global",
        action="store_true",
        help="Write to registry.toml (tracked/shared) instead of registry.local.toml",
    )
    as_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be written without making changes",
    )

    subparsers.add_parser(
        "migrate-publish-mirrors",
        help=(
            "Idempotently migrate repos.coordinator_claude / repos.deep_research_claude "
            "(and legacy repos.deep_research alias) from registry.local.toml into the "
            "publish.mirrors.* namespace. Also rewrites repo:<mirror> → publish-mirror:<key> "
            "in any publish.targets registry array rows. Re-running is a no-op."
        ),
    )

    parsed = parser.parse_args()

    dispatch = {
        "get": cmd_get,
        "require": cmd_require,
        "has": cmd_has,
        "keys": cmd_keys,
        "external-workspace": cmd_external_workspace,
        "store": cmd_store,
        "locate": cmd_locate,
        "relocate-store": cmd_relocate_store,
        "dump": cmd_dump,
        "check": cmd_check,
        "path": cmd_path,
        "dir": cmd_dir,
        "set": cmd_set,
        "unset": cmd_unset,
        "retire-publisher": cmd_retire_publisher,
        "array-append": cmd_array_append,
        "array-set": cmd_array_set,
        "migrate-publish-mirrors": cmd_migrate_publish_mirrors,
    }
    global _toml_memo
    try:
        if parsed.command in _MUTATING_COMMANDS:
            with _registry_write_lock():
                return dispatch[parsed.command](parsed)
        return dispatch[parsed.command](parsed)
    finally:
        _toml_memo = None


_DEPTH_ENV = "MACHINE_LOCAL_DEPTH"
# Load per CPU above which a read refuses rather than adds a process to the pile.
_LOAD_PER_CPU_LIMIT = 8.0

# Box-wide in-flight cap. Each invocation holds an OS lock on one of N slot files for its
# whole life; when every slot is held it exits at once. The OS drops the lock when the
# process exits or is killed, so an orphan holds a slot only while it is actually alive and
# a crash never leaks one.
_SLOT_DIR_ENV = "MACHINE_LOCAL_SLOT_DIR"
_MAX_INFLIGHT_ENV = "MACHINE_LOCAL_MAX_INFLIGHT"
_DEFAULT_MAX_INFLIGHT = 16
_held_slot: int | None = None  # kept open until exit: closing it would release the slot


def _slot_dir() -> str:
    override = os.environ.get(_SLOT_DIR_ENV)
    if override:
        return override
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
    else:
        base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base or os.path.expanduser("~"), "coordinator", "machine-local-slots")


def _max_inflight() -> int:
    try:
        return max(1, int(os.environ.get(_MAX_INFLIGHT_ENV, _DEFAULT_MAX_INFLIGHT)))
    except ValueError:
        return _DEFAULT_MAX_INFLIGHT


def _try_lock(fd: int) -> bool:
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _claim_inflight_slot() -> bool:
    """Hold one slot for this process's life; False only when every slot is held by another.

    Fails open: a slot directory that cannot be created or opened must cost the cap, never
    the read.
    """
    global _held_slot
    n = _max_inflight()
    d = _slot_dir()
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        return True
    contended = False
    start = os.getpid() % n
    for i in range(n):
        try:
            fd = os.open(os.path.join(d, f"slot-{(start + i) % n}.lock"), os.O_RDWR | os.O_CREAT, 0o600)
        except OSError:
            continue
        if _try_lock(fd):
            _held_slot = fd
            return True
        os.close(fd)
        contended = True
    return not contended


def _spawn_storm_breaker() -> int | None:
    """Refuse a nested or overloaded invocation; return an exit code, or None to proceed.

    Trap: nothing this CLI does legitimately re-enters it, yet a descendant (a git
    hook, a BASH_ENV-sourced profile calling `machine-local get`) can, and each
    level fans out again: one such loop put 842 processes, 10+ deep, on a box in
    3 s. The depth var is inherited by every child we spawn, so any descendant
    that calls back in sees it and stops. Many unrelated top-level callers never
    nest, so the slot cap bounds them.
    """
    depth = os.environ.get(_DEPTH_ENV, "0")
    if depth != "0":
        print(f"machine-local: refused nested invocation ({_DEPTH_ENV}={depth}); "
              f"a descendant of a machine-local call re-entered it. Find the caller "
              f"from the parent process chain.", file=sys.stderr)
        return EXIT_OPERATIONAL
    os.environ[_DEPTH_ENV] = "1"
    if not _claim_inflight_slot():
        print(f"machine-local: refused, {_max_inflight()} invocations already in flight "
              f"box-wide (slots under {_slot_dir()}); retry once they drain.", file=sys.stderr)
        return EXIT_OPERATIONAL
    try:
        load1 = os.getloadavg()[0]  # absent on Windows; the slot cap above is the Windows bound
    except (AttributeError, OSError):
        return None
    limit = _LOAD_PER_CPU_LIMIT * (os.cpu_count() or 1)
    if load1 > limit:
        print(f"machine-local: refused under load {load1:.0f} (limit {limit:.0f}); "
              f"the box is saturated, retry once it drains.", file=sys.stderr)
        return EXIT_OPERATIONAL
    return None


if __name__ == "__main__":
    _refused = _spawn_storm_breaker()
    if _refused is not None:
        sys.exit(_refused)
    _env = os.environ.get("MACHINE_LOCAL_DEADLINE_S")
    try:
        _secs = float(_env) if _env else _BACKSTOP_S
    except ValueError:
        _secs = _BACKSTOP_S
    _scan_budget_s = _SCAN_BUDGET_S
    _arm_deadline(_secs if sys.argv[1:2] and sys.argv[1] in {"get", "require", "has", "path", "dir", "dump", "keys"} else 0.0)
    sys.exit(main())
