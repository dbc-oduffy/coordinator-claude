#!/usr/bin/env python3
"""door-serving-census.py — durable, operator-runnable CLI trampoline over
`coordinator_core.install.door_serving_census`.

Purpose: `docs/plans/2026-08-30-twenty-one-bin-names-reach-the-door-or-are-
thoroughly-dead.md` C4's AC6 — the census must be repeatable by someone
else as a runnable command, not a shell pipeline pasted into a handoff.
This trampoline carries no logic of its own: every bucket, every
resolution rule, and every negative-spec lives in
`coordinator_core/install/door_serving_census.py`, reused unchanged here.

Naked Python, no bash — CLAUDE.md § Runtime conventions. Never spawns a
process unless invoked with `--probe NAME`, which the underlying module's
own docstring names as the one opt-in exception to "resolution, not
probing".

Usage:
    python3 door-serving-census.py [--probe NAME]
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from coordinator_core.install.door_serving_census import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
