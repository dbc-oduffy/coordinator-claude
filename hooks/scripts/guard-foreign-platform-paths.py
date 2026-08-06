#!/usr/bin/env python3
"""SessionStart(startup|clear|compact) naked-Python thin stub — foreign-
platform-path guard for the live `settings.json`.

Catches the 2026-07-28 incident shape: a POSIX host's `settings.json` silently
carrying a Windows drive-letter-rooted hook-command path, or the Windows-host
reverse. Every hook whose `command` string points at a foreign drive fails
to fire, and produces NO error anywhere — the only symptom is a tool call
failing against a path that does not exist on this machine.

DoE owns only this thin PLUMBING shim (DR-047 transport-seam carve-out): resolve
the claude-klabauter engine, hand it the live settings path, relay its stdout text.
Claude-klabauter owns the guard LOGIC
(`coordinator_core.ops.session.guard_foreign_platform_paths`). Mirrors
`guard-settings-integrity.py`'s in-process-import shape exactly.

Contract:
  stdin   — drained and discarded (no field of the SessionStart payload is
            needed by this guard).
  stdout  — the guard's banner text (raw, becomes additionalContext), or
            NOTHING when clean/healthy/absent/unparsable.
  exit 0  — ALWAYS. SessionStart hooks must never block session start; a
            missing/unimportable claude-klabauter engine fails OPEN (silent, exit 0).

Residual gap (AC-3, stated plainly rather than papered over): on this repo's
actual dev topology, native `--plugin-dir` hook-delivery is dead (upstream
bug #38699), so EVERY hook — this one included — is delivered by being baked
as an absolute-path entry into `settings.json`'s OWN `hooks` block
(`docs/wiki/external-plugin-live-resolution.md § Hook-delivery`). A corruption
that damages the `hooks` block ITSELF therefore also disables this guard for
that session — the exact circularity a hook-only guard cannot solve by
construction. This is the same circularity `docs/wiki/settings-integrity-
guard.md` claims is solved by "living in the plugin, not settings.json" — that
claim is accurate for a native `--plugin-dir` install and STALE for this
machine's settings.json-baked delivery mechanism. The independent second leg
that closes this gap is a native git `pre-commit` hook
(`coordinator-precommit-foreign-platform-check`, claude-klabauter, installed via
`install_meta_repo_precommit_hook.py`'s Gate 3) — it fires via git itself, not
via any Claude Code hook, so it survives a session where every Claude Code
hook is already dead. See that script's own docstring for what it still can't
catch (a corruption that never passes through a local `git commit`).

Source: coordinator_core.ops.session.guard_foreign_platform_paths.evaluate_foreign_platform_paths
Spec backlink: state/subagent-share/32637f2b-204d-4937-89a7-c3518928e38d/coordinatorexecutor-7bb4cb37.md
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
    # sibling _engine_root.py must still fail-open rather than crash on import.
    def _resolve_claude_klabauter_root() -> str | None:
        return None

    def _arm_lazy_ops() -> None:
        return None


def main() -> int:
    # --- Drain stdin (mirror the bash-hook stdin-drain pattern). ---
    try:
        sys.stdin.read()
    except Exception:
        pass

    root = _resolve_claude_klabauter_root()
    if not root:
        return 0  # fail-open — claude-klabauter unresolvable on this machine

    if root not in sys.path:
        sys.path.insert(0, root)

    # Single direct-import engine call, no dispatch-by-name -- the ~80-module
    # eager op-registry population is dead weight here. Must precede the first
    # coordinator_core import. See _engine_root.arm_lazy_ops for the rationale.
    _arm_lazy_ops()

    try:
        from coordinator_core.ops.session.guard_foreign_platform_paths import (
            evaluate_foreign_platform_paths,
        )
    except Exception:
        return 0  # engine unimportable -> fail-open (never block SessionStart)

    # Path.home() (not os.path.expanduser) fails loud -- RuntimeError, not a
    # silent literal "~" -- when every home rung is unset. Caught here and
    # degraded to the same fail-open 0 this hook already returns for an
    # unimportable engine, matching its never-block-SessionStart posture.
    try:
        home = str(Path.home())
    except RuntimeError:
        return 0  # fail-open — home unresolvable on this machine
    config_dir_raw = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(home, ".claude")
    config_dir = Path(config_dir_raw)
    settings_path = config_dir / "settings.json"

    try:
        text = evaluate_foreign_platform_paths(settings_path, config_dir=config_dir)
    except Exception:
        return 0  # any engine failure -> fail-open (never block SessionStart)

    if text:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
