#!/usr/bin/env python3
"""Idempotently seed enabledPlugins[<plugin>@<marketplace>] for every present
marketplace-sibling plugin into settings.local.json.

Purpose: a fresh **inline** coordinator install (`claude --plugin-dir
<clone>/coordinator`) never writes any `enabledPlugins` entry for a
marketplace-sibling repo (project-rag, project-rag-ue-addon,
Example-game-workbench-repo, example-cockpit-repo, example-market-data-repo, example-store-repo,
Claude-klabauter, ...) — the plugin's slash commands stay dark until someone
hand-authors the key. This seeder derives, at `coordinator:install` time,
which siblings are actually checked out on THIS machine (registry-driven)
and what `<plugin>@<marketplace>` key(s) each one needs (manifest-driven),
then merges only the missing keys into `settings.local.json`.

Enumeration is manifest-derived, not a maintained table (the Director of Engineering F2 — the
machine-local registry holds ~19 `repos.*` entries, most non-plugin; a
maintained table would just re-encode what each sibling's own
`.claude-plugin/marketplace.json` already declares, and rot). For each
present `repos.*` registry entry:
  - search BOTH `<repo>/.claude-plugin/marketplace.json` and
    `<repo>/plugin/.claude-plugin/marketplace.json` (example-game-workbench-repo's
    manifest is nested at the latter — a root-only scan silently misses it);
  - iterate `plugins[]` (one manifest can ship multiple plugins, e.g.
    example-game-repo/example-game-repo-control/game-dev);
  - key = `plugins[i].name + "@" + manifest.name` — **never**
    `install.enabled_plugins_key` (that field is the bare plugin name with
    no `@marketplace` suffix and produces an unresolvable key);
  - a malformed or absent manifest skips that ONE sibling with a stderr
    warning and continues — one bad sibling must never dark the whole run.

Merge is against the EFFECTIVE MERGED VIEW Claude Code actually evaluates
(committed `settings.json` UNION `settings.local.json`, Local > User): a key
is only seeded when it is absent from BOTH files. An explicit `true`/`false`
in either file always wins — this seeder never overwrites, and only ever
writes `true` (never `false`; disabling absent siblings was the dead
`platform-localize.sh` SessionStart hook's job, de-wired 2026-07-15).

No coordinator self-entry is ever seeded (`coordinator@coordinator-claude`)
— the inline install loads coordinator live via `--plugin-dir`, not through
a marketplace, so there is nothing to enable. In practice this falls out of
the two-location manifest search never resolving coordinator's own manifest
(nested under `coordinator/.claude-plugin/`, not root or `plugin/`), but the
marketplace-name check below is explicit belt-and-suspenders.

Negative-spec: does NOT write committed `settings.json` (leaks
machine-specific enablement fleet-wide — the `ecc81fb1c` precedent). Only
`settings.local.json` (gitignored, per-machine) is ever written.
Negative-spec: does NOT import `_machine_local.py` in-process (the
dual-identity anti-pattern, `docs/wiki/dual-identity-module-hazard.md`) —
`registry.local.toml` is read directly here with stdlib `tomllib`, which is
a plain file read, not a resolution-layer / write-path import.
Negative-spec: does NOT resurrect `platform-localize.sh` — this reuses the
merge *idiom* (codex / claude-klabauter's shipped `seed_enabled_plugins.py` shape),
not the file.

Spec backlink: docs/plans/2026-07-16-seed-marketplace-enabledplugins-at-install.md
  § D1 (C1) — AC1, AC2, AC3, AC4, AC5. § D4 (C6) — AC9 (registration).
Twin: claude-klabauter's shipped `scripts/seed_enabled_plugins.py` (f4e165e9)
  — same shape, differs only in TARGET (settings.local.json here, not
  settings.json) and SCOPE (all detected siblings here, not just claude-klabauter).

D4 (registration, the Director of Engineering F1's PM-ratified co-scope): enablement alone
(`enabledPlugins[<plugin>@<marketplace>] = true`) is inert on a genuinely
fresh box until the `<marketplace>` name is actually REGISTERED — Claude
Code resolves that key only once `extraKnownMarketplaces` (in
`settings.local.json`) and `~/.claude/plugins/known_marketplaces.json` (the
file Claude Code itself reads at marketplace-resolution time, bug #51806)
both carry a `directory`-source entry pointing at a real, manifest-bearing
directory. This module writes both, sharing D1's enumeration (same present-
sibling walk, same skip-with-warn-on-malformed discipline) — for each
present, manifest-bearing sibling it derives ONE registration entry keyed by
`manifest.name` (the marketplace name, same value used in D1's `@marketplace`
key suffix).

EXECUTOR DERISKING NOTE (resolved, disk-verified this session): the
registered directory-source `path` is the REPOS.* DEV CHECKOUT's
manifest-bearing directory (repo root, or `repo/plugin` for example-game-repo's
nested manifest — the same directory `_discover_manifest()` already found
for D1) — NOT the `~/.claude/plugins/<name>` marketplace clone. Rationale:
on a genuinely fresh box `~/.claude/plugins/<name>` does not exist yet
(nothing has ever been installed there) — registering a directory-source
`path` that doesn't exist would leave the marketplace exactly as dark as
before. Empirical check on this Mac (`~/.claude/settings.local.json` +
`~/.claude/plugins/known_marketplaces.json`) shows `claude-klabauter`'s
registered `path`/`installLocation` (`~/.claude/plugins/claude-klabauter`) is
itself a symlink BACK to its `repos.*` checkout (`/Users/example-operator/X/
Claude-klabauter`) — i.e. the real, pre-existing, manifest-bearing directory
is the checkout; `~/.claude/plugins/<name>` is, at best, downstream of it.
Pointing registration directly at the checkout is the fresh-box-correct
choice; it also matches D1's own manifest-discovery output 1:1, so no new
path-resolution logic is needed beyond what `_discover_manifest()` already
returns.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import tempfile
from datetime import datetime, timezone

if sys.version_info < (3, 11):
    print(
        "seed-marketplace-enabledplugins: requires Python 3.11+ for stdlib"
        " tomllib; upgrade Python.",
        file=sys.stderr,
    )
    sys.exit(1)

import tomllib  # stdlib, 3.11+

# coordinator_core is engine-owned (claude-klabauter), not on sys.path by default for a
# coordinator/bin script (DoE-side) — resolve this script's own co-located
# CLAUDE_KLABAUTER_ROOT (self-location-first, never a machine-local registry lookup for
# a checkout this script already lives inside) rather than importing
# coordinator_core.machine_resolver/_machine_local in-process, per this
# module's existing negative-spec above (dual-identity anti-pattern).
_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import resolve_colocated_claude_klabauter_root  # noqa: E402

_CLAUDE_KLABAUTER_ROOT = resolve_colocated_claude_klabauter_root(__file__)
if _CLAUDE_KLABAUTER_ROOT not in sys.path:
    sys.path.insert(0, _CLAUDE_KLABAUTER_ROOT)
from coordinator_core.install.write_surface import (  # noqa: E402
    ShapedClause,
    WriteSurfaceDeclaration,
    WriteSurfaceEntry,
)

# Marketplace name never seeded as an enabledPlugins key — the inline install
# loads coordinator live via --plugin-dir, so it has no marketplace entry to
# enable. See module docstring "No coordinator self-entry" above.
_COORDINATOR_MARKETPLACE_NAME = "coordinator-claude"

# Subpaths (relative to a sibling repo root) searched for a marketplace
# manifest, in order. "" = repo root; "plugin" = example-game-workbench-repo's
# nested location (the Director of Engineering F2, disk-verified).
_MANIFEST_SUBPATHS = ("", "plugin")

# structured-file-key surface constants — read by WRITE_SURFACE below so the
# declaration and the writer share one spelling of each key/filename rather
# than the declaration restating a literal.
_ENABLED_PLUGINS_KEY = "enabledPlugins"
_EXTRA_KNOWN_MARKETPLACES_KEY = "extraKnownMarketplaces"
_SETTINGS_LOCAL_FILENAME = "settings.local.json"
_KNOWN_MARKETPLACES_FILENAME = "known_marketplaces.json"

_DISCOVERED_BY = "_read_repos_registry -> _enumerate_present_plugin_keys"
"""Names the one shared discovery chain that feeds all three surfaces below:
a read over `registry.toml`/`registry.local.toml` (`_read_repos_registry`)
producing the present-sibling set, then a per-sibling
`.claude-plugin/marketplace.json` read (`_enumerate_present_plugin_keys`,
which also derives both the D1 enabledPlugins keys and the D4 marketplace-
registration entries in one walk). Both functions run every time; neither
alone is the whole mechanism."""

WRITE_SURFACE = WriteSurfaceDeclaration(
    writer_id="seed-marketplace-enabledplugins",
    # Review: coordinator:code-reviewer — bare filename, not a fake dotted
    # path: `write_surface_manifest._dotted_module_path` returns None for
    # any hyphenated segment and falls back to file-location loading, so
    # this is never a real importable path; matches the sibling convention
    # in setup-github-auth-1password.py.
    source_module="seed-marketplace-enabledplugins",
    clauses=(
        # D1a: settings.local.json["enabledPlugins"][<plugin>@<marketplace>].
        # A merge into a config file this writer does not own outright — an
        # existing true/false anywhere always wins (see module docstring) —
        # never an overwrite of the whole file or the whole key.
        ShapedClause(
            discovered_by=_DISCOVERED_BY,
            entry_template=WriteSurfaceEntry(
                kind="structured-file-key",
                path=_SETTINGS_LOCAL_FILENAME,
                key=f"{_ENABLED_PLUGINS_KEY}.<plugin>@<marketplace>",
            ),
        ),
        # D1b/D4a: settings.local.json["extraKnownMarketplaces"][<marketplace>].
        # Same file as above, DIFFERENT key — kept as its own clause so a
        # precise uninstall can distinguish the two keys within one file.
        ShapedClause(
            discovered_by=_DISCOVERED_BY,
            entry_template=WriteSurfaceEntry(
                kind="structured-file-key",
                path=_SETTINGS_LOCAL_FILENAME,
                key=f"{_EXTRA_KNOWN_MARKETPLACES_KEY}.<marketplace>",
            ),
        ),
        # D4b: known_marketplaces.json's own top-level entries, keyed by
        # marketplace name — a DIFFERENT FILE from the two clauses above,
        # fed by the same discovery chain (the Director of Engineering F1's co-scoping: D1 and D4
        # share one present-sibling walk, not one write target).
        ShapedClause(
            discovered_by=_DISCOVERED_BY,
            entry_template=WriteSurfaceEntry(
                kind="structured-file-key",
                path=_KNOWN_MARKETPLACES_FILENAME,
                key="<marketplace>",
            ),
        ),
    ),
)
"""Which `<plugin>@<marketplace>` keys and `<marketplace>` registrations get
seeded is entirely machine-dependent (whatever `_DISCOVERED_BY`'s chain finds
checked out on THIS box) — never enumerate today's observed plugin/
marketplace names here (see module docstring D1/D4 sections). All three
entries are merges into a config file this writer does not own outright
(`structured-file-key`, not `file-path`): `enabledPlugins`/
`extraKnownMarketplaces` merge into one shared `settings.local.json` under
two distinct keys, and `known_marketplaces.json`'s top-level entries merge
into a second, separate file. Modelled as three clauses (one per file/key
pair) rather than one collapsed clause so an uninstall can still tell "this
key in this file" apart from its file/key-sharing siblings."""


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def _settings_home() -> pathlib.Path:
    """Resolve the coordinator settings-home root.

    Precedence: COORDINATOR_SETTINGS_HOME (explicit override) ->
    ${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings. Inline mirror of
    _machine_local.py::_settings_home() — a plain env-var/path computation,
    not an in-process import (see module docstring negative-spec).
    """
    override = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if override:
        return pathlib.Path(override)
    home = os.environ.get("CLAUDE_HOME") or str(pathlib.Path.home())
    return pathlib.Path(home) / ".coordinator-claude-settings"


