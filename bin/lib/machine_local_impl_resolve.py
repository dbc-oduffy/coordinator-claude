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

One deliberate exception: `gen-claude-klabauter-root-pointer.py` inlines this same
ladder rather than importing this module, for bootstrap-time
standalone-invocability (see that file's own docstring) — keep both in sync
by hand when this module's precedence rule changes (review: code-reviewer
F5/F6).

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

Spec backlink: claude-klabauter state/audits/2026-07-25-claude-bin-mirror-read-
  rungs.md (work-list); DoE-claude state/audits/2026-07-24-claude-bin-compat-
  mirror-binding-audit.md (VERDICT: HAS-BINDINGS); docs/decisions/
  DR-210-claude-klabauter-native-tooling-ownership-strangler.md Amendment 2026-07-24
  ("resolves nothing through ~/.claude/bin").
"""
from __future__ import annotations

import os


def claude_home() -> str:
    """Return the ``~/.claude`` root, honouring ``CLAUDE_HOME`` env var for
    test isolation. Byte-identical contract to every caller's own
    pre-existing ``_claude_home()``/``claude_home()`` copy."""
    override = os.environ.get("CLAUDE_HOME")
    if override:
        return override
    return os.path.join(os.path.expanduser("~"), ".claude")


def settings_home() -> str:
    """Return the coordinator settings-home root, honouring
    ``COORDINATOR_SETTINGS_HOME`` first and falling back to
    ``${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings``.

    NOTE: the fallback base is ``CLAUDE_HOME or HOME`` directly — NOT
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
    home = os.environ.get("CLAUDE_HOME") or os.path.expanduser("~")
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
