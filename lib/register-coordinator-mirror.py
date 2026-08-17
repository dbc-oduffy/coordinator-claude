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

# This file lives in coordinator/lib/ (not coordinator/bin/), so the shared
# cc_invoke helper is a sibling of coordinator/bin/, not of this file's own directory.
_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin", "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_main():
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.ops.register_coordinator_mirror import main as _op_main
    return _op_main


def _python_argv(script: str, *args: str) -> list:
    """Build an argv that invokes a `.py` script via a resolved interpreter.

    `[script, ...]` alone cannot exec a `.py` file directly on any platform —
    this always needs an explicit interpreter in argv[0]. Probes python3 /
    python / py in that order (matches the sibling shell callers of
    resolve-coordinator-clone.py) rather than relying on a shebang re-exec,
    which is the load-bearing fix over the retired bash predecessor: that one
    shelled out via `bash <script>` on Windows — a bash dependency this port
    removes entirely.

    # Review: code-reviewer (slicedoe-2commits Finding 5) — on Windows, probe
    # `sys.executable` first: `shutil.which("python3")` can resolve to the
    # App-Execution-Alias stub under `%LOCALAPPDATA%/Microsoft/WindowsApps/`
    # (a Store-redirect shim, not a real interpreter) when the operator
    # hasn't disabled the alias, whereas `sys.executable` is always the real,
    # currently-running interpreter and never a Store stub. POSIX behavior is
    # unchanged.
    """
    if os.name == "nt" and sys.executable:
        return [sys.executable, script, *args]
    for cand in ("python3", "python", "py"):
        if shutil.which(cand):
            return [cand, script, *args]
    return [sys.executable, script, *args]


def _claude_home_argv(*args: str) -> list:
    """Resolve an executable argv for the `claude-home` helper.

    A bare "claude-home" fails on Windows with WinError 2: CreateProcess does
    not consult PATHEXT (so the delivered `.cmd` is invisible) and the install's
    bin dir is not necessarily on PATH anyway. Probe the known install
    locations for the `.cmd` first, then fall back to PATH lookup — shutil.which
    DOES honour PATHEXT — and only then to the bare name.

    POSIX branch (state/audits/2026-07-25-claude-bin-mirror-read-rungs.md § 2,
    this function's row): a bare "claude-home" PATH lookup is order-dependent
    on whatever the invoking process's PATH happens to contain, which can
    resolve to the retired mirror ahead of settings-home. Probe settings-home
    by explicit path first, then PATH (`shutil.which`), then the retired
    mirror by explicit path, with the bareword as the final rung — mirroring
    `coordinator_core/install/maximalist.py::_claude_home_cli_argv`'s POSIX
    branch. Negative spec: the mirror does not go ahead of `shutil.which`.
    """
    if os.name == "nt":
        # Review: code-reviewer (slice1b Finding 1) — EM-verified disposition:
        # `CLAUDE_HOME` means "the home directory *containing* `.claude`", not
        # `~/.claude` itself. 889 call sites across this codebase join
        # `CLAUDE_HOME` with `/.claude` (the `${CLAUDE_HOME:-$HOME}/.claude/...`
        # idiom) vs. 5 that use it bare, and those 5 are docs/tests, not
        # runtime resolvers. The `.claude`-suffix join below is correct and
        # consistent with that convention — do not "fix" it to drop the join.
        # Settings-home first (DR-210 Amendment 2026-07-24: "resolves nothing
        # through ~/.claude/bin") — this Windows-only probe previously tried
        # the retired compat mirror's `.cmd` BEFORE settings-home's, an
        # inverted precedence on the platform that matters most (Windows is
        # the primary machine per DoE-claude CLAUDE.md § Runtime conventions).
        # Swapped so settings-home wins whenever both candidates exist; the
        # mirror candidate is retained, tried last.
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
        # Review: code-reviewer (slice1b Finding 3) — breadcrumb before the
        # bare-name last resort: distinguishes "not installed" from
        # "installed somewhere unexpected" for an operator debugging a
        # WinError 2 on the fallback below.
        print(
            "register-coordinator-mirror.py: claude-home not found at known install "
            "locations or on PATH; falling back to bare-name invocation (likely to fail "
            "with WinError 2 on Windows if not on PATH)",
            file=sys.stderr,
        )
        return ["claude-home", *args]

    # Review: review-integrator — same bareword defect flagged in
    # maximalist.py's POSIX branch (audit row above); ladder now matches.
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
    """DoE-local "coordinator live path" resolution — unchanged from the bash oracle.

    Tier 1: the script-relative resolve-coordinator-clone.py --for-content helper
    (co-located sibling of this file — this file lives in coordinator/lib/, so
    "up one then back into lib/" lands on the same directory). Invoked directly
    via a resolved python interpreter (E2-c ported the resolver itself to naked
    Python), removing the Windows-only `bash <script>` indirection the retired
    bash predecessor needed. Tier 2 (defensive fallback, resolver missing or returned
    empty): flat layout under `claude-home plugins`.
    """
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

    # Review: code-reviewer (slicedoe-2commits Finding 4) — one-line stderr
    # breadcrumb before the Tier-2 fallback so a transient Tier-1 failure
    # (torn resolver script, permissions) isn't papered over indefinitely.
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
