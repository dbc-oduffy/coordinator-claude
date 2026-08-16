"""
_resolve_claude_klabauter.py — shared resolve-claude-klabauter-bin ladder, extracted from
``coordinator_core.install.substrate._write_agent_forwarder``'s
formerly-inline-per-forwarder body.

Every emitted bin forwarder used to carry its own copy (~50 lines) of the
registry-then-sentinel resolution ladder that locates
``<claude-klabauter-root>/coordinator/bin/`` and validates it before exec'ing into a
target CLI there. With the forwarder SET now derived from a directory
listing (rather than a hand-maintained ~10-entry tuple — see
``substrate.py``'s ``_derive_agent_helper_names``), that duplication would
have scaled to ~127+ near-identical copies of the same ladder. This module
is installed ONCE (alongside every emitted forwarder, in the same shim
dir — settings-home ``bin/`` and the ``~/.claude/bin`` compat mirror) and
imported by each forwarder's now-trivial ~6-line body.

Contract preserved verbatim from the prior inline body (DoE-claude
``coordinator/snippets/resolve-claude-klabauter-bin.md``, DoE commit ``ad7fb0d1``):
registry-key-then-sentinel resolution rungs, ``coordinator/bin`` composition,
the ``..``-traversal guard, on-disk existence checks for the resolved root
and ``coordinator/bin``, an *executable* sentinel probe (``archive-stamp-cli``),
and distinct fail-loud messages for the two on-disk failure modes (wrong/
incomplete checkout vs. stale/partial migration).

Deliberately does NOT carry the ``_cc_trusted``/``.doe-root`` trust-prefix
dance the prior template never carried either — this seam's trust posture
differs from ``cc-root-source-guard``: ``registry.local.toml`` and
``.claude-klabauter-root`` are per-machine, gitignored, operator-authored config under
the operator's own settings-home, not a harness-supplied value an external
actor can steer. What this module DOES check — because a typo'd or stale
config value is a real, non-adversarial failure mode, not a trust boundary —
is exactly the four checks enumerated above.

Spec backlink:
    DoE-claude coordinator/snippets/resolve-claude-klabauter-bin.md (DoE commit ad7fb0d1)
    docs/plans/2026-07-23-... (M1 — forwarder-ladder extraction + derived set)
    cross-repo/inbox/2026-07-22-claude-central-em-forwarder-template-still-execs-dead-doe-bin.md

Port source: coordinator_core.install.substrate._write_agent_forwarder

Review: code-reviewer — sanctioned path-load consumer surface. Underscore-
prefixed names below (``_ml_dir``, ``_registry_value``,
``_resolve_claude_klabauter_root``) are NOT general-purpose public API — this module's
only stable contract for arbitrary callers is
``resolve_claude_klabauter_root_with_class()``, the ``RESOLUTION_*`` constants, and
``resolve_claude_klabauter_bin_dir()``/``exec_cli()``. The ONE declared exception:
``coordinator_core.claude_klabauter_root`` (loaded BY PATH, never imported as a
package — see that module's own docstring) is a named path-load consumer of
``_ml_dir``, ``_registry_value``, and ``_resolve_claude_klabauter_root`` directly, in
its hot-path short-circuit that skips the full
``resolve_claude_klabauter_root_with_class()`` ladder when ``repos.claude_klabauter``
is not registered. Changing ``resolve_claude_klabauter_root_with_class()``'s step-1
precondition (the published-engine-registered-and-usable check) obliges
updating that wrapper's short-circuit in the SAME change — see
``coordinator_core/claude_klabauter_root.py``'s matching declaration, and
``coordinator_core/tests/test_claude_klabauter_root_two_tier.py``'s cross-entrypoint
agreement test (fixture: ``repos.claude_klabauter`` absent) for the
mechanical backstop that catches drift here.
"""
from __future__ import annotations

import os
import runpy
import stat
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple


class ClaudeKlabauterResolutionError(RuntimeError):
    """A fully-formed, fail-loud message ready to write to stderr verbatim.

    Each raise site below matches one distinct failure mode from the ladder
    (missing config, traversal, missing root, missing coordinator/bin,
    missing/non-executable sentinel) — callers must not collapse these into
    a single generic message; see module docstring.
    """


def _settings_home() -> Path:
    """Resolve the coordinator settings home (mirrors _claude_home.py's
    settings_home() precedence, replicated inline here rather than imported
    — this module must stay import-independent of coordinator_core, since it
    is installed standalone into a bare bin/ directory with no package
    context).

    HOME guard (2026-07-28): the Windows claude-doe.cmd -> `bash -c` launch
    chain is a NON-LOGIN, cmd-spawned shell env that can present with
    COORDINATOR_SETTINGS_HOME/CLAUDE_HOME/HOME all empty. The prior body then
    fell back to os.path.expanduser("~"), which returns a LITERAL "~" when no
    home var is resolvable — silently yielding the garbage relative path
    "~/.coordinator-claude-settings"; the shell-equivalent
    "$HOME/.coordinator-claude-settings" with empty $HOME collapses to
    "/.coordinator-claude-settings", which Windows resolves to the current
    DRIVE ROOT (a stray 0-byte X:\\.coordinator-claude-settings was created that
    way, 2026-07-28). This resolver now (a) consults USERPROFILE so a bare
    cmd.exe session with no HOME still resolves on Windows, and (b) fails loud
    (ClaudeKlabauterResolutionError, caught by exec_cli into a clean stderr message)
    rather than returning a path a downstream writer lands junk at. Empty
    COORDINATOR_SETTINGS_HOME still falls through (unchanged) — a launch env
    that exports it empty must not start failing.
    """
    override = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if override:
        return Path(override)
    home = (
        os.environ.get("CLAUDE_HOME")
        or os.environ.get("HOME")
        or os.environ.get("USERPROFILE")
        or ""
    )
    if not home:
        expanded = os.path.expanduser("~")
        if expanded and expanded != "~":
            home = expanded
    if not home:
        raise ClaudeKlabauterResolutionError(
            "ERROR: cannot resolve the coordinator settings home — none of "
            "COORDINATOR_SETTINGS_HOME, CLAUDE_HOME, HOME, or USERPROFILE is set "
            "and '~' is unexpandable (a non-login shell env). Set CLAUDE_HOME or "
            "HOME to your home directory, or launch from a normal shell\n"
        )
    return Path(home) / ".coordinator-claude-settings"


