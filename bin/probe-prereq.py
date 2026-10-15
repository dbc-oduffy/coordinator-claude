# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""probe-prereq.py -- install.md Phase 1 prerequisite probe with no existing
landed CLI: a thin `python3` passthrough to
coordinator_core.install.prereq_probe.probe_python() (Windows
App-Execution-Alias stub detection) -- so coordinator-content-repo's
coordinator/commands/install.md Phase 1 can invoke it by name through the
settings-home forwarder instead of carrying narrated shell fences.

Read-only: never mutates. Each subcommand prints a single Step-Zero-shaped
NDJSON line (coordinator_core.install.step_zero_emit.emit_line contract:
name/status/severity/detail/remediation) to stdout and exits 0 on a "pass"
status, 1 otherwise.

Subcommands:
  python3
      Thin passthrough to
      coordinator_core.install.prereq_probe.probe_python() -- detects the
      Windows App-Execution-Alias stub (a 0-byte `python3`/`python` that
      resolves on PATH but errors on run) as a distinct fail case from
      "not found".

Negative-spec: does NOT re-implement probe_python's detection logic --
delegates to coordinator_core.install.prereq_probe, the SSOT for that probe.

Negative-spec (git-lfs-enable, removed 2026-10-13): the engine neither
enables nor recommends git-lfs; the subcommand and its `git lfs install`
mutation are gone. Do not re-add one.

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
in coordinator-content-repo (see cross-repo/archive/2026-07-23-coordinator-content-repo-em-four-new-bin-
entrypoints-command-fence-extraction.md: "Not yet wired to any forwarder ...
a separate, later wave") and that wave never happened -- a repo-wide grep of
Coordinator-content-repo found zero references to `probe-prereq` or `bash-version` outside
this file's own docstring/tests. The one still-real bash-version gate lives
at coordinator_core/install/first_run.py `_bash_version_ok()` (sanctioned
class (d), a different site, driving the macOS brew-bash offer flow) and is
untouched by this removal. Do not re-add a `bash-version` subcommand here
without first re-establishing a live caller -- a probe with no consumer is
not a probe, it is dead code wearing a probe's docstring.

Spec backlink: coordinator/commands/install.md (coordinator-content-repo) § 1b.1 (python3
    stub detection);
    docs/2026-07-29-debash-residual-sites-spec.md § Group F (this removal).
"""
from __future__ import annotations

INSTALL_CLASS = True

import argparse
import json
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


def _cmd_python3(args: argparse.Namespace) -> int:
    del args
    _ensure_repo_root()
    from coordinator_core.install import prereq_probe

    line = prereq_probe.probe_python()
    sys.stdout.write(line)
    return 0 if json.loads(line)["status"] == "pass" else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="probe-prereq",
        description="Install-time prereq probe with no other landed CLI (python3).",
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_py = sub.add_parser("python3", help="Probe python3 for the Windows App-Execution-Alias stub.")
    p_py.set_defaults(func=_cmd_python3)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _ensure_repo_root()
    from coordinator_core.install.step_zero_emit import emit_line  # noqa: F401

    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
