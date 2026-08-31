"""coordinator_registry — shared registry loader for coordinator doc-type and identity data.

Single source of truth (SoT): schemas/coordinator-registry.manifest.json.
Loaded once at import time via json.load; callers import the named constants directly.
An absent or malformed manifest is an install-integrity failure and raises immediately.

Exposed names (reconstruction rules per manifest._reconstruction key):
  KNOWN_TYPES         — frozenset of all recognized --type values
  SIDECAR_TYPES       — frozenset of types that are plan sidecars
  QUEUE_TYPES         — frozenset of queue-delegate types
  REPO_ALIASES        — dict registryKey → shortname  (Python _REPO_KEY_ALIASES convention)
  CENTRAL_RECEIVER_IDS — frozenset of valid central EM receiver identity strings
  REDIRECT_ALIASES    — frozenset of DoE-canonical home/mirror redirect aliases
                         (identity.redirectAliases; cross-repo-memo's former
                         code-pinned _DOE_CANONICAL_REDIRECT_ALIASES literal.
                         Cross-repo contract surface: the engine repo's
                         coordinator_core/ops/fleet/_memo_resolver.py
                         read_redirect_aliases() is a downstream consumer.)
  RECEIVER_EM_ALIASES — dict shortname → registryKey  (inverse; for cross-repo-memo)
  SIDECAR_SUFFIXES    — dict sidecar-type → filesystem suffix (e.g. "review" → "review")
  DOC_TYPES           — raw docTypes tuple for callers needing schemaName/offerable fields

Shared identity-resolution functions (canonical, importable by all 4 CLIs):
  repo_key_to_em_id(key)                         — repos.<name> → <name>-em, with central anchor
  em_id_for_root(root, repo_key_paths)            — repo root path → em-id string
  _central_canonical_id()                        — the one canonical central-EM identity string
                                                    (centralReceiverIds[0]); see docstring below
  _same_path(a, b)                               — internal path-equality helper, importable by the CLIs that need direct comparison

Shared state-root resolver (canonical, importable by all doctrine CLIs):
  doe_root()                         — DoE repo root (Review: staff-eng MAJOR-4 —
                                        env DOE_ROOT → env REPO_DOE_CLAUDE FIRST, so the
                                        documented override is a real override again; DR-071
                                        reorder (2026-08-10) — THEN machine-local
                                        repos.doe_claude (the canonical anchor), THEN the
                                        codename-free rungs: .doe-root pointer → marketplace
                                        cache → flat plugin layout → CLAUDE_PLUGIN_ROOT
                                        (normalized, state/-gated) → registry live_path
                                        (normalized, state/-gated) → raise. REPO_DOE_CLAUDE is
                                        the documented override (ambient, shell-exported by
                                        the engine repo's install surface); DOE_ROOT is a permanent
                                        legacy alias retained for backward compatibility and
                                        still wins first among the two when both are set. The
                                        codename-free ladder must rank BELOW the registry per
                                        DR-071 — see doe_root()'s own docstring for the live
                                        incident this reorder closes.
  _DoeUnresolvable                   — raised when DoE root is unresolvable; callers catch and WARN+skip (exit 0)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

# Self-locating sys.path insert (defensive — most callers already insert this
# same directory before importing this module, but this module must also be
# importable standalone). Enables the settings-home-first delegation below.
_REGISTRY_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
if _REGISTRY_LIB_DIR not in sys.path:
    sys.path.insert(0, _REGISTRY_LIB_DIR)

from machine_local_impl_resolve import (  # noqa: E402
    claude_home as _mlir_claude_home,
    machine_local_bin_candidates as _mlir_machine_local_bin_candidates,
    machine_local_impl_path as _mlir_machine_local_impl_path,
    registry_get as _mlir_registry_get,
)

# ---------------------------------------------------------------------------
# Manifest path — layout-tolerant, never a hardcoded absolute path.
#
# Two live layouts since the 2026-07-22 executable-surface migration:
#   1. Co-located    — schemas/ sits beside bin/ under the same coordinator root
#                      (the pre-migration DoE layout, and any OSS install that
#                      ships both halves together).
#   2. Split-repo    — this code lives in the engine repo while schemas/ stayed
#                      in DoE-claude, because schemas are CONTRACT and DR-047
#                      splits contract to DoE and the engine to here. Resolve the
#                      DoE root the same way every other doctrine CLI does.
#
# Rung 1 first so the co-located case costs nothing and needs no registration.
# ---------------------------------------------------------------------------
_MANIFEST_RELPATH = os.path.join("schemas", "coordinator-registry.manifest.json")
_MANIFEST_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    _MANIFEST_RELPATH,
)

# coordinator/lib — sibling of coordinator/bin/lib (this file's own dir),
# hosting the shared coordinator_read_doe_root_pointer() substrate. Two
# dirname()s up from _REGISTRY_LIB_DIR (bin/lib -> bin -> coordinator), then
# down into lib/.
_COORDINATOR_LIB_DIR = os.path.join(os.path.dirname(os.path.dirname(_REGISTRY_LIB_DIR)), "lib")

# Published payload flattens: the mirror ships helper at "<repo root>/lib"
# with no "coordinator/" segment (coordinator/lib -> lib). Three dirname()s
# up from _REGISTRY_LIB_DIR (bin/lib -> bin -> coordinator -> repo root),
# then down into lib/. Probed as a fallback below — private tree wins first.
_COORDINATOR_LIB_DIR_FLAT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(_REGISTRY_LIB_DIR))), "lib"
)

# Env var name honoured by the internal machine-local reader — shared with the CLIs
# so a single test-isolation set covers all callers (MACHINE_LOCAL_IMPL). Defined
# here (ahead of the manifest bootstrap below) rather than further down, because
# the codename-free rung ladder's registry rung (rung 5) needs it at import time.
_REGISTRY_MACHINE_LOCAL_IMPL_ENV = "MACHINE_LOCAL_IMPL"


def _registry_machine_local_impl() -> str:
    """Return the path to _machine_local.py, settings-home first, honoring
    MACHINE_LOCAL_IMPL for tests.

    Delegates to machine_local_impl_resolve.machine_local_impl_path() — see
    that module's docstring (DR-210 Amendment: "resolves nothing through
    ~/.claude/bin"; this rung now tries settings-home before the mirror).
    """
    return _mlir_machine_local_impl_path(_REGISTRY_MACHINE_LOCAL_IMPL_ENV)


def _registry_machine_local_get(key: str) -> str | None:
    """Call machine-local get <key> and return the value, or None on failure.

    In-process FIRST via machine_local_impl_resolve.registry_get(key) —
    returned when truthy. Only on None does this fall through to the
    existing subprocess spawn below, which stays the fallback rung.

    Uses sys.executable (the interpreter running this module) — no subprocess
    probing needed; safe on macOS, Linux, and Windows. CREATE_NO_WINDOW guard
    suppresses the Windows console popup (portable: getattr resolves to 0 on
    non-Windows).

    Documented hazard (review F1, 2026-08-20): for `repos.*` keys, this
    in-process rung's source-file ladder is `registry.local.toml` then
    `registry.toml` (machine_local_impl_resolve.registry_get()) — but the
    real `machine-local get repos.<slug>` CLI routes `repos.*` through a
    4-rung ladder (REPO_<SLUG> env → marker autodiscovery →
    path-exceptions.toml → registry.local.toml) that NEVER consults
    registry.toml for this key class. registry.toml is install-mutable
    (seeded from a template, then mutated in place by
    _register_hardware_concern and cockpit-key notices), so a stale non-empty
    `repos.*` row there can short-circuit this rung and return a value the
    CLI's ladder would never have produced — not merely a reordering that is
    "precedence-preserving at the value level," since the CLI's ladder does
    not have a registry.toml rung to be equivalent to. Inherited from the
    shared oracle reader and already ratified at 5 other repos.* call sites
    (gen_claude_doe_shim.py, gen_doe_root_pointer.py, new_project_scaffold.py,
    render_template_tree.py, repo_bootstrap.py) — not invented here. Do NOT
    fix by skipping registry.toml for repos.* keys in this function; that is
    a separate, deliberately deferred cross-site change (all 6 sites
    together), not a local patch.
    """
    _in_process = _mlir_registry_get(key)
    if _in_process:
        return _in_process
    impl = _registry_machine_local_impl()
    cmd = [sys.executable, impl, "get", key]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        # Review: staff-eng MAJOR-5 — this function is reachable from the
        # module-level import bootstrap (rung 5) on any box where rungs 1-4
        # miss, and this repo's own load norm (50-70 concurrent LLM sessions,
        # CLAUDE.md § Load norm) makes a slow machine-local spawn the
        # expected case, not the pathological one. An unbounded subprocess
        # at import time — blocking every one of the 32 payload CLIs that
        # import this module — has no recovery path; bound it and treat a
        # timeout the same as any other lookup failure, matching the
        # timeout=10 the legacy bootstrap reader below already uses.
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.strip()


def _mp_candidate_manifest_path(root: str) -> str | None:
    """Probe both published manifest layouts under `root`; return the first
    that exists, else None.

      <root>/schemas/coordinator-registry.manifest.json               (OSS: manifest flat at repo/plugin root)
      <root>/coordinator/schemas/coordinator-registry.manifest.json   (private: DoE repo shape)

    Required because DoE's coordinator-claude publish row ships the manifest
    flat at plugin root, while the private tree has it under coordinator/.
    """
    for _relpath in (
        _MANIFEST_RELPATH,
        os.path.join("coordinator", _MANIFEST_RELPATH),
    ):
        _candidate = os.path.join(root, _relpath)
        if os.path.exists(_candidate):
            return _candidate
    return None


def _mp_doe_root_pointer_rung() -> str:
    """Codename-free rungs 1-2: the durable + legacy `.doe-root` pointer file
    reads. DELEGATES to coordinator/lib/read_doe_root_pointer.py rather than
    reimplementing the read — that helper already tries
    `${settings-home}/machine-local/.doe-root` then
    `${CLAUDE_HOME:-$HOME}/.claude/.doe-root` in that exact order, returns ""
    on failure, and never raises. Pure file I/O — no subprocess, preserving
    import-time purity.
    """
    # Probe both helper-dir layouts, private tree first: co-located
    # coordinator/lib exists here on this dev box, but the published
    # payload flattens to <root>/lib with no coordinator/ segment.
    _lib_dir = _COORDINATOR_LIB_DIR
    if not os.path.isfile(os.path.join(_lib_dir, "read_doe_root_pointer.py")):
        _lib_dir = _COORDINATOR_LIB_DIR_FLAT
    _added = _lib_dir not in sys.path
    if _added:
        sys.path.insert(0, _lib_dir)
    try:
        from read_doe_root_pointer import coordinator_read_doe_root_pointer

        return coordinator_read_doe_root_pointer()
    except Exception:
        # Swallows: helper missing at both probed dirs, import error inside
        # the helper itself, or any runtime failure in the read — all
        # collapse to "no pointer configured" by contract (never-raise).
        return ""
    finally:
        if _added:
            try:
                sys.path.remove(_lib_dir)
            except ValueError:
                pass


def _mp_repo_root_from_plugin_root_candidate(candidate: str, *, allow_unchanged_fallback: bool = True) -> str:
    """Normalize a CLAUDE_PLUGIN_ROOT-shaped value to the coordinator REPO
    root that doe_root() callers expect.

    Single-sourced (state/debt-backlog/2026-08-08-three-divergent-copies-of-
    the-plugin-roo-8d584d3b90d3.yaml): delegates to coordinator_core.ops.
    coordinator_doe_root.repo_root_from_plugin_root_candidate() (the same
    engine module this file already imports coordinator_core from, via
    _same_path() below — no new import edge), with THIS copy's own historical
    shape reproduced exactly via keyword args: drive_root_guard="normpath"
    (os.path.normpath()-based, NOT the B7 bare-drive-root truncation guard —
    see that function's "KNOWN CROSS-COPY DIVERGENCE" docstring note),
    basename_compare="casefold" (case-insensitive on every platform, unlike
    the engine copy's Windows-only normcase compare — same flagged note),
    manifest_relpath_fallback=False (this copy never carried the B5 fix),
    allow_unchanged_fallback=<this function's own kwarg>.

    Do NOT edit coordinator_core's copy of this helper to "fix" the two
    flagged divergences above under cover of this refactor — they are
    reported to the EM/PM, not resolved, pending a decision on whether they
    are intentional or latent bugs.

    CLAUDE_PLUGIN_ROOT is a *content* root (see
    resolve_coordinator_clone.py::resolve_content_root() rung 1, and its
    `.doe-root` pointer rung which returns `<repo_root>/coordinator`) — in
    the private/dev DoE layout this is `<repo_root>/coordinator`, one level
    below the repo root doe_root() must return (state/ hangs off the repo
    root, never off the coordinator/ subdir — see doe_root()'s own
    negative-spec). In the OSS flat layout the content root and the repo
    root coincide (manifest ships flat at plugin root, no coordinator/
    prefix — this module's "Two live layouts" docstring note).

    Disambiguate the same way _mp_flat_layout_probe_rung() does: gate on the
    `.claude-plugin/plugin.json` marketplace marker. If it sits directly
    under `candidate`, candidate already IS the repo root (OSS flat case).
    If it sits one level up (candidate's basename is "coordinator" and the
    marker is beside it), the repo root is the parent (private/dev layout).

    `allow_unchanged_fallback` (Review: staff-eng BLOCKER-2) — True
    (default; the manifest-bootstrap ladder's use, gated afterward by a
    manifest-presence probe) returns `candidate` unchanged when neither
    shape matches. False (doe_root()'s rungs 4-5, which have no downstream
    manifest gate) returns "" instead — an unrecognizable candidate must not
    silently win over an operator's explicit override just because
    os.path.isdir() happens to be true.

    Review: staff-eng MINOR-8 — normalizes via os.path.normpath before
    stripping trailing separators (a bare rstrip strips a trailing separator
    off a bare drive-letter root, leaving a form Windows resolves as
    CWD-relative rather than the drive root) and casefolds the "coordinator"
    basename compare (a
    case-insensitive filesystem can hand back "...\\Coordinator", which a
    case-sensitive == would miss, falling through to the unchanged-candidate
    branch and reintroducing the content-root bug C1E fixed one rung up).
    """
    if _REGISTRY_LIB_DIR not in sys.path:
        sys.path.insert(0, _REGISTRY_LIB_DIR)
    import cc_invoke

    cc_invoke.ensure_engine_on_path(__file__)
    from coordinator_core.ops.coordinator_doe_root import repo_root_from_plugin_root_candidate

    return repo_root_from_plugin_root_candidate(
        candidate,
        drive_root_guard="normpath",
        basename_compare="casefold",
        manifest_relpath_fallback=False,
        allow_unchanged_fallback=allow_unchanged_fallback,
    )


def _mp_flat_layout_probe_rung() -> str:
    """Codename-free rung: the flat `~/.claude/plugins/coordinator-claude`
    marketplace-clone layout, gated on the `.claude-plugin/plugin.json`
    marker (same marker `resolve_coordinator_clone.py::_resolve_source_mode`
    gates its OSS-install check on). Implemented inline rather than importing
    `coordinator_core.resolve_coordinator_clone` — this module's manifest
    bootstrap runs at IMPORT time and must stay filesystem-and-env only;
    importing a coordinator_core module here is not viable to verify as
    side-effect-free at that phase, so the marker check is duplicated instead.

    NOT where Claude Code actually installs a marketplace clone (Review:
    staff-eng MINOR-7) — see _mp_marketplace_cache_rung() below for the real
    install location. Retained because it is a real layout this codebase's
    own install/uninstall/sandbox-check tooling produces.

    Home resolution delegates to the canonical _mlir_claude_home() (Review:
    staff-eng MINOR-7 secondary) rather than a hand-rolled
    CLAUDE_HOME-or-HOME-or-USERPROFILE chain — this file already imports it,
    and a second, slightly different home ladder in the same module drifts
    from the settings-home-aware canonical version silently.
    """
    _home = _mlir_claude_home()
    if not _home:
        return ""
    _candidate = os.path.join(_home, "plugins", "coordinator-claude")
    _marker = os.path.join(_candidate, ".claude-plugin", "plugin.json")
    return _candidate if os.path.isfile(_marker) else ""


def _mp_marketplace_cache_rung() -> str:
    """Codename-free rung: Claude Code's REAL marketplace-install location —
    `<claude_home>/plugins/cache/coordinator-claude/coordinator/<version>/`,
    newest version wins (numeric compare, DR-148-safe). Mirrors
    `resolve_coordinator_clone._newest_cache_dir()` inline rather than
    importing `coordinator_core` — same import-time-purity reasoning as
    `_mp_flat_layout_probe_rung()` above; this module's manifest bootstrap
    runs at IMPORT time and must stay filesystem-and-env only.

    Review: staff-eng BLOCKER-1(a) — `_mp_flat_layout_probe_rung()`'s
    candidate is not where Claude Code installs a marketplace plugin; this
    is. Without this rung, a direct-CLI invocation on a real OSS install (no
    `.doe-root` pointer, no CLAUDE_PLUGIN_ROOT, no machine-local registry)
    has no live rung left and the manifest bootstrap fails loud on
    install-integrity — the defect this workstream exists to close.

    Resolves to the repo root directly (OSS-flat shaped: schemas/ sits
    directly under the version dir) — no normalization needed before use.
    """
    _home = _mlir_claude_home()
    if not _home:
        return ""
    _cache_parent = os.path.join(_home, "plugins", "cache", "coordinator-claude", "coordinator")
    if not os.path.isdir(_cache_parent):
        return ""
    _best = ""
    _best_key = (-1, -1, -1)
    try:
        _entries = os.listdir(_cache_parent)
    except OSError:
        return ""
    for _name in _entries:
        _child = os.path.join(_cache_parent, _name)
        if not os.path.isdir(_child):
            continue
        _parts = (_name.split(".") + ["0", "0", "0"])[:3]
        _nums: list[int] = []
        for _part in _parts:
            _digits = ""
            for _ch in _part:
                if _ch.isdigit():
                    _digits += _ch
                else:
                    break
            _nums.append(int(_digits) if _digits else 0)
        _key = (_nums[0], _nums[1], _nums[2])
        if _key > _best_key:
            _best_key = _key
            _best = _child
    return _best


if not os.path.exists(_MANIFEST_PATH):
    # Split-repo layout: DR-071 canonical anchor FIRST — env override, then the
    # machine-local repos.doe_claude registry entry, which DR-071 ratifies as
    # the authoritative coordinator-root anchor, ranked ABOVE the codename-free
    # ladder below (including `.doe-root`). Resolved inline rather than via
    # doe_root() below because this runs at import time, before that function
    # is defined — same chain (DOE_ROOT env → REPO_DOE_CLAUDE env → machine-local
    # repos.doe_claude), deliberately duplicated only for the bootstrap order.
    # REPO_DOE_CLAUDE is aliased here too (not just in doe_root() below) — it is
    # the ambient, shell-exported name; omitting it from the bootstrap would
    # leave the split-repo import path resolving to the wrong root exactly the
    # way doe_root() used to.
    #
    # Review: this rung ordering (registry before codename-free) previously ran
    # AFTER the codename-free ladder below — the same DR-071 precedence defect
    # `coordinator_core/ops/coordinator_doe_root.py` fixed per finding B2
    # (state/review-findings/2026-08-08-codename-free-partitioned/slice-B-doe-root.md),
    # whose own coverage note flagged this module as explicitly NOT reviewed/
    # reordered at the time. On a box where the registry correctly names the
    # private DoE-claude tree but a codename-free rung (e.g. a stale/published
    # marketplace install, or a `.doe-root` pointer inherited from an earlier
    # install) ALSO resolves to a directory carrying a manifest, the ladder
    # below used to win and this module's RECEIVER_EM_ALIASES / centralReceiverIds
    # were built from that (potentially scrubbed) manifest instead of the
    # registry-anchored private one — see
    # cross-repo/inbox/2026-08-10-doe-claude-em-reconcile-close-terminal-and-scrub-key.md
    # § 3 (`cross-repo-memo` send path resolving `repos.example_doctrine_repo`).
    #
    # Settings-home-first (DR-210 Amendment 2026-07-24: "resolves nothing
    # through ~/.claude/bin") — try each machine-local candidate in order
    # (settings-home, then the retired compat mirror as last resort) until
    # one exists on disk; the mirror candidate is never removed, only tried
    # last. Spec backlink: machine_local_impl_resolve.py module docstring.
    _doe = os.environ.get("DOE_ROOT", "").strip() or os.environ.get("REPO_DOE_CLAUDE", "").strip()
    if not _doe:
        _doe = _mlir_registry_get("repos.doe_claude") or ""
    if not _doe:
        for _ml_cand in _mlir_machine_local_bin_candidates():
            if not os.path.exists(_ml_cand):
                continue
            try:
                _mlres = subprocess.run(
                    [_ml_cand, "get", "repos.doe_claude"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if _mlres.returncode == 0:
                    _doe = _mlres.stdout.strip()
            except (OSError, subprocess.SubprocessError):
                _doe = ""
            if _doe:
                break
    if _doe:
        _candidate = os.path.join(_doe, "coordinator", _MANIFEST_RELPATH)
        if os.path.exists(_candidate):
            _MANIFEST_PATH = _candidate

if not os.path.exists(_MANIFEST_PATH):
    # Codename-free rung ladder (rung 2.75, DR-071) — only reached when the
    # canonical registry anchor above did not resolve. CLAUDE_PLUGIN_ROOT is
    # only set while Claude Code is executing a plugin-declared hook/command,
    # so it is ABSENT for every direct CLI invocation this must survive; both
    # it and the registry live_path being empty is the NORMAL OSS case. None
    # of these rung sources contain a private codename, so the OSS
    # depersonalize scrub cannot touch them directly — but a genuinely
    # published/scrubbed marketplace install IS reachable through them, which
    # is exactly why DR-071 ranks them below the registry rung above.
    for _mp_root in (
        _mp_doe_root_pointer_rung(),
        _mp_marketplace_cache_rung(),
        _mp_flat_layout_probe_rung(),
        os.environ.get("CLAUDE_PLUGIN_ROOT", "").strip(),
        _registry_machine_local_get("plugin.mirrors.coordinator-claude.live_path") or "",
    ):
        if not _mp_root or not os.path.isdir(_mp_root):
            continue
        _mp_manifest_cand = _mp_candidate_manifest_path(_mp_root)
        if _mp_manifest_cand:
            _MANIFEST_PATH = _mp_manifest_cand
            break

try:
    with open(_MANIFEST_PATH, encoding="utf-8") as _f:
        _manifest = json.load(_f)
except FileNotFoundError as _e:
    # Split-repo layout (schemas/ live in DoE-claude, not co-located here):
    # every rung above that could have found the manifest elsewhere derives
    # from the same DOE_ROOT/REPO_DOE_CLAUDE resolution doe_root() performs
    # below -- if none of them found it, that resolution is what actually
    # failed. Name it explicitly so this reads as a dependency-resolution
    # failure the operator can act on (set DOE_ROOT / REPO_DOE_CLAUDE), not
    # a generic "plugin isn't installed" report when it demonstrably is.
    raise FileNotFoundError(
        f"coordinator_registry: manifest not found at {_MANIFEST_PATH!r}, and no "
        "DOE_ROOT/REPO_DOE_CLAUDE-resolvable candidate located one either. "
        "This is an install-integrity failure — ensure the coordinator plugin is "
        "fully installed, or set DOE_ROOT to the schemas-hosting repo's root."
    ) from _e
except json.JSONDecodeError as _e:
    raise ValueError(
        f"coordinator_registry: manifest at {_MANIFEST_PATH!r} is malformed JSON: {_e}. "
        "This is an install-integrity failure — do not hand-edit the manifest."
    ) from _e

try:
    _doc_types: list[dict] = _manifest["docTypes"]
    _queue_types_list: list[str] = _manifest["queueTypes"]
    _identity: dict = _manifest["identity"]
except KeyError as _e:
    # review F1 — a structurally-valid JSON file missing any top-level key is still an
    # install-integrity failure; emit a helpful message (the FileNotFoundError /
    # json.JSONDecodeError paths do this already — now the KeyError path does too).
    raise ValueError(
        f"coordinator_registry: manifest at {_MANIFEST_PATH!r} is missing required key: {_e}. "
        "This is an install-integrity failure — do not hand-edit the manifest."
    ) from _e

# ---------------------------------------------------------------------------
# Derived constants — reconstruction rules per manifest._reconstruction key.
# ---------------------------------------------------------------------------

# KNOWN_TYPES = {d.type for d in docTypes} ∪ set(queueTypes)
# docTypes is complete over every non-queue type (offerable and excluded alike),
# so this union byte-equals the pre-refactor coordinator-doc-new._KNOWN_TYPES.
KNOWN_TYPES: frozenset[str] = frozenset(d["type"] for d in _doc_types) | frozenset(_queue_types_list)

# SIDECAR_TYPES = {d.type for d in docTypes if d.isSidecar}
SIDECAR_TYPES: frozenset[str] = frozenset(d["type"] for d in _doc_types if d["isSidecar"])

# QUEUE_TYPES = set(queueTypes)
QUEUE_TYPES: frozenset[str] = frozenset(_queue_types_list)

try:
    # review F1 — identity nested-key accesses are equally susceptible to KeyError on a
    # hand-edited or partially-upgraded manifest; guard them under the same helpful message.
    _repo_aliases_raw = _identity["repoAliases"]
    _central_receiver_ids_raw = _identity["centralReceiverIds"]
except KeyError as _e:
    raise ValueError(
        f"coordinator_registry: manifest at {_MANIFEST_PATH!r} is missing required identity key: {_e}. "
        "This is an install-integrity failure — do not hand-edit the manifest."
    ) from _e

# REPO_ALIASES: registryKey → shortname — matches the Python _REPO_KEY_ALIASES convention
# in coordinator-doc-new and coordinator-queue-append.
REPO_ALIASES: dict[str, str] = {a["registryKey"]: a["shortname"] for a in _repo_aliases_raw}

# CENTRAL_RECEIVER_IDS: valid central EM receiver identity strings
CENTRAL_RECEIVER_IDS: frozenset[str] = frozenset(_central_receiver_ids_raw)


def _central_canonical_id() -> str:
    """The single canonical central-EM identity string.

    Derived from identity.centralReceiverIds[0] in the manifest — index 0 is
    canonical by convention (mirrors DoE's frontmatter validator, which derives
    its own canonical id the same way: centralReceiverIds[0]). All OTHER entries
    in the list remain valid receiver aliases (see CENTRAL_RECEIVER_IDS, which
    membership-tests the full set) — this helper exists only to name the ONE
    preferred value callers should emit/display, not to narrow what's accepted.

    Negative-spec: do not hardcode "doe-claude-em" (or any central-em string) as
    a bare literal anywhere that needs the canonical id — derive it from here so
    a future manifest re-ordering of centralReceiverIds propagates automatically.
    """
    return _central_receiver_ids_raw[0]

# REDIRECT_ALIASES: DoE-canonical home/mirror redirect aliases (identity.redirectAliases).
# Unlike repoAliases/centralReceiverIds above, this key is read via .get() with a
# fallback default, NOT a required-key KeyError guard — the field is a 2026-07-21
# promotion of what was previously a code-pinned literal in cross-repo-memo, and a
# manifest predating that promotion (or a hand-edited copy that dropped the key)
# must still degrade to the same known-good set rather than hard-failing every CLI
# invocation. The literal below is therefore a FALLBACK DEFAULT, not the authority —
# once identity.redirectAliases is present (as it is in this manifest), that value
# wins; this default only fires if the key is ever absent.
#
# Cross-repo contract surface: the engine repo's coordinator_core/ops/fleet/
# _memo_resolver.py `read_redirect_aliases()` reads this same manifest field
# declaratively (their negative-spec forbids hardcoding the literal on their side).
_redirect_aliases_raw = _identity.get(
    "redirectAliases",
    [".claude-em", "claude-home", "coordinator-claude", "coordinator-claude-em"],
)
REDIRECT_ALIASES: frozenset[str] = frozenset(
    a.strip().lower() for a in _redirect_aliases_raw if isinstance(a, str) and a.strip()
)

# RECEIVER_EM_ALIASES: shortname → registryKey (inverse of REPO_ALIASES; used by cross-repo-memo)
RECEIVER_EM_ALIASES: dict[str, str] = {a["shortname"]: a["registryKey"] for a in _repo_aliases_raw}

# SIDECAR_SUFFIXES: sidecar-type → filesystem suffix (e.g. "review" → "review").
# review F3 — replaces the local _SIDECAR_SUFFIX dict in coordinator-doc-new; derived from
# the manifest "suffix" field on isSidecar entries so new sidecar types never KeyError.
SIDECAR_SUFFIXES: dict[str, str] = {
    d["type"]: d["suffix"]
    for d in _doc_types
    if d.get("isSidecar") and "suffix" in d
}

# DOC_TYPES: raw docTypes list for callers needing schemaName/offerable fields.
# review F4 — prevents container-level .append/index-assignment; inner dicts remain
# mutable — callers must not mutate items in place.
DOC_TYPES: tuple[dict, ...] = tuple(_doc_types)

# ---------------------------------------------------------------------------
# Shared identity-resolution helpers
#
# Canonical form lifted from the 4 CLI local copies and centralised here so the
# CLIs import instead of duplicating. The ~./claude home special-case is REMOVED;
# central identity is now anchored on repos.doe_claude path-match only.
#
# Spec backlink: DoE-claude:pln-complete-the-claude-central-em-e9000c § C1
# ---------------------------------------------------------------------------


def _same_path(a: str, b: str) -> bool:
    """True if two paths resolve to the same directory (cross-platform).

    Thin alias onto ``coordinator_core.win_portability.same_path`` -- the
    consolidated primitive (state/sizings/2026-08-07-path-equality-
    consolidates-onto-one-prim.yaml).

    ``coordinator_core`` is NOT ambiently importable outside an engine-repo
    checkout with an editable install (see editable-install-masks-engine-
    import-defects hazard) -- callers elsewhere (e.g. coordinator-queue-append
    invoked without ``--from-repo``, from a caller repo's cwd) hit a bare
    ``ModuleNotFoundError`` here. Route through the same engine-root-on-
    sys.path seam every other bin/lib trampoline uses (records_query.py's
    ``_no_console_kw``, coordinator-queue-append's ``_resolve_session_id``)
    rather than a raw import.
    """
    if _REGISTRY_LIB_DIR not in sys.path:
        sys.path.insert(0, _REGISTRY_LIB_DIR)
    import cc_invoke

    cc_invoke.ensure_engine_on_path(__file__)
    from coordinator_core.win_portability import same_path

    return same_path(a, b)


def repo_key_to_em_id(key: str) -> str:
    """Reverse a repos.<name> registry key to its EM identity string.

    Special-case: repos.doe_claude → the manifest-derived canonical central
    identity (see _central_canonical_id() — identity.centralReceiverIds[0],
    currently "doe-claude-em"). "claude-central-em", "central-em" and "central"
    were RETIRED OUTRIGHT from identity.centralReceiverIds by DoE at their
    b787bf0f0 (2026-08-26): they are not aliases, not members of
    CENTRAL_RECEIVER_IDS, and do not resolve — their absence is the operative
    rule and a send to one is meant to fail loudly. Sequenced with this repo's
    own test_central_receiver_ids narrowing at 4164ae195.

    Otherwise applies REPO_ALIASES for doctrine-shortname divergence (e.g.
    example_game_workbench_repo → example-game-repo → example-game-repo-em), then converts remaining
    underscores to dashes.

    Callers are expected to pass fully-qualified `repos.<name>` keys; bare keys
    are handled defensively but unsupported.

    Negative-spec: the ~/.claude/home path is NOT special-cased here — central
    identity is anchored on repos.doe_claude, not the home directory.
    """
    if key == "repos.doe_claude":
        return _central_canonical_id()
    shortname = key[len("repos."):] if key.startswith("repos.") else key
    canonical = REPO_ALIASES.get(shortname)
    if canonical is not None:
        return canonical + "-em"
    return shortname.replace("_", "-") + "-em"


def em_id_for_root(root: str | None, repo_key_paths: dict[str, str]) -> str:
    """Resolve a repo root path to its EM identity string.

    Resolution order:
      1. root is None  → 'unknown-sender-em'
      2. root path-matches repo_key_paths['repos.doe_claude']  → the manifest-derived
         canonical central identity (see _central_canonical_id())
      3. root path-matches any other registered repos.* path   → repo_key_to_em_id(key)
      4. unregistered git repo  → basename(root) + '-em'

    Negative-spec: the old ~/.claude/home special-case is REMOVED — ~/.claude is no
    longer a memo-identity anchor. Central identity flows through repos.doe_claude only.
    """
    if root is None:
        return "unknown-sender-em"
    doe_claude_path = repo_key_paths.get("repos.doe_claude")
    if doe_claude_path and _same_path(root, doe_claude_path):
        return _central_canonical_id()
    for key, path in repo_key_paths.items():
        if path and _same_path(path, root):
            return repo_key_to_em_id(key)
    return os.path.basename(root.rstrip("/\\")) + "-em"


# ---------------------------------------------------------------------------
# Shared state-root resolver — DoE doctrine central-state writes
#
# doe_root() is the canonical resolver for the DoE repo root, importable by all
# doctrine-writing CLIs. The resolution chain mirrors the engine root resolver's shape
# in the CLIs but raises on failure rather than returning None — callers catch
# _DoeUnresolvable and degrade gracefully (WARN + skip, exit 0).
#
# CONCERN-BOUNDARY: doe_root() (state-root axis) is INDEPENDENT of
# em_id_for_root/_resolve_from_repo() (identity axis). Both read repos.doe_claude
# but as orthogonal consumers — state-root vs. identity. Do NOT merge them.
# The shared surface is the machine-local reader only.
#
# Spec backlink: DoE-claude:pln-gate-2-w2-3-live-caller-switch-3e51cf § C1
# ---------------------------------------------------------------------------

# Env var for DOE_ROOT override — mirrors the engine root's §4b idempotency gate form.
# Guard form: os.environ.get(_DOE_ROOT_ENV, "").strip() — non-empty string wins.
_DOE_ROOT_ENV = "DOE_ROOT"

# Env var for REPO_DOE_CLAUDE override — the documented, ambient name. Every
# coordinator_core referent (26 of them, via ops/coordinator_doe_root.py)
# binds this name, and the engine repo's generated shell shim exports it into cold
# login shells (see coordinator_core/install/sandbox_check.py AC2) — so in
# normal operation it is already set, not merely available as an escape
# hatch. DOE_ROOT (above) is a permanent legacy alias and still wins first
# when both are set — that ordering is load-bearing and preserves every
# existing test/consumer byte-for-byte.
_REPO_DOE_CLAUDE_ENV = "REPO_DOE_CLAUDE"

# _REGISTRY_MACHINE_LOCAL_IMPL_ENV is defined earlier, ahead of the manifest
# bootstrap block, since the codename-free rung ladder's registry rung needs
# it at import time. Review: code-reviewer (F4) — the sibling
# _REGISTRY_CLAUDE_HOME_ENV constant was deleted here: dead since
# _registry_claude_home() delegates to machine_local_impl_resolve.claude_home()
# (hardcodes "CLAUDE_HOME" internally).


class _DoeUnresolvable(RuntimeError):
    """Raised when the DoE root cannot be resolved via env var (REPO_DOE_CLAUDE,
    or the permanent legacy alias DOE_ROOT) or machine-local registry.

    Callers in the doctrine central write loop catch this and degrade gracefully
    (WARN + skip, exit 0). The resolver itself fails loud via this exception;
    this is the caller-layer resilience wrapper.

    Negative-spec: this exception is NOT raised for per-project (cwd-relative) writes —
    only for central doctrine writes that require the DoE repo root.

    Spec backlink: DoE-claude:pln-gate-2-w2-3-live-caller-switch-3e51cf § C1
    """


def _registry_claude_home() -> str:
    """Return the ~/.claude root, honoring CLAUDE_HOME env var for test isolation.

    Delegates to machine_local_impl_resolve.claude_home() — see that module's
    docstring for why the settings-home-first ladder now lives there, shared
    across every caller that used to hand-roll this same join.
    """
    return _mlir_claude_home()


# _registry_machine_local_impl() / _registry_machine_local_get() are defined
# earlier, ahead of the manifest bootstrap block, since the codename-free rung
# ladder's registry rung (rung 5) needs them at import time.


def doe_root() -> str:
    """Resolve the DoE repo root for doctrine central-state writes.

    Resolution chain — Review: staff-eng MAJOR-4 put the explicit env-var
    override rungs FIRST, ahead of the codename-free rungs, restoring
    "REPO_DOE_CLAUDE/DOE_ROOT is the documented override" as true fact (an
    operator's stated intent cannot be present by accident; ambient
    file/registry state must not outrank it).

    DR-071 reorder (2026-08-10): the machine-local `repos.doe_claude`
    registry rung now runs immediately after the env overrides and AHEAD of
    the codename-free ladder, matching `coordinator_core/ops/
    coordinator_doe_root.py`'s DR-071-mandated order (review finding B2,
    state/review-findings/2026-08-08-codename-free-partitioned/
    slice-B-doe-root.md). Previously this rung ran LAST, so a codename-free
    candidate that also happened to resolve (a stale marketplace install
    left from an earlier `coordinator:install`, or a genuinely published/
    scrubbed plugin cache) silently outranked the registry's correctly
    registered private DoE-claude tree — exactly the DR-071 violation B2
    fixed in the ops-module twin, except that finding's own coverage note
    named this module as explicitly not reviewed/reordered at the time. See
    cross-repo/inbox/2026-08-10-doe-claude-em-reconcile-close-terminal-and-scrub-key.md
    § 3 for the live incident this closes (`cross-repo-memo` send path
    resolving the scrubbed `repos.example_doctrine_repo` registry key via
    this exact ordering gap).

      1a. DOE_ROOT env var — if non-empty, trusted as-is (§4b idempotency parity
          with the engine root; guard form os.environ.get(..., "").strip()). Wins
          first when both DOE_ROOT and REPO_DOE_CLAUDE are set — a permanent
          legacy alias, preserved byte-for-byte for every existing test/consumer.
      1b. REPO_DOE_CLAUDE env var — the documented, ambient override name every
          coordinator_core referent binds (see _REPO_DOE_CLAUDE_ENV docstring
          above). Consulted only when rung 1a is unset/empty.
      2.  machine-local get repos.doe_claude — the DR-071 canonical,
          authoritative coordinator-root anchor. Delegates to the §4c
          discovery ladder via the same _machine_local.py reader the identity
          flip uses.
      3-4. `.doe-root` pointer (durable settings-home, then legacy
           `~/.claude/.doe-root`) — see _mp_doe_root_pointer_rung(). Already
           returns the DoE REPO root directly (coordinator_read_doe_root_pointer()
           reads exactly that), no conversion needed. Only reached when rung 2
           returns nothing.
      5.  Claude Code's real marketplace-cache install location — see
          _mp_marketplace_cache_rung() (Review: staff-eng BLOCKER-1).
          Resolves to the repo root directly, same contract as rung 6.
      6.  Flat `~/.claude/plugins/coordinator-claude` marketplace-clone layout
          — see _mp_flat_layout_probe_rung(). resolve_coordinator_clone.py
          treats this same path as the repo/clone root directly (its
          resolve_clone_root() rung 4), so it is used as-is here too. Gated
          (Review: staff-eng BLOCKER-2) on `<cand>/state` being a directory —
          this ladder promises callers a root state/ hangs off, not merely
          any directory that satisfies the marker check.
      7.  CLAUDE_PLUGIN_ROOT — a *content* root, not necessarily the repo
          root (see resolve_content_root()'s `<root>/coordinator` shape for
          the private/dev layout). Normalized via
          _mp_repo_root_from_plugin_root_candidate(allow_unchanged_fallback=False)
          before use (Review: staff-eng BLOCKER-2 — an unrecognized
          candidate yields "", never itself: CLAUDE_PLUGIN_ROOT names
          whichever plugin's hook/command is currently executing, which is
          routinely a DIFFERENT plugin than coordinator; passing it through
          unchanged let an unrelated repo win over an explicit correct
          override). Also gated on `<cand>/state` being a directory.
      8.  machine-local `plugin.mirrors.coordinator-claude.live_path` —
          Review: staff-eng MAJOR-3 — this is the SAME class of value as
          CLAUDE_PLUGIN_ROOT (a content root in the private/dev layout,
          `<repo_root>/coordinator`) and is now routed through the same
          normalizer + state/ gate rather than trusted as a repo root
          unconverted. resolve_coordinator_clone.py's resolve_clone_root()
          does NOT, in fact, use this value directly as claimed by earlier
          commit messages in this workstream — its rung 2 gates on
          `os.path.isdir(os.path.join(live, ".git"))`, which is exactly the
          check that filters a content root out; this rung reproduces that
          intent via the repo-root normalizer instead.
      None of rungs 3-8 contain a private codename, so the OSS depersonalize
      scrub cannot touch them directly — mirrors the manifest bootstrap
      ladder above — but per DR-071 they must still rank BELOW rung 2's
      registry anchor, since a codename-free rung is reachable through a
      genuinely published/scrubbed install.
      9.  Raises _DoeUnresolvable when no rung resolves.

    Returns the DoE REPO root (e.g. /path/to/DoE-claude). Callers append
    state/<class>/ to build the full write path:
      os.path.join(doe_root(), "state", "lessons-outbox")
      os.path.join(doe_root(), "state", "improvement-queue")

    Negative-spec: the state/ subdirectory is NOT included in the return value.
    Callers must NOT pass the return value to os.path.join(..., "state", "state", ...).

    Negative-spec: INDEPENDENT of em_id_for_root/_resolve_from_repo() — both use
    repos.doe_claude but for orthogonal axes (state-root vs. identity). Do NOT merge.

    Spec backlink: DoE-claude:pln-gate-2-w2-3-live-caller-switch-3e51cf § C1
    Spec backlink: pln-the-published-engine-resolves-ae0bf7 § C1D
    """
    override = os.environ.get(_DOE_ROOT_ENV, "").strip()
    if override:
        return override
    override = os.environ.get(_REPO_DOE_CLAUDE_ENV, "").strip()
    if override:
        return override

    # DR-071 canonical anchor: the machine-local repos.doe_claude registry
    # entry, ranked ABOVE the codename-free ladder below. Previously this
    # rung ran LAST (after every codename-free candidate) — the same
    # precedence defect `coordinator_core/ops/coordinator_doe_root.py` fixed
    # per review finding B2 (state/review-findings/2026-08-08-codename-free-
    # partitioned/slice-B-doe-root.md), whose own coverage note named this
    # module as explicitly not reviewed/reordered at the time. On a box
    # where the registry correctly names the private DoE-claude tree but a
    # codename-free rung ALSO resolves (e.g. a stale or genuinely published
    # marketplace install), the ladder below used to win, silently returning
    # a byte-copy install instead of the registry-anchored source tree — see
    # state/review-findings/2026-08-08-codename-free-partitioned/slice-B-doe-root.md
    # § B2 (the primary precedence evidence; the separate
    # cross-repo/inbox/2026-08-10-doe-claude-em-reconcile-close-terminal-and-scrub-key.md
    # § 3 incident is a scrubbed registry key masking a cross-repo-memo
    # send-path defect, not this precedence issue).
    #
    # This registry read is now in-process (machine_local_impl_resolve.
    # registry_get()), CLI spawn retained as the fallback rung.
    val = _registry_machine_local_get("repos.doe_claude")
    if val:
        return val

    _dr_pointer_root = _mp_doe_root_pointer_rung()
    if _dr_pointer_root and os.path.isdir(_dr_pointer_root):
        return _dr_pointer_root

    for _dr_root in (
        _mp_marketplace_cache_rung(),
        _mp_flat_layout_probe_rung(),
    ):
        if _dr_root and os.path.isdir(_dr_root) and os.path.isdir(os.path.join(_dr_root, "state")):
            return _dr_root

    _dr_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "").strip()
    if _dr_plugin_root:
        _dr_normalized = _mp_repo_root_from_plugin_root_candidate(_dr_plugin_root, allow_unchanged_fallback=False)
        if _dr_normalized and os.path.isdir(_dr_normalized) and os.path.isdir(os.path.join(_dr_normalized, "state")):
            return _dr_normalized

    _dr_live_path = _registry_machine_local_get("plugin.mirrors.coordinator-claude.live_path") or ""
    if _dr_live_path:
        _dr_live_normalized = _mp_repo_root_from_plugin_root_candidate(_dr_live_path, allow_unchanged_fallback=False)
        if (
            _dr_live_normalized
            and os.path.isdir(_dr_live_normalized)
            and os.path.isdir(os.path.join(_dr_live_normalized, "state"))
        ):
            return _dr_live_normalized

    raise _DoeUnresolvable(
        "repos.doe_claude not set in machine-local registry and neither "
        "REPO_DOE_CLAUDE nor DOE_ROOT (legacy alias) env var is set"
    )
