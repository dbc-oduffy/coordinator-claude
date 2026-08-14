"""coordinator_data_root — shared resolver for coordinator DATA directories
(snippets/, schemas/, templates/, docs/) across the split-repo layout.

The 2026-07-22 executable-surface migration moved ~1100 executables from
DoE-claude/coordinator/{bin,lib,scripts,tests} into the engine repo's coordinator/,
but their sibling DATA dirs — schemas/, snippets/, templates/, docs/, hooks/ —
correctly stayed in DoE-claude (DR-047: contract/data lives with DoE, engine
with the engine repo). Any migrated script that resolved a sibling data dir via a bare
`__file__`-relative walk (the old `bin/../<data-dir>` shape) is now broken: that
walk lands inside the engine repo, where the data dir no longer exists.

`coordinator_registry.py`'s `_MANIFEST_PATH` bootstrap (see that module, fix
commit 4f74656c) was the first caller to hit this and fixed itself inline with
a two-rung chain. This module extracts that SAME two-rung shape into one
shared, importable resolver so the five (now six, counting the fixed original)
remaining callers do not each hand-roll their own copy — six independent
copies of the resolution chain is exactly the drift that caused this bug.

Two live layouts:
  1. Co-located    — the data dir sits beside bin/ under the same coordinator
                     root (the pre-migration DoE layout, and any OSS install
                     that ships both halves together). Free, no registration.
  2. Split-repo    — this code lives in the engine repo while the data dir
                     stayed in DoE-claude. Resolve the DoE root the same way
                     every other doctrine CLI does (coordinator_registry.doe_root()).

Rung 1 first so the co-located case costs nothing and needs no registration.

Rung 1.5 — codename-free ladder (added 2026-08-07, C2). `coordinator_registry.
doe_root()` (rung 2 below) has NO codename-free rung of its own — unlike this
module's sibling bootstrap in `coordinator_registry.py`'s own `_MANIFEST_PATH`
resolution (`git show 067da377c1b0`, C1), which gained one, `doe_root()` the
FUNCTION still only tries DOE_ROOT env -> REPO_DOE_CLAUDE env -> machine-local
`repos.doe_claude` -> raise — every one of those needs a private codename this
module's callers running from the published mirror cannot supply. So this
module adds its OWN rung 1.5, ahead of the `doe_root()` call, mirroring the
shape `coordinator_core.ops.coordinator_doe_root` added at its own rung 1.5
(`git show f5d3dde5b523`, C1B) and `coordinator_registry.py`'s manifest
bootstrap added at import time (C1): try, in order, the `.doe-root` pointer
file (durable, then legacy), the flat `~/.claude/plugins/coordinator-claude`
marketplace-clone layout, then `CLAUDE_PLUGIN_ROOT` (normalized via
`_cdr_repo_root_from_plugin_root_candidate()`, C1E fix — the raw env value
is a content root, one level below the repo root this ladder needs), then
the registry's
`plugin.mirrors.coordinator-claude.live_path` key — each candidate accepted
only once it is a directory AND contains one of the two published manifest
layouts (OSS flat `schemas/...`, private `coordinator/schemas/...`). This is
an ADDITIVE rung, not a reimplementation of `doe_root()`'s own env/registry
chain (see negative-spec below) — `doe_root()` itself is untouched.

CORRECTION (Review: staff-eng, twin-divergence finding C2): the premise above
("`doe_root()` the FUNCTION still has no ladder") expired ~6 minutes after C2
landed — `coordinator_registry.py`'s C1D chunk (`git show b9c68ca7d`) gave
`doe_root()` exactly that ladder. This module's rung 1.5 is therefore now
REDUNDANT with `doe_root()`'s own rungs in the common case (harmless — rung
1.5 simply wins first when it also resolves) rather than covering a gap
`doe_root()` structurally lacks. It remains additive and is not removed here
(removing it is a separate, larger change than this review's remit), but a
future reader should not treat "doe_root() has no codename-free rung" as
still true — see `coordinator_registry.doe_root()`'s own docstring for its
current (post-C1D, post-MAJOR-4-reorder) ladder.

Negative-spec: this module does NOT reimplement the DOE_ROOT resolution chain
(env DOE_ROOT -> machine-local repos.doe_claude -> raise). That chain lives in
exactly one place, `coordinator_registry.doe_root()`, and this module calls it
rather than duplicating it. A caller that hand-rolls its own DOE_ROOT lookup
instead of importing `data_root()` from here re-introduces the six-copies-of-
one-chain drift this module exists to close. The rung-1.5 codename-free ladder
above is a SEPARATE, additive rung that `doe_root()` does not carry — adding it
here does not violate this negative-spec, which is about the env/registry
chain `doe_root()` itself owns.

Import-time purity (negative-spec, load-bearing): `coordinator_registry` is
imported LAZILY, inside `data_root()`, NOT at module top level.
`coordinator_registry` eagerly resolves its own manifest at import time (a
`machine-local` subprocess needing `HOME` in the environment) — so a
top-level `from coordinator_registry import ...` here would make merely
IMPORTING this module able to fail or spawn a subprocess, even for callers
who never call `data_root()` because rung 1 (co-located) already resolves
their case, or who run under a stripped/minimal environment (e.g. a test
harness that replaces rather than merges `os.environ`). This module's own
rung-1 resolution (`_colocated_root()`) is zero-subprocess, zero-env-
dependent by construction, and must stay that way. A future editor hoisting
the `coordinator_registry` import back to module level reintroduces exactly
this bug — do not do it, no matter how natural "just import it up top like
everything else" feels. See regression test
`coordinator/tests/test_coordinator_data_root.py` (stripped-env import
assertion).

Public API:
    data_root(dir_name: str) -> Path
        Resolve one of "snippets", "schemas", "templates", "docs" (or any other
        coordinator data-dir name) to its absolute, existing directory Path.
        Raises RuntimeError, naming the dir and both rungs tried, if neither
        rung resolves to an existing directory. Never returns a path that
        doesn't exist; never silently falls back to a wrong location.

Spec backlink: cross-repo/archive/2026-07-22-claude-central-em-executable-surface-migrated-and-76-op-ask.md
               (the originating memo; in cross-repo/inbox/ until the boot sweep moves it)
DR backlink:   docs/decisions/DR-047-doe-claude-klabauter-boundary-redraw-contract-vs-e.md (DoE-side)
Reference fix: coordinator/bin/lib/coordinator_registry.py `_MANIFEST_PATH` bootstrap
               (commit 4f74656c, "coordinator_registry: resolve the schemas manifest
               across the repo split")
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Defensive self-locate — mirrors the sys.path.insert convention every bin/
# entrypoint already uses (see coordinator/bin/snippet-registry's own
# `_LIB_DIR` insertion) so this module resolves its `coordinator_registry`
# sibling import regardless of whether the caller already inserted bin/lib.
#
# NOTE: this insertion is safe to do at import time (pure sys.path mutation,
# no subprocess, no env read) — it is the actual `coordinator_registry`
# import, below in `data_root()`, that is NOT safe at import time. See the
# module docstring's "Import-time purity" negative-spec.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

# F6 fix (2026-08-08, hermetic-ac-reverify) — `claude_home()` is pure
# (module docstring: only imports `os`, no subprocess), safe at module top
# level like coordinator_registry.py's own `_mlir_claude_home` import.
# Converges this module's home derivation onto the SAME semantics
# `coordinator_registry.py::_mp_marketplace_cache_rung`/
# `_mp_flat_layout_probe_rung` already use — `claude_home()` returns
# `CLAUDE_HOME` AS-IS when set (not `<CLAUDE_HOME>/.claude`). This module's
# own rungs previously inlined `CLAUDE_HOME or HOME or USERPROFILE` and then
# unconditionally joined `.claude`, so with `CLAUDE_HOME` set the two
# modules probed different directories — see F6 in
# state/review-findings/2026-08-08-successor-partitioned/hermetic-ac-reverify.md.
from machine_local_impl_resolve import claude_home as _mlir_claude_home

# coordinator/lib — sibling of coordinator/bin/lib (this file's own dir),
# hosting the shared coordinator_read_doe_root_pointer() substrate. Two
# dirname()s up from _THIS_DIR (bin/lib -> bin -> coordinator), then down
# into lib/. Mirrors coordinator_registry.py's own _COORDINATOR_LIB_DIR.
_CDR_COORDINATOR_LIB_DIR = os.path.join(os.path.dirname(os.path.dirname(_THIS_DIR)), "lib")

# Published payload flattens: the mirror ships helper at "<repo root>/lib"
# with no "coordinator/" segment. Three dirname()s up from _THIS_DIR
# (bin/lib -> bin -> coordinator -> repo root), then down into lib/. Probed
# as a fallback below — private tree wins first.
_CDR_COORDINATOR_LIB_DIR_FLAT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(_THIS_DIR))), "lib"
)

# Published-manifest relpath (OSS flat layout). The private DoE-repo layout
# nests the same relpath under `coordinator/`. Shared by the rung-1.5
# codename-free ladder's acceptance gate below — see module docstring.
_CDR_MANIFEST_RELPATH = os.path.join("schemas", "coordinator-registry.manifest.json")


def _cdr_manifest_present(root: str) -> bool:
    """True if `root` contains either published manifest layout: OSS flat
    (`<root>/schemas/coordinator-registry.manifest.json`) or the private
    DoE-repo shape (`<root>/coordinator/schemas/coordinator-registry.manifest.json`).
    Gates each rung-1.5 candidate so a resolved-but-unrelated directory is
    never accepted over a later, correct rung.

    LIMITATION (C1E): probing both layouts here is deliberately
    level-ambiguous by itself -- a CONTENT root (`<repo_root>/coordinator`)
    satisfies the OSS-flat relpath (`<content_root>/schemas/...`) exactly as
    readily as a genuine repo root satisfies the private relpath. This gate
    cannot and does not disambiguate levels; it only confirms "some published
    manifest lives under this directory." Every candidate reaching this gate
    MUST already be repo-root-shaped BEFORE it gets here -- the pointer-file
    and flat-layout rungs already are; `CLAUDE_PLUGIN_ROOT` is normalized to
    repo-root shape by `_cdr_repo_root_from_plugin_root_candidate()`
    immediately before being passed in here, precisely so this gate never has
    to arbitrate the level question it structurally cannot answer. Do not add
    a new rung-1.5 candidate without doing the same normalization first.
    """
    for relpath in (_CDR_MANIFEST_RELPATH, os.path.join("coordinator", _CDR_MANIFEST_RELPATH)):
        if os.path.exists(os.path.join(root, relpath)):
            return True
    return False


def _cdr_doe_root_pointer_rung() -> str:
    """Rung 1.5a/b: the durable + legacy `.doe-root` pointer file reads.
    DELEGATES to coordinator/lib/read_doe_root_pointer.py (pure file I/O, no
    subprocess) rather than reimplementing the read — see
    coordinator_registry.py's `_mp_doe_root_pointer_rung()`, same shape."""
    lib_dir = _CDR_COORDINATOR_LIB_DIR
    if not os.path.isfile(os.path.join(lib_dir, "read_doe_root_pointer.py")):
        lib_dir = _CDR_COORDINATOR_LIB_DIR_FLAT
    added = lib_dir not in sys.path
    if added:
        sys.path.insert(0, lib_dir)
    try:
        from read_doe_root_pointer import coordinator_read_doe_root_pointer

        return coordinator_read_doe_root_pointer()
    except Exception:
        # Swallows: helper missing at both probed dirs, import error inside
        # the helper itself, or any runtime failure in the read — all
        # collapse to "no pointer configured" by contract (never-raise).
        return ""
    finally:
        if added:
            try:
                sys.path.remove(lib_dir)
            except ValueError:
                pass