def _registry_dir(explicit: str | None) -> pathlib.Path:
    """Resolve the machine-local registry directory.

    Precedence: --registry-dir CLI arg (test isolation) ->
    MACHINE_LOCAL_REGISTRY_DIR env var (same override machine-local's own
    reader honors) -> <settings-home>/machine-local.
    """
    if explicit:
        return pathlib.Path(explicit)
    override = os.environ.get("MACHINE_LOCAL_REGISTRY_DIR")
    if override:
        return pathlib.Path(override)
    return _settings_home() / "machine-local"


def _resolve_settings_local_path(explicit: str | None) -> pathlib.Path:
    """Resolve settings.local.json — the ONLY file this seeder ever writes.

    Precedence: the --settings-path CLI arg, falling back to
    `settings.local.json` under CLAUDE_CONFIG_DIR, falling back to
    `.claude/settings.local.json` under CLAUDE_HOME or, absent that, the
    platform home directory (USERPROFILE on Windows, HOME or the passwd entry
    on POSIX).
    """
    if explicit:
        return pathlib.Path(explicit)
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    if config_dir:
        return pathlib.Path(config_dir) / _SETTINGS_LOCAL_FILENAME
    home = os.environ.get("CLAUDE_HOME") or str(pathlib.Path.home())
    return pathlib.Path(home) / ".claude" / _SETTINGS_LOCAL_FILENAME


