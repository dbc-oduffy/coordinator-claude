"""Shared claude-klabauter-root resolution seam for coordinator/hooks/scripts/*.py hooks.

Purpose: every hook that needs to import `coordinator_core` from the sibling
Claude-klabauter checkout previously carried its own copy-pasted
`_resolve_claude_klabauter_root()` ladder (22 independent copies as of the 2026-07-22
executable-surface migration). This module is the ONE seam all of them import
from instead — one place to fix, one place to test.

Second responsibility: this module also hosts `run_stop_hook_pointer_shim`,
the shared Stop-hook transport body for the Family-A pointer-shim pair — see
that function's own docstring for the full contract.

HARD CONSTRAINT — zero-spawn: these hooks run on the hot-path
PreToolUse/PostToolUse dispatch, where this doctrine-plane repo's own zero-spawn boot mandate
(the 2026-07-15 zero-spawn directive, see `project-orientation.py`)
requires zero subprocess spawns per invocation — a constraint on this
repo's hook code in its own right, not derived from any engine-side
latency SLA. This module MUST NOT shell out, spawn a subprocess, or invoke the
`machine-local` CLI. It reads the registry
TOML directly with stdlib `tomllib` (3.11+, best-effort — wrapped in
try/except so a pre-3.11 interpreter degrades to the next rung rather than
raising).

Spec: 2026-07-22 executable-surface-migration break-class fix (coordinator
`bin`/`lib`/`scripts`/`tests` relocated to claude-klabauter; `coordinator/schemas/`
stayed here). Negative-spec: the previous per-hook ladder read a registry path
built from the home directory joined with a literal `machine-local` segment
under a literal dot-claude segment — that path does not exist on this fleet's
machines; the real registry lives under
`${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}/machine-local/`
(note the brace nesting: the `.coordinator-claude-settings` suffix applies
ONLY to the `${CLAUDE_HOME:-$HOME}` fallback, never to an explicit
COORDINATOR_SETTINGS_HOME override — see `_settings_home_registry_dir`'s
negative-spec for the bug this fixes). That stale construction must never
reappear (guarded by a grep-based test).
"""

from __future__ import annotations

import os
from pathlib import Path


def _settings_home_registry_dir() -> Path:
    """Resolve the machine-local registry directory per the documented
    precedence, matching `coordinator-settings-home` (the settings-home CLI
    entrypoint) and `project-orientation.py::_settings_home()` bit-for-bit:

      - COORDINATOR_SETTINGS_HOME, when set, IS the settings-home root
        already — used AS-IS, with no further suffix appended.
      - otherwise CLAUDE_HOME (or HOME) joined with the fixed
        `.coordinator-claude-settings` suffix.

    Either way, `machine-local` is then appended to reach the registry dir.

    Negative-spec: an earlier version of this function treated
    COORDINATOR_SETTINGS_HOME the same as CLAUDE_HOME/HOME — i.e. as a
    directory `.coordinator-claude-settings` should be appended to. That is
    wrong: when COORDINATOR_SETTINGS_HOME is explicitly set (the documented
    override rung), it already points AT the settings home, so appending the
    suffix again produced a doubled, nonexistent
    `<value>/.coordinator-claude-settings/machine-local` path. On a machine
    where a sibling `claude-klabauter` checkout also exists next to this repo,
    rung 3 (sibling walk) silently produced the right answer anyway, masking
    the registry rung never having fired. Caught 2026-07-22 by explicitly
    setting COORDINATOR_SETTINGS_HOME and neutralizing rung 3.
    """
    return _settings_home() / "machine-local"


def _settings_home() -> Path:
    """The settings-home ROOT, per the precedence documented on
    `_settings_home_registry_dir` (which is this joined with `machine-local`).

    Split out when the resolved-engine rung landed: that rung needs the root
    itself, not the registry subdirectory, and duplicating the ladder is
    exactly how this module's 22 copy-pasted predecessors drifted.

    `Path.home()`, never a bare `$HOME` read: a literal `${CLAUDE_HOME:-$HOME}`
    transliteration resolves EMPTY on native Windows shells and mints a
    cwd-relative settings home. Two sibling resolvers on the engine plane have
    already been bitten by that exact bug.
    """
    override = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if override:
        return Path(override)
    base = os.environ.get("CLAUDE_HOME") or str(Path.home())
    return Path(base) / ".coordinator-claude-settings"


# Resolution classes returned alongside the root by
# `resolve_claude_klabauter_root_with_class`. RESOLVED_ENGINE means a published engine
# mirror; LIVE_WORKING_TREE means a checkout whose contents are whatever a
# concurrent session has in it at this instant.
# Review: code-reviewer — top-of-file comment described the deleted
# rung-0 snapshot semantics, contradicting the docstring below.
#
# RESOLUTION_RESOLVED_ENGINE now has a producer: `_resolve_published_engine`
# reads `repos.claude_klabauter`, written at install time by the engine
# plane's own installer (`scripts/setup.py::register_claude_klabauter_root()`,
# commit `5080edc48d3f`) on a claude-klabauter (published-mirror) checkout.
# It fires once that key is registered on the current machine — see
# `_resolve_published_engine`'s own docstring for the read contract.
# `project-orientation.py` already consumes the constant.
RESOLUTION_RESOLVED_ENGINE = "resolved-engine"
RESOLUTION_LIVE_WORKING_TREE = "live-working-tree"
RESOLUTION_UNRESOLVED = "unresolved"

#: Literal sibling-repo dirname rung 3's last-resort walk matches against —
#: see that rung's negative-spec and the OSS-locality allowlist entry
#: covering this site.
_CLAUDE_KLABAUTER_SIBLING_DIR_NAME = "claude-klabauter"

#: Env vars rung 1 consults, in ratified precedence order (see
#: `_resolve_live_working_tree`). Exported as a constant rather than inlined at
#: the loop so that consumers which must SET one of these — the OSS-only
#: `coordinator-update` skill's tests, notably — can name it by reference
#: instead of by literal. That matters beyond tidiness: this module goes
#: through the publish content-transform sweep and the injected skill payload
#: deliberately does not, so a literal spelled on the consumer side would name
#: a variable the published resolver no longer reads.
LIVE_TREE_ENV_VARS = ("REPO_CLAUDE_KLABAUTER", "CLAUDE_KLABAUTER_ROOT")