def _ml_dir() -> Path:
    """Resolve the machine-local registry directory.

    Negative-spec: does NOT validate ``MACHINE_LOCAL_REGISTRY_DIR`` itself —
    by the time this override is read, the operator has already selected
    the file; a guard here would be vacuous (the value has no independent
    "before use" moment to police).
    """
    override = os.environ.get("MACHINE_LOCAL_REGISTRY_DIR")
    return Path(override) if override else (_settings_home() / "machine-local")


def _resolve_claude_klabauter_root(ml_dir: Path) -> str:
    """Resolve the claude-klabauter root path via the registry-then-sentinel
    ladder, validating it before return.

    Rung 1 (preferred): registry.toml (tracked baseline) then
    registry.local.toml (per-machine override, wins on collision) — key
    "repos.claude_klabauter" in either the nested [repos] table or the flat
    quoted-dotted-key form ``machine-local set`` writes. Empty-string is a
    miss, not a hit (never overwrites a value already resolved from the
    other file).

    Rung 2 (fallback): .claude-klabauter-root sentinel — honored when the registry key
    above is absent or the file itself is missing.

    Raises ClaudeKlabauterResolutionError (with a fail-loud, distinct message) when:
      - neither rung resolves anything,
      - the resolved value contains a '..' traversal segment,
      - the resolved value does not exist on disk as a directory.
    """
    claude_klabauter_root = ""
    for fname in ("registry.toml", "registry.local.toml"):
        registry_path = ml_dir / fname
        if not registry_path.is_file():
            continue
        try:
            import tomllib
            with open(registry_path, "rb") as f:
                registry_data = tomllib.load(f)
        except Exception:
            continue
        nested = registry_data.get("repos", {})
        if isinstance(nested, dict):
            v = nested.get("claude_klabauter")
            if isinstance(v, str) and v:
                claude_klabauter_root = v
        flat = registry_data.get("repos.claude_klabauter")
        if isinstance(flat, str) and flat:
            claude_klabauter_root = flat

    if not claude_klabauter_root:
        sentinel_path = ml_dir / ".claude-klabauter-root"
        try:
            with open(sentinel_path, "r", encoding="utf-8") as f:
                claude_klabauter_root = f.read().rstrip("\r\n")
        except OSError:
            claude_klabauter_root = ""

    claude_klabauter_root = claude_klabauter_root.rstrip("\r\n").rstrip("/")

    if not claude_klabauter_root:
        raise ClaudeKlabauterResolutionError(
            "ERROR: cannot resolve claude-klabauter — set it via 'machine-local set "
            f"repos.claude_klabauter <path>' (writes {ml_dir}/registry.local.toml), "
            f"or write the path to {ml_dir}/.claude-klabauter-root, or register a published "
            "engine mirror via 'machine-local set repos.claude_klabauter <path>'\n"
        )

    # Corrupted/typo'd-config guard, not a hostile-input guard — see module
    # docstring for why no harness-facing prefix-allowlist applies here.
    # Checks both separators: a resolved path can carry OS-native
    # backslashes on Windows (e.g. `str(Path(...))`), and `/..` alone would
    # silently miss a Windows-style `\..` traversal segment.
    if "/.." in claude_klabauter_root or "\\.." in claude_klabauter_root:
        raise ClaudeKlabauterResolutionError(
            f"ERROR: resolved claude-klabauter root '{claude_klabauter_root}' contains a "
            f"'..' traversal segment — refusing; fix {ml_dir}/registry.local.toml "
            f"or {ml_dir}/.claude-klabauter-root\n"
        )

    if not os.path.isdir(claude_klabauter_root):
        raise ClaudeKlabauterResolutionError(
            f"ERROR: resolved claude-klabauter root '{claude_klabauter_root}' does not exist "
            "on disk — re-run 'machine-local set repos.claude_klabauter <path>' or fix "
            f"{ml_dir}/.claude-klabauter-root\n"
        )

    return claude_klabauter_root


# Resolution classes returned alongside the root by
# ``resolve_claude_klabauter_root_with_class()``. Verbatim from DoE-claude's
# ``coordinator/hooks/scripts/_engine_root.py`` — a conformance fixture
# (chunk C8) drives both implementations against the same registry-state
# cases, so the string values themselves are part of the contract, not just
# their names.
RESOLUTION_RESOLVED_ENGINE = "resolved-engine"
RESOLUTION_LIVE_WORKING_TREE = "live-working-tree"
RESOLUTION_UNRESOLVED = "unresolved"


# --- C5: engine/edit skew advisory -----------------------------------------
#
# PM-ruled 2026-08-07 (option (b), verbatim: "that's fine, skew detection").
# Spec backlink: pln-two-tier-engine-root-resolutio-024269 § C5
#
# Fires exactly once per process, ONLY when this resolution came back
# ``RESOLUTION_RESOLVED_ENGINE`` (a published engine was chosen) AND
# ``repos.claude_klabauter`` *also* resolves to an existing directory on this
# box — the genuinely ambiguous configuration: a live working tree exists,
# but the CLI just invoked is not that tree. Reports a CONFIGURATION, never a
# staleness verdict — deliberately NOT a sha comparison (a stored ref
# "nothing compares against gets trusted eventually"); a pure registry read
# that cannot go stale.
#
# Negative-spec:
#   - Does NOT spawn a subprocess or touch git — reuses ``_resolve_claude_klabauter_root``
#     (registry-then-sentinel rungs only), the same pure-read ladder
#     ``resolve_claude_klabauter_root_with_class`` already runs for the live-tree leg.
#   - Does NOT fire for ``RESOLUTION_LIVE_WORKING_TREE`` or
#     ``RESOLUTION_UNRESOLVED`` — only the resolved-engine branch is the
#     ambiguous one this advisory exists to name.
#   - Writes to stderr ONLY, never stdout — this module is loaded by every
#     emitted forwarder and by hook-path callers; stdout is reserved for
#     PreToolUse hook JSON envelopes and CLI target output.
#
# PM-ruled 2026-08-10: OPT-IN, not opt-out. This module is loaded by every
# forwarder, so the advisory landed on the `claude` startup banner — PM-facing
# chrome on a configuration only an engine-side reader can act on. Silent
# unless CLAUDE_KLABAUTER_ROOT_SKEW_VERBOSE is set; the older QUIET kill-switch stays
# honoured (it wins over VERBOSE) so an install that exported it keeps working.
CLAUDE_KLABAUTER_SKEW_ADVISORY_QUIET_VAR = "CLAUDE_KLABAUTER_ROOT_SKEW_QUIET"
CLAUDE_KLABAUTER_SKEW_ADVISORY_VERBOSE_VAR = "CLAUDE_KLABAUTER_ROOT_SKEW_VERBOSE"

