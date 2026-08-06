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
PreToolUse/PostToolUse dispatch, where DoE's own zero-spawn boot mandate
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

      1. `CLAUDE_PROJECT_DIR` env var, if set and points at a real directory.
      2. Pure-Python upward walk from `Path.cwd()` looking for a `.git` entry
         (directory for a normal clone, FILE for a worktree).

    Zero-spawn (no `git rev-parse`), never raises. Returns None if
    undeterminable.
    """
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


def resolve_claude_klabauter_root_with_class() -> tuple[str | None, str]:
    """Resolve the engine root AND say which class of thing answered.

    Returns `(root, resolution_class)` where the class is one of
    `RESOLUTION_RESOLVED_ENGINE` (a published engine mirror), or
    `RESOLUTION_LIVE_WORKING_TREE` (a checkout, contents whatever a concurrent
    session has in it right now), or `RESOLUTION_UNRESOLVED` (root is None).

    **Why this exists, and why it is not merely diagnostic.** Before it, a
    consumer executing a half-finished engine mid-edit saw a guard behaving
    oddly, an op erroring, or an agent politely declining — none of which is
    distinguishable, from the consumer's seat, from that engine behaving
    correctly. A live investigation on a sibling plane spent two days on a
    wrong theory for exactly this reason: the failure was silent by
    construction, not merely unlogged. Closing the race without making the
    resolution class observable would fix the smaller half of the defect.

    A live working tree is a LEGITIMATE answer, not a failure — on a
    co-development machine it is the answer you want. What this makes possible
    is that it be a deliberate, visible state rather than an invisible default.

    **Resolution order — FAIL-OPEN is the load-bearing property here, not an
    incidental one.** `RESOLUTION_RESOLVED_ENGINE` (the published-engine
    rung) now has a producer: `_resolve_published_engine` fires once
    `repos.claude_klabauter` is registered on the current machine (written
    at install time by the engine plane's own installer,
    `scripts/setup.py::register_claude_klabauter_root()`, commit `5080edc48d3f`, on a
    claude-klabauter checkout). On a machine with no such registration —
    every machine before its klabauter install runs — this ladder still
    degrades to exactly the live-tree-or-unresolved behaviour that existed
    before the working-repo gate was wired — byte-identical, not merely
    similar. Once a published engine DOES exist (registered on this
    machine), a repo is only ever diverted away from the live tree when
    `_is_engine_working_repo()` returns the concrete `False`
    determination — a `None` (undeterminable) never diverts, because
    diverting an undeterminable repo away from the live tree with no
    fallback would silently strand it exactly the way the deleted rung-0
    engine-snapshot producer once did (see module docstring, rung 3
    negative-spec):

      1. `published = _resolve_published_engine()`
      2. If `published` and `_is_engine_working_repo() is False` →
         `(published, RESOLUTION_RESOLVED_ENGINE)` — a confirmed
         non-working repo, with somewhere to divert TO.
      3. Else `live = _resolve_live_working_tree()`; if `live` →
         `(live, RESOLUTION_LIVE_WORKING_TREE)` — covers working repos,
         undeterminable repos, and (today) every repo, since step 2 never
         fires while `published` is `None`.
      4. Else if `published` → `(published, RESOLUTION_RESOLVED_ENGINE)` —
         a published engine beats no engine at all.
      5. Else `(None, RESOLUTION_UNRESOLVED)`.

    Zero-spawn, fail-open, never raises — same contract as
    `resolve_claude_klabauter_root`, which delegates here.
    """
    published = _resolve_published_engine()

    if published and _is_engine_working_repo() is False:
        return published, RESOLUTION_RESOLVED_ENGINE

    live = _resolve_live_working_tree()
    if live:
        return live, RESOLUTION_LIVE_WORKING_TREE

    if published:
        return published, RESOLUTION_RESOLVED_ENGINE

    return None, RESOLUTION_UNRESOLVED


def resolve_claude_klabauter_root() -> str | None:
    """Resolve the engine root, fail-open (never raise).

    Thin wrapper over `resolve_claude_klabauter_root_with_class`, dropping the class —
    kept because callers predating the resolved-engine rung depend on this
    exact signature. New callers that can surface WHICH engine they executed
    should prefer the `_with_class` form.

    Rungs, in order per `resolve_claude_klabauter_root_with_class` (see that
    function's docstring for the full fail-open sequencing rationale):
      0. published-engine mirror (`_resolve_published_engine`), ONLY when
         the current session is a CONFIRMED (not undeterminable)
         non-working repo — fires once `repos.claude_klabauter` is
         registered on this machine (written at install time by the engine
         plane's own installer, `scripts/setup.py::register_claude_klabauter_root()`,
         commit `5080edc48d3f`, on a claude-klabauter checkout); on a
         machine with no such registration this rung stays inert, same as
         before.
      1. REPO_CLAUDE_KLABAUTER env, then CLAUDE_KLABAUTER_ROOT env (dir must exist)
      2. machine-local registry TOML (see `_registry_value`), key
         "repos.claude_klabauter" (dir must exist)
      3. last-resort sibling walk: a "claude-klabauter" directory next to this
         repo's root.
      4. published-engine mirror again, as a last resort ahead of totally
         unresolved, if one exists and rungs 1-3 all missed.

    Negative-spec on rung 3: this hardcodes BOTH the checkout depth
    (`parents[3]` assumes the fixed `<repo>/coordinator/hooks/scripts/`
    layout) AND the literal sibling directory name "claude-klabauter" — it
    resolves correctly on exactly one conventional checkout layout
    (`~/X/DoE-claude` + `~/X/claude-klabauter` side by side) and will silently
    miss on any other layout (different parent dir, different sibling name,
    Windows drive-letter split checkouts). It is kept ONLY so a machine
    without a registry entry doesn't regress relative to the pre-fix
    behavior — it must never be promoted above the registry rung, and a
    registry entry is the correct fix for any machine that hits it.
    """
    return resolve_claude_klabauter_root_with_class()[0]


def _resolve_live_working_tree() -> str | None:
    """Rungs 1-3 — a CHECKOUT, whose contents are whatever is in it right now.

    Was split out unchanged when a since-deleted engine-snapshot rung landed
    ahead of it, so the live-tree ladder was one named thing the
    class-reporting resolver could point at distinctly from that rung. Every
    rung here answers "where is the checkout?"; the deleted rung answered
    "which engine do I execute?" — a distinction worth keeping even with that
    rung gone, because the forthcoming published-engine-mirror rung will draw
    the same line again. Those two questions coincide only on a
    co-development machine, which is why the divergence went unnoticed for as
    long as it did.
    """
    for env in LIVE_TREE_ENV_VARS:
        v = os.environ.get(env)
        if v and Path(v).is_dir():
            return v

    try:
        reg_dir = _settings_home_registry_dir()
        v = _registry_value(reg_dir, "repos.claude_klabauter")
        if v and Path(v).is_dir():
            return v
    except Exception:
        pass

    try:
        # __file__ = <repo>/coordinator/hooks/scripts/_engine_root.py
        repo_root = Path(__file__).resolve().parents[3]
        sibling = repo_root.parent / _CLAUDE_KLABAUTER_SIBLING_DIR_NAME
        if sibling.is_dir():
            return str(sibling)
    except Exception:
        pass

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
      stderr  — the nudge text, on fire only
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

    root = resolve_claude_klabauter_root()
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
