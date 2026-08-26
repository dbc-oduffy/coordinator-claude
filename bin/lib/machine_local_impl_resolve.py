"""machine_local_impl_resolve — single canonical settings-home-first resolver
for the on-disk `_machine_local.py` reader path (and its sibling
`machine-local` CLI forwarder path).

Purpose: 7 call sites across `coordinator/bin/` and `coordinator/bin/lib/`
independently hand-rolled a byte-identical `_claude_home()` +
`_machine_local_impl()` pair that joined `<claude_home>/bin/_machine_local.py`
UNCONDITIONALLY — no settings-home rung at all. That directly violates DR-210
Amendment 2026-07-24 ("coordinator resolves nothing through `~/.claude/bin`")
and, worse, is drift-prone: independently-maintained copies of the same
two-line join is exactly the duplication class that let 456 call sites miss a
caller sweep on 2026-07-22 (see DoE-claude CLAUDE.local.md § Repo-specific
gotchas). This module is the resolver the seven callers now delegate to:
`coordinator-doc-new`, `coordinator-lesson-add`, `cross-repo-memo`,
`cli_shared.py`, `coordinator_registry.py`, `cc_invoke.py`,
`resolve-repo-path.py`.

``claude_home()`` additionally inlines the ``CLAUDE_CONFIG_DIR`` rung that
``coordinator_core._settings_home.claude_config_dir()`` established (added
2026-08-08, DR seam: ``CLAUDE_CONFIG_DIR`` is the harness's own env var naming
the config directory itself, ahead of this fleet's own ``CLAUDE_HOME``
invention naming its parent). This module cannot import ``_settings_home``
— it must stay import-free of `coordinator_core` for its six `bin/` callers'
standalone use — so the rung is duplicated inline here, following this
module's own established precedent of already inlining the ``CLAUDE_HOME``
chain for that same self-containment reason. Keep ``claude_home()`` in step
by hand with ``claude_config_dir()`` whenever its precedence changes.

Two deliberate exceptions inline this same ladder rather than importing this
module, for the same self-contained/no-recursion reason — keep BOTH in sync
by hand when this module's precedence rule changes:
  - `gen-claude-klabauter-root-pointer.py` (see that file's own docstring) (review:
    code-reviewer F5/F6).
  - `coordinator/bin/machine-local` (its own docstring gives the recursion
    rationale: engine-root resolution itself shells out to machine-local, so
    a trampoline that imports this module here would recurse). This second
    exception was not originally listed here, which is how its inline copy
    drifted from this ladder (dropped the `CLAUDE_HOME` rung) unnoticed
    until a review caught it — now corrected and listed.

Resolution order (settings-home FIRST, mirror LAST — mirrors
`coordinator_core.pyresolve._machine_local_impl()`, the pre-existing correct
ladder this module generalizes into a reusable, importable form):
  1. `<env_override>` (default `MACHINE_LOCAL_IMPL`) — test-isolation escape
     hatch, honoured byte-identically to every caller's pre-existing contract.
  2. `<settings-home>/bin/_machine_local.py` — canonical home (DR-071/072).
  3. `<claude_home>/bin/_machine_local.py` — retired compat mirror, kept as a
     last-resort fallback only (never removed — DR-210 Amendment retires the
     mirror as a RESOLUTION-ORDER concern, not an existence concern).

Negative-spec: does NOT remove, neuter, or stop-populating the mirror rung —
callers on a machine where settings-home is somehow absent/incomplete must
still resolve via the mirror. This module changes precedence only.

Spec backlink: this repo's own state/audits/2026-07-25-claude-bin-mirror-read-
  rungs.md (work-list); DoE-claude state/audits/2026-07-24-claude-bin-compat-
  mirror-binding-audit.md (VERDICT: HAS-BINDINGS); docs/decisions/
  DR-210-claude-klabauter-native-tooling-ownership-strangler.md Amendment 2026-07-24
  ("resolves nothing through ~/.claude/bin").

``registry_dir()``/``registry_get()`` (added for the "root rung 2 stops
spawning" chunk) extend this module's by-hand-parity obligation to a third
pair, alongside ``claude_home``/``settings_home`` above: they are a
spawn-free, direct-``tomllib`` port of
``coordinator_core.machine_resolver.registry_dir``/``registry_get``, pinned
to that oracle by this module's own ``test_machine_local_registry_reader_
parity.py`` for every case EXCEPT the divergences enumerated below — this is
NOT a blanket byte-for-byte parity claim. Three divergences are ACCEPTED and
do not fall under that parity obligation:
  1. Fallback base is ``CLAUDE_HOME or HOME or USERPROFILE or
     expanduser("~")`` here, vs. ``CLAUDE_HOME`` else ``Path.home()`` there —
     under MSYS, ``HOME`` and ``USERPROFILE`` can differ. (Inherited from
     this module's pre-existing ``settings_home()`` above, not introduced by
     ``registry_dir``/``registry_get``.)
  2. ``_settings_home`` raises ``ValueError`` (via ``_require_rooted``) on a
     cwd-relative ``COORDINATOR_SETTINGS_HOME``/``CLAUDE_HOME`` override;
     this module accepts one silently. (Same inheritance as #1.)
  3. ``registry_get`` repairs an MSYS/Cygwin mount-form return value
     (``/<drive>/...`` -> ``<drive>:/...``) on BOTH the env-override rung and the
     file-read rung, byte-equivalently to
     ``coordinator_core._settings_home.native_path_form``; the oracle
     ``machine_resolver.registry_get`` does no normalization anywhere in its
     body and returns such a value raw — normalization is a caller
     responsibility there. This is a DELIBERATE divergence, not an oversight:
     this module's callers are `coordinator/bin/` CLIs whose CLI-spawn
     fallback rung already returned normalized values, so normalizing here
     removes a latent inconsistency at that seam rather than introducing one.
     This module cannot import ``coordinator_core._settings_home`` (see HARD
     CONSTRAINT below), so the repair is inlined here, following the same
     by-hand-parity precedent as ``claude_home``/``settings_home``. Precedent
     for wrapping a registry-read return value in this repair:
     ``coordinator_core.ops.gen_doe_root_pointer._resolve_doe_root`` wraps
     both of its rungs (env override, registry read) in
     ``native_path_form(...)`` before returning — the collector's own
     2026-08-16 "REPOS.* LADDER-LOSS FIX" note documents why a stored
     backslash form is a real, live value on this box that must not be
     silently dropped. Pinned (not merely documented) by
     ``test_registry_get_repairs_msys_mount_form_for_repos_key``, which
     asserts both ``mlir.registry_get`` returns the repaired native form AND
     ``machine_resolver.registry_get`` returns the raw stored value —
     i.e. it asserts ``mine != theirs`` for this exact case, so the
     divergence cannot silently drift back into unintended parity or
     unintended non-parity.

HARD CONSTRAINT: this module MUST NOT import ``coordinator_core``, directly
or under a ``try/except ImportError`` guard — a guarded import makes
resolution depend on ``sys.path`` state, so two otherwise-identical boxes
could silently resolve differently with no signal. ``registry_get``/
``registry_dir`` therefore reimplement the direct-``tomllib`` read rather
than delegating to ``coordinator_core.machine_resolver``.
"""
from __future__ import annotations