def _warn_fail_open(where: str, exc: BaseException) -> None:
    """Emit ONE stderr line for a fail-open degrade, then return.

    Why this exists rather than a bare `except Exception: pass`: the
    resolver's fail-open contract and its observability are two different
    requirements, and a silent swallow satisfies only the first. A resolver
    defect (a registry TOML read mid-write, an OSError on a disconnected
    drive holding a registered published-engine mirror, a NameError from a
    half-landed edit to the rung ladder) then presents to the consumer as
    "the engine had nothing to say" — indistinguishable from correct
    behaviour, which is the failure shape a sibling plane spent two days
    chasing.

    Deliberately one line, not a traceback: these run on the hot-path hook
    dispatch, and on the Stop-hook shim path stderr is a contended channel
    (exit 2 there means "show this to Claude"). The write is itself guarded —
    a closed or non-writable stderr must never convert a fail-open into a
    raise.
    """
    try:
        import sys

        sys.stderr.write(
            f"[_engine_root] fail-open degrade in {where}: "
            f"{type(exc).__name__}: {exc}\n"
        )
    except Exception:
        pass


def _flatten_registry(data: dict, _prefix: str = "") -> dict:
    """Flatten nested registry TOML tables to dotted keys.

    Mirrors `_machine_local.py::_flatten_nested` (the canonical registry
    reader) so this hot-path reader accepts the same natural
    `[repos]\\nclaude_klabauter = "..."` table form as the flat dotted-key
    form. Dependency-free (no import), cheap — the registry files this
    reads are small, so a full-dict recursive flatten is fine on the
    zero-spawn hook hot path.
    """
    result: dict = {}
    for k, v in data.items():
        full_key = f"{_prefix}{k}"
        if isinstance(v, dict):
            result.update(_flatten_registry(v, _prefix=f"{full_key}."))
        else:
            result[full_key] = v
    return result


def _registry_value(reg_dir: Path, key: str) -> str | None:
    """Read `key` from the machine-local registry TOML pair under `reg_dir`.

    Reads `registry.local.toml` before the tracked `registry.toml` baseline
    and returns the first hit — per-machine values live in the gitignored
    `.local.toml` layer and override the tracked baseline's empty-string key
    DECLARATIONS (see `docs/wiki/machine-local-registry.md`). Accepts both
    the flat dotted-key form (`"repos.claude_klabauter" = "..."`) and a nested
    `[repos]` table — nested tables are flattened to dotted keys
    (`_flatten_registry`) before the lookup, so a hand-edited registry using
    natural TOML table syntax resolves the same as the flat form. An
    empty-string value is a sentinel placeholder, not a resolution.
    """
    try:
        import tomllib
    except ImportError:
        return None

    for name in ("registry.local.toml", "registry.toml"):
        reg = reg_dir / name
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


def _harness_home_dir() -> Path | None:
    """The harness install root (`~/.claude`, i.e. `Path.home() / ".claude"`) —
    NOT the settings-home (`_settings_home()`, `~/.coordinator-claude-settings`
    by default), a distinct directory.

    `~/.claude` is a backup/harness-config repo, never a coordinator working
    repo (PM ruling, bug `2026-08-15-dispatch-working-data-is-being-written-i-
    cc43ea98c52e`) — it must never be RETURNED as a session repo root even
    when it happens to carry its own unrelated `.git` (e.g. a personal
    doctrine-backup clone). Best-effort: returns None rather than raising if
    `Path.home()` itself fails to resolve.

    Returns the RESOLVED real path, and callers must compare against equally
    resolved candidates via `_is_harness_home()` — a bare `Path` equality
    misses the shapes this actually arrives in on Windows: a trailing
    separator, a case variant, an 8.3 short name, or a reparse point. On this
    box `~/.claude/machine-local` is an NTFS junction, so link-blind
    comparison is not hypothetical here.
    """
    try:
        return (Path.home() / ".claude").resolve()
    except Exception:
        return None


def _is_harness_home(candidate: Path, harness_home: Path | None) -> bool:
    """True when `candidate` resolves to the same directory as `~/.claude`.

    Never raises: an unresolvable candidate is reported as NOT the harness
    home, which fails toward the ordinary resolution path rather than
    silently discarding a legitimate repo root.
    """
    if harness_home is None:
        return False
    try:
        return candidate.resolve() == harness_home
    except Exception:
        return False


def _session_repo_root() -> Path | None:
    """The repo root of the SESSION currently running — not this plugin's own
    root.

    `__file__`-relative resolution (as used elsewhere in this module for the
    plugin's own checkout depth) answers "where is this plugin installed",
    which is the wrong question here: the working-repo gate needs to know
    which repo the CURRENT session is running in, so it can check that repo
    against `engine.working_repos.*`.

    Mirrors the boot-safe pattern documented on `resolve_repo_root_boot` in
    the project-orientation SessionStart hook — deliberately NOT imported (a
    hook script is not a library this module may depend on; see module
    docstring on the zero-spawn/no-cross-hook-import contract),
    reimplemented locally instead:

      1. `CLAUDE_PROJECT_DIR` env var, if set and points at a real directory
         AND is not `~/.claude` (see below).
      2. Pure-Python upward walk from `Path.cwd()` looking for a `.git` entry
         (directory for a normal clone, FILE for a worktree), skipping any
         candidate that IS `~/.claude`.

    `~/.claude` exclusion (2026-08-15, bug `2026-08-15-dispatch-working-data-
    is-being-written-i-cc43ea98c52e`): `~/.claude` is the harness install/
    backup root, never a coordinator working repo, but it can carry its own
    unrelated `.git` (e.g. a personal doctrine-backup clone) — a session
    whose cwd transiently lands inside it (or under it) must not have this
    resolver hand back `~/.claude` as "the session's repo root", which would
    silently redirect every state write (subagent-share sidecars, housekeeping
    liveness/failure logs, etc.) into that backup tree instead of the actual
    working repo, or `None` if there genuinely is none.

    # Review: code-reviewer — this docstring previously claimed the walk
    # "fails closed to None" once it passes `~/.claude`. It does not: the
    # walk continues PAST `~/.claude` and MAY return an ANCESTOR of it (e.g.
    # `Path.home()` itself, if that directory has its own unrelated `.git`)
    # rather than stopping at `None`. `test_cwd_walk_skips_claude_home_but_
    # finds_real_repo_above_it` (added in this same commit) pins exactly
    # that. This is deliberate: continuing the walk lets a real repo
    # genuinely above `~/.claude` resolve correctly instead of always
    # failing closed, at the cost of accepting that ancestor if it happens
    # to carry an unrelated `.git` of its own — a narrower, accepted risk,
    # not a "fails closed" guarantee.

    Zero-spawn (no `git rev-parse`), never raises. Returns None if
    undeterminable.
    """
    harness_home = _harness_home_dir()

    env_root = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_root:
        try:
            p = Path(env_root)
            if p.is_dir():
                # Review: code-reviewer (Finding 4) — this rung resolves `p`
                # itself rather than delegating to `_is_harness_home`
                # (which fails toward False, i.e. "not harness home", on a
                # resolve() exception). That fail-open direction is safe at
                # the cwd-walk rung below (a resolve failure there just
                # means the walk tries the next candidate), but at THIS
                # rung "not harness home" is the ONLY thing standing between
                # a resolve() failure and directly RETURNING the candidate
                # as the session repo root — the one outcome this whole
                # function exists to prevent. So this rung fails CLOSED: a
                # resolve() exception here is treated as "could not prove
                # this ISN'T `~/.claude`", and falls through to the cwd
                # walk instead of trusting the unresolved env value.
                try:
                    resolved = p.resolve()
                except Exception:
                    resolved = None
                if resolved is not None and (
                    harness_home is None or resolved != harness_home
                ):
                    return p
        except Exception:
            pass

    try:
        cwd = Path.cwd()
    except Exception:
        return None

    try:
        for candidate in (cwd, *cwd.parents):
            if _is_harness_home(candidate, harness_home):
                continue
            if (candidate / ".git").exists():
                return candidate
    except Exception:
        return None

    return None