def _resolve_committed_settings_path(
    explicit: str | None, local_path: pathlib.Path
) -> pathlib.Path:
    """Resolve the committed settings.json read for the effective-merged-view
    clobber check (the Director of Engineering F3). Defaults to the sibling settings.json next to
    the resolved settings.local.json — never written, only read.
    """
    if explicit:
        return pathlib.Path(explicit)
    return local_path.parent / "settings.json"


def _resolve_known_marketplaces_path(
    explicit: str | None, local_path: pathlib.Path
) -> pathlib.Path:
    """Resolve known_marketplaces.json — D4's second write target.

    Precedence: --known-marketplaces-path CLI arg (test isolation) ->
    <claude-home>/plugins/known_marketplaces.json, where <claude-home> is
    settings.local.json's own parent directory (settings.local.json lives
    directly at <claude-home>/settings.local.json, so this is the sibling
    `plugins/` dir Claude Code itself reads known_marketplaces.json from —
    bug #51806).
    """
    if explicit:
        return pathlib.Path(explicit)
    return local_path.parent / "plugins" / _KNOWN_MARKETPLACES_FILENAME


# ---------------------------------------------------------------------------
# Registry enumeration
# ---------------------------------------------------------------------------


def _flatten_repos(data: dict) -> dict[str, str]:
    """Extract `repos.*` declarations from one parsed TOML document, in
    either write form: a nested `[repos]` table, or the flat quoted-dotted-key
    form (`"repos.foo" = "..."`) `machine-local set` writes. Both are valid
    registry shapes; a value from either form for the same key is returned
    (nested does not clobber flat or vice versa within one file — collisions
    within a single well-formed registry file are not expected)."""
    repos: dict[str, str] = {}
    nested = data.get("repos", {})
    if isinstance(nested, dict):
        for k, v in nested.items():
            if isinstance(v, str):
                repos[k] = v
    for key, value in data.items():
        if isinstance(key, str) and key.startswith("repos.") and isinstance(value, str):
            repos[key[len("repos."):]] = value
    return repos


