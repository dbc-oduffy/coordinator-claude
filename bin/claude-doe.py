#!/usr/bin/env python3
# Unix shebang — load-bearing, not decoration. Unlike its peers in this
# directory, this file is installed by BYTE COPY (shutil.copyfile via
# coordinator_core.install.wrapper_onto_path) as an extension-less, exec-bit
# POSIX target at <settings-home>/bin/claude-doe. The peers that lack a shebang
# at source (doctor.py, cross-repo-memo.py) are fine because their installed
# copies are GENERATED trampolines whose content is authored with one. Nothing
# injects a shebang into a byte copy, so without this line execve returns
# ENOEXEC, the shell falls back to parsing Python as sh, and no session can
# launch. Guard: coordinator_core/install/tests/test_installed_posix_targets_have_shebang.py
# claude-doe — persistent launch wrapper for the DoE-maximalist coordinator delivery shape.
#
# Purpose: resolve the DoE clone, validate its coordinator/ sub-directory, then exec claude
# with --plugin-dir pointing at that coordinator dir so skills/agents resolve live-external.
#
# 2026-07-22: ported from bash to naked Python 3 (mega-gate wave, plan row 6) — extensionless
# entrypoint, name UNCHANGED (callers depend on the bare `claude-doe` invocation; do not rename,
# do not add an extension). Behavior preserved byte-for-byte: exit codes, stdout/stderr text,
# env-var contract, argument parsing. Per review finding F7, the rung-3 fallback below now calls
# `resolve-coordinator-clone.py` directly (never a fresh reference to the retired
# `lib/resolve-coordinator-clone.sh` path) — see that rung's comment for detail. The bash
# original's `BASH_VERSINFO < 4` guard is dropped: it is moot under a python3 shebang.
#
# 2026-07-20: the wrapper previously also regenerated the settings.json hook block on every
# launch (self-heal for harness clobber bugs #22659/#28966/#28847) via gen-settings-hooks.sh:
# a sha256(hooks.json)-vs-stored-sentinel-hash comparison, ORed with a grep -qF total-absence
# catch, gated a per-launch call to gen-settings-hooks.sh (docs/plans/2026-07-12-claude-doe-settings-hooks-sentinel.md).
# That call was removed — measured ~1.3s added to EVERY session boot, and it no-op'd on the
# normal (unclobbered) path. Hook seeding is now an install-time-only concern; see whichever
# install-flow doc currently owns gen-settings-hooks.py invocation (not this wrapper). The
# sentinel/regen test suite (coordinator/bin/tests/test-claude-doe-sentinel.sh) was retired
# in full the same day — every case there covered this mechanism. To resurrect either the
# mechanism or its tests, `git log --follow` that path from before 2026-07-20 rather than
# re-deriving the cases from scratch.
#
# 2026-08-14: `--help`/`-h` is answered directly by this wrapper (see `_USAGE`
# and `main`'s first check), BEFORE any of the resolution rungs below run —
# `--help` must never require external state (a registered DoE clone, a
# reachable machine-local registry) to answer. Closes the klabauter publish-
# round ENTRYPOINT gate failure: the publish sandbox scrubs `repos.doe_claude`
# to the placeholder `repos.example_doctrine_repo`, which resolves to nothing,
# so rung 2 below used to fail before `--help` ever got a chance to short-
# circuit. This prints claude-doe's OWN usage text (the flags THIS wrapper
# adds) and does not forward to the wrapped `claude` binary's own --help —
# a working local install's `claude-doe --help` output therefore changed:
# it used to print the wrapped `claude` binary's help (forwarded post-
# resolution), it now prints this wrapper's own usage unconditionally. See
# `coordinator/bin/tests/test_hand_rolled_cli_help_sweep.py`.
#
# Spec backlink: docs/plans/2026-07-04-doe-maximalist-execution-plugin-dir.md § M2
# Mechanism record: docs/wiki/external-plugin-live-resolution.md § Documented behavior row 4
#   (--plugin-dir skill leg). The hook-delivery leg formerly documented here no longer applies.
#
# Resolution order for DoE clone root:
#   0. --doe-root <path> / --doe-root=<path> argv flag (highest — explicit
#      caller override, consumed, never forwarded to claude). Argv seam per
#      DoE DR-087 — lets the DoE shim pass a pointer-derived root through
#      argv instead of injecting it into the REPO_DOE_CLAUDE rung-1
#      authority slot (a value that CAN diverge from the registry). A
#      missing value, an explicitly-empty value (either form), or a value
#      that itself looks like a flag (starts with "--") all fail loud with
#      exit 2 rather than silently falling through to a lower rung. If
#      --doe-root is repeated (either form, in any combination), the LAST
#      occurrence wins — same last-wins convention as most CLI argv parsers;
#      not itself validated as an error.
#   1. REPO_DOE_CLAUDE env var (explicit operator override)
#   2. machine-local get repos.doe_claude  (registry — CANONICAL)
#   2.5. machine-local get plugin.mirrors.coordinator-claude.live_path
#        (registry — FALLBACK; plan C6/AC9 registry-namespace collision
#        resolution, only fires when rung 2 returned nothing)
#   3. Fallback: resolve-coordinator-clone --clone-root (EXTENSIONLESS python3
#        shim at the fixed out-of-tree path CLAUDE_HOME|HOME|USERPROFILE/.claude/
#        bin/ — NOT a `.py`; see rung 3 below). Reads the cold `.doe-root` pointer plus
#        the flat-layout OSS rung, so a wiped repos.doe_claude registry key still
#        resolves the clone durably.
#   4. fail-loud with remediation
#
# Recast (thin caller): docs/plans/2026-07-09-resolver-unification-v3split-01.md § C3 —
# rungs 1-2 (env, repos.doe_claude registry key) are UNCHANGED.
#
# Registry-namespace collision resolution (plan C6/AC9, § C6): repos.doe_claude
# and plugin.mirrors.coordinator-claude.live_path are RELATED but not identical
# facts — repos.doe_claude is the clone ROOT, while live_path is the live PLUGIN
# dir one level below it (<clone>/coordinator). This is a non-destructive
# READ-ORDER fix, not a schema restructure — repos.doe_claude stays canonical
# (rung 2), and rung 2.5 below reads live_path as a fallback when repos.doe_claude
# is unset, NORMALIZING it back to the clone root (strips the trailing
# "coordinator" segment — see rung 2.5) so a machine that only set live_path still
# resolves to the same clone root rung 2 would have returned.
#
# NEVER falls back to bare `claude` without --plugin-dir — a coordinator-less session is
# the footgun this wrapper exists to prevent.
#
# REMEDIATION TEXT IS A RUNNABLE SCRIPT, NEVER A SLASH COMMAND. Every failure in this
# module fires BEFORE a Claude Code session exists — that is the whole point of a launch
# wrapper. Telling the operator to "run /coordinator:install" at that moment names a
# remedy that by definition cannot run: the agentic surface is exactly what failed to
# come up. Emit a shell/python command line the operator can paste into a cold terminal.
# Guard: coordinator/tests/test_cold_path_remediation_is_runnable.py.
#
# Environment overrides (for testing / sandbox runs):
#   CLAUDE_DOE_DRY_RUN=1        — dry-run: prints the resolved exec line and exits without
#                                  execing claude. Side-effect-free. Same effect as --dry-run.
#   CLAUDE_DOE_PRINT_PLUGIN_DIR=1 — print ONLY the resolved coordinator --plugin-dir and exit,
#                                  without execing claude. Side-effect-free. Same effect as
#                                  --print-plugin-dir. This is the machine-readable seam the
#                                  Windows launchers use to fetch the plugin dir via bash so
#                                  the interactive claude TUI is launched NATIVELY (not through
#                                  bash -c, which corrupts the Windows console input mode).
#   CLAUDE_DOE_MACHINE_LOCAL_BIN — override path to machine-local binary; when set, bypasses
#                                  the PATH lookup entirely (testing only)
#   CLAUDE_DOE_NO_EXEC=1        — resolve and validate as normal, but skip the terminal
#                                  `exec claude`; exits 0 instead. Testing seam for exercising
#                                  clone resolution without launching the real binary.