_skew_advisory_emitted = False


def _env_flag_set(name: str) -> bool:
    """True iff ``name`` is present and not one of the falsey spellings.

    Review: code-reviewer — a bare truthy check on the raw string treats "0"
    and "false" as set, since Python treats those strings as truthy; an
    operator spelling a flag off that way would silently get it on.
    """
    raw = os.environ.get(name)
    if raw is None:
        return False
    return raw.strip().lower() not in ("", "0", "false")


def _reset_skew_advisory() -> None:
    """Test-only helper: clear the once-per-process advisory flag."""
    global _skew_advisory_emitted
    _skew_advisory_emitted = False


def _maybe_emit_skew_advisory(ml_dir: Path, published: str) -> None:
    """Emit the engine/edit skew advisory (stderr, once per process) iff
    ``repos.claude_klabauter`` ALSO resolves to an existing directory
    alongside the published-engine resolution just made, AND the operator
    opted in via ``CLAUDE_KLABAUTER_ROOT_SKEW_VERBOSE``. Silent, and never raises, on
    any other outcome (not opted in, kill-switch set, already emitted, or
    ``repos.claude_klabauter`` unset/unresolved/nonexistent)."""
    global _skew_advisory_emitted
    if _skew_advisory_emitted:
        return
    if not _env_flag_set(CLAUDE_KLABAUTER_SKEW_ADVISORY_VERBOSE_VAR):
        return
    if _env_flag_set(CLAUDE_KLABAUTER_SKEW_ADVISORY_QUIET_VAR):
        return
    try:
        live = _resolve_claude_klabauter_root(ml_dir)
    except ClaudeKlabauterResolutionError:
        return
    except Exception:
        return
    _skew_advisory_emitted = True
    # Shape, not decoration: the consequence leads, and the two paths are
    # aligned so the reader compares them at a glance instead of parsing them
    # out of prose. No silencing tail — the reader set VERBOSE to get here and
    # knows how to unset it. The registry key name is deliberately NOT here:
    # implementation detail for a reader of this module, not of this notice.
    sys.stderr.write(
        "note: ran the published engine, not your working tree — "
        "edits to the tree do not affect this CLI.\n"
        f"        ran   {published}\n"
        f"        tree  {live}\n"
    )


def _flatten_registry(data: dict, _prefix: str = "") -> dict:
    """Flatten nested registry TOML tables to dotted keys.

    Mirrors DoE's ``_engine_root.py::_flatten_registry`` bit-for-bit — the
    two-tier readers below (``_engine_working_repo_roots``,
    ``_registry_value``) need to enumerate or look up keys under a table
    prefix (``engine.working_repos.*``, ``repos.claude_klabauter``) the same
    way regardless of whether the on-disk TOML used the nested
    ``[engine.working_repos]`` table form or the flat quoted-dotted-key form
    ``machine-local set`` writes. ``_resolve_claude_klabauter_root`` above does not use
    this helper — it reads exactly one key with its own inline nested/flat
    handling, predates this extraction, and stays untouched (AC7:
    byte-identical on a single-tree box)."""
    result: dict = {}
    for k, v in data.items():
        full_key = f"{_prefix}{k}"
        if isinstance(v, dict):
            result.update(_flatten_registry(v, _prefix=f"{full_key}."))
        else:
            result[full_key] = v
    return result


def _registry_value(ml_dir: Path, key: str) -> Optional[str]:
    """Read *key* from the machine-local registry TOML pair under *ml_dir*.

    Reads ``registry.local.toml`` before the tracked ``registry.toml``
    baseline and returns the first hit — mirrors DoE's ``_registry_value``.
    Fail-open throughout: missing file, unparseable TOML, or a missing
    ``tomllib`` (pre-3.11) all fall through to the next rung rather than
    raising. An empty-string value is a declaration, not a resolution."""
    try:
        import tomllib
    except ImportError:
        return None

    for name in ("registry.local.toml", "registry.toml"):
        reg = ml_dir / name
        try:
            if not reg.is_file():
                continue
            with reg.open("rb") as fh:
                data = tomllib.load(fh)
        except (OSError, tomllib.TOMLDecodeError):
            continue
        v = _flatten_registry(data).get(key)
        if isinstance(v, str) and v:
            return v

    return None