def _cdr_repo_root_from_plugin_root_candidate(candidate: str) -> str:
    """Normalize a CLAUDE_PLUGIN_ROOT-shaped value to the coordinator REPO
    root this ladder must return (ported from
    coordinator_registry.py::_mp_repo_root_from_plugin_root_candidate(); do
    NOT edit that module, see chunk C1E task notes).

    CLAUDE_PLUGIN_ROOT is a *content* root: in the private/dev DoE layout
    this is `<repo_root>/coordinator`, one level below the repo root
    `data_root()` needs (it appends `"coordinator" / dir_name` itself below
    — feeding it a content root double-nests to
    `<repo_root>/coordinator/coordinator/<dir_name>`, which exists nowhere).
    In the OSS flat layout the content root and repo root coincide.
    Disambiguate via the `.claude-plugin/plugin.json` marketplace marker:
    if it sits directly under `candidate`, candidate already IS the repo
    root; if it sits one level up (candidate's basename is "coordinator"),
    the repo root is the parent. Otherwise return candidate unchanged as a
    best-effort fallback — callers still gate on os.path.isdir() /
    manifest-presence before trusting the result (this ladder's candidates
    all pass through `_cdr_manifest_present` afterward, unlike
    `coordinator_registry.doe_root()`'s rungs, so the unchanged-fallback
    here stays safe — see that module's BLOCKER-2 fix for why its call site
    needed a stricter `allow_unchanged_fallback=False`).

    Review: staff-eng MINOR-8 — normalizes via os.path.normpath before
    stripping trailing separators (a bare rstrip strips a trailing separator
    off a bare drive-letter root, leaving a form Windows resolves as
    CWD-relative rather than the drive root) and casefolds the "coordinator"
    basename compare (a
    case-insensitive filesystem can hand back "...\\Coordinator", which a
    case-sensitive == would miss).
    """
    stripped = os.path.normpath(candidate).rstrip("/\\")
    if os.path.isfile(os.path.join(stripped, ".claude-plugin", "plugin.json")):
        return stripped
    parent = os.path.dirname(stripped)
    if os.path.basename(stripped).casefold() == "coordinator" and os.path.isfile(
        os.path.join(parent, ".claude-plugin", "plugin.json")
    ):
        return parent
    return candidate


