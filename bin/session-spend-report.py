"""Print JSON spend report for one session transcript: EM share, product-edit share, strict-dispatch mode.

Usage: session-spend-report.py <session>.jsonl   (subagents read from <session>/subagents/)
Read-only. Exit 0 with JSON on stdout; exit 2 when the transcript is missing.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if argv[1:2] in (["--help"], ["-h"]):
        print(__doc__)
        return 0
    # Import-time inert: the lib dir joins sys.path only when the CLI actually runs.
    here = Path(__file__).resolve().parent
    sys.path.insert(0, str(here / "lib"))
    import session_spend

    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    transcript = Path(argv[1])
    if not transcript.is_file():
        print(f"transcript not found: {transcript}", file=sys.stderr)
        return 2
    root, provenance = None, None
    try:
        import cc_invoke

        root = cc_invoke.resolve_engine_root(__file__)
        provenance = list(cc_invoke.provenance_against(root=root))
    except Exception:  # an unresolved engine yields mode "unknown", not a failed report
        pass
    print(json.dumps(session_spend.build_report(transcript, root, provenance), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
