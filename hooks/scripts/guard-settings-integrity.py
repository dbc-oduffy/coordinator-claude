#!/usr/bin/env python3
"""SessionStart(startup|clear|compact) naked-Python thin stub — settings.json
clobber-guard, hook-delivery-duplication detector, and hooks-kill-switch
announcer.

Replaces `guard-settings-integrity.sh` — zero Git-Bash cold-start per boot
(each bash.exe spawn costs 200-500ms on Windows; this is the whole point).

This doctrine-plane repo owns only this thin PLUMBING shim (DR-047 transport-seam carve-out): resolve
the claude-klabauter engine, hand it the config dir, relay its stdout text. Claude-klabauter owns
the guard LOGIC (`coordinator_core.ops.session.guard_settings_integrity`, direct
Python port of the bash oracle — W4a-sessionstart-recipe.md § 2.3). All three
engine functions below are imported and called IN-PROCESS — no bash, no
`python3 -m` subprocess re-spawn, no async IPC round-trip — so a whole boot
pays exactly one Python interpreter start, regardless of how many checks run.
Mirrors `preuse-write-dispatch.py`'s `_resolve_claude_klabauter_root()` shape exactly
(env -> <settings-home>/machine-local/registry.local.toml direct tomllib
read, checked before the tracked registry.toml baseline -> sibling-dir
marker).

Three checks compose into one relayed banner, in this order:
  1. `evaluate_settings_integrity` — settings.json clobber/restore (existing).
  2. `evaluate_hook_delivery_duplication` — detects both hook-delivery
     surfaces (plugin-side `hooks.json` + settings-side baked `hooks` block)
     live for the SAME scripts, meaning every one of those hooks fires
     TWICE per session (worst on Windows, where process-spawn is most
     expensive). DETECT-ONLY, never writes.
  3. `evaluate_hooks_kill_switch_announcement` — announces when hook
     generation is disabled via the `.coordinator-hooks-disabled` marker:
     since when, whether its historical disarm condition is already met,
     and — once the marker's own `Expires:` date has passed — escalates and
     demands a human re-confirm. Never writes to the marker.
  Order rationale: settings-integrity is the most severe (a clobbered
  settings.json silently disables every plugin, so it leads); duplication is
  the next most costly (a live perf tax every boot); the kill-switch
  announcement is informational/operator-facing and closes the composed
  text. Each of the three is called and formatted independently so a
  raising check can never suppress a healthy sibling's banner (see the
  per-check try/except below) — texts are concatenated in this fixed order,
  never interleaved or reordered by which one happened to run first.

Contract (mirrors the bash hook it replaces):
  stdin   — drained and discarded (mirrors the bash hook's stdin-drain; no
            field of the SessionStart payload is needed by this guard).
  stdout  — the composed banner text (raw, becomes additionalContext), or
            NOTHING when all three checks are healthy/silent.
  exit 0  — ALWAYS. SessionStart hooks must never block session start; a
            missing/unimportable claude-klabauter engine, OR any INDIVIDUAL check
            raising, fails OPEN for that check only (silent for that check,
            exit 0) — the other checks still run and still emit. Identical
            philosophy to preuse-write-dispatch.py's fail-open, extended to
            per-check independence rather than one all-or-nothing gate.

NOTE: `CLAUDE_CONFIG_DIR` (falling back to `$HOME/.claude`) is read here (not
inside the engine call) so the stub's own env-resolution matches the bash
oracle's `${CLAUDE_CONFIG_DIR:-$HOME/.claude}` precedent — the claude-klabauter op
functions accept an explicit `config_dir` and do their OWN independent env
read when None is passed, so passing it explicitly here is redundant-but-safe
belt-and-suspenders, not a behavior fork.

Source: coordinator/hooks/scripts/guard-settings-integrity.sh
Spec: scratch/subagent-sandbox/bash-to-python-migration/W4a-sessionstart-recipe.md § 2.3
Spec (duplication + kill-switch checks): doctrine-repo dispatch
  state/subagent-share/78b683cd-1b62-4a25-904d-954cb3c69412/
  coordinatorexecutor-d531b05a.md (2026-07-29) — wires claude-klabauter
  `evaluate_hook_delivery_duplication` (82c1918c) and
  `evaluate_hooks_kill_switch_announcement` (f88b409c) into this live path.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
try:
    from _engine_root import (  # noqa: E402
        arm_lazy_ops as _arm_lazy_ops,
        resolve_claude_klabauter_root as _resolve_claude_klabauter_root,
    )
except Exception:
    # Defensive fallback -- a hook script copied/deployed WITHOUT its
    # sibling _engine_root.py (e.g. an isolated test harness, or a
    # partial deploy) must still fail-open rather than crash on import.
    def _resolve_claude_klabauter_root() -> str | None:
        return None

    def _arm_lazy_ops() -> None:
        return None


def main() -> int:
    # --- Drain stdin (mirror the bash hook's stdin-drain pattern; no field needed). ---
    try:
        sys.stdin.read()
    except Exception:
        pass

    root = _resolve_claude_klabauter_root()
    if not root:
        return 0  # fail-open — claude-klabauter unresolvable on this machine

    if root not in sys.path:
        sys.path.insert(0, root)

    # This stub calls three engine functions by direct import and never
    # dispatches an op by name, so the ~80-module eager op-registry population
    # `import coordinator_core.ops` triggers is pure dead weight here (~78ms of
    # this hook's ~118ms). Must precede the first coordinator_core import.
    _arm_lazy_ops()

    try:
        from coordinator_core.ops.session.guard_settings_integrity import (
            evaluate_settings_integrity,
            evaluate_hook_delivery_duplication,
            evaluate_hooks_kill_switch_announcement,
        )
    except Exception:
        return 0  # engine unimportable -> fail-open (never block SessionStart)

    # Path.home() (not os.path.expanduser) fails loud -- RuntimeError, not a
    # silent literal "~" -- when every home rung (USERPROFILE, HOME) is
    # unset. Caught here and degraded to the same fail-open 0 this hook
    # already returns for an unimportable engine, matching the never-block-
    # SessionStart posture this whole function is built around.
    try:
        home = str(Path.home())
    except RuntimeError:
        return 0  # fail-open — home unresolvable on this machine
    config_dir_raw = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(home, ".claude")
    config_dir = Path(config_dir_raw)

    # Each check is called and formatted independently -- one check raising
    # must NEVER suppress a healthy sibling's banner. Order is fixed (see
    # module docstring): settings-integrity, then delivery-duplication, then
    # kill-switch announcement.
    parts: list[str] = []

    try:
        text = evaluate_settings_integrity(config_dir)
        if text:
            parts.append(text)
    except Exception:
        pass  # fail-open for this check only -- others still run

    try:
        text = evaluate_hook_delivery_duplication(config_dir)
        if text:
            parts.append(text)
    except Exception:
        pass  # fail-open for this check only -- others still run

    try:
        text = evaluate_hooks_kill_switch_announcement(config_dir)
        if text:
            parts.append(text)
    except Exception:
        pass  # fail-open for this check only -- others still run

    if parts:
        sys.stdout.write("".join(parts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
