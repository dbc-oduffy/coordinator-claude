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
The write commands (set / array-*) have no "absent" concept; they keep the
simpler 0 = success / non-zero = refused-or-failed convention.

Negative-spec: env does NOT outrank registry layers (the Director of Engineering F1 inversion).
Negative-spec: missing .local files are not errors — treated as empty.
Negative-spec: no regex fallback, no PyYAML, no tomli — stdlib tomllib only.
Negative-spec: reader is read-only for GET path; bare SET writes only registry.local.toml
              (or registry.toml with --global) and never touches concern files — UNLESS
              --concern <name> is passed, the explicit concern-file write path
              (cmd_set_concern: per-key [provenance.<key>], type-AND-table-preserving
              read-merge-write into <name>.local.toml). The registry path and the concern
              path are disjoint: bare set still refuses concern-namespace keys.

All consumers — including the ergonomic wrapper ``claude_machine_local.py`` —
shell out to the ``machine-local`` CLI. Direct in-process import is the
dual-identity anti-pattern (docs/wiki/dual-identity-module-hazard.md and
docs/wiki/machine-local-registry.md §8(a)); shell-out is the only contract.
"""

import sys
import os
import json
import argparse
import re
import subprocess
import datetime
import difflib
from pathlib import Path

# Read-path exit-code contract (see module docstring). Operational failure MUST be
# distinguishable from a cleanly-absent key so a consumer swallowing non-zero does
# not mask a broken reader as "key not found" (2026-06-24 daemon read-path bug).
EXIT_OK = 0
EXIT_NOT_FOUND = 1      # get: key not found | has: key not set — a clean negative
EXIT_OPERATIONAL = 2    # reader could not answer: version guard, malformed TOML

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

import tomllib  # stdlib, 3.11+

# A console-subsystem child with no console of its own allocates a fresh
# conhost on Windows -- with a visible window. Every git spawn below is
# short-lived and output-captured, so without this each one flashes.
# 0 on POSIX, where the flag does not exist.
_NO_CONSOLE = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}

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
    """Raised when marker-autodiscovery finds ≥2 distinct directories for the same slug.

    The operator must set REPO_<SLUG> (rung 1 env override) to resolve the ambiguity.
    Spec backlink: docs/plans/2026-06-30-cross-machine-path-resolution-ladder.md §C1
    """


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
             COORDINATOR_SETTINGS_HOME > ${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings

    Spec backlink: docs/plans/2026-07-06-durable-substrate-to-settings-home.md § C2a
                   project-rag/docs/wiki/cross-machine-path-resolution-contract.md
                   § The 4-Rung Resolution Ladder
    """
    override = os.environ.get("MACHINE_LOCAL_REGISTRY_DIR")
    if override:
        return override
    return os.path.join(_settings_home(), "machine-local")


def _load_toml(path: str) -> dict:
    """Load a TOML file and return its contents as a dict.

    Errors loudly on malformed TOML — no silent degradation.
    Returns empty dict when file is absent (missing .local files are fine).

    Fatal-on-malformed is deliberate here and stays the DEFAULT for every
    existing caller (registry.toml/registry.local.toml, search-roots.toml,
    path-exceptions.toml, and the pre-write reads in the set/array-* writers):
    those files are either the root namespace itself or feed a write path that
    must fail loud. Concern-file reads during layer-building are the one
    exception — see _load_toml_isolated.
    """
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        print(
            f"machine-local: malformed TOML in {path}: {exc}\n"
            "Remediation: fix the TOML syntax in the file above.",
            file=sys.stderr,
        )
        # Operational failure, not absence: the reader could not parse its input.
        sys.exit(EXIT_OPERATIONAL)


def _load_toml_isolated(path: str) -> dict | None:
    """Load a TOML file for the per-concern-file read-isolation seam.

    Fail-soft counterpart to _load_toml, scoped ONLY to concern-file reads in
    _build_resolution_layers. Returns {} when the file is absent (same as
    _load_toml), the parsed dict on success, or None on a TOMLDecodeError —
    None is the drop-this-layer sentinel, distinct from {} (absent/empty),
    so the caller can tell "nothing here" from "something here I couldn't read".

    On parse failure, warns to stderr naming the file, the parse error, and
    the remediation, then returns None instead of exiting — one malformed
    concern file must not take down every other concern's keys or the
    registry layers (blast-radius defect, cross-repo memo
    cross-repo/inbox/2026-08-03-project-rag-ue-addon-em-machine-local-rulings-still-outstanding.md,
    doctrine-plane ruling (a): "fail soft on read, loud on write").

    Registry files (registry.toml / registry.local.toml) deliberately do NOT
    route through this function — they stay on the fatal _load_toml path.
    There is nothing to isolate them from: they ARE the root namespace, and
    degrading them would silently produce a reader that answers with a
    partial registry. That asymmetry is intentional, not an oversight.
    """
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
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
    """Scan a candidate directory for its .coordinator-dev-repo identity marker.

    The dev-repo shape (the doctrine-repo authoring clone: no marketplace manifest,
    identified instead by a repo-root `.coordinator-dev-repo` sentinel) — see that
    file's own header for why its location is load-bearing.

    Reads <candidate_dir>/.coordinator-dev-repo line by line, looking for a
    non-comment `slug: <value>` line, and returns value.replace("-", "_") as the
    registry slug — matching the marketplace-name convention above.

    Returns None if the file is absent, unreadable, or carries no `slug:` key
    (a keyless sentinel is a valid dev-repo marker for every OTHER reader, which
    are presence-only; this leg alone needs the key, and its absence must not
    crash or guess — it is simply not a rung-2 hit).
    """
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
    """Scan a candidate directory for its installation-shape identity marker.

    Two first-class, mutually-exclusive marker shapes, each resolved by its own
    helper:
      - marketplace shape — _scan_marketplace_marker: .claude-plugin/marketplace.json,
        at either the repo-root or one-level-nested placement (unchanged behaviour
        and precedence from before this function split in two).
      - dev-repo shape — _scan_dev_repo_marker: the repo-root .coordinator-dev-repo
        sentinel's `slug:` line. This is the doctrine-repo authoring clone's shape —
        it carries no marketplace manifest at all.

    A candidate carrying BOTH marker kinds is an identity contradiction, not a
    precedence question: this returns None, the same way an unreadable or
    slug-less marker of either single kind resolves to None — never a silent
    pick of one shape over the other.

    Returns None if neither shape resolves, or both do.

    Negative-spec: does NOT infer a slug from the directory basename in either
    shape — a locally-renamed clone must resolve to nothing, not a
    wrong-but-plausible guess. Does NOT prefer one shape when both are present;
    "return None on both-present" is itself the contract, not a fallback.

    This is the stable, documented entrypoint for callers that only need the
    single collapsed slug (or None) and have no use for a both-present
    contradiction beyond "not a match". `_autodiscover_repo` is NOT such a
    caller — a both-present candidate is exactly the case it must hold and
    surface at the resolution boundary (AC4), which needs the raw
    marketplace/dev-repo pair this function's `str | None` contract collapses
    away. It therefore calls `_scan_marketplace_marker`/`_scan_dev_repo_marker`
    directly instead of this function — see its docstring.

    Spec backlink: project-rag/docs/wiki/cross-machine-path-resolution-contract.md
                   § The 4-Rung Resolution Ladder
    Spec backlink: docs/plans/2026-08-03-doe-claude-as-a-first-class-installation.md § C2
    """
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
    Spec backlink: docs/plans/2026-08-03-doe-claude-as-a-first-class-installation.md § C2
    """
    roots_by_platform = _load_search_roots(reg_dir)
    platform_roots = roots_by_platform.get(sys.platform, [])
    # Review: code-reviewer (F2) — bare-string value (e.g. darwin = "~/X") would iterate
    # over characters, yielding 0 candidates with no error. Fail loud to match the
    # fail-loud-on-malformed contract — same style as _load_toml's TOML error handling.
    if not isinstance(platform_roots, list):
        print(
            f"machine-local: search-roots.toml: platform key '{sys.platform}' must be a list "
            f"of paths, not a bare string. Got: {platform_roots!r}\n"
            "Remediation: wrap the value in brackets, e.g. darwin = [\"~/X\"].",
            file=sys.stderr,
        )
        sys.exit(EXIT_OPERATIONAL)

    candidates: list[str] = []
    # Held, not raised — a both-present candidate relevant to this slug (see
    # docstring). (path, marketplace_slug, dev_repo_slug) triples.
    contradictions: list[tuple[str, str, str]] = []
    for root in platform_roots:
        expanded_root = os.path.expanduser(str(root))
        if not os.path.isdir(expanded_root):
            continue
        try:
            child_names = os.listdir(expanded_root)
        except OSError:
            continue
        for child in sorted(child_names):  # sorted for determinism
            child_path = os.path.join(expanded_root, child)
            if not os.path.isdir(child_path):
                continue
            marketplace_slug = _scan_marketplace_marker(child_path)
            dev_repo_slug = _scan_dev_repo_marker(child_path)
            if marketplace_slug is not None and dev_repo_slug is not None:
                if slug in (marketplace_slug, dev_repo_slug):
                    # realpath, not the raw child_path: `expanded_root` may carry
                    # forward slashes (search-roots.toml is written POSIX-
                    # normalized, see search_roots.py) while `child` is appended
                    # via os.path.join's native separator, so the raw join mixes
                    # '/' and '\' on Windows -- neither the operator's own path
                    # string nor os.path.realpath(their_path) then substring-
                    # matches it in the composed error message below.
                    # os.path.realpath resolves to one native, unambiguous form.
                    contradictions.append((os.path.realpath(child_path), marketplace_slug, dev_repo_slug))
                continue
            found_slug = marketplace_slug if marketplace_slug is not None else dev_repo_slug
            if found_slug == slug:
                candidates.append(child_path)

    # Deduplicate by realpath so symlinks to the same directory don't count as distinct.
    distinct: list[str] = []
    seen_real: set[str] = set()
    for c in candidates:
        # Review: code-reviewer (F3) — try/except OSError removed; realpath(strict=False)
        # (the default) never raises OSError, making the except branch dead code.
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
    """Resolve <cand>'s git common-dir to an absolute realpath, or None if <cand>
    is not inside a git repository (or git is unavailable / errors / times out).

    The common-dir is shared by a primary working tree and all of its linked
    worktrees (`git worktree add`), making it the correct grouping key for
    worktree-collapse: `git rev-parse --git-common-dir` returns a path
    (relative to <cand> or absolute, depending on whether the common-dir lives
    inside or outside <cand>) that resolves to the primary tree's .git
    directory.
    # Review: code-reviewer (F4) — reworded to state both cases git can emit
    # (relative-inside vs absolute-outside), not relative-only.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", cand, "rev-parse", "--git-common-dir"],
            capture_output=True,
            text=True,
            timeout=5,
            **_NO_CONSOLE,
        )
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
    """Collapse realpath-distinct candidates that are actually the SAME underlying
    git repository (a primary working tree plus one or more linked worktrees) into
    ONE representative — the primary working tree.

    A linked worktree's marker-bearing directory shares its parent repo's
    marketplace.json (same slug), so without this step it counts as a second,
    spuriously-distinct candidate and triggers a false AmbiguousRepoMatch.

    Non-git candidates (git missing, rev-parse fails/errors/times out) are never
    collapsed — each such candidate forms its own singleton group, preserving
    genuinely-distinct standalone marker directories as distinct candidates.
    Genuinely-distinct git repos (different common-dirs) are likewise preserved
    as distinct — only candidates sharing a common-dir collapse.

    Spec backlink: project-rag/docs/wiki/cross-machine-path-resolution-contract.md
                   § The 4-Rung Resolution Ladder
    Negative-spec: a linked worktree living inside a search-root previously caused
    AmbiguousRepoMatch for its parent repo's slug (e.g. Claude-klabauter-baseline-afc9f129,
    a linked worktree of claude-klabauter, both carrying name: "claude-klabauter"
    under ~/X) — this function is the fix for that incident.
    """
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
            # No primary found under the search-root (main tree lives elsewhere),
            # or an unexpected >1 primaries — fall back to deterministic first.
            # Review: code-reviewer (F5) — >1 primaries sharing one common-dir key
            # is structurally unexpected (should be unreachable in normal git
            # usage) and worth a debuggability note; 0-primaries is the mundane
            # case and stays silent.
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
    """Convert an MSYS/Cygwin mount-form path ('/x/...' or '/cygdrive/x/...') to
    native Windows drive form (drive letter, colon, forward slash, then the
    rest) so native-Windows consumers (node, py.exe, claude.exe, Path.exists)
    resolve it. No-op on POSIX (os.name != 'nt') and on paths already in that
    native drive form (forward- or back-slashed).

    This is the MSYS-mount-form companion to the as_posix() backslash-drive fix
    below: as_posix() repairs a backslashed native drive path to the
    forward-slashed form but does NOT touch '/x/...', which a native-Windows
    process resolves as drive-relative (doubled drive, drive-letter directory
    repeated) — the .doe-root / repos.doe_claude mis-resolution bug. Mirrors
    the bash `cygpath -m` normalization on the write side
    (gen-doe-root-pointer.py, install-maximalist.py).
    """
    if os.name != "nt":
        return s
    m = re.match(r"^/(?:cygdrive/)?([A-Za-z])(/.*)?$", s)
    if m:
        return m.group(1).upper() + ":" + (m.group(2) or "/")
    return s