def _read_repos_registry(registry_dir: pathlib.Path) -> dict[str, str]:
    """Read every `repos.*` entry from the settings-home registry.

    Returns {slug: path} for each non-empty string-valued repos.* key (e.g.
    "project_rag" -> "/Users/x/X/project-rag"), merging `registry.toml`
    (tracked baseline) with `registry.local.toml` (per-machine override) —
    `.local` wins on collision, and an empty-string declaration in either
    file is treated as NOT FOUND (never inserted, never overwrites a real
    value from the other file). Neither file present -> empty dict (nothing
    checked out yet is not an error). Malformed TOML in either present file
    fails loud — an unparseable registry means enumeration can't be trusted,
    so no writes happen either (see main()).

    Negative-spec: this used to read ONLY `registry.local.toml` (never
    falling through to the tracked `registry.toml`) via a flat-dotted-key-only
    scan (missing a nested `[repos]` table declaration entirely), with no
    empty-string-is-a-miss handling. Do not reintroduce a single-file,
    single-form read here. `coordinator_core.machine_resolver.registry_get`
    is deliberately NOT used for this multi-key enumeration (this file reads
    a whole `repos.*` prefix, not one key, and — per this module's own
    negative-spec above — never imports an in-process registry-reader module,
    since it must also run before coordinator_core is necessarily installed
    on a fresh machine at `coordinator:install` time); this function
    reimplements the same registry.local.toml-before-registry.toml,
    empty-is-a-miss contract inline instead.
    """
    merged: dict[str, str] = {}
    for fname in ("registry.toml", "registry.local.toml"):  # tracked first; .local wins on collision
        path = registry_dir / fname
        if not path.is_file():
            continue
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except tomllib.TOMLDecodeError as exc:
            print(
                f"ERROR: malformed {fname} ({exc}) at {path} —"
                " refusing to enumerate present siblings.",
                file=sys.stderr,
            )
            sys.exit(1)
        for slug, value in _flatten_repos(data).items():
            if value:
                merged[slug] = value
    return merged


