#!/usr/bin/env python3
"""Launch codex, grok or agy as an autonomous worker on its own branch.

Usage: agent-worker-launch.py <codex|grok|agy> [--session-id ID] [--run RUN] [--allow-engine-repo] [-- cli args...]
       (--help prints this text)

Order: preflight (box load + G-EM slot, see coordinator_core.agent_pipe.worker_mode), refuse a
protected current branch and a dirty working tree (the checkout is shared; switching branches under
a peer's uncommitted work is the collision a quiet box rules out), check out the worker branch
(created from HEAD when absent; never a worktree), set the worker env marker, exec the CLI with
WORKER_ARGV. Exit 2 on a refusal, 127 when the CLI is not on PATH.
The claude-klabauter engine repo is declined as a worker target unless the PM passes --allow-engine-repo.
"""
import argparse
import datetime
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_REPO_ROOT = HERE.parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

REFUSED = 2


def _git(cwd, *args):
    """(returncode, stdout) of one git call in `cwd`."""
    from coordinator_core.git.run import run_git

    done = run_git(list(args), cwd=str(cwd) if cwd is not None else None)
    return done.returncode, done.stdout.strip()


def launch(agent, extra, *, session_id=None, run=None, cwd=None, wm=None, which=shutil.which,
           execv=os.execv, git=_git, host=None, today=None, environ=None, allow_engine_repo=False,
           prepare_only=False, platform=None, native_executable=None):
    """Run the worker launch sequence; returns an exit code on refusal, else does not return.

    A claude-klabauter engine checkout is declined by default (preflight); `allow_engine_repo` is the PM's explicit override.
    """
    if wm is None:
        from coordinator_core.agent_pipe import worker_mode as wm
    cwd = str(cwd or os.getcwd())
    platform = sys.platform if platform is None else platform
    if platform == "win32" and not prepare_only:
        print(f"agent-worker-launch: Windows interactive launch must run in the current PowerShell process. "
              f"Run {Path(__file__).with_suffix('.ps1')} {agent}", file=sys.stderr)
        return REFUSED
    environ = os.environ if environ is None else environ
    cli = native_executable or which(agent + ".exe" if platform == "win32" else agent)
    if not cli:
        print(f"agent-worker-launch: {agent} is not on PATH", file=sys.stderr)
        return 127
    if platform == "win32" and not cli.lower().endswith(".exe"):
        print("agent-worker-launch: Windows requires the native CLI .exe, not a .cmd/.bat shim; "
              "pass --native-executable with its installed path", file=sys.stderr)
        return REFUSED
    verdict = wm.preflight(agent, session_id=session_id, run=run,
                           start_dir=None if allow_engine_repo else cwd)
    if not verdict.ok:
        print(f"agent-worker-launch: refused: {verdict.reason}", file=sys.stderr)
        return REFUSED
    rc, current = git(cwd, "rev-parse", "--abbrev-ref", "HEAD")
    if rc != 0 or not current or current == "HEAD":
        print("agent-worker-launch: refused: not on a named branch of a git checkout", file=sys.stderr)
        return REFUSED
    if wm.is_protected_branch(current):
        print(f"agent-worker-launch: refused: on protected branch {current}", file=sys.stderr)
        return REFUSED
    rc, dirty = git(cwd, "status", "--porcelain")
    if rc != 0 or dirty:
        print("agent-worker-launch: refused: working tree is dirty (shared checkout); "
              "commit or clear it first", file=sys.stderr)
        return REFUSED
    branch = wm.worker_branch(agent, host or socket.gethostname(),
                              today or datetime.date.today().isoformat())
    if wm.is_protected_branch(branch):
        print(f"agent-worker-launch: refused: worker branch {branch} is protected", file=sys.stderr)
        return REFUSED
    if current != branch:
        exists = git(cwd, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}")[0] == 0
        rc, _ = git(cwd, "checkout", branch) if exists else git(cwd, "checkout", "-b", branch)
        if rc != 0:
            print(f"agent-worker-launch: refused: cannot check out {branch}", file=sys.stderr)
            return REFUSED
    cmd = [cli, *wm.WORKER_ARGV[agent], *extra]
    if prepare_only:
        print(json.dumps({"argv": cmd, "cwd": cwd, "branch": branch,
                          "environment": {wm.WORKER_ENV: agent}}))
        return 0
    environ[wm.WORKER_ENV] = agent
    execv(cmd[0], cmd)
    return 0


def main(argv=None, **kw):
    args = list(sys.argv[1:] if argv is None else argv)
    if args in ([], ["--help"], ["-h"]):
        print(__doc__)
        return 0 if args else REFUSED
    if "--" in args:
        i = args.index("--")
        args, extra = args[:i], args[i + 1:]
    else:
        extra = []
    ap = argparse.ArgumentParser(prog="agent-worker-launch", add_help=False)
    ap.add_argument("agent", choices=("codex", "grok", "agy"))
    ap.add_argument("--session-id")
    ap.add_argument("--run")
    ap.add_argument("--allow-engine-repo", action="store_true")
    ap.add_argument("--prepare-only", action="store_true")
    ap.add_argument("--native-executable")
    ns = ap.parse_args(args)
    return launch(ns.agent, extra, session_id=ns.session_id, run=ns.run,
                  allow_engine_repo=ns.allow_engine_repo, prepare_only=ns.prepare_only,
                  native_executable=ns.native_executable, **kw)


if __name__ == "__main__":
    sys.exit(main())