def _cdr_flat_layout_probe_rung() -> str:
    """Rung 1.5c: the flat `~/.claude/plugins/coordinator-claude`
    marketplace-clone layout, gated on the `.claude-plugin/plugin.json`
    marker — same marker `resolve_coordinator_clone._resolve_source_mode`
    gates its OSS-install check on. Duplicated inline (matching C1/C1B's
    shape) rather than importing a shared probe — no standalone marker check
    exists to reuse.

    NOT where Claude Code actually installs a marketplace clone (Review:
    staff-eng MINOR-7) — see _cdr_marketplace_cache_rung() below for the
    real install location; retained because it is a real layout this
    codebase's own install/uninstall/sandbox-check tooling produces.

    Home resolution delegates to `_mlir_claude_home()` (F6 fix, 2026-08-08)
    — see module import comment; previously inlined a divergent
    `CLAUDE_HOME`-or-`HOME`-or-`USERPROFILE` ladder that, unlike
    `claude_home()`, always appended `.claude` even when `CLAUDE_HOME` was
    already set to the `.claude` directory itself.
    """
    home = _mlir_claude_home()
    if not home:
        return ""
    candidate = os.path.join(home, "plugins", "coordinator-claude")
    marker = os.path.join(candidate, ".claude-plugin", "plugin.json")
    return candidate if os.path.isfile(marker) else ""


