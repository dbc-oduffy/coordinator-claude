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
  RECEIVER_EM_ALIASES — dict shortname → registryKey  (inverse; for cross-repo-memo)
  SIDECAR_SUFFIXES    — dict sidecar-type → filesystem suffix (e.g. "review" → "review")
  DOC_TYPES           — raw docTypes tuple for callers needing schemaName/offerable fields

Shared identity-resolution functions (canonical, importable by all 4 CLIs):
  repo_key_to_em_id(key)                         — repos.<name> → <name>-em, with central anchor
  em_id_for_root(root, repo_key_paths)            — repo root path → em-id string
  _same_path(a, b)                               — internal path-equality helper, importable by the CLIs that need direct comparison

Shared state-root resolver (canonical, importable by all doctrine CLIs):
  doe_root()                         — DoE repo root (env DOE_ROOT → machine-local repos.doe_claude → raise)
  _DoeUnresolvable                   — raised when DoE root is unresolvable; callers catch and WARN+skip (exit 0)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

# ---------------------------------------------------------------------------
# Manifest path — resolved relative to __file__ (bin/lib/ → ../../schemas/).
# Never hardcoded to an absolute path; portable across machines and clones.
# ---------------------------------------------------------------------------
_MANIFEST_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "schemas",
    "coordinator-registry.manifest.json",
)

try:
    with open(_MANIFEST_PATH, encoding="utf-8") as _f:
        _manifest = json.load(_f)
