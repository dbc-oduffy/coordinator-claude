
from __future__ import annotations

INSTALL_CLASS = True

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

GENERATES = []

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _no_console_kw() -> dict:
    """CREATE_NO_WINDOW kwargs for a captured child on Windows; empty elsewhere."""
    if os.name != "nt":
        return {}
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def _resolve_sha(source: Path, sha_arg: str | None) -> str:
    if sha_arg is not None:
        if not _SHA_RE.fullmatch(sha_arg):
            print(f"ERROR: --sha is not 40-hex: {sha_arg!r}", file=sys.stderr)
            sys.exit(1)
        return sha_arg

    if not source.is_dir():
        print(f"ERROR: --source path does not exist or is not a directory: {source}", file=sys.stderr)
        sys.exit(1)

    result = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        **_no_console_kw(),
    )
    if result.returncode != 0:
        print(
            f"ERROR: git rev-parse HEAD failed (exit {result.returncode}) in {source}\n"
            f"stderr: {result.stderr.strip()}",
            file=sys.stderr,
        )
        sys.exit(1)

    sha = result.stdout.strip()
    if not _SHA_RE.fullmatch(sha):
        print(f"ERROR: git HEAD did not produce a 40-hex SHA: {sha!r}", file=sys.stderr)
        sys.exit(1)
    return sha


PLUGIN_VERSION_FILE = "plugin-version.txt"


def read_plugin_version(source: Path) -> str | None:
    """The plugin's ``version`` from its ``plugin.json``, or None when absent or unreadable."""
    for rel in (".claude-plugin/plugin.json", "coordinator/.claude-plugin/plugin.json"):
        try:
            data = json.loads((source / rel).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        version = data.get("version") if isinstance(data, dict) else None
        if isinstance(version, str) and version.strip():
            return version.strip()
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write a 40-hex source-HEAD SHA into <path>/version.txt.",
    )
    parser.add_argument("--path", required=True, help="Target directory; version.txt is written at <path>/version.txt.")
    parser.add_argument("--source", default=".", help="Git repo root to read HEAD from (default: cwd).")
    parser.add_argument("--sha", default=None, help="Explicit 40-hex SHA; bypasses git rev-parse.")
    args = parser.parse_args(argv)

    target = Path(args.path)
    if not target.is_dir():
        print(f"ERROR: --path does not exist or is not a directory: {target}", file=sys.stderr)
        return 1

    sha = _resolve_sha(Path(args.source), args.sha)

    sentinel = target / "version.txt"
    sentinel.write_text(sha + "\n", encoding="utf-8", newline="\n")

    version = read_plugin_version(Path(args.source))
    if version is not None:
        (target / PLUGIN_VERSION_FILE).write_text(version + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
