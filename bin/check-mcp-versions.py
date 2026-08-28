# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""check-mcp-versions.py — Compare pinned MCP server versions against npm latest.

Reads pinned versions from settings.json and reports available updates.
Designed to be called manually or from a session-orientation ceremony
(Tool Availability section).

Respects a 7-day cooldown via a marker file to avoid hammering npm.
Pass --force to skip the cooldown.

Port backlink: docs/plans/2026-07-19-debash-coordinator-windows.md § E3-b

KNOWN GAP (self-claim scope-drop, NOT reproduced in this port): the bash
oracle registered the marker-file write with the active coordinator session
via lib/coordinator-session.sh::cs_self_claim (best-effort, no-op if the lib
or an active session is absent). No general-purpose Python "register this
path with the current session" call exists yet (mirrors the same documented
gap in coordinator/bin/refresh-queries.py's port header). Until a Python
self-claim port lands, files this script writes during an active session
will not appear in touched.txt. Flagged here per DR-059, not silently
dropped.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import subprocess
import sys

GENERATES = []  # writes only ~/.claude/.mcp-version-check (cooldown marker), outside claude-klabauter's own tracked tree

COOLDOWN_DAYS = 7

_PINNED_RE = re.compile(r"^(?P<pkg>.+)@(?P<ver>[0-9][0-9.]*)$")


def _claude_config_dir() -> str:
    """`<harness-config>/` root, routed through the canonical seam rather than
    hand-rolled `~/.claude` — see coordinator_core._settings_home.claude_config_dir()'s
    module docstring for the CLAUDE_HOME/CLAUDE_CONFIG_DIR naming split this closes."""
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_colocated_engine_on_path

    require_colocated_engine_on_path(__file__)
    from coordinator_core._settings_home import claude_config_dir

    return str(claude_config_dir())


def _settings_path() -> str:
    return os.path.join(_claude_config_dir(), "settings.json")


def _marker_path() -> str:
    return os.path.join(_claude_config_dir(), ".mcp-version-check")


def _cooldown_active(marker: str) -> tuple[bool, int]:
    try:
        with open(marker, "r", encoding="utf-8") as fh:
            last_check = fh.read().strip()
    except OSError:
        return False, 0

    try:
        last_date = datetime.datetime.strptime(last_check, "%Y-%m-%d").replace(
            tzinfo=datetime.timezone.utc
        )
    except ValueError:
        print(
            "WARNING: could not parse last-check date '%s' — treating "
            "cooldown as expired" % last_check,
            file=sys.stderr,
        )
        return False, 0

    now = datetime.datetime.now(datetime.timezone.utc)
    age_days = (now - last_date).days
    return age_days < COOLDOWN_DAYS, age_days


def _write_marker(marker: str) -> None:
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    with open(marker, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(today + "\n")


def _collect_pinned_packages(settings_path: str) -> list[tuple[str, str]]:
    try:
        with open(settings_path, "r", encoding="utf-8") as fh:
            settings = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []

    pinned: list[tuple[str, str]] = []
    mcp_servers = settings.get("mcpServers") or {}
    if not isinstance(mcp_servers, dict):
        return []

    for _name, entry in mcp_servers.items():
        if not isinstance(entry, dict):
            continue
        args = entry.get("args") or []
        if not isinstance(args, list):
            continue
        for arg in args:
            if not isinstance(arg, str) or "@" not in arg:
                continue
            if not re.search(r"@[0-9]", arg):
                continue
            match = _PINNED_RE.match(arg)
            if match:
                pinned.append((match.group("pkg"), match.group("ver")))
    return pinned


def _npm_latest(pkg: str) -> str | None:
    try:
        proc = subprocess.run(
            ["npm", "view", pkg, "version"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    latest = proc.stdout.strip()
    return latest or None


def main(argv: list[str]) -> int:
    force = "--force" in argv

    marker = _marker_path()
    settings = _settings_path()

    if not force:
        cooling, age_days = _cooldown_active(marker)
        if cooling:
            print(
                "MCP versions: checked %dd ago (cooldown: %dd). "
                "Pass --force to recheck." % (age_days, COOLDOWN_DAYS)
            )
            return 0

    if shutil.which("npm") is None:
        print("MCP versions: npm not found, skipping check.")
        return 0

    pinned_packages = _collect_pinned_packages(settings)

    if not pinned_packages:
        print("MCP versions: no pinned npm packages found in settings.json.")
        _write_marker(marker)
        return 0

    print("MCP version check:")
    updates_available = False
    for pkg, pinned_ver in pinned_packages:
        latest = _npm_latest(pkg)
        if not latest:
            continue
        if pinned_ver != latest:
            updates_available = True
            print("  - **%s**: pinned %s -> latest %s" % (pkg, pinned_ver, latest))

    if not updates_available:
        print("  All pinned MCP packages are current.")

    _write_marker(marker)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
