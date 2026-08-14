"""cli_shared.py — shared CLI/arg/IO boilerplate for DoE-resident coordinator bin/ CLIs.

Consolidation target for the ~150 LoC of near-verbatim duplication between
coordinator-queue-append and coordinator-lesson-promote (both write structured
YAML entries into claude-klabauter/DoE-routed state directories and resolve their own
from_repo identity from cwd git context). Extracts exactly four primitives:

  - machine_local_get / machine_local_repos_keys — `machine-local` CLI bridge
  - claude_klabauter_root — CLAUDE_KLABAUTER_ROOT env-or-registry resolution (AC1/AC13)
  - resolve_from_repo — the cwd git-root -> machine-local reverse-lookup ->
    doe_claude -> unregistered-repo -> "unknown-sender-em" ladder (same
    convention as cross-repo-memo._sender_em_id)
  - write_path_excl — O_CREAT|O_EXCL + retry-with-incrementing-suffix write,
    bounded and fail-loud-after-cap-exhausted (never a silent overwrite, never
    a bare first-collision FileExistsError)

DoE-resident (NOT coordinator_core-resident): this is call-site/CLI plumbing —
arg parsing support, path resolution for THIS repo's machine-local registry —
not engine-owned business logic, so it does not cross the DR-047 boundary.
Consistent with cc_invoke.py's own residency alongside this module.

Negative-spec: do NOT add schema-specific validation, op-param shaping, or
YAML-emission helpers here — those stay per-script (each CLI routes to a
different native op with a different param shape). This module is boilerplate
ONLY: CLI-name-agnostic path/registry resolution and one collision-safe writer.

Spec backlink: docs/plans/2026-07-15-bash-to-naked-python-engine-migration.md
  (T2-g2, recipe § 3 — "Consolidation — shared boilerplate module")
"""

from __future__ import annotations

import os
import subprocess
import sys

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from coordinator_registry import em_id_for_root  # noqa: E402
from machine_local_impl_resolve import (  # noqa: E402
    claude_home as _mlir_claude_home,
    machine_local_impl_path as _mlir_machine_local_impl_path,
)
from repo_identity import resolve_checked_repo_root  # noqa: E402

# ---------------------------------------------------------------------------
# Env vars — identical spelling/semantics across both current consumers.
# ---------------------------------------------------------------------------

MACHINE_LOCAL_IMPL_ENV = "MACHINE_LOCAL_IMPL"
CLAUDE_HOME_ENV = "CLAUDE_HOME"
CLAUDE_KLABAUTER_ROOT_ENV = "CLAUDE_KLABAUTER_ROOT"

# Bounded retry attempts before write_path_excl fails loud.
COLLISION_RETRY_CAP = 1000

# Windows: suppresses the console popup a subprocess.run(...) would otherwise
# trigger under the headless Claude Code Bash-tool parent. No-op (0) elsewhere.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def claude_home() -> str:
    """Return the ~/.claude root, honouring CLAUDE_HOME env var for test isolation.

    Delegates to machine_local_impl_resolve.claude_home() (settings-home-first
    resolution now lives there, shared across every former hand-roll of this
    join — see that module's docstring).
    """
    return _mlir_claude_home()


def machine_local_impl() -> str:
    """Return the path to _machine_local.py, settings-home first, honouring
    MACHINE_LOCAL_IMPL for tests.

    Delegates to machine_local_impl_resolve.machine_local_impl_path() — DR-210
    Amendment 2026-07-24 ("resolves nothing through ~/.claude/bin"): this rung
    now tries settings-home before the retired compat mirror.
    """
    return _mlir_machine_local_impl_path(MACHINE_LOCAL_IMPL_ENV)


def resolve_python() -> str:
    """Return a usable Python interpreter for subprocess calls.

    sys.executable is always valid — the interpreter running this script.
    Avoids subprocess probing that raises FileNotFoundError on Windows.
    """
    return sys.executable


def machine_local_get(key: str) -> str | None:
    """Call machine-local get <key> and return the value, or None on failure."""
    impl = machine_local_impl()
    python = resolve_python()
    try:
        result = subprocess.run(
            [python, impl, "get", key],
            capture_output=True,
            text=True,
            creationflags=_NO_WINDOW,
        )
    except OSError:
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.strip()


def machine_local_repos_keys() -> list[str]:
    """Return all repos.* keys from the machine-local registry."""
    impl = machine_local_impl()
    python = resolve_python()
    try:
        result = subprocess.run(
            [python, impl, "keys"],
            capture_output=True,
            text=True,
            creationflags=_NO_WINDOW,
        )
    except OSError:
        return []
    if result.returncode != 0:
        return []
    return [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip().startswith("repos.")
    ]


