"""setup-detect-test-cmd.py — CLI trampoline over claude-klabauter coordinator_core.install.detect_test_cmd.

Repo-setup-time helper: inspects common stack markers (package.json,
pyproject.toml/pytest.ini/setup.cfg, Cargo.toml) in a target repo, proposes
fast_test_cmd/full_test_cmd values, and upserts them into that repo's
coordinator.local.md frontmatter. This trampoline is a thin argv/exit-code passthrough
— full detection rules, the exit-code contract, and the negative-spec live in the
Claude-klabauter module's own docstring.
"""
# setup-detect-test-cmd — CLI trampoline over claude-klabauter
# coordinator_core.install.detect_test_cmd.
#
# Repo-setup-time helper: inspects common stack markers (package.json,
# pyproject.toml/pytest.ini/setup.cfg, Cargo.toml) in a target repo, proposes
# fast_test_cmd/full_test_cmd values, and upserts them into that repo's
# coordinator.local.md frontmatter. Full detection rules, exit-code contract,
# and negative-spec live in the claude-klabauter module's own docstring (this
# trampoline is a thin argv/exit-code passthrough).
#
# Usage:
#   setup-detect-test-cmd.py --root <repo_root> [--non-interactive [fast] [full]] [--force]
#   setup-detect-test-cmd.py <repo_root> [--non-interactive [fast] [full]] [--force]
#
# Exit codes (parity-critical — matches claude-klabauter's own docstring exactly):
#   0  — commands written successfully.
#   1  — ambiguous candidates / declined in interactive mode / write error /
#        bad CLI usage (repo_root missing/non-existent, unknown flag).
#   2  — nothing detected, OR keys already present and --force not passed.
#   3  — coordinator.local.md missing or its frontmatter is malformed.
#   4  — TRANSPORT FAILURE: CLAUDE_KLABAUTER_ROOT could not be resolved, or the claude-klabauter
#        module was not importable. Dedicated code (does NOT reuse 0-3, all
#        of which are business outcomes per the table above) so a caller can
#        distinguish "claude-klabauter engine unreachable" from "detection ran and
#        found nothing" (PORTER-BRIEF-ADDENDUM.md rule A3b). On a cold
#        machine CLAUDE_KLABAUTER_ROOT may be genuinely unresolvable — this is a known
#        systemic condition, not a bug in this trampoline; the printed
#        remediation points at the resolver chain, not a specific fix.
#
# Spec backlink: docs/plans/2026-06-23-setup-time-substrate-completeness.md § C1
# Port backlink: docs/plans/2026-07-15-bash-to-naked-python-engine-migration.md
#   (BIG_PORT Wave C, item setup-detect-test-cmd)

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
# This file lives in coordinator/lib/; the shared cc_invoke helper lives in
# coordinator/bin/lib/ (reused, not re-derived — same helper coordinator-auto-push
# and handoff-gate-aging import).
_LIB_DIR = os.path.normpath(os.path.join(_HERE, "..", "bin", "lib"))
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_main():
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.install.detect_test_cmd import main as _op_main

    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"setup-detect-test-cmd: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        print(
            "  Remediation: ensure CLAUDE_KLABAUTER_ROOT is set, or that "
            "<settings-home>/machine-local/.claude-klabauter-root points at a valid "
            "claude-klabauter checkout (see coordinator-claude-klabauter-root.sh).",
            file=sys.stderr,
        )
        sys.exit(4)
    except ImportError as exc:
        print(
            f"setup-detect-test-cmd: coordinator_core.install.detect_test_cmd not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(4)
    sys.exit(op_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
