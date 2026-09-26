"""
register-coordinator-mirror.py — CLI trampoline over claude-klabauter
coordinator_core.ops.register_coordinator_mirror.

Finish-strangler port (DOE-PORT, variant #1 — pristine, no claude-klabauter shim borrows this
script): the bash implementation (idempotent atomic write of
`registry.local.toml::plugin.mirrors.coordinator-claude`) has been fully ported to
coordinator_core/ops/register_coordinator_mirror.py per DR-047 (DoE owns
contract/generator, claude-klabauter owns engine). This file is now a thin DoE-side (contract)
trampoline over that claude-klabauter (engine) module — it resolves the DoE-local "coordinator
live path" fact (script-relative `resolve-coordinator-clone.py --for-content`, with a
`claude-home plugins` fallback, exactly as the bash oracle did) and hands it to the
Claude-klabauter module via `--live-path`; the claude-klabauter module owns only the pure TOML-section
write.

A sibling `.cmd` launcher (regenerated via `coordinator/bin/gen-launcher-shim.py`)
preserves Windows bareword-invocation parity (DR-076).

Spec: docs/plans/2026-05-21-plugin-source-live-mirror-doctrine.md § Chunk 5 / AC-7
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin", "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402
from python_interp import python_argv  # noqa: E402


def _import_main():
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.ops.register_coordinator_mirror import main as _op_main
    return _op_main


def _python_argv(script: str, *args: str) -> list:
    """Build an argv that invokes a `.py` script via a resolved interpreter.

    `[script, ...]` alone cannot exec a `.py` file directly on any platform —
    this always needs an explicit interpreter in argv[0]. Delegates to the
    shared `python_interp.python_argv` ladder (venv-agnostic here; this is a
    standalone script invocation, not a repo test resolver) rather than
    relying on a shebang re-exec, which is the load-bearing fix over the
    retired bash predecessor: that one shelled out via `bash <script>` on
    Windows — a bash dependency this port removes entirely.

    On Windows, the shared ladder prefers a console CPython resolved from
    `sys.executable` over probing `python3` on PATH: `shutil.which("python3")`
    can resolve to the App-Execution-Alias stub under
    `%LOCALAPPDATA%/Microsoft/WindowsApps/` (a Store-redirect shim, not a real
    interpreter) when the operator hasn't disabled the alias. What changed:
    the premise "`sys.executable` is always the real, currently-running
    interpreter" is false under an installed forwarder (e.g. a
    Store-alias-adjacent launcher exe) — handing that exe a script path
    re-enters the forwarder's own argv parsing rather than running the
    script. "Never a Store stub" still holds: the shared ladder refuses a
    forwarder and falls through to `sys._base_executable` and then
    `shutil.which("python3")`/`shutil.which("python")` instead. POSIX
    behavior is unchanged.
    """
    resolved = python_argv(script, *args)
    if resolved is not None:
        return resolved
    for cand in ("python3", "python", "py"):
        if shutil.which(cand):
            return [cand, script, *args]
    return [sys.executable, script, *args]


def _claude_home_argv(*args: str) -> list:
    if os.name == "nt":
        # `CLAUDE_HOME` means "the home directory *containing* `.claude`", not
        # `CLAUDE_HOME` with `/.claude` (the `${CLAUDE_HOME:-$HOME}/.claude/...`
        home = (
            os.environ.get("CLAUDE_HOME")
            or os.environ.get("HOME")
            or os.environ.get("USERPROFILE")
            or os.path.expanduser("~")
        )
        for cand in (
            os.path.join(home, ".coordinator-claude-settings", "bin", "claude-home.cmd"),
            os.path.join(home, ".claude", "bin", "claude-home.cmd"),
        ):
            if os.path.isfile(cand):
                return [cand, *args]
        found = shutil.which("claude-home")
        if found:
            return [found, *args]
        print(
            "register-coordinator-mirror.py: claude-home not found at known install "
            "locations or on PATH; falling back to bare-name invocation (likely to fail "
            "with WinError 2 on Windows if not on PATH)",
            file=sys.stderr,
        )
        return ["claude-home", *args]

    home = os.environ.get("HOME") or os.environ.get("USERPROFILE") or os.path.expanduser("~")
    settings_home_cand = os.path.join(
        os.environ.get("COORDINATOR_SETTINGS_HOME")
        or os.path.join(home, ".coordinator-claude-settings"),
        "bin",
        "claude-home",
    )
    if os.path.isfile(settings_home_cand):
        return [settings_home_cand, *args]
    found = shutil.which("claude-home")
    if found:
        return [found, *args]
    mirror_cand = os.path.join(home, ".claude", "bin", "claude-home")
    if os.path.isfile(mirror_cand):
        return [mirror_cand, *args]
    return ["claude-home", *args]


def _resolve_coordinator_live() -> str:
    this_dir = os.path.dirname(os.path.abspath(__file__))
    resolver = os.path.join(this_dir, "..", "lib", "resolve-coordinator-clone.py")
    coordinator_live = ""
    tier1_fail_reason = None
    if os.path.isfile(resolver):
        try:
            result = subprocess.run(
                _python_argv(resolver, "--for-content"),
                capture_output=True,
                text=True,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode == 0:
                coordinator_live = result.stdout.strip()
                if not coordinator_live:
                    tier1_fail_reason = "resolver exited 0 but printed no path"
            else:
                tier1_fail_reason = f"resolver exited {result.returncode}"
        except OSError as exc:
            coordinator_live = ""
            tier1_fail_reason = f"resolver invocation raised OSError: {exc}"
    else:
        tier1_fail_reason = "resolver script not found"

    if not coordinator_live and tier1_fail_reason:
        print(
            f"register-coordinator-mirror.py: resolver Tier 1 failed ({tier1_fail_reason}), "
            "falling back to claude-home plugins",
            file=sys.stderr,
        )

    if not coordinator_live:
        try:
            plugins_result = subprocess.run(
                _claude_home_argv("plugins"),
                capture_output=True,
                text=True,
                check=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            print(
                f"register-coordinator-mirror.py: failed to resolve coordinator live path: {exc}",
                file=sys.stderr,
            )
            sys.exit(1)
        coordinator_live = os.path.join(
            plugins_result.stdout.strip(), "coordinator-claude", "coordinator"
        )

    return coordinator_live


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"register-coordinator-mirror.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except ImportError as exc:
        print(
            f"register-coordinator-mirror.py: coordinator_core.ops.register_coordinator_mirror not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    coordinator_live = _resolve_coordinator_live()
    argv = list(sys.argv[1:]) + ["--live-path", coordinator_live]
    sys.exit(op_main(argv))


if __name__ == "__main__":
    main()
