"""discover-working-repos.py — CLI trampoline over claude-klabauter coordinator_core.ops.discover_working_repos.

Three-tier working-repo discovery for /setup Phase 2 Step 4: Tier A (~/.claude/projects/
activity record), Tier A.5 (machine-local registry repos.* enumeration), Tier B (common
dev-folder layouts). Prints discovered repo paths to stdout, one per line; empty stdout
means no repos discovered and the caller falls through to Tier C (an interactive operator
prompt, not implemented here). This file is a thin DoE-side (contract) trampoline per
DR-047 — the discovery logic itself is ported to coordinator_core/ops/discover_working_repos.py.
"""
# Review: code-reviewer -- Finding 2 (2026-07-17 BIG_PORT Wave C sidecar): the
# live caller is coordinator_core.install.first_run._seed_machine_local_registry
# (reached via the `coordinator/scripts/first-run` trampoline), not the retired
# bash oracle this comment used to cite.
# Both `coordinator_core.install.first_run._seed_machine_local_registry` and
# `coordinator/commands/install.md` (Step 4 — Discover working repos) invoke
# this file as `"$PYTHON_BIN" "${PYTHON_ARGS[@]}" ".../lib/discover-working-repos.py"`
# (per `lib/resolve-python.sh`). `coordinator/lib/register-discovered-repos.py`'s
# sibling caller (`coordinator/scripts/first-run`) invokes this file
# directly (no interpreter prefix, relies on the +x bit + shebang).
#
# discover-working-repos.py — CLI trampoline over claude-klabauter
# coordinator_core.ops.discover_working_repos.
#
# Finish-strangler port (bash->pure-Python clean-slate migration): the bash
# implementation (three-tier working-repo discovery for /setup Phase 2 Step 4 —
# Tier A: ~/.claude/projects/ activity record; Tier A.5: machine-local registry
# repos.* enumeration; Tier B: common dev-folder layouts) has been fully ported
# to coordinator_core/ops/discover_working_repos.py in the claude-klabauter sibling repo.
# This file is now a thin DoE-side (contract) trampoline over that claude-klabauter
# (engine) module, per DR-047 (DoE owns contract/generator, claude-klabauter owns engine).
#
# Contract preserved from the bash oracle: prints discovered repo paths to
# stdout, one per line; empty stdout means no repos discovered (caller falls
# through to Tier C — an interactive operator prompt, NOT implemented here).
# Stops at first non-empty tier (A takes priority over B); Tier A.5 always runs
# alongside whichever of A/B fires.
#
# Never-block contract (preserved from the bash oracle): this script ALWAYS
# exits 0 — there is no failure signal to distinguish via exit code, on either
# side of the claude-klabauter link. If the claude-klabauter link itself cannot be resolved
# (CLAUDE_KLABAUTER_ROOT unresolvable, module not importable), this trampoline ALSO
# exits 0 (loud on stderr) rather than blocking `/setup` — matching the
# oracle's "advisory, never a gate" posture (transport-failure disposition per
# PORTER-BRIEF-ADDENDUM.md § 3b: best-effort/advisory scripts degrade to exit 0).
from __future__ import annotations
import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin", "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_main():
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.ops.discover_working_repos import main as _op_main
    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"discover-working-repos.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(0)
    except ImportError as exc:
        print(
            f"discover-working-repos.py: coordinator_core.ops.discover_working_repos "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(0)
    sys.exit(op_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
