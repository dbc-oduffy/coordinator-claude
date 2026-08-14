"""gen-claude-klabauter-root-pointer.py — project the claude-klabauter repo root into a cold-readable pointer file.

Purpose: reads repos.claude_klabauter from the machine-local registry and writes
<settings-home>/machine-local/.claude-klabauter-root (one line, the claude-klabauter repo root, no
trailing junk) so that BOTH the bash resolver (coordinator-claude-klabauter-root.sh rung
1.5) and the Python transport (cc_invoke.py::_resolve_claude_klabauter_root rung 1.5) can
read the pointer with zero subprocess spawn, avoiding the 5s bash-fallback hang
on Windows that motivated this fix.

Cross-platform by design (Python, not bash): the analogous DoE writer
(gen-doe-root-pointer.py) is bash-only, which is fine for the DoE resolver
(bash-native consumers only). The claude-klabauter pointer, by contrast, is read by a
Python transport whose whole point is avoiding a bash subprocess spawn on
Windows — a bash-only WRITER would reintroduce exactly the fragility (bash
dependency on the Windows install path) the reader-side fix eliminated. This
script is invoked identically from the POSIX install path (install-maximalist.py,
via `python3`/`python`) and the Windows install path (setup.ps1, via
`python3`/`python`) — one implementation, no shell-specific duplication.

Spec backlink: pln-claude-klabauter-windows-portability-a48fac § C1b
Design mirror: coordinator/bin/gen-doe-root-pointer.py (bash analog for the DoE
                repo root pointer — same idempotent/atomic/--check-only shape).
Resolution mirror: coordinator/lib/coordinator-claude-klabauter-root.sh (bash reader),
                    coordinator/bin/lib/cc_invoke.py::_resolve_claude_klabauter_root (Python reader).

Resolution order for the claude-klabauter clone root:
  1. REPO_CLAUDE_KLABAUTER env var (operator override; also the rung-1 override
     inside machine-local's resolve_sibling_repo ladder — reusing that name
     keeps a single override knob rather than inventing a second one).
  2. machine-local get repos.claude_klabauter (via a direct subprocess call to
     _machine_local.py using sys.executable — no shell, no bash, works
     identically on Windows/macOS/Linux; mirrors coordinator_registry.py's
     _registry_machine_local_get pattern).
  3. fail-loud with remediation.

Usage:
    gen-claude-klabauter-root-pointer.py             — write (or refresh) the live pointer
    gen-claude-klabauter-root-pointer.py --check-only — validate without mutating the live pointer

Idempotency: if the live pointer already contains the correct value, the file is
not rewritten (avoids spurious mtime churn and concurrent-write races in steady state).

Dry-run safety: --check-only generates to a temp file, validates, then discards.
The live pointer is byte-unchanged after any --check-only run.

Fail-loud contract: if repos.claude_klabauter is unset/empty in both the env
override and the registry, the script exits non-zero with a stderr message and
a remediation hint.

Negative-spec: does NOT clone the claude-klabauter repo, does NOT edit any registry key,
does NOT write any file other than the pointer file (and a discarded temp file
under --check-only).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile

GENERATES = []  # writes only <settings-home>/machine-local/.claude-klabauter-root, outside claude-klabauter's tracked tree

# ---------------------------------------------------------------------------
# Settings-home resolution — inline mirror of cc_invoke.py::_resolve_claude_klabauter_root.
# Kept inline (no cross-module import) for the same single-file-module reason
# _machine_local.py documents.
#
# Precedence (most-specific first):
#   COORDINATOR_SETTINGS_HOME (explicit override) →
#   ${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings
# ---------------------------------------------------------------------------


def _settings_home() -> str:
    override = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if override:
        return override
    home = (
        os.environ.get("CLAUDE_HOME")
        or os.environ.get("HOME")
        or os.environ.get("USERPROFILE")
        or os.path.expanduser("~")
    )
    return os.path.join(home, ".coordinator-claude-settings")


# ---------------------------------------------------------------------------
# machine-local registry access — direct subprocess to _machine_local.py via
# sys.executable. Mirrors coordinator_registry.py::_registry_machine_local_get.
# No shell=True, no bash — portable to Windows/macOS/Linux alike.
# ---------------------------------------------------------------------------

_CLAUDE_HOME_ENV = "CLAUDE_HOME"
_MACHINE_LOCAL_IMPL_ENV = "MACHINE_LOCAL_IMPL"


def _claude_home() -> str:
    """Return the ~/.claude root, honoring CLAUDE_HOME env var for test isolation."""
    override = os.environ.get(_CLAUDE_HOME_ENV)
    if override:
        return override
    return os.path.join(os.path.expanduser("~"), ".claude")


def _machine_local_impl() -> str:
    """Return the path to _machine_local.py, settings-home first, honoring
    MACHINE_LOCAL_IMPL for tests.

    Settings-home-first (DR-210 Amendment 2026-07-24: "resolves nothing
    through ~/.claude/bin") — this file already inlines `_settings_home()`
    above (for the `.claude-klabauter-root` pointer path) for the single-file-module
    portability reason documented there; reused here rather than a new
    cross-module import, so this file's own inlining discipline stays intact.
    Falls back to the retired compat mirror (`_claude_home()`) only when the
    settings-home candidate is absent on disk.
    """
    override = os.environ.get(_MACHINE_LOCAL_IMPL_ENV)
    if override:
        return override
    settings_home_impl = os.path.join(_settings_home(), "bin", "_machine_local.py")
    if os.path.exists(settings_home_impl):
        return settings_home_impl
    return os.path.join(_claude_home(), "bin", "_machine_local.py")


def _machine_local_get(key: str) -> str | None:
    """Call machine-local get <key> via a direct sys.executable subprocess.

    Returns the resolved value, or None on any failure (missing impl, non-zero
    exit, empty stdout). CREATE_NO_WINDOW guard suppresses the Windows console
    popup (portable: getattr resolves to 0 on non-Windows, per project convention).
    """
    impl = _machine_local_impl()
    if not os.path.isfile(impl):
        return None
    cmd = [sys.executable, impl, "get", key]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.strip()


def _resolve_claude_klabauter_root() -> str:
    """Resolve the claude-klabauter repo root: env override, then machine-local registry.

    Raises SystemExit(1) with a remediation message on stderr if unresolvable.
    """
    # Tier 1: explicit env override (mirrors gen-doe-root-pointer.py's
    # REPO_DOE_CLAUDE tier; REPO_CLAUDE_KLABAUTER is also the rung-1 override
    # inside machine-local's own resolve_sibling_repo ladder for repos.claude_klabauter).
    override = os.environ.get("REPO_CLAUDE_KLABAUTER")
    if override:
        return override

    # Tier 2: machine-local registry (repos.claude_klabauter).
    resolved = _machine_local_get("repos.claude_klabauter")
    if not resolved:
        print(
            "gen-claude-klabauter-root-pointer.py: cannot resolve repos.claude_klabauter "
            "(env REPO_CLAUDE_KLABAUTER unset; machine-local registry lookup failed/empty).",
            file=sys.stderr,
        )
        print(
            "  Remediation: machine-local set repos.claude_klabauter <path>  "
            "then re-run this script (or /coordinator:install).",
            file=sys.stderr,
        )
        sys.exit(1)
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Project the claude-klabauter repo root into a cold-readable pointer file."
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Validate without mutating the live pointer (dry-run-safe).",
    )
    args = parser.parse_args()

    claude_klabauter_root = _resolve_claude_klabauter_root().rstrip("/\\")

    if not os.path.isdir(claude_klabauter_root):
        print(
            f"gen-claude-klabauter-root-pointer.py: claude-klabauter root not found at {claude_klabauter_root!r}",
            file=sys.stderr,
        )
        print(
            "  Remediation: confirm repos.claude_klabauter in the registry is a valid "
            "directory, or set REPO_CLAUDE_KLABAUTER=<path>  then re-run.",
            file=sys.stderr,
        )
        return 1

    if not os.path.isdir(os.path.join(claude_klabauter_root, "coordinator_core")):
        print(
            f"gen-claude-klabauter-root-pointer.py: coordinator_core/ subdir absent at "
            f"{claude_klabauter_root!r}/coordinator_core",
            file=sys.stderr,
        )
        print(
            "  Remediation: confirm the claude-klabauter clone has coordinator_core/ populated.",
            file=sys.stderr,
        )
        return 1

    pointer_file = os.path.join(_settings_home(), "machine-local", ".claude-klabauter-root")

    if args.check_only:
        # Dry-run safety: write to a temp file, validate, discard. The live
        # pointer_file is never touched.
        fd, tmp_path = tempfile.mkstemp(prefix="gen-claude-klabauter-root-pointer.")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(claude_klabauter_root + "\n")
            with open(tmp_path, "r", encoding="utf-8") as f:
                written = f.read().strip()
            if written != claude_klabauter_root:
                print(
                    f"gen-claude-klabauter-root-pointer.py: --check-only validation failed "
                    f"(wrote {written!r}, expected {claude_klabauter_root!r})",
                    file=sys.stderr,
                )
                return 1
            print(
                f"gen-claude-klabauter-root-pointer.py: --check-only OK — would write "
                f"{claude_klabauter_root!r} to {pointer_file} (not written)",
                file=sys.stderr,
            )
            return 0
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    # Live write path: idempotent — skip if the pointer already holds the
    # correct value (no mtime churn, no race).
    if os.path.isfile(pointer_file):
        try:
            with open(pointer_file, "r", encoding="utf-8") as f:
                existing = f.read().strip()
        except OSError:
            existing = None
        if existing == claude_klabauter_root:
            return 0

    pointer_dir = os.path.dirname(pointer_file)
    os.makedirs(pointer_dir, exist_ok=True)

    # Atomic write: write to a sibling temp file then os.replace into place
    # (same-filesystem rename is atomic on POSIX and Windows alike).
    fd, tmp_live = tempfile.mkstemp(prefix=".claude-klabauter-root.tmp.", dir=pointer_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(claude_klabauter_root + "\n")
        os.replace(tmp_live, pointer_file)
    except Exception:
        try:
            os.remove(tmp_live)
        except OSError:
            pass
        raise

    print(f"gen-claude-klabauter-root-pointer.py: wrote {claude_klabauter_root!r} to {pointer_file}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
