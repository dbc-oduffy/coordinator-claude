#!/usr/bin/env python3
"""platform-localize.py — INSTALL-TIME (NOT a live SessionStart hook, despite
some historical comment framing elsewhere) localizer for per-machine Claude
Code settings. Trampoline over claude-klabauter coordinator_core.hooks.platform_localize.

Deployment topology note (load-bearing for the resolution strategy below):
unlike coordinator-auto-push / install-substrate.sh (which run FROM the
coordinator source tree, so a __file__-relative `lib/` sibling reliably
exists), THIS file is COPIED at install time to
`<settings-home>/bin/platform-localize.py` (and a compat copy at
`~/.claude/bin/platform-localize.py`) by install-substrate.sh /
coordinator_core.install.substrate — see install-maximalist.sh:573-575
("This runs from the INSTALLED location ... not from the coordinator
tree."). A __file__-relative `lib/cc_invoke.py` sibling is therefore NOT
guaranteed to exist wherever this copy happens to run from. Resolution
instead anchors on the FIXED, position-independent contract path
`${CLAUDE_HOME:-$HOME}/.claude/bin/resolve-coordinator-clone --for-content`
(the same "out-of-tree consumer" fixed-path contract resolve-coordinator-
clone's own header documents for exactly this chicken-and-egg class of
caller), falling back to a __file__-relative sibling only as a last resort
(covers running straight from templates/bin/ during development/tests).

Callers (as of this port): first-run.sh (Step 4c, fail-loud), coordinator/
commands/install.md (Step 9, fail-loud), dist/publish-repo-setup/install.sh
(delivers the copy; does not itself execute it), and claude-klabauter's
coordinator_core/install/uninstall_legs.py:680 (CHECK 5 tri-file regen on
`revert-to-marketplace` uninstall — that subprocess call site is a
cross-repo consumer NOT repointed by this port; it already tolerates a
non-zero exit by appending to its own `errors` list rather than crashing).

Exit-code contract — FAIL-LOUD (this is an install/config-writer script,
not a never-block runtime hook; both first-run.sh:173 ("fail-loud on any
non-zero exit") and install.md Step 9 treat a non-zero exit here as fatal
to the whole install chain — mirrors install-substrate.sh's same
documented posture):
  0 — ran to completion (including the no-op case of nothing to localize).
  1 — the ported module ran and recorded an unexpected internal error (see
      coordinator_core.hooks.platform_localize.main's own docstring for its
      business exit-code contract).
  3 — DEDICATED transport-failure code (PORTER-BRIEF-ADDENDUM § 3b): the
      coordinator-root / CLAUDE_KLABAUTER_ROOT resolution failed, or
      coordinator_core.hooks.platform_localize was not importable. Distinct
      from 1 (a business-logic failure) so a caller can tell "claude-klabauter link is
      down" apart from "localization itself found something wrong" — never
      silently degrades to 0, unlike the never-block posture used for hot-
      path hooks (coordinator-auto-push).

Spec backlink: docs/plans/2026-07-16-bash-to-naked-python-engine-migration.md
Prior filename: platform-localize.sh (renamed off .sh 2026-07-22 as part of
the repo-wide de-bash sweep — see state/audits/2026-07-20-sh-suffixed-
python-trampolines.md; the file's body has been pure Python since
28a7b868 "de-polyglot"). Every known in-repo caller has been repointed in
the same commit; the sole cross-repo caller (claude-klabauter's uninstall_legs.py) is
out of reach from here and is accepted-broken per the de-bash campaign's
"we fix tomorrow" posture.
"""

import os
import subprocess
import sys
from pathlib import Path

_TRANSPORT_FAILURE_EXIT = 3

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_NO_CONSOLE = {"creationflags": _CREATE_NO_WINDOW} if os.name == "nt" else {}