# --- C3: box-wide engine target -------------------------------------------
#
# PM RULING 2026-08-16, verbatim: "There will not be any 'some repos use x
# engine, others use y engine' as the engine choice will be for the entire
# box." One declared fact, box-wide, two values. No per-repo axis exists to
# SET this — ``engine.working_repos`` (above) remains a per-repo LOCATOR
# (which repos are working trees to divert away from), a different axis
# entirely; C4 retires its exemption duty but this fact never grows one of
# its own.
#
# Registry key: ``engine.target`` (nested ``[engine] target = "..."`` or the
# flat quoted-dotted-key form ``machine-local set`` writes), read via
# ``_registry_value`` — registry.local.toml (per-machine override) wins over
# the tracked registry.toml baseline, first-hit-wins, identical precedence to
# every other declared fact this module reads.
#
# HARD CONSTRAINT (memo-invalidation): this key MUST live in one of the two
# files ``_registry_mtime_pair`` (coordinator_core/claude_klabauter_root.py) already
# stats -- registry.toml or registry.local.toml -- so that writing it
# self-invalidates both ``_ROOT_MEMO`` and ``_GATE_MEMO`` by mtime with no
# explicit reset call. ``_registry_value`` reads exactly those two files, so
# this constraint is satisfied by construction; do not move this fact to a
# new sentinel file, a settings-home JSON, or an env-only var -- any of those
# would sit outside the stat tuple and make a rollback silently ineffective
# for every process that has already resolved. ``_reset_root_memo()`` is a
# test-only seam with zero non-test callers -- it is not the rollback
# mechanism; the mtime pair changing IS the mechanism.
#
# NEGATIVE SPEC: this is NOT a channel axis on the resolver's ladder above --
# ``resolve_claude_klabauter_root_with_class()`` still resolves a PATH, and this
# declaration does not touch it, ``resolution_class``, or the conformance
# schema. The target fact is a declared value for resolution/diagnostics
# callers (C8+) to consume later, never a per-call ref check spliced into the
# ladder here.
#
# NEGATIVE SPEC: never inferred from whatever the mirror has checked out.
# Declared or nothing -- the closed defect ``track_ref`` already exists to
# prevent that shape.
#
# AC20: absent or unreadable is a READ-SITE default (resolves the way the
# box resolves today), never a third stored value and never an opt-out --
# ``resolve_engine_target`` returns ``None`` for both "key absent" and "key
# present but not one of the two declared values" (a typo'd/stale config
# value is treated the same as absence, not raised as an error -- consistent
# with every other fail-open reader in this module).
ENGINE_TARGET_MAIN = "main"
ENGINE_TARGET_CANDIDATE = "candidate"
ENGINE_TARGET_KEY = "engine.target"
ENGINE_TARGET_VALUES = frozenset({ENGINE_TARGET_MAIN, ENGINE_TARGET_CANDIDATE})


def resolve_engine_target(ml_dir: Optional[Path] = None) -> Optional[str]:
    """Read the box-wide ``engine.target`` fact, or ``None`` if absent,
    unreadable, or not one of the two declared values.

    ``ml_dir`` defaults to ``_ml_dir()`` (same override-aware resolution
    every other reader in this module uses) when not supplied. Never raises.
    """
    if ml_dir is None:
        ml_dir = _ml_dir()
    value = _registry_value(ml_dir, ENGINE_TARGET_KEY)
    if value not in ENGINE_TARGET_VALUES:
        return None
    return value


def _engine_working_repo_roots(ml_dir: Path) -> List[str]:
    """Every non-empty registered ``engine.working_repos.*`` value,
    UNIONED across both registry files.

    Deliberately NOT first-hit-wins (unlike ``_registry_value`` and
    ``_resolve_claude_klabauter_root``'s single-key read) — this reads a SET of
    working repos, not one key, so a repo registered in either file is a
    working repo. Mirrors DoE's ``_engine_working_repo_roots``. Dedupes by
    value; never raises."""
    try:
        import tomllib
    except ImportError:
        return []

    prefix = "engine.working_repos."
    seen: dict = {}
    for name in ("registry.local.toml", "registry.toml"):
        reg = ml_dir / name
        try:
            if not reg.is_file():
                continue
            with reg.open("rb") as fh:
                data = tomllib.load(fh)
        except (OSError, tomllib.TOMLDecodeError):
            continue
        for k, v in _flatten_registry(data).items():
            if k.startswith(prefix) and isinstance(v, str) and v:
                seen[v] = None

    return list(seen.keys())


def _same_repo_path(a: str, b: str) -> bool:
    """Cross-platform path-equality check — mirrors DoE's
    ``_same_repo_path``: ``samefile`` when both paths exist, falling back to
    ``normcase``+``realpath`` comparison (so a registry entry pointing at a
    not-yet-cloned repo never raises). Never raises.

    Mirrors ``coordinator_core.win_portability.same_path`` (the consolidated
    primitive; state/sizings/2026-08-07-path-equality-consolidates-onto-one-
    prim.yaml) but does NOT import it -- this module's own docstring requires
    it to stay import-independent of coordinator_core (installs standalone
    into a bare ``bin/`` with no package context), so this copy is a
    PERMANENT, structural exception, not a laggard."""
    try:
        return os.path.samefile(a, b)
    except Exception:
        try:
            return os.path.normcase(os.path.realpath(a)) == os.path.normcase(
                os.path.realpath(b)
            )
        except Exception:
            return False


def _session_repo_root() -> Optional[Path]:
    """The repo root of the SESSION currently running.

    Mirrors DoE's ``_session_repo_root``: ``CLAUDE_PROJECT_DIR`` env var
    first, then a pure-Python upward walk from ``Path.cwd()`` looking for a
    ``.git`` entry (directory for a normal clone, file for a worktree).
    Never raises. Returns ``None`` if undeterminable."""
    env_root = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_root:
        try:
            p = Path(env_root)
            if p.is_dir():
                return p
        except Exception:
            pass

    try:
        cwd = Path.cwd()
    except Exception:
        return None

    try:
        for candidate in (cwd, *cwd.parents):
            if (candidate / ".git").exists():
                return candidate
    except Exception:
        return None

    return None