except FileNotFoundError as _e:
    raise FileNotFoundError(
        f"coordinator_registry: manifest not found at {_MANIFEST_PATH!r}. "
        "This is an install-integrity failure — ensure the coordinator plugin is fully installed."
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
# Spec backlink: docs/plans/2026-07-05-central-identity-flip-completion.md § C1
# ---------------------------------------------------------------------------


def _same_path(a: str, b: str) -> bool:
    """True if two paths resolve to the same directory (cross-platform).

    Uses os.path.samefile when both paths exist; falls back to normcase+realpath
    string comparison so absent/unregistered repos never raise.
    """
    try:
        return os.path.samefile(a, b)
    except OSError:
        return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def repo_key_to_em_id(key: str) -> str:
    """Reverse a repos.<name> registry key to its EM identity string.

    Special-case: repos.doe_claude → claude-central-em (canonical central identity;
    doe-claude-em is the alias in CENTRAL_RECEIVER_IDS, but the canonical return is
    claude-central-em so downstream comparisons use one string).

    Otherwise applies REPO_ALIASES for doctrine-shortname divergence (e.g.
    example_game_workbench_repo → example-game-repo → example-game-repo-em), then converts remaining
    underscores to dashes.

    Callers are expected to pass fully-qualified `repos.<name>` keys; bare keys
    are handled defensively but unsupported.

    Negative-spec: the ~/.claude/home path is NOT special-cased here — central
    identity is anchored on repos.doe_claude, not the home directory.
    """
    if key == "repos.doe_claude":
        return "claude-central-em"
    shortname = key[len("repos."):] if key.startswith("repos.") else key
    canonical = REPO_ALIASES.get(shortname)
    if canonical is not None:
        return canonical + "-em"
    return shortname.replace("_", "-") + "-em"


def em_id_for_root(root: str | None, repo_key_paths: dict[str, str]) -> str:
    """Resolve a repo root path to its EM identity string.

    Resolution order:
      1. root is None  → 'unknown-sender-em'
      2. root path-matches repo_key_paths['repos.doe_claude']  → 'claude-central-em'
      3. root path-matches any other registered repos.* path   → repo_key_to_em_id(key)
      4. unregistered git repo  → basename(root) + '-em'

    Negative-spec: the old ~/.claude/home special-case is REMOVED — ~/.claude is no
    longer a memo-identity anchor. Central identity flows through repos.doe_claude only.
    """
    if root is None:
        return "unknown-sender-em"
    doe_claude_path = repo_key_paths.get("repos.doe_claude")
    if doe_claude_path and _same_path(root, doe_claude_path):
        return "claude-central-em"
    for key, path in repo_key_paths.items():
        if path and _same_path(path, root):
            return repo_key_to_em_id(key)
    return os.path.basename(root.rstrip("/\\")) + "-em"


# ---------------------------------------------------------------------------
# Shared state-root resolver — DoE doctrine central-state writes
#
# doe_root() is the canonical resolver for the DoE repo root, importable by all
# doctrine-writing CLIs. The resolution chain mirrors the _example_orchestration_hub_root() shape
# in the CLIs but raises on failure rather than returning None — callers catch
# _DoeUnresolvable and degrade gracefully (WARN + skip, exit 0).
#
# CONCERN-BOUNDARY: doe_root() (state-root axis) is INDEPENDENT of
# em_id_for_root/_resolve_from_repo() (identity axis). Both read repos.doe_claude
# but as orthogonal consumers — state-root vs. identity. Do NOT merge them.
# The shared surface is the machine-local reader only.
#
# Spec backlink: docs/plans/2026-07-06-gate2-w23-state-seam-caller-switch.md § C1
# ---------------------------------------------------------------------------

# Env var for DOE_ROOT override — mirrors EXAMPLE_ORCHESTRATION_HUB_ROOT §4b idempotency gate form.
# Guard form: os.environ.get(_DOE_ROOT_ENV, "").strip() — non-empty string wins.
_DOE_ROOT_ENV = "DOE_ROOT"

# Env var names honoured by the internal machine-local reader — shared with the CLIs
# so a single test-isolation set covers all callers (MACHINE_LOCAL_IMPL, CLAUDE_HOME).
_REGISTRY_MACHINE_LOCAL_IMPL_ENV = "MACHINE_LOCAL_IMPL"
_REGISTRY_CLAUDE_HOME_ENV = "CLAUDE_HOME"


class _DoeUnresolvable(RuntimeError):
    """Raised when DOE_ROOT cannot be resolved via env var or machine-local registry.

    Callers in the doctrine central write loop catch this and degrade gracefully
    (WARN + skip, exit 0). The resolver itself fails loud via this exception;
    this is the caller-layer resilience wrapper.

    Negative-spec: this exception is NOT raised for per-project (cwd-relative) writes —
    only for central doctrine writes that require the DoE repo root.

    Spec backlink: docs/plans/2026-07-06-gate2-w23-state-seam-caller-switch.md § C1
    """


def _registry_claude_home() -> str:
    """Return the ~/.claude root, honoring CLAUDE_HOME env var for test isolation."""
    override = os.environ.get(_REGISTRY_CLAUDE_HOME_ENV)
    if override:
        return override
    return os.path.join(os.path.expanduser("~"), ".claude")


def _registry_machine_local_impl() -> str:
    """Return the path to _machine_local.py, honoring MACHINE_LOCAL_IMPL for tests."""
    override = os.environ.get(_REGISTRY_MACHINE_LOCAL_IMPL_ENV)
    if override:
        return override
    return os.path.join(_registry_claude_home(), "bin", "_machine_local.py")


def _registry_machine_local_get(key: str) -> str | None:
    """Call machine-local get <key> and return the value, or None on failure.

    Uses sys.executable (the interpreter running this module) — no subprocess
    probing needed; safe on macOS, Linux, and Windows. CREATE_NO_WINDOW guard
    suppresses the Windows console popup (portable: getattr resolves to 0 on
    non-Windows).
    """
    impl = _registry_machine_local_impl()
    cmd = [sys.executable, impl, "get", key]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.strip()


def doe_root() -> str:
    """Resolve the DoE repo root for doctrine central-state writes.

    Resolution chain (three-rung, env → machine-local → hard-error):
      1. DOE_ROOT env var — if non-empty, trusted as-is (§4b idempotency parity
         with EXAMPLE_ORCHESTRATION_HUB_ROOT; guard form os.environ.get(..., "").strip()).
      2. machine-local get repos.doe_claude — delegates to the §4c discovery ladder
         via the same _machine_local.py reader the identity flip uses.
      3. Raises _DoeUnresolvable when neither rung resolves.

    Returns the DoE REPO root (e.g. /path/to/DoE-claude). Callers append
    state/<class>/ to build the full write path:
      os.path.join(doe_root(), "state", "lessons-outbox")
      os.path.join(doe_root(), "state", "improvement-queue")

    Negative-spec: the state/ subdirectory is NOT included in the return value.
    Callers must NOT pass the return value to os.path.join(..., "state", "state", ...).

    Negative-spec: INDEPENDENT of em_id_for_root/_resolve_from_repo() — both use
    repos.doe_claude but for orthogonal axes (state-root vs. identity). Do NOT merge.

    Spec backlink: docs/plans/2026-07-06-gate2-w23-state-seam-caller-switch.md § C1
    """
    override = os.environ.get(_DOE_ROOT_ENV, "").strip()
    if override:
        return override
    val = _registry_machine_local_get("repos.doe_claude")
    if val:
        return val
    raise _DoeUnresolvable(
        "repos.doe_claude not set in machine-local registry and DOE_ROOT env var not set"
    )