import os
import shutil
import subprocess
import sys
from pathlib import Path, PureWindowsPath


def _machine_local_argv(ml_bin: str) -> list[str]:
    """Windows-safe invocation argv for the resolved machine-local CLI.

    shutil.which() honours PATHEXT and returns machine-local.CMD on Windows, but a
    list-form subprocess.run([..."machine-local.CMD"...]) mis-executes it: cmd.exe
    parses the .cmd body line-by-line and fails rc=255 (the classic Windows
    .cmd/.bat subprocess-exec trap; an extensionless POSIX shim hits WinError 193
    the same way, since CreateProcess cannot exec a non-PE). When the resolved
    shim has a co-located `_machine_local.py` implementation (the substrate always
    installs it in the same bin dir), invoke THAT directly under this interpreter —
    no shell/cmd.exe in the loop, immune to both traps. Mirrors
    coordinator_core.install._shared.resolve_machine_local_cli's `[sys.executable,
    _machine_local.py]` preference; kept inline because this wrapper is installed
    STANDALONE and cannot import coordinator_core.
    """
    impl = os.path.join(os.path.dirname(os.path.abspath(ml_bin)), "_machine_local.py")
    if os.path.isfile(impl):
        return [sys.executable, impl]
    return [ml_bin]


def _ml_bin_invocable(path: str) -> bool:
    """True if `path` (already known to be an existing file) is something
    this OS would actually launch directly, i.e. answers "will invoking this
    succeed" rather than "does this exist" — the question the bare-form
    presence gate in `_resolve_doe_clone` actually needs.

    Mirrors `coordinator_core.win_portability.is_executable`'s predicate
    (kept inline, not imported — see the caller's comment / this module's
    own STANDALONE constraint documented on `_machine_local_argv`):

    POSIX: `os.access(path, os.X_OK)` is meaningful here — real exec-bit
    query, not the Windows F_OK degradation this fix exists to avoid.

    Windows: NTFS has no exec bit, so X_OK always lies "yes" for any
    existing file. The real predicate is PATHEXT-resolvability: a file
    whose own extension is in PATHEXT is directly launchable; an
    extensionless file (this repo's own bareword CLI shim shape, e.g.
    `machine-local`) is NOT what CreateProcess launches on its own —
    Windows would need a PATHEXT-suffixed sibling for that, and this
    predicate is asked about `path` itself, not a sibling.
    """
    if os.name != "nt":
        return os.access(path, os.X_OK)
    pathext = os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD;.VBS;.VBE;.JS;.JSE;.WSF;.WSH;.MSC")
    exts = {ext.upper() for ext in pathext.split(";") if ext}
    _, suffix = os.path.splitext(path)
    return suffix.upper() in exts


