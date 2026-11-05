"""Send a message to another agent through the unimatrix peer router.

For Codex and agy peers: an agent's message in is answered with this command out, addressed to
the sender, never with plain text to the human at the keyboard.

    unimatrix-send.py --to coordinator-content-repo-ea 'Reviewed the plan: two issues, ...'
    unimatrix-send.py --list

The sender is identified from the shell this runs in: CODEX_THREAD_ID (Codex) or
ANTIGRAVITY_CONVERSATION_ID (agy) names the session, and the router maps it to that peer's
name. --as overrides it. Reads no token and puts no credential in argv.
"""
import argparse
import importlib.util
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _router():
    spec = importlib.util.spec_from_file_location("unimatrix_peer_router", HERE / "unimatrix-peer-router.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def own_target(env=os.environ):
    return env.get("CODEX_THREAD_ID") or env.get("ANTIGRAVITY_CONVERSATION_ID") or ""


def main(argv=None):
    p = argparse.ArgumentParser(prog="unimatrix-send.py", description=__doc__.split("\n\n")[0])
    p.add_argument("--to", help="name of the agent to message (see --list)")
    p.add_argument("--list", action="store_true", help="list the agents you can message")
    p.add_argument("--as", dest="as_name", default=os.environ.get("UNIMATRIX_PEER_NAME", ""))
    p.add_argument("--endpoint-dir", default=None)
    p.add_argument("text", nargs="*")
    a = p.parse_args(argv)
    r = _router()
    ctl = r.endpoint_path(r.ROUTER_ENDPOINT_SEED, a.endpoint_dir)
    if a.list:
        req = {"op": "list"}
    elif a.to and a.text:
        req = {"op": "send", "to": a.to, "text": " ".join(a.text),
               "as_target": own_target(), "as": a.as_name or "cli"}
    else:
        p.error("give --to NAME and the message text, or --list")
    try:
        resp = r.request_line(ctl, req)
    except OSError as e:
        print(f"unimatrix router not reachable: {e}", file=sys.stderr)
        return 1
    if not resp.get("ok"):
        print(resp.get("error", "failed"), file=sys.stderr)
        if resp.get("peers"):
            print("agents: " + ", ".join(resp["peers"]), file=sys.stderr)
        return 1
    if a.list:
        ready = resp.get("ready", {})
        rows = [f"{n}\t{'ready' if ready.get(n, True) else 'not-ready (no leg)'}" for n in sorted(resp.get("peers", []))]
        rows += sorted(set(resp.get("sessions", [])) - set(resp.get("peers", [])))
        print("\n".join(rows))
    elif resp.get("reply"):
        print(resp["reply"])
    else:
        print(f"sent to {a.to}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