def _discover_manifest(repo_dir: pathlib.Path) -> pathlib.Path | None:
    """Return the first marketplace.json found under repo_dir, checking root
    then plugin/ (the Director of Engineering F2 — example-game-workbench-repo's manifest is nested)."""
    for sub in _MANIFEST_SUBPATHS:
        base = repo_dir / sub if sub else repo_dir
        candidate = base / ".claude-plugin" / "marketplace.json"
        if candidate.is_file():
            return candidate
    return None


def _enumerate_present_plugin_keys(
    repos: dict[str, str],
) -> tuple[list[str], dict[str, pathlib.Path], list[str]]:
    """Derive enabledPlugins keys AND marketplace-registration entries for
    every present, manifest-bearing sibling (D1 + D4 share this one walk —
    the Director of Engineering F1's co-scoping note: "likely the same script doing both writes in
    one pass, since they are near-twins").

    Returns (keys, marketplaces, warnings):
      - keys: one `plugin@marketplace` string per plugins[] entry, per
        manifest (D1, unchanged shape from C1).
      - marketplaces: {marketplace_name: manifest_dir} — one entry per
        present sibling's marketplace (D4). manifest_dir is the directory
        directly containing `.claude-plugin/` (repo root or `repo/plugin`,
        per D1's multi-location resolution) — see module docstring
        "EXECUTOR DERISKING NOTE" for why this is the repos.* checkout
        directory, not the `~/.claude/plugins/<name>` marketplace clone.
      - warnings: shared skip-with-warn-on-malformed discipline (D1 step 1
        negative-spec: one bad sibling must never dark every other sibling
        or its registration).
    """
    keys: list[str] = []
    marketplaces: dict[str, pathlib.Path] = {}
    warnings: list[str] = []
    seen_dirs: set[str] = set()

    for slug in sorted(repos):
        repo_path = repos[slug]
        repo_dir = pathlib.Path(repo_path)
        if not repo_dir.is_dir():
            continue  # registered but not checked out on this machine

        resolved = str(repo_dir.resolve())
        if resolved in seen_dirs:
            continue  # two registry aliases pointing at the same checkout
        seen_dirs.add(resolved)

        manifest_path = _discover_manifest(repo_dir)
        if manifest_path is None:
            warnings.append(
                f"skip '{slug}' ({repo_dir}): no discoverable"
                " .claude-plugin/marketplace.json (checked repo root and"
                " plugin/)"
            )
            continue

        try:
            manifest_raw = manifest_path.read_text(encoding="utf-8")
            manifest = json.loads(manifest_raw)
        except (json.JSONDecodeError, OSError) as exc:
            warnings.append(f"skip '{slug}' ({manifest_path}): malformed manifest ({exc})")
            continue

        if not isinstance(manifest, dict):
            warnings.append(
                f"skip '{slug}' ({manifest_path}): manifest top-level value is"
                f" {type(manifest).__name__}, expected object"
            )
            continue

        marketplace_name = manifest.get("name")
        if not isinstance(marketplace_name, str) or not marketplace_name:
            warnings.append(f"skip '{slug}' ({manifest_path}): manifest missing 'name'")
            continue

        if marketplace_name == _COORDINATOR_MARKETPLACE_NAME:
            continue  # no coordinator self-entry — see module docstring

        # D4: manifest_path = <manifest_dir>/.claude-plugin/marketplace.json
        # -- manifest_dir is the directory _discover_manifest() found
        # (repo root or repo/plugin), i.e. the registration path.
        marketplaces.setdefault(marketplace_name, manifest_path.parent.parent)

        plugins = manifest.get("plugins")
        if not isinstance(plugins, list) or not plugins:
            warnings.append(
                f"skip '{slug}' ({manifest_path}): manifest missing non-empty"
                " 'plugins' array"
            )
            continue

        for entry in plugins:
            if not isinstance(entry, dict):
                warnings.append(
                    f"skip malformed plugin entry in {manifest_path}"
                    f" (expected object, got {type(entry).__name__})"
                )
                continue
            plugin_name = entry.get("name")
            if not isinstance(plugin_name, str) or not plugin_name:
                warnings.append(
                    f"skip malformed plugin entry in {manifest_path}"
                    " (missing 'name')"
                )
                continue
            # Deliberately NOT entry.get("install", {}).get("enabled_plugins_key")
            # -- that field is the bare plugin name with no @marketplace suffix
            # and produces an unresolvable key (the Director of Engineering F2 trap).
            keys.append(f"{plugin_name}@{marketplace_name}")

    return keys, marketplaces, warnings