# Review: code-reviewer — the docstring below previously opened by claiming
# reuse of `_registry_value`'s precedence pattern; this function deliberately
# unions across both registry files rather than first-hit-wins, per its own
# body comments, so that framing was dropped.
def _engine_working_repo_roots(reg_dir: Path) -> list[str]:
    """Every non-empty registered `engine.working_repos.*` value.

    Reuses `_flatten_registry`'s nested-table flattening pattern rather than
    re-implementing it (each file is read and flattened independently here,
    since we want every matching key per file, not a single named key), so a
    hand-edited `[engine.working_repos]` table resolves the same as the flat
    dotted-key form.

    An empty-string value is a DECLARATION (the tracked baseline names the
    key so `.local.toml` has something to override), not a resolution — such
    entries are skipped, matching `_registry_value`'s own empty-string
    sentinel treatment.

    Merges both registry files (rather than first-hit-wins) because this
    reads a SET of repos, not a single key — a machine may declare working
    repos across both the tracked baseline and the local override layer.
    Never raises; returns `[]` on any read/parse failure.
    """
    try:
        import tomllib
    except ImportError:
        return []

    prefix = "engine.working_repos."
    seen: dict[str, None] = {}
    for name in ("registry.local.toml", "registry.toml"):
        reg = reg_dir / name
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


def resolve_publish_mirror_roster() -> list[tuple[str, str]]:
    """Every registered `publish.mirrors.*` entry, as `(path, owner)` pairs.

    Spec: 2026-08-08 publish-mirror-roster-on-the-engine-boot plan. The read
    side of a write-time guard that already exists: `bump_out_of_repo_tool_write`,
    `bump_outside_repo_write`, `bump_foreign_repo_write`, and
    `block_oss_mirror_memo_delivery` all fire on a WRITE to a registered publish
    mirror, correctly refusing it — but an agent that reasons its way to never
    writing never reaches one of those guards, and has nothing on the read path
    to tell it the directory it just met is a publish mirror rather than an
    ordinary sibling repo. This function is that read-side fact, sourced once
    so `engine_resolution_banner()` (project-orientation.py) can announce it
    unprompted on the boot path.

    Negative-spec — why `publish.mirrors.*` and not `repos.claude_klabauter`:
    `repos.claude_klabauter` resolves to the SAME directory as a publish
    mirror on some machines, which makes the two look interchangeable. They
    are not. `repos.claude_klabauter` is the *engine-resolution* rung —
    already covered by the existing class line in `engine_resolution_banner`,
    and it exists in `repos.*` for `_resolve_published_engine`'s reason, not
    this one. Reading it here would conflate the engine seam with the publish
    seam, and would miss `publish.mirrors.coordinator_claude` (and any other
    registered mirror with no engine-resolution role) entirely.

    Negative-spec — no `coordinator_core/` existence check: that guard is
    `_resolve_published_engine`'s, where it distinguishes a half-cloned
    *engine* checkout from a finished one. A publish mirror is not an engine
    and carries no such marker; requiring one here would silently empty the
    roster on every machine, which is exactly the invisible-by-construction
    failure this function exists to end.

    Mirrors `_engine_working_repo_roots`'s prefix-scan shape: both registry
    layers are read and flattened independently (`registry.local.toml` then
    `registry.toml`, via `_flatten_registry`), and both are MERGED — a
    mirror's `owner` typically lives in the tracked baseline while its
    per-machine `path` lives in the gitignored local layer (see
    `docs/wiki/machine-local-registry.md` §5c.2's schema-shape example), so a
    first-hit-wins read would miss the pairing entirely.

    An entry is included only when `path` is a non-empty string AND
    `Path(path).is_dir()` — an empty-string value is a declaration sentinel
    (`_registry_value`'s convention), and a declared-but-nonexistent path is
    not a directory an agent will ever actually meet. A populated `path` with
    a missing/empty `owner` is still listed, rendered as the literal
    `"unknown owner"` rather than dropped — an unowned mirror is still not a
    peer repo, and dropping it would re-introduce exactly the invisibility
    this function exists to close.

    De-duplicates on path, preserving first-seen order (local-layer scan
    first, then tracked-baseline scan — same file order as `_registry_value`
    and `_engine_working_repo_roots`), so a mirror declared in both layers
    lists once.

    Zero-spawn, never raises — `[]` on any missing registry, unreadable file,
    TOML parse error, or filesystem exception, same fail-open contract as
    every other rung in this module.
    """
    try:
        import tomllib
    except ImportError:
        return []

    try:
        reg_dir = _settings_home_registry_dir()
    except Exception:
        return []

    prefix = "publish.mirrors."
    flattened: list[dict] = []
    for name in ("registry.local.toml", "registry.toml"):
        reg = reg_dir / name
        try:
            if not reg.is_file():
                continue
            with reg.open("rb") as fh:
                data = tomllib.load(fh)
            flattened.append(_flatten_registry(data))
        except (OSError, tomllib.TOMLDecodeError):
            continue
        except Exception:
            continue

    # Pass 1: collect every `.owner` across BOTH layers first, so pass 2 can
    # pair a `.path` found in either layer against an `.owner` that may live
    # in the OTHER one — see the docstring's merge rationale (the schema
    # commonly splits owner into the tracked baseline and path into the
    # gitignored local layer).
    owners: dict[str, str] = {}
    for flat in flattened:
        for k, v in flat.items():
            if k.startswith(prefix) and k.endswith(".owner") and isinstance(v, str) and v:
                key = k[len(prefix) : -len(".owner")]
                owners.setdefault(key, v)

    # Pass 2: collect `.path` entries, first-seen order across the same
    # local-then-tracked scan, de-duplicated on the resolved path.
    roster: list[tuple[str, str]] = []
    seen_paths: dict[str, None] = {}
    for flat in flattened:
        for k, v in flat.items():
            if not (k.startswith(prefix) and k.endswith(".path")):
                continue
            key = k[len(prefix) : -len(".path")]
            if not isinstance(v, str) or not v:
                continue
            try:
                if not Path(v).is_dir():
                    continue
            except Exception:
                continue
            if v in seen_paths:
                continue
            seen_paths[v] = None
            roster.append((v, owners.get(key) or "unknown owner"))

    return roster


