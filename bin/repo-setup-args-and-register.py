# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""repo-setup-args-and-register.py — naked-Python port of the residual bash
logic previously embedded in DoE-claude's `coordinator/skills/repo-setup/SKILL.md`.

Ports five concerns the skill's fenced bash blocks used to implement inline
(2026-07-23 debash campaign, chunk C-REPOSETUP):

  resolve-target-root
      `--root`/`--target` arg extraction (out of a raw `${ARGUMENTS:-}` string)
      + existence/worktree validation of the resolved target path. Was two
      separate fences in the skill (Phases preamble, "Target-root resolution")
      because the shell mechanic threaded `$_ARG_ROOT` through a second
      `$_TARGET_ROOT` variable before validating — ported as one subcommand
      since the extraction feeds directly into the validation with no
      independently-useful intermediate state.

  whoami-status
      The `coordinator_whoami` import-or-install 3-way gate (Phase 1
      "coordinator_whoami availability"): ready (already importable) /
      would-install (--check-only) / installed (pip -e succeeded) / failed
      (pip errored). Never halts the caller — mirrors the original's
      never-block contract (Phase 4's `ModuleNotFoundError` fallback remains
      the last-resort signal downstream).

  resolve-exec-summary-generator
      The `generate-exec-summary.py` path-fallback ladder (Phase 3d.5):
      prefer the coordinator plugin root's own `bin/generate-exec-summary.py`,
      fall back to the claude-klabauter sibling's copy when the plugin-root
      copy is absent (as of the 2026-07-22 `b644d5a9` migration, the
      plugin-root copy is now always absent in practice — this subcommand
      still implements the full ladder so a future re-vendor doesn't silently
      break the fallback).

  register-repo
      Repo-key derivation (Phase 3x "Fleet memo-destination registration"):
      lowercase basename, every non-alnum run collapsed to a single `_`,
      leading/trailing `_` stripped (mirrors cross-repo-memo's
      `_receiver_repo_key` resolution) + idempotent `machine-local
      has`/`set` registration under `repos.<key>` (only-if-absent — never
      clobbers an existing entry).

NOT ported (per dispatch brief scope): the `resolve-claude-klabauter-bin` resolver
ladder, the `_cc_trusted`/`_cc_root` guard preambles, the `_cc_claude_klabauter`
resolution ladder duplicated ~10x across the skill file, and the thin
single-CLI-invocation fences (`coordinator-ensure-post-commit-hook`,
`coordinator-ensure-prepare-commit-msg-hook`,
`coordinator_core.install.scaffold_structure`) — those are D1/D2's concern.

Machine-local reads/writes reuse `coordinator_core.install._shared`'s
`resolve_machine_local_cli`/`ml_get`/`ml_set` (the same resolver
install/uninstall already use) rather than re-deriving a machine-local
invocation ladder here.

Spec backlink: DoE-claude coordinator/skills/repo-setup/SKILL.md
  §§ "Target-root resolution", "coordinator_whoami availability",
  "3d.5. docs/exec-summary.md", "3x. Fleet memo-destination registration"
Port backlink: docs/plans (M3 chunk C-REPOSETUP, PM-authorized extirpation plan)

Exit codes: each subcommand documents its own contract in its docstring
below (`whoami-status` never exits non-zero by design, matching the
original bash's never-block posture; the others exit 0 on success, 1 on a
recoverable/expected miss, 2 on an infra/transport failure such as an
unresolvable machine-local CLI).
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

_BIN_DIR = Path(__file__).resolve().parent
_LIB_DIR = _BIN_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

_CLAUDE_KLABAUTER_ROOT = _BIN_DIR.parent.parent  # coordinator/bin/.. .. == claude-klabauter checkout root
if str(_CLAUDE_KLABAUTER_ROOT) not in sys.path:
    sys.path.insert(0, str(_CLAUDE_KLABAUTER_ROOT))

from coordinator_core.engine_root import coordinator_engine_root_env  # noqa: E402
from coordinator_core.win_portability import no_console_creationflags, no_console_passthrough_kwargs  # noqa: E402


# ---------------------------------------------------------------------------
# resolve-target-root
# ---------------------------------------------------------------------------

_ROOT_ARG_RE = re.compile(r".*--(?:root|target) (\S+)")


