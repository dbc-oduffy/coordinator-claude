from __future__ import annotations
"""
seed-skill-overrides.py — CLI trampoline over claude-klabauter
coordinator_core.ops.seed_skill_overrides.

Renamed off the `.sh` suffix (POSIX-exec drain, 2026-08-14): the stated reason
for keeping it — the install-health-run.py orchestrator's
`bin/install-health/*.sh` glob discovering this drop-in — is stale.
`coordinator_core/ops/install_health_run.py`'s `_NATIVE_LEGS` registry calls
`seed_skill_overrides.main()` directly in-process and explicitly excludes this
basename from the residual glob via `_decoupled_basenames`; this trampoline
file is not invoked by anything today.

install-health drop-in: seed bundled-skill skillOverrides. The coordinator
ships bundled skills (e.g. /plan, /review) whose command names must be
registered in Claude Code's settings.json as skillOverrides so the harness
can route them. Registering manually is error-prone; this drop-in ensures the
seed is applied idempotently on every install/re-install via
install-health-run.py.

Deep-research override: Post-merge (coordinator consolidation Wave C4),
deep-research is ALWAYS bundled inside the coordinator plugin — the
"deep-research": "off" skillOverride is unconditionally seeded to suppress
the Claude Code built-in /deep-research skill in favour of
/coordinator:research.

CHECK_ONLY mode: when the CHECK_ONLY environment variable is non-empty
(exported by coordinator:install --check-only at Step 1b), passes
--check-only to the DoE-resident bin/seed-skill-overrides.py helper so no
writes are performed — only a delta report is printed.

The actual settings.json merge logic lives in bin/seed-skill-overrides.py
(DoE-resident, NOT ported — this trampoline only replaces the bash
trust-guard/arg-building/subprocess-invoke shell, not the helper itself).

Exit codes:
  0 — helper ran successfully, OR the helper script was not found (degrades
      gracefully — does not fail the whole install-health orchestrator)
  1 — the resolved plugin root failed the trusted-root-guard check, OR
      engine-root resolution / the claude-klabauter module import itself failed
  N — helper's own exit code on failure

Fail-loud convention: matches coordinator/bin/generate-repomap.py — the
untrusted-root and claude-klabauter-link-failure branches exit 1 (gate/config-writer
shape), while the missing-helper branch is the ONE deliberate exit-0
degrade, preserved verbatim from the original bash body.

Spec backlink: docs/plans/2026-06-27-ccos-1-dual-context-validator.md
    (seed-skill-overrides chunk); install-health drop-in plan (2026-06-27);
    contract pinned to seed-skill-overrides.py helper interface.
Port source: coordinator/bin/install-health/seed-skill-overrides.sh (this
    file, retired bash body on this cutover; see git log for the prior
    74-line implementation)
"""

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _import_main():
    """Resolve the engine root, put it on sys.path, and import the ported entrypoint.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it -- this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.ops.seed_skill_overrides import main as _op_main

    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"seed-skill-overrides.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except ImportError as exc:
        print(
            f"seed-skill-overrides.py: coordinator_core.ops.seed_skill_overrides not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    # plugin_root mirrors the original .sh's own resolution:
    # ${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)} —
    # env override first, else this file's own grandparent directory
    # (coordinator/bin/install-health/seed-skill-overrides.sh -> coordinator/).
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    # site mirrors the original .sh's own $0 in its ERROR line — whatever
    # invocation-time path/argv[0] the caller used, not a fixed basename.
    sys.exit(op_main(sys.argv[1:], plugin_root=plugin_root, site=sys.argv[0]))


if __name__ == "__main__":
    main()
