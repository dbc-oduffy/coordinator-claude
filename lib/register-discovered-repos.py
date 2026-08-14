"""
register-discovered-repos.py — CLI trampoline over claude-klabauter
coordinator_core.ops.register_discovered_repos.

Finish-strangler port (bash→pure-Python clean-slate migration): the bash
implementation (F16 fix — bridges tier-gated discovery output into the
machine-local `repos.*` registry) has been fully ported to
coordinator_core/ops/register_discovered_repos.py in the claude-klabauter sibling repo. This
file is now a thin DoE-side (contract) trampoline over that claude-klabauter (engine) module,
per DR-047 (DoE owns contract/generator, claude-klabauter owns engine).

De-bash rename (2026-07-21, chunk I-a): this trampoline itself started life as
a `.sh`-suffixed pure-Python file (a bash-invocation-tax artifact, not genuine
bash) and has been renamed to its natural `.py` extension; a co-located
`.cmd` launcher (`register-discovered-repos.cmd`, regenerated via
`coordinator/bin/gen-launcher-shim.py`) still carries Windows invocation.

Never-block contract (preserved from the bash oracle): almost every failure mode is
a silent skip that exits 0 — this bridge is advisory best-effort registration
during install, never a gate. If the claude-klabauter link itself cannot be resolved
(CLAUDE_KLABAUTER_ROOT unresolvable, module not importable), this trampoline also exits 0
rather than blocking install — matching the oracle's "skip with a stderr note"
shape for every other failure mode it already handles.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin", "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_main():
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.ops.register_discovered_repos import main as _op_main
    return _op_main


def main() -> None:
    self_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"register-discovered-repos.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(0)
    except ImportError as exc:
        print(
            f"register-discovered-repos.py: coordinator_core.ops.register_discovered_repos "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(0)
    sys.exit(op_main(sys.argv[1:], self_dir=self_dir))


if __name__ == "__main__":
    main()