def _resolve_coordinator_root() -> str:
    """Locate the coordinator plugin content root without assuming this file
    (a post-install COPY, not an in-tree file) has any particular sibling
    layout — see the deployment-topology comment block above.

    Rung 1: the fixed, position-independent contract path
            `${CLAUDE_HOME:-$HOME}/.claude/bin/resolve-coordinator-clone
            --for-content` — resolve-coordinator-clone's own header documents
            this exact path as the stable contract for out-of-tree callers
            with the identical chicken-and-egg problem this file has.
    Rung 2: a __file__-relative sibling `resolve-coordinator-clone` (covers
            running straight from coordinator/templates/bin/ in dev/tests,
            where the fixed CLAUDE_HOME path may not be installed yet).
    Raises RuntimeError if neither resolves.
    """
    # Path.home() (not os.path.expanduser) fails loud -- RuntimeError, not a
    # silent "~" -- when every home rung (USERPROFILE, HOME) is unset; this
    # is a fail-loud install script (see module docstring's exit-code
    # contract), so a resolution failure here belongs in that same posture.
    claude_home = os.path.join(os.environ.get("CLAUDE_HOME") or str(Path.home()), ".claude")
    candidates = [
        os.path.join(claude_home, "bin", "resolve-coordinator-clone"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "resolve-coordinator-clone"),
    ]

    resolver = next((c for c in candidates if os.path.isfile(c)), None)
    if resolver is None:
        raise RuntimeError(
            "resolve-coordinator-clone not found at any of: " + ", ".join(candidates)
        )

    # resolve-coordinator-clone is python3 source as of the 2026-07-22 de-bash
    # wave (was bash at commit-time; see the header note above) — invoke it
    # with a Python interpreter, matching the house fallback ladder used
    # elsewhere in this port wave (see install-substrate.py's identical
    # `sys.executable or platform-gated fallback` shape).
    # (Review: code-reviewer — F1, 2026-07-22.)
    python_bin = sys.executable or ("python" if os.name == "nt" else "python3")
    try:
        proc = subprocess.run(
            [python_bin, resolver, "--for-content"],
            capture_output=True,
            text=True,
            timeout=15,
            stdin=subprocess.DEVNULL,
            **_NO_CONSOLE,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"resolve-coordinator-clone --for-content failed to run: {exc}") from exc

    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError(
            f"resolve-coordinator-clone --for-content exited {proc.returncode}: "
            f"{(proc.stderr or '').strip()}"
        )
    return proc.stdout.strip()


def _import_main():
    """Resolve the coordinator root, then CLAUDE_KLABAUTER_ROOT via cc_invoke's
    battle-tested ladder (env var -> settings-home pointer file ->
    coordinator-claude-klabauter-root.sh) rather than re-deriving it -- this is a plain
    in-process import, not an RPC invoke, so cc_invoke's subprocess-spawn
    transport (cc_invoke()/route()) is deliberately NOT used here (same shape
    as coordinator-auto-push / handoff-gate-aging — template-variant #1,
    direct-import).
    """
    # Rung 0 — CLAUDE_KLABAUTER_ROOT env, honored directly. cc_invoke.py migrated to
    # claude-klabauter with the executable surface (b644d5a9), so on a post-migration
    # content root the cc_invoke import below is unreachable until claude-klabauter is
    # already known — env-pinned callers (tests, install legs) break that cycle.
    env_claude_klabauter = os.environ.get("CLAUDE_KLABAUTER_ROOT")
    if env_claude_klabauter and os.path.isdir(env_claude_klabauter):
        claude_klabauter_root = env_claude_klabauter
    else:
        coordinator_root = _resolve_coordinator_root()
        bin_lib_dir = os.path.join(coordinator_root, "bin", "lib")
        if not os.path.isfile(os.path.join(bin_lib_dir, "cc_invoke.py")):
            raise RuntimeError(f"cc_invoke.py not found under resolved coordinator root: {bin_lib_dir}")
        if bin_lib_dir not in sys.path:
            sys.path.insert(0, bin_lib_dir)
        from cc_invoke import _resolve_claude_klabauter_root

        claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.hooks.platform_localize import main as _op_main

    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"platform-localize: coordinator-root/CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(_TRANSPORT_FAILURE_EXIT)
    except ImportError as exc:
        print(
            f"platform-localize: coordinator_core.hooks.platform_localize not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(_TRANSPORT_FAILURE_EXIT)

    sys.exit(op_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
