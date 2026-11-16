#!/usr/bin/env python3
"""First 1b proof: a non-interactive Codex session, briefed as EM, fires one bounded read-only engine op.

Usage: unimatrix-codex-em-proof.py [--timeout SECONDS] [--audit PATH]   (--help prints this text)

The session runs `coordinator-invoke ping '{}'` and the harness parses the engine's JSON-RPC reply
out of the session's JSONL event stream. It writes an audit record (session id, request id, op,
outcome) and exits 0 on pass, 1 on fail, 2 on a typed refusal, 127 when codex is not on PATH.
A fail is a result: it is recorded once, never retried.
"""
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OP = "ping"
DEFAULT_TIMEOUT = 300
AUDIT_REL = Path("state/audits/2026-11/2026-11-15-1b-first-em-proof-run-8887a1.md")
SETTINGS_KEY = "COORDINATOR_SETTINGS_HOME"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class Refusal(Exception):
    """A typed refusal: a required path or key could not be resolved."""


def settings_home(env=None):
    """The settings home from COORDINATOR_SETTINGS_HOME, else the conventional default; Refusal naming the key if neither exists."""
    env = os.environ if env is None else env
    explicit = env.get(SETTINGS_KEY)
    if explicit:
        return Path(explicit)
    default = Path(env.get("CLAUDE_HOME") or Path.home()) / ".coordinator-claude-settings"
    if default.is_dir():
        return default
    raise Refusal(f"{SETTINGS_KEY} is unset and {default} does not exist")


def resolve_invoke(env=None, which=shutil.which):
    """Absolute path of coordinator-invoke under the settings home bin, else PATH; Refusal naming the key if absent."""
    home = settings_home(env)
    for name in ("coordinator-invoke", "coordinator-invoke.cmd"):
        cand = home / "bin" / name
        if cand.is_file():
            return str(cand)
    found = which("coordinator-invoke")
    if found:
        return found
    raise Refusal(f"coordinator-invoke not found under {SETTINGS_KEY}={home}/bin or on PATH")


def build_brief(invoke):
    """The EM brief: run exactly one read-only op and echo the raw reply."""
    return (
        "You are acting as the EM for a one-step proof. Run exactly this one shell command, "
        "once, from the current directory, and do nothing else (no edits, no other commands):\n\n"
        f"    \"{invoke}\" {OP} '{{}}'\n\n"
        "Then reply with the engine's JSON reply copied verbatim, and nothing else. "
        "If the command fails, reply with its raw output verbatim.\n"
    )


def codex_argv(codex):
    """Non-interactive, read-only-sandboxed session in the repo root; the brief arrives on stdin."""
    return [codex, "exec", "--json", "--sandbox", "read-only", "-C", str(REPO), "-"]


def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)


def _engine_reply(text):
    """The first JSON-RPC 2.0 envelope embedded in `text`, or None."""
    dec = json.JSONDecoder()
    for m in re.finditer(r"\{", text):
        try:
            obj, _ = dec.raw_decode(text[m.start():])
        except ValueError:
            continue
        if isinstance(obj, dict) and obj.get("jsonrpc") == "2.0" and ("result" in obj or "error" in obj):
            return obj
    return None


def parse_events(stdout):
    """(session_id, engine_reply, event_type) from codex --json JSONL; absent parts are None."""
    session, reply, etype = None, None, None
    for line in stdout.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if not isinstance(ev, dict):
            continue
        if session is None:
            session = ev.get("thread_id") or ev.get("session_id") or ev.get("conversation_id")
        if reply is None:
            for s in _strings(ev):
                reply = _engine_reply(s)
                if reply:
                    item = ev.get("item")
                    etype = item.get("type") if isinstance(item, dict) else ev.get("type")
                    break
    return session, reply, etype


def judge(returncode, stdout, timed_out=False):
    """Audit fields for one finished (or timed-out) session. Pass needs exit 0, a session id and an ok engine reply."""
    session, reply, etype = parse_events(stdout or "")
    rec = {"session_id": session, "request_id": reply.get("id") if reply else None, "op": OP,
           "reply_event": etype, "codex_exit": returncode, "reason": None}
    if timed_out:
        rec["reason"] = "wall timeout"
    elif returncode != 0:
        rec["reason"] = f"codex exited {returncode}"
    elif not session:
        rec["reason"] = "no session id in event stream"
    elif reply is None:
        rec["reason"] = "no engine reply in event stream"
    elif etype != "command_execution":
        rec["reason"] = "engine reply not from a command execution event"
    elif "error" in reply or not (isinstance(reply.get("result"), dict) and reply["result"].get("ok")):
        rec["reason"] = "engine reply is not ok"
    rec["outcome"] = "fail" if rec["reason"] else "pass"
    return rec


def run_session(argv, brief, timeout, run=subprocess.run):
    """Run codex once; returns (returncode, stdout, timed_out). Never retried."""
    try:
        done = run(argv, input=brief, capture_output=True, text=True, timeout=timeout,
                   creationflags=_NO_WINDOW)
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        return -1, out, True
    return done.returncode, done.stdout, False


def write_audit(path, rec):
    """Write the audit record as markdown with frontmatter; returns the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = ["---", "title: 1b first EM proof run (Codex as EM)", f"recorded_at: {stamp}",
             f"outcome: {rec['outcome']}"]
    for key in ("session_id", "request_id", "op", "reply_event", "codex_exit", "reason"):
        lines.append(f"{key}: {json.dumps(rec[key])}")
    lines += ["---", "", f"# 1b first EM proof run: {rec['outcome']}", "",
              f"Codex session {rec['session_id']} ran `coordinator-invoke {rec['op']}`; "
              f"engine request id {rec['request_id']}; outcome {rec['outcome']}"
              + (f" ({rec['reason']})." if rec["reason"] else "."), ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main(argv=None, run=subprocess.run, which=shutil.which, env=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args in (["--help"], ["-h"]):
        print(__doc__)
        return 0
    timeout, audit = DEFAULT_TIMEOUT, REPO / AUDIT_REL
    try:
        while args:
            flag = args.pop(0)
            if flag == "--timeout":
                timeout = float(args.pop(0))
            elif flag == "--audit":
                audit = Path(args.pop(0))
            else:
                raise ValueError(flag)
    except (ValueError, IndexError) as exc:
        print(f"unimatrix-codex-em-proof: bad arguments ({exc})", file=sys.stderr)
        return 2
    codex = which("codex")
    if not codex:
        print("unimatrix-codex-em-proof: codex is not on PATH", file=sys.stderr)
        return 127
    try:
        invoke = resolve_invoke(env, which)
    except Refusal as exc:
        print(f"unimatrix-codex-em-proof: refused: {exc}", file=sys.stderr)
        return 2
    code, out, timed_out = run_session(codex_argv(codex), build_brief(invoke), timeout, run)
    rec = judge(code, out, timed_out)
    write_audit(audit, rec)
    print(f"unimatrix-codex-em-proof: {rec['outcome']} session={rec['session_id']} "
          f"request_id={rec['request_id']} audit={audit}")
    return 0 if rec["outcome"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