class SiblingRepoNotFoundError(Exception):
    """Raised when resolve_sibling_repo_required cannot locate a sibling repo.

    The error message includes a standardized remediation string (verbatim from
    the contract) naming machine-local set as the last-resort fallback action.

    This exact name is pinned by the cross-machine path-resolution contract;
    conformers catching this error must import or mirror it by this name.

    Spec backlink: project-rag/docs/wiki/cross-machine-path-resolution-contract.md
                   § Fail-Loud Seam — Two-Function Contract
    """


def resolve_sibling_repo(name: str) -> "Path | None":
    """Walk the 4-rung cross-machine resolution ladder; return first resolved path or None.

    Optional variant — never raises on *absence*; AmbiguousRepoMatch propagates
    through (it is a misconfig, not absence) but only AFTER the whole ladder has been
    walked. A rung-1 set-but-nonexistent env var also propagates (EnvironmentError)
    because it is a misconfig, not absence.

    Rung order:
      1. REPO_<SLUG> env var — if set AND path exists, return it.
             If set AND path does NOT exist → EnvironmentError (misconfig).
      2. Autodiscovery — _autodiscover_repo. An ambiguous scan is held, not raised:
             rungs 3 and 4 still get their turn, and the exception surfaces only if
             neither resolves. An explicit operator declaration must stay reachable
             past an ambiguous guess.
      3. path-exceptions.toml OS-keyed table — expanduser; existence-checked.
      4. registry.local.toml direct read — empty-string → None (not a hit).

    Review: code-reviewer — this ordering guarantee (rungs 3/4 outrank a deferred
    rung-2 ambiguity) is exercised at the CLI-contract level, not by a direct call
    to this function: see test_machine_local.py's
    TestAmbiguousScanDoesNotOutrankExplicitDeclaration, and that file's own
    negative-spec for why its tests shell out to the CLI instead of importing this
    module directly.

    Slug = name (underscored form); SLUG = name.upper() (env var prefix).

    Negative-spec: does NOT fall through to the generic _resolve_key /
    _build_resolution_layers stack; that stack's lowest layer (registry.toml)
    carries `repos.x = ""` sentinel placeholders that _resolve_key would return
    as hits, silently defeating fail-loud. Rung 4 reads only registry.local.toml
    directly and treats empty-string as not-found.

    Spec backlink: project-rag/docs/wiki/cross-machine-path-resolution-contract.md
                   § Fail-Loud Seam — Two-Function Contract
    """
    slug = name
    env_var = f"REPO_{slug.upper()}"
    reg_dir = _registry_dir()

    # Rung 1 — explicit env override
    env_val = os.environ.get(env_var)
    if env_val is not None:
        p = Path(env_val)
        if p.exists():
            return p
        # Set but absent: this is a misconfig (not a clean absence) — hard error.
        # Review: code-reviewer (F1) — prefix stripped here; cmd_get catch site (~:587)
        # already prepends "machine-local: ", so keeping it here would double-prefix.
        raise EnvironmentError(
            f"{env_var} is set to {env_val!r} but that path does not exist. "
            f"Fix or unset {env_var} to allow autodiscovery to proceed."
        )

    # Rung 2 — search-roots autodiscovery. An ambiguous scan is a rung-2 NON-RESULT,
    # not a ladder-terminating error: the contract says stop at the first rung that
    # produces a result, and two candidates produce none. Hold the exception and keep
    # walking so an explicit operator declaration at rung 3/4 stays reachable; re-raise
    # only if nothing further resolves. Letting it propagate here made a correct,
    # unambiguous registry.local.toml pin unreachable whenever any stray copy of the
    # repo appeared under a search root.
    deferred_ambiguity: AmbiguousRepoMatch | None = None
    try:
        discovered = _autodiscover_repo(slug, reg_dir)
    except AmbiguousRepoMatch as exc:
        deferred_ambiguity = exc
        discovered = None
    if discovered is not None:
        return Path(discovered)

    # Rung 3 — path-exceptions.toml OS-keyed table
    exceptions = _load_path_exceptions(reg_dir)
    platform_exc = exceptions.get(sys.platform, {})
    if isinstance(platform_exc, dict):
        exc_path_str = platform_exc.get(slug)
        if exc_path_str is not None:
            exc_path = Path(os.path.expanduser(str(exc_path_str)))
            if exc_path.exists():
                return exc_path

    # Rung 4 — registry.local.toml direct read; empty-string → not a hit
    reg_local_path = os.path.join(reg_dir, "registry.local.toml")
    reg_local_data = _load_toml(reg_local_path)
    if reg_local_data:
        flat = _flatten_nested(reg_local_data)
        key = f"repos.{slug}"
        val = flat.get(key)
        # Empty-string is a sentinel placeholder (registry.toml carries repos.x = "")
        # and MUST NOT be treated as a resolved path — return None so the caller
        # can degrade gracefully or raise SiblingRepoNotFoundError.
        if val is not None and str(val) != "":
            return Path(str(val))

    # Nothing was declared anywhere — now the rung-2 ambiguity is the real answer.
    if deferred_ambiguity is not None:
        raise deferred_ambiguity

    return None


def resolve_sibling_repo_required(name: str) -> "Path":
    """Walk the 4-rung resolution ladder; raise SiblingRepoNotFoundError if no rung resolves.

    Required variant — the fail-loud counterpart to resolve_sibling_repo. Callers
    that need a missing sibling to be a hard error MUST use this function, not test
    the optional variant for None and raise themselves (which would bypass the
    standardized remediation string that operators depend on).

    AmbiguousRepoMatch propagates from the inner call — it is a misconfig, not absence.

    Spec backlink: project-rag/docs/wiki/cross-machine-path-resolution-contract.md
                   § Fail-Loud Seam — Two-Function Contract
    """
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
    """Emit a warning if schema version doesn't match expected."""
    schema_val = data.get("schema")
    if schema_val is not None and schema_val != SCHEMA_EXPECTED:
        print(
            f"machine-local: warning: {path} declares schema={schema_val}, "
            f"reader expects schema={SCHEMA_EXPECTED}. "
            "Some keys may not be read correctly.",
            file=sys.stderr,
        )