def _same_repo_path(a: str, b: str) -> bool:
    """Cross-platform path-equality check (samefile, normcase+realpath
    fallback) — mirrors the engine's own path-equality helper used for
    receiver/self repo-identity resolution.

    Reimplemented locally rather than imported: this module cannot import
    `coordinator_core` (see module docstring — that would be the exact
    circularity this seam exists to resolve). `samefile` when both paths
    exist; `normcase`+`realpath` fallback so a registry entry pointing at a
    not-yet-cloned repo never raises. Never raises.

    DRIFT SEAM — the helper this mirrors is the engine plane's own
    path-equality helper for receiver/self resolution
    (`ops/fleet/_memo_resolver.py::same_repo_path` in the engine tree), which
    carries the owning note. A *semantics* change there — the ANSWER for some
    pair of paths, not the implementation — silently desynchronizes the
    engine-working-repo gate below, and no test on either side detects the
    divergence; the engine plane ships such a change as a cross-plane memo.
    The reciprocal holds: a semantics change here ships one back.
    """
    # Review: code-reviewer — was `except OSError`, which let an unusual
    # filesystem/encoding edge case propagate out of this function despite
    # the "Never raises" contract above, letting the outer tri-state
    # collapse None (undeterminable) into False. Catch Exception here so
    # "Never raises" holds by construction rather than by convention.
    try:
        return os.path.samefile(a, b)
    except Exception:
        try:
            return os.path.normcase(os.path.realpath(a)) == os.path.normcase(
                os.path.realpath(b)
            )
        except Exception:
            return False


def _is_engine_working_repo() -> bool | None:
    """Is the CURRENT session running inside a registered engine-working
    repo (`engine.working_repos.*`)?

    Tri-state, deliberately: `True`/`False` are determinations; `None` means
    "could not determine" (no session root, unreadable registry, or an empty
    working-repo set) — a genuinely different thing from `False`; a
    consumer MUST NOT treat `None` as `False`, or a repo whose gate simply
    couldn't be evaluated on this run would get diverted away from the live
    tree it should still be resolving (see `resolve_claude_klabauter_root_with_class`'s
    `is False` check, not a bare falsiness check).

    Now armed: `_resolve_published_engine` can return non-`None` once
    `repos.claude_klabauter` is registered, so the per-call TOML re-parse
    and `.git` walk this performs is live cost on such a machine, not merely
    speculative. No memoization was added at the producer-landing change
    this comment used to defer to: this module is consumed by short-lived,
    per-invocation hook processes (see module docstring's zero-spawn/
    hot-path framing), where a module-level cache buys nothing — the values
    it would cache (this process's session root, the registry's on-disk
    contents) cannot change again within that same process's remaining
    lifetime whether or not the read is cached. Within a genuinely
    long-lived process instead (this repo's own test suite, which
    monkeypatches settings-home/env/registry state per test and calls this
    function repeatedly across tests in one process), a naive module-level
    cache would actively break test isolation by serving a stale
    determination across test boundaries. Left unadded on purpose, not
    merely unaddressed — add it only alongside actual per-invocation cost
    evidence AND a cache-invalidation story for a long-lived caller, neither
    of which exists today.

    Zero-spawn, never raises.
    """
    session_root = _session_repo_root()
    if session_root is None:
        return None

    try:
        reg_dir = _settings_home_registry_dir()
        working_roots = _engine_working_repo_roots(reg_dir)
    except Exception:
        return None

    if not working_roots:
        return None

    session_str = str(session_root)
    # Review: code-reviewer — `_same_repo_path` is now fixed to genuinely
    # never raise, but this loop tracks raised-vs-not defensively too:
    # returning False (CONFIRMED non-working) after every comparison raised
    # would still collapse "couldn't determine" into "not a match" if a
    # future edit to `_same_repo_path` reintroduced a raising path.
    any_determined = False
    for root in working_roots:
        try:
            if _same_repo_path(session_str, root):
                return True
            any_determined = True
        except Exception:
            continue

    return False if any_determined else None


def _resolve_published_engine() -> str | None:
    """The published-engine seam — resolves the published engine mirror
    (the coordinator-engine distribution consumer repos should resolve to).

    Reads `repos.claude_klabauter` from the machine-local registry (via
    `_registry_value`) — the key the engine plane's own installer,
    `scripts/setup.py::register_claude_klabauter_root()` (commit `5080edc48d3f`),
    writes at install time when it determines the current checkout is a
    published claude-klabauter mirror rather than the engine-source working
    tree (`resolve_repo_identity()` makes that call). An engine-source
    install writes neither this key nor a ref/sha alongside it.

    Deliberately no ref/sha field: a stored value nothing compares against
    gets trusted eventually, past the point where it can still be believed.
    The sha, when one is needed, is obtained by `git -C <root> rev-parse` at
    the moment of need against the right repository — not by this function,
    which stays zero-spawn.

    Guards the half-installed-clone case: the registered root must both
    exist AND contain a `coordinator_core/` directory before it is trusted.
    That check is the engine plane's, agreed as part of this seam's contract
    and surviving on its installer side unchanged; it is mirrored here so a
    root that got registered before its clone finished is not handed on as
    a resolved engine. No other rung in this module performs it — the other
    rungs resolve a checkout the caller already knows how to fail on.

    Zero-spawn, fail-open, never raises — any registry-read or filesystem
    exception yields `None`, same contract as every other rung in this
    module.
    """
    try:
        reg_dir = _settings_home_registry_dir()
        root = _registry_value(reg_dir, "repos.claude_klabauter")
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


