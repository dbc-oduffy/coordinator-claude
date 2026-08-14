"""
verify-snippet-sync — CONSOLIDATED CLI trampoline over claude-klabauter
coordinator_core.snippet_sync.verify, replacing the 7 retired
`verify-<name>-sync.sh` scripts (reviewer-calibration, docs-checker-consumption,
plan-coverage-check-consumption, prior-art-check-consumption,
quota-self-detect-preamble, meta-ask-preamble, text-only-recovery-preamble).

Usage:
  verify-snippet-sync <name>            Verify all consumers match the canonical snippet.
                                         Exit non-zero on mismatch/missing.
  verify-snippet-sync <name> --check    Alias for the default mode (explicit).
  verify-snippet-sync <name> --fix      Overwrite mismatched sentinel blocks with the
                                         canonical snippet (auto-inserts on snippets with
                                         allow_insert=True in registry.toml — currently
                                         quota-self-detect-preamble only).
  verify-snippet-sync <name> --list     List consumers. For registry-driven snippets this
                                         is the CANONICAL UNIVERSE (all registered consumer
                                         paths, regardless of current on-disk state); for
                                         scan-driven snippets (meta-ask-preamble,
                                         text-only-recovery-preamble) it is the discovered set.

<name> must be enrolled in snippets/registry.toml (`snippet-registry list-snippets`
enumerates the valid names).

Env overrides:
  CLAUDE_PLUGIN_ROOT        — plugin root (default: resolved via doe_root(),
                               see _resolve_plugin_root() docstring below)
  COORDINATOR_CONTENT_ROOT  — overrides plugin-root-relative consumer resolution only
                               (cache-install seam; sibling/conditional consumers stay
                               anchored to the true plugin root regardless)
  NODE_BIN                  — unused (no node dependency post-port; accepted+ignored
                               for invocation-shape compatibility with old callers)

Exit codes:
  0  — verify: all consumers match / --fix: no unhandled errors / --list: printed
  1  — business outcome (verify: at least one consumer MISSING/MISMATCH), OR a
       transport failure: CLAUDE_KLABAUTER_ROOT resolution, coordinator_core.snippet_sync.verify
       import failure, or an unresolvable coordinator doctrine repo root (see _resolve_plugin_root()).
  2  — CLI usage error (missing/`--help` argv)

Spec backlink: DoE scratch/subagent-sandbox/bash-to-python-engine-migration/recipe-t3a-g3.md § 6
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_BIN_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_BIN_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
# machine_local_resolve.py imports from the coordinator_core package
# (win_portability) at module level -- that package is resolvable only from
# the repo root, not from _LIB_DIR, so it must be on sys.path too or the
# import below raises ModuleNotFoundError every time this CLI runs as a
# subprocess (which is how every real caller invokes it).
_REPO_ROOT = os.path.dirname(os.path.dirname(_BIN_DIR))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402
from coordinator_registry import _DoeUnresolvable, doe_root  # noqa: E402
from machine_local_resolve import resolve_machine_local_bin  # noqa: E402


def _resolve_plugin_root() -> Path:
    """Resolve the plugin root (coordinator/) that owns snippets/ and the
    consumer agent prompts this CLI checks for drift.

    Env var CLAUDE_PLUGIN_ROOT wins if set, returned verbatim. Otherwise
    resolves via doe_root() (see that function's own docstring for its
    env-var/machine-local resolution chain) and returns
    <doe_root()>/coordinator.

    This does NOT derive from this script's own __file__ location. b644d5a9
    migrated this executable to claude-klabauter while snippets/ (and every
    registry-driven consumer prompt) stayed in DoE-claude — self-location
    now resolves to <claude-klabauter>/coordinator, which has no snippets/ at all. Do
    not "restore" __file__-based resolution to regain parity with the
    pre-migration layout — that parity is exactly what caused the break
    once this file moved repos.

    Fails loud (sys.exit(1)) if doe_root() cannot resolve: this is a gate
    script, not a never-block hook, so an unresolvable DoE root must not
    degrade to a silent scan of the wrong tree.
    """
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env:
        return Path(env)
    try:
        root = doe_root()
    except _DoeUnresolvable as exc:
        print(
            "verify-snippet-sync: cannot resolve the coordinator doctrine repo root "
            f"({exc}). Set repos.doe_claude in the machine-local registry, or set "
            "the DOE_ROOT env var, or set CLAUDE_PLUGIN_ROOT directly.",
            file=sys.stderr,
        )
        sys.exit(1)
    return Path(root) / "coordinator"


def _resolve_cs_lib(plugin_root: Path) -> "Path | None":
    """Historical coordinator-session.sh ladder mirroring the 7 retired
    originals' `_CS_LIB` resolution: plugin_root/lib/coordinator-session.sh
    first (covers both the CLAUDE_PLUGIN_ROOT-set and default-relative-to-
    script cases, since plugin_root already folds that env var in), else the
    ~/.claude/.doe-root pointer file's coordinator/lib/coordinator-session.sh.
    coordinator-session.sh was deleted 2026-07-22 (session-family-repoint
    C4a) — both rungs now resolve to None and this vestigial ladder is kept
    only for the legacy-consumer resolution shape it still feeds `run()`.
    """
    direct = plugin_root / "lib" / "coordinator-session.sh"
    if direct.is_file():
        return direct
    doe_root_file = Path(
        os.environ.get("CLAUDE_HOME")
        or os.environ.get("HOME")
        or os.environ.get("USERPROFILE")
        or os.path.expanduser("~")
    ) / ".claude" / ".doe-root"
    try:
        doe_root_text = doe_root_file.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not doe_root_text:
        return None
    candidate = Path(doe_root_text) / "coordinator" / "lib" / "coordinator-session.sh"
    return candidate if candidate.is_file() else None


def main() -> None:
    args = sys.argv[1:]
    if "--help" in args or "-h" in args:
        sys.stdout.write(__doc__ or "")
        sys.exit(0)
    if not args:
        # Bare/no-argument invocation is a usage error, not documented help:
        # fail loud on stderr so a no-arg call can never be misread as a
        # passing verification gate.
        sys.stderr.write(__doc__ or "")
        sys.exit(2)

    name = args[0]
    mode = args[1] if len(args) > 1 else "verify"

    try:
        claude_klabauter_root = _resolve_claude_klabauter_root()
    except RuntimeError as exc:
        print(f"verify-snippet-sync: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(1)
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    try:
        from coordinator_core.snippet_sync.verify import run
    except ImportError as exc:
        print(
            f"verify-snippet-sync: coordinator_core.snippet_sync.verify not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    plugin_root = _resolve_plugin_root()
    content_root_env = os.environ.get("COORDINATOR_CONTENT_ROOT")
    content_root = Path(content_root_env) if content_root_env else None

    outcome = run(
        name,
        mode,
        plugin_root=plugin_root,
        content_root=content_root,
        machine_local_bin=resolve_machine_local_bin(script_dir),
        cs_lib=_resolve_cs_lib(plugin_root),
    )

    # `run()`'s SyncOutcome.lines carry native-OS separators for verify/--fix
    # (an internal Path/os.path reopen-and-compare surface, deliberately not
    # normalized -- see coordinator_core/snippet_sync/verify.py's --list
    # block). `--list` output is a display/consumer-enumeration surface, not
    # a filesystem handle a caller reopens, so normalize it to POSIX here at
    # the CLI boundary rather than in the engine.
    for line in outcome.lines:
        print(Path(line).as_posix() if mode == "--list" else line)
    for line in outcome.stderr_lines:
        print(line, file=sys.stderr)
    sys.exit(outcome.exit_code)


if __name__ == "__main__":
    main()
