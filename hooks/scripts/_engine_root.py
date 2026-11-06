"""Shared engine-root resolution seam for coordinator/hooks/scripts/*.py hooks.

Purpose: every hook that needs to import `coordinator_core` resolves the
engine root through this ONE seam — one place to fix, one place to test. Only
a stamped engine root answers (the registered claude-klabauter mirror, or a
stamped directory named by the rung-0 env var); no rung selects an
engine-source working tree. The importable resolvers return
`(None, "unresolved")` on a miss and never raise; the CLI entrypoint exits 2
naming the claude-klabauter fetch.

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
`bin`/`lib`/`scripts`/`tests` relocated to the engine repo; `coordinator/schemas/`
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
    `<value>/.coordinator-claude-settings/machine-local` path.
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

    coordinator/tests/test_settings_home_ladder_parity.py is the guard that
    keeps this copy in step with templates/bin/_machine_local.py::_settings_home.
    """
    override = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if override:
        return Path(override)
    base = os.environ.get("CLAUDE_HOME") or str(Path.home())
    return Path(base) / ".coordinator-claude-settings"


# Resolution classes returned alongside the root by
# `resolve_claude_klabauter_root_with_class`. RESOLVED_ENGINE means a stamped engine
# root (the registered claude-klabauter mirror, or a stamped directory named
# by the rung-0 env var); UNRESOLVED means no engine answered. No rung returns
# LIVE_WORKING_TREE: an engine-source working tree is never the engine. The
# constant stays exported for consumers that still compare against it.
RESOLUTION_RESOLVED_ENGINE = "resolved-engine"
RESOLUTION_LIVE_WORKING_TREE = "live-working-tree"
RESOLUTION_UNRESOLVED = "unresolved"

#: Env var(s) the rung-0 override consults. It answers only for a stamped
#: engine root (`_is_stamped_engine_root`); an engine-source working tree
#: carries no `coordinator_core/_engine_stamp` and is refused. Exported as a
#: constant so consumers that must SET one — the OSS-only `coordinator-update`
#: skill's tests, notably — name it by reference: the injected skill payload
#: skips the publish content-transform sweep, so a literal on the consumer
#: side would name a variable the published resolver no longer reads.
LIVE_TREE_ENV_VARS = ("COORDINATOR_ENGINE_ROOT",)


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


def _warn_floor_notice(root: str, verdict) -> None:
    """Emit ONE stderr notice line for a behind/indeterminate engine-floor verdict.

    Notice only: the resolved tuple is never changed. The write is guarded so
    a closed stderr cannot raise.
    """
    try:
        import sys

        if verdict.state == "behind":
            line = (
                f"[_engine_root] engine {root}: stamp {verdict.stamp} behind claude-klabauter "
                f"floor {verdict.floor} (coordinator/engine-floor.json); "
                "remedy: refresh the published engine\n"
            )
        else:
            line = (
                f"[_engine_root] engine {root}: engine floor check indeterminate "
                f"({verdict.cause}); floor {verdict.floor} "
                "(coordinator/engine-floor.json) not enforced\n"
            )
        sys.stderr.write(line)
    except Exception:
        pass


def _load_engine_floor():
    """The sibling `_engine_floor` module, importable whatever sys.path holds."""
    import sys

    mod = sys.modules.get("_engine_floor")
    if mod is not None:
        return mod
    try:
        import _engine_floor as mod  # type: ignore[import-not-found]

        return mod
    except ImportError:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "_engine_floor", Path(__file__).resolve().with_name("_engine_floor.py")
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules["_engine_floor"] = mod
        spec.loader.exec_module(mod)
        return mod


