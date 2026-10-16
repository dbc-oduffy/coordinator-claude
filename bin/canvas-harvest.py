"""canvas-harvest -- harvest or probe one canvas into a record directory.

Direct-import trampoline over the registered op `canvas.harvest`
(coordinator_core.ops.canvas_harvest): no IPC hop, no spawn. The handler runs inside
`recording_declared_writes` so every record file is claimed for the scoped commit.

  canvas-harvest harvest|probe --url URL --out DIR [--session-id SID] [--transcript PATH] [--reader]
  canvas-harvest reader-dispatch --url URL

`harvest --reader` needs --transcript: the named reader subagent's sidechain transcript.
`reader-dispatch` prints the one-shot reader Agent dispatch as one JSON line and writes nothing.
Success prints the record path, then one `deleted <path>` line per deleted path. A refusal
prints one stderr line `canvas-harvest: <reason>: <detail>` and nothing on stdout.

Exit status:
  0  written
  1  named refusal
  2  usage
  3  engine unresolvable or not importable
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_USAGE = 2
EXIT_TRANSPORT = 3


def _load_handler():
    import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import _resolve_engine_root

    root = _resolve_engine_root()
    if root not in sys.path:
        sys.path.insert(0, root)
    from coordinator_core.ops import canvas_harvest

    return canvas_harvest._handler


def _settle(result):
    """Run an async handler's coroutine to its result; a plain value passes through."""
    import asyncio
    import inspect

    if inspect.iscoroutine(result):
        return asyncio.run(result)
    return result


def _one_line(text) -> str:
    return " ".join(str(text or "").split())


def main(argv: list[str], op=None) -> int:
    ap = argparse.ArgumentParser(prog="canvas-harvest")
    ap.add_argument("mode", choices=("harvest", "probe", "reader-dispatch"))
    ap.add_argument("--url", required=True)
    ap.add_argument("--out")
    ap.add_argument("--session-id", dest="session_id")
    ap.add_argument("--transcript")
    ap.add_argument("--reader", action="store_true")
    try:
        args = ap.parse_args(argv)
        if args.mode != "reader-dispatch" and not args.out:
            ap.error("--out is required for harvest and probe")
    except SystemExit as exc:
        return EXIT_USAGE if exc.code else EXIT_OK

    if op is None:
        try:
            op = _load_handler()
        except (RuntimeError, ImportError) as exc:
            print(f"canvas-harvest: engine unavailable: {_one_line(exc)}", file=sys.stderr)
            return EXIT_TRANSPORT

    params: dict = {"mode": args.mode, "url": args.url}
    if args.out:
        params["out"] = args.out
    if args.reader:
        params["reader"] = True
    if args.session_id:
        params["session_id"] = args.session_id
    if args.transcript:
        params["transcript"] = args.transcript

    cwd = Path.cwd()
    try:
        from coordinator_core.canvas_harvest import model
        from coordinator_core.cli_entry import recording_declared_writes
    except ImportError as exc:
        print(f"canvas-harvest: engine unavailable: {_one_line(exc)}", file=sys.stderr)
        return EXIT_TRANSPORT

    with recording_declared_writes(cwd=str(cwd), max_paths=model.MAX_RECORD_FILES):
        result = _settle(op(params, repo_root=cwd))

    if not result.get("ok"):
        reason = _one_line(result.get("reason")) or "refused"
        print(f"canvas-harvest: {reason}: {_one_line(result.get('detail'))}", file=sys.stderr)
        return EXIT_REFUSED

    if args.mode == "reader-dispatch":
        sys.stdout.write(json.dumps(result["dispatch"]) + "\n")
        return EXIT_OK

    wrote = result.get("wrote") or []
    record = next((p for p in wrote if Path(p).name == "harvest.json"), None)
    if record is None and wrote:
        record = wrote[0]
    lines = [str(record) if record else str(args.out)]
    lines.extend(f"deleted {p}" for p in result.get("deleted") or [])
    sys.stdout.write("\n".join(lines) + "\n")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