def _resolve_claude_bin() -> str | None:
    """Resolve the `claude` binary on PATH.

    `shutil.which("claude")` on Windows only matches PATHEXT-suffixed
    candidates (.EXE/.CMD/.BAT/...) per CPython's implementation — unlike
    POSIX, it never also tries the bare, extensionless name. A real
    npm-global `claude` install commonly ships BOTH a `.cmd`/`.ps1` Windows
    wrapper AND a bare, shebang-launched entry point with no extension.
    Calling `shutil.which("claude")` for the whole PATH first (as a
    two-pass "try which, then fall back to a bare-name scan" shape) gets
    PATH-order precedence wrong: a `.cmd` match several directories further
    along PATH would win over a bare match in an EARLIER directory, because
    the fallback pass never runs at all once `shutil.which` succeeds
    anywhere. Walk PATH ourselves, one directory at a time, checking both
    the PATHEXT-suffixed candidates AND the bare name before moving to the
    next directory — this preserves PATH order across both candidate
    shapes, matching POSIX PATH-search semantics instead of Windows'
    extension-only default.

    Review: code-reviewer (Finding 1) — this is the SAME PATH/PATHEXT walk as
    `coordinator_core.launchable.which_path_ordered` (used by
    `coordinator_core.ops.coordinator_complete_entry._which_render_rollup_shim`
    for the identical CPython gap). Not delegated to that shared helper here
    because this file is installed STANDALONE (see `_machine_local_argv`
    above) and cannot import `coordinator_core` — genuinely can't be the same
    *callable*. Kept as a deliberate, explicitly-linked duplicate instead: a
    future PATHEXT-ordering fix belongs in `which_path_ordered` first, then
    mirrored here by hand; this docstring is the pointer that makes the
    "also update the standalone copy" step discoverable instead of silently
    skipped.
    """
    pathext = os.environ.get("PATHEXT", "").split(os.pathsep) if os.name == "nt" else []
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if not directory:
            continue
        candidates = [os.path.join(directory, "claude" + ext) for ext in pathext]
        candidates.append(os.path.join(directory, "claude"))
        for candidate in candidates:
            if os.path.isfile(candidate):
                return candidate
    return None