def _resolve_engine_target() -> str | None:
    """Read `engine.target` from the machine-local registry (via
    `_registry_value`, reused rather than a second hand-rolled reader).

    READER ONLY — no consumer in this module yet. Wiring this into the
    resolution ladder is a separate, later chunk
    (`docs/plans/2026-08-16-engine-targeting-contract-reply.md`, chunk C4);
    landing the reader alone here is what makes that chunk's inert-landing
    property provable rather than asserted. This function is not yet part
    of the ladder's behavioural shape and is deliberately excluded from
    `_ladder_source_hash()` in `test_engine_root_conformance.py` for exactly
    that reason — it joins that pin at C4, when it actually starts
    influencing an outcome.

    Returns the target value, or `None` meaning UNREADABLE. `None` is the
    chosen sentinel rather than a new value: every other fail-open rung in
    this module (`_resolve_published_engine`, `_registry_value` itself)
    already uses `None` for "could not produce an answer," and a target
    value is always a non-empty string, so there is no legitimate value
    this could be confused with.

    UNREADABLE covers exactly four conditions, all folding to `None`:
      - the key is absent (`_registry_value` returns `None`)
      - the registry directory/files are absent (`_registry_value`'s
        per-file `OSError`/not-`is_file` handling continues past a missing
        file and returns `None` once both are exhausted)
      - the registry is corrupt (`_registry_value` catches
        `tomllib.TOMLDecodeError` per file and continues)
      - the value is empty or whitespace-only (`_registry_value` already
        filters a bare empty string via its own `isinstance(v, str) and v`
        check, but a whitespace-only string like `"   "` is truthy and
        would pass through uncaught — filtered here with `.strip()`)

    **Any non-empty (post-strip) value is READABLE, returned verbatim.**
    This function does not validate, normalize, case-fold, or compare the
    value against a channel vocabulary (e.g. `main`/`candidate`) — this
    resolver does not own that vocabulary (see the plan's "What
    `engine.target` means on this plane" section and AC17). It never
    substitutes a default or a channel name for an unreadable read.

    **Anti-strand duty.** The rule that "a `None`/unreadable determination
    never diverts" re-homes onto this reader's return value once C4 wires
    it in — the same principle already named doctrine at
    `_is_engine_working_repo`'s own docstring (this module — the passage
    reading "a consumer MUST NOT treat `None` as `False`, or a repo whose
    gate simply couldn't be evaluated on this run would get diverted away
    from the live tree it should still be resolving")
    and at `docs/decisions/DR-132-engine-working-repos-is-its-own-namespace-
    not-a-repos-star-inference.md` § Consequences ("no consumer repo can be
    stranded"). Both are phrased against `_is_engine_working_repo()` because
    it was the only mechanism that existed when they were written; the
    principle is pinned, not the variable, and is not re-derived here.

    Zero-spawn, no memoization, never raises — same contract as the rest of
    this module.
    """
    try:
        reg_dir = _settings_home_registry_dir()
        value = _registry_value(reg_dir, "engine.target")
    except Exception:
        return None
    if value is None:
        return None
    if not value.strip():
        return None
    return value


