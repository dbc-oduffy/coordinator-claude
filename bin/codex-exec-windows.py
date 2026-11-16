#!/usr/bin/env python3
"""codex-exec-windows.py — run `codex exec` with a clean PATH, prompt on stdin, JSONL to a file.

Usage: codex-exec-windows.py --prompt FILE --events FILE [codex exec args ...]

Drops every PATH entry containing WindowsApps (App Execution Alias stubs shadow
the real binaries), prepends the directory of a non-WindowsApps pwsh when one is
found, feeds the prompt file on stdin to `codex exec <args>`, writes codex's
stdout to the events file byte-for-byte (codex emits utf8 JSONL), and exits with
codex's exit code. Exit 127 when no codex resolves on the cleaned PATH.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

_NO_CODEX_RC = 127


def clean_path(path_value: str) -> str:
    """Return `path_value` without any entry containing WindowsApps, plus the real pwsh dir first."""
    kept = [e for e in path_value.split(os.pathsep) if e and "windowsapps" not in e.lower()]
    cleaned = os.pathsep.join(kept)
    pwsh = shutil.which("pwsh", path=cleaned)
    if pwsh:
        pwsh_dir = str(Path(pwsh).parent)
        cleaned = os.pathsep.join([pwsh_dir, *[e for e in kept if e != pwsh_dir]])
    return cleaned


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="codex-exec-windows.py",
        description=(
            "Run `codex exec <codex args>` with WindowsApps stripped from PATH, the prompt "
            "file on stdin, and stdout JSONL written to the events file. Every argument "
            "this tool does not own is passed to `codex exec`."
        ),
        allow_abbrev=False,
    )
    p.add_argument("--prompt", required=True, help="file whose bytes are fed to codex on stdin")
    p.add_argument("--events", required=True, help="file receiving codex stdout (utf8 JSONL)")
    return p


def main(argv: list[str] | None = None) -> int:
    args, codex_args = _build_parser().parse_known_args(argv)
    if codex_args and codex_args[0] == "--":
        codex_args = codex_args[1:]

    path_value = clean_path(os.environ.get("PATH", ""))
    codex = shutil.which("codex", path=path_value)
    if not codex:
        print("codex-exec-windows.py: codex not found on PATH after WindowsApps strip", file=sys.stderr)
        return _NO_CODEX_RC

    env = dict(os.environ)
    env["PATH"] = path_value
    with open(args.prompt, "rb") as stdin_fh, open(args.events, "wb") as events_fh:
        proc = subprocess.run(
            [codex, "exec", *codex_args],
            stdin=stdin_fh,
            stdout=events_fh,
            env=env,
            shell=False,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