def _cdr_marketplace_cache_rung() -> str:
    """Rung 1.5b — Claude Code's REAL marketplace-install location,
    `<claude_home>/plugins/cache/coordinator-claude/coordinator/<version>/`,
    newest version wins (numeric compare, DR-148-safe). Ported from
    `coordinator_registry.py::_mp_marketplace_cache_rung()` (same
    Review: staff-eng BLOCKER-1(a) fix — `_cdr_flat_layout_probe_rung()`'s
    candidate is not where a marketplace clone actually installs; this is).
    Resolves to the repo root directly, gated by `_cdr_manifest_present`
    like every other candidate in this ladder — no normalization needed
    before that gate.

    Home resolution delegates to `_mlir_claude_home()` (F6 fix, 2026-08-08)
    — see `_cdr_flat_layout_probe_rung()`'s docstring and the module import
    comment for why.
    """
    home = _mlir_claude_home()
    if not home:
        return ""
    cache_parent = os.path.join(home, "plugins", "cache", "coordinator-claude", "coordinator")
    if not os.path.isdir(cache_parent):
        return ""
    best = ""
    best_key = (-1, -1, -1)
    try:
        entries = os.listdir(cache_parent)
    except OSError:
        return ""
    for name in entries:
        child = os.path.join(cache_parent, name)
        if not os.path.isdir(child):
            continue
        parts = (name.split(".") + ["0", "0", "0"])[:3]
        nums: list[int] = []
        for part in parts:
            digits = ""
            for ch in part:
                if ch.isdigit():
                    digits += ch
                else:
                    break
            nums.append(int(digits) if digits else 0)
        key = (nums[0], nums[1], nums[2])
        if key > best_key:
            best_key = key
            best = child
    return best


