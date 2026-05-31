"""coordinator_whoami/session/cli.py — CLI entry point for the session adopter.

`python -m coordinator_whoami.session` prints the coordinator-session envelope
JSON to stdout. This adopter is live-only: it computes orientation health from
git + filesystem state at call time and NEVER persists to disk.

Usage:
    python -m coordinator_whoami.session [--human]

    --human    Pretty-print JSON (default: compact single-line).

Spec backlink: archive/specs/2026-05-27-whoami-session-spine-refactor.md § C2
"""
from __future__ import annotations

import argparse
import json
import sys

from coordinator_whoami.session.envelope import compose_envelope


def main(argv: list[str] | None = None) -> int:
    """Entry point for the session adopter CLI.

    Prints the envelope JSON to stdout. Returns 0 on success.
    Returns 1 on unexpected errors (probe errors are graceful, not fatal).
    """
    parser = argparse.ArgumentParser(
        prog="python -m coordinator_whoami.session",
        description="Emit the coordinator-session whoami envelope (live git+fs probe).",
    )
    parser.add_argument(
        "--human",
        action="store_true",
        default=False,
        help="Pretty-print JSON output (default: compact single-line).",
    )
    args = parser.parse_args(argv)

    try:
        envelope = compose_envelope()
    except Exception as exc:  # noqa: BLE001
        # Unexpected error — probes are expected to degrade gracefully, but wrap
        # any unforeseen top-level exception so the CLI always exits cleanly.
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1

    if args.human:
        print(json.dumps(envelope, indent=2))
    else:
        print(json.dumps(envelope))

    return 0