import os
import re


def claude_home() -> str:
    """Return the ``~/.claude`` root, honouring ``CLAUDE_CONFIG_DIR`` (the
    harness's own env var naming the config directory itself) ahead of
    ``CLAUDE_HOME`` (this fleet's own invention naming its *parent*), for
    test isolation and to keep this module's resolution in step with the
    canonical ``coordinator_core._settings_home.claude_config_dir()`` seam.

    Precedence mirrors ``claude_config_dir()`` exactly: ``CLAUDE_CONFIG_DIR``
    first, else the ``CLAUDE_HOME``-derived ``<home>/.claude``. This module
    cannot import that seam (see module docstring — the whole point of this
    file is to stay importable by scripts that never establish
    ``coordinator_core`` on ``sys.path``), so the rung is duplicated inline
    here, matching this module's own existing precedent of inlining the
    ``CLAUDE_HOME`` chain for the same self-containment reason. Keep this in
    step by hand with ``claude_config_dir()`` when its precedence changes."""
    config_dir_override = os.environ.get("CLAUDE_CONFIG_DIR")
    if config_dir_override:
        return config_dir_override
    override = os.environ.get("CLAUDE_HOME")
    if override:
        return override
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE") or os.path.expanduser("~")
    return os.path.join(home, ".claude")


