"""
assert-plan-sizing-citation.py — CLI trampoline over the engine repo's
coordinator_core.ops.assert_plan_sizing_citation.

AC4 gate for the plan sizing-citation gate: asserts zero dangling
`sizing_object:` frontmatter citations across `docs/plans/*.md`. Reads
ONLY the parsed frontmatter mapping for each plan — never the body text
(AC6, the load-bearing negative: a plan may legitimately cite a
nonexistent sizing object in BODY prose to document that it was never
written; a text-scanning check would make that plan unwriteable). No
`--fix` mode — unlike the analogous plan-backlinks gate there is no
move-map to repoint a dangling citation against.

No shebang, matching the current `coordinator/bin/*.py` convention —
invoke via `python3 coordinator/bin/assert-plan-sizing-citation.py` on
macOS/Linux; the co-located `.cmd` twin is the Windows entrypoint.

Exit convention: this is a fail-loud GATE script (asserts zero dangling
sizing_object citations), NOT a never-block hook like coordinator-auto-push —
an engine-link failure (CLAUDE_KLABAUTER_ROOT unresolved, module not importable) exits 1
here, not 0, so the failure is visible rather than silently swallowed.

Spec backlink: pln-plan-sizing-citation-gate-scaf-45eaed § C3 / AC4 / AC6
"""


# --- routing half: this file is now a thin shim over entry_point_shim.run_gate_target ---
from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from entry_point_shim import run_gate_target  # noqa: E402

if __name__ == "__main__":
    sys.exit(run_gate_target("assert-plan-sizing-citation", sys.argv[1:]))