def _cdr_codename_free_root() -> str:
    """Rung 1.5 — codename-free ladder (C2). Runs ahead of rung 2
    (`coordinator_registry.doe_root()`), which has no codename-free rung of
    its own. Tries, in order: the `.doe-root` pointer file (durable, then
    legacy), the real marketplace-cache install location (Review: staff-eng
    BLOCKER-1), the flat marketplace-clone layout, `CLAUDE_PLUGIN_ROOT`,
    then the `plugin.mirrors.coordinator-claude.live_path` registry key
    (Review: staff-eng MAJOR-3 — routed through the same
    CLAUDE_PLUGIN_ROOT-shaped normalizer, not trusted as a repo root
    unconverted; see that helper's docstring). Each candidate is accepted
    only once it is a directory AND `_cdr_manifest_present` confirms one of
    the two published manifest layouts lives under it. See module docstring
    for why this rung exists.

    The registry sub-rung imports `coordinator_registry` LAZILY (only when
    the earlier file rungs miss) — see module docstring's "Import-time
    purity" negative-spec; this function is itself only ever called from
    inside `data_root()`, never at import time.
    """
    _plugin_root_env = os.environ.get("CLAUDE_PLUGIN_ROOT", "").strip()
    for candidate in (
        _cdr_doe_root_pointer_rung(),
        _cdr_marketplace_cache_rung(),
        _cdr_flat_layout_probe_rung(),
        _cdr_repo_root_from_plugin_root_candidate(_plugin_root_env) if _plugin_root_env else "",
    ):
        if candidate and os.path.isdir(candidate) and _cdr_manifest_present(candidate):
            return candidate

    from coordinator_registry import _registry_machine_local_get

    live_path = _registry_machine_local_get("plugin.mirrors.coordinator-claude.live_path") or ""
    if live_path:
        live_normalized = _cdr_repo_root_from_plugin_root_candidate(live_path)
        if live_normalized and os.path.isdir(live_normalized) and _cdr_manifest_present(live_normalized):
            return live_normalized
    return ""


