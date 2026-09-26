"""untested-platform-advisory.py — warn once at ceremony start when the running
platform is declared-but-untested (packageability contract point 4).

PURPOSE: reads this repo's own `coordinator/docs/install/agent-install-manifest.json`
and compares the running platform against the manifest's `present_platforms` /
`tested_platforms` arrays. If the running platform is declared present (the repo
ships an entry-point implementation for it) but NOT declared tested (no
executed-and-verified evidence backs the claim), emit exactly one advisory line
pointing the reader at `agent-install-contract.md`'s "### Point 4" subsection.
Silent otherwise — see the three-state contract below.

Invoked from `coordinator/commands/workday-start.md` Step -0.4, alongside the
Step -1 (session reaper) and Step -0.5 (EM environment check) advisories — same
shape: one-line, non-blocking, early in the ceremony.

THREE-STATE CONTRACT:
  1. running platform in present_platforms, NOT in tested_platforms
     -> emit exactly one advisory line, exit 0.
  2. running platform in tested_platforms (or manifest has no present_platforms/
     tested_platforms data at all) -> silent, exit 0.
  3. manifest declares no `packageability_compliance.declared: true` marker
     -> silent, exit 0 (mirrors validate-install-contract.py's existing
     declared===true skip-clean rule — a repo that hasn't opted into the
     contract is never held to it).

ADVISORY ONLY (per plan Anti-scope): this script NEVER exits non-zero and NEVER
blocks the ceremony it's invoked from. Any error (missing/unreadable/malformed
manifest, unrecognized platform) degrades to silent exit 0 — the same
best-effort orientation-banner posture as check-em-environment.py.

Windows-clean: platform resolution uses stdlib `platform.system()` (no shell-
out, no `/etc/os-release` read); the manifest path is derived from `__file__`
via `pathlib`/`os.path` (no `expanduser("~")`/`HOME` dependency — this script
never needs the user's home directory, only its own on-disk location).

Spec backlink: DoE-claude:pln-platform-verified-is-a-distinc-a076aa § C4
"""
from __future__ import annotations

import json
import os
import platform
import sys

_PLATFORM_MAP = {
    "Darwin": "macos",
    "Linux": "linux",
    "Windows": "windows",
}

_MANIFEST_RELATIVE = os.path.join("docs", "install", "agent-install-manifest.json")

_ANCHOR_HINT = (
    "coordinator/docs/wiki/agent-install-contract.md's \"### Point 4\" subsection"
)


def _running_platform_id() -> str | None:
    return _PLATFORM_MAP.get(platform.system())


def _manifest_path() -> str:
    bin_dir = os.path.dirname(os.path.abspath(__file__))
    coordinator_dir = os.path.dirname(bin_dir)
    return os.path.join(coordinator_dir, _MANIFEST_RELATIVE)


def _load_manifest(path: str) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def advisory_line(manifest: dict | None, running_platform: str | None) -> str | None:
    if manifest is None or running_platform is None:
        return None

    if manifest.get("packageability_compliance", {}).get("declared") is not True:
        return None

    present = manifest.get("present_platforms") or []
    tested = manifest.get("tested_platforms") or []

    if running_platform in present and running_platform not in tested:
        return (
            f"⚠ UNTESTED PLATFORM — this repo declares '{running_platform}' "
            f"present but not tested (packageability contract point 4). See "
            f"{_ANCHOR_HINT} before treating this ceremony's output as "
            f"platform-verified."
        )

    return None


def main(argv: "list[str] | None" = None) -> int:
    del argv
    try:
        running_platform = _running_platform_id()
        manifest = _load_manifest(_manifest_path())
        line = advisory_line(manifest, running_platform)
        if line:
            print(line)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
