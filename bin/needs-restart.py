"""needs-restart -- print exactly one verdict: `none`, `/reload-plugins`, or `restart`.

Diffs the current load-time surfaces against this session's SessionStart snapshot.
Session id: `--session-id`, else $CLAUDE_SESSION_ID / $CLAUDE_CODE_SESSION_ID, else the most
recent snapshot. Always exits 0; any failure prints `none`.
"""
import os
import sys
from pathlib import Path


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    sid = ""
    if "--session-id" in argv:
        i = argv.index("--session-id")
        sid = argv[i + 1] if i + 1 < len(argv) else ""
    sid = sid or os.environ.get("CLAUDE_SESSION_ID") or os.environ.get("CLAUDE_CODE_SESSION_ID") or ""
    out = "none"
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
        import session_surface_snapshot as s
        out = s.verdict(sid)
    except Exception as exc:
        # stdout vocabulary is closed (none | /reload-plugins | restart): fail open, but say why.
        print(f"needs-restart: probe failed ({type(exc).__name__}: {exc}); reporting none", file=sys.stderr)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