def claude_klabauter_root() -> str | None:
    """Resolve the claude-klabauter repo root, mirroring coordinator-claude-klabauter-root.sh (AC1).

    Resolution chain:
      1. CLAUDE_KLABAUTER_ROOT env var — if non-empty, trusted as-is (§4b idempotency gate).
      2. machine-local get repos.claude_klabauter — delegates to the §4c discovery ladder.
      3. Returns None when unresolvable — callers degrade gracefully (AC13).

    Negative-spec: never raises; returns None when unresolvable so callers can emit
    WARN + skip. The low-level shell primitive coordinator-claude-klabauter-root.sh hard-errors;
    this is the Python caller-layer resilience wrapper.

    Spec backlink: pln-stop-the-rot-claude-klabauter-state-home-placement-4cc787 § AC1 / AC13
    """
    override = os.environ.get(CLAUDE_KLABAUTER_ROOT_ENV, "").strip()
    if override:
        return override
    val = machine_local_get("repos.claude_klabauter")
    return val if val else None


def resolve_from_repo(root: str | None = None) -> str:
    """Identify the from_repo/EM identity for a queue/outbox entry from cwd context.

    Resolution order (same convention as cross-repo-memo._sender_em_id):
      1. cwd git-root -> reverse-lookup against machine-local repos.* table
      2. repos.doe_claude (DoE-claude repo) -> "claude-central-em"
      3. Unregistered git repo -> basename of git root + "-em"
      4. Not in a git repo -> "unknown-sender-em"
      Never uses `git remote get-url origin` — that yields a URL, not a shortname.

    Accepts a pre-resolved repo root to avoid spawning a second git-root
    resolution when the caller already holds it (coordinator-lesson-promote's
    F3 hoist). Pass None (default) to resolve internally via the checked
    resolver (`repo_identity.resolve_checked_repo_root`).

    Classification: READER (AC10). On MISMATCH — positive evidence the cwd
    names a DIFFERENT real repo than the harness anchor — warns to stderr and
    proceeds with the resolved root anyway (identity attribution, not a
    destructive action); per DR-277
    (docs/decisions/DR-277-guards-are-advisory-by-default-two-named.md).
    UNRESOLVED never refuses either, degrading to `root=None` exactly as the
    predecessor's git-failure branch did.

    Ensures repos.doe_claude is present in the paths table for the central-identity
    anchor even when machine_local_repos_keys() omits it (e.g. unregistered machine).
    """
    if root is None:
        root, verdict = resolve_checked_repo_root(explicit_root=None)
        if verdict.get("verdict") == "MISMATCH":
            print(
                verdict.get("message", "cli_shared: repo-identity MISMATCH"),
                file=sys.stderr,
            )
    keys = machine_local_repos_keys()
    paths = {k: machine_local_get(k) for k in keys}
    paths.setdefault("repos.doe_claude", machine_local_get("repos.doe_claude"))
    return em_id_for_root(root, {k: v for k, v in paths.items() if v})


def write_path_excl(out_path: str, content: str, *, caller_name: str) -> str:
    """Write content to out_path using an exclusive-create + retry-with-suffix loop.

    Replaces a plain os.replace()/open("w") silent overwrite with os.O_CREAT|O_EXCL
    so a same-key collision from a concurrent second write does NOT destroy the
    first entry. On FileExistsError, retries with an incrementing filename suffix
    inserted before the extension (<stem>-2<ext>, -3<ext>, ...) bounded to
    COLLISION_RETRY_CAP attempts, so both entries persist under distinct filenames.
    Only when the cap is exhausted does this raise — fail loud, never silently
    drop the entry.

    caller_name is interpolated into the exhausted-retry error message so an
    operator debugging a stuck write knows which CLI produced it — the one bit
    of per-caller distinction preserved by this consolidation (do NOT flatten
    to one generic string).

    Returns the actual path written (== out_path unless a collision suffix was used).

    Negative-spec: do NOT swap this for a plain os.replace()/open("w") — that
    silently clobbers a same-key concurrent write. Do NOT swap this for a bare
    fail-loud FileExistsError (the cross-repo-memo shape) either — callers of
    this helper are terminal writers with no retry path of their own, so failing
    loud on the FIRST collision would drop the entry rather than preserve it;
    retry-with-suffix is required.

    Counter-pattern (deliberate divergence): coordinator/bin/cross-repo-memo.py's
    _write_file FAILS LOUD (FileExistsError, no retry) on collision because its
    caller is interactive and retries with a new --topic.

    Spec backlink: F1/F2 legacy-fallback silent-overwrite collision guard (chunk C1).
    """
    root, ext = os.path.splitext(out_path)
    candidate = out_path
    attempt = 1
    while True:
        try:
            fd = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            attempt += 1
            if attempt > COLLISION_RETRY_CAP:
                raise FileExistsError(
                    f"{caller_name}: refusing to drop entry — exhausted "
                    f"{COLLISION_RETRY_CAP} collision-retry attempts for base path "
                    f"{out_path!r}. All candidate filenames already exist. "
                    f"Tried {out_path!r} through {root!r}-{COLLISION_RETRY_CAP}{ext!r}."
                ) from None
            candidate = f"{root}-{attempt}{ext}"
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        return candidate