def _flatten_nested(data: dict, _prefix: str = "") -> dict:
    """Recursively flatten nested dicts in a registry file into dotted keys.

    Companion to _flatten_concern, but for registry.toml / registry.local.toml
    where there is no concern-name prefix (the file is the root namespace).
    This makes natural TOML table syntax (``[unreal]\\ninstall_root = "..."``)
    or dotted-key syntax (``unreal.install_root = "..."``) visible to
    ``machine-local get`` for keys whose namespace is NOT promoted to a
    concern file. Belt-and-suspenders: keeps the registry reader robust to
    hand-edits and to namespaces not yet (or no longer) promoted to concerns.

    Supported namespaces resolved via this path (non-exhaustive):
      - ``repos.*``                  — working repo sibling-discovery paths
      - ``publish.mirrors.<k>.path`` — publish-target mirror destinations
      - ``publish.mirrors.<k>.owner``— mirror owning EM id
      - ``publish.targets``          — per-machine publish topology array
    Spec backlink: docs/plans/2026-06-30-registry-publish-vs-working-targets.md § D1
    """
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
    """Prefix all keys in a concern file with '<concern_name>.<prefix>'.

    Recursively flattens nested dicts into dotted subkeys so every nested
    table (not just 'versions') is reachable.  Native types are stored as-is
    so _resolve_key's isinstance(val, list) branch handles list→newline
    uniformly at resolve time rather than at flatten time.

    Self-named top-level table elision: when the concern file uses
    ``[<concern_name>]`` as the top-level table (e.g. ``[unreal]`` inside
    ``unreal.local.toml``), the matching prefix is NOT doubled. The contents
    of that table are merged into the concern's flat namespace. This lets
    operators write the natural TOML form (``[unreal]\\ninstall_root = "..."``)
    and have it resolve as ``unreal.install_root`` instead of
    ``unreal.unreal.install_root``. Top-level keys placed directly (without
    the self-named table) still work — they are auto-prefixed by concern_name.

    Recursive flatten ensures arbitrary nesting is reachable. Native types (not
    str()) preserved so list→newline join at resolve time handles arrays uniformly.
    """
    result = {}
    # Strip sentinel prefix ("\x00") before using in key construction.
    # The sentinel is used only to disable self-named-table elision on
    # recursive calls — it must not appear in the output key strings.
    effective_prefix = _prefix if _prefix != "\x00" else ""
    base = f"{concern_name}.{effective_prefix}" if effective_prefix else f"{concern_name}."
    for k, v in data.items():
        if k == "schema":
            continue  # meta-key, not a user key
        # Self-named top-level table elision: at the root of the concern file
        # (_prefix=""), a sub-table named after the concern itself collapses
        # so that [unreal] inside unreal.local.toml produces unreal.<key>, not
        # unreal.unreal.<key>. Below the root, table names are kept as-is —
        # nested [unreal.versions] etc. still produce the natural dotted path.
        # Sentinel prefix ("\x00") on the recursive call ensures the elision
        # condition (not _prefix) is False for all nested levels — prevents
        # double-elision if a hand-crafted file has [unreal]\nunreal = {...}.
        if not _prefix and isinstance(v, dict) and k == concern_name:
            result.update(_flatten_concern(concern_name, v, _prefix="\x00"))
            continue
        full_key = f"{base}{k}"
        if isinstance(v, dict):
            # Recurse: flatten nested table with dotted subkeys.
            result.update(_flatten_concern(concern_name, v, _prefix=f"{effective_prefix}{k}." if effective_prefix else f"{k}."))
        else:
            # Store native type; _resolve_key handles list→newline join.
            result[full_key] = v
    return result


def _build_resolution_layers(reg_dir: str, _registry_local_data: dict | None = None) -> list[dict]:
    """Build the ordered list of dicts representing the resolution stack.

    Spec: resolution order is concern.local → concern → registry.local → registry.
    Returns layers in priority order (index 0 = highest priority).

    `_registry_local_data`, if given, is an already-parsed registry.local.toml
    dict, reused instead of re-parsing the file from disk. No current call site
    passes it — cmd_get now avoids the double-parse this parameter was meant
    for by building the layers once, up front, and passing them into
    resolve_one directly (see cmd_get), rather than by pre-parsing just
    registry.local.toml and threading it through here. The parameter is kept
    as a general escape hatch for a future caller that legitimately has a
    pre-parsed registry.local.toml dict on hand and nothing else.
    """
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

    # Concern-namespace exclusivity (the Director of Engineering F5): when a concern is listed in
    # `concerns`, keys in registry.toml whose first segment matches the concern
    # prefix emit a warning and are dropped from the registry layer.
    concerns_list = registry.get("concerns", [])
    if not isinstance(concerns_list, list):
        concerns_list = []

    # Build set of concern prefixes for namespace exclusivity check.
    concern_prefixes = {c.lower() for c in concerns_list}

    # Clean registry dict: flatten nested dicts to dotted keys, drop meta-keys,
    # then enforce namespace exclusivity on the flattened key set. Flattening
    # first lets natural TOML table syntax (`[unreal]\ninstall_root = "..."`)
    # and dotted-key syntax (`unreal.install_root = "..."`) both produce the
    # canonical dotted key the resolver looks up. Belt-and-suspenders: concern
    # files own promoted namespaces, but registry hand-edits or future
    # namespaces should still resolve cleanly.
    def _clean_registry(data: dict, source_label: str) -> dict:
        flat = _flatten_nested(data)
        cleaned = {}
        for k, v in flat.items():
            first_seg = k.split(".")[0].lower()
            if first_seg in concern_prefixes:
                print(
                    f"machine-local: warning: key '{k}' in {source_label} "
                    f"belongs to concern namespace '{first_seg}' — "
                    "the concern file wins; this entry is ignored.",
                    file=sys.stderr,
                )
                continue
            cleaned[k] = v
        return cleaned

    # Load concern layers (highest priority first within each concern).
    concern_local_layers = []
    concern_base_layers = []

    for concern in concerns_list:
        concern = str(concern)
        c_path = os.path.join(reg_dir, f"{concern}.toml")
        c_local_path = os.path.join(reg_dir, f"{concern}.local.toml")

        # Per-file isolation (doctrine-plane ruling (a), see _load_toml_isolated): a malformed
        # concern file warns and drops ONLY its own layer, None distinguishes that
        # from "absent/empty" ({}) so the two don't collapse into one warning below.
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

        # "Neither loadable" only when BOTH are cleanly absent/empty — not when
        # one or both are malformed. A malformed file already got its own warning
        # from _load_toml_isolated; repeating this generic warning on top of it
        # would be a confusing, duplicated diagnosis for the operator.
        if not c_data and not c_local_data and not c_data_malformed and not c_local_data_malformed:
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

    # Registry layers: flatten + enforce namespace exclusivity via the same helper.
    reg_local_clean = _clean_registry(registry_local, "registry.local.toml")
    reg_clean = _clean_registry(registry, "registry.toml")

    # Priority order: concern.local > concern > registry.local > registry
    layers = concern_local_layers + concern_base_layers + [reg_local_clean, reg_clean]
    return layers


def _resolve_key(key: str, layers: list[dict]) -> str | None:
    """Walk resolution layers and return first match, or None."""
    for layer in layers:
        if key in layer:
            val = layer[key]
            # TOML arrays are stored as Python lists; join with newlines.
            if isinstance(val, list):
                return "\n".join(str(i) for i in val)
            return str(val)
    return None


def _env_key(key: str) -> str:
    """Convert a dotted key to its env-var override name."""
    return "MACHINE_LOCAL_" + key.upper().replace(".", "_")


def _all_keys(layers: list[dict]) -> list[str]:
    """Return deduplicated, ordered list of all keys visible across layers."""
    seen = {}
    for layer in layers:
        for k in layer:
            if k not in seen:
                seen[k] = True
    return list(seen.keys())


def _normalize_key_separators(key: str) -> str:
    """Collapse '-', '.', '_' to one canonical separator for near-miss comparison.

    Registry keys mix separators inconsistently: underscore is the dominant house
    style but is NOT enforced -- some live keys are hyphenated. A caller reading a
    hyphenated repo/directory name off disk and reaching for its registry key has
    no in-context signal for which separator the registry chose, so the miss is
    structurally 50/50. This normalizer exists ONLY to power a suggestion (see
    `_did_you_mean`) -- it is never used to resolve a lookup.
    """
    return key.translate(str.maketrans({"-": "_", ".": "_"})).lower()


def _did_you_mean(key: str, candidates: list[str]) -> list[str]:
    """Return suggestion-only near-miss candidates for a missed registry key.

    Separator-insensitive matching runs first and is load-bearing: it catches the
    exact class of miss (a key that differs from a real one only by separator)
    deterministically, with no edit-distance cutoff to miss a long key whose sole
    difference is one separator. Falls back to `difflib.get_close_matches` for
    genuine typos only when no separator-normalized match exists.

    Because both separators are legal registry syntax, a normalized lookup can
    hit more than one candidate (e.g. two keys differing only by '-' vs '_'
    coexisting) -- ALL separator-normalized matches are returned, sorted for
    deterministic, test-assertable ordering, rather than picking a winner. This
    is suggestion-only, mirroring this fleet's existing near-miss "did you mean"
    convention for identifier resolution elsewhere: callers MUST NOT auto-resolve
    a near-miss.
    """
    normalized_key = _normalize_key_separators(key)
    others = [c for c in candidates if c != key]
    sep_matches = sorted(c for c in others if _normalize_key_separators(c) == normalized_key)
    if sep_matches:
        return sep_matches
    return sorted(difflib.get_close_matches(key, others, n=3, cutoff=0.6))


def _print_key_miss(key: str, candidates: list[str]) -> None:
    """Print the standard key-miss message plus a stderr-only 'did you mean' hint.

    Hard constraint: the hint is STDERR ONLY -- stdout must stay empty on a
    miss, and callers across the fleet branch on `get`'s clean
    exit-1-empty-stdout contract. This helper never touches stdout or the
    return code; callers still return EXIT_NOT_FOUND themselves.

    If `key` is a namespace prefix of other candidates (e.g. `repos`, which
    contains `repos.<slug>` entries), print a namespace-not-a-key hint instead
    of a near-miss suggestion -- at minimum, a pointer to `machine-local keys`.
    """
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