# ---------------------------------------------------------------------------
# settings.local.json / settings.json read + merge
# ---------------------------------------------------------------------------


def _read_settings_dict(path: pathlib.Path) -> tuple[dict | None, str | None]:
    """Read a settings JSON file for the effective-merged-view check.

    Returns (data, None) on success — data is {} when the file is absent
    (fine, not an error). Returns (None, error_message) on malformed JSON,
    a non-object top level, or a non-dict enabledPlugins — the read-fail-loud
    integrity contract (claude-klabauter's shape): never overwrite a file we can't
    fully trust the shape of.
    """
    if not path.is_file():
        return {}, None
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (json.JSONDecodeError, OSError) as exc:
        return None, f"{path} malformed ({exc})"
    if not isinstance(data, dict):
        return (
            None,
            f"{path} top-level value is {type(data).__name__}, expected object",
        )
    enabled = data.get(_ENABLED_PLUGINS_KEY, {})
    if not isinstance(enabled, dict):
        return (
            None,
            f"{path}: {_ENABLED_PLUGINS_KEY} is present but not an object"
            f" (got {type(enabled).__name__})",
        )
    extra_marketplaces = data.get(_EXTRA_KNOWN_MARKETPLACES_KEY, {})
    if not isinstance(extra_marketplaces, dict):
        return (
            None,
            f"{path}: {_EXTRA_KNOWN_MARKETPLACES_KEY} is present but not an object"
            f" (got {type(extra_marketplaces).__name__})",
        )
    return data, None


def _read_marketplaces_dict(path: pathlib.Path) -> tuple[dict | None, str | None]:
    """Read known_marketplaces.json (D4's second write target) for the
    merge-never-clobber check.

    Flat {marketplace_name: {...}} shape at the top level (no wrapper key,
    unlike settings.local.json's enabledPlugins/extraKnownMarketplaces).
    Returns ({}, None) when the file is absent (fine, not an error — a
    genuinely fresh box has no known_marketplaces.json yet). Returns
    (None, error) on malformed JSON or a non-object top level — same
    read-fail-loud integrity contract as settings.local.json: never
    overwrite a file whose shape can't be trusted.
    """
    if not path.is_file():
        return {}, None
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (json.JSONDecodeError, OSError) as exc:
        return None, f"{path} malformed ({exc})"
    if not isinstance(data, dict):
        return (
            None,
            f"{path} top-level value is {type(data).__name__}, expected object",
        )
    return data, None