def _apply_engine_floor(root, cls, prov):
    """Floor-check a published root; ALWAYS returns `(root, cls, prov)` unchanged.

    behind and indeterminate verdicts emit one stderr notice each; clean is
    silent. Any exception inside the check is swallowed here (an exception
    reaching the resolver's outer handler would drop a healthy engine).
    """
    try:
        verdict = _load_engine_floor().check_engine_floor(root)
        if verdict.state != "clean":
            _warn_floor_notice(root, verdict)
    except Exception:
        pass
    return root, cls, prov


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
    DECLARATIONS (see `docs/wiki/hook-best-practices/machine-local-registry.md`). Accepts both
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

    The walk does not fail closed to None once it passes `~/.claude`: it
    continues PAST `~/.claude` and MAY return an ANCESTOR of it (e.g.
    `Path.home()` itself, if that directory has its own unrelated `.git`)
    rather than stopping at `None`. `test_cwd_walk_skips_claude_home_but_
    finds_real_repo_above_it` pins exactly that. This is deliberate:
    continuing the walk lets a real repo genuinely above `~/.claude` resolve
    correctly instead of always failing closed, at the cost of accepting
    that ancestor if it happens to carry an unrelated `.git` of its own — a
    narrower, accepted risk, not a "fails closed" guarantee.

    Zero-spawn (no `git rev-parse`), never raises. Returns None if
    undeterminable.
    """
    harness_home = _harness_home_dir()

    env_root = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_root:
        try:
            p = Path(env_root)
            if p.is_dir():
                # This rung resolves `p`
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


# Unions across both registry files rather than first-hit-wins, per its own
# body comments.
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


def resolve_publish_mirror_roster() -> list[tuple[str, str, str]]:
    """Every registered `publish.mirrors.*` entry, as `(path, owner, key)` triples.

    2026-08-30 (DR-188 Option D, chunk C3): the `key` element (the
    `publish.mirrors.<key>` registry segment) was added so callers can test a
    row against `resolve_own_publish_target_keys()` -- the per-mirror gate
    that replaces the old unconditional roster leg in
    `engine_resolution_banner`. Every existing caller that destructured
    `(path, owner)` pairs must be updated to the 3-tuple; this is a
    deliberate breaking shape change, not an additive one.

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
    `docs/wiki/hook-best-practices/machine-local-registry.md` §5c.2's schema-shape example), so a
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
    roster: list[tuple[str, str, str]] = []
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
            roster.append((v, owners.get(key) or "unknown owner", key))

    return roster


_EXTERNAL_WORKSPACE_KIND = "external-readonly"


def resolve_external_workspace_roster() -> list[tuple[str, str, str, str]]:
    """Every registered `external_workspaces.<key>` entry, as `(path, key, kind, vcs)`.

    An external workspace is someone else's code on this box: findable by name
    and path, never a `repos.*` peer, memo receiver or `$REPO_*` export.
    `registry.local.toml` is merged over `registry.toml` per field (local wins),
    via `_flatten_registry`. An entry is listed only when `path` is a non-empty
    string naming an existing directory. `kind` is always returned as
    `external-readonly` (absent or unknown reads closed); `vcs` is the registry
    value or `""`. De-duplicated on key, first-seen order.

    Zero-spawn, never raises -- `[]` on any failure.
    """
    try:
        import tomllib
    except ImportError:
        return []
    try:
        reg_dir = _settings_home_registry_dir()
    except Exception:
        return []

    prefix = "external_workspaces."
    fields: dict[str, dict[str, str]] = {}
    for name in ("registry.local.toml", "registry.toml"):
        reg = reg_dir / name
        try:
            if not reg.is_file():
                continue
            with reg.open("rb") as fh:
                flat = _flatten_registry(tomllib.load(fh))
        except Exception:
            continue
        for k, v in flat.items():
            if not k.startswith(prefix) or not isinstance(v, str):
                continue
            key, _, field = k[len(prefix):].rpartition(".")
            if not key or field not in ("path", "vcs"):
                continue
            if v:
                fields.setdefault(key, {}).setdefault(field, v)

    roster: list[tuple[str, str, str, str]] = []
    for key, f in fields.items():
        path = f.get("path")
        if not path:
            continue
        try:
            if not Path(path).is_dir():
                continue
        except Exception:
            continue
        roster.append((path, key, _EXTERNAL_WORKSPACE_KIND, f.get("vcs", "")))
    return roster


