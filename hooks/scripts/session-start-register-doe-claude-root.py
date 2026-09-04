"""SessionStart hook — self-heals `engine.working_repos.doe_claude` in the
machine-local registry.

Purpose: DR-132
(docs/decisions/DR-132-engine-working-repos-is-its-own-namespace-not-a-repos-star-inference.md,
Consequences section) records that `engine.working_repos.*` is declared
`idempotent-regeneratable` as target state, but only `claude_klabauter` self-heals
today — the engine plane's own installer writes it via
`scripts/setup.py::register_claude_klabauter_root()`. `doe_claude` is operator-set and has
NO install-time (or session-time) self-registration, so a fresh clone, a wiped
registry, or an operator typo leaves the key silently wrong or absent, and
`_engine_root.py`'s working-repo gate (`_is_engine_working_repo()`) can never
confirm this repo as a working repo on that machine. This hook closes that gap
from THIS repo's own plane — this repo cannot wait on an engine-plane
installer change for a discriminant that governs whether THIS repo's own
sessions resolve the live engine checkout or the published engine.

Contract:
  stdin   — SessionStart JSON payload (unused — this hook needs no payload
            field; it always resolves its OWN root from `__file__`, per
            CLAUDE.md "Scripts self-resolve their own root from BASH_SOURCE,
            never cwd")
  stdout  — NOTHING (registered `async: true` in hooks.json — this hook's
            whole value is the registry side effect, not context-bound
            output; see hooks.json's own C8/boot-sweep entries for the
            identical "no context-bound stdout -> async is correct" argument
            this hook makes for itself)
  exit 0  — ALWAYS. FAIL OPEN at every step, unconditionally: a SessionStart
            hook that raises greets every session in the fleet with a stack
            trace, which is worse than one that silently no-ops. Every
            failure mode (unresolvable settings home, unreadable registry,
            missing `_machine_local.py` impl, a failed/timed-out
            `machine-local set` spawn) degrades to a silent no-op, never an
            exception, never non-zero. Mirrors
            `session-start-write-bump-anchor.py`'s shape (small idempotent
            per-session write, exhaustive matcher, fail-open) — read that
            file first if editing this one; this hook was written to mirror
            its structure, error handling, and docstring style.

Idempotence: reads the current registry value first
(`_engine_root._registry_value`, the same zero-spawn TOML reader the engine
resolution ladder itself uses) and does NOTHING — no write, no subprocess
spawn — when it already matches this repo's own root. Only a genuinely
absent or different value triggers a write.

Write path: the sanctioned CLI writer, `machine-local set
engine.working_repos.doe_claude <path>` — never a hand-edit of the registry
TOML (a concurrent session may be writing it; see
`docs/wiki/machine-local-registry.md` § "Use this instead of editing
registry files by hand"). Invoked here by shelling out to
`<settings-home>/bin/_machine_local.py` directly under `sys.executable`
(the same implementation file the `machine-local`/`machine-local.cmd`
forwarders both resolve to — see `templates/bin/machine-local`'s own
docstring), so this hook depends on neither shim existing or being
executable on the current platform. The actual write is isolated in
`_write_registry_value()`, which is a bare, patchable module-level function
so unit tests can substitute a in-memory recorder for the real subprocess
spawn — no shelling out required to unit test the decision logic above it.

Wrong-repo guard (Non-negotiable #7 in this hook's dispatch brief): this
hook must NEVER register a tree that is not genuinely this repo's own working
tree, because a false positive here would divert a *consumer* repo's own
session away from the published engine forever — the exact failure DR-132
exists to prevent. Chosen guard: presence of `.coordinator-dev-repo` at the
resolved repo root (a repo-root, not `coordinator/`-relative, sentinel; see
that file's own header for why its location is load-bearing and must never
move) AND its `slug: doe-claude` content line matches. Presence-only would
already be sufficient in practice — `.coordinator-dev-repo` is structurally
absent from every OSS/marketplace install and from every consumer repo,
since the one-way doctrine-plane->OSS percolation sweep (`coordinator/.percolate-ignore`)
never touches the repo root, only `coordinator/`'s own contents (see
CLAUDE.md "Both trees are named 'coordinator-claude'; they are NOT the same
tree" and the sentinel's own header comment) — but this hook additionally
checks the `slug:` line so that if this SAME hook script is ever percolated
into another dev-repo class in the future (unlikely today, but the sentinel
format explicitly supports a `slug:` payload for exactly this kind of
disambiguation — see `_scan_dev_repo_marker`'s rung-2 autodiscovery use of
the same field), it still only ever fires for the literal `doe-claude` slug,
not merely "some dev repo, whichever one this is."

Matcher (see hooks.json registration): mirrors
`session-start-write-bump-anchor.py`'s exhaustive
`startup|resume|clear|compact|fork` matcher — every SessionStart source the
harness emits, not just cold start. Safe to fire on all of them because this
hook is idempotent by construction (a repeat fire when the key is already
correct is a single cheap TOML read and nothing else).

Spec backlink: DR-132 Consequences section ("`doe_claude` is NOT [written by
an installer] ... its key is operator-set and does not yet self-heal").
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
try:
    from _engine_root import (  # noqa: E402
        _registry_value as _engine_registry_value,
        _settings_home,
        _settings_home_registry_dir,
    )
except Exception:
    # Defensive fallback — a hook script copied/deployed WITHOUT its sibling
    # _engine_root.py (e.g. an isolated test harness, or a partial deploy)
    # must still fail-open rather than crash on import.
    def _engine_registry_value(reg_dir, key):  # type: ignore[no-redef]
        return None

    def _settings_home():  # type: ignore[no-redef]
        return None

    def _settings_home_registry_dir():  # type: ignore[no-redef]
        return None

try:
    from _forwarder_resolve import forwarder_argv as _forwarder_argv
except Exception:
    # Review: overengineering-reviewer F3 -- see _forwarder_resolve's
    # "Import-fallback contract" docstring section for the rationale.
    def _forwarder_argv(script_path, tail=()):  # type: ignore[no-redef]
        raise OSError("forwarder resolution unavailable -- import fallback declined to guess a launch decision")


_REGISTRY_KEY = "engine.working_repos.doe_claude"
_SENTINEL_NAME = ".coordinator-dev-repo"
_EXPECTED_SLUG = "doe-claude"


def _repo_root() -> Path:
    """This repo's own root, resolved from `__file__`, never cwd.

    `__file__` = <repo>/coordinator/hooks/scripts/<this file>.py — three
    parents up reaches <repo>, the same depth `_engine_root.py`'s own rung-3
    sibling walk uses for its identical layout assumption.
    """
    return Path(__file__).resolve().parents[3]


def _is_genuine_doe_claude_repo(root: Path) -> bool:
    """Wrong-repo guard — see module docstring's "Wrong-repo guard" section
    for the full rationale. Never raises; any read failure is treated as
    "not confirmed", which is the fail-closed direction for a guard whose
    job is preventing a false-positive registration.

    Parses the sentinel line-by-line for a `slug:` key and compares the
    trimmed value for EXACT equality with `doe-claude` — mirrors
    `_scan_dev_repo_marker` in `templates/bin/_machine_local.py` (the
    canonical parser for this sentinel format). A substring/`in` check
    would also match a prefix-sharing slug such as `doe-claude-fork`,
    defeating the guard.
    """
    sentinel = root / _SENTINEL_NAME
    try:
        if not sentinel.is_file():
            return False
        text = sentinel.read_text(encoding="utf-8")
    except Exception:
        return False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("slug:"):
            slug = stripped[len("slug:"):].strip()
            return slug == _EXPECTED_SLUG
    return False


def _write_registry_value(key: str, value: str) -> None:
    """Injectable write step — the ONE function this hook's tests patch out
    rather than actually shelling out. Never raises (caller wraps it too,
    defense in depth): any resolution failure, missing impl file, spawn
    failure, or timeout is a silent no-op.

    Windows console-subprocess discipline: `sys.executable` on Windows is
    typically `python.exe`, a console-subsystem binary — CREATE_NO_WINDOW
    suppresses the focus-stealing console flash under this hook's headless
    SessionStart parent. `getattr` degrades to a harmless `0` on
    macOS/Linux, where the flag does not exist.

    Launch guard: `_forwarder_argv` decides whether `impl` needs a
    `sys.executable` prefix by inspecting the file itself (suffix plus
    native-image magic-byte probe), never by trusting the `.py` suffix in
    this call site's own path literal — a cut-over door installed at the
    same stem is a compiled native image, and handing one to the Python
    interpreter dies on the first byte with `SyntaxError: Non-UTF-8 code`.
    See `_forwarder_resolve.forwarder_argv`'s own docstring ("Ask the
    bytes").
    """
    home = _settings_home()
    if home is None:
        return
    impl = Path(home) / "bin" / "_machine_local.py"
    if not impl.is_file():
        return
    try:
        # Review: overengineering-reviewer F3 -- argv computation moved inside
        # the try so a fallback-leg OSError (see _forwarder_resolve) is
        # absorbed by the handler below rather than needing its own guard.
        argv = _forwarder_argv(impl, ["set", key, value])
        subprocess.run(
            argv,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            # Below hooks.json's 10s whole-process timeout for this hook, so
            # this in-process catch has room to fire and return before the
            # harness's hard-kill would otherwise beat it to the graceful
            # path.
            # Review: coordinator-code-reviewer (s3-selfreg-hook) — inner
            # timeout previously equaled the outer envelope (10s == 10s).
            timeout=6,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        # Review: coordinator-code-reviewer (s3-selfreg-hook) — the
        # docstring claimed "never raises" without this wrap; TimeoutExpired
        # or an OSError from the spawn previously propagated out, relying
        # solely on the caller's wrap for fail-open. Caller-side wrap is
        # kept too, making the defense-in-depth claim real.
        return


def main() -> int:
    try:
        root = _repo_root()
    except Exception:
        return 0

    try:
        if not _is_genuine_doe_claude_repo(root):
            return 0  # not confirmed as THIS repo — never register
    except Exception:
        return 0

    try:
        reg_dir = _settings_home_registry_dir()
        if reg_dir is None:
            return 0
    except Exception:
        return 0

    root_str = str(root)

    try:
        current = _engine_registry_value(reg_dir, _REGISTRY_KEY)
    except Exception:
        current = None

    if current == root_str:
        return 0  # already correct — quiet, no write, no spawn

    try:
        _write_registry_value(_REGISTRY_KEY, root_str)
    except Exception:
        # _write_registry_value already fails open internally, but this call
        # site swallows unconditionally too: a SessionStart hook erroring is
        # worse than one that silently no-ops.
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