def settings_home() -> str:
    """Return the coordinator settings-home root, honouring
    ``COORDINATOR_SETTINGS_HOME`` first and falling back to
    ``${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings``.

    NOTE: the fallback base is ``CLAUDE_HOME or HOME or USERPROFILE or
    expanduser("~")`` directly — NOT
    ``claude_home()`` (which itself appends ``/.claude``). Using
    ``claude_home()`` here would nest settings-home one level too deep
    (``~/.claude/.coordinator-claude-settings`` instead of the canonical
    ``~/.coordinator-claude-settings``) — mirrors every existing correct
    inline copy of this ladder (`gen-claude-klabauter-root-pointer.py::_settings_home`,
    `cc_invoke.py::_resolve_claude_klabauter_root`'s inline settings-home block).

    Inlined rather than importing ``coordinator_core._settings_home`` —
    mirrors `cc_invoke.py::_resolve_claude_klabauter_root`'s documented rationale
    ("kept inline here for the same single-file-module reason
    `_machine_local.py` documents — no cross-file import hack across the
    source/install-tree split"): this module lives in `coordinator/bin/lib/`
    and must stay importable by scripts that never establish `coordinator_core`
    on `sys.path`.
    """
    override = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if override:
        return override
    home = (
        os.environ.get("CLAUDE_HOME")
        or os.environ.get("HOME")
        or os.environ.get("USERPROFILE")
        or os.path.expanduser("~")
    )
    return os.path.join(home, ".coordinator-claude-settings")


def machine_local_impl_path(env_override: "str | None" = "MACHINE_LOCAL_IMPL") -> str:
    """Resolve the on-disk path to ``_machine_local.py``, settings-home first.

    ``env_override`` names the test-isolation env var to consult first — pass
    ``None`` to skip that check entirely for a caller whose pre-existing
    contract never honoured one (e.g. `cc_invoke.py`, which must not gain new
    env-var-triggered behavior as a side effect of this precedence fix).

    Returns the settings-home candidate if it exists on disk; otherwise falls
    back to the (possibly-nonexistent) mirror candidate unconditionally — the
    caller is expected to `os.path.exists`/`os.path.isfile`-check the result
    before use, exactly as every pre-existing caller already does. This
    mirrors `coordinator_core.pyresolve._machine_local_impl()`'s existing,
    correctly-ordered ladder.
    """
    override = os.environ.get(env_override) if env_override else None
    if override:
        return override
    settings_home_impl = os.path.join(settings_home(), "bin", "_machine_local.py")
    if os.path.exists(settings_home_impl):
        return settings_home_impl
    return os.path.join(claude_home(), "bin", "_machine_local.py")


def windows_cmd_first_candidates(bases: "list[str]") -> "list[str]":
    """Given ordered base paths (extensionless), return the candidate list a
    caller should probe: on Windows, try ``<base>.cmd`` before the bare
    ``<base>`` for EACH base in order (``CreateProcess`` does not consult
    ``PATHEXT``, so a bare extensionless invocation of a delivered ``.cmd``
    silently fails); on every other platform, return ``bases`` unchanged.

    Review: code-reviewer F2 — extracted from `resolve-repo-path.py`'s
    `_machine_local_path_candidates()` (which had this logic correct) so
    `machine_local_bin_candidates()` below stops silently omitting it — the
    duplication-avoidance this whole module exists for, applied to itself.
    """
    if os.name == "nt":
        candidates: "list[str]" = []
        for base in bases:
            candidates.extend([base + ".cmd", base])
        return candidates
    return bases


def machine_local_bin_candidates() -> list[str]:
    """Return ordered candidate paths for the ``machine-local`` CLI forwarder
    itself (distinct from `_machine_local.py`, the reader it forwards to) —
    settings-home first, mirror last, `.cmd`-first-per-base on Windows (see
    `windows_cmd_first_candidates()`). Used by callers that shell out to the
    `machine-local` CLI directly rather than invoking `_machine_local.py` via
    `sys.executable`.
    """
    bases = [
        os.path.join(settings_home(), "bin", "machine-local"),
        os.path.join(claude_home(), "bin", "machine-local"),
    ]
    return windows_cmd_first_candidates(bases)


def registry_dir() -> str:
    """Resolve the machine-local registry directory — spawn-free, no
    ``coordinator_core`` import (see module docstring's HARD CONSTRAINT).

    ``MACHINE_LOCAL_REGISTRY_DIR`` env override first (test isolation),
    else ``<settings_home()>/machine-local``. MUST call this module's own
    ``settings_home()`` above rather than re-deriving the
    ``COORDINATOR_SETTINGS_HOME or <fallback>`` chain inline — mirrors
    ``coordinator_core.machine_resolver.registry_dir`` +
    ``_settings_home.machine_local_dir``.
    """
    override = os.environ.get("MACHINE_LOCAL_REGISTRY_DIR")
    if override:
        return override
    return os.path.join(settings_home(), "machine-local")