def _is_engine_working_repo(ml_dir: Path) -> Optional[bool]:
    """Is the CURRENT session running inside a registered engine-working
    repo (``engine.working_repos.*``)?

    Tri-state, deliberately: ``True``/``False`` are determinations; ``None``
    means "could not determine" (no session root, unreadable registry, or an
    empty working-repo set) — a genuinely different thing from ``False``. A
    caller MUST NOT treat ``None`` as ``False``: diverting an undeterminable
    repo away from the live tree, with nowhere principled to divert it FROM,
    would silently strand it. See ``resolve_claude_klabauter_root_with_class``'s
    ``is False`` check, never bare falsiness. Mirrors DoE's
    ``_is_engine_working_repo``. Never raises."""
    session_root = _session_repo_root()
    if session_root is None:
        return None

    try:
        working_roots = _engine_working_repo_roots(ml_dir)
    except Exception:
        return None

    if not working_roots:
        return None

    session_str = str(session_root)
    any_determined = False
    for root in working_roots:
        try:
            if _same_repo_path(session_str, root):
                return True
            any_determined = True
        except Exception:
            continue

    return False if any_determined else None


def _resolve_published_engine(ml_dir: Path) -> Optional[str]:
    """The published-engine seam — resolves the published engine mirror
    (``repos.claude_klabauter``), the coordinator-engine distribution a
    consumer repo should fall back to when its own tree is not the live
    working checkout.

    "Registered and usable" iff the key resolves to a value, that path
    exists as a directory, AND ``<root>/coordinator_core`` exists — guards
    the half-installed-clone case, where a root got registered before its
    clone finished. Mirrors DoE's ``_resolve_published_engine``. Fail-open,
    never raises."""
    try:
        root = _registry_value(ml_dir, "repos.claude_klabauter")
        if not root:
            return None
        root_path = Path(root)
        if not root_path.is_dir():
            return None
        if not (root_path / "coordinator_core").is_dir():
            return None
        return root
    except Exception:
        return None


def resolve_claude_klabauter_root_with_class() -> Tuple[Optional[str], str]:
    """Resolve the engine root AND say which class of thing answered —
    DR-132's two-tier ladder, mirroring DoE's
    ``_engine_root.py::resolve_claude_klabauter_root_with_class`` step order exactly.
    The NET effect is live-tree preference; do not "simplify" this into a
    live-tree-first ladder or invert it to prefer the published engine.

    Returns ``(root, resolution_class)`` where the class is one of
    ``RESOLUTION_RESOLVED_ENGINE``, ``RESOLUTION_LIVE_WORKING_TREE``, or
    (only via a raised ``ClaudeKlabauterResolutionError`` — see below)
    ``RESOLUTION_UNRESOLVED`` never actually returned by this function today,
    since the terminal miss raises rather than returning a sentinel tuple;
    it is exported for callers building their own class-comparison logic.

    Ladder:
      1. A published engine registered/usable AND the working-repo gate
         returns literally ``False`` (a CONFIRMED non-working repo, not an
         undeterminable one) -> ``(published, RESOLUTION_RESOLVED_ENGINE)``.
      2. Otherwise today's existing ladder (``_resolve_claude_klabauter_root``:
         registry key -> ``.claude-klabauter-root`` sentinel) -> if it resolves,
         ``(root, RESOLUTION_LIVE_WORKING_TREE)``.
      3. Otherwise, if a published engine is registered/usable ->
         ``(published, RESOLUTION_RESOLVED_ENGINE)``.
      4. Otherwise re-raise the ``ClaudeKlabauterResolutionError`` step 2 raised —
         "the existing" error, its remediation text now extended (see
         ``_resolve_claude_klabauter_root``) to also mention ``repos.claude_klabauter``.

    Fail-open (AC7): on a single-tree box with no ``engine.working_repos.*``
    and no ``repos.claude_klabauter``, ``published`` is always ``None`` and
    step 1 never fires — behavior collapses to step 2 exactly as it runs
    today, byte-identical."""
    ml_dir = _ml_dir()
    published = _resolve_published_engine(ml_dir)

    if published and _is_engine_working_repo(ml_dir) is False:
        _maybe_emit_skew_advisory(ml_dir, published)
        return published, RESOLUTION_RESOLVED_ENGINE

    try:
        live = _resolve_claude_klabauter_root(ml_dir)
        return live, RESOLUTION_LIVE_WORKING_TREE
    except ClaudeKlabauterResolutionError:
        if published:
            _maybe_emit_skew_advisory(ml_dir, published)
            return published, RESOLUTION_RESOLVED_ENGINE
        raise


def _is_executable(path: str) -> bool:
    """Stdlib-only twin of ``coordinator_core.win_portability.is_executable``
    — POSIX exec-bit inspection, Windows PATHEXT resolvability (a suffixed
    file must carry a PATHEXT suffix; an extensionless one is launchable only
    via a PATHEXT-suffixed sibling, which is what ``CreateProcess`` actually
    execs).

    Negative-spec — this MUST NOT become
    ``from coordinator_core.win_portability import is_executable``, at module
    scope or lazily. This file is installed standalone into the operator's
    ``<settings-home>/bin/`` beside every generated forwarder (the set is
    derived by ``substrate._derive_agent_helper_target_map`` from a
    ``coordinator/bin/`` listing, not a frozen count) and runs on a
    bare ``#!/usr/bin/env python3`` with only the stdlib importable: its
    entire job is to FIND claude-klabauter, so it cannot presuppose claude-klabauter is already
    importable. The package import landed here in ``a141074a``'s 40-site
    ``os.access(X_OK)`` -> ``is_executable()`` sweep, which had no way to see
    that this one call site executes outside the package, and it took down
    every bareword CLI on PATH at once — ``ModuleNotFoundError:
    coordinator_core`` before the ladder's first line, including
    ``~/.local/bin/claude-doe``, i.e. launching Claude Code itself.

    A lazy import off the resolved root is not the fix either: it would make
    the sentinel probe demand a FULL, importable checkout, conflating
    "coordinator/bin/ holds a launchable sentinel" (what this ladder rung
    actually asks) with "this tree is an installed Python package". The
    duplication is the deliberate cost of this file's standalone contract —
    keep the two in sync by hand if the Windows semantics change.

    ``os.access(path, os.X_OK)`` is banned repo-wide (see
    ``win_portability``'s own docstring: it degrades to existence-only on
    NTFS) — mode-bit inspection, not that call, is the POSIX branch here."""
    p = Path(path)
    if os.name != "nt":
        try:
            mode = os.stat(p).st_mode
        except OSError:
            return False
        return bool(mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))

    # PATHEXT's own separator is always ';' on Windows — never os.pathsep,
    # which would be ':' under a POSIX host modelling Windows semantics.
    pathext = os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD")
    exts = [e.upper() for e in pathext.split(";") if e.strip()]
    if p.suffix:
        return p.is_file() and p.suffix.upper() in exts
    return any((p.parent / (p.name + ext.lower())).is_file() for ext in exts)


