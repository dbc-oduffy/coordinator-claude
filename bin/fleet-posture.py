"""fleet-posture: sanctioned writer and reader for the fleet-scoped posture artifact.

NOT PROTECTED from agent invocation: an agent can run this through Bash. A written
artifact applies only when the grant verifier returns `granted` for its grant_id;
without that it resolves as not-applying. Do not read a successful `set` as a posture
in force; run `show` to see what a session resolves.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HOOKS_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "hooks" / "scripts"


def _load_fp():
    """Import `_fleet_posture` on demand: the path mutation must not run at import."""
    if str(_HOOKS_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_HOOKS_SCRIPTS_DIR))
    import _fleet_posture  # type: ignore

    return _fleet_posture


def _parse_args(argv: list[str]) -> argparse.Namespace:
    fp = _load_fp()
    ap = argparse.ArgumentParser(prog="fleet-posture", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("set", help="write the artifact atomically")
    s.add_argument("--posture", required=True, choices=sorted(fp.POSTURES))
    s.add_argument("--scope", action="append", required=True,
                   help="repo-root basename (repeatable) or 'all-on-host'")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--expires-in-minutes", type=float)
    g.add_argument("--expires-at", help="absolute tz-aware ISO-8601 UTC timestamp")
    s.add_argument("--grant-id", required=True)
    s.add_argument("--channel-holder")
    sh = sub.add_parser("show", help="print what a session resolves")
    sh.add_argument("--session-id")
    sh.add_argument("--cwd")
    sub.add_parser("clear", help="remove the artifact")
    sub.add_parser("revoke", help="write the tombstone for the artifact's grant")
    return ap.parse_args(argv)


def main(argv: list[str]) -> int:
    fp = _load_fp()
    args = _parse_args(argv)
    if args.cmd == "set":
        if args.expires_at:
            expiry = fp._parse_utc(args.expires_at)
            if expiry is None:
                print("fleet-posture: --expires-at must be tz-aware ISO-8601", file=sys.stderr)
                return 2
        else:
            expiry = datetime.now(timezone.utc) + timedelta(minutes=args.expires_in_minutes)
        scope = fp.ALL_ON_HOST if args.scope == [fp.ALL_ON_HOST] else args.scope
        try:
            path = fp.write_posture(args.posture, scope, expiry, args.grant_id, args.channel_holder)
        except ValueError as exc:
            print("fleet-posture: %s" % exc, file=sys.stderr)
            return 2
        print("wrote %s (applies only once the grant verifier returns granted)" % path)
        return 0
    if args.cmd == "show":
        res = fp.resolve_posture(args.session_id, args.cwd)
        out = {
            "applies": res.applies, "posture": res.posture, "reason": res.reason,
            "grant_verdict": res.grant_verdict,
            "human_channel": fp.human_channel(args.session_id, args.cwd),
            "ask_route": fp.ask_route(args.session_id, args.cwd),
        }
        print(json.dumps(out, indent=2))
        return 0
    if args.cmd == "clear":
        print("cleared" if fp.clear_posture() else "no artifact")
        return 0
    tomb = fp.revoke_posture_grant()
    if tomb is None:
        print("fleet-posture: no readable artifact naming a grant", file=sys.stderr)
        return 1
    print("revoked via %s" % tomb)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