def resolve_one(key: str, layers: list[dict] | None = None) -> tuple[int, str | None]:
    """Resolve ONE key to (rc, value) without printing — the single read-path kernel.

    Returns an rc from the §4.1 tri-state (0 found / 1 cleanly absent / 2 operational
    failure) plus the resolved value on rc=0, or the operator-facing failure message
    on rc=2.  `--default` handling and all stdout/stderr emission stay with the
    callers, so this stays usable from both the CLI verbs and in-process consumers.

    `layers` is an optional pre-built resolution stack (see _build_resolution_layers).
    Pass it when resolving many keys in one process — cmd_dump does — so the TOML
    layers are parsed once rather than once per key.  It is only consulted on the
    generic (non-`repos.<slug>`) path; the repos ladder reads its own rungs by
    contract and must not be short-circuited through the generic stack (see
    resolve_sibling_repo's negative-spec).

    Negative-spec: this function is the ONLY place the routing decision between the
    repos 4-rung ladder and the generic resolution stack is made.  cmd_get and
    cmd_dump both call it precisely so a batch read cannot answer differently from
    a single read — a second reader that re-derived the routing would drift, and the
    drift would be silent (a repos.* sentinel resolving as a hit in one verb but not
    the other).
    """
    # Route repos.<slug> keys through the 4-rung sibling-repo resolver.
    # Only exact two-segment repos.* keys (repos.<single-slug>) are routed here;
    # deeper keys like repos.something.sub fall through to generic resolution.
    key_parts = key.split(".")
    if len(key_parts) == 2 and key_parts[0] == "repos":
        slug = key_parts[1]
        try:
            resolved = resolve_sibling_repo(slug)
        except (AmbiguousRepoMatch, EnvironmentError) as exc:
            # AmbiguousRepoMatch = detect-then-silently-pick footgun (misconfig).
            # EnvironmentError   = REPO_<SLUG> set but path absent (misconfig).
            # Both are EXIT_OPERATIONAL: the reader could not produce a clean answer.
            return EXIT_OPERATIONAL, f"machine-local: {exc}"

        if resolved is not None:
            # Emit forward-slash (POSIX) form for repos.* paths, unconditionally.
            # str(Path(...)) on a native Windows drive path yields the OS-native
            # backslashed form on Windows; that backslash-drive form breaks the
            # moment it reaches a bash-executed consumer (a leading backslash
            # letter is an escape → drive-relative doubling) — the F4
            # install-breaking hook-path bug. Forward slashes are accepted by
            # bash, py.exe, node, claude.exe, AND the Windows path APIs alike, so
            # this is the single canonical seam that fixes the hook-path bake (F4),
            # claude-doe's clone resolution + regen grep-gate (F6), and any shell
            # consumer doing `cd "$(machine-local get repos.x)"`.
            # _to_native_drive_path additionally repairs the MSYS mount form
            # ('/x/...' -> native drive form), which as_posix() leaves untouched
            # and which a native-Windows consumer would resolve as drive-relative
            # (doubled drive-letter directory).
            return EXIT_OK, _to_native_drive_path(resolved.as_posix())

        # resolve_sibling_repo returns None for both "absent key" and "key explicitly
        # set to empty string" (rung 4 maps empty→None to prevent registry.toml
        # sentinel placeholders from resolving as hits).  Distinguish the two cases
        # by reading registry.local.toml directly: if the key is present there (even
        # as ""), the user explicitly stored it and it must round-trip with rc=0.
        # Only registry.local.toml is checked here — NOT registry.toml, which carries
        # repos.* = "" sentinels for undiscovered slugs.
        reg_local_path = os.path.join(_registry_dir(), "registry.local.toml")
        reg_local_data = _load_toml(reg_local_path)
        if reg_local_data:
            flat_local = _flatten_nested(reg_local_data)
            if key in flat_local:
                return EXIT_OK, str(flat_local[key])

        return EXIT_NOT_FOUND, None

    # Generic resolution for non-repos keys.
    if layers is None:
        layers = _build_resolution_layers(_registry_dir())

    # Walk resolution order: concern.local → concern → registry.local → registry
    val = _resolve_key(key, layers)

    # Env override is BELOW all .toml layers (the Director of Engineering F1 / plan §4.3).
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

    # repos.<slug> keys route through the 4-rung sibling ladder inside resolve_one
    # and never touch the generic layers -- pre-building here would add a TOML
    # parse to the single hottest call in the CLI for no benefit. Every other key
    # builds the layers once, up front, and reuses them for both the resolve and
    # (on miss) the hint -- avoiding the double-parse this fix addresses.
    key_parts = key.split(".")
    is_repos_key = len(key_parts) == 2 and key_parts[0] == "repos"
    layers = None if is_repos_key else _build_resolution_layers(reg_dir)

    rc, val = resolve_one(key, layers=layers)

    if rc == EXIT_OPERATIONAL:
        print(val, file=sys.stderr)
        return EXIT_OPERATIONAL

    if rc == EXIT_OK:
        print(val)
        return EXIT_OK

    if args.default is not None:
        print(args.default)
        return EXIT_OK

    if layers is None:
        layers = _build_resolution_layers(reg_dir)
    _print_key_miss(key, _all_keys(layers))
    return EXIT_NOT_FOUND


def _repos_shell_var_name(key: str) -> str | None:
    """Normalize a repos.<slug> key to its shell variable name: REPO_<SLUG>.

    Strips the "repos." prefix, uppercases the suffix, and maps both "." and
    "-" to "_" -- the transform claude-machine-local.sh/.ps1 used to each
    implement themselves before dump grew a --format sh emitter; this is now
    the one implementation both indirectly share (they consume the emitter's
    output rather than re-deriving the name).

    Returns None for anything the shell exporter must not emit: a key that
    is not a two-segment repos.<slug> key, or one whose normalized name is
    not a valid POSIX shell identifier (^[A-Z_][A-Z0-9_]*$) -- callers skip
    and warn in that case, mirroring the identifier guard the shell wrappers
    used to apply themselves.
    """
    parts = key.split(".")
    if len(parts) != 2 or parts[0] != "repos":
        return None
    var = "REPO_" + re.sub(r"[.\-]", "_", parts[1]).upper()
    if not re.match(r"^[A-Z_][A-Z0-9_]*$", var):
        return None
    return var


def _shell_single_quote(value: str) -> str:
    """Escape `value` for a POSIX single-quoted shell literal, eval-safe.

    Closes the quote, emits a literal escaped quote, reopens -- the standard
    '\\'' idiom. Registry values are local paths today, but dump's `--format
    sh` output is `eval`'d by its caller, so this must hold for arbitrary
    content, not just the paths currently stored.
    """
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
      - resolved, non-empty            -> `[ -n "${VAR:-}" ] || export VAR='...'`
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
            elif rc == EXIT_OPERATIONAL:
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
            values[k] = val
        elif rc == EXIT_OPERATIONAL:
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


def cmd_has(args: argparse.Namespace) -> int:
    """Implement: machine-local has <key> — exit 0 if set, 1 if not (no output).

    Operational failures (version guard, malformed TOML) exit 2 before reaching
    this return, so a 1 here is always a clean "not set", never a broken reader.
    """
    reg_dir = _registry_dir()
    layers = _build_resolution_layers(reg_dir)
    key = args.key

    val = _resolve_key(key, layers)
    if val is None:
        val = os.environ.get(_env_key(key))

    return EXIT_OK if val is not None else EXIT_NOT_FOUND


def cmd_keys(args: argparse.Namespace) -> int:
    """Implement: machine-local keys [--prefix <p>] — list all known keys, one per line.

    stdout is the machine-parseable contract (one key per line, unchanged). When
    the listing includes tracked-baseline empty declarations (`repos.foo = ""`) —
    keys that enumerate here but for which `get` correctly reports not-found
    (empty ⇒ not provisioned on this machine) — a one-line hint is emitted to
    STDERR so first-contact users aren't confused by the keys/get asymmetry.
    Stderr keeps stdout pipe-clean. Spec: tasks/2026-07-14-install-dogfood-friction.md § F7.

    `--prefix` (optional) filters the listing to keys equal to, or nested under
    (dot-separated), the given prefix -- the one-step "what lives under `repos.`?"
    companion to `get`'s namespace-hit hint (`_print_key_miss`), so a caller that
    lands on a namespace instead of a leaf key has a next step other than a blind
    directory guess.
    """
    reg_dir = _registry_dir()
    layers = _build_resolution_layers(reg_dir)
    all_keys = _all_keys(layers)
    # Review: code-reviewer (Finding 5) — args.prefix is guaranteed present
    # (default None) by the argparse `--prefix` declaration on every path that
    # reaches cmd_keys via main(); getattr's defensive fallback was dead code.
    prefix = args.prefix
    if prefix:
        all_keys = [k for k in all_keys if k == prefix or k.startswith(f"{prefix}.")]
    empty_declared = [k for k in all_keys if _resolve_key(k, layers) == ""]
    for k in all_keys:
        print(k)
    if empty_declared:
        print(
            "note: {} key(s) are DECLARED (tracked baseline, empty) but not SET on "
            "this machine — `get` reports not-found for these until provisioned: {}".format(
                len(empty_declared), ", ".join(empty_declared)
            ),
            file=sys.stderr,
        )
    return 0