def _validate_bin_dir(claude_klabauter_root: str) -> str:
    """Validate ``<claude_klabauter_root>/coordinator/bin`` and return it.

    Extracted from ``resolve_claude_klabauter_bin_dir()`` (C4b) so ``exec_cli`` can run
    the identical directory/sentinel validation against a root it resolved
    via the class-aware ``resolve_claude_klabauter_root_with_class()`` ladder, without
    duplicating the two fail-loud messages below. ``resolve_claude_klabauter_bin_dir()``
    itself is untouched byte-for-byte in behaviour — see its own docstring.

    Probes a specific, load-bearing executable (``archive-stamp-cli``)
    rather than trusting dir-existence alone — a bare directory can exist
    without containing the CLIs a caller needs.

    Raises ClaudeKlabauterResolutionError with a message distinguishing "wrong or
    incomplete checkout" (coordinator/bin/ itself missing) from "stale or
    partial migration" (coordinator/bin/ exists but its sentinel doesn't) —
    these are different failure modes and must not be collapsed into one
    generic message.
    """
    bin_dir = claude_klabauter_root + "/coordinator/bin"
    if not os.path.isdir(bin_dir):
        raise ClaudeKlabauterResolutionError(
            f"ERROR: '{bin_dir}' does not exist — the claude-klabauter clone at '"
            f"{claude_klabauter_root}' has no coordinator/bin/ directory; wrong or incomplete "
            "checkout. Confirm repos.claude_klabauter points at the claude-klabauter repo "
            "root (not a subdirectory)\n"
        )

    # Both shapes are accepted, and the `.py` one is accepted on EXISTENCE
    # rather than the exec bit: the POSIX-exec drain (docs/plans/2026-08-13-
    # grind-the-posix-exec-baseline-to-zero.md, chunk C6) renames the
    # extensionless entrypoints to `.py` and clears their exec bit, so
    # demanding an executable extensionless sentinel means demanding the
    # pre-drain shape forever. Checking both also keeps this resolver working
    # while the rename is mid-flight on a shared tree, which is when a false
    # negative here does the most damage.
    # Accepting both shapes is necessary but NOT sufficient to survive the
    # rename, because C6 lands it as delete-then-write rather than an atomic
    # move: for the instant between the two, NEITHER shape is on disk and a
    # single probe reads the same as a genuinely absent sentinel. Measured
    # live 2026-08-13 from a memo pickup taken mid-wave — the resolver raised,
    # and since archive-stamp-cli is the sole authorized frontmatter writer,
    # every concurrent session's handoff and memo stamping fails closed for
    # the width of that window.
    #
    # Re-probe before believing the miss. A rename window is sub-millisecond;
    # a genuinely absent sentinel stays absent, so the retry costs a bounded
    # ~300ms on a path that was about to hard-fail anyway and nothing at all
    # on the happy path (the first probe short-circuits). Deliberately NOT
    # solved by widening the sentinel to several files: that trades a precise
    # "this exact writer is missing" diagnostic for a fuzzy one, and every
    # candidate file is renamed by the same wave.
    sentinel_bare = bin_dir + "/archive-stamp-cli"
    sentinel_py = sentinel_bare + ".py"

    def _sentinel_present() -> bool:
        return _is_executable(sentinel_bare) or os.path.isfile(sentinel_py)

    if not _sentinel_present():
        for _backoff_sec in (0.05, 0.1, 0.15):
            time.sleep(_backoff_sec)
            if _sentinel_present():
                break
        else:
            raise ClaudeKlabauterResolutionError(
                f"ERROR: neither '{sentinel_bare}' nor '{sentinel_py}' is present — "
                f"coordinator/bin exists at '{bin_dir}' but its sentinel CLI "
                "(archive-stamp-cli, the sole authorized handoff/memo frontmatter "
                "writer) is absent in either shape, and stayed absent across a "
                "re-probe; this is a stale or partial claude-klabauter migration, "
                "not a wrong-path problem. Re-run the "
                "installer against this clone, or check out the missing file with "
                "`git checkout -- coordinator/bin/` — do NOT re-clone: this tree is "
                "shared by concurrent sessions and a re-clone discards their "
                "uncommitted work\n"
            )

    return bin_dir


def resolve_claude_klabauter_bin_dir() -> str:
    """Resolve, validate, and return ``<claude-klabauter-root>/coordinator/bin``.

    The coordinator-owned CLIs live at ``<claude-klabauter-root>/coordinator/bin``, NOT
    ``<claude-klabauter-root>/bin`` (that top-level bin/ is a different, unrelated
    claude-klabauter directory with its own entries).

    Byte-identical to its pre-C4b behaviour: resolves the root via the
    single-tier ``_resolve_claude_klabauter_root`` ladder only (never the published
    engine) — this is the function ``test_resolve_claude_klabauter.py`` exercises
    directly, and callers other than ``exec_cli`` (e.g. install-time
    tooling) still want the live-tree-only contract. ``exec_cli`` itself
    (C4b) resolves via ``resolve_claude_klabauter_root_with_class()`` instead and
    calls ``_validate_bin_dir`` directly — see its own docstring.
    """
    ml_dir = _ml_dir()
    claude_klabauter_root = _resolve_claude_klabauter_root(ml_dir)
    return _validate_bin_dir(claude_klabauter_root)