def _canon_path(p: str) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(p)))


def external_workspace_containing(path: str | os.PathLike) -> tuple[str, str, str, str] | None:
    """The roster entry whose root equals or contains `path`, else None.

    Containment is by canonical equality or `root + os.sep` prefix
    (realpath + normcase). Never raises.
    """
    try:
        target = _canon_path(os.fspath(path))
        for entry in resolve_external_workspace_roster():
            root = _canon_path(entry[0])
            if target == root or target.startswith(root.rstrip(os.sep) + os.sep):
                return entry
            # Case-insensitive filesystems (macOS default) keep the spelling
            # realpath was handed; compare nearest existing ancestors by inode.
            cur = target
            while cur and not os.path.exists(cur):
                parent = os.path.dirname(cur)
                if parent == cur:
                    break
                cur = parent
            while cur and os.path.exists(cur):
                if os.path.samefile(cur, entry[0]):
                    return entry
                parent = os.path.dirname(cur)
                if parent == cur:
                    break
                cur = parent
    except Exception:
        return None
    return None


def resolve_own_publish_target_keys(repo_root: str | Path | None = None) -> set[str]:
    """Every `publish-mirror:<key>` sigil declared in THIS repo's own
    `setup/publish-targets.portable` -- the declared publish topology this
    repo owns, as distinct from `resolve_publish_mirror_roster()`'s
    per-machine registered mirror set.

    Spec: 2026-08-30 foreign-repo-identity-suppression plan, chunk C3
    (DR-188 Option D). A registered publish-mirror roster row is foreign
    identity to a session UNLESS it is either that session's own resolved
    engine root, or one of its OWN declared publish targets -- this function
    answers the second half. Reads the portable, TRACKED file (never the
    machine-local registry): a mirror this repo does not itself publish to
    is not "its own topology" merely because some registry entry happens to
    be populated on this machine.

    `repo_root` defaults to `_session_repo_root()` -- the session's own repo
    root, never this plugin's own installed location -- matching every other
    session-facing resolver in this module. Row grammar: pipe-delimited,
    `name|mode|<dest-sigil>|source_subdir|dest_subdir[|...]` (see
    `setup/publish-targets.portable`'s own header comment); only the
    `publish-mirror:<key>` dest-sigil form (field index 2) is relevant here --
    `repo:<key>` rows name working-repo destinations, a different namespace,
    and are ignored.

    Zero-spawn, never raises: an absent file, an unreadable file, or a
    malformed row all degrade to an empty set rather than raising, matching
    this module's standing fail-open convention.
    """
    try:
        root = Path(repo_root) if repo_root is not None else _session_repo_root()
    except Exception:
        root = None
    if root is None:
        return set()

    portable = Path(root) / "setup" / "publish-targets.portable"
    try:
        text = portable.read_text(encoding="utf-8")
    except Exception:
        return set()

    keys: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = stripped.split("|")
        if len(fields) < 3:
            continue
        dest = fields[2].strip()
        if dest.startswith("publish-mirror:"):
            key = dest[len("publish-mirror:") :].strip()
            if key:
                keys.add(key)
    return keys


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
    # Catch Exception, not just OSError: an unusual filesystem/encoding edge
    # case must not propagate out of this function, or the outer tri-state
    # collapses None (undeterminable) into False. "Never raises" holds by
    # construction rather than by convention.
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
    consumer MUST NOT treat `None` as `False`.

    Not a ladder input: `resolve_claude_klabauter_root_with_provenance` never consults
    it, so it cannot select or refuse a root. No memoization: this module is consumed by short-lived,
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
    # `_same_repo_path` never raises, but this loop tracks raised-vs-not
    # defensively too: returning False (CONFIRMED non-working) after every
    # comparison raised would collapse "couldn't determine" into "not a
    # match" if `_same_repo_path` ever gained a raising path.
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

    **Stamp gate (2026-08-29).** The engine plane's own dispatch axis now
    treats "an engine root is a stamped build" as load-bearing, not merely
    measured — a directory only counts as a resolvable engine when it
    carries a valid `coordinator_core/_engine_stamp`
    (`docs/plans/2026-08-19-an-engine-root-is-a-stamped-build.md` § C2/C4 on
    their side; `coordinator_core.warm.engine_root.is_engine_root` is their
    canonical predicate). This module cannot import that predicate — it
    must not import `coordinator_core` at all (module docstring) — so the
    check is reimplemented locally, at the SAME validity bar their
    predicate uses (readable and non-empty, not merely present: a partial
    write can leave a zero-byte file behind) rather than the cheaper bare
    `isfile` their own bootstrap hot-path (`engine_bootstrap.py` rung 1.5)
    accepts for its own, differently-costed reason. This is the ONLY rung
    in this module that resolves `RESOLUTION_RESOLVED_ENGINE` — see
    `resolve_claude_klabauter_root_with_provenance`'s ladder, every one of whose
    published-engine returns flows through this function's `root` — so
    gating here alone makes "no unstamped tree is ever the resolved engine"
    true on this ladder too, matching the reciprocal heads-up this
    responds to (`cross-repo/inbox/2026-08-19-claude-klabauter-em-engine-
    root-ladder-coupling-heads-up.md`).

    Per-call cost: one additional `Path.read_bytes()` on a single-line file
    (the stamp is `sha:<sha>\n`, a few dozen bytes) — one more syscall on
    top of the two `is_dir()` checks this rung already pays, on the hot
    path this rung reaches only when a published engine is registered at
    all (most machines never reach this rung — see `resolve_claude_klabauter_root_
    with_provenance`'s own cost framing for the rungs ahead of this one).

    Zero-spawn, fail-open, never raises — any registry-read or filesystem
    exception yields `None`, same contract as every other rung in this
    module.
    """
    try:
        reg_dir = _settings_home_registry_dir()
        root = _registry_value(reg_dir, "repos.claude_klabauter")
        if not root:
            return None
        return root if _is_stamped_engine_root(root) else None
    except Exception:
        return None


def _is_stamped_engine_root(root: str) -> bool:
    """True when `root` is an existing directory whose `coordinator_core/`
    carries a readable, non-empty `_engine_stamp`. The stamp is the only test
    of "this is a built engine"; an engine-source working tree has none.
    Never raises."""
    try:
        root_path = Path(root)
        if not (root_path / "coordinator_core").is_dir():
            return False
        stamp_bytes = (root_path / "coordinator_core" / "_engine_stamp").read_bytes()
        return bool(stamp_bytes)
    except Exception:
        return False


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

    **Provenance only.** The ladder uses this value solely to pick
    `"published-target"` over `"published-no-target"`; readability never
    decides whether the registered engine answers.

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

    No rung returns an engine-source working tree: the ladder answers a
    stamped engine root or nothing.

    **Cross-plane downstream consumer — this ladder is not repo-local.** The
    engine plane's warm-server generation token fingerprints
    `coordinator_core/_engine_stamp` in whichever clone THIS ladder resolved,
    so a rung reordering here changes warm-generation behaviour in the engine
    plane with no engine commit and no engine test. Rung ordering changes
    carry the same cross-repo heads-up duty as a change to the hook
    invocation shape: tell the engine team's EM before it lands.

    **Precedence rule.** An engine-source working tree is never the engine,
    at any rung: only a STAMPED engine root answers. A registry live key, a
    sibling engine checkout, the working-repo gate (`True`, `False` or
    `None`) and an unstamped env-named directory never select anything.
    The provenance `"published-no-target"` names a registered engine that
    won while `engine.target` is unset, so orientation can tell the box
    which key to add.

    **Rung 0 stamp guard.** The explicit env-var override answers only for a
    stamped engine root (`_is_stamped_engine_root`): a stale, typo'd, moved
    or unstamped override (an engine-source working tree has no stamp) falls
    through to the rest of the ladder, emitting one `_warn_fail_open`-class
    line naming the env var and the path. A stamped override wins outright.

    **Resolution order — FAIL-OPEN is the load-bearing property here, not an
    incidental one.** `_resolve_published_engine` fires once
    `repos.claude_klabauter` is registered on the current machine (written
    at install time by the engine plane's own installer,
    `scripts/setup.py::register_claude_klabauter_root()`). On a machine with no such
    registration, and no stamped env override, the ladder degrades to
    unresolved and the caller fails loud:

      0. `env_override = _resolve_live_tree_env_override()` (an explicit
         env var, see `LIVE_TREE_ENV_VARS`, naming an existing directory).
         If set AND stamped →
         `(env_override, RESOLUTION_RESOLVED_ENGINE, "env-override")` — an
         explicit override outranks ambient registry state, published-engine
         registration included. If set but NOT stamped, one
         `_warn_fail_open`-class line is emitted and resolution falls
         through rather than answering.
      1. `published = _resolve_published_engine()`. If set →
         `(published, RESOLUTION_RESOLVED_ENGINE, "published-target")` when
         `_resolve_engine_target()` is not `None`, else
         `(published, RESOLUTION_RESOLVED_ENGINE, "published-no-target")`.
      2. Else `(None, RESOLUTION_UNRESOLVED, "none")`. Importable callers
         degrade on it; the CLI entrypoint exits 2 naming the
         claude-klabauter fetch.

      Every resolved answer (rung 0's stamped override, "published-target",
      "published-no-target") passes through `_apply_engine_floor`: a behind
      or indeterminate engine floor verdict emits one stderr notice and the
      tuple is unchanged.

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

    No memoization (see `_is_engine_working_repo`'s own docstring): every
    rung is re-derived on each call, deliberately — see that negative-spec
    before adding a cache here.
    """
    try:
        env_override = _resolve_live_tree_env_override()
        if env_override:
            if _is_stamped_engine_root(env_override):
                published = _resolve_published_engine()
                if published and os.path.realpath(env_override) == os.path.realpath(published):
                    return _apply_engine_floor(
                        published, RESOLUTION_RESOLVED_ENGINE, "published-target"
                    )
                return _apply_engine_floor(
                    env_override, RESOLUTION_RESOLVED_ENGINE, "env-override"
                )
            override_var = next(
                (v for v in LIVE_TREE_ENV_VARS if os.environ.get(v) == env_override),
                "unknown-env-var",
            )
            _warn_fail_open(
                "resolve_claude_klabauter_root_with_provenance (rung 0 override unstamped)",
                RuntimeError(
                    f"{override_var}={env_override} is not a stamped engine root — "
                    "falling through to the rest of the ladder"
                ),
            )

        published = _resolve_published_engine()
        if published:
            provenance = (
                "published-target" if _resolve_engine_target() is not None else "published-no-target"
            )
            return _apply_engine_floor(published, RESOLUTION_RESOLVED_ENGINE, provenance)

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
    """Rung 0 of `resolve_claude_klabauter_root_with_class` — an EXPLICIT env var (see
    `LIVE_TREE_ENV_VARS`) naming an existing directory, checked ahead of the
    published-engine rung. Existence only: the ladder applies the stamp test
    (`_is_stamped_engine_root`) before it answers.

    Zero-spawn, fail-open, never raises.
    """
    for env in LIVE_TREE_ENV_VARS:
        v = os.environ.get(env)
        if v and Path(v).is_dir():
            return v
    return None


def _resolve_live_working_tree() -> tuple[str | None, str]:
    """Locator compatibility stub: always `(None, "none")`.

    NEGATIVE-SPEC — an engine-source working tree is never inferred, from a
    registry key, a sibling-checkout walk, a pointer file or an env var, and
    the ladder does not consult this function. `repos.claude_klabauter` is the
    sole carrier of published-engine LOCATION; a settings-home pointer file of
    a similar name belongs to the engine's perf cache and must not be read here.
    Callers that import this name degrade to "no live tree".
    """
    return None, "none"


_PLUGIN_ROOT_WALK_MAX_LEVELS = 12


def _find_plugin_root(start: Path) -> Path | None:
    """Walk upward from `start` to the nearest ancestor containing a
    `.claude-plugin/` directory — the plugin root under BOTH shipped
    layouts. Under the nested layout the plugin root is `<repo>/
    coordinator`; under the flat mirror layout the plugin root IS the repo
    root (`.claude-plugin/` sits directly under it). Bounded to
    `_PLUGIN_ROOT_WALK_MAX_LEVELS` ancestors so a filesystem with no `.claude-plugin/`
    anywhere above `start` (a stray copy of this file, a test fixture)
    cannot walk indefinitely — returns `None` once the walk reaches the
    filesystem root or exhausts the bound, whichever comes first.

    Negative-spec: this replaces a fixed `Path(__file__).resolve().parents[3]`
    count that was correct only for the nested layout
    (`<repo>/coordinator/hooks/scripts/_engine_root.py`) and silently wrong
    under the flat mirror layout this file also ships into
    (`<repo>/hooks/scripts/_engine_root.py`), where that same fixed count
    lands two levels above the clone and the sibling probe below it could
    never hit — the hidden cause of a cold-box bootstrap deadlock on the
    recommended install path, where the installed-plugin-cache anchor makes
    every other rung dead by construction too.
    """
    current = start
    for _ in range(_PLUGIN_ROOT_WALK_MAX_LEVELS):
        if (current / ".claude-plugin").is_dir():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent
    return None


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

    place_engine_root_on_path(root)

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
    THIS process only, on an engine old enough to still have a mode to select.
    MUST be called BEFORE the first `import coordinator_core.*`.

    Backward-compatibility affordance, not a live control channel. Current
    engines register lazily UNCONDITIONALLY: `coordinator_core/ops/__init__.py`
    retired its `_lazy_ops_requested()` gate, so it reads neither this `sys`
    attribute nor the `COORDINATOR_CORE_LAZY_OPS` env var, and this call is an
    inert no-op against such an engine. It is retained because an install
    resolves whatever engine revision is on disk, and against a PRE-retirement
    engine this call is still the difference between the lazy and eager import
    paths. Retire it — and every call site at once, never a subset — once the
    fleet's engine floor is past that retirement.

    Why it mattered: a pre-retirement `ops/__init__.py` imported ~80 op modules
    at package-init time to populate the op registry, so a hook stub reaching
    into ONE engine module
    (`from coordinator_core.ops.session.X import evaluate_Y`) still paid for all
    80 — measured on this machine at ~100ms of the ~122ms a SessionStart guard
    stub costs end-to-end, against ~2ms of actual guard logic. Arming dropped
    that engine-import leg from ~101ms to ~23ms.

    The channel is a `sys` attribute, deliberately NOT an env var, so it is
    inherited by no child process. Two writers existed before this one
    (`coordinator_core.invoke.__main__` and `coordinator/bin/lib/cc_invoke.py`);
    hook stubs are the same shape of caller those two are: short-lived processes
    that touch a single named op module.

    Safe for registry dispatch too, not just direct-import stubs: a registry miss
    resolves the op through its targeted per-op import on either engine, so an op
    looked up by name still resolves — under a pre-retirement engine it just pays
    the eager cost at lookup instead of at import.

    Never raises: setting an attribute on `sys` cannot fail, and an engine that
    does not read it simply ignores it. Against a PRE-retirement engine ONLY,
    that engine's own operator override `COORDINATOR_CORE_LAZY_OPS` still wins in
    both directions over this call ("1" forces lazy, "0" forces eager); a current
    engine reads neither, so there is no precedence left to state.
    """
    import sys

    sys._coordinator_core_lazy_ops = True  # type: ignore[attr-defined]


def place_engine_root_on_path(root: str) -> str:
    """Put the resolved engine `root` on `sys.path` where it can actually win,
    WITHOUT displacing the hooks dir from index 0. Returns `root` unchanged so a
    caller can end on `return place_engine_root_on_path(root)`.

    This is the one primitive every hook uses to reach the engine; do not
    hand-roll the placement at a call site.

    **Why not `sys.path.append`, which the runner contract used to mandate.**
    The contract's requirement is that the hooks dir stay AHEAD of the engine
    root, so a module-NAME collision resolves toward the doctrine-plane-local
    helper. Appending satisfies that and nothing else: it puts the root at the
    END of `sys.path`, behind site-packages, and therefore behind an editable
    install of the engine (`__editable__.coordinator_core-*.pth` naming the
    WORKING TREE). On such a box the resolver answers the published mirror and
    the import returns the working tree -- in a clean process, every time, with
    nothing else having run. Append cannot lose to a late import because it has
    already lost to site-packages.

    Index 1 satisfies the contract's ACTUAL requirement and outranks
    site-packages: hooks dir at 0, engine root at 1. When the hooks dir is not
    at index 0 (a caller that resolved the engine before its own
    self-resolution), the root goes to index 0 -- being outranked by
    site-packages is the failure this exists to prevent, and there is no
    collision to lose because the hooks dir is not competing yet.

    Idempotent: a root already at index 0 or 1 is left alone. A root elsewhere
    on `sys.path` -- e.g. appended by an older caller in the same process -- is
    MOVED, because leaving it where it cannot win is the whole defect.

    Never raises: `sys.path` manipulation cannot fail, and a falsy root is a
    no-op returning what it was given.

    Placement is necessary, not sufficient -- it loses to a module cache already
    bound by an earlier bare import. Confirm the outcome with
    `engine_import_provenance()`; see
    [[A-FRONT-INSERTED-ENGINE-ROOT-LOSES-TO-THE-MODULE-CACHE]].
    """
    import sys

    if not root:
        return root

    hooks_dir = str(Path(__file__).resolve().parent)
    target = 1 if (sys.path and sys.path[0] == hooks_dir) else 0

    if root in sys.path[:2]:
        return root
    while root in sys.path:
        sys.path.remove(root)
    sys.path.insert(target, root)
    return root


PROVENANCE_UNIMPORTED = "unimported"
PROVENANCE_MATCH = "match"
PROVENANCE_DIVERGENT = "divergent"
PROVENANCE_UNRESOLVED = "unresolved"


def engine_import_provenance() -> tuple[str, str | None, str | None]:
    """Where the ALREADY-IMPORTED `coordinator_core` actually came from,
    against the root this module resolves. Returns
    `(verdict, imported_file, engine_root)` where verdict is one of
    `PROVENANCE_UNIMPORTED` / `PROVENANCE_MATCH` / `PROVENANCE_DIVERGENT` /
    `PROVENANCE_UNRESOLVED`.

    Why this is not redundant with `sys.path.insert(0, root)`. Front-inserting
    the resolved root is the correct guard and it wins in a clean process, but
    it is defeated by the module cache: once ANYTHING in the process has done a
    bare `import coordinator_core`, `sys.modules` is bound and every later
    insert is a no-op. On a box with an editable install
    (`site-packages/__editable__.coordinator_core-*.pth` naming the engine's
    WORKING TREE) that ambient path is on `sys.path` from site init, so the
    losing case is the default rather than the exception. The insert asserts
    an intent; this asserts the outcome.

    Negative spec -- what this deliberately does NOT do:

    - It does NOT import `coordinator_core`. A consumer that has not imported
      the engine gets `PROVENANCE_UNIMPORTED`, never an import as a side
      effect of asking a question. Calling this on a hot-path hook that never
      touches the engine must stay free.
    - It does NOT raise, on any input or any filesystem state. Hooks call it;
      `UserPromptSubmit` is blocking and a non-zero exit rejects the human's
      prompt. Every fallible step degrades to `PROVENANCE_UNRESOLVED`.
    - It does NOT mutate `sys.path` to repair a divergence. By the time this
      can observe one, the module object is already bound and handed out;
      re-pathing would produce a second, differently-rooted copy of the same
      package, which is strictly worse than one wrong copy.

    The failure this exists to make visible is silent, not loud: both trees
    export the same names, so a consumer reading the wrong one differs only in
    behaviour or timing that will not reproduce elsewhere -- and can still pass
    every budget and assertion it is checked against.
    """
    try:
        import sys

        module = sys.modules.get("coordinator_core")
        if module is None:
            return (PROVENANCE_UNIMPORTED, None, None)

        imported_file = getattr(module, "__file__", None)
        if not imported_file:
            return (PROVENANCE_UNRESOLVED, None, None)

        root = resolve_claude_klabauter_root()
        if not root:
            return (PROVENANCE_UNRESOLVED, str(imported_file), None)

        imported_resolved = Path(imported_file).resolve()
        root_resolved = Path(root).resolve()
        try:
            imported_resolved.relative_to(root_resolved)
        except ValueError:
            return (PROVENANCE_DIVERGENT, str(imported_resolved), str(root_resolved))
        return (PROVENANCE_MATCH, str(imported_resolved), str(root_resolved))
    except Exception as exc:
        _warn_fail_open("engine_import_provenance", exc)
        return (PROVENANCE_UNRESOLVED, None, None)


def warn_on_engine_import_divergence(where: str) -> str:
    """Emit ONE stderr line if the imported engine is not the resolved one,
    and return the verdict. Never raises; safe on a blocking hook.

    Deliberately a warning and not a hard failure at the hook seam: a
    divergent engine still executes, and converting an observability gap into
    a prompt rejection trades a silent problem for a louder one the operator
    did not ask for. Tests are where this verdict is an assertion -- see
    `coordinator/tests/test_engine_import_provenance.py`.
    """
    verdict, imported_file, root = engine_import_provenance()
    if verdict != PROVENANCE_DIVERGENT:
        return verdict
    try:
        import sys

        sys.stderr.write(
            f"[_engine_root] engine import divergence in {where}: "
            f"imported {imported_file!r}, resolved root {root!r} -- "
            "an earlier bare `import coordinator_core` bound the module cache "
            "before the front-insert ran\n"
        )
    except Exception:
        pass
    return verdict


def resolve_engine_bin_script(name: str) -> Path | None:
    """`<engine root>/coordinator/bin/<name>`, or None when the root or the script is absent.

    `coordinator/bin/<name>` in this repo is a forwarder for every engine-owned script, so an
    in-process load by path must target this copy, never the forwarder. Zero-spawn.
    """
    root = resolve_claude_klabauter_root()
    if not root:
        return None
    target = Path(root) / "coordinator" / "bin" / name
    return target if target.is_file() else None


if __name__ == "__main__":
    # CLI entrypoint so a `.md` command/skill fence (which cannot `import`
    # this module) resolves the engine root by shelling out to this SAME
    # seam instead of hand-rolling a second, bash-native TOML reader — one
    # implementation, three consumers (Python import, `_claude_klabauter-root.js`
    # mirror, this CLI). A hit prints the path and exits 0; a miss prints
    # nothing to stdout, names the fix on stderr, and exits 2. A fence tests
    # the exit code; a non-empty stdout is still the path. The importable
    # functions stay fail-open. Deliberately not zero-spawn (unlike them) —
    # a `.md` fence already pays a `python3` invocation for its main body.
    import sys

    _root = resolve_claude_klabauter_root()
    if _root:
        print(_root)
        sys.exit(0)
    print(
        "engine root unresolved: no stamped claude-klabauter engine is registered. "
        "Fetch it (git clone https://github.com/dbc-oduffy/claude-klabauter), then set "
        "registry key repos.claude_klabauter in "
        f"{_settings_home_registry_dir() / 'registry.local.toml'} "
        "(INSTALL.md § Step 1e)",
        file=sys.stderr,
    )
    sys.exit(2)