def cmd_path(args: argparse.Namespace) -> int:
    """Implement: machine-local path — print absolute path to active registry.toml."""
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
    honours COORDINATOR_SETTINGS_HOME > ${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings.
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


def _build_header_pats(prefix_parts):
    """Build (header_pat, aot_pat) for a given table prefix.

    # Review: code-reviewer (F1) — hoisted from inner closures in both
    # _locate_existing_definition and _locate_existing_array_span to eliminate
    # verbatim duplication. Both locators call this module-level function.
    """
    table_path = ".".join(prefix_parts)
    # Review: code-reviewer (F1) — OR bare-key and quoted-segment forms.
    quoted_segs = r'\s*\.\s*'.join(f'"{re.escape(p)}"' for p in prefix_parts)
    h_pat = re.compile(
        r"^\[\s*(?:" + re.escape(table_path) + r"|" + quoted_segs + r")\s*\][ \t]*(?:#[^\n]*)?$",
        re.MULTILINE,
    )
    # Review: code-reviewer (F7) — detect [[table.path]] array-of-tables.
    aot_pat = re.compile(
        r"^\[\[\s*(?:" + re.escape(table_path) + r"|" + quoted_segs + r")\s*\]\][ \t]*(?:#[^\n]*)?$",
        re.MULTILINE,
    )
    return h_pat, aot_pat


def _locate_existing_definition(content: str, key: str) -> dict | None:
    """Find an existing definition of `key` in TOML content.

    Returns a dict describing how the key is currently defined, or None if no
    matching structure exists. Three shapes:

      - {"kind": "flat", "match": <re.Match>}
          Found as `"key.with.dots" = "value"` anywhere in the file (the form
          machine-local set has historically written).
      - {"kind": "table-leaf", "leaf_match": <re.Match>, "abs_start": int,
         "abs_end": int}
          Found as a bare-leaf assignment inside an existing `[table.path]`
          header (the form natural TOML uses for grouped config — and the form
          that triggered the 2026-05-23 duplicate-write bug when set only knew
          about the flat shape).
      - {"kind": "table-header-only", "section_start": int, "section_end": int,
         "leaf_path": str}
          The `[table.path]` header exists but the leaf is absent inside it.
          cmd_set inserts the new leaf into the existing section body — a flat
          append below subsequent `[other.section]` headers would be a TOML
          parse error.
      - {"kind": "array-of-tables-detected", "table_path": str}
          The key's table path is defined as an array-of-tables ([[table.path]]).
          cmd_set cannot modify this shape — surface an actionable error.

    The search tries the longest table-path prefix first so that, for a key
    like `a.b.c.d`, it prefers an existing `[a.b.c]\nd = …` over `[a.b]\nc.d = …`
    if both exist (the registry only uses one form per key in practice).
    """
    # Review: code-reviewer (F11) — re and datetime moved to module-level imports.

    flat_pat = re.compile(
        r'^(\s*"' + re.escape(key) + r'"\s*=\s*)(?:"[^"]*"|\'[^\']*\')([ \t]*(?:#[^\n]*)?)',
        re.MULTILINE,
    )
    fm = flat_pat.search(content)
    if fm:
        return {"kind": "flat", "match": fm}

    parts = key.split(".")
    next_section_pat = re.compile(r"^\[", re.MULTILINE)

    # Review: code-reviewer (F2) — two-pass approach: first pass finds table-leaf
    # matches (longest prefix first); second pass finds table-header-only matches.
    # This prevents returning table-header-only for [a.b.c] when [a.b] already
    # has c.d = "..." as a dotted-leaf assignment inside it.

    # Pass 1: look for table-leaf matches only (longest prefix first).
    for i in range(len(parts) - 1, 0, -1):
        prefix_parts = parts[:i]
        leaf_path = ".".join(parts[i:])
        h_pat, aot_pat = _build_header_pats(prefix_parts)
        # Array-of-tables check is done in pass 1 so it still exits early.
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

    # Pass 2: look for table-header-only matches (longest prefix first).
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
    """Find an existing flat-array definition of `key` in TOML content.

    Spec backlink: docs/plans/2026-06-17-publish-targets-machine-local-migration.md § C1
    Purpose: Locate the byte span of an existing multi-line flat array assignment so
    array-append / array-set can replace the whole span atomically.

    The array-write commands (array-append / array-set) only write and read
    quoted-dotted-key multi-line flat arrays:
        "publish.targets" = [
          'row1',
          'row2',
        ]
    This function detects that shape plus the degenerate single-line / empty forms.

    Returns a dict on match:
        {"kind": "flat-array", "span_start": int, "span_end": int,
         "comment_start": int | None}
    where span_start..span_end covers the `"key" = [\n...\n]` block (plus the
    trailing newline, if any), and comment_start, if not None, points to the start
    of a provenance-comment line immediately above the array assignment (preserved
    on replace per F5).

    Returns None if no array assignment is found for this key (caller then creates
    one fresh).

    Uses module-level _build_header_pats (shared with _locate_existing_definition):
    if the key's table path appears as [[array-of-tables]], this function returns
    {"kind": "array-of-tables-detected", "table_path": str} so the caller can emit
    a specific error.

    Negative-spec: does NOT handle inline-table form (`key = {...}`) — the caller
    detects that via the round-trip pre-check (same as cmd_set's inline-table path).
    """
    # Review: code-reviewer (F4) — removed dead next_section_pat local (unused in this
    # function) and removed the inner _build_header_pats closure (now module-level per F1).
    parts = key.split(".")

    # Check for array-of-tables collision on the full key and any prefix.
    # [[publish.targets]] means the key itself is an array-of-tables table path.
    # [[publish]] with targets as a leaf would also be a collision (a prefix match).
    for i in range(len(parts), 0, -1):
        prefix_parts = parts[:i]
        _, aot_pat = _build_header_pats(prefix_parts)
        if aot_pat.search(content):
            return {"kind": "array-of-tables-detected", "table_path": ".".join(prefix_parts)}

    # Match the flat quoted-dotted-key array form:
    #   "key.with.dots" = [
    #     'row1',
    #     ...
    #   ]
    # The opening bracket may be on the same line or the closing may be on the same
    # line (degenerate []). We match from the `"key"` assignment to the closing `]`.
    array_open_pat = re.compile(
        r'^(\s*"' + re.escape(key) + r'"\s*=\s*\[)',
        re.MULTILINE,
    )
    m = array_open_pat.search(content)
    if not m:
        return None

    # Find the closing `]` that matches the opening `[`.
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
        # Malformed (unclosed bracket) — let the round-trip check catch it.
        return None

    # span_end: include the trailing newline after `]` if present.
    span_start = m.start()
    span_end = close_pos + 1
    if span_end < len(content) and content[span_end] == "\n":
        span_end += 1

    # Detect a provenance comment immediately above the assignment (F5).
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
    """Return True (reject) if element contains a single quote.

    TOML literal strings (single-quoted) have no escape mechanism.
    Negative-spec: no fallback encoding — refuse rather than guess.
    """
    return "'" in element


def _build_array_content(key: str, elements: list[str], date_tag: str,
                         provenance_comment: str | None = None) -> str:
    """Render a quoted-dotted-key multi-line flat TOML array block.

    Write shape per spec:
        # array-append <date>
        "publish.targets" = [
          'row1',
          'row2',
        ]

    If provenance_comment is provided (non-None), it replaces the fresh
    `# array-append <date>` comment (F5: preserve leading comment on replace).
    If elements is empty, renders an empty array.
    """
    comment = provenance_comment if provenance_comment is not None else f"# array-append {date_tag}"
    rows = "".join(f"  '{e}',\n" for e in elements)
    return f'{comment}\n"{key}" = [\n{rows}]\n'


def _write_registry_file(target_path: str, new_content: str, is_new: bool) -> int:
    """Atomic tmp+rename write of registry content.

    Returns 0 on success, 1 on failure (prints error to stderr).
    Preserves file mode when replacing an existing file.
    """
    tmp_path = target_path + f".tmp.{os.getpid()}"
    try:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        if not is_new:
            try:
                os.chmod(tmp_path, os.stat(target_path).st_mode)
            except OSError:
                pass
        os.replace(tmp_path, target_path)
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
    """Return (target_file, target_path, content, is_new) for set/array commands."""
    target_file = "registry.toml" if write_global else "registry.local.toml"
    target_path = os.path.join(reg_dir, target_file)
    if os.path.exists(target_path):
        with open(target_path, "r", encoding="utf-8") as f:
            content = f.read()
        is_new = False
    else:
        is_new = True
        # Review: code-reviewer (F5) — header says "machine-local" not "machine-local set"
        # because array commands also create new files via this helper.
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
    """Return 1 (with error) if key belongs to a loaded concern namespace, else 0."""
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
    """Implement: machine-local array-append <key> <element> [--global] [--dry-run]

    Append element to the TOML array at key.  Idempotent: skip if element is
    already present (exact-string dedup).  Create the array if key is absent.

    Spec backlink: docs/plans/2026-06-17-publish-targets-machine-local-migration.md § C1
    Note: the current sole consumer is publish.targets, but the API is keyed on the
    dotted key, not hardcoded to that name.

    Fail loud if key already exists as a scalar (not an array), as an
    array-of-tables, or as an inline table.  Reject elements containing a
    single quote (TOML literal strings have no escape).
    """
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

    _target_file, target_path, content, is_new = _load_registry_target(reg_dir, args.write_global)
    date_tag = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Review: code-reviewer (F2) — removed dead pre_parsed/pre_flat/pre_val block; pre_val
    # was never used. The real collision check is the segment-walking parse below.

    # Detect scalar collision — key exists but resolves to a string (not a list).
    # Note: _flatten_nested stores the native Python type; lists come through as list.
    # For the pre-check we read the raw parsed value, not _flatten_nested, because
    # _resolve_key joins lists with \n (losing the list type we need here); _flatten_nested
    # itself stores non-dict values, including lists, unchanged.
    try:
        pre_raw = tomllib.loads(content)
        # Walk dotted key segments into the parsed dict.
        _cursor = pre_raw
        for seg in key.split("."):
            if isinstance(_cursor, dict) and seg in _cursor:
                _cursor = _cursor[seg]
            else:
                # Also check quoted-dotted flat key form.
                if isinstance(_cursor, dict) and key in _cursor:
                    _cursor = _cursor[key]
                    break
                _cursor = None
                break
        raw_existing = _cursor
        # Also try quoted-dotted flat key form at top level.
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

    # Detect array-of-tables shape via locator.
    array_span = _locate_existing_array_span(content, key)
    if array_span is not None and array_span["kind"] == "array-of-tables-detected":
        print(
            f"machine-local: '{key}' is defined as an array-of-tables ([[{array_span['table_path']}]]); "
            "cannot use array-append. Hand-edit the file to update it.",
            file=sys.stderr,
        )
        return 1

    # Read current elements from the existing flat-array span (if any).
    current_elements: list[str] = []
    provenance_comment: str | None = None

    if array_span is not None and array_span["kind"] == "flat-array":
        # Parse existing array via tomllib to get the current elements.
        try:
            parsed_existing = tomllib.loads(content)
            # Navigate to the key value — may be a flat quoted-dotted key or
            # nested table, so use _flatten_nested's list-preserving sibling.
            # _resolve_key joins lists with \n, so read from the raw parsed dict instead.
            flat_raw = _get_raw_list(parsed_existing, key)
            if isinstance(flat_raw, list):
                current_elements = [str(e) for e in flat_raw]
        except tomllib.TOMLDecodeError:
            pass

        # Retrieve provenance comment (F5).
        if array_span["comment_start"] is not None:
            # Find end of comment line.
            cstart = array_span["comment_start"]
            cend = content.find("\n", cstart)
            if cend == -1:
                cend = len(content)
            provenance_comment = content[cstart:cend]

    # Idempotent dedup: skip if element already present.
    if element in current_elements:
        if dry_run:
            print(f"[dry-run] '{key}': element already present (no-op): {element!r}")
        else:
            print(f"machine-local: '{key}': element already present (no-op): {element!r}")
        return 0

    new_elements = current_elements + [element]
    array_block = _build_array_content(key, new_elements, date_tag, provenance_comment)

    if array_span is not None and array_span["kind"] == "flat-array":
        # Replace the existing span (including provenance comment if we captured it).
        replace_start = array_span["comment_start"] if array_span["comment_start"] is not None else array_span["span_start"]
        replace_end = array_span["span_end"]
        new_content = content[:replace_start] + array_block + content[replace_end:]
        action = "updated"
    else:
        # Insert before first [section] header, or at EOF.
        section_pat = re.compile(r"^\[", re.MULTILINE)
        m = section_pat.search(content)
        if m:
            insert_at = m.start()
            new_content = content[:insert_at].rstrip("\n") + "\n" + array_block + "\n" + content[insert_at:]
        else:
            new_content = content.rstrip("\n") + "\n" + array_block
        action = "added"

    # Post-build round-trip sanity: parse new_content and verify the array
    # contains the expected elements.  Also verifies correct top-level scope
    # (a key appended after a [table] header would scope INTO that table).
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
        print(f"[dry-run] would {action} array '{key}' (append {element!r}) in {target_path}")
        return 0

    rc = _write_registry_file(target_path, new_content, is_new)
    if rc != 0:
        return rc

    print(f"machine-local: {action} array '{key}' (appended {element!r}) in {target_path}")
    return 0


def cmd_array_set(args: argparse.Namespace) -> int:
    """Implement: machine-local array-set <key> <element>... [--global] [--dry-run]

    Replace the entire array at key with the given elements (order-preserving
    dedup).  Same scalar-collision fail-loud and single-quote rejection as
    array-append.

    Spec backlink: docs/plans/2026-06-17-publish-targets-machine-local-migration.md § C1
    Note: the current sole consumer is publish.targets, but the API is keyed on the
    dotted key, not hardcoded to that name.
    """
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

    _target_file, target_path, content, is_new = _load_registry_target(reg_dir, args.write_global)
    date_tag = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Same pre-check as array-append: fail loud on scalar / inline-table.
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

    # Order-preserving dedup of supplied elements.
    seen: set[str] = set()
    deduped: list[str] = []
    for e in elements:
        if e not in seen:
            seen.add(e)
            deduped.append(e)

    # Retrieve provenance comment from existing span (F5).
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

    # Post-build round-trip sanity.
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
        print(f"[dry-run] would {action} array '{key}' = {deduped!r} in {target_path}")
        return 0

    rc = _write_registry_file(target_path, new_content, is_new)
    if rc != 0:
        return rc

    print(f"machine-local: {action} array '{key}' = {deduped!r} in {target_path}")
    return 0


def _get_raw_list(parsed: dict, key: str) -> object:
    """Navigate parsed TOML dict to retrieve the native value for a dotted key.

    Handles both quoted-dotted-key flat form (where the literal dot is in the
    top-level dict key) and nested-table form.  Returns the raw Python object
    (list, str, dict, etc.) so callers can isinstance-check the type.
    Returns None if the key is not found.
    """
    # Try quoted-dotted flat key first (the form array-write uses).
    if key in parsed:
        return parsed[key]
    # Try walking nested dicts via split(".").
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
        # TOML literal string; the caller rejects embedded single quotes.
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
    escape). Mirrors the addon ``_write_unreal_concern`` full-reserialize shape
    rather than surgical edits, because concern files are tool-managed.
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


