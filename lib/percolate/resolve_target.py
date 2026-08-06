"""coordinator/lib/percolate/resolve_target.py — publish-target row resolver.

Native-Python port of `setup/lib/resolve-publish-target.sh`. Normalizes a single pipe-delimited
publish-target row to the absolute `name|mode|ABSsource|ABSdest[|native_slugs
[|allowlist]]` form the publish.sh main loop (and, downstream, claude-klabauter's
percolate preflight) consumes — so callers can import this resolver directly
instead of shelling out to bash.

Row shapes accepted (field 3, 0-indexed 2, decides the shape):
  Legacy          (field 3 does NOT start with `repo:` or `publish-mirror:`):
    name|mode|ABSsource|ABSdest[|native_slugs]                  — 4 or 5 fields, pass-through
  Portable repo:  (field 3 starts with `repo:`, backward-compat):
    name|mode|repo:<dest_key>|source_subdir|dest_subdir[|native_slugs]        — 5 or 6 fields
    DEST resolved via: machine-local get repos.<dest_key>
  Publish-mirror: (field 3 starts with `publish-mirror:`, primary mirror form):
    name|mode|publish-mirror:<key>|source_subdir|dest_subdir[|native_slugs[|allowlist]] — 5-7 fields
    DEST resolved EXCLUSIVELY via: machine-local get publish.mirrors.<key>.path
    NO repos.* read in this branch — structural class separation (D1/D2).

Return contract (mirrors the bash function's return codes 1:1 — see
`ResolveError.code`):
  0 (no exception) — success; the return value is the resolved stdout row.
  1 — machine-local CLI present but registry key unset (fail-loud, remediation
      in `ResolveError.message`).
  2 — malformed row (fail-loud, `ResolveError.message` set).
  3 — machine-local CLI absent (fall-through signal; `ResolveError.message`
      is empty, matching the bash no-message rc-3 contract).
  4 — machine-local CLI resolved and present, but the exec/invocation itself
      failed (transport error — e.g. Windows WinError 193 from attempting to
      CreateProcess an extensionless shebang script directly). Distinct from
      rc 1 on purpose: rc 1 means "the CLI ran fine and reported the key
      absent"; rc 4 means "the CLI could not be run at all", so the key may
      already be set correctly — telling the operator to (re)set it would be
      actively wrong. `ResolveError.message` carries the underlying OSError.

Spec backlink: docs/plans/2026-06-22-portable-registry-resolved-publish-targets.md
               § C1 (resolve-publish-target lib)
Port: docs/plans/2026-07-21-percolate-python-port.md (chunk C-W0).

Negative-spec: this module performs no top-level side effects and mutates no
global state — every call to `resolve_publish_row` is independent.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional
from coordinator_core.win_portability import is_executable


class ResolveError(Exception):
    """Raised by `resolve_publish_row` / `resolve_machine_local_bin` for a
    non-zero bash return code. `code` mirrors the bash exit code exactly
    (1/2/3); `message` is the diagnostic text the bash equivalent would have
    printed to stderr (empty string for rc 3, which is a silent fall-through
    signal in the bash original)."""

    def __init__(self, message: str, code: int):
        super().__init__(message)
        self.message = message
        self.code = code


def _default_meta_root() -> Path:
    """META_ROOT = the meta-repo root. `COORDINATOR_META_ROOT` env wins when
    set; otherwise derived from this file's own location. This module lives
    at coordinator/lib/percolate/resolve_target.py — one directory deeper
    than the bash original (setup/lib/resolve-publish-target.sh) — so the
    walk-up depth differs (parents[3] here vs. 3 `dirname` calls there) but
    both land on the same repo root."""
    env = os.environ.get("COORDINATOR_META_ROOT")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[3]


def _settings_home_dir() -> Path:
    """Resolve the coordinator settings home.

    Mirrors ``coordinator_core._settings_home.settings_home()``'s precedence
    (``COORDINATOR_SETTINGS_HOME`` when set, else ``.coordinator-claude-settings``
    under ``CLAUDE_HOME`` or the home directory)
    rather than importing it: this module is deliberately self-contained, since
    claude-klabauter-root resolution itself routes through the machine-local CLI this
    function helps locate.

    ``Path.home()`` is used for the home fallback because it honours
    ``USERPROFILE`` on Windows, where ``HOME`` is typically unset in native
    shells (PowerShell, cmd.exe). A bare ``os.environ["HOME"]`` would resolve
    empty there and silently produce a relative path.
    """
    override = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if override:
        return Path(override)
    claude_home = os.environ.get("CLAUDE_HOME")
    base = Path(claude_home) if claude_home else Path.home()
    return base / ".coordinator-claude-settings"


def resolve_machine_local_bin(root: Path) -> Optional[str]:
    """Locate the machine-local registry CLI. Rung order: `MACHINE_LOCAL_BIN`
    env var (SECURITY-validated) -> `<root>/bin/machine-local` -> `<root>/
    coordinator/bin/machine-local` -> `<settings-home>/bin/machine-local` ->
    `machine-local` on PATH.

    The settings-home rung exists because the `<root>`-relative rungs resolve
    only for callers whose root is a repo that vendors the CLI. `publish.py`
    passes the DoE clone, which vendors nothing under `coordinator/bin`, so
    every filesystem rung missed and resolution fell through to PATH — where
    the settings-home bin dir is not present on all platforms. That returned
    None, which the caller rendered as "registry key unset", pointing the
    operator at a key that was already set correctly and making percolation
    unusable.

    It is deliberately placed AFTER the `<root>`-relative rungs, not before:
    an explicit caller-supplied `root` is a stronger signal of intent than the
    ambient machine install, and tests that hand this function a sandboxed
    fake root must keep winning over the real machine's settings home. Putting
    it first leaked this machine's actual registry into those tests.

    Windows note: `machine-local` is delivered as an extensionless Python
    shebang script alongside a `machine-local.cmd` sibling
    (`coordinator/bin/gen-launcher-shim.py`'s generated launcher).
    `CreateProcess` cannot exec the extensionless file directly — it fails
    with `WinError 193 ("%1 is not a valid Win32 application")` — so on
    Windows each filesystem rung tries the `.cmd` sibling FIRST, matching the
    precedent in `coordinator/bin/lib/machine_local_resolve.py`
    (`windows_cmd_first_candidates`). `shutil.which` is PATHEXT-aware and
    already finds a `.cmd` on PATH correctly, so the PATH rung needs no
    change.

    Returns the resolved path string, or None if no rung resolved (bash rc 1).
    Raises ResolveError(code=2) if MACHINE_LOCAL_BIN fails SECURITY validation
    (not absolute, or contains '..' traversal) — bash rc 2, propagated fatal,
    never falls through to the filesystem rungs.
    """
    env_bin = os.environ.get("MACHINE_LOCAL_BIN")
    if env_bin:
        if not os.path.isabs(env_bin):
            raise ResolveError(
                f"resolve_machine_local_bin: SECURITY: MACHINE_LOCAL_BIN='{env_bin}' "
                "must be an absolute path — refusing to use it.",
                2,
            )
        normalized = env_bin.replace("\\", "/")
        if "/../" in normalized or normalized.endswith("/.."):
            raise ResolveError(
                f"resolve_machine_local_bin: SECURITY: MACHINE_LOCAL_BIN='{env_bin}' "
                "contains '..' traversal — refusing to use it.",
                2,
            )
        return env_bin

    rung2 = root / "bin" / "machine-local"
    rung3 = root / "coordinator" / "bin" / "machine-local"
    # The settings home is the canonical, machine-agnostic install location for
    # the CLI, so it is a rung in its own right rather than something only a
    # PATH lookup happens to find. Without it, resolution depends on which repo
    # `root` points at: when a caller passes the DoE clone (publish.py does),
    # neither <root>/bin nor <root>/coordinator/bin exists — DoE-claude tracks
    # no files under coordinator/bin — so every filesystem rung missed and
    # resolution fell through to PATH. The settings-home bin dir is NOT on PATH
    # on all platforms, so that fall-through returned None, which the caller
    # rendered as "registry key unset" and pointed the operator at a key that
    # was already set correctly. Percolation was unusable as a result.
    rung_settings_home = _settings_home_dir() / "bin" / "machine-local"

    if os.name == "nt":
        for rung in (rung2, rung3, rung_settings_home):
            cmd_sibling = rung.with_suffix(".cmd")
            if cmd_sibling.is_file():
                return str(cmd_sibling)
            if rung.is_file():
                return str(rung)
        found = shutil.which("machine-local")
        if found:
            return found
        return None

    if is_executable(rung2):
        return str(rung2)

    if is_executable(rung3):
        return str(rung3)

    if is_executable(rung_settings_home):
        return str(rung_settings_home)

    found = shutil.which("machine-local")
    if found:
        return found

    return None


def _machine_local_get(machine_local_bin: str, key: str) -> Optional[str]:
    """Invoke `<machine_local_bin> get <key>` directly (shebang-honoring exec).
    The bash original wrapped this in `${BASH:-bash} "$machine_local_bin"`
    because machine-local WAS a bash script; it is now a `#!/usr/bin/env
    python3` forwarder, and bash-wrapping it makes bash parse Python source —
    every key silently reads as unset. Returns stdout (stripped of the
    trailing newline) on success, None on any non-zero exit (key unset).

    Raises ResolveError(code=4) if the CLI could not be EXECUTED at all
    (`OSError` — e.g. Windows WinError 193 from CreateProcess-ing an
    extensionless shebang script). This is a distinct failure class from "key
    unset": conflating the two used to report a correctly-set registry key as
    unset, with remediation instructing the operator to re-set a key that was
    never the problem. See module docstring rc-4 for the full contract."""
    try:
        result = subprocess.run(
            [machine_local_bin, "get", key],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise ResolveError(
            f"resolve-publish-target: machine-local invocation failed — "
            f"could not execute '{machine_local_bin} get {key}': {exc}. "
            "This is a TRANSPORT failure (the CLI itself could not be run), "
            f"NOT an unset registry key — '{key}' may already be set "
            "correctly. On Windows this is typically WinError 193 from "
            "attempting to exec an extensionless shebang script directly; "
            "verify the resolved machine-local path is a `.cmd`/`.exe` "
            "sibling, not the bare shebang file.",
            4,
        ) from exc
    if result.returncode != 0:
        return None
    value = result.stdout.rstrip("\n")
    # An ABSENT key is reported as rc=0 with EMPTY stdout, not a non-zero exit.
    # Returning "" here would defeat every `is None` unset-check downstream: the
    # `repos.*` and `<root>/plugins/...` fallbacks would never fire, and an empty
    # base would be silently concatenated with the sigil's subpath — producing a
    # bare "\coordinator" that fails much later as "source path does not exist",
    # far from the missing key that caused it. Normalize empty to None so "unset"
    # has exactly one representation.
    return value or None


def _resolve_machine_local_or_raise(meta_root: Path) -> str:
    """Resolve the machine-local CLI.

    Two distinct failures, deliberately NOT collapsed:

    - Nothing resolves to a usable executable -> ResolveError(code=3) with an
      empty message, matching the bash no-message fall-through. This covers a
      genuinely absent path AND a broken symlink (a directory entry that
      exists while its target does not) — both fail `os.path.exists` the same
      way and land here.
    - The path EXISTS but is not executable -> ResolveError(code=4), the same
      TRANSPORT class `_machine_local_get` raises when exec itself fails.

    Reporting the second as code 3 is the "unreachable reads as unset" pathology
    that rc-4 exists to eliminate: a present-but-unrunnable CLI is a transport
    problem, and answering it with the unset-key framing sends the operator to
    re-set a key that was never wrong. On Windows the exec-bit check is
    meaningless (`os.access(..., X_OK)` is true for any existing file), so that
    platform reaches this failure later, inside `_machine_local_get`; on POSIX it
    is caught here. Same class, same code, whichever leg observes it.
    """
    machine_local_bin = resolve_machine_local_bin(meta_root)
    if machine_local_bin is None:
        machine_local_bin = str(meta_root / "bin" / "machine-local")
    if not is_executable(machine_local_bin):
        if os.path.exists(machine_local_bin):
            raise ResolveError(
                f"resolve-publish-target: machine-local at '{machine_local_bin}' "
                "exists but is not executable. This is a TRANSPORT failure (the "
                "CLI itself could not be run), NOT an unset registry key — the "
                "keys it would have read may already be set correctly. Restore "
                "the exec bit, or re-run /coordinator:setup (Phase 3).",
                4,
            )
        raise ResolveError("", 3)
    return machine_local_bin


def resolve_publish_row(raw_row: str, meta_root: Optional[Path] = None) -> str:
    """Normalize a single pipe-delimited publish-target row to the absolute
    `name|mode|ABSsource|ABSdest[|native_slugs[|allowlist]]` form.

    `meta_root` defaults to `_default_meta_root()` (COORDINATOR_META_ROOT env
    or this file's own repo-root-relative location); pass explicitly to pin
    it (mirrors the bash function reading `COORDINATOR_META_ROOT`/`BASH_SOURCE`
    fresh on every call).

    Raises ResolveError with `.code` in {1, 2, 3} on any of the bash
    function's non-zero-exit paths — see the module docstring's return
    contract.
    """
    # NOTE: Python's str.split("|") preserves trailing empty fields (unlike
    # bash's `IFS='|' read -ra`, which drops them) — the manual field-peel the
    # bash original performs is therefore unnecessary here; a plain split
    # already keeps a trailing empty dest_subdir intact.
    fields = raw_row.split("|")
    nfields = len(fields)
    field3 = fields[2] if nfields > 2 else ""

    if field3.startswith("publish-mirror:"):
        return _resolve_publish_mirror_row(raw_row, fields, nfields, field3, meta_root)

    if not field3.startswith("repo:"):
        # LEGACY ABSOLUTE PATH — pass through verbatim.
        if nfields < 4 or nfields > 5:
            raise ResolveError(
                f"resolve-publish-target: malformed legacy row (expected 4 or 5 fields, "
                f"got {nfields}): {raw_row}",
                2,
            )
        return raw_row

    return _resolve_repo_row(raw_row, fields, nfields, field3, meta_root)


def _resolve_repo_row(
    raw_row: str,
    fields: list[str],
    nfields: int,
    field3: str,
    meta_root: Optional[Path],
) -> str:
    """PORTABLE ROW (`repo:`) — retained for backward-compat. Resolves DEST
    via `repos.<dest_key>`.

    Deliberately NOT extended with allowlist/source_map support: this branch
    keeps its original 5-6 field guard and has never carried an allowlist.
    Only `_resolve_publish_mirror_row` (the `publish-mirror:` branch) gained
    `source_map` (§2 of the multi-source config surface) — do not "fix" that
    asymmetry by extending this function to match; it is scoped intentionally."""
    if nfields < 5 or nfields > 6:
        raise ResolveError(
            f"resolve-publish-target: malformed portable row (expected 5 or 6 fields, "
            f"got {nfields}): {raw_row}",
            2,
        )

    name = fields[0]
    mode = fields[1]
    source_subdir = fields[3]
    dest_subdir = fields[4]
    native_slugs = fields[5] if nfields == 6 else ""

    dest_key = field3[len("repo:") :]
    if not dest_key:
        raise ResolveError(
            f"resolve-publish-target: malformed portable row — empty repo key in field 3 "
            f"('repo:' alone): {raw_row}",
            2,
        )
    if not source_subdir:
        raise ResolveError(
            f"resolve-publish-target: malformed portable row — empty source_subdir "
            f"(field 4): {raw_row}",
            2,
        )

    root = meta_root if meta_root is not None else _default_meta_root()
    abs_source = str(root / source_subdir)

    machine_local_bin = _resolve_machine_local_or_raise(root)

    dest_root = _machine_local_get(machine_local_bin, f"repos.{dest_key}")
    if dest_root is None:
        raise ResolveError(
            f"resolve-publish-target: repos.{dest_key} is unset on this machine (must "
            "NOT be re-added — key was removed by migration to publish.mirrors.*; see "
            f"remediation below) — cannot resolve dest for target '{name}'.\n"
            f"  Remediation: machine-local set publish.mirrors.{dest_key}.path "
            "<absolute-path-to-the-publish-repo>",
            1,
        )

    abs_dest = dest_root if not dest_subdir else f"{dest_root}/{dest_subdir}"

    if native_slugs:
        return f"{name}|{mode}|{abs_source}|{abs_dest}|{native_slugs}"
    return f"{name}|{mode}|{abs_source}|{abs_dest}"


def _resolve_source_sigil(
    sigil: str, root: Path, machine_local_bin: str, *, strict: bool = False
) -> str:
    """Resolve one SOURCE-position sigil to an absolute path. `plugin-source:
    <key>[/subpath]` reads `plugin.mirrors.<key>.source_path` from the
    registry; anything else is the legacy meta-root-relative form. Shared by
    the row's primary field-4 source and by every root named in a
    `source_map` entry (§2) — the only two SOURCE-position call sites.
    `machine_local_bin` must already be resolved by the caller; this helper
    never re-resolves it, so it must be called with the SAME resolved value
    at every call site within one row.

    `strict` is the deliberate asymmetry between the two call sites, NOT
    something to "fix" into consistency:
      - strict=False (default) — the PRIMARY field-4 source. Unresolved
        `plugin.mirrors.<key>.source_path` falls back to
        `${meta_root}/plugins/<key>` with a stderr warning, exactly as
        before. Left untouched on purpose: every existing publish-targets
        row relies on this call site, and loosening or tightening it would
        change resolved output for rows that predate `source_map` entirely.
      - strict=True — a `source_map` (§2) entry only. Unresolved
        `plugin.mirrors.<key>.source_path` falls back to the ALREADY
        machine-local `repos.<key>` (underscore-normalized) key before
        failing; if that too is unset, raises ResolveError(code=1) instead
        of warning-and-falling-back to a path that may not exist. A
        source_map root silently resolving to a nonexistent tree is exactly
        the empty-source-directory mass-delete failure mode this field was
        introduced to prevent — a warning nobody reads is not a mitigation.
    """
    if sigil.startswith("plugin-source:"):
        ps_ref = sigil[len("plugin-source:") :]
        if "/" in ps_ref:
            ps_key, ps_subpath = ps_ref.split("/", 1)
            ps_subpath = "/" + ps_subpath
        else:
            ps_key, ps_subpath = ps_ref, ""

        if ".." in ps_subpath:
            raise ResolveError(
                f"resolve-publish-target: rejected unsafe plugin-source subpath in '{sigil}'",
                2,
            )

        plugin_mirror_key = f"plugin.mirrors.{ps_key}.source_path"
        ps_base = _machine_local_get(machine_local_bin, plugin_mirror_key)

        if strict:
            if ps_base is None:
                # repos.* keys are underscore-normalized fleet-wide
                # (repos.doe_claude, repos.claude_klabauter, …) while
                # plugin-source sigils use the repo's hyphenated directory
                # name (plugin-source:claude-klabauter) — normalize before
                # the lookup, not the sigil itself.
                repos_key = f"repos.{ps_key.replace('-', '_')}"
                ps_base = _machine_local_get(machine_local_bin, repos_key)
                if ps_base is None:
                    raise ResolveError(
                        f"resolve-publish-target: unresolvable source_map sigil "
                        f"'{sigil}' — neither {plugin_mirror_key} nor {repos_key} "
                        "is set on this machine.\n"
                        f"  Remediation: machine-local set {repos_key} "
                        "<absolute-path-to-the-repo>\n"
                        f"  (or, to pin a mirror distinct from repos.*: machine-local "
                        f"set {plugin_mirror_key} <absolute-path>)",
                        1,
                    )
            return f"{ps_base}{ps_subpath}"

        if ps_base is None:
            ps_base = str(root / "plugins" / ps_key)
            print(
                f"resolve-publish-target: {plugin_mirror_key} unset — "
                f"falling back to {ps_base}",
                file=sys.stderr,
            )
            print(
                f"  Remediation: machine-local set {plugin_mirror_key} "
                "<absolute-path-to-doe-coordinator>",
                file=sys.stderr,
            )
        return f"{ps_base}{ps_subpath}"

    return str(root / sigil)


def _resolve_publish_mirror_row(
    raw_row: str,
    fields: list[str],
    nfields: int,
    field3: str,
    meta_root: Optional[Path],
) -> str:
    """`publish-mirror:<key>` branch — primary mirror form. Resolves DEST
    EXCLUSIVELY via `publish.mirrors.<key>.path`; no `repos.*` read (D1/D2
    structural class separation)."""
    if nfields < 5 or nfields > 8:
        raise ResolveError(
            f"resolve-publish-target: malformed publish-mirror row (expected 5–8 "
            f"fields, got {nfields}): {raw_row}",
            2,
        )

    name = fields[0]
    mode = fields[1]
    source_subdir = fields[3]
    dest_subdir = fields[4]
    native_slugs = fields[5] if nfields >= 6 else ""
    allowlist = fields[6] if nfields >= 7 else ""
    source_map = fields[7] if nfields == 8 else ""

    key = field3[len("publish-mirror:") :]
    if not key:
        raise ResolveError(
            "resolve-publish-target: malformed publish-mirror row — empty key in field "
            f"3 ('publish-mirror:' alone): {raw_row}",
            2,
        )
    if not source_subdir:
        raise ResolveError(
            "resolve-publish-target: malformed publish-mirror row — empty source_subdir "
            f"(field 4): {raw_row}",
            2,
        )

    root = meta_root if meta_root is not None else _default_meta_root()

    # Resolved ONCE, before every SOURCE- and DEST-position sigil lookup
    # below (primary source, each source_map root, and dest) — a prior
    # version of this function re-resolved it a second time ahead of the
    # dest lookup even though the primary-source branch already needed it.
    machine_local_bin = _resolve_machine_local_or_raise(root)

    abs_source = _resolve_source_sigil(source_subdir, root, machine_local_bin)

    dest_root = _machine_local_get(machine_local_bin, f"publish.mirrors.{key}.path")
    if dest_root is None:
        raise ResolveError(
            f"resolve-publish-target: publish.mirrors.{key}.path is unset on this "
            f"machine — cannot resolve dest for target '{name}'.\n"
            f"  Remediation: machine-local set publish.mirrors.{key}.path "
            "<absolute-path-to-the-publish-repo>",
            1,
        )

    abs_dest = dest_root if not dest_subdir else f"{dest_root}/{dest_subdir}"

    # source_map: `<source-sigil>=<csv-of-entries>` segments joined by `;`.
    # Each sigil resolves through the SAME helper (and the same
    # machine_local_bin) as the primary source; the CSV of allowlist-entry
    # names passes through unresolved — publish.py maps entries -> roots.
    resolved_source_map = ""
    if source_map:
        resolved_segments = []
        for segment in source_map.split(";"):
            if not segment:
                continue
            sig, sep, csv = segment.partition("=")
            if not sep or not sig or not csv:
                raise ResolveError(
                    f"resolve-publish-target: malformed source_map segment '{segment}' "
                    f"in row: {raw_row}",
                    2,
                )
            abs_root = _resolve_source_sigil(sig, root, machine_local_bin, strict=True)
            resolved_segments.append(f"{abs_root}={csv}")
        resolved_source_map = ";".join(resolved_segments)

    out_fields = [name, mode, abs_source, abs_dest, native_slugs, allowlist, resolved_source_map]
    while out_fields and out_fields[-1] == "":
        out_fields.pop()
    return "|".join(out_fields)