def _atomic_write(target: pathlib.Path, data: dict) -> None:
    """Write data to target atomically via a sibling temp file.

    Mirrors claude-klabauter's shipped seed_enabled_plugins.py::_atomic_write: resolve()
    before the swap (symlinked settings.local.json is written through, not
    replaced), preserve the destination's existing file mode across the swap
    (mkstemp always creates 0600), mkdir(parents=True) first (settings dir
    may not exist yet on a genuinely fresh box).
    """
    target = target.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".settings.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", newline="\n") as f:
            f.write(json.dumps(data, indent=2) + "\n")
        if target.exists():
            os.chmod(tmp, os.stat(target).st_mode)
        os.replace(tmp, target)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _now_iso8601_millis() -> str:
    """Real install-time UTC timestamp, millisecond precision, `Z` suffix —
    matches the shape Claude Code itself writes to known_marketplaces.json
    (empirically verified: `"2026-07-16T11:42:39.815Z"`). Not a
    workflow-script constraint (D4 step 5) — a live wall-clock read each
    time this module runs.
    """
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def _directory_source_entry(manifest_dir: pathlib.Path) -> dict:
    """Build the `{"source": {"source": "directory", "path": ...}}` shape
    shared by extraKnownMarketplaces and known_marketplaces.json entries
    (D4 steps 1-2). Path is absolute — resolve() so a relative repos.*
    registry entry doesn't leak a cwd-relative path into settings."""
    return {"source": {"source": "directory", "path": str(manifest_dir.resolve())}}


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _run(
    *,
    registry_dir: pathlib.Path,
    local_path: pathlib.Path,
    committed_path: pathlib.Path,
    known_marketplaces_path: pathlib.Path,
    check_only: bool,
) -> int:
    repos = _read_repos_registry(registry_dir)
    present_keys, present_marketplaces, warnings = _enumerate_present_plugin_keys(repos)
    for warning in warnings:
        print(f"seed-marketplace-enabledplugins: {warning}", file=sys.stderr)

    committed_data, err = _read_settings_dict(committed_path)
    if err:
        print(f"ERROR: {err} — refusing to write.", file=sys.stderr)
        return 1
    local_data, err = _read_settings_dict(local_path)
    if err:
        print(f"ERROR: {err} — refusing to write.", file=sys.stderr)
        return 1
    known_marketplaces_data, err = _read_marketplaces_dict(known_marketplaces_path)
    if err:
        print(f"ERROR: {err} — refusing to write.", file=sys.stderr)
        return 1

    committed_enabled = committed_data.get(_ENABLED_PLUGINS_KEY, {})
    local_enabled = local_data.get(_ENABLED_PLUGINS_KEY, {})
    local_extra_marketplaces = local_data.get(_EXTRA_KNOWN_MARKETPLACES_KEY, {})

    # D1 — Effective-merged-view merge-never-clobber (the Director of Engineering F3): seed a key
    # only when it is absent from BOTH files. An explicit true/false
    # anywhere wins and this seeder never touches it.
    keys_to_seed = []
    for key in dict.fromkeys(present_keys):  # order-preserving dedup
        if key in committed_enabled or key in local_enabled:
            continue
        keys_to_seed.append(key)

    # D4 — merge-never-clobber against the TARGET file only (the Director of Engineering F3's
    # discipline applied here too, per plan D4 step 3: "absent from the
    # target file", not the effective-merged-view — extraKnownMarketplaces/
    # known_marketplaces.json don't carry the true/false disable-polarity
    # concern that motivated the effective-merged-view read for D1).
    extra_marketplaces_to_seed = {
        name: manifest_dir
        for name, manifest_dir in present_marketplaces.items()
        if name not in local_extra_marketplaces
    }
    known_marketplaces_to_seed = {
        name: manifest_dir
        for name, manifest_dir in present_marketplaces.items()
        if name not in known_marketplaces_data
    }

    if not keys_to_seed and not extra_marketplaces_to_seed and not known_marketplaces_to_seed:
        print("seed-marketplace-enabledplugins: nothing to seed (already covered)")
        return 0

    if check_only:
        if keys_to_seed:
            print(
                "seed-marketplace-enabledplugins: would seed enabledPlugins"
                " (check-only, no write): " + ", ".join(keys_to_seed)
            )
        if extra_marketplaces_to_seed:
            print(
                "seed-marketplace-enabledplugins: would seed extraKnownMarketplaces"
                " (check-only, no write): " + ", ".join(sorted(extra_marketplaces_to_seed))
            )
        if known_marketplaces_to_seed:
            print(
                "seed-marketplace-enabledplugins: would seed known_marketplaces.json"
                " (check-only, no write): " + ", ".join(sorted(known_marketplaces_to_seed))
            )
        return 0

    # Review: code-reviewer — both payloads share one atomic write to local_path; the outer
    # `if` gates whether a write happens at all, not two independently-gateable writes.
    if keys_to_seed or extra_marketplaces_to_seed:
        if keys_to_seed:
            local_data.setdefault(_ENABLED_PLUGINS_KEY, {})
            for key in keys_to_seed:
                local_data[_ENABLED_PLUGINS_KEY][key] = True
        if extra_marketplaces_to_seed:
            local_data.setdefault(_EXTRA_KNOWN_MARKETPLACES_KEY, {})
            for name, manifest_dir in extra_marketplaces_to_seed.items():
                local_data[_EXTRA_KNOWN_MARKETPLACES_KEY][name] = _directory_source_entry(
                    manifest_dir
                )
        _atomic_write(local_path, local_data)
        if keys_to_seed:
            print("seed-marketplace-enabledplugins: seeded enabledPlugins: " + ", ".join(keys_to_seed))
        if extra_marketplaces_to_seed:
            print(
                "seed-marketplace-enabledplugins: seeded extraKnownMarketplaces: "
                + ", ".join(sorted(extra_marketplaces_to_seed))
            )

    if known_marketplaces_to_seed:
        for name, manifest_dir in known_marketplaces_to_seed.items():
            resolved = str(manifest_dir.resolve())
            known_marketplaces_data[name] = {
                "source": {"source": "directory", "path": resolved},
                "installLocation": resolved,
                "lastUpdated": _now_iso8601_millis(),
            }
        _atomic_write(known_marketplaces_path, known_marketplaces_data)
        print(
            "seed-marketplace-enabledplugins: seeded known_marketplaces.json: "
            + ", ".join(sorted(known_marketplaces_to_seed))
        )

    return 0