def _run_target_in_process(target_path: str, argv: List[str], claude_klabauter_root: str) -> int:
    """Run *target_path* (a ``coordinator/bin/`` Python CLI) in-process,
    return its intended exit code.

    Every ``coordinator/bin/`` CLI is a plain ``.py``-shaped module (some
    extensionless, some ``.py``-suffixed — see ``substrate.py``'s
    ``_write_agent_forwarder`` docstring) whose body is either a bare script
    or the ``if __name__ == "__main__": sys.exit(main(sys.argv[1:]))``
    pattern (e.g. ``archive-stamp-cli``). ``runpy.run_path(...,
    run_name="__main__")`` is the portable stdlib primitive that executes a
    plain file path as if it were run as ``__main__`` — no shebang
    interpretation needed (unlike ``os.execv`` on Windows, which goes
    through ``CreateProcess`` and cannot honor ``#!`` lines), no second
    interpreter cold-start, and no module-registry entry required for a
    target this function has no static import path for (targets are
    resolved dynamically by filename, not by package name).

    ``sys.argv`` is swapped for the duration of the call (restored in
    ``finally``) because target scripts read ``sys.argv`` directly (as
    ``archive-stamp-cli`` does) rather than accepting an injected argv
    parameter — this is the in-process equivalent of what ``execv``/
    ``subprocess`` would otherwise set up via the child's own process argv.

    *claude_klabauter_root* is inserted at the FRONT of ``sys.path`` for the duration
    of the call, restored (never merely popped — a target is free to mutate
    ``sys.path`` itself) in the same ``finally`` as ``sys.argv``. Why this is
    needed: ``run_path`` contributes only the TARGET SCRIPT's own directory
    (``<claude_klabauter_root>/coordinator/bin``) to ``sys.path``, never the repo root
    — unlike a normal ``python target_path`` invocation, which the POSIX leg
    of ``exec_cli`` uses and which gets the root for free via the CLI's own
    relative-import machinery not applying here (these targets import
    ``coordinator_core`` as an absolute top-level package). Without this, any
    forwarded target that does ``import coordinator_core`` at module scope
    dies with ``ModuleNotFoundError`` before running a line of its own logic
    — the root the caller already resolved (``resolve_claude_klabauter_root_with_class``
    et al.) is reused here, never re-resolved. Idempotent: skipped if
    *claude_klabauter_root* is already present, so a target that itself re-enters this
    function (or is invoked from a process that already has the root on
    ``sys.path``) never accumulates duplicate entries.

    A target that calls ``sys.exit(n)`` raises ``SystemExit(n)`` through
    ``run_path`` exactly as it would run standalone; that is caught here and
    its ``.code`` propagated (``None`` and non-int codes normalize to 0/1
    per Python's own ``sys.exit`` contract, mirrored here rather than
    reinvented). A target that falls off the end without calling
    ``sys.exit`` completes with implicit success (0), matching normal
    process-exit semantics.

    Negative-spec: the POSIX leg of ``exec_cli`` (interpreter-targeted
    ``os.execv``) needs none of this — a fresh interpreter process resolves
    its own ``sys.path`` from ``target_path``'s directory the normal way,
    and this function is never called on that leg. Do not add a ``sys.path``
    insert there; it would be a no-op on a process image this function never
    touches.
    """
    original_argv = sys.argv
    original_path = list(sys.path)
    try:
        sys.argv = [target_path] + argv
        if claude_klabauter_root not in sys.path:
            sys.path.insert(0, claude_klabauter_root)
        runpy.run_path(target_path, run_name="__main__")
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        sys.stderr.write(str(code) + "\n")
        return 1
    finally:
        sys.argv = original_argv
        sys.path[:] = original_path
    return 0