def _cmd_set_concern(args: argparse.Namespace) -> int:
    """Implement: machine-local set --concern <name> <key> <value> [--dry-run]

    The general-purpose writer for namespaced concern keys (`unreal.*`,
    `hardware.*`, ...) — the namespace that the registry `set` refuses by
    concern-exclusivity. Resolves the concern file at `<name>.local.toml`,
    validates the key is under the `<name>.` namespace (no cross-concern
    pollution), performs an atomic read-merge-write that preserves every other
    key/table, and stamps provenance under `[provenance.<bare_key>]`.

    Spec backlink: cross-repo memo 2026-06-23-machine-local-concern-set-writer.md
    (project-rag-ue-addon-em ask; dogfood finding #3). Replaces the workaround of
    hand-editing the concern TOML, which loses atomicity + provenance.
    """
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

    # Namespace validation: the key's first segment must equal the concern name.
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

    # Soft offer (not a block): if the concern is not registered in `concerns`,
    # the written value will not resolve via `get` until it is — surface the gap
    # with the remediation rather than silently writing an unreadable file.
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

    # Read-merge: parse existing concern file (fail loud on malformed) into a
    # body dict (the self-named table contents + any top-level scalars folded in)
    # and a provenance dict.
    schema_val: object = 1
    body: dict = {}
    provenance: dict = {}
    is_new = not os.path.exists(target_path)
    if not is_new:
        with open(target_path, "r", encoding="utf-8") as f:
            existing_content = f.read()
        try:
            existing = tomllib.loads(existing_content)
        except tomllib.TOMLDecodeError as exc:
            print(
                f"machine-local: cannot parse existing {target_path}: {exc}. "
                "Fix or remove it by hand.",
                file=sys.stderr,
            )
            return 1
        schema_val = existing.get("schema", 1)
        named = existing.get(name)
        if isinstance(named, dict):
            body = dict(named)
        # Fold any top-level scalar/table keys (the auto-prefixed form the reader
        # also accepts) into the canonical self-named table.
        for k, v in existing.items():
            if k in ("schema", "provenance", name):
                continue
            body[k] = v
        prov = existing.get("provenance")
        if isinstance(prov, dict):
            provenance = dict(prov)

    # Upsert the bare key (dotted bare keys → nested sub-tables).
    segs = bare.split(".")
    cursor = body
    for seg in segs[:-1]:
        nxt = cursor.get(seg)
        if not isinstance(nxt, dict):
            nxt = {}
            cursor[seg] = nxt
        cursor = nxt
    cursor[segs[-1]] = value

    date_tag = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    provenance[bare] = {
        "written_by": "machine-local",
        "written_at": date_tag,
        "source": "cli:--concern",
    }

    try:
        new_content = _serialize_concern_file(name, body, provenance, schema_val)
    except ValueError as exc:
        print(
            f"machine-local: refusing to write — {exc}. "
            "A co-writer left a value type this writer does not serialize; "
            "edit the concern file by hand for that key.",
            file=sys.stderr,
        )
        return 1

    # Round-trip sanity: the new content must parse and the key must resolve to
    # the requested value through the same `_flatten_concern` the reader uses.
    # `name` and `key` are both lowercase here (the mixed-case guard above rejected
    # any uppercase), so the literal `key` is the canonical resolution form.
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

    tmp_path = target_path + f".tmp.{os.getpid()}"
    try:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        if not is_new:
            try:
                os.chmod(tmp_path, os.stat(target_path).st_mode)
            except OSError:
                pass
        os.replace(tmp_path, target_path)
    except Exception as exc:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        print(f"machine-local: write failed: {exc}", file=sys.stderr)
        return 1

    print(f"machine-local: set {key!r} = {value!r} in {target_path}")
    return 0