def extract_root_arg(arguments: str) -> str:
    """Extract a `--root <path>`/`--target <path>` value out of a raw argument
    string, mirroring the skill's `case`+`sed -En` pair:

        case "${ARGUMENTS:-}" in
          *--root\\ *|*--target\\ *) _ARG_ROOT="$(printf '%s' "${ARGUMENTS:-}" \\
            | sed -En 's/.*--(root|target) ([^ ]*).*/\\2/p')" ;;
        esac

    `.*` is greedy in both `sed -En` and Python `re`, so a string with more
    than one `--root`/`--target` occurrence resolves to the LAST one — same
    behavior as the original. Returns "" when neither flag is present.
    """
    match = _ROOT_ARG_RE.match(arguments)
    return match.group(1) if match else ""


def _is_git_worktree(path: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", path, "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            timeout=10,
            **no_console_creationflags(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def cmd_resolve_target_root(args: argparse.Namespace) -> int:
    """Resolve + validate `$_TARGET_ROOT`: the `--root`/`--target` value if
    given, else the caller's cwd. Fails loud (never silently falls back to
    cwd on an explicitly-passed-but-invalid path) — mirrors the skill's two
    `[ -d ... ] || { ... exit 1; }` / `git ... rev-parse ... || { ... exit 1; }`
    guards.

    Prints the resolved absolute path to stdout and exits 0 on success.
    Exits 1 with an `ERROR: ...` line on stderr when the resolved path does
    not exist, or exists but is not inside a git work tree.
    """
    arguments = args.arguments if args.arguments is not None else os.environ.get("ARGUMENTS", "")
    arg_root = extract_root_arg(arguments)
    target_root = arg_root or args.cwd

    if not os.path.isdir(target_root):
        print(
            f"ERROR: --root/--target path '{target_root}' does not exist — "
            "pass an existing directory",
            file=sys.stderr,
        )
        return 1

    if not _is_git_worktree(target_root):
        print(
            f"ERROR: --root/--target path '{target_root}' is not inside a git "
            "repo — repo-setup requires a git-tracked target",
            file=sys.stderr,
        )
        return 1

    print(os.path.abspath(target_root))
    return 0


# ---------------------------------------------------------------------------
# whoami-status
# ---------------------------------------------------------------------------


def cmd_whoami_status(args: argparse.Namespace) -> int:
    """The `coordinator_whoami` import-or-install 3-way gate:

        if python3 -c "import coordinator_whoami" 2>/dev/null; then
          whoami_status="ready"
        elif [ "${CHECK_ONLY:-0}" = "1" ]; then
          whoami_status="would-install"
        else
          if pip_stderr=$(python3 -m pip install -e "$CLAUDE_PLUGIN_ROOT/whoami/" 2>&1 >/dev/null); then
            whoami_status="installed"
          else
            whoami_status="failed"
          fi
        fi

    Always exits 0 — this is an informational/advisory gate the original
    never used to halt the skill (a `failed` status is surfaced to the PM
    via Phase 4's status table, not a fatal error). Prints
    `whoami_status: <status>` to stdout; on `failed`, also prints the
    captured pip stderr on a following `pip_stderr: ...` stdout line so a
    caller can fold it into its own report without re-parsing stderr.

    Deliberate isolation boundary — do not convert to an in-process
    import. This is a distinct interpreter: the whoami import/install
    check must run under the resolved project python (`args.python` /
    `COORDINATOR_PYTHON`), not this process's own interpreter. Reason
    recorded in
    state/audits/2026-08-06-self-spawn-isolation-boundary-classification.md.
    """
    python_bin = args.python or os.environ.get("COORDINATOR_PYTHON") or "python3"
    check_only = args.check_only or os.environ.get("CHECK_ONLY", "0") == "1"

    probe = subprocess.run(
        [python_bin, "-c", "import coordinator_whoami"],
        capture_output=True,
        text=True,
        **no_console_creationflags(),
    )
    if probe.returncode == 0:
        print("whoami_status: ready")
        return 0

    if check_only:
        print("whoami_status: would-install")
        return 0

    plugin_root = args.plugin_root or os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    whoami_dir = os.path.join(plugin_root, "whoami") if plugin_root else "whoami"
    install = subprocess.run(
        [python_bin, "-m", "pip", "install", "-e", whoami_dir],
        capture_output=True,
        text=True,
        **no_console_creationflags(),
    )
    if install.returncode == 0:
        print("whoami_status: installed")
        return 0

    print("whoami_status: failed")
    print(f"pip_stderr: {install.stderr.strip()}")
    return 0


# ---------------------------------------------------------------------------
# resolve-exec-summary-generator
# ---------------------------------------------------------------------------


def _resolve_claude_klabauter_root_for_exec_summary(settings_home: "str | None") -> "str | None":
    """Native mirror of the skill's claude-klabauter-root fallback chain used only by
    the exec-summary generator lookup:
    REPO_CLAUDE_KLABAUTER, falling back to COORDINATOR_ENGINE_ROOT (via the
    accessor), falling back to `<settings-home>/machine-local/.claude-klabauter-root`,
    falling back to `.claude/machine-local/.claude-klabauter-root` under CLAUDE_HOME or,
    absent that, the platform home directory (USERPROFILE on Windows, HOME or
    the passwd entry on POSIX).

    C23: was a bare ``os.environ.get("CLAUDE_KLABAUTER_ROOT")`` with no new-name rung at
    all -- silently dark since C14 closed the dual-read window. Routed through
    the accessor rather than adding a second raw read of the new name.
    """
    candidate = os.environ.get("REPO_CLAUDE_KLABAUTER") or coordinator_engine_root_env(__name__)
    if candidate:
        return candidate

    home = os.environ.get("CLAUDE_HOME") or os.path.expanduser("~")
    resolved_settings_home = (
        settings_home
        or os.environ.get("COORDINATOR_SETTINGS_HOME")
        or os.path.join(home, ".coordinator-claude-settings")
    )
    for pointer_path in (
        os.path.join(resolved_settings_home, "machine-local", ".claude-klabauter-root"),
        os.path.join(home, ".claude", "machine-local", ".claude-klabauter-root"),
    ):
        try:
            with open(pointer_path, "r", encoding="utf-8") as handle:
                value = handle.read().strip()
            if value:
                return value
        except OSError:
            continue
    return None


def cmd_resolve_exec_summary_generator(args: argparse.Namespace) -> int:
    """Path-fallback ladder for `generate-exec-summary.py`:

        _cc_gen="$_cc_root/bin/generate-exec-summary.py"
        if [ ! -f "$_cc_gen" ]; then
          _cc_claude_klabauter="${REPO_CLAUDE_KLABAUTER:-${CLAUDE_KLABAUTER_ROOT:-<pointer-file lookups>}}"
          [ -n "$_cc_claude_klabauter" ] && _cc_gen="$_cc_claude_klabauter/coordinator/bin/generate-exec-summary.py"
        fi

    Prints the resolved absolute path to stdout and exits 0 when a
    generator was found. Exits 1 (no stdout, a warning on stderr) when
    neither the coordinator-plugin-root copy nor the claude-klabauter sibling
    copy resolves — this is the "exec-summary generation skipped" case; the
    original degraded gracefully here rather than failing the whole skill,
    so callers should treat exit 1 as "skip, don't abort".

    With `--run`, additionally invokes the resolved generator via
    `<python> <path>` (stdio inherited) and exits with ITS return code
    instead.

    Deliberate isolation boundary — do not convert to an in-process
    import. This is a distinct interpreter: the generator is resolved and
    invoked under the target python, not this process's own interpreter.
    Reason recorded in
    state/audits/2026-08-06-self-spawn-isolation-boundary-classification.md.
    """
    coordinator_root = args.coordinator_root or os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    candidate = os.path.join(coordinator_root, "bin", "generate-exec-summary.py") if coordinator_root else ""

    resolved = candidate if candidate and os.path.isfile(candidate) else None
    if resolved is None:
        claude_klabauter_root = _resolve_claude_klabauter_root_for_exec_summary(args.settings_home)
        if claude_klabauter_root:
            fallback = os.path.join(claude_klabauter_root, "coordinator", "bin", "generate-exec-summary.py")
            if os.path.isfile(fallback):
                resolved = fallback

    if resolved is None:
        print(
            "[repo-setup-args-and-register] generate-exec-summary.py unresolvable "
            "(checked coordinator/bin/ and the claude-klabauter sibling via "
            "REPO_CLAUDE_KLABAUTER/CLAUDE_KLABAUTER_ROOT/.claude-klabauter-root) — exec-summary "
            "generation skipped",
            file=sys.stderr,
        )
        return 1

    if args.run:
        python_bin = args.python or "python"
        proc = subprocess.run(
            [python_bin, resolved],
            **no_console_passthrough_kwargs(),
        )
        return proc.returncode

    print(resolved)
    return 0


# ---------------------------------------------------------------------------
# register-repo
# ---------------------------------------------------------------------------

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def derive_repo_key(repo_name: str) -> str:
    """Lowercase basename, non-alnum runs collapsed to a single `_`,
    leading/trailing `_` stripped. Mirrors:

        tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '_' | sed 's/^_//;s/_$//'

    and matches cross-repo-memo's `_receiver_repo_key` resolution
    (`shortname.replace("-", "_")` generalized to any non-alnum run).
    """
    return _NON_ALNUM_RE.sub("_", repo_name.lower()).strip("_")


def cmd_register_repo(args: argparse.Namespace) -> int:
    """Idempotent `repos.<key>` machine-local registration:

        _repo_name="$(basename "$(pwd)")"
        _repo_key="$(... derive_repo_key ...)"
        if machine-local has "repos.$_repo_key" >/dev/null 2>&1; then
          echo "repos.$_repo_key already registered — leaving as-is."
        else
          machine-local set "repos.$_repo_key" "$(pwd)"
        fi

    Only-if-absent — never clobbers an existing `repos.<key>` entry. Exits
    0 on success (registered, already-registered, or would-register under
    `--check-only`). Exits 2 when no machine-local CLI can be resolved
    (an infra/transport failure, not a routine registry miss).
    """
    from coordinator_core.install._shared import ml_get, ml_set, resolve_machine_local_cli

    path = os.path.abspath(args.path or os.getcwd())
    repo_name = os.path.basename(path.rstrip(os.sep))
    repo_key = derive_repo_key(repo_name)
    registry_key = f"repos.{repo_key}"

    plugin_root = args.plugin_root or os.environ.get("CLAUDE_PLUGIN_ROOT")
    if resolve_machine_local_cli(plugin_root) is None:
        print(
            f"register-repo: cannot resolve a machine-local CLI — unable to "
            f"register {registry_key}",
            file=sys.stderr,
        )
        return 2

    existing = ml_get(registry_key, plugin_root=plugin_root)
    if existing:
        print(f"{registry_key} already registered — leaving as-is.")
        return 0

    if args.check_only:
        print(f"{registry_key} would be registered -> {path}")
        return 0

    ok = ml_set(registry_key, path, plugin_root=plugin_root)
    if not ok:
        print(f"register-repo: machine-local set failed for {registry_key}", file=sys.stderr)
        return 2

    print(f"{registry_key} registered -> {path}")
    return 0


# ---------------------------------------------------------------------------
# argv wiring
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="repo-setup-args-and-register.py",
        description="Naked-Python port of repo-setup's residual bash logic (see module docstring).",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    p_root = subparsers.add_parser(
        "resolve-target-root",
        help="Extract + validate --root/--target from a raw ARGUMENTS string",
    )
    p_root.add_argument("--arguments", default=None, help="Raw argument string (default: $ARGUMENTS)")
    p_root.add_argument("--cwd", default=os.getcwd(), help="Fallback cwd when --root/--target absent")
    p_root.set_defaults(func=cmd_resolve_target_root)

    p_whoami = subparsers.add_parser(
        "whoami-status",
        help="coordinator_whoami import-or-install 3-way gate",
    )
    p_whoami.add_argument("--plugin-root", default=None, help="Coordinator plugin root (default: $CLAUDE_PLUGIN_ROOT)")
    p_whoami.add_argument("--check-only", action="store_true", help="Report would-install instead of installing")
    p_whoami.add_argument("--python", default=None, help="Python interpreter (default: $COORDINATOR_PYTHON or python3)")
    p_whoami.set_defaults(func=cmd_whoami_status)

    p_exec = subparsers.add_parser(
        "resolve-exec-summary-generator",
        help="Resolve (and optionally run) generate-exec-summary.py via the coordinator-root/claude-klabauter-sibling fallback ladder",
    )
    p_exec.add_argument("--coordinator-root", default=None, help="Coordinator plugin root (default: $CLAUDE_PLUGIN_ROOT)")
    p_exec.add_argument("--settings-home", default=None, help="Settings-home override (default: $COORDINATOR_SETTINGS_HOME)")
    p_exec.add_argument("--run", action="store_true", help="Invoke the resolved generator instead of just printing its path")
    p_exec.add_argument("--python", default=None, help="Python interpreter used with --run (default: python)")
    p_exec.set_defaults(func=cmd_resolve_exec_summary_generator)

    p_register = subparsers.add_parser(
        "register-repo",
        help="Derive repo key + idempotently register repos.<key> in the machine-local registry",
    )
    p_register.add_argument("--path", default=None, help="Repo path to register (default: cwd)")
    p_register.add_argument("--plugin-root", default=None, help="Coordinator plugin root (default: $CLAUDE_PLUGIN_ROOT)")
    p_register.add_argument("--check-only", action="store_true", help="Report would-register instead of registering")
    p_register.set_defaults(func=cmd_register_repo)

    return parser


def main(argv: "list[str] | None" = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
