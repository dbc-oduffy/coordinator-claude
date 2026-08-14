"""lib/coordinator_currency.py — Per-repo coordinator currency stamp: write + read.

Purpose: records which COORDINATOR_SCHEMA_VERSION a project's scaffolding was
onboarded (or last refreshed) against. Consumed by /repo-setup and
/coordinator:install Currency-stamp steps (stamp write).

Port: docs/plans/2026-07-19-debash-coordinator-windows.md (chunk E3-f).

Spec backlink: docs/plans/2026-05-29-it-just-works-agentic-install-currency.md § Chunk 1

Compose-vs-invent decision (recorded here per spec, carried over from the bash
oracle): the existing version.txt sentinel (agentic-install-integrity.md §3) is
a git-SHA anchoring the PLUGIN live-install to a source HEAD — it is a
byte-divergence classifier anchor, not a schema version. `probe-onboarding-currency.py`
(P-13, backed natively by `coordinator_core.ops.probe_onboarding_currency`) has
no concept of "consumer project was onboarded against schema version N" vs
"plugin install differs from plugin source." These primitives are orthogonal.
A per-repo stamp (coordinator-currency.yaml) is therefore required. It is kept
separate from coordinator-setup-state.yaml whose set-once/never-overwritten
contract is architecturally load-bearing.

Stamp location (per-repo): docs/coordinator-currency.yaml
Schema version source:      <plugin_root>/coordinator-schema-version  (single integer line)

Public API:
    coordinator_currency_write(repo_root, plugin_root) -> None
        Idempotent stamp write. Raises CurrencyError on failure (unreadable
        schema constant, directory create failure, write failure).
    coordinator_currency_read(repo_root) -> str | None
        Returns the stamped schema_version, or None when absent/unparseable.

FIX-IN-PORT (DR-059): the bash oracle also exposed `coordinator_currency_probe`.
That classification (current / drift(N->M) / unstamped(legacy) / inconclusive)
is now natively implemented in claude-klabauter as
`coordinator_core.ops.probe_onboarding_currency.coordinator_currency_probe`,
already wired to callers via `bin/probe-onboarding-currency.py` (P-13). This
port does NOT reproduce a second probe implementation — callers that need the
drift classification invoke `bin/probe-onboarding-currency.py` directly.

CLI entrypoint (for bash/markdown-doc callers that cannot import Python
modules directly — commands/install.md, skills/repo-setup/SKILL.md):
    python3 coordinator_currency.py write <repo_root> <plugin_root>
    python3 coordinator_currency.py read <repo_root>
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from datetime import datetime, timezone

_SCHEMA_VERSION_RE = re.compile(r"^[1-9][0-9]*$")
_STAMP_VERSION_RE = re.compile(r"^schema_version:\s*([1-9][0-9]*)\s*$")


class CurrencyError(Exception):
    """Raised on a write failure (unreadable schema constant, I/O error)."""


def _stamp_path(repo_root: str) -> str:
    return os.path.join(repo_root, "docs", "coordinator-currency.yaml")


def _read_schema_version(plugin_root: str) -> str | None:
    ver_file = os.path.join(plugin_root, "coordinator-schema-version")
    try:
        with open(ver_file, "r", encoding="utf-8") as fh:
            raw = fh.read()
    except OSError:
        return None
    ver = raw.strip()
    if _SCHEMA_VERSION_RE.match(ver):
        return ver
    return None


def coordinator_currency_read(repo_root: str) -> str | None:
    """Read the stamped schema_version from repo_root's stamp file.

    Returns the version string, or None when the stamp is absent or its
    schema_version line is missing/unparseable.
    """
    stamp_path = _stamp_path(repo_root)
    try:
        with open(stamp_path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return None
    for line in lines:
        m = _STAMP_VERSION_RE.match(line.rstrip("\n"))
        if m:
            return m.group(1)
    return None


def coordinator_currency_write(repo_root: str, plugin_root: str) -> None:
    """Idempotent stamp write.

    If a stamp already exists with the SAME version, this is a byte-identical
    no-op (no file touch — see T2 in the port's pytest coverage: a rewrite on
    an unchanged version would spuriously bump stamped_at and create noise
    diffs). If the stamp exists with a DIFFERENT version, overwrites (refresh
    after plugin upgrade). Creates docs/ if absent.

    Raises CurrencyError when the schema constant is unreadable or the write
    fails (directory create / temp-file write / atomic rename).
    """
    current_version = _read_schema_version(plugin_root)
    if current_version is None:
        raise CurrencyError(
            f"cannot read COORDINATOR_SCHEMA_VERSION from "
            f"'{plugin_root}/coordinator-schema-version'"
        )

    stamp_path = _stamp_path(repo_root)
    stamp_dir = os.path.dirname(stamp_path)

    if os.path.isfile(stamp_path):
        existing_version = coordinator_currency_read(repo_root)
        if existing_version == current_version:
            return  # already current — no file change

    try:
        os.makedirs(stamp_dir, exist_ok=True)
    except OSError as exc:
        raise CurrencyError(f"failed to create directory '{stamp_dir}': {exc}") from exc

    stamp_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    body = (
        "# coordinator-currency.yaml — per-repo coordinator schema currency stamp.\n"
        "#\n"
        "# Written by: coordinator_currency_write (lib/coordinator_currency.py)\n"
        "# Spec backlink: docs/plans/2026-05-29-it-just-works-agentic-install-currency.md § Chunk 1\n"
        "#\n"
        "# MUTABLE — updated on refresh. Separate from coordinator-setup-state.yaml (set-once).\n"
        "# Read by: doctor probe P-13 (bin/probe-onboarding-currency.py).\n"
        f"schema_version: {current_version}\n"
        f"stamped_at: {stamp_date}\n"
    )

    fd, tmp_path = tempfile.mkstemp(prefix=os.path.basename(stamp_path) + ".", dir=stamp_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(body)
        os.replace(tmp_path, stamp_path)
    except OSError as exc:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise CurrencyError(f"failed to write stamp '{stamp_path}': {exc}") from exc


# ---------------------------------------------------------------------------
# CLI trampoline — for bash/markdown-doc callers (install.md, repo-setup SKILL.md)
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(
            "usage: coordinator_currency.py write <repo_root> <plugin_root>\n"
            "       coordinator_currency.py read <repo_root>",
            file=sys.stderr,
        )
        return 2

    cmd = argv[0]
    if cmd == "write":
        if len(argv) != 3:
            print("usage: coordinator_currency.py write <repo_root> <plugin_root>", file=sys.stderr)
            return 2
        try:
            coordinator_currency_write(argv[1], argv[2])
        except CurrencyError as exc:
            print(f"coordinator_currency_write: {exc}", file=sys.stderr)
            return 1
        return 0

    if cmd == "read":
        if len(argv) != 2:
            print("usage: coordinator_currency.py read <repo_root>", file=sys.stderr)
            return 2
        version = coordinator_currency_read(argv[1])
        if version is None:
            return 1
        print(version)
        return 0

    print(f"unknown subcommand '{cmd}' — expected write|read", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