def resolve_claude_klabauter_root_with_provenance() -> tuple[str | None, str, str]:
    """Resolve the engine root, its resolution class, AND which rung answered.

    Returns `(root, resolution_class, provenance)`. `resolution_class` is one
    of `RESOLUTION_RESOLVED_ENGINE` (a published engine mirror), or
    `RESOLUTION_LIVE_WORKING_TREE` (a checkout, contents whatever a concurrent
    session has in it right now), or `RESOLUTION_UNRESOLVED` (root is None) —
    unchanged in meaning from `resolve_claude_klabauter_root_with_class`, which now
    delegates here (see that function's own docstring for a short pointer).
    `provenance` is a purely additive third value naming the RUNG that
    answered; no fourth resolution class is introduced, and no existing
    consumer comparing `resolution_class` sees any change.

    **Why this exists, and why it is not merely diagnostic.** Before it, a
    consumer executing a half-finished engine mid-edit saw a guard behaving
    oddly, an op erroring, or an agent politely declining — none of which is
    distinguishable, from the consumer's seat, from that engine behaving
    correctly. A live investigation on a sibling plane spent two days on a
    wrong theory for exactly this reason: the failure was silent by
    construction, not merely unlogged. Closing the race without making the
    resolution class observable would fix the smaller half of the defect.
    Naming WHICH rung answered (not just which class) is the same argument
    one layer deeper — see `docs/plans/2026-08-16-engine-targeting-contract-
    reply.md` § The provenance seam for the full rationale, including why the
    class and the provenance are kept as two separate return values rather
    than folded into one richer class enum.

    A live working tree is a LEGITIMATE answer, not a failure — on a
    co-development machine it is the answer you want. What this makes possible
    is that it be a deliberate, visible state rather than an invisible default.

    **Rung 2 is a DISJUNCTION (2026-08-16, C4).** Divert to the published
    engine when EITHER `engine.target` is readable (`_resolve_engine_target()`
    is not `None`) OR the legacy gate concretely confirms a non-working repo
    (`_is_engine_working_repo() is False`) — `published and (target_is_readable
    or _is_engine_working_repo() is False)`. The legacy disjunct is UNCHANGED
    and does not leave the ladder here: retiring it is a later, separately
    risky chunk (C5), deliberately sequenced after the engine plane's
    `engine.target` write has been observed live on this box for a cycle. This
    chunk is strictly additive over the single-disjunct ladder — every state
    that diverted before this chunk keeps diverting; `engine.target`
    readability only ever adds NEW divert states. That is the monotonicity
    property (AC14): no drivable state that resolved `RESOLUTION_RESOLVED_
    ENGINE` before this chunk resolves `RESOLUTION_LIVE_WORKING_TREE` after
    it — proved by construction (a disjunction only grows the set of true
    conditions), not by an ex­haustive enumeration. See
    `docs/plans/2026-08-16-engine-targeting-contract-reply.md` § The landing
    property that de-risks this / § The provenance seam for the full
    rationale, including why this is monotone rather than byte-identical (the
    ladder already diverts today for every repo outside `engine.working_
    repos`, so byte-identity was never available).

    **Anti-strand duty, now shared between the two disjuncts.** The rule that
    "a `None`/unreadable determination never diverts" — already named at
    `_is_engine_working_repo`'s own docstring (this module — the passage
    reading "a consumer MUST NOT treat `None` as `False`, or a repo whose
    gate simply couldn't be evaluated on this run would get diverted away
    from the live tree it should still be resolving") and at
    `docs/decisions/DR-132-engine-working-repos-is-its-own-
    namespace-not-a-repos-star-inference.md` § Consequences ("no consumer
    repo can be stranded") — is what rung 3's `"live-no-target"` provenance
    value makes visible: it is reached only when a published engine EXISTS
    (there was somewhere to divert to) but BOTH disjuncts failed to fire —
    `engine.target` unreadable AND `_is_engine_working_repo()` not concretely
    `False` (i.e. `True` or `None`). That state is the rollout no-op flagged
    to the engine plane: the box was supposed to divert and did not, named
    per-session rather than silently inferred. When no published engine
    exists at all, rung 3 keeps reporting whichever live sub-rung answered
    (`"live-env-dup"` / `"live-registry"` / `"sibling-walk"`) exactly as
    before — `"live-no-target"` names a specifically UNREALIZED divert
    opportunity, not "no live tree found."

    **Rung 0 gained a health guard (AC19, C4).** Under this ladder, rung 0
    (the explicit env-var override) is the ONLY live-tree-by-intent path —
    the PM's manual test-and-execute carve-out — so a stale, typo'd, or moved
    override must not silently outrank a healthy published engine with no
    fallback. It now applies the same `coordinator_core/` existence guard
    `_resolve_published_engine()` already applies to its own registered root:
    a set-but-unhealthy override falls through to the rest of the ladder
    rather than answering, emitting one `_warn_fail_open`-class line naming
    the env var and the path. A HEALTHY override still wins outright, exactly
    as before.

    **Resolution order — FAIL-OPEN is the load-bearing property here, not an
    incidental one.** `RESOLUTION_RESOLVED_ENGINE` (the published-engine
    rung) now has a producer: `_resolve_published_engine` fires once
    `repos.claude_klabauter` is registered on the current machine (written
    at install time by the engine plane's own installer,
    `scripts/setup.py::register_claude_klabauter_root()`, commit `5080edc48d3f`, on a
    claude-klabauter checkout). On a machine with no such registration —
    every machine before its klabauter install runs — this ladder still
    degrades to exactly the live-tree-or-unresolved behaviour that existed
    before the working-repo gate was wired. Once a published engine DOES
    exist (registered on this machine), a repo is only ever diverted away
    from the live tree when `engine.target` is readable OR
    `_is_engine_working_repo()` returns the concrete `False`
    determination — an unreadable target combined with an undeterminable
    (`None`) or confirmed-working (`True`) gate never diverts, because
    diverting a repo with no confirmed answer and no fallback would silently
    strand it exactly the way the deleted rung-0 engine-snapshot producer
    once did (see module docstring, rung 3 negative-spec):

      0. `env_override = _resolve_live_tree_env_override()` (an explicit
         `REPO_CLAUDE_KLABAUTER`/`CLAUDE_KLABAUTER_ROOT` env var pointing at an existing
         directory). If set AND healthy (contains `coordinator_core/`) →
         `(env_override, RESOLUTION_LIVE_WORKING_TREE, "env-override")` — an
         explicit override always wins over ambient discovery, published-
         engine registration included, when it is actually an engine
         checkout. If set but UNHEALTHY, one `_warn_fail_open`-class line is
         emitted (naming the env var and the path) and resolution falls
         through to the rest of the ladder rather than answering (AC19).
         This rung is checked BEFORE the published-engine rung below on
         purpose: an operator or test that sets this env var deliberately is
         stating an explicit intent, and ambient registry state must never
         outrank a stated intent (previously it did — see this module's own
         history for the defect this rung ordering closes).
      1. `published = _resolve_published_engine()`;
         `target_is_readable = _resolve_engine_target() is not None`.
      2. If `published` and `target_is_readable` →
         `(published, RESOLUTION_RESOLVED_ENGINE, "published-target")` — the
         NEW disjunct, added this chunk. Checked first so its provenance
         wins when both disjuncts would fire, per § The provenance seam's
         naming.
         Else if `published` and `_is_engine_working_repo() is False` →
         `(published, RESOLUTION_RESOLVED_ENGINE, "published-legacy-gate")`
         — the ORIGINAL, single disjunct from before this chunk, unchanged
         in condition, renamed to make explicit it is one of two now.
         Retires at C5.
      3. Else `live, live_provenance = _resolve_live_working_tree()`; if
         `live`:
           - if `published` and NOT `target_is_readable` (which, having
             passed step 2's checks, also implies `_is_engine_working_repo()`
             is not concretely `False`) → `(live, RESOLUTION_LIVE_WORKING_
             TREE, "live-no-target")` — both disjuncts failed even though a
             published engine existed; the rollout no-op named above.
           - else → `(live, RESOLUTION_LIVE_WORKING_TREE, live_provenance)`
             — no published engine existed at all, so there was nothing to
             fail to divert to; covers working repos, undeterminable repos,
             and (pre-activation) every repo. `_resolve_live_working_tree`
             reports its OWN answering rung — `"live-env-dup"`,
             `"live-registry"`, or `"sibling-walk"` (matching § The
             provenance seam's vocabulary verbatim) — rather than this
             function collapsing them to one value from outside. Recording
             it at the rung that answers, instead of re-deriving which
             sub-check fired by re-running the checks here, is what keeps
             this a single ladder rather than growing a second one that can
             silently disagree with the first — see that helper's own
             docstring for the full per-rung breakdown, including why
             `"live-env-dup"` became reachable through this call path once
             rung 0 gained its health guard: an unhealthy override refused
             upstream is re-answered here as a bare locator.
      4. Else if `published` → `(published, RESOLUTION_RESOLVED_ENGINE,
         "published-fallback")` — a published engine beats no engine at
         all.
      5. Else `(None, RESOLUTION_UNRESOLVED, "none")`.

    Zero-spawn, fail-open, never raises — same contract as
    `resolve_claude_klabauter_root_with_class` and `resolve_claude_klabauter_root`, both of which
    delegate here. That promise is ENFORCED, not merely stated: the whole
    rung ladder runs inside one `try`, and anything escaping a rung degrades
    to `(None, RESOLUTION_UNRESOLVED, "none")` plus a single `_warn_fail_open`
    line. The per-rung callees carry their own `except Exception` handlers;
    this outer guard covers what they cannot — the rung-0 call itself, the
    sequencing between rungs, and any future edit to this body. Negative-
    spec: it was absent until a live `NameError` from a half-landed edit to
    the rung ladder escaped through both this function and
    `run_stop_hook_pointer_shim` and killed two Stop hooks with tracebacks in
    a live engine-plane session (2026-08-08).

    No memoization (see `_is_engine_working_repo`'s own docstring, the
    passage beginning "No memoization was added at the producer-landing
    change..."): every rung is re-derived on each call, deliberately — see
    that negative-spec before adding a cache here.
    """
    try:
        env_override = _resolve_live_tree_env_override()
        if env_override:
            if (Path(env_override) / "coordinator_core").is_dir():
                return env_override, RESOLUTION_LIVE_WORKING_TREE, "env-override"
            override_var = next(
                (v for v in LIVE_TREE_ENV_VARS if os.environ.get(v) == env_override),
                "unknown-env-var",
            )
            _warn_fail_open(
                "resolve_claude_klabauter_root_with_provenance (rung 0 override unhealthy)",
                RuntimeError(
                    f"{override_var}={env_override} has no coordinator_core/ — "
                    "falling through to the rest of the ladder"
                ),
            )

        published = _resolve_published_engine()
        target_is_readable = _resolve_engine_target() is not None

        if published and target_is_readable:
            return published, RESOLUTION_RESOLVED_ENGINE, "published-target"

        if published and _is_engine_working_repo() is False:
            return published, RESOLUTION_RESOLVED_ENGINE, "published-legacy-gate"

        live, live_provenance = _resolve_live_working_tree()
        if live:
            if published and not target_is_readable:
                return live, RESOLUTION_LIVE_WORKING_TREE, "live-no-target"
            return live, RESOLUTION_LIVE_WORKING_TREE, live_provenance

        if published:
            return published, RESOLUTION_RESOLVED_ENGINE, "published-fallback"

        return None, RESOLUTION_UNRESOLVED, "none"
    except Exception as exc:
        _warn_fail_open("resolve_claude_klabauter_root_with_provenance", exc)
        return None, RESOLUTION_UNRESOLVED, "none"