def _native_path_form(raw: str) -> str:
    """Byte-equivalent inline port of
    ``coordinator_core._settings_home.native_path_form`` — the MSYS/Cygwin
    mount-form repair (``/<drive>/...`` -> ``<drive>:/...``), gated to ``os.name ==
    "nt"``. This module cannot import that seam (see module docstring's HARD
    CONSTRAINT), so the repair is duplicated here under the same
    by-hand-parity obligation ``claude_home``/``settings_home`` already
    carry. NOT a general path canonicalizer: resolves nothing, expands
    nothing, strips no trailing separator — the sole transform is the
    mount-form repair."""
    s = str(raw)
    if os.name != "nt":
        return s
    m = re.match(r"^/(?:cygdrive/)?([A-Za-z])(/.*)?$", s)
    if m:
        return m.group(1).upper() + ":" + (m.group(2) or "/")
    return s


def _env_override_key(key: str) -> str:
    """Convert a dotted registry key to its env-var override name — mirrors
    ``coordinator_core.machine_resolver._env_override_key``."""
    return "MACHINE_LOCAL_" + key.upper().replace(".", "_")


def _load_toml_flat(path: str) -> dict:
    """Load and flatten one registry TOML file. Degrades to ``{}`` on any
    absent/malformed file or missing ``tomllib``/``tomli`` — never raises.
    Mirrors ``coordinator_core.machine_resolver._load_toml`` +
    ``_flatten`` byte-for-byte, including the ``tomli`` fallback import."""
    if not os.path.isfile(path):
        return {}
    try:
        import tomllib as _tomllib  # type: ignore[import-not-found]
    except ImportError:
        try:
            import tomli as _tomllib  # type: ignore[no-redef]
        except ImportError:
            return {}
    try:
        with open(path, "rb") as f:
            data = _tomllib.load(f)
    except Exception:  # noqa: BLE001 — faithful catch-all; malformed registry degrades to "not found"
        return {}
    return _flatten_registry_table(data)


def _flatten_registry_table(data: dict, prefix: str = "") -> dict:
    """Flatten nested TOML tables into dotted keys, excluding any
    ``schema``/``concerns``-keyed table at EVERY nesting level (not only the
    root) — mirrors ``coordinator_core.machine_resolver._flatten`` exactly."""
    out: dict = {}
    for k, v in data.items():
        if k in ("schema", "concerns"):
            continue
        full = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flatten_registry_table(v, prefix=f"{full}."))
        else:
            out[full] = v
    return out


def registry_get(key: str) -> "str | None":
    """Resolve a dotted registry key, or ``None`` if unresolved — spawn-free,
    no ``coordinator_core`` import (see module docstring's HARD CONSTRAINT).

    Resolution order: ``MACHINE_LOCAL_<KEY>`` env override (``"MACHINE_LOCAL_"
    + key.upper().replace(".", "_")``) -> ``registry.local.toml`` ->
    ``registry.toml``, each loaded via ``tomllib``/``tomli`` and flattened to
    dotted keys. Empty string is NOT-FOUND (falls through to the next rung).
    A list value joins with ``"\\n"``. A malformed or absent file degrades to
    ``{}``, never raises. Mirrors
    ``coordinator_core.machine_resolver.registry_get`` for every case EXCEPT
    the NORMALIZATION divergence below — NOT a blanket byte-for-byte parity
    claim — pinned by this module's own
    ``test_machine_local_registry_reader_parity.py``.

    NORMALIZATION (deliberate divergence from the oracle — see module
    docstring's "Three divergences ... ACCEPTED" list, item 3): for a
    ``repos.*``-shaped key whose stored value carries an MSYS/Cygwin mount
    form, the return value is repaired to native drive form via
    ``_native_path_form`` before returning, on both the env-override rung and
    the file-read rung. The oracle does not do this."""
    env_override = os.environ.get(_env_override_key(key))
    if env_override:
        return _native_path_form(env_override)

    reg_dir = registry_dir()
    for fname in ("registry.local.toml", "registry.toml"):
        flat = _load_toml_flat(os.path.join(reg_dir, fname))
        if key in flat:
            val = flat[key]
            if isinstance(val, list):
                val = "\n".join(str(i) for i in val)
            s = str(val)
            if s:
                return _native_path_form(s)
    return None