def cmd_set(args: argparse.Namespace) -> int:
    """Implement: machine-local set <key> <value> [--global] [--dry-run]
                  machine-local set --concern <name> <key> <value> [--dry-run]

    Writes a string key=value pair to registry.local.toml (default) or
    registry.toml (--global).  Atomic, idempotent, concern-aware.

    With --concern <name>, routes to the concern-file writer (_cmd_set_concern)
    which writes the namespaced key into <name>.local.toml — the path the bare
    registry writer refuses by concern-exclusivity.

    Use this instead of editing registry files by hand — direct edits are
    fragile: they do not reproduce on reinstall or transfer to a new machine,
    and may be clobbered by a concurrent session.
    """
    # Review: code-reviewer (F11) — re and datetime moved to module-level imports.

    if getattr(args, "concern", None):
        return _cmd_set_concern(args)

    reg_dir = _registry_dir()
    target_file = "registry.toml" if args.write_global else "registry.local.toml"
    target_path = os.path.join(reg_dir, target_file)

    key = args.key
    value = args.value
    dry_run = args.dry_run

    # Review: code-reviewer (F7) — replaced inline concern-namespace check with
    # _check_concern_namespace helper (same behavior, matches array commands).
    rc = _check_concern_namespace(reg_dir, key)
    if rc != 0:
        return rc

    # Read existing content or seed a new file.
    if os.path.exists(target_path):
        with open(target_path, "r", encoding="utf-8") as f:
            content = f.read()
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

    # Refuse to write values containing a single quote — TOML literal strings
    # (single-quoted) have no escape mechanism. This matches the example-game-repo
    # write_unreal_concern.py policy: refuse rather than guess.
    if "'" in value:
        print(
            f"machine-local: refusing to write value containing single quote: {value!r}. "
            "Literal-string TOML has no escape for single quote.",
            file=sys.stderr,
        )
        return 1

    value_literal = f"'{value}'"  # TOML literal string (no escape processing)

    # Existing-definition detection has four shapes:
    #   1. Flat:  "key.with.dots" = "old"   anywhere in file
    #   2. Table-form leaf:  [table.path]\nleaf = "old"  — leaf inside an existing table
    #   3. Table-form header without leaf:  [table.path] exists but no matching leaf
    #   4. Array-of-tables / inline table — detected but not modifiable by this writer
    # We try (1) → (2) → (3) → inline-table pre-check → append-as-flat, in order.
    # The dispatch covers the 2026-05-23 bug where set saw only (1) and appended a
    # duplicate when the existing definition was (2), creating a TOML where the
    # table-form silently won on read.
    update_result = _locate_existing_definition(content, key)

    # Guard F1: if the key resolves (via _flatten_nested on the parsed file) to a
    # list, it is an array — fail loud before touching it.  This fires BEFORE the
    # array-of-tables branch and inline-table check so the operator gets the
    # actionable array-command message rather than a generic shape error.
    try:
        _pre_parsed_for_guard = tomllib.loads(content)
        _pre_flat_for_guard = _flatten_nested(_pre_parsed_for_guard)
        _pre_val_for_guard = _pre_flat_for_guard.get(key)
    except tomllib.TOMLDecodeError:
        _pre_val_for_guard = None

    if isinstance(_pre_val_for_guard, list):
        # _flatten_nested stores the list unchanged (it only recurses into dicts), so
        # this branch fires on a genuine list — but raw pre-parse check is more
        # reliable.  Re-check via _get_raw_list to confirm it is genuinely a list.
        _raw_for_guard = _get_raw_list(_pre_parsed_for_guard, key)
        if isinstance(_raw_for_guard, list):
            print(
                f"machine-local: '{key}' is an array; use `array-append`/`array-set`, not `set`.",
                file=sys.stderr,
            )
            return 1

    if update_result is not None and update_result["kind"] == "array-of-tables-detected":
        # Review: code-reviewer (F7) — array-of-tables detected; route to actionable error.
        print(
            f"machine-local: key '{key}' resolves in '{target_path}' but its "
            "definition shape (inline table, array-of-tables, or other) is not "
            "modifiable by this writer. Hand-edit the file to update it.",
            file=sys.stderr,
        )
        return 1

    if update_result is None:
        # Review: code-reviewer (F3) — inline-table pre-check before falling through to
        # flat-append. If the key resolves via tomllib but no regex shape matched it,
        # the definition is an inline table, array-of-tables, or other unmodifiable form.
        # The round-trip check below would also catch this, but surfacing the specific
        # diagnosis here is far more actionable.
        try:
            pre_parsed = tomllib.loads(content)
            pre_resolved = _flatten_nested(pre_parsed).get(key)
        except tomllib.TOMLDecodeError:
            pre_resolved = None  # malformed — let write proceed, round-trip check will catch it

        if pre_resolved is not None:
            print(
                f"machine-local: key '{key}' resolves in '{target_path}' but its "
                "definition shape (inline table, array-of-tables, or other) is not "
                "modifiable by this writer. Hand-edit the file to update it.",
                file=sys.stderr,
            )
            return 1

        # No existing definition anywhere — append a flat quoted-dotted-key line
        # before the first [<section>] header (or at EOF if none).
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
            # Table header exists but the leaf is absent inside it. Inject the
            # leaf at the end of the table's body (before the next section header
            # or EOF). Flat-append would be a TOML error if subsequent
            # [<other.section>] headers follow this one — TOML forbids reopening
            # a closed table from outside any table.
            section_start = update_result["section_start"]
            section_end = update_result["section_end"]
            leaf_path = update_result["leaf_path"]
            section_body = content[section_start:section_end]
            # Review: code-reviewer (F6) — match sibling key indentation rather than
            # always injecting unindented. Standard registry TOML has no indentation,
            # so this falls back to no-indent for the common case.
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

    # Post-build round-trip sanity check: the new content must parse and the
    # requested key must resolve to the requested value via _flatten_nested.
    # Review: code-reviewer (F4) — this check verifies parse+flatten correctness
    # for the file being written. It does NOT verify the full resolution stack:
    # concern-namespace exclusivity is already handled by the guard above; env-var
    # resolution is below all TOML layers and irrelevant for write verification.
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

    # Resolve via the same flatten logic the reader uses so a quoted-dotted-key
    # (`"repos.example-game-repo" = ...` parses as a single flat key) and a nested table
    # (`[repos]\nexample_game_repo = ...` parses as `{"repos": {"example-game-repo": ...}}`) both
    # resolve to the dotted key the operator typed. Walking parsed with split(".")
    # mishandles the quoted-key shape because TOML keeps the literal dot in the key.
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
        print(f"[dry-run] would {action} {key!r} = {value!r} in {target_path}")
        return 0

    # Atomic write via tmp + rename.
    tmp_path = target_path + f".tmp.{os.getpid()}"
    try:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        if not is_new:
            try:
                os.chmod(tmp_path, os.stat(target_path).st_mode)
            except OSError:
                pass
        os.replace(tmp_path, target_path)
    except Exception as exc:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        print(f"machine-local: write failed: {exc}", file=sys.stderr)
        return 1

    print(f"machine-local: {action} {key!r} = {value!r} in {target_path}")
    return 0


def _remove_key(content: str, key: str) -> tuple[str, str | None]:
    """Remove a TOML scalar key from content, preserving surrounding keys and comments.

    Handles the flat quoted-dotted form (the form cmd_set writes) and the
    table-leaf form (bare leaf inside a [table.path] section).

    Also removes an immediately-preceding standalone comment line (a line whose
    stripped form starts with '#', with no blank line between it and the key
    assignment) since that comment belongs to the removed key, not its neighbours.
    Mirrors the F5 provenance-comment detection in cmd_array_append (~:617).

    Returns (new_content, old_value_str) when the key is found and removed.
    Returns (content, None) when the key is absent, not a string scalar, or in a
    shape this helper cannot surgically remove (array, inline table, array-of-tables).

    Spec backlink: docs/plans/2026-06-30-registry-publish-vs-working-targets.md § D4
    Negative-spec: does NOT remove [table] section headers left empty by leaf removal
    — only the leaf line (and its provenance comment) are excised.
    Negative-spec: does NOT modify registry.toml (tracked) — callers pass only the
    local-file content string.
    """
    # Resolve current value from the file so we can return it to the caller.
    try:
        parsed = tomllib.loads(content)
        flat = _flatten_nested(parsed)
        old_value = flat.get(key)
    except tomllib.TOMLDecodeError:
        return content, None

    if old_value is None:
        return content, None
    if not isinstance(old_value, str):
        # Arrays, inline tables, etc. are not handled here.
        return content, None

    locate = _locate_existing_definition(content, key)
    if locate is None:
        return content, None

    kind = locate["kind"]

    def _excise(line_start: int, match_end: int) -> str:
        """Remove line [line_start, line_end), optionally its preceding comment."""
        line_end_pos = content.find("\n", match_end)
        line_end = line_end_pos + 1 if line_end_pos != -1 else len(content)
        # Check for an immediately-preceding provenance comment (# line, no gap).
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

    # table-header-only: section exists but leaf absent — nothing to remove.
    # array-of-tables-detected or other: not safely handled here.
    return content, None


def cmd_unset(args: argparse.Namespace) -> int:
    """Implement: machine-local unset <key> [--global] [--dry-run] [--concern NAME]

    Removes a string-scalar key from ONE target file: registry.local.toml
    (default) or registry.toml (--global). Target-file-scoped, NOT
    resolution-stack-scoped — it does not consult or mutate other layers.
    Consequence: after unsetting from registry.local.toml, `machine-local has
    <key>` may still exit 0 because registry.toml (or a concern layer, or the
    env layer) still supplies it. That is correct behavior, not a bug.

    Exit-code contract — the read-path tri-state, NOT cmd_set's 0/non-zero
    convention. unset is the one write verb with a clean-absence outcome:
        0  key was present in the target file and was removed (or, under
           --dry-run, would be).
        1  key was already absent from the target file — a clean no-op, no
           write, no stderr noise. Makes the verb idempotent while still
           distinguishing "removed" from "was already absent".
        2  operational failure: every refusal path (malformed target TOML,
           array-valued key, non-string-scalar key, an unhandled definition
           shape, round-trip failure, atomic-write failure, --concern) — never
           1, which is reserved for the clean negative.

    --concern is deliberately NOT supported: accepted by argparse, refused at
    runtime (exit 2) with an actionable message, rather than omitted (which
    would surface argparse's bare "unrecognized arguments"). Concern-file leaf
    removal is unimplemented because _cmd_set_concern also writes a per-key
    [provenance.<key>] table that a leaf-only removal would strand; remediation
    is to hand-edit <NAME>.local.toml.

    No concern-namespace guard (deliberate divergence from cmd_set): removing
    a stale concern-namespace key still sitting in a registry file is exactly
    the cleanup this verb exists for, so _check_concern_namespace is NOT
    called here.

    Empty [table] headers are left in place — inherits _remove_key's negative-
    spec. A generic header sweep is unsafe (comments, sibling tooling), and an
    empty table resolves to nothing, so an operator note is printed instead of
    an automatic sweep.

    Review: code-reviewer (F2) — the read-then-write here is not compare-and-
    swap: a concurrent writer's change landing between the read at file open
    and the `os.replace` in _write_registry_file is silently lost. The atomic
    write narrows the race window from the minutes a hand-edit takes to the
    milliseconds this verb runs in; it does not eliminate the race.

    Spec backlink: state/handoffs/2026-08-12-machine-local-toml-and-unset-verb.md
    """
    if getattr(args, "concern", None):
        print(
            "machine-local: unset does not support --concern: the concern-file "
            "writer (_cmd_set_concern) also writes a per-key [provenance.<key>] "
            "table that a leaf-only removal would strand, and stranded-provenance "
            f"removal is unimplemented. Hand-edit {args.concern}.local.toml instead.",
            file=sys.stderr,
        )
        return EXIT_OPERATIONAL

    reg_dir = _registry_dir()
    target_file = "registry.toml" if args.write_global else "registry.local.toml"
    target_path = os.path.join(reg_dir, target_file)
    key = args.key

    if not os.path.exists(target_path):
        return EXIT_NOT_FOUND

    with open(target_path, "r", encoding="utf-8") as f:
        content = f.read()

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

    # Review: code-reviewer (F3) — only note a possibly-empty header when the
    # section body is actually now empty (whitespace/comments only), not
    # merely because the removed leaf's original shape was table-leaf; a
    # table with sibling leaves remaining must not print the note.
    empty_header_note = False
    # Review: code-reviewer (F5) — `content` is immutable and unchanged by
    # _remove_key above; re-reading it here (rather than new_content) is
    # deliberate, to see the pre-removal shape/position for detection.
    removed_kind = (_locate_existing_definition(content, key) or {}).get("kind")
    if removed_kind == "table-leaf":
        # Find the header line immediately preceding the key's original
        # position, then check whether that same section in new_content is
        # now whitespace/comment-only up to the next header (or EOF).
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
    return EXIT_OK