def exec_cli(target: str, argv: Optional[List[str]] = None) -> None:
    """Resolve ``<claude-klabauter-root>/coordinator/bin/<target>`` and run it,
    forwarding *argv* (defaults to ``sys.argv[1:]``).

    POSIX: ``os.execv``s into ``sys.executable`` with *target_path* as its
    first argument (``[sys.executable, target_path, *argv]`` — never returns
    on success, replaces the current process image). Interpreter-targeted,
    not shebang-dependent: this runs the target as ``python target_path``
    rather than executing *target_path* itself, so it no longer relies on
    every ``coordinator/bin/`` CLI carrying a ``#!/usr/bin/env python3``
    shebang or its executable bit being set.

    Windows: ``os.execv`` cannot honor a POSIX shebang — ``CreateProcess``
    (which ``os.execv`` goes through on Windows) does not interpret ``#!``
    lines, so a bare extensionless *target_path* fails outright. Windows
    also can't truly replace the current process image the way POSIX
    ``exec`` does. The prior body worked around both problems by resolving
    a second Python interpreter and ``subprocess.run``-ing the target — a
    full interpreter cold-start on every single forwarder call. Every
    ``coordinator/bin/`` target is a Python CLI (naked ``.py``-shaped file,
    with or without a ``.py`` suffix — see ``substrate.py``'s
    ``_write_agent_forwarder`` docstring), so there is no "genuinely
    unimportable target class" requiring a spawn fallback: this process is
    already running Python, so the fix is to run the target **in-process**
    via ``_run_target_in_process`` (``runpy.run_path``) instead of shelling
    out to a second one. This removes the interpreter-resolution failure
    mode entirely — there is no longer a "no Python interpreter found on
    PATH" case, because no second interpreter is ever located or started.

    Negative-spec (POSIX mechanism) — interpreter-targeted ``execv`` was
    chosen over in-process ``runpy.run_path`` (the same primitive the
    Windows leg uses) for the POSIX leg too. Measured on one warm macOS
    box, 12 runs each, both orders, pessimistic reading: status quo
    ``os.execv(target_path, ...)`` 32.6ms; interpreter-targeted execv
    31.3ms; in-process 20.2ms. In-process was rejected despite being
    fastest because it abandons process identity and couples forwarder and
    target process state permanently — specifically, ``runpy.run_path``
    from a forwarder leaves the FORWARDER's directory at ``sys.path[0]``
    rather than the target's, breaking bare sibling imports that
    direct-script invocation handles. Interpreter-targeted execv runs the
    target as ``python target_path``, which CPython treats identically to
    today's shebang-invoked script for ``sys.path[0]``, ``sys.argv[0]``,
    ``__file__``, signal disposition, and traceback shape — this is why the
    POSIX leg does NOT collapse onto ``_run_target_in_process``.

    On a resolution failure, writes the distinct fail-loud message to
    stderr and exits 1 (matching the prior inline body's contract). On a
    missing (or unreadable — see the `os.access(os.R_OK)` pre-check below)
    *target* itself (partial install, mid-refresh tree, or a name-map entry
    pointing at a stale target), exits 127 (POSIX command-not-found
    convention) with a one-line remediation. Non-executable is no longer a
    127 case: the interpreter-targeted POSIX mechanism below runs the
    target as `python target_path`, not target_path directly, so the exec
    bit is never required.

    C4b — per-target existence gate on the published-engine rung. Root
    resolution now goes through `resolve_claude_klabauter_root_with_class()` (C3's
    two-tier ladder) rather than the single-tier `resolve_claude_klabauter_bin_dir()`,
    so this function can see WHICH class answered. A directory-level
    sentinel probe (`resolve_claude_klabauter_bin_dir`'s `archive-stamp-cli` check)
    passes against the published mirror even though the claude-klabauter-vs-published
    forwarder sets are NOT nested (C4a's oracle: 20 names live-tree-only, 5
    published-only on this tree) — the gap is per-target, so the gate must
    be too. When the resolved class is `resolved-engine` and *target* is
    absent under that root's `coordinator/bin/`, falls back to the live
    working tree (via the same single-tier ladder `resolve_claude_klabauter_bin_dir`
    uses) and execs the target from there if it exists; only if that ALSO
    misses does the 127 path fire, naming both roots tried. When the
    resolved class is `live-working-tree`, behaviour is byte-identical to
    before this chunk — no fallback probe, no new I/O — this class already
    IS the live tree, so there is nowhere else to fall back to.
    """
    if argv is None:
        argv = sys.argv[1:]

    try:
        claude_klabauter_root, resolution_class = resolve_claude_klabauter_root_with_class()
        bin_dir = _validate_bin_dir(claude_klabauter_root)
    except ClaudeKlabauterResolutionError as exc:
        sys.stderr.write(str(exc))
        sys.exit(1)

    target_path = bin_dir + "/" + target
    # `.py`-suffix probe for a bare target name. The 745 installed settings-home
    # forwarders each call `exec_cli("<bare-name>")`, and the POSIX-exec drain
    # (docs/plans/2026-08-13-grind-the-posix-exec-baseline-to-zero.md, chunk C6)
    # renames the extensionless entrypoints they name to `<bare-name>.py`. The
    # install chain maps the suffix back off at INSTALL time, so a re-installed
    # tree is fine either way — but a forwarder installed before the rename
    # keeps naming the bare form, and every session on a not-yet-reinstalled
    # tree would exec-fail until it reinstalled. Probing here makes the
    # transition survivable without a fleet-wide reinstall, which is the same
    # bargain DoE took for `install-sentinel-write` in their `d34a977a8`.
    if not os.path.isfile(target_path) and not target.endswith(".py"):
        suffixed = target_path + ".py"
        if os.path.isfile(suffixed):
            target_path = suffixed
    target_claude_klabauter_root = claude_klabauter_root

    # Hoisted above the os.name branch (Review: code-reviewer F4 — was
    # byte-for-byte duplicated on both legs). Readability, not executability
    # (Review: code-reviewer F1) — the interpreter-targeted POSIX mechanism
    # below execs `sys.executable`, which always exists and is executable,
    # so `os.execv` itself no longer raises for an unreadable *target*; the
    # failure would otherwise surface only after process replacement, inside
    # the second interpreter's own `open()` of target_path, losing both the
    # 127 contract and the remediation message for exactly the
    # partial-install/mid-refresh scenario this check exists to catch. A
    # target can still change state between this check and the exec below
    # (TOCTOU) — that narrower window is accepted, not closed, and the
    # `except OSError` handler on the POSIX leg remains its backstop.
    if not os.path.isfile(target_path) or not os.access(target_path, os.R_OK):
        fallback_target_path = None
        live_bin_dir_desc = None
        if resolution_class == RESOLUTION_RESOLVED_ENGINE:
            try:
                live_bin_dir = resolve_claude_klabauter_bin_dir()
                live_bin_dir_desc = live_bin_dir
                candidate = live_bin_dir + "/" + target
                if os.path.isfile(candidate) and os.access(candidate, os.R_OK):
                    fallback_target_path = candidate
            except ClaudeKlabauterResolutionError:
                live_bin_dir_desc = "unresolvable live working tree"

        if fallback_target_path is not None:
            target_path = fallback_target_path
            # live_bin_dir is always "<root>/coordinator/bin" (_validate_bin_dir's
            # own composition) — strip the fixed suffix rather than re-resolving
            # the root via a second ladder call.
            target_claude_klabauter_root = live_bin_dir[: -len("/coordinator/bin")]
        elif resolution_class == RESOLUTION_RESOLVED_ENGINE:
            sys.stderr.write(
                f"ERROR: coordinator helper '{target}' is missing under both the "
                f"resolved published engine ('{bin_dir}') and the live working "
                f"tree ('{live_bin_dir_desc}') — re-run coordinator:install to "
                "repair the plugin tree\n"
            )
            sys.exit(127)
        else:
            sys.stderr.write(
                f"ERROR: coordinator helper '{target_path}' is missing — "
                "re-run coordinator:install to repair the plugin tree\n"
            )
            sys.exit(127)

    if os.name == "nt":
        sys.exit(_run_target_in_process(target_path, argv, target_claude_klabauter_root))

    try:
        os.execv(sys.executable, [sys.executable, target_path, *argv])
    except OSError as exc:
        sys.stderr.write(
            f"ERROR: coordinator helper '{target_path}' is missing or not "
            f"executable ({exc.strerror}) — re-run coordinator:install to "
            "repair the plugin tree\n"
        )
        sys.exit(127)
