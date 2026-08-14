# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
bin/render-template.py — CLI trampoline over claude-klabauter coordinator_core.ops.render_template.

Narrow Mustache-style template renderer: substitutes literal {{KEY}} tokens
in a template file with caller-supplied KEY=VALUE pairs. Fails loudly on any
unsubstituted {{KEY}} remaining after render; rejects keys with whitespace
inside braces by treating them as unsubstituted.

Spec backlink: docs/plans/2026-05-19-coordinator-installer-redesign-implementation.md § C1 (D3.b)
               docs/plans/2026-06-26-coordinator-install-update-friction-fix-slate.md § C-R3a

Usage:
  bin/render-template.py <template-path> [-o <output-path>] [KEY=VALUE]...

Arguments:
  <template-path>   Path to the template file containing {{KEY}} tokens.
  -o <output-path>  Optional. Write rendered output to <output-path>
                    atomically (render to tempfile, then replace).
                    Without -o, rendered output goes to stdout.
  KEY=VALUE         Zero or more substitution pairs. KEY must be a
                    bare identifier (no whitespace). VALUE may be any
                    string; it is treated as a literal replacement.

Exit codes:
  0  All {{KEY}} tokens were substituted; output written successfully.
  1  One or more {{KEY}} tokens remain unsubstituted after render, OR
     template file is not readable, OR output path is not writable, OR
     argument parsing failed, OR the claude-klabauter link itself failed (fail-loud —
     this is a config-writer/installer-path tool, never silently skip).

Error output:
  Unsubstituted keys → stderr:
    render-template: unsubstituted keys: KEY1, KEY2 in <template-path>

Port source: coordinator/bin/render-template.py (this file, pre-port bash body; see git log)
Ported logic: ../claude-klabauter coordinator_core/ops/render_template.py
              (co-located test: coordinator_core/ops/test_render_template.py)
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_runner():
    """In-process import, not an RPC invoke — this is a plain local file
    mutation, same rationale as edit-live-hook.py's own trampoline.

    DR-276: the op is run through `coordinator_core.cli_entry.run_op_main`
    rather than by calling its `main` directly, so the paths it declares
    become a session scope-touch claim. Without that, everything this CLI
    writes is an orphan at the `scoped_git_commit` sink.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(f"render-template: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except ImportError as exc:
        print(f"render-template: coordinator_core.cli_entry not importable: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        code = run_op_main("coordinator_core.ops.render_template", sys.argv[1:])
    except ImportError as exc:
        print(f"render-template: coordinator_core.ops.render_template not importable: {exc}", file=sys.stderr)
        sys.exit(1)

    sys.exit(code)


if __name__ == "__main__":
    main()
