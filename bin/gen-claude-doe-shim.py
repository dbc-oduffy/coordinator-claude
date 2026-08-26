# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""gen-claude-doe-shim.py — CLI trampoline over the claude-klabauter claude() shim
generator.

Renders the claude() shim from the coordinator template and wires exactly one
sentinel-guarded source block into the operator's interactive rc file,
including legacy-stopgap detection. DoE owns the contract/generator surface;
Claude-klabauter (coordinator_core.ops.gen_claude_doe_shim) owns the engine (DR-047).
Supports --check-only (validate without mutating live files) and --rc/
--template overrides.
"""
# gen-claude-doe-shim.py — CLI trampoline over claude-klabauter
# coordinator_core.ops.gen_claude_doe_shim.
#
# Finish-strangler port (BIG_PORT): the bash implementation (renders the claude()
# shim from the coordinator template, wires exactly one sentinel-guarded source
# block into the operator's interactive rc, legacy-stopgap detection) has been
# fully ported to coordinator_core/ops/gen_claude_doe_shim.py per DR-047 (DoE owns
# contract/generator, claude-klabauter owns engine). This file is now a thin trampoline
# over that claude-klabauter (engine) module — it lives in claude-klabauter post the
# 2026-07-22 executable-surface migration, resolving its DoE-owned template
# via coordinator_data_root.data_root(), not a co-located script path. See the
# claude-klabauter module's own docstring for the full design rationale (idempotency,
# dry-run safety, Windows temp-file portability, faithful-oracle negative-spec).
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
# Usage:
#   gen-claude-doe-shim.py                    -- render shim + wire rc source line
#   gen-claude-doe-shim.py --check-only       -- validate without mutating live files
#   gen-claude-doe-shim.py --rc <path>        -- override target rc file
#   gen-claude-doe-shim.py --template <path>  -- override template source path
#   gen-claude-doe-shim.py --shell powershell -- target a PowerShell profile
#                                                (default template follows the family)
#
# Exit codes: 0 on success (including an idempotent no-op re-run, or a clean
# --check-only pass); 1 on a business failure (unknown argument, missing flag
# value, template not found, rc sentinel block hand-modified, rc file
# uncreatable); 2 on a engine-root-resolution or import (transport) failure --
# a dedicated code, never a reused business rc, so install-maximalist.py's
# `run_required` wrapper (and any other caller) can distinguish "the install
# step itself failed" from "the claude-klabauter engine link is broken" -- this is an
# install-step gate, so failures must block the install rather than being
# swallowed, unlike the never-block auto-push shape. See
# coordinator_core.ops.gen_claude_doe_shim's own docstring § Transport-failure
# exit code note for the module-side half of this contract.
#
# Spec backlink: DoE-claude:pln-coordinator-maximalist-install-e73afa § C2
# Port backlink: docs/plans/2026-07-16-bash-clean-slate-residual-migration.md
# Prior bash implementation: see git log (gen-claude-doe-shim.py, 231 lines,
# retired on this cutover).

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402
from coordinator_data_root import data_root  # noqa: E402


def _default_template_path(shell_family: str = "bash") -> str:
    """Mirror the bash oracle's `${_script_dir}/../templates/shell/claude-doe-shim.sh.tmpl`
    default. Resolved via `coordinator_data_root.data_root()`'s co-located/
    DoE-resident two-rung chain, not a bare `__file__`-relative walk: the
    2026-07-22 executable-surface migration moved this trampoline into
    claude-klabauter while `templates/` stayed in DoE-claude (DR-047
    contract/engine split), so a `${script_dir}/../templates` walk no longer
    lands anywhere.

    Negative-spec: the default MUST branch on the shell family, symmetric with
    the engine's `_shim_filename`. A family-blind default renders the bash
    oracle's bytes into a file named `claude-doe-shim.ps1` and dot-sources it
    from a PowerShell profile — a render that succeeds, a `--check-only` that
    reports "Template valid", and a profile that fails at every subsequent
    shell start. An unrecognized family falls through to the bash template and
    is rejected downstream by the engine's own `--shell` validation."""
    stem = "claude-doe-shim.ps1.tmpl" if shell_family == "powershell" else "claude-doe-shim.sh.tmpl"
    return os.path.join(str(data_root("templates")), "shell", stem)


def _shell_family_from_argv(argv: list[str]) -> str:
    """Read `--shell <family>` out of argv without consuming or validating it —
    the engine owns both. Space-separated form only, matching the engine's
    parser.

    When `--shell` is absent the default comes from the ENGINE
    (`gen_claude_doe_shim._default_shell_family`), never a local literal: this
    function only picks the template, while the engine independently picks the
    shim filename and rc target from the same family. A local "bash" fallback
    made those two disagree on Windows — the engine selected the `.ps1` shim and
    the pwsh profile while this side handed it the bash `.sh` template, i.e. a
    POSIX shim body written to a PowerShell shim path."""
    for i, arg in enumerate(argv):
        if arg == "--shell" and i + 1 < len(argv):
            return argv[i + 1]
    from coordinator_core.ops.gen_claude_doe_shim import _default_shell_family

    return _default_shell_family()


def _import_runner():
    """Resolve the engine root, put it on sys.path, and import the in-process runner.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it -- this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.

    DR-276: the op is run through `coordinator_core.cli_entry.run_op_main`
    rather than by calling its `main` directly, so the paths it declares
    become a session scope-touch claim. Without that, the shim file and the
    rc-file source block this CLI writes are orphans at the
    `scoped_git_commit` sink.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(
            f"gen-claude-doe-shim.py: engine-root resolution failed: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)
    except ImportError as exc:
        print(
            "gen-claude-doe-shim.py: "
            f"coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    argv = sys.argv[1:]
    if "--template" not in argv and "-h" not in argv and "--help" not in argv:
        try:
            argv = argv + ["--template", _default_template_path(_shell_family_from_argv(argv))]
        except RuntimeError as exc:
            print(
                f"gen-claude-doe-shim.py: could not resolve a default "
                f"--template: {exc}",
                file=sys.stderr,
            )
            sys.exit(1)

    try:
        code = run_op_main("coordinator_core.ops.gen_claude_doe_shim", argv)
    except ImportError as exc:
        print(
            "gen-claude-doe-shim.py: "
            f"coordinator_core.ops.gen_claude_doe_shim not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(code)


if __name__ == "__main__":
    main()
