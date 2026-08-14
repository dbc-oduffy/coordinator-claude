"""detect-onboarding-offer.py — CLI trampoline over claude-klabauter coordinator_core.ops.detect_onboarding_offer.

Session-preflight onboarding currency detector for /workday-start Step 1.10: checks
whether the cwd repo needs /repo-setup (unonboarded, or onboarded-but-stale against the
current coordinator-schema-version) and emits a single offer line on stdout, or nothing
when silent. This file resolves CLAUDE_KLABAUTER_ROOT, tells the claude-klabauter engine module where this
file lives on disk (the plugin_root default the engine cannot derive itself), and
forwards argv/exit code — the detection logic itself lives entirely in
coordinator_core/ops/detect_onboarding_offer.py.
"""
from __future__ import annotations
# lib/detect-onboarding-offer.py — CLI trampoline over claude-klabauter
# coordinator_core.ops.detect_onboarding_offer.
#
# Session-preflight onboarding currency detector: detects whether the cwd repo
# needs /repo-setup (unonboarded, or onboarded-but-stale against the current
# coordinator-schema-version) and emits a single offer line, or nothing if
# silent. Consumed by /workday-start Step 1.10 at session-preflight cadence.
#
# The detection logic (gitignore-based distribution-repo classification,
# dismissal-sentinel check, unonboarded/stale/current classification via the
# currency probe) is fully ported to
# coordinator_core/ops/detect_onboarding_offer.py — this file's only remaining
# job is: resolve CLAUDE_KLABAUTER_ROOT, tell the engine module where THIS file lives on
# disk (a DoE-side/contract-only fact the engine cannot derive itself — used to
# default plugin_root when neither a CLI flag nor an env var supplies one), and
# forward argv/exit code.
#
# Usage:
#   detect-onboarding-offer.py [--repo <path>] [--plugin-root <path>]
#   Env overrides (equivalent to the flags above; flags win if both given):
#     DETECT_ONBOARDING_REPO_ROOT    — repo to check (default: git root of cwd)
#     DETECT_ONBOARDING_PLUGIN_ROOT  — coordinator plugin root (default: this
#                                       file's own plugin root, i.e. the parent
#                                       of the `lib/` dir this file lives in)
#
# Output (stdout): offer line when action warranted; nothing when silent.
# Callers MUST NOT infer meaning from exit code — check stdout content.
#
# Exit codes: 0 — always. This is a best-effort/advisory probe (never blocks a
# caller) — mirrors coordinator-auto-push's posture. A claude-klabauter-link failure
# (CLAUDE_KLABAUTER_ROOT unresolvable / module not importable) is a loud stderr note, not
# a nonzero exit or a swallowed failure — same transport-failure-degrades-to-0
# posture as coordinator-auto-push / handoff-gate-aging (best-effort class per
# docs/wiki § Exit-code contract).
#
# Spec backlink: docs/plans/2026-05-29-it-just-works-agentic-install-currency.md § Chunk 3
# Port backlink: docs/plans/2026-07-16-bash-clean-slate-residual-migration.md, BIG_PORT wave
#
# Negative-spec (retired bash-oracle surface — deliberately NOT reproduced here):
#   The bash oracle's SOURCE mode (`source detect-onboarding-offer.sh` then call
#   `detect_onboarding_offer` as a shell function) is dropped. Grepped every real
#   caller (commands/workday-start.md, bin/tests/test-detect-onboarding-offer.sh)
#   — both invoke this file as a subprocess, never `source`. SOURCE mode was
#   unused dead API surface, not load-bearing behavior; this is not a
#   scope-drop regression (see the claude-klabauter module's own negative-spec for the
#   fuller citation).
import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PLUGIN_ROOT = os.path.dirname(_SCRIPT_DIR)  # this file lives at <plugin_root>/lib/...
_LIB_DIR = os.path.join(_PLUGIN_ROOT, "bin", "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_main():
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.ops.detect_onboarding_offer import main as _op_main
    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(
            f"detect-onboarding-offer.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}",
            file=sys.stderr,
        )
        sys.exit(0)
    except ImportError as exc:
        print(
            f"detect-onboarding-offer.py: coordinator_core.ops.detect_onboarding_offer "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(0)
    # default_plugin_root is a DoE-side/contract-only fact (where THIS file
    # lives on disk) the engine module cannot derive itself — see module
    # docstring. Only used when neither --plugin-root nor the env var is given.
    sys.exit(op_main(sys.argv[1:], default_plugin_root=_PLUGIN_ROOT))


if __name__ == "__main__":
    main()