def resolve_claude_klabauter_root_with_class() -> tuple[str | None, str]:
    """Resolve the engine root AND say which class of thing answered.

    Two-value wrapper over `resolve_claude_klabauter_root_with_provenance`, dropping
    the provenance rung — see that function's docstring for the full rung
    ladder, the fail-open contract, and the provenance vocabulary. Kept as
    its own function (rather than folded away) because most existing callers
    only need the class; `resolve_claude_klabauter_root_with_provenance` is preferred
    for any caller that can also surface WHICH rung answered.
    """
    root, klass, _provenance = resolve_claude_klabauter_root_with_provenance()
    return root, klass


def resolve_claude_klabauter_root() -> str | None:
    """Resolve the engine root, fail-open (never raise).

    Thin wrapper over `resolve_claude_klabauter_root_with_class`, dropping the class —
    kept because callers predating the resolved-engine rung depend on this
    exact signature. See `resolve_claude_klabauter_root_with_provenance` for the
    canonical rung-by-rung ladder (this wrapper's own rung list previously
    drifted from that canonical one into a stale, differently-numbered
    breakdown — reconciled here by pointing at the one true ladder rather
    than duplicating it again). New callers that can surface WHICH engine
    they executed, or WHICH rung answered, should prefer the `_with_class`
    or `_with_provenance` forms respectively.
    """
    return resolve_claude_klabauter_root_with_class()[0]


def _resolve_live_tree_env_override() -> str | None:
    """Rung 0 of `resolve_claude_klabauter_root_with_class` — an EXPLICIT
    `REPO_CLAUDE_KLABAUTER`/`CLAUDE_KLABAUTER_ROOT` env var pointing at an existing
    directory, checked ahead of the published-engine rung.

    Split out from `_resolve_live_working_tree` so the class-reporting
    resolver can consult the explicit-override rung alone, before any
    ambient registry state (the published-engine mirror) gets a vote. Same
    env-var order and existence check as the first loop inside
    `_resolve_live_working_tree` — deliberately duplicated there too (rather
    than removed) so `_resolve_live_working_tree` alone still resolves the
    full live-tree ladder (env, then registry, then sibling walk) for any
    caller reaching it directly after the published-engine short-circuit.

    Zero-spawn, fail-open, never raises.
    """
    for env in LIVE_TREE_ENV_VARS:
        v = os.environ.get(env)
        if v and Path(v).is_dir():
            return v
    return None


def _resolve_live_working_tree() -> tuple[str | None, str]:
    """Rungs 1-3 — a CHECKOUT, whose contents are whatever is in it right now.

    Returns `(root, provenance)` (2026-08-16, C2 follow-on) — this helper now
    reports its OWN answering rung rather than leaving the caller to collapse
    every possible answer to one value or re-derive which sub-check fired.
    Recording it here, at the point each rung actually answers, is what keeps
    AC8 ("distinct provenance value per drivable state") satisfiable without
    growing a second copy of this ladder in `resolve_claude_klabauter_root_with_
    provenance` — the two-ladder-divergence defect this whole seam exists to
    prevent. `provenance` is `"none"` alongside a `None` root when nothing
    resolves, matching `resolve_claude_klabauter_root_with_provenance`'s own terminal
    value.

    Was split out unchanged when a since-deleted engine-snapshot rung landed
    ahead of it, so the live-tree ladder was one named thing the
    class-reporting resolver could point at distinctly from that rung. Every
    rung here answers "where is the checkout?"; the deleted rung answered
    "which engine do I execute?" — a distinction worth keeping even with that
    rung gone, because the forthcoming published-engine-mirror rung will draw
    the same line again. Those two questions coincide only on a
    co-development machine, which is why the divergence went unnoticed for as
    long as it did.

    Rung 1 here (the env-var loop below, provenance `"live-env-dup"`) is
    ALSO checked, alone, ahead of the published-engine rung by
    `_resolve_live_tree_env_override` — see that function's docstring for
    why. This function's own rung 1 stays in place so the full 1-3 ladder is
    still available to whatever reaches this function directly.

    This rung deliberately does NOT apply rung 0's `coordinator_core/`
    health guard, and the asymmetry is a decision, not an oversight. Rung 0
    answers "which engine do I execute, by stated intent?" — a stated intent
    that points at something which is not an engine checkout is refused, so
    it cannot outrank a healthy published engine. This ladder answers a
    different question: "where is the checkout?" Requiring `coordinator_core/`
    here would redefine the locator itself, and the cross-plane conformance
    fixture pins existing cases whose live trees are declared without one —
    flipping their expected outcomes would be a CASE-SET amend against a
    shared contract, in a chunk whose whole property is that no existing
    case's expectation changes.

    It was tried and measured, so the concrete harm is on record rather than
    left as an argument from principle. Guarding this rung does not merely
    relabel a rejected override: it makes the loop skip it, and control falls
    through to rung 3's sibling walk, which on a conventional side-by-side
    checkout resolves the REAL engine repo next door. The operator who set an
    unhealthy override would silently get an unrelated live tree instead of
    the one they named — strictly worse than the duplicate-label consequence
    the guard was meant to prevent, and inconsistent with the rest of this
    sub-ladder (the registry rung and the sibling walk have never carried a
    health requirement either). The live-tree contract is "whatever is
    actually there," not "whatever is healthy."

    The consequence, stated plainly because it is the non-obvious part:
    `"live-env-dup"` IS reachable through
    `resolve_claude_klabauter_root_with_provenance`'s own call path, and became so
    when rung 0 gained its health guard. A set-but-unhealthy override — an
    existing directory with no `coordinator_core/` — is refused by rung 0,
    falls through, and, when neither rung-2 disjunct fires, is answered here
    instead, returning that same path under `"live-env-dup"` rather than
    `"env-override"`. No concurrent env mutation is required. The provenance
    split is what makes that visible: an operator seeing `"live-env-dup"`
    through the full seam is being told the override was rejected upstream
    and re-answered as a bare locator, which is exactly the diagnostic the
    unhealthy case needs. A caller reaching this function directly (a test,
    or a future caller that skips rung 0) sees the same rung with no health
    filtering at all.

    Rung 2, provenance `"live-registry"`: the machine-local registry's
    `repos.claude_klabauter` key -- on this mirror that is the SAME
    registry key the published-engine rung reads; the two-rung distinction
    the engine-source plane preserves collapses to one key here.

    Rung 3, provenance `"sibling-walk"`: the last-resort directory-next-to-
    this-repo walk — see `resolve_claude_klabauter_root`'s own negative-spec for why
    it is kept despite its layout-specific fragility.
    """
    for env in LIVE_TREE_ENV_VARS:
        v = os.environ.get(env)
        if v and Path(v).is_dir():
            return v, "live-env-dup"

    try:
        reg_dir = _settings_home_registry_dir()
        v = _registry_value(reg_dir, "repos.claude_klabauter")
        if v and Path(v).is_dir():
            return v, "live-registry"
    except Exception:
        pass

    try:
        # __file__ = <repo>/coordinator/hooks/scripts/_engine_root.py
        repo_root = Path(__file__).resolve().parents[3]
        sibling = repo_root.parent / _CLAUDE_KLABAUTER_SIBLING_DIR_NAME
        if sibling.is_dir():
            return str(sibling), "sibling-walk"
    except Exception:
        pass

    return None, "none"


