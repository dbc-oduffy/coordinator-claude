# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""edit-live-hook.py — CLI trampoline over the claude-klabauter stage/validate/atomic-swap
helper for editing a live PreToolUse Bash-matcher hook.

Provides `stage` (copy the live hook to a same-directory scratch file) and
`commit` (bash -n validate the scratch file, then atomically swap it over the
live hook, refusing the swap on syntax failure) so a hook edit never exposes a
syntactically-broken intermediate to the Claude Code harness's per-tool-call
exec. Built to prevent the fleet-wide Bash-tool outage documented in
concurrent-em-hazards.md § H33.
"""
# edit-live-hook.sh — CLI trampoline over claude-klabauter
# coordinator_core.ops.edit_live_hook: stage/validate/atomic-swap helper for
# editing a LIVE PreToolUse Bash-matcher hook without ever exposing a
# syntactically-broken intermediate to the Claude Code harness's per-tool-call
# `exec`. See coordinator/docs/wiki/concurrent-em-hazards.md § H33 for the
# incident this helper was built to prevent (2026-07-09, block-illegal-
# filename.sh heredoc-fix took down 4 concurrent agents' Bash tool fleet-wide).
#
# DO NOT multi-Edit a live Bash-matcher hook path directly, even "just to fix
# one line" — there is no atomic single-line Edit at the harness level; the
# file is briefly absent/truncated during the write, and a fresh `exec` racing
# that window sees a broken or empty script. Always stage-edit-validate-swap.
#
# Usage:
#   edit-live-hook.sh stage <hook-path>
#       Copies <hook-path> to a scratch file next to it (same directory, so
#       the eventual swap is same-filesystem/atomic) and prints the scratch
#       path. Also runs the Bash-matcher detection check and WARNs — but does
#       not block — if the target isn't actually a live Bash-matcher hook.
#
#   edit-live-hook.sh commit <hook-path> <scratch-path>
#       Validates <scratch-path> with `bash -n`. On success, atomically swaps
#       <scratch-path> over <hook-path> (same-filesystem replace) and reports
#       success. On syntax failure, refuses to swap, leaves both files in
#       place, and exits non-zero — the live hook is never touched.
#
# Exit codes (parity-critical — matches coordinator_core.ops.edit_live_hook
# byte-for-byte):
#   0 — success
#   1 — usage/argument error
#   2 — `bash -n` validation failure on commit (or `bash` unavailable on this
#       machine) — the swap did NOT happen; live hook untouched.
#   3 — CLAUDE_KLABAUTER_ROOT resolution / import failure (transport failure). This is
#       a dedicated code, distinct from both business codes above, per the
#       fail-loud-validator posture (a stage/commit call must not silently
#       misreport a claude-klabauter-link outage as either a usage error or a syntax
#       failure) — DO NOT reuse 1 or 2 for this case.
#
# Shebang note: the SHEBANG line above is `#!/usr/bin/env python3`, generator-
# owned by `gen-launcher-shim.py --ensure-unix`, and correct for this shape. On
# Windows, this file's co-located `.cmd` twin wins via `PATHEXT` when invoked
# as a bareword, so the shebang is never read there; on macOS/Linux `python3`
# is the right interpreter. Caution: callers must invoke via the extensionless
# name or a resolved-interpreter prefix, never a bareword `.py` through git-
# bash — git-bash DOES honor the shebang and would exec-127 with no `python3`
# present. See the carve-out in DoE-claude's coordinator/docs/wiki/bash-on-
# windows-gotchas.md § Carve-out (cross-repo — this wiki lives in the
# DoE-claude repo, not here).
#
# Ported logic: claude-klabauter coordinator_core/ops/edit_live_hook.py
# (co-located pytest: coordinator_core/ops/test_edit_live_hook.py)
# Spec backlink: DoE-claude:pln-bash-polyglot-clean-slate-full-5c71ee

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402

EXIT_TRANSPORT_FAILURE = 3


def _import_runner():
    """Resolve CLAUDE_KLABAUTER_ROOT, put it on sys.path, and import the shared
    in-process runner.

    Reuses cc_invoke's battle-tested CLAUDE_KLABAUTER_ROOT resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it -- this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.

    DR-276: the op is run through `coordinator_core.cli_entry.run_op_main`
    rather than by importing and calling its `main` directly, so the atomic
    swap it declares on `commit` becomes a session scope-touch claim. Without
    that, the live hook this helper swaps in is an orphan at the
    `scoped_git_commit` sink.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main() -> None:
    # EDIT_LIVE_HOOK_SCRIPT_DIR tells the ported module where THIS trampoline
    # lives, so its Bash-matcher hooks.json detection can resolve
    # ../hooks/hooks.json relative to this bin/ directory -- the same
    # resolution the original bash script did via
    # `$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)`. Only set if unset, so
    # an explicit caller-provided override is never clobbered.
    os.environ.setdefault(
        "EDIT_LIVE_HOOK_SCRIPT_DIR", os.path.dirname(os.path.abspath(__file__))
    )

    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(f"edit-live-hook.sh: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(EXIT_TRANSPORT_FAILURE)
    except ImportError as exc:
        print(
            f"edit-live-hook.sh: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(EXIT_TRANSPORT_FAILURE)

    try:
        code = run_op_main("coordinator_core.ops.edit_live_hook", sys.argv[1:])
    except ImportError as exc:
        print(
            f"edit-live-hook.sh: coordinator_core.ops.edit_live_hook not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(EXIT_TRANSPORT_FAILURE)

    sys.exit(code)


if __name__ == "__main__":
    main()