def _check_only_requested(args: argparse.Namespace) -> bool:
    if args.check_only:
        return True
    env_val = os.environ.get("CHECK_ONLY", "").strip().lower()
    return env_val in ("1", "true", "yes")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Idempotently seed enabledPlugins[<plugin>@<marketplace>] = true"
            " into settings.local.json for every present, manifest-bearing"
            " marketplace-sibling repo."
        )
    )
    parser.add_argument(
        "--settings-path",
        default=None,
        help=(
            "Explicit settings.local.json path (used by tests). Default"
            " resolution: $CLAUDE_CONFIG_DIR/settings.local.json, falling"
            " back to ${CLAUDE_HOME:-$HOME}/.claude/settings.local.json."
        ),
    )
    parser.add_argument(
        "--committed-settings-path",
        default=None,
        help=(
            "Explicit committed settings.json path (used by tests, for the"
            " effective-merged-view clobber check). Default: the sibling"
            " settings.json next to the resolved settings.local.json."
        ),
    )
    parser.add_argument(
        "--registry-dir",
        default=None,
        help=(
            "Explicit machine-local registry directory (used by tests)."
            " Default: MACHINE_LOCAL_REGISTRY_DIR env var, falling back to"
            " <settings-home>/machine-local."
        ),
    )
    parser.add_argument(
        "--known-marketplaces-path",
        default=None,
        help=(
            "Explicit known_marketplaces.json path (used by tests, D4"
            " registration second write target). Default:"
            " <claude-home>/plugins/known_marketplaces.json, sibling to the"
            " resolved settings.local.json."
        ),
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Compute and report what would be seeded; write nothing.",
    )
    args = parser.parse_args()

    local_path = _resolve_settings_local_path(args.settings_path)
    committed_path = _resolve_committed_settings_path(
        args.committed_settings_path, local_path
    )
    known_marketplaces_path = _resolve_known_marketplaces_path(
        args.known_marketplaces_path, local_path
    )
    registry_dir = _registry_dir(args.registry_dir)
    check_only = _check_only_requested(args)

    rc = _run(
        registry_dir=registry_dir,
        local_path=local_path,
        committed_path=committed_path,
        known_marketplaces_path=known_marketplaces_path,
        check_only=check_only,
    )

    # install.md § 3.5c-2 contract row (Phase 7 status table): additive —
    # collapses that block's own status-derivation to a single forwarder
    # call over this script. `_run`'s own prints above carry the per-key
    # detail; this is just the terse row the table reads.
    if rc != 0:
        status = "failed"
    elif check_only:
        status = "would seed (check-only)"
    else:
        status = "seeded"
    print(f"marketplace_enabledplugins_seed: {status}")

    return rc


if __name__ == "__main__":
    sys.exit(main())
