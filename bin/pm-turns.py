"""pm-turns -- read one recorded PM turn back, byte-identical.

Direct-import trampoline over coordinator_core.ops.baton_pm_turns._pm_turns: no IPC hop, no
spawn. The log resolves under the cwd's git-common-dir, so the op is handed repo_root=cwd.

  pm-turns quote N [--session-id SID]     the stored prompt of turn N
  pm-turns referent N [--session-id SID]  the EM message turn N answered: its excerpt, else
                                          its transcript_uuid
  pm-turns window [--session-id SID]      the PM-turn window `sizing-assemble --write` would
                                          embed, as a JSON list (`[]` when none)

Output is UTF-8 on stdout with no trailing newline added, so `$(pm-turns quote 3)` and a pipe
see exactly the stored text.

Exit status:
  0  written (`window` always, `[]` when no turns)
  1  no such turn, or `referent` on a turn that recorded none (reason on stderr)
  2  usage
  3  engine unresolvable or not importable
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_ABSENT = 1
EXIT_USAGE = 2
EXIT_TRANSPORT = 3


def _load_op():
    import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import _resolve_engine_root

    root = _resolve_engine_root()
    if root not in sys.path:
        sys.path.insert(0, root)
    from coordinator_core.ops import baton_pm_turns

    return baton_pm_turns


def _emit(text: str) -> None:
    sys.stdout.buffer.write(text.encode("utf-8"))
    sys.stdout.buffer.flush()


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="pm-turns")
    sub = ap.add_subparsers(dest="verb", required=True)
    for verb in ("quote", "referent"):
        p = sub.add_parser(verb)
        p.add_argument("n", type=int, metavar="N")
        p.add_argument("--session-id", dest="session_id")
    pw = sub.add_parser("window")
    pw.add_argument("--session-id", dest="session_id")
    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        return EXIT_USAGE if exc.code else EXIT_OK

    try:
        mod = _load_op()
    except (RuntimeError, ImportError) as exc:
        print(f"pm-turns: engine unavailable: {exc}", file=sys.stderr)
        return EXIT_TRANSPORT

    if args.verb == "window":
        window = mod.recent_window(session_id=args.session_id, cwd=str(Path.cwd()))
        _emit(json.dumps(window, ensure_ascii=False))
        return EXIT_OK

    op = mod._pm_turns
    params: dict = {"turn": args.n}
    if args.session_id:
        params["session_id"] = args.session_id
    result = op(params, repo_root=Path.cwd())
    turns = result.get("turns") or []
    if not result.get("ok") or not turns:
        print(f"pm-turns: {result.get('reason') or f'no turn {args.n}'}", file=sys.stderr)
        return EXIT_ABSENT

    if args.verb == "quote":
        _emit(result["text"])
        return EXIT_OK

    referent = turns[0].get("referent")
    value = referent and (referent.get("excerpt") or referent.get("transcript_uuid"))
    if not value:
        print(f"pm-turns: turn {args.n} recorded no referent", file=sys.stderr)
        return EXIT_ABSENT
    _emit(value)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