def _insert_mirror_path(content: str, mirror_key: str, path_value: str,
                        date_tag: str) -> str:
    """Write path = '<path_value>' into [publish.mirrors.<mirror_key>] in content.

    Prefers injecting into an existing [publish.mirrors.<mirror_key>] section if
    one is present (table-header-only or table-leaf update). When no such section
    exists, appends a new one at EOF (the common case for registry.local.toml on
    a machine that has never set publish.mirrors.* keys).

    Mirrors the table-header-only injection logic in cmd_set for the update path.

    Spec backlink: docs/plans/2026-06-30-registry-publish-vs-working-targets.md § D4
    Negative-spec: operates only on the content string supplied by the caller
    (registry.local.toml); does not read or modify registry.toml (tracked).
    """
    # Review: code-reviewer (F5) — TOML literal strings (single-quoted) have no
    # escape mechanism; a path containing a single quote would produce malformed TOML.
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
        # No existing section — append a fresh [publish.mirrors.<key>] block.
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
        # Section header exists but 'path' leaf is absent — inject it inside.
        # Mirrors cmd_set's table-header-only injection (match sibling indentation).
        section_start = locate["section_start"]
        section_end = locate["section_end"]
        leaf_path = locate["leaf_path"]  # e.g. "path"
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

    # array-of-tables-detected or unknown shape — fall back to appending.
    block = (
        f"\n[publish.mirrors.{mirror_key}]\n"
        f"path = {value_literal}  # migrate-publish-mirrors {date_tag}\n"
    )
    return content.rstrip("\n") + "\n" + block


# Review: code-reviewer (F6) — hoisted from inside cmd_migrate_publish_mirrors to
# module-level so the migration contract is greppable without reading the full function.
_MIRROR_SOURCES = [
    # (old_key, canonical_mirror_key, is_legacy_alias)
    # Canonical keys first so the legacy alias sees the target already set.
    ("repos.coordinator_claude",   "coordinator_claude",   False),
    ("repos.deep_research_claude", "deep_research_claude", False),
    ("repos.deep_research",        "deep_research_claude", True),  # legacy alias
]

_ARRAY_TOKEN_REPLACEMENTS = [
    # (old_token, new_token) — rewrites repo:<mirror> → publish-mirror:<key>
    # in publish.targets array rows so D3 removal of repos.* doesn't break them.
    ("repo:coordinator_claude",   "publish-mirror:coordinator_claude"),
    ("repo:deep_research_claude", "publish-mirror:deep_research_claude"),
    ("repo:deep_research",        "publish-mirror:deep_research_claude"),  # legacy alias
]


def cmd_migrate_publish_mirrors(args: argparse.Namespace) -> int:
    """Implement: machine-local migrate-publish-mirrors

    Idempotently migrate publish-mirror destination paths from the deprecated
    repos.* namespace into the correct publish.mirrors.* tables in
    registry.local.toml (per-machine, gitignored).

    Keys migrated (registry.local.toml → publish.mirrors.*.path):
      repos.coordinator_claude   → publish.mirrors.coordinator_claude.path
      repos.deep_research_claude → publish.mirrors.deep_research_claude.path
      repos.deep_research        → publish.mirrors.deep_research_claude.path (legacy alias)

    Also rewrites any 'publish.targets' registry-array rows whose field-3 contains
    a 'repo:<mirror>' reference to the new 'publish-mirror:<key>' prefix, so that
    D3 (removal of repos.* mirror keys from the tracked registry.toml) does not
    rc1-fail those rows at resolve time.

    For the legacy setup/publish-targets.sh fallback (gitignored, per-machine),
    this command cannot safely auto-edit it — instead it emits a loud
    operator-remediation block naming exactly what to change.

    Idempotent: re-running after a successful migration is a no-op (no write).
    Fresh clean-install (absent or empty registry.local.toml): no-op, exit 0.

    Spec backlink: docs/plans/2026-06-30-registry-publish-vs-working-targets.md § D4
    """
    reg_dir = _registry_dir()
    local_path = os.path.join(reg_dir, "registry.local.toml")

    # Fresh clean-install: absent file → no-op.
    if not os.path.exists(local_path):
        print("machine-local migrate-publish-mirrors: registry.local.toml absent — nothing to migrate.")
        return EXIT_OK

    with open(local_path, "r", encoding="utf-8") as f:
        content = f.read()

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

        # Re-parse after every step — content may have changed in prior iterations.
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
            # Key absent from this file — skip.
            continue

        if is_alias:
            print(
                f"machine-local: DEPRECATION: {old_key!r} is the legacy alias for "
                f"'repos.deep_research_claude'; migrating its value to {target_path_key!r}."
            )

        target_already = cur_flat.get(target_path_key)

        if target_already is not None:
            # Target path already set (canonical key was migrated earlier in this
            # run or in a previous run). Only remove the stale old key.
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
            # Migrate: remove old key, write path into publish.mirrors.<key>.
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
                # Review: code-reviewer (F3) — rows need rewriting but the array span could
                # not be located (None) or is array-of-tables (not rewritable by this writer).
                # A partial migration reported as success would leave stale repo:<mirror> rows.
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

    # --- Legacy publish-targets.sh operator remediation ---
    # The legacy file is gitignored and per-machine; auto-edit is not safe.
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

    # Final round-trip sanity: ensure the modified content is valid TOML before writing.
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
    # Review: code-reviewer (F8) — operator note: _remove_key does NOT remove empty
    # [table] section headers left behind after leaf removal (negative-spec of _remove_key).
    # An empty [repos] section header may remain — this is harmless valid TOML; remove
    # it manually if desired (e.g. delete the [repos] line from registry.local.toml).
    print(
        "machine-local: Note: an empty [repos] header may remain in registry.local.toml "
        "after migration — this is harmless valid TOML; remove it manually if desired."
    )
    return EXIT_OK


def main() -> int:
    # Windows: Python text-mode stdout translates '\n' -> '\r\n', so a captured
    # `$(machine-local get repos.x)` carries a trailing '\r'. That stray CR
    # silently breaks downstream string/path comparisons — notably claude-doe's
    # regen grep-gate (friction F6: the CR made `grep -qF "$DOE_COORDINATOR/hooks"`
    # never match settings.json, forcing a full hook-block regen + "clobbered"
    # noise on every launch). Emit LF-only output on every platform. Guarded for
    # stream objects that don't expose reconfigure (non-TextIOWrapper).
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(newline="\n")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(
        prog="machine-local",
        description="Read per-machine config from <settings-home>/machine-local/",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # get
    get_p = subparsers.add_parser("get", help="Print value for a key")
    get_p.add_argument("key", help="Dotted key name (e.g. repos.example_game_workbench_repo)")
    get_p.add_argument("--default", metavar="VALUE", default=None,
                       help="Value to print if key is missing (always exits 0)")

    # has
    has_p = subparsers.add_parser("has", help="Exit 0 if key is set, 1 if not set, 2 on operational failure (see machine-local-registry.md §4.1)")
    has_p.add_argument("key", help="Dotted key name")

    # keys
    keys_p = subparsers.add_parser("keys", help="List all known keys, one per line")
    keys_p.add_argument(
        "--prefix", metavar="PREFIX", default=None,
        help="Only list keys equal to, or nested under (dotted), PREFIX (e.g. repos)",
    )

    # dump
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
        "--format", choices=["json", "sh"], default="json",
        help=(
            "Output format. 'json' (default): a JSON object of key -> value, "
            "unchanged contract. 'sh': one guarded `export VAR=...` line per "
            "resolved repos.<slug> key, for `eval` by claude-machine-local.sh."
        ),
    )

    # path
    subparsers.add_parser("path", help="Print absolute path to active registry.toml")

    # dir
    subparsers.add_parser(
        "dir",
        help=(
            "Print absolute path to the machine-local directory "
            "(<settings-home>/machine-local). Sanctioned dir-resolution primitive "
            "for concern-file readers — use instead of hardcoding ~/.claude/machine-local."
        ),
    )

    # set
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

    # unset
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
        help="Not supported — accepted so the operator gets an actionable message "
             "instead of a bare argparse 'unrecognized arguments' error.",
    )

    # array-append
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

    # array-set
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

    # migrate-publish-mirrors
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
        "has": cmd_has,
        "keys": cmd_keys,
        "dump": cmd_dump,
        "path": cmd_path,
        "dir": cmd_dir,
        "set": cmd_set,
        "unset": cmd_unset,
        "array-append": cmd_array_append,
        "array-set": cmd_array_set,
        "migrate-publish-mirrors": cmd_migrate_publish_mirrors,
    }
    return dispatch[parsed.command](parsed)


if __name__ == "__main__":
    sys.exit(main())
