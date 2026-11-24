#!/usr/bin/env python3
"""model-for-role.py -- print the model a family runs for a role.

Usage: model-for-role.py <family> <role>

Resolves through coordinator_core.agent_pipe.model_tiers.model_for_role, so the role -> Claude
tier mapping and each family's tier slots live in one place. The root is this file's own
location, never the cwd.

Exit codes: 0 model id on stdout; 2 usage error or unknown family/role; 3 BLOCKED, the family
has no verified model in the tier slot the role needs (stderr names family, role and tier; no
other tier is substituted).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] in ("-h", "--help"):
        print("usage: model-for-role <family> <role>", file=sys.stderr)
        return 2
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from coordinator_core.agent_pipe.model_tiers import ModelSlotBlocked, model_for_role

    family, role = argv
    try:
        print(model_for_role(family, role))
    except ModelSlotBlocked as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except ValueError as exc:
        print(f"model-for-role: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
