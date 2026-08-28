# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""probe-prereq.py -- install.md Phase 1 prerequisite probes/mutations that
have no existing landed CLI: git-lfs-enable (idempotent `git lfs install`
mutation gated by a functional check), and a thin `python3` passthrough to
coordinator_core.install.prereq_probe.probe_python() (Windows
App-Execution-Alias stub detection) -- so DoE-claude's
coordinator/commands/install.md Phase 1 can invoke these by name through the
settings-home forwarder instead of carrying narrated shell fences.

Read-only probes (`python3`) never mutate; `git-lfs-enable` mutates only when
NOT run with `--check-only` and only when the `git` + `git-lfs` binaries are
functional on PATH (advisory absence never hard-fails -- git-lfs is
coverage-ahead-of-need, not a coordinator hard requirement, matching
install.md's own "act-not-gate" framing for this step).

Each subcommand prints a single Step-Zero-shaped NDJSON line
(coordinator_core.install.step_zero_emit.emit_line contract: name/status/
severity/detail/remediation) to stdout and exits 0 on a "pass" status, 1
otherwise -- `git-lfs-enable` is the one exception, always exiting 0
(advisory, non-blocking) per its own subcommand contract below.

Subcommands:
  python3
      Thin passthrough to
      coordinator_core.install.prereq_probe.probe_python() -- detects the
      Windows App-Execution-Alias stub (a 0-byte `python3`/`python` that
      resolves on PATH but errors on run) as a distinct fail case from
      "not found".

  git-lfs-enable [--check-only]
      Functional check (git-lfs binary present AND `filter.lfs.clean`
      globally configured) via
      coordinator_core.install.prereq_probe.probe_git_lfs(). Under
      --check-only, reports state only -- never mutates. Otherwise, if `git
      lfs version` succeeds, runs the idempotent `git lfs install` mutation
      (plain install, NOT --force -- coexists with existing hooks) and
      re-probes to print the post-mutation state. Always exits 0: git-lfs is
      advisory coverage-ahead-of-need, never a hard install blocker.

Negative-spec: does NOT re-implement probe_python/probe_git_lfs's detection
logic -- delegates to coordinator_core.install.prereq_probe, the SSOT for
those two probes (see that module's own docstring). Only the mutation half
of git-lfs-enable is genuinely new here.

Negative-spec (bash-version, removed 2026-07-29): this CLI originally also
carried a `bash-version` subcommand (`shutil.which("bash")` then
`bash -c 'printf ... ${BASH_VERSINFO[0]} ...'` to read bash's own version,
matching sanctioned class (d)'s rationale -- asking the interpreter about
itself has no native substitute). It was removed, not ported, because
tracing its actual consumer found none: install.md's Phase 1a.0 text claimed
the check was "folded into setup.py --preflight", but
coordinator_core.ops.setup_chain_walker's --preflight explicitly enumerates
its probe set (python, uv, pwsh, ue, clone_auth, longpaths) and
coordinator_core.install.prereq_probe's own docstring negative-spec #1
explicitly scopes bash-version OUT of `_PROBE_ORDER` by design. This
subcommand was landed 2026-07-21 but never wired to any forwarder call site
in DoE-claude (see cross-repo/archive/2026-07-23-doe-claude-em-four-new-bin-
entrypoints-command-fence-extraction.md: "Not yet wired to any forwarder ...
a separate, later wave") and that wave never happened -- a repo-wide grep of
DoE-claude found zero references to `probe-prereq` or `bash-version` outside
this file's own docstring/tests. The one still-real bash-version gate lives
at coordinator_core/install/first_run.py `_bash_version_ok()` (sanctioned
class (d), a different site, driving the macOS brew-bash offer flow) and is
untouched by this removal. Do not re-add a `bash-version` subcommand here
without first re-establishing a live caller -- a probe with no consumer is
not a probe, it is dead code wearing a probe's docstring.

Spec backlink: coordinator/commands/install.md (DoE-claude) § 1a.3 (git-lfs
    enablement), § 1b.1 (python3 stub detection);
    docs/2026-07-29-debash-residual-sites-spec.md § Group F (this removal).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

_BIN_DIR = Path(__file__).resolve().parent


def _ensure_repo_root() -> Path:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_colocated_engine_on_path

    try:
        return Path(require_colocated_engine_on_path(__file__))
    except RuntimeError as _exc:
        print(f"{Path(__file__).name}: CLAUDE_KLABAUTER_ROOT resolution failed: {_exc}", file=sys.stderr)
        sys.exit(1)


def _run(argv: List[str], *, timeout: float = 10.0) -> Optional[subprocess.CompletedProcess]:
    """Uniform subprocess.run wrapper matching
    coordinator_core.install.prereq_probe's own `_run` shape: text-mode
    capture, stdin closed, no console flash on Windows, None on any
    transport-level failure (binary absent, timeout, OSError).

    Deliberate isolation boundary — do not convert to an in-process
    import. This is crash containment: a prereq probe of arbitrary
    external binaries must not be able to take this process down with
    it. Reason recorded in
    state/audits/2026-08-06-self-spawn-isolation-boundary-classification.md.
    """
    from coordinator_core.win_portability import no_console_creationflags

    try:
        return subprocess.run(
            argv,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            **no_console_creationflags(),
        )
    except (OSError, subprocess.TimeoutExpired, subprocess.SubprocessError):
        return None


def _cmd_python3(args: argparse.Namespace) -> int:
    del args
    from coordinator_core.install import prereq_probe

    line = prereq_probe.probe_python()
    sys.stdout.write(line)
    return 0 if json.loads(line)["status"] == "pass" else 1


def _cmd_git_lfs_enable(args: argparse.Namespace) -> int:
    """Check, and idempotently enable, git-lfs; emit `probe_git_lfs()` either way.

    Both spawns go through `_run`, so both are bounded and both are captured.
    `git lfs install` previously ran bare: no timeout (a hung git on a cold
    install path blocks the installer with nothing to report) and no capture
    (its "Git LFS initialized." line landed on the same stdout as the JSON
    result line below, which callers parse). The install's own return is
    discarded on purpose — `probe_git_lfs()` is the oracle for whether it took.
    """
    from coordinator_core.install import prereq_probe

    if args.check_only:
        sys.stdout.write(prereq_probe.probe_git_lfs())
        return 0

    lfs_ver = _run(["git", "lfs", "version"])
    if lfs_ver is not None and lfs_ver.returncode == 0:
        _run(["git", "lfs", "install"])

    sys.stdout.write(prereq_probe.probe_git_lfs())
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="probe-prereq",
        description="Install-time prereq probes/mutations with no other landed CLI "
        "(python3, git-lfs-enable).",
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_py = sub.add_parser("python3", help="Probe python3 for the Windows App-Execution-Alias stub.")
    p_py.set_defaults(func=_cmd_python3)

    p_lfs = sub.add_parser("git-lfs-enable", help="Check, and idempotently enable, git-lfs.")
    p_lfs.add_argument("--check-only", action="store_true")
    p_lfs.set_defaults(func=_cmd_git_lfs_enable)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _ensure_repo_root()
    from coordinator_core.install.step_zero_emit import emit_line  # noqa: F401

    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