def run_stop_hook_pointer_shim(module_name: str) -> int:
    """Shared Stop-hook transport body for the Family-A pointer-shim pair
    (`nudge-unrouted-sizing.py`, `nudge-harness-directive-dispatch.py`,
    DR-047/DR-118 transport-seam carve-out).

    Both shims' `main()` bodies were IDENTICAL except for the imported engine
    module name (`coordinator_core.hooks.<module_name>`) — this function is
    that shared body, parameterised on the one thing that differed, so the
    pair no longer duplicates ~45 lines of executable statements. It is
    deliberately scoped to this ONE call shape (Stop JSON in on stdin →
    `m.op(payload)` → message-dict-or-degrade on stdout/exit code) — do not
    widen it into a general-purpose op dispatcher for other shim families;
    that is precisely the families-spanning shared-transport module this
    plan's § Recommendation declines to build. Living in `_engine_root.py`
    (rather than a new file) keeps the constraint "no NEW cross-hook shared
    module" satisfied: this is the same seam both shims already import,
    carrying one more function.

    Contract (identical to each shim's own docstring — this function does not
    change it, only removes the duplication):
      stdin   — Stop JSON (session_id, transcript_path, cwd, stop_hook_active, agent_id…)
      stderr  — the nudge text, on fire only; plus, on an UNEXPECTED
                fail-open degrade (never on an expected one — an
                unresolvable engine, a malformed payload, an `op()` that
                declines), one `_warn_fail_open` line alongside exit 0
      returns 2 — nudge fires (caller should block the stop; stderr is shown to Claude)
      returns 0 — every other path, including every failure path

    Graceful degradation — REQUIRED, same as each caller's own contract: any
    failure to read stdin, resolve the engine root, import the named engine
    module, parse the payload, or run/translate `op()`'s result falls through
    to 0. Never raises.

    `module_name` is the short name under `coordinator_core.hooks` (e.g.
    `"nudge_unrouted_sizing"`) — this function imports
    `coordinator_core.hooks.<module_name>` and calls its `op(payload)`.
    """
    import json
    import sys

    try:
        raw = sys.stdin.read()
    except Exception:
        # stdin read (broken pipe, decode error) is part of the same
        # fail-open surface as every other path below; must never crash the
        # turn.
        return 0

    try:
        root = resolve_claude_klabauter_root()
    except Exception as exc:
        # The resolver promises never to raise and now enforces it, but this
        # transport's own contract names engine-root resolution as a
        # fail-open surface — it must hold even if that promise is broken
        # again upstream, which is exactly how two Stop hooks died with
        # tracebacks on 2026-08-08.
        _warn_fail_open("run_stop_hook_pointer_shim/resolve_claude_klabauter_root", exc)
        return 0
    if not root:
        return 0  # engine unresolvable on this machine

    if root not in sys.path:
        sys.path.insert(0, root)

    try:
        import importlib

        m = importlib.import_module(f"coordinator_core.hooks.{module_name}")
    except Exception:
        return 0

    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return 0
    except Exception:
        return 0

    try:
        result = m.op(payload)
    except Exception:
        return 0  # any engine failure → let the turn end

    # The engine's return value is untrusted shape, not just untrusted
    # content. A truthy non-dict result or a non-str "message" must degrade
    # to 0 too, per this function's own "no failure mode here that exits
    # non-zero" contract.
    try:
        if result and isinstance(result, dict):
            msg = result.get("message")
            if isinstance(msg, str) and msg:
                sys.stderr.write(msg)
                return 2
    except Exception:
        return 0
    return 0


def arm_lazy_ops() -> None:
    """Suppress `coordinator_core.ops`' eager all-op-module registration for
    THIS process only. MUST be called BEFORE the first `import coordinator_core.*`.

    Why: `coordinator_core/ops/__init__.py` imports ~80 op modules at package-init
    time to populate the op registry. A hook stub that reaches into ONE engine
    module (`from coordinator_core.ops.session.X import evaluate_Y`) still pays
    for all 80 — measured on this machine at ~100ms of the ~122ms a SessionStart
    guard stub costs end-to-end, against ~2ms of actual guard logic. Arming the
    lazy channel drops that engine-import leg from ~101ms to ~23ms.

    This is the in-process channel documented at
    `coordinator_core.ops._lazy_ops_requested` — a `sys` attribute, deliberately
    NOT an env var, so it is inherited by no child process. Two writers existed
    before this one (`coordinator_core.invoke.__main__` and
    `coordinator/bin/lib/cc_invoke.py`); hook stubs are the same shape of caller
    those two are: short-lived processes that touch a single named op module.

    Safe for registry dispatch too, not just direct-import stubs: a registry miss
    under lazy mode falls back to `_eager_import_all()`, so an op looked up by
    name still resolves — it just pays the eager cost at lookup instead of at
    import. Callers that dispatch by name and are latency-sensitive should still
    prefer `cc_invoke`, which arms this channel itself.

    Never raises: an engine whose `ops` package predates the lazy channel simply
    ignores an attribute it does not read. The operator override
    `COORDINATOR_CORE_LAZY_OPS` still wins in BOTH directions over this call.
    """
    import sys

    sys._coordinator_core_lazy_ops = True  # type: ignore[attr-defined]


if __name__ == "__main__":
    # CLI entrypoint so a `.md` command/skill fence (which cannot `import`
    # this module) resolves the claude-klabauter root by shelling out to this SAME
    # seam instead of hand-rolling a second, bash-native TOML reader — one
    # implementation, three consumers (Python import, `_claude_klabauter-root.js`
    # mirror, this CLI). Prints the resolved path, or an empty line on total
    # miss (never raises, never prints "None") so a fence can test with a
    # plain `[ -z "$var" ]` check. Deliberately not zero-spawn (unlike the
    # importable function, which the hot-path hooks require) — a `.md` fence
    # already pays a `python3` invocation for its main body of work, so one
    # more short-lived interpreter start here is not a new cost class.
    print(resolve_claude_klabauter_root() or "")