def _colocated_root() -> Path:
    """The coordinator root this module's own bin/lib sits under (rung-1 base).

    coordinator/bin/lib/coordinator_data_root.py -> parents[2] == coordinator/
    (file -> lib/ -> bin/ -> coordinator/), the same triple `os.path.dirname`
    walk `coordinator_registry.py`'s `_MANIFEST_PATH` bootstrap uses.
    """
    return Path(__file__).resolve().parents[2]


def data_root(dir_name: str) -> Path:
    """Resolve `dir_name` (e.g. "snippets", "schemas", "templates", "docs") to
    its absolute, existing directory Path.

    Resolution chain (co-located -> codename-free ladder -> DoE-resident):
      1. Co-located — `<coordinator-root>/<dir_name>` beside this module's own
         bin/lib, where `<coordinator-root>` is computed identically to
         `coordinator_registry.py`'s manifest-path bootstrap. Free, no
         registration, wins whenever both halves ship together.
      1.5. Codename-free ladder (C2) — `.doe-root` pointer file, flat
         marketplace-clone layout, `CLAUDE_PLUGIN_ROOT`, registry
         `live_path`; see `_cdr_codename_free_root()` and module docstring.
      2. DoE-resident — `<doe_root()>/coordinator/<dir_name>` (private layout),
         falling back to `<doe_root()>/<dir_name>` (OSS-flat layout, F2 fix
         2026-08-08 -- see below), delegating the DOE_ROOT/machine-local
         resolution to `coordinator_registry.doe_root()` (never reimplemented
         here — see module negative-spec).

    Raises RuntimeError, naming `dir_name` and both candidate paths tried
    (or the DoE-resolution failure reason), if neither rung resolves to an
    existing directory. Never returns a path that doesn't exist.
    """
    colocated = _colocated_root() / dir_name
    if colocated.is_dir():
        return colocated

    doe = _cdr_codename_free_root()

    if not doe:
        # Lazy import — see module docstring's "Import-time purity" negative-spec.
        # Paid only on this rung-2 path, which already needs the subprocess/env
        # dependent `coordinator_registry.doe_root()` resolution anyway.
        from coordinator_registry import _DoeUnresolvable, doe_root

        try:
            doe = doe_root()
        except _DoeUnresolvable as exc:
            raise RuntimeError(
                f"coordinator_data_root: cannot resolve data dir {dir_name!r}. "
                f"Rung 1 (co-located) tried: {colocated} (not found). "
                f"Rung 2 (DoE-resident) failed: {exc}"
            ) from exc

    # F2 fix (2026-08-08, hermetic-ac-reverify) -- the codename-free ladder's
    # gate (`_cdr_manifest_present`/`_mp_candidate_manifest_path`) accepts
    # EITHER published manifest layout: private DoE-repo shape
    # (`<root>/coordinator/schemas/...`) AND OSS-flat shape
    # (`<root>/schemas/...`, no `coordinator/` segment). This terminal join
    # previously ALWAYS inserted `coordinator/`, so a correctly-resolved
    # OSS-flat root (e.g. a real marketplace-cache install) produced a path
    # that cannot exist. Try the private-shape join first (unchanged default
    # for every existing caller/test resolving a private-layout root), then
    # the OSS-flat shape -- see F2 in
    # state/review-findings/2026-08-08-successor-partitioned/hermetic-ac-reverify.md.
    # Must stay behaviourally identical to coordinator_core/data_root.py's
    # own data_root() (AC4) -- same two-candidate order there.
    private_candidate = Path(doe) / "coordinator" / dir_name
    if private_candidate.is_dir():
        return private_candidate

    flat_candidate = Path(doe) / dir_name
    if flat_candidate.is_dir():
        return flat_candidate

    raise RuntimeError(
        f"coordinator_data_root: cannot resolve data dir {dir_name!r}. "
        f"Rung 1 (co-located) tried: {colocated} (not found). "
        f"Rung 2 (DoE-resident) tried: {private_candidate} (private layout, not found), "
        f"{flat_candidate} (OSS-flat layout, not found)."
    )