def _claude_exec_argv(claude_bin: str) -> list[str]:
    """Build the argv PREFIX (interpreter + script, or just the binary) used
    to exec a resolved `claude` binary.

    Mirrors `_machine_local_argv`'s shebang-awareness above. A bare,
    extensionless match reached only via `_resolve_claude_bin`'s manual PATH
    fallback is typically a shebang-launched script (`#!/usr/bin/env node`
    or similar) — `os.execv` cannot launch that directly on native Windows
    (CreateProcess cannot exec a non-PE file; WinError 193 "is not a valid
    Win32 application"), so the real-exec leg would still never actually
    reach `claude` even once resolved. Read the file's first line; a
    shebang gets resolved to its named interpreter via PATH (POSIX kernel
    semantics, done in userspace here) and prefixed. A `.exe`/`.cmd`/`.bat`
    match (the common case `shutil.which` returns) is left unchanged —
    Windows resolves those natively via CreateProcess/cmd.exe association.
    """
    try:
        with open(claude_bin, "r", encoding="utf-8", errors="ignore") as fh:
            first_line = fh.readline()
    except OSError:
        return [claude_bin]

    if not first_line.startswith("#!"):
        return [claude_bin]

    shebang_parts = first_line[2:].strip().split()
    if not shebang_parts:
        return [claude_bin]

    interpreter_name = os.path.basename(shebang_parts[0])
    interpreter_args = shebang_parts[1:]
    if interpreter_name == "env" and interpreter_args:
        interpreter_name = interpreter_args[0]
        interpreter_args = interpreter_args[1:]

    interpreter = shutil.which(interpreter_name)
    if not interpreter:
        return [claude_bin]

    return [interpreter, *interpreter_args, claude_bin]


def _resolve_home_for_clone_shim() -> str | None:
    """CLAUDE_HOME -> HOME -> USERPROFILE, first non-empty wins — mirrors
    coordinator_core.install._shared.require_home's env-var order (kept
    inline because this wrapper is installed STANDALONE and cannot import
    coordinator_core; see ``_machine_local_argv`` above for the same
    constraint). Unlike ``require_home``, this is a best-effort fallback
    rung (rung 3 of ``_resolve_doe_clone``), not a destructive-target guard,
    so it returns None rather than raising when nothing resolves — the
    caller then skips rung 3 and falls through to rung 4's fail-loud.

    Review: code-reviewer P1, 2026-07-28 — the prior
    ``os.environ.get("CLAUDE_HOME") or os.environ.get("HOME") or ""`` had no
    USERPROFILE rung (unreachable rung 3 on a native cmd.exe/PowerShell
    session with no HOME set) AND defaulted the no-match case to "", which
    made ``Path("") / ".claude"`` a RELATIVE path silently resolved against
    the process cwd instead of the "durable fallback" the caller's comment
    promises — a stray ``<cwd>/.claude/bin/resolve-coordinator-clone`` could
    have been picked up by accident. Returning None here instead makes the
    absence explicit and lets the caller skip the rung outright."""
    for var in ("CLAUDE_HOME", "HOME", "USERPROFILE"):
        value = os.environ.get(var) or ""
        if value:
            return value
    return None


def _clone_root_from_live_path(live_path: str) -> str:
    """Normalize a plugin.mirrors.coordinator-claude.live_path value to the DoE
    clone ROOT.

    live_path points at the live PLUGIN dir — the coordinator/ subdirectory
    (<clone>/coordinator) that --plugin-dir consumes — NOT the clone root, which
    is what repos.doe_claude holds and what the caller then appends "/coordinator"
    to. Strip one trailing "coordinator" segment when present (the standard nested
    DoE layout); a value without it (a flat OSS layout where the plugin IS the
    repo root) is returned unchanged. Separator-agnostic (Windows live_path values
    carry mixed / and \\ ).
    """
    norm = PureWindowsPath(live_path).as_posix().rstrip("/")
    head, _, tail = norm.rpartition("/")
    if tail == "coordinator" and head:
        return head
    return live_path


def _resolve_doe_clone(cli_doe_root: str = "") -> str | None:
    """Resolution order documented in the module header. Returns the clone
    root path, or None with a fail-loud message already written to stderr.
    """
    if cli_doe_root:
        return cli_doe_root

    repo_doe_claude = os.environ.get("REPO_DOE_CLAUDE", "")
    if repo_doe_claude:
        return repo_doe_claude

    # machine-local resolves the registry (repos.doe_claude) which in turn gives us
    # DOE_CLONE — so machine-local itself cannot be resolved FROM DOE_CLONE here
    # (that would be circular: it's the very lookup that produces DOE_CLONE).
    # Mirrors install.md's own canonical resolution snippet (§ 3.5a): override,
    # then PATH — no co-located-sibling guess, since machine-local is installed as
    # its own persistent PATH artifact by install/substrate.py, independent of
    # wherever this wrapper happens to live.
    # Review: code-reviewer F5 — CLAUDE_DOE_MACHINE_LOCAL_BIN bypasses the PATH
    # lookup so tests can inject a mock or absent binary deterministically.
    ml_bin_override = os.environ.get("CLAUDE_DOE_MACHINE_LOCAL_BIN", "")
    if ml_bin_override:
        ml_bin = ml_bin_override
        # Windows-safe invocation prefix — see _machine_local_argv (avoids the
        # machine-local.CMD list-form subprocess trap that fails rc=255 in the
        # cmd-spawned non-login bash env the launcher runs under).
        #
        # The presence gate runs on the RESOLVED argv target, not on `ml_bin`
        # itself. Gating on `ml_bin`'s exec bit first rejected the very shape
        # _machine_local_argv prefers — an extensionless shim whose co-located
        # `_machine_local.py` sibling carries the implementation and is invoked
        # under this interpreter, so the shim's own exec bit is never consulted
        # by anything. A shebang no longer implies an exec bit either
        # (POSIX-EXEC-ASSUMPTION-GUARD PM ruling, 8ca7213f2), so an exec-bit
        # check on the raw path is not a substitute for "can this run".
        ml_argv = _machine_local_argv(ml_bin)
        # Sibling form: [sys.executable, <impl>] — _machine_local_argv already
        # proved <impl> is a file, and sys.executable is this running process.
        # Bare form: [ml_bin] — that path is the thing exec'd directly by
        # subprocess.run below, so the real question is "will this OS actually
        # launch this path", not merely "does it exist". `os.access(ml_bin,
        # os.X_OK)` answers the wrong question on Windows — NTFS has no exec
        # bit, so X_OK there silently degrades to F_OK (existence-only) and
        # would pass an extensionless non-invocable file. `_ml_bin_invocable`
        # below mirrors `coordinator_core.win_portability.is_executable`'s
        # predicate (POSIX mode-bit check / Windows PATHEXT-resolvability
        # check) inline, NOT imported: this wrapper is installed STANDALONE
        # and cannot import coordinator_core (see `_machine_local_argv`'s own
        # docstring, same constraint, same reason).
        if ml_argv == [ml_bin] and not (os.path.isfile(ml_bin) and _ml_bin_invocable(ml_bin)):
            sys.stderr.write(f"claude-doe: machine-local not found at {ml_bin} and not on PATH\n")
            sys.stderr.write("  Remediation: python3 <engine-clone>/scripts/setup.py\n")
            return None
    else:
        found = shutil.which("machine-local")
        if not found:
            sys.stderr.write("claude-doe: machine-local not found on PATH\n")
            sys.stderr.write("  Remediation: python3 <engine-clone>/scripts/setup.py\n")
            return None
        ml_bin = found
        ml_argv = _machine_local_argv(ml_bin)

    ml_get_failed = False
    resolved = ""
    try:
        result = subprocess.run(
            [*ml_argv, "get", "repos.doe_claude"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        if result.returncode != 0:
            ml_get_failed = True
        else:
            resolved = result.stdout.strip()
    except OSError:
        ml_get_failed = True

    if not ml_get_failed and resolved:
        return resolved

    # Rung 2.5: fallback to plugin.mirrors.coordinator-claude.live_path (plan
    # C6/AC9 registry-namespace collision resolution — see file header).
    # Only fires when rung 2 (repos.doe_claude, canonical) returned nothing.
    resolved_fallback = ""
    try:
        result_fb = subprocess.run(
            [*ml_argv, "get", "plugin.mirrors.coordinator-claude.live_path"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        if result_fb.returncode == 0:
            resolved_fallback = result_fb.stdout.strip()
    except OSError:
        pass

    if resolved_fallback:
        # live_path is the live PLUGIN dir (<clone>/coordinator), not the clone
        # root — normalize it back before returning, or the caller's appended
        # "/coordinator" produces a "…/coordinator/coordinator" double and a
        # spurious "coordinator dir not found". See _clone_root_from_live_path.
        return _clone_root_from_live_path(resolved_fallback)

    # Rung 3: the DURABLE fallback — the unified resolver's --clone-root verb,
    # reached via the fixed-path out-of-tree shim (CLAUDE_HOME|HOME|USERPROFILE/
    # .claude/bin/resolve-coordinator-clone — see _resolve_home_for_clone_shim;
    # None means no home var resolved, so the rung is skipped rather than
    # deriving a cwd-relative path). This wrapper is installed STANDALONE (see
    # file header), so it cannot assume a co-located resolver lib; the fixed-path
    # shim is position-independent by design and solves that chicken-and-egg. The
    # shim reads the COLD `.doe-root` pointer (settings-home/machine-local/.doe-root
    # or ~/.claude/.doe-root) as well as the flat-layout OSS rung, so a WIPED
    # `repos.doe_claude` registry key — which the install-dogfood churn clears
    # intermittently — still resolves the clone here. Only reached when the
    # registry rungs above yielded nothing, preserving rungs 1-2 exactly as before.
    #
    # The entry point is EXTENSIONLESS (`resolve-coordinator-clone`, a python3-
    # shebang source file), NOT `resolve-coordinator-clone.py`: the 2026-07-22
    # de-bash port landed it under the bare name (plus a `.cmd` Windows sibling),
    # so the former `.py` path was a dangling reference that never fired and left
    # this rung dead on every machine. Invoke via [sys.executable, <bare path>],
    # which runs a python-source file regardless of on-disk name and sidesteps the
    # Windows .cmd/extensionless CreateProcess exec traps (same principle as
    # _machine_local_argv above). Supersedes the stale Review-F7 note that assumed
    # the resolver's de-bash port had not yet happened.
    home_for_shim = _resolve_home_for_clone_shim()
    fallback = ""
    if home_for_shim is not None:
        cc_home = Path(home_for_shim) / ".claude"
        resolver = cc_home / "bin" / "resolve-coordinator-clone"
        try:
            result_r3 = subprocess.run(
                [sys.executable, str(resolver), "--clone-root"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            if result_r3.returncode == 0:
                fallback = result_r3.stdout.strip()
        except OSError:
            pass

    if fallback:
        return fallback

    # Rung 4: fail-loud. Preserves the two original distinct diagnostics
    # (get failed vs. registered-but-empty) as the observable interface, now
    # emitted after the fallback rung has also been exhausted.
    if ml_get_failed:
        sys.stderr.write("claude-doe: machine-local get repos.doe_claude failed\n")
        sys.stderr.write("  Remediation: set REPO_DOE_CLAUDE=<path>, or python3 <engine-clone>/scripts/setup.py\n")
    else:
        sys.stderr.write(
            "claude-doe: repos.doe_claude and plugin.mirrors.coordinator-claude.live_path "
            "are both empty — DoE clone not registered\n"
        )
        sys.stderr.write("  Remediation: machine-local set repos.doe_claude <path>\n")
    return None


_USAGE = """\
claude-doe [--doe-root <path>] [--dry-run] [--print-plugin-dir] [claude args...]

Launch wrapper for the DoE-maximalist coordinator delivery shape: resolves
the DoE clone (see resolution order in this file's module header), then
execs the real `claude` binary with --plugin-dir pointing at that clone's
coordinator/ sub-directory. Any arguments not consumed below are forwarded
to `claude` unchanged.

Wrapper-only flags (consumed here, never forwarded to claude):
  --doe-root <path>       Explicit DoE clone root override (highest-priority
                           resolution rung; also accepts --doe-root=<path>).
  --dry-run               Print the resolved exec line and exit 0 without
                           launching claude.
  --print-plugin-dir      Print only the resolved --plugin-dir value and
                           exit 0.
  --help, -h              Show this message and exit 0.

--help/-h is answered here, directly, before any DoE-clone registry lookup
runs -- it must never require external state (a registered DoE clone, a
reachable machine-local registry) to answer. This is claude-doe's OWN usage
text, not the wrapped `claude` binary's --help output: run `claude-doe
<real claude args> --help` is not forwarded; if you need the wrapped
binary's own help text, resolve --print-plugin-dir yourself and invoke
`claude --plugin-dir <dir> --help` directly.
"""


def main(argv: list[str]) -> int:
    # -------------------------------------------------------------------
    # --help/-h answered here, first, before ANY clone/registry resolution
    # touches disk or spawns machine-local -- see docstring on _USAGE and
    # coordinator/bin/tests/test_hand_rolled_cli_help_sweep.py. A fresh
    # install with no DoE clone registered must still answer --help.
    # -------------------------------------------------------------------
    if "--help" in argv or "-h" in argv:
        print(_USAGE, end="")
        return 0

    # -------------------------------------------------------------------
    # Parse --doe-root / --dry-run from args BEFORE clone resolution (both
    # consumed here, never forwarded to claude); all other args pass through.
    # --doe-root takes rung 0 precedence over every env/registry rung below
    # (see module header "Resolution order").
    # -------------------------------------------------------------------
    dry_run = os.environ.get("CLAUDE_DOE_DRY_RUN", "0") == "1"
    print_plugin_dir = os.environ.get("CLAUDE_DOE_PRINT_PLUGIN_DIR", "0") == "1"
    cli_doe_root = ""
    passthrough_args: list[str] = []

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--dry-run":
            dry_run = True
        elif arg == "--print-plugin-dir":
            print_plugin_dir = True
        elif arg == "--doe-root":
            # Review: code-reviewer F1/F2 — reject a missing value, an
            # explicitly-empty value, and a following token that itself looks
            # like a flag (a typo'd "--doe-root --dry-run" would otherwise
            # silently swallow --dry-run as the path value). All three fail
            # loud with the same message + exit 2 as the original missing-
            # value case, since each is the same underlying ambiguity: no
            # usable path was actually supplied.
            if i + 1 >= len(argv) or not argv[i + 1] or argv[i + 1].startswith("--"):
                sys.stderr.write("claude-doe: --doe-root requires a path argument\n")
                return 2
            cli_doe_root = argv[i + 1]
            i += 1
        elif arg.startswith("--doe-root="):
            value = arg[len("--doe-root="):]
            if not value:
                # Review: code-reviewer F1 — explicit empty equals-form value
                # (--doe-root=) must fail loud rather than silently falling
                # through to REPO_DOE_CLAUDE/registry via Python truthiness.
                sys.stderr.write("claude-doe: --doe-root requires a path argument\n")
                return 2
            cli_doe_root = value
        else:
            passthrough_args.append(arg)
        i += 1

    doe_clone = _resolve_doe_clone(cli_doe_root)
    if doe_clone is None:
        return 1

    # -------------------------------------------------------------------
    # Validate clone and coordinator sub-directory
    # -------------------------------------------------------------------
    if not os.path.isdir(doe_clone):
        sys.stderr.write(f'claude-doe: DoE clone not found at "{doe_clone}"\n')
        sys.stderr.write(f'  Remediation: git clone <DoE-repo-url> "{doe_clone}"\n')
        sys.stderr.write("  Then: python3 <engine-clone>/scripts/setup.py\n")
        return 1

    doe_coordinator = os.path.join(doe_clone, "coordinator")
    if not os.path.isdir(doe_coordinator):
        sys.stderr.write(f'claude-doe: DoE coordinator/ dir not found at "{doe_coordinator}"\n')
        sys.stderr.write(f'  Remediation: git -C "{doe_clone}" pull   (clone predates the coordinator/ cutover)\n')
        return 1

    if dry_run:
        # Print the resolved exec line for human inspection; do not exec.
        # Review: code-reviewer F1/F6 — args are space-joined (not shell-quoted); display only, not eval.
        # Security: single %s so passthrough args containing % are never treated as format specifiers.
        suffix = f" {' '.join(passthrough_args)}" if passthrough_args else ""
        print(f"exec claude --plugin-dir {doe_coordinator}{suffix}")
        return 0

    if print_plugin_dir:
        # Print ONLY the resolved coordinator dir and exit. Side-effect-free.
        # This is the machine-readable seam the Windows launchers use to fetch
        # --plugin-dir via bash without launching the interactive claude TUI
        # THROUGH bash -c (which corrupts the Windows console input mode —
        # control keys such as Enter (Ctrl+M) and Ctrl+C arrive stripped to
        # plain letters). Single value, single line, no "exec claude" prefix.
        print(doe_coordinator)
        return 0

    if os.environ.get("CLAUDE_DOE_NO_EXEC", "0") == "1":
        return 0

    claude_bin = _resolve_claude_bin()
    if not claude_bin:
        sys.stderr.write("claude-doe: claude: command not found\n")
        return 127

    exec_prefix = _claude_exec_argv(claude_bin)
    full_argv = [*exec_prefix, "--plugin-dir", doe_coordinator, *passthrough_args]

    # Cross-session peer messaging is gated behind the harness's `ig()` predicate,
    # whose FIRST branch is this env var — it short-circuits ahead of both the
    # platform check and the GrowthBook flags (`tengu_harbor_kite`, and on Windows
    # the separate `tengu_harbor_kite_win`), all of which are off for us. Without
    # it the harness binds no inbox, enumerates zero peers, and refuses every send,
    # so the fleet's only working peer channel is writing into each other's files.
    #
    # `setdefault`: an operator who exports it themselves wins over this default.
    #
    # But the opt-out is NOT "0", and an earlier revision of this comment was wrong
    # to say so. The harness predicate is `if (env.CLAUDE_CODE_HARBOR_KITE) return
    # true` — plain JS truthiness on a string, where "0" is truthy. Exporting "0"
    # therefore defeats this `setdefault` and still opens the gate: the operator gets
    # the opposite of what they asked for. Only the EMPTY string defeats both, since
    # `setdefault` leaves an existing empty value alone and the predicate reads it as
    # falsy. Classifier and its named test:
    # `coordinator_core.session.messaging_gate`.
    #
    # Evidence this works, and the bundle-version floor it carries:
    # state/audits/2026-08-14-cross-session-messaging-gate-predicate-and-build-channel.md
    # Bundles before 2.1.232 return false on Windows BEFORE reading this var, so on
    # an older harness the line is inert rather than wrong.
    os.environ.setdefault("CLAUDE_CODE_HARBOR_KITE", "1")

    if os.name == "nt" or len(exec_prefix) > 1:
        # Windows has no exec(2). CPython maps `os.execv` onto the CRT's
        # P_OVERLAY spawn, which does NOT replace this process: it starts
        # `claude` as a separate process and terminates the parent
        # IMMEDIATELY, without waiting. That unblocks every caller up the
        # launch chain (python3 -> claude-doe.cmd -> the PowerShell `claude`
        # shim), so the interactive shell returns to its PROMPT while the
        # claude TUI is still live on the same console — two readers draining
        # one console input buffer. Keystrokes misroute between the TUI and
        # the shell, and the terminal's xterm focus-reporting events (DECSET
        # 1004: ESC[I focus-in / ESC[O focus-out) leak through as literal
        # `[I`/`[O` text, corrupting both the TUI and the shell prompt. The
        # same non-waiting spawn also DISCARDS the child's exit status: the
        # shell observes 0 no matter how claude exited.
        #
        # Measured on Windows 11 / PowerShell 7.6: the execv parent returns in
        # ~40ms against a 4s child, and reports rc=0 for a child that exits 42.
        #
        # `subprocess.run` waits, keeps this process as the console-owning
        # parent for claude's whole lifetime, and propagates the real exit
        # code. It also quotes argv correctly, which matters for the
        # shebang-interpreter case below on every platform.
        #
        # Negative-spec: do NOT "restore" os.execv on Windows as a
        # process-count optimisation — the extra frame is load-bearing.
        # Guard: coordinator/tests/test_claude_doe_launch_waits.py.
        #
        # len(exec_prefix) > 1 keeps the POSIX shebang case on subprocess.run
        # too: `os.execv` there builds its command line via a raw, unquoted
        # join, so a resolved interpreter path containing a space in one of
        # its directory components (a stock Git-for-Windows install path is
        # one common example) gets split mid-path and the launch fails ("No
        # such file or directory" from the misparsed remainder).
        result = subprocess.run(full_argv)
        return result.returncode

    # POSIX, direct binary: exec(2) is a genuine process replacement — the
    # shell's child IS claude, so there is no second console reader and no
    # exit code to propagate.
    os.execv(exec_prefix[0], full_argv)
    return 1  # pragma: no cover - unreachable, execv replaces the process on success


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
